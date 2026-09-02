"""
CHESCA（Community-based Hierarchical Energy Systems Coordination Algorithm）

2023 CityLearn 挑战赛冠军算法的核心 Agent 实现。

============================================================================
【5 个阶段】
============================================================================

  观测 observations 进入
       │
       ▼
  ┌─ 阶段1: ForecastAgent.compute_forecast() ─────────────────────────┐
  │  · 记录当前观测到历史                                              │
  │  · XGBoost 集成预测未来 tau 步：室外温度、光伏、负荷、热水需求      │
  └───────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌─ 阶段2: initial_actions() — 每栋楼独立生成初稿 ──────────────────┐
  │  正常：PID 定冷机 + 规则定 DHW + 电池=0                            │
  │  停电：限电下保冷 + 储热优先 + 光伏/电池平衡                        │
  └───────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌─ 阶段3: get_future_cooling/dhw_demands() ─────────────────────────┐
  │  滚动预测未来 tau 步冷机、DHW 设备用电（供阶段4 树搜索用）          │
  └───────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌─ 阶段4: refine_actions_with_battery_controller() ─────────────────┐
  │  仅第 2 步起执行（首步无历史负荷）                                  │
  │  BatteryController 树搜索优化电池充放电，使社区净负荷接近历史均值    │
  │  负荷过高 → 减 DHW/冷机；负荷过低 → 加 DHW 加热                   │
  └───────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌─ 阶段5: ResMARL 残差修正（默认关闭）──────────────────────────────┐
  │  a_final = clip(a_base + α · mask · Δa_RL)                         │
  │  阶段0：无策略网络，enabled=False 或 α=0 时严格恒等（基线冻结）    │
  └───────────────────────────────────────────────────────────────────┘
       │
       ▼
  ┌─ 阶段6: compute_elec_consumption_values() ────────────────────────┐
  │  净用电 = 不可调负荷 + 冷机 + DHW + 电池 − 光伏                    │
  │  写入历史，下一步 refine 会用到                                     │
  └───────────────────────────────────────────────────────────────────┘
       │
       ▼
  返回动作 [[DHW_0, ELE_0, TMP_0, DHW_1, ...]] 给 env.step()

每建筑 3 维动作（按 building 顺序拼接）：
  [DHW_storage, electrical_storage, cooling_device] × n_buildings
  DHW_storage        — 生活热水储热罐：正=加热，负=放热
  electrical_storage — 电池：正=充电，负=放电（动作是 SOC 变化比例，如 0.05）
  cooling_device     — 冷机：控制制冷出力（PID 输出）
============================================================================
"""

import numpy as np
from typing import List
from citylearn.agents.base import Agent
from citylearn.citylearn import CityLearnEnv
from checa.cooling_device_controller.cooling_device_controller import CoolingDeviceController
from checa.forecast_agent.forecasting_agent import ForecastAgent
from checa.battery_control_search.battery_controller import BatteryController
from checa.residual import ResidualCorrector, parse_residual_config
from checa.utils import get_observation_names_with_building, observation_value


class Checa(Agent):
    """
    CHESCA 分层协调控制 Agent。

    继承 citylearn.agents.base.Agent，仅支持 central_agent=True（单智能体统一决策）。
    """

    def __init__(self, env: CityLearnEnv, params=None, **kwargs):
        """
        初始化预测器、冷机 PID 控制器、电池树搜索控制器及历史缓存。

        参数 env：WrapperEnv，含 buildings_metadata 与观测/动作空间。
        参数 params：超参字典；为 None 时使用论文/调参后的默认配置。
        """
        super().__init__(env, **kwargs)
        self.env = env
        self.n_buildings = len(self.env.buildings_metadata)
        self.observation_names = env.observation_names
        # 将重名观测（如多栋 solar_generation）展开为 solar_generation_0, _1, ...
        self.observation_names_b = get_observation_names_with_building(env.observation_names[0])
        self.seen_steps = 0  # 当前 episode 已执行步数

        # 各小时电池 SOC 下限（正常无停电时），用于树搜索约束
        min_soc_per_hour = {
            "0": 0.60, "1": 0.65, "2": 0.72, "3": 0.78, "4": 0.80, "5": 0.85,
            "6": 0.80, "7": 0.75, "8": 0.70, "9": 0.60, "10": 0.50, "11": 0.60,
            "12": 0.65, "13": 0.65, "14": 0.70, "15": 0.70, "16": 0.70, "17": 0.65,
            "18": 0.70, "19": 0.60, "20": 0.60, "21": 0.60, "22": 0.60, "23": 0.55,
        }

        default_params = {
            'tau': 1,              # 预测/优化向前看的步数
            'balance_type': 'C',   # 电池树搜索适应度函数类型（A/B/C）
            'dt': 0.05,            # 电池动作离散化步长（SOC 比例）
            'max_soc_normal': 0.99,
            'min_soc_per_hour': min_soc_per_hour,
            'max_soc_outage': 0.87,
            'B_low': 1.18,         # 负荷低于均值−B_low×std 时触发增负荷
            'B_high': 1.0,         # 负荷高于均值+B_high×std 时触发减负荷
            'TMP_max_reduction_percent': 0.0,
            'peak_TMP_reduction': 0.0,
            'max_soc_reduction_in_outage': 0.70,
            'increase_scale_outage': 1.166,
            # ResMARL 残差层（阶段0：默认关闭，保证与纯 CHESCA 基线一致）
            'resmarl_enabled': False,
            'residual_alpha': 0.0,
            'residual_action_mask': {'dhw': False, 'ele': True, 'tmp': False},
            'resmarl_policy_path': None,
            'resmarl_after_safety': True,
        }
        if params is not None:
            self.params = {**default_params, **params}
        else:
            self.params = default_params

        self.residual_config = parse_residual_config(self.params)
        self.residual_corrector = ResidualCorrector(self.n_buildings, self.residual_config)
        self.residual_corrector.set_observation_names(self.observation_names_b)
        self._trace_residual_meta = {}

        # ---------- 子模块：时序预测 ----------
        self.forecast_agent = ForecastAgent(env, self.params['tau'], self.observation_names_b)
        self.forecasts = None  # 每步 compute_forecast 的结果

        # ---------- 历史缓存：用于负荷平衡与 ramping 优化 ----------
        self.elec_consumption_history = [[] for _ in range(self.n_buildings)]
        self.elec_consumption_history_per_hour = [[[] for _ in range(24)] for _ in range(self.n_buildings)]
        self.elec_consumption_prediction_history = [[] for _ in range(self.n_buildings)]

        self.predicted_dhw_device_demand = [0.0 for _ in range(self.n_buildings)]
        self.predicted_cooling_demand = [0.0 for _ in range(self.n_buildings)]
        self.predicted_battery_demand = [0.0 for _ in range(self.n_buildings)]
        self.future_dhw_demands = None
        self.future_cooling_demands = None

        # 每建筑一个冷机 PID + XGBoost 辅助控制器
        self.cooling_device_controller = [
            CoolingDeviceController(self.env.buildings_metadata[b], b, self.observation_names_b)
            for b in range(self.n_buildings)
        ]

        # ---------- 电池物理参数（来自 schema 元数据）----------
        self.battery_capacities = np.array([
            self.building_metadata[b]['electrical_storage']['capacity'] for b in range(self.n_buildings)
        ])
        self.battery_nominal_powers = np.array([
            self.building_metadata[b]['electrical_storage']['nominal_power'] for b in range(self.n_buildings)
        ])
        self.battery_efficiency_curves = np.array([
            self.building_metadata[b]['electrical_storage']['power_efficiency_curve'] for b in range(self.n_buildings)
        ])
        self.battery_capacity_power_curves = np.array([
            self.building_metadata[b]['electrical_storage']['capacity_power_curve'] for b in range(self.n_buildings)
        ])
        self.min_battery_soc = np.array([
            1 - self.building_metadata[b]['electrical_storage']['depth_of_discharge'] for b in range(self.n_buildings)
        ])
        self.cur_battery_soc = np.array([0.0 for _ in range(self.n_buildings)])

        # 每建筑一个电池 MCTS/树搜索控制器
        self.battery_controller = [
            BatteryController(
                self.battery_capacities[b], self.params['tau'], self.params['min_soc_per_hour'],
                self.params['dt'], self.params['max_soc_normal'], self.params['balance_type']
            )
            for b in range(self.n_buildings)
        ]

        # ---------- DHW（生活热水）设备/储热参数 ----------
        self.dhw_storage_capacity = np.array([
            self.building_metadata[b]['dhw_storage']['capacity'] for b in range(self.n_buildings)
        ])
        self.dhw_device_efficiency = np.array([
            self.building_metadata[b]['dhw_device']['efficiency'] for b in range(self.n_buildings)
        ])
        self.dhw_device_nominal_powers = np.array([
            self.building_metadata[b]['dhw_device']['nominal_power'] for b in range(self.n_buildings)
        ])
        self.cur_dhw_soc = np.array([0.0 for _ in range(self.n_buildings)])

        # DHW 加热计划：凌晨 2–5 点、下午 14 点倾向储热
        self.cur_dhw_heat_schedules = np.zeros((self.n_buildings, 24))
        self.cur_dhw_heat_schedules[:, 2:6] = 0.2
        self.cur_dhw_heat_schedules[:, 14] = 0.2

        # 停电状态跟踪（每建筑独立）
        self.outage_details = [{
            'outage_duration': 0,
            'time_since_last_outage': 0,
            'saturation_perc': False,
            'outage_flag': False,
            'curr_error': 0,
            'outage_previously': False,
            'saturated_previously': False,
        } for _ in range(self.n_buildings)]

        self.plot = False
        self.trace_recorder = None
        self._trace_refine_meta = {}
        self._trace_initial_meta = {}

    def predict(self, observations: List[List[float]], deterministic: bool = None) -> List[List[float]]:
        """
        主决策入口：每个仿真小时调用一次，返回本步要施加的 a_final。

        ====================================================================
        【单步决策链 — 启用 CHESCA-ResMARL 时】
        ====================================================================
        阶段1  时序预测（ForecastAgent）
        阶段2  各建筑动作初稿 initial_actions
        阶段3  未来设备用电估计
        阶段4  电池树搜索 refine → 得到 a_base（纯 CHESCA 基准动作）
        阶段5  apply_residual_correction：
                 SAC 各 agent 输出 Δa
                 a_final = clip(a_base + α·mask·Δa)   ← 环境实际执行的是 a_final
        随后   更新净负荷历史、seen_steps += 1

        【纯 CHESCA（resmarl_enabled=False 或 α=0）】
        阶段5 恒等返回 a_base，即 a_final = a_base

        调用时机：register_reset（第0小时）及主循环每步 env.step 之后的 predict。
        """
        # central_agent 模式：observations 外层列表长度必须为 1
        assert len(observations) == 1, "Only central agent is supported"

        # 取出唯一 agent 的观测向量（一维 float 列表，长度 = 观测维度，约 50+）
        observations = observations[0]

        # 从观测中读取当前小时（1–24），用于 SOC 下限查表、DHW 计划、电池树搜索等
        hour = int(observations[self.observation_names_b.index('hour')])

        # --- 阶段 1：时序预测 ---
        # ForecastAgent 将本步观测写入历史，用 XGBoost/历史均值集成预测未来 tau 步：
        #   outdoor_temp, solar_generation, non_shiftable_load, dhw_demand 等（按建筑分）
        # 结果存入 self.forecasts，供后续 initial_actions / refine 使用
        self.forecasts = self.forecast_agent.compute_forecast(observations)

        # --- 阶段 2：各建筑独立生成动作初稿 ---
        # 对每栋建筑输出 [DHW_action, ELE_action, TMP_action] 并 extend 拼接
        # 正常模式：冷机 PID、DHW 规则、电池=0；停电模式：保冷 + 有限放电策略
        # 同时更新 cur_battery_soc、elec_consumption_history、predicted_*_demand 等内部状态
        action_proposals = self.initial_actions(observations)
        initial_actions = list(action_proposals)

        # --- 阶段 3：估计未来设备用电（供电池优化）---
        # 用辅助 PID 滚动预测未来 tau 步冷机电耗；t=0 使用上面得到的真实 TMP 动作
        self.future_cooling_demands = self.get_future_cooling_demands(observations, action_proposals)
        # 按 cur_dhw_heat_schedules 24h 计划表估算未来 tau 步 DHW 储热需求
        self.future_dhw_demands = self.get_future_dhw_demands(observations)

        # --- 阶段 4：社区级负荷平衡（电池树搜索 refine）---
        # seen_steps==0 为 episode 首步：历史负荷为空，跳过 refine，避免无意义的树搜索
        # seen_steps>=1 起：对非停电建筑用 BatteryController.search 优化 ELE 动作，
        #   使 net load 接近历史均值，降低 ramping；必要时微调 DHW/TMP
        refine_applied = self.seen_steps >= 1
        self._trace_refine_meta = {}
        if refine_applied:
            action_proposals = self.refine_actions_with_battery_controller(hour, action_proposals)

        # --- 阶段 5：CHESCA-ResMARL 残差（local_evaluation_copy 启用 multi_agent 时）---
        # 输入 action_proposals = a_base（阶段4 refine 之后）
        # 输出 action_proposals = a_final = clip(a_base + α·mask·Δa)
        # residual_corrector 在 setup 时被替换为 MultiAgentResidualCorrector（SAC）
        # α=0 或未启用时原样返回 a_base
        action_proposals = self.apply_residual_correction(action_proposals, observations)

        if self.trace_recorder is not None:
            self.trace_recorder.record_step(
                self,
                observations,
                hour,
                initial_actions,
                action_proposals,
                refine_applied,
                self._trace_refine_meta,
                self._trace_initial_meta,
                getattr(self, '_trace_step_pricing', None),
            )

        # 根据最终动作与预测值，估算本步各建筑净用电，写入 elec_consumption_prediction_history
        # 公式：non_shiftable + cooling + DHW + battery − PV
        self.compute_elec_consumption_values()

        # Agent 内部步计数 +1（与 env.step 配对；下一步 predict 时 seen_steps 已更新）
        self.step()

        # 包装为 central_agent 要求的二维结构：外层长度 1，内层为完整动作向量
        return [action_proposals]

    def apply_residual_correction(self, action_proposals, observations):
        """
        阶段 5：对 CHESCA 基准动作 a_base 施加残差，得到 a_final。

        公式：a_final = clip(a_base + α · mask · Δa)

        行为保证：
          - resmarl_enabled=False 或 residual_alpha=0 → 原样返回 a_base
          - residual_corrector 无有效策略 / Δa 全 0 → 数值上等于 a_base
          - CHESCA-ResMARL 下 Δa 来自 Multi-Agent SAC（见 multi_agent_runner_copy）
        """
        a_base = list(action_proposals)
        low = self.env.action_space[0].low
        high = self.env.action_space[0].high
        chesca_state = {
            'hour': int(observations[self.observation_names_b.index('hour')])
            if 'hour' in self.observation_names_b else None,
            'forecasts': self.forecasts,
            'cur_battery_soc': list(self.cur_battery_soc),
            'cur_dhw_soc': list(self.cur_dhw_soc),
            'net_load_mean': [
                float(np.mean(self.elec_consumption_history[b])) if self.elec_consumption_history[b] else 0.0
                for b in range(self.n_buildings)
            ],
        }
        a_final = self.residual_corrector.correct(
            a_base,
            observations=observations,
            chesca_state=chesca_state,
            action_low=low,
            action_high=high,
        )
        a_final = a_final.tolist() if hasattr(a_final, 'tolist') else list(a_final)
        self._trace_residual_meta = self.residual_corrector.last_trace.to_dict()

        # ELE 残差会改变电池充放电，必须重算 predicted_battery_demand，
        # 否则 compute_elec_consumption_values() 仍用 refine 后的旧预测，净负荷历史失真。
        for b in range(self.n_buildings):
            ele_idx = 3 * b + 1
            if ele_idx >= len(a_final):
                break
            if abs(float(a_final[ele_idx]) - float(a_base[ele_idx])) > 1e-12:
                self.predicted_battery_demand[b], _ = self.compute_pred_battery_consumption(
                    b, a_final[ele_idx]
                )

        return a_final

    def step(self):
        """Agent 内部步计数 +1（与 env.step 同步调用）。"""
        self.seen_steps += 1

    def initial_actions(self, observations):
        """
        为每栋建筑生成初始动作三元组 [DHW, 电池, 冷机]。

        停电与正常工况分支策略不同：
          - 停电：优先保冷、限放电、利用光伏充电
          - 正常：PID 定冷机，DHW 按预测与 SOC 决定，电池初值置 0（后续 refine）
        """
        hour = int(observations[self.observation_names_b.index('hour')])
        predicted_outdoor_temp = self.forecasts['outdoor_temp'][0]

        action_proposals = []
        self._trace_initial_meta = {}
        try:
            electricity_pricing = observation_value(
                observations, self.observation_names_b, 'electricity_pricing'
            )
        except ValueError:
            electricity_pricing = None
        self._trace_step_pricing = electricity_pricing

        for b in range(self.n_buildings):
            # ---------- 读取建筑 b 的当前状态，写入历史（供 refine 算均值/标准差）----------
            self.cooling_device_controller[b].get_cop(predicted_outdoor_temp)  # 更新制冷 COP（能效比）
            # 停电标志：观测中 power_outage_b==1 表示该楼当前停电
            self.outage_details[b]['outage_flag'] = observations[self.observation_names_b.index('power_outage_' + str(b))] == 1
            self.cur_battery_soc[b] = observations[self.observation_names_b.index('electrical_storage_soc_' + str(b))]
            self.cur_dhw_soc[b] = observations[self.observation_names_b.index('dhw_storage_soc_' + str(b))]
            net_electricity_consumption = observations[self.observation_names_b.index(f'net_electricity_consumption_{b}')]
            self.elec_consumption_history[b].append(net_electricity_consumption)
            self.elec_consumption_history_per_hour[b][hour - 1].append(net_electricity_consumption)
            # 前 13 步冷机 PID 需要预热，冷却需求暂置 0
            last_step_cooling_demand = (
                observations[self.observation_names_b.index(f'cooling_demand_{b}')]
                if self.seen_steps > 13 else 0.0
            )

            if self.outage_details[b]['outage_flag']:
                indoor_temp = observation_value(
                    observations, self.observation_names_b, f'indoor_dry_bulb_temperature_{b}'
                )
                setpoint_temp = observation_value(
                    observations, self.observation_names_b, f'indoor_dry_bulb_temperature_set_point_{b}'
                )
                self._trace_initial_meta[b] = {
                    'control_mode': 'outage',
                    'indoor_temp': float(indoor_temp),
                    'setpoint_temp': float(setpoint_temp),
                    'dhw_strategy': 'outage_priority',
                }
                # ===== 停电模式：在有限电力下尽量保舒适 =====
                self.outage_details[b]['outage_previously'] = True
                self.outage_details[b]['time_since_last_outage'] = 0
                self.outage_details[b]['outage_duration'] += 1

                available_soc = max(float(self.cur_battery_soc[b] - self.min_battery_soc[b]), 0.0)
                max_soc_reduction = min(self.params['max_soc_reduction_in_outage'], available_soc)
                max_elec_in_battery = self.battery_capacities[b] * max_soc_reduction

                # 冷机：在「电池可放电量 + 光伏」约束下找最优 TMP（尽量制冷）
                expected_available_elec = max_elec_in_battery + self.forecasts[b]['solar_generation'][0]
                TMP_action = self.cooling_device_controller[b].find_best_action(
                    observations, predicted_outdoor_temp, last_step_cooling_demand,
                    self.outage_details[b], expected_available_elec
                )
                cooling_elec_demand, cooling_energy_demand = self.cooling_device_controller[b].compute_pred_cooling_consumption(
                    TMP_action, predicted_outdoor_temp
                )

                # DHW：优先用储热，不足再放电
                if self.forecasts[b]['dhw_demand'][0] < self.cur_dhw_soc[b] * self.dhw_storage_capacity[b]:
                    dhw_demand = 0.0
                else:
                    dhw_demand = self.forecasts[b]['dhw_demand'][0]
                DHW_action = self.env.action_space[0].low[3 * b]

                # 光伏 / 电池 / 负荷平衡（三档 CASE：有余电充电 / 刚好 / 需放电）
                diff_energy = self.forecasts[b]['solar_generation'][0] - (
                    self.params['increase_scale_outage'] * cooling_elec_demand
                    + 0.0 * dhw_demand + 0.0 * self.forecasts[b]['non_shiftable_load'][0]
                )
                if diff_energy > 0.0:
                    if self.cur_battery_soc[b] < self.params['max_soc_outage']:
                        ELE_action = self.compute_battery_action_given_demand(b, -diff_energy)
                    else:
                        ELE_action = 0.0
                else:
                    diff_energy2 = diff_energy + max_elec_in_battery
                    if diff_energy2 > 0.0:
                        ELE_action = self.compute_battery_action_given_demand(b, -diff_energy)
                    else:
                        ELE_action = -max_soc_reduction

                DHW_action = np.clip(DHW_action, self.env.action_space[0].low[3 * b], self.env.action_space[0].high[3 * b])
                self.predicted_dhw_device_demand[b] = self.compute_pred_dhw_device_consumption(b, DHW_action)

                ELE_action = np.clip(ELE_action, self.env.action_space[0].low[3 * b + 1], self.env.action_space[0].high[3 * b + 1])
                self.predicted_battery_demand[b], _ = self.compute_pred_battery_consumption(b, ELE_action)
                TMP_action = np.clip(TMP_action, self.env.action_space[0].low[3 * b + 2], self.env.action_space[0].high[3 * b + 2])
                self.predicted_cooling_demand[b], _ = self.cooling_device_controller[b].compute_pred_cooling_consumption(
                    TMP_action, predicted_outdoor_temp
                )
                pid_trace = getattr(self.cooling_device_controller[b], '_trace_last', {})
                self._trace_initial_meta[b].update(pid_trace)
                self._trace_initial_meta[b].update({
                    'min_battery_soc': float(self.min_battery_soc[b]),
                    'actual_net_load': float(net_electricity_consumption),
                    'forecast_outdoor_next': float(predicted_outdoor_temp),
                    'pred_cooling_kwh': float(self.predicted_cooling_demand[b]),
                    'pred_dhw_kwh': float(self.predicted_dhw_device_demand[b]),
                    'pred_battery_kwh': float(self.predicted_battery_demand[b]),
                    'expected_available_elec': float(expected_available_elec),
                    'max_elec_in_battery': float(max_elec_in_battery),
                    'available_battery_soc': float(available_soc),
                })

            else:
                indoor_temp = observation_value(
                    observations, self.observation_names_b, f'indoor_dry_bulb_temperature_{b}'
                )
                setpoint_temp = observation_value(
                    observations, self.observation_names_b, f'indoor_dry_bulb_temperature_set_point_{b}'
                )
                self._trace_initial_meta[b] = {
                    'control_mode': 'normal',
                    'indoor_temp': float(indoor_temp),
                    'setpoint_temp': float(setpoint_temp),
                }
                # ===== 正常模式：舒适优先，电池留给阶段4 优化 =====
                if self.outage_details[b]['outage_previously']:
                    self.outage_details[b]['time_since_last_outage'] += 1

                if self.outage_details[b]['outage_duration'] > 0:
                    self.outage_details[b]['time_since_last_outage'] = 0
                    self.outage_details[b]['outage_duration'] = 0

                # 冷机：PID 根据室内温 vs 设定温 + 室外温，输出 TMP_action
                TMP_action = self.cooling_device_controller[b].find_best_action(
                    observations, predicted_outdoor_temp, last_step_cooling_demand,
                    self.outage_details[b], expected_available_elec=np.inf
                )
                TMP_action = np.clip(TMP_action, self.env.action_space[0].low[3 * b + 2], self.env.action_space[0].high[3 * b + 2])
                self.predicted_cooling_demand[b], _ = self.cooling_device_controller[b].compute_pred_cooling_consumption(
                    TMP_action, predicted_outdoor_temp
                )

                # DHW：若当前需求低于 24h 日均且储热 SOC<0.9 → 加热储热；否则从罐中放热
                building_dhw_demand = self.forecasts[b]['dhw_demand'][0]
                avg_dhw_demand = 0
                for h in range(24):
                    h_avg = self.forecast_agent.hourly_expected_values['dhw_demand'][b][h]
                    if len(h_avg) > 0:
                        avg_dhw_demand += np.mean(h_avg)
                avg_dhw_demand /= 24
                heat_water = building_dhw_demand < avg_dhw_demand and self.cur_dhw_soc[b] < 0.9

                if heat_water:
                    DHW_action = self.env.action_space[0].high[3 * b + 2] * 0.20  # 加热：动作上限的 20%
                    dhw_strategy = 'heat_storage'
                else:
                    DHW_action = -0.83  # 放电：从储热罐取热（负值表示释放 stored heat）
                    dhw_strategy = 'discharge_storage'

                self._trace_initial_meta[b]['dhw_strategy'] = dhw_strategy
                self._trace_initial_meta[b].update({
                    'building_dhw_demand': float(building_dhw_demand),
                    'avg_dhw_demand': float(avg_dhw_demand),
                    'heat_water': bool(heat_water),
                })
                DHW_action = np.clip(DHW_action, self.env.action_space[0].low[3 * b], self.env.action_space[0].high[3 * b])
                self.predicted_dhw_device_demand[b] = self.compute_pred_dhw_device_consumption(b, DHW_action)

                # 电池初稿故意置 0：正常工况下由阶段4 树搜索决定充放电，以平滑社区负荷
                ELE_action = 0.0
                self.predicted_battery_demand[b], _ = self.compute_pred_battery_consumption(b, ELE_action)
                pid_trace = getattr(self.cooling_device_controller[b], '_trace_last', {})
                self._trace_initial_meta[b].update(pid_trace)
                self._trace_initial_meta[b].update({
                    'min_battery_soc': float(self.min_battery_soc[b]),
                    'actual_net_load': float(net_electricity_consumption),
                    'forecast_outdoor_next': float(predicted_outdoor_temp),
                    'pred_cooling_kwh': float(self.predicted_cooling_demand[b]),
                    'pred_dhw_kwh': float(self.predicted_dhw_device_demand[b]),
                    'pred_battery_kwh': float(self.predicted_battery_demand[b]),
                })

            # 按 [DHW, ELE, TMP] 顺序拼接到总动作向量
            action_proposals.extend([DHW_action, ELE_action, TMP_action])

        return action_proposals

    def compute_elec_consumption_values(self):
        """
        根据预测负荷与各设备预测用电，估算每建筑净用电并写入 prediction_history。

        公式：non_shiftable + cooling + DHW + battery − PV
        """
        predicted_consumption_per_b = np.zeros(self.n_buildings)
        for b in range(self.n_buildings):
            predicted_consumption_per_b[b] = (
                self.forecasts[b]['non_shiftable_load'][0]
                + self.predicted_cooling_demand[b]
                + self.predicted_dhw_device_demand[b]
                + self.predicted_battery_demand[b]
                - self.forecasts[b]['solar_generation'][0]
            )

            if len(self.elec_consumption_prediction_history[b]) > self.seen_steps:
                self.elec_consumption_prediction_history[b][-1] = predicted_consumption_per_b[b]
            else:
                self.elec_consumption_prediction_history[b].append(predicted_consumption_per_b[b])

    def get_future_cooling_demands(self, obs, action_proposals):
        """
        用辅助 PID 滚动预测未来 tau 步冷机电耗（t=0 用实际 TMP 动作）。
        """
        future_cooling_demands = np.zeros((self.n_buildings, self.params['tau']))
        future_outdoor_temps = self.forecasts['outdoor_temp']
        for b in range(self.n_buildings):
            aux_pid_controller = self.cooling_device_controller[b].aux_pid_controller
            aux_pid_controller.integral = self.cooling_device_controller[b].pid_controller.integral
            aux_pid_controller.prev_error = self.cooling_device_controller[b].pid_controller.prev_error
            indoor_temp = observation_value(obs, self.observation_names_b, f'indoor_dry_bulb_temperature_{b}')
            setpoint = observation_value(obs, self.observation_names_b, f'indoor_dry_bulb_temperature_set_point_{b}')
            for t in range(self.params['tau']):
                pred_out_temp = future_outdoor_temps[t]
                action = aux_pid_controller.get_actions(b, indoor_temp, setpoint, 0.0, False, pred_out_temp)
                action = np.clip(action, self.env.action_space[0].low[3 * b + 2], self.env.action_space[0].high[3 * b + 2])
                if t == 0:
                    action = action_proposals[3 * b + 2]
                future_cooling_demands[b, t] = self.cooling_device_controller[b].compute_pred_cooling_consumption(
                    action, pred_out_temp
                )[0]
                indoor_temp = setpoint

        return future_cooling_demands

    def get_future_dhw_demands(self, observations):
        """按 DHW 加热计划表估算未来 tau 步 DHW 储热需求。"""
        hour = int(observations[self.observation_names_b.index('hour')])
        used_hour = hour - 1 if hour != 0 else 23
        schedules = self.cur_dhw_heat_schedules
        future_dhw_demands = np.zeros((self.n_buildings, self.params['tau']))

        for t in range(self.params['tau']):
            h = used_hour + t if used_hour + t < 24 else used_hour + t - 24
            for b in range(self.n_buildings):
                future_dhw_demands[b, t] = schedules[b, h] * self.dhw_storage_capacity[b]

        return future_dhw_demands

    def get_consumption_forecast(self, hour):
        """
        构造每建筑 (tau+1) 步净负荷预测，索引 0 为当前实测，1..tau 为预测。

        供电池树搜索状态向量使用。
        """
        consumption_forecasts_per_b = np.zeros((self.n_buildings, self.params['tau'] + 1))
        for b in range(self.n_buildings):
            consumption_forecasts_per_b[b, 0] = self.elec_consumption_history[b][-1]
            for t in range(self.params['tau']):
                if t == 0:
                    cooling_demand = self.predicted_cooling_demand[b]
                    dhw_demand = self.predicted_dhw_device_demand[b]
                else:
                    used_hour = hour + t if hour + t < 24 else hour + t - 24
                    cooling_demand = self.future_cooling_demands[b, t]
                    expected_dhw_demand = self.forecast_agent.hourly_expected_values['dhw_demand'][b][used_hour]
                    dhw_demand = (
                        np.mean(expected_dhw_demand) if len(expected_dhw_demand) > 0
                        else self.predicted_dhw_device_demand[b]
                    )
                    expected_cooling_demand = self.forecast_agent.hourly_expected_values['cooling_demand'][b][used_hour]
                    if len(expected_cooling_demand) > 0:
                        cooling_demand += np.mean(expected_cooling_demand)
                        cooling_demand /= 2

                consumption_forecasts_per_b[b, t + 1] = (
                    self.forecasts[b]['non_shiftable_load'][t] + cooling_demand + dhw_demand
                    - self.forecasts[b]['solar_generation'][t]
                )

        return consumption_forecasts_per_b

    def refine_actions_with_battery_controller(self, hour, action_proposals):
        """
        对非停电建筑用电池树搜索优化 ELE 动作，并按 B_high/B_low 微调 DHW/TMP。

        目标：使社区净负荷接近历史均值，降低 ramping，必要时牺牲部分舒适/ DHW。
        """
        normal_building_idx = [b for b in range(self.n_buildings) if not self.outage_details[b]['outage_flag']]
        consumption_forecast = self.get_consumption_forecast(hour)  # 每楼 (tau+1) 步净负荷预测
        final_actions = action_proposals.copy()
        self._trace_refine_meta = {}

        for b in normal_building_idx:
            # 用本楼历史净用电的均值和标准差，作为「负荷应维持在什么水平」的参考
            avg_balance = np.array(self.elec_consumption_history[b]).mean()
            std_balance = np.array(self.elec_consumption_history[b]).std()

            # 树搜索状态向量：
            #   [历史均值, 当前SOC, 当前净负荷, 未来第1步净负荷, ..., 未来第tau步净负荷]
            state = np.array([avg_balance, self.cur_battery_soc[b], *consumption_forecast[b, :]])
            action, cost = self.battery_controller[b].search(state, hour=hour)
            ele_after_search = float(action[0])
            final_actions[3 * b + 1] = ele_after_search
            self.predicted_battery_demand[b], _ = self.compute_pred_battery_consumption(b, ele_after_search)

            # 加上电池用电后的下一步总净负荷
            next_step_total_consumption = consumption_forecast[b, 1] + self.predicted_battery_demand[b]
            b_high_threshold = avg_balance + self.params['B_high'] * std_balance
            b_low_threshold = avg_balance - self.params['B_low'] * std_balance
            trace_meta = {
                'net_load_mean': avg_balance,
                'net_load_std': std_balance,
                'net_load_next': next_step_total_consumption,
                'battery_search_cost': cost,
                'trigger_reduce_load': False,
                'trigger_increase_load': False,
                'b_high_threshold': b_high_threshold,
                'b_low_threshold': b_low_threshold,
                'ele_after_search': ele_after_search,
                'predicted_net_load_step1': float(consumption_forecast[b, 1]),
                'min_battery_soc': float(self.min_battery_soc[b]),
                'battery_soc': float(self.cur_battery_soc[b]),
                'tree_state_mean': float(avg_balance),
                'tree_state_soc': float(self.cur_battery_soc[b]),
                'tree_state_net_current': float(consumption_forecast[b, 0]),
                'tree_state_net_step1': float(consumption_forecast[b, 1]),
                'pred_cooling_kwh': float(self.predicted_cooling_demand[b]),
                'pred_dhw_kwh': float(self.predicted_dhw_device_demand[b]),
                'pred_battery_kwh': float(self.predicted_battery_demand[b]),
                'dhw_before_safety': float(final_actions[3 * b]),
                'tmp_before_safety': float(final_actions[3 * b + 2]),
            }

            # 净负荷过高（超过 均值 + B_high×标准差）：削减 DHW 加热或略降冷机
            if next_step_total_consumption > avg_balance + self.params['B_high'] * std_balance:
                trace_meta['trigger_reduce_load'] = True
                consumption_to_be_reduced = next_step_total_consumption - avg_balance

                DHW_action = final_actions[3 * b]
                if (DHW_action > 0.0) and (consumption_to_be_reduced > 0):
                    avoidable_elec = self.predicted_dhw_device_demand[b]
                    consumption_to_be_reduced -= avoidable_elec
                    final_actions[3 * b] = self.env.action_space[0].low[3 * b]
                    self.predicted_dhw_device_demand[b] = self.compute_pred_dhw_device_consumption(b, final_actions[3 * b])

                TMP_action = final_actions[3 * b + 2]
                avoidable_elec = self.params['TMP_max_reduction_percent'] * self.predicted_cooling_demand[b]
                if (consumption_to_be_reduced > 0) and (avoidable_elec > consumption_to_be_reduced):
                    final_actions[3 * b + 2] = TMP_action * (1 - self.params['TMP_max_reduction_percent'])
                else:
                    consumption_to_be_reduced -= avoidable_elec
                    final_actions[3 * b + 2] = TMP_action * (1 - self.params['TMP_max_reduction_percent'])
                pred_out_temp = self.forecasts['outdoor_temp'][0]
                self.predicted_cooling_demand[b], _ = self.cooling_device_controller[b].compute_pred_cooling_consumption(
                    final_actions[3 * b + 2], pred_out_temp
                )

            # 净负荷过低（低于 均值 − B_low×标准差）：增加 DHW 加热，吸收多余电力
            elif next_step_total_consumption < avg_balance - self.params['B_low'] * std_balance:
                trace_meta['trigger_increase_load'] = True
                consumption_to_be_increased = avg_balance - next_step_total_consumption - self.params['B_low'] * std_balance
                assert consumption_to_be_increased > 0, "This should not happen"

                DHW_action = final_actions[3 * b]
                building_dhw_demand = self.forecasts[b]['dhw_demand'][0]
                avg_dhw_demand = 0
                for h in range(24):
                    h_avg = self.forecast_agent.hourly_expected_values['dhw_demand'][b][h]
                    if len(h_avg) > 0:
                        avg_dhw_demand += np.mean(h_avg)
                avg_dhw_demand /= 24

                if (building_dhw_demand < avg_dhw_demand) and (self.cur_dhw_soc[b] < 0.95) and (consumption_to_be_increased > 0):
                    if DHW_action < 0.0:
                        left_to_charge = (1 - self.cur_dhw_soc[b]) * self.dhw_storage_capacity[b]
                        if left_to_charge > consumption_to_be_increased:
                            consumption_to_be_increased = 0
                            final_actions[3 * b] = self.dhw_device_efficiency[b] * (left_to_charge - consumption_to_be_increased) / self.dhw_storage_capacity[b]
                        else:
                            consumption_to_be_increased -= left_to_charge
                            final_actions[3 * b] = self.env.action_space[0].high[3 * b]

                    self.predicted_dhw_device_demand[b] = self.compute_pred_dhw_device_consumption(b, final_actions[3 * b])

            trace_meta['dhw_after_safety'] = float(final_actions[3 * b])
            trace_meta['tmp_after_safety'] = float(final_actions[3 * b + 2])
            trace_meta['pred_cooling_kwh_final'] = float(self.predicted_cooling_demand[b])
            trace_meta['pred_dhw_kwh_final'] = float(self.predicted_dhw_device_demand[b])
            trace_meta['pred_battery_kwh_final'] = float(self.predicted_battery_demand[b])

            self._trace_refine_meta[b] = trace_meta

        # 最终裁剪到动作空间
        for b in range(self.n_buildings):
            DHW_action = final_actions[3 * b]
            ELE_action = final_actions[3 * b + 1]
            TMP_action = final_actions[3 * b + 2]
            final_actions[3 * b] = np.clip(DHW_action, self.env.action_space[0].low[3 * b], self.env.action_space[0].high[3 * b])
            final_actions[3 * b + 1] = np.clip(ELE_action, self.env.action_space[0].low[3 * b + 1], self.env.action_space[0].high[3 * b + 1])
            final_actions[3 * b + 2] = np.clip(TMP_action, self.env.action_space[0].low[3 * b + 2], self.env.action_space[0].high[3 * b + 2])
        return final_actions

    def compute_pred_battery_consumption(self, b, ELE_action):
        """
        由电池动作（SOC 比例）估算实际电网侧电耗，考虑效率曲线与 SOC 功率限制。

        返回：(electricity_consumption, efficiency)
        """
        ELE_action = np.clip(ELE_action, self.env.action_space[0].low[3 * b + 1], self.env.action_space[0].high[3 * b + 1])
        energy = ELE_action * self.battery_capacities[b]
        max_input_power = self.calculate_battery_max_input_power(b, self.cur_battery_soc[b])
        efficiency = self.calculate_battery_efficiency(b, energy)
        cur_energy = self.cur_battery_soc[b] * self.battery_capacities[b]

        if energy >= 0:  # 充电
            energy = min(max_input_power, self.battery_nominal_powers[b], energy)
            energy_final = min(cur_energy + energy * efficiency, self.battery_capacities[b])
            electricity_consumption = (energy_final - cur_energy) / efficiency
        else:  # 放电
            soc_difference = self.cur_battery_soc[b] - self.min_battery_soc[b]
            energy_limit_wrt_dod = -1 * max(soc_difference * self.battery_capacities[b] * efficiency, 0.0)
            energy = max(-max_input_power, energy_limit_wrt_dod, energy)
            energy_final = max(0.0, cur_energy + energy / efficiency)
            electricity_consumption = (energy_final - cur_energy) * efficiency

        return electricity_consumption, efficiency

    def calculate_battery_efficiency(self, b, energy):
        """按功率-效率曲线线性插值当前充放电效率。"""
        energy_normalized = np.abs(energy) / self.battery_nominal_powers[b]
        idx = max(0, np.argmax(energy_normalized <= self.battery_efficiency_curves[b][0]) - 1)
        efficiency = (
            self.battery_efficiency_curves[b][1][idx]
            + (energy_normalized - self.battery_efficiency_curves[b][0][idx])
            * (self.battery_efficiency_curves[b][1][idx + 1] - self.battery_efficiency_curves[b][1][idx])
            / (self.battery_efficiency_curves[b][0][idx + 1] - self.battery_efficiency_curves[b][0][idx])
        )
        return efficiency

    def calculate_battery_max_input_power(self, b, soc):
        """按 SOC-最大功率曲线插值当前允许充放电功率。"""
        idx = max(0, np.argmax(soc <= self.battery_capacity_power_curves[b][0]) - 1)
        max_input_power = (
            self.battery_nominal_powers[b]
            * (
                self.battery_capacity_power_curves[b][1][idx]
                + (self.battery_capacity_power_curves[b][1][idx + 1] - self.battery_capacity_power_curves[b][1][idx])
                * (soc - self.battery_capacity_power_curves[b][0][idx])
                / (self.battery_capacity_power_curves[b][0][idx + 1] - self.battery_capacity_power_curves[b][0][idx])
            )
        )
        return max_input_power

    def compute_battery_action_given_demand(self, b, ELE_demand):
        """由目标电网侧电量需求反推电池动作（SOC 比例，负=放电）。"""
        efficiency = self.calculate_battery_efficiency(b, ELE_demand)
        input_energy = ELE_demand * efficiency
        needed_action = input_energy / self.battery_capacities[b]
        return -1 * needed_action

    def compute_pred_dhw_device_consumption(self, b, DHW_action):
        """
        由 DHW 储热动作估算设备电网侧电耗。

        正动作：加热储热罐；负动作：从储热罐取热，不足部分由设备补热。
        """
        DHW_action = np.clip(DHW_action, self.env.action_space[0].low[3 * b], self.env.action_space[0].high[3 * b])
        energy = DHW_action * self.dhw_storage_capacity[b]
        cur_energy = self.cur_dhw_soc[b] * self.dhw_storage_capacity[b]
        demand = self.forecasts[b]['dhw_demand'][0]
        if demand < 0.15:
            demand = 0.0

        if energy > 0.0:
            max_output = min(np.inf, self.dhw_device_nominal_powers[b]) * self.dhw_device_efficiency[b]
            energy = min(max_output, energy)
            consumption = energy + demand
        else:
            used_energy = min(abs(energy), cur_energy)
            if used_energy > demand:
                consumption = 0.0
            else:
                consumption = demand - used_energy

        electricity_consumption = consumption / self.dhw_device_efficiency[b]
        return electricity_consumption
