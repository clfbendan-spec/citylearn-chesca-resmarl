"""
CoolingDeviceController — CHESCA 阶段2：冷机 PID 控制
=====================================================

【作用】
  为每栋建筑控制冷机（cooling_device）出力，维持室内温度接近设定温度。

【核心方法】
  find_best_action() — 根据室内外温差、停电状态、可用电力，输出 TMP_action
  compute_pred_cooling_consumption() — 由 TMP 动作估算电网侧冷机电耗

【控制原理：PID】
  PID = 比例(P) + 积分(I) + 微分(D) 控制器
  · 室温高于设定温 → 增大制冷（TMP 动作更负/更大）
  · 室外温度通过 OutTempScaler 加权影响控制量
  · 停电时用 Kp_outage 不同的增益，在有限电力下尽量保舒适

【与阶段3 的关系】
  aux_pid_controller 是 PID 的副本，用于 get_future_cooling_demands()
  滚动模拟未来几步的冷机电耗，供电池树搜索使用。
"""
import numpy as np
from checa.cooling_device_controller.pid_controller import PIDController
from checa.utils import observation_value, observation_value_optional, resolve_citylearn_env
from scipy import stats

# PID 积分限幅系数（× 冷机额定功率）。2026-10-08 由 0.5 收到 0.15：
#
# 为什么改 —— B2 的 cost_total 一直 >1（本集 1.088，历史各集 1.0~1.6）：
#   CityLearn 的 cost_total = 控制净电耗 / 「理想无控制负荷」净电耗，而 B2 全年约 30% 的
#   冷量发生在室温已低于设定点之后（PID 的 P 项为负、I 项独自把需求顶成正数），
#   净冷量比理想负荷高 14.6% ⇒ 成本被直接抬高。
#   积分限幅 0.5×额定 对 B2（额定仅 2.25 kW）意味着允许 1.13 kW 的"积分记忆"，
#   远超它 0.5 kW 量级的平均需求 ⇒ 收进来即可。
#
# 实测（本集 online_evaluation_1，2208 步；另一集 online_evaluation_2 结论一致）：
#   cost_total             0.938 → 0.861（District，-8.2%）；
#                          B2 1.088 → 0.961（唯一 >1 的楼栋降回 <1）
#   discomfort_proportion  0.019 → 0.027（其中"过热" 0.005 → 0.010）
#   thermal_resilience / 停电未供能 不变
# 保守选项：0.25 ⇒ cost 0.897、discomfort 0.020（几乎不动舒适度）；
# 再往下（0.05~0.1）会开始出现 bang-bang 振荡（室温反复越过设定带）。
INTEGRAL_LIMIT_FRAC = 0.15


class CoolingDeviceController:
    def __init__(self, building_metadata, b, obs_names_b):
        self.building_metadata = building_metadata
        self.observation_names_b = obs_names_b
        self.b = b
        self.seen_steps = 0

        self.update_freq = 24
        self.n = 2.0  # exponent in the error to update scores

        self.cooling_nominal_powers = self.building_metadata['cooling_device']['nominal_power']
        self.cooling_device_efficiency = self.building_metadata['cooling_device']['efficiency']
        self.cooling_cop = 0.0

        # PID
        # Initialize PID controller
        self.use_pid = True

        # Controller for all three buildings
        self.pid_controller = PIDController()
        self.pid_controller.Kp = -0.288074675781558  # -0.0183231
        self.pid_controller.Ki = -2.489908316536426  # -4.298114009977
        self.pid_controller.Kd = 0.009479951268930725  # 0.0 to be a PI controller
        self.pid_controller.dt = 0.1  # 0.1
        self.pid_controller.OutTempScaler = 0.09629375171771082
        self.pid_controller.Kp_outage = -0.27351617926369537
        # 积分限幅：避免长期负饱和导致 TMP 恒为 0，同时抑制 windup 造成的过度制冷
        i_lim = float(self.cooling_nominal_powers) * float(INTEGRAL_LIMIT_FRAC)
        self.pid_controller.integrator_min = -i_lim
        self.pid_controller.integrator_max = i_lim

        self.aux_pid_controller = PIDController()
        self.aux_pid_controller.Kp = -0.288074675781558
        self.aux_pid_controller.Ki = -2.489908316536426
        self.aux_pid_controller.Kd = 0.009479951268930725
        self.aux_pid_controller.dt = 0.1
        self.aux_pid_controller.OutTempScaler = 0.09629375171771082
        self.aux_pid_controller.Kp_outage = -0.27351617926369537
        self.aux_pid_controller.integrator_min = -i_lim
        self.aux_pid_controller.integrator_max = i_lim

        """
        {"target": Dont know, "params": {"Kp_o": -0.2859441319844675, "OutTempScaler": 0.1024468677938111}, Average score: Average score: 0.500, Resilience: 0.354, Unserved: 0.442

        {"target": -0.505676805973053, "params": {"Kp_o": -0.27351617926369537, "OutTempScaler": 0.09629375171771082}, Average score: 0.499, Resilience: 0.345, Unserved: 0.442
        {"target": -0.5059506297111511, "params": {"Kp_o": -0.2811766922821901, "OutTempScaler": 0.08356605234881731},
        {"target": -0.5045549869537354, "params": {"Kp_o": -0.2692889293697175, "OutTempScaler": 0.08117311805607505}, Average score: 0.499, Resilience: 0.349, Unserved: 0.440
        {"target": -0.5058454275131226, "params": {"Kp_o": -0.2788985853672359, "OutTempScaler": 0.087780233592517}, 
        {"target": -0.5039359331130981, "params": {"Kp_o": -0.2675317659029748, "OutTempScaler": 0.03640156612555039}, Average score: 0.499, Resilience: 0.351, Unserved: 0.436
        {"target": -0.5039920210838318, "params": {"Kp_o": -0.26547226577692423, "OutTempScaler": 0.03181194000391644},
        {"target": -0.5061987042427063, "params": {"Kp_o": -0.2860233588478051, "OutTempScaler": 0.1}, Average score: 0.501, Resilience: 0.359, Unserved: 0.442
        {"target": -0.5043141841888428, "params": {"Kp_o": -0.2574072807620056, "OutTempScaler": 0.032388445279158365}, Average score: 0.499, Resilience: 0.355, Unserved: 0.435
        
        
        AVG SCORE MULTIPLE SEEDS
        {"target": -0.5067414045333862, "params": {"Kp_o": -0.247013260264578, "OutTempScaler": 0.03100663702805051}, "datetime": {"datetime": "2023-11-12 20:23:34", "elapsed": 12329.972161, "delta": 583.082663}}
        {"target": -0.506675660610199, "params": {"Kp_o": -0.2520716329315423, "OutTempScaler": 0.02476989675830077}, "datetime": {"datetime": "2023-11-12 17:01:46", "elapsed": 0.0, "delta": 0.0}}

        OUTAGE
        {"target": -0.7852861991014534, "params": {"Kp_o": -0.27718231017358447, "OutTempScaler": 0.10122917387682927}, "datetime": {"datetime": "2023-11-12 20:38:48", "elapsed": 12542.656823, "delta": 582.264053}}
        {"target": -0.7863135214158126, "params": {"Kp_o": -0.2661926894272662, "OutTempScaler": 0.040887324044468536}, "datetime": {"datetime": "2023-11-12 21:00:47", "elapsed": 13885.767592, "delta": 573.705677}}
        {"target": -0.7842492774382114, "params": {"Kp_o": -0.2589563545239867, "OutTempScaler": 0.03621714354693686}, "datetime": {"datetime": "2023-11-12 19:08:24", "elapsed": 6866.007594, "delta": 862.97067}}
        {"target": -0.7805302212058559, "params": {"Kp_o": -0.2520716329315423, "OutTempScaler": 0.02476989675830077}, "datetime": {"datetime": "2023-11-12 17:09:46", "elapsed": 0.0, "delta": 0.0}}
        {"target": -0.7813702335728071, "params": {"Kp_o": -0.2564384096876519, "OutTempScaler": 0.025462126196686148}, "datetime": {"datetime": "2023-11-12 21:07:34", "elapsed": 14266.482332, "delta": 581.023997}}

        RESILIENCE
        {"target": -0.35921516754850086, "params": {"Kp_o": -0.3087273271121387, "OutTempScaler": 0.10495128632644757}, "datetime": {"datetime": "2023-11-12 18:31:28", "elapsed": 4855.576308, "delta": 603.819682}}
        {"target": -0.3574514991181657, "params": {"Kp_o": -0.3999607691153279, "OutTempScaler": 0.09733470317930655}, "datetime": {"datetime": "2023-11-12 20:44:13", "elapsed": 12809.625391, "delta": 591.020145}}
        """

        self.setpoint_history = []
        self.last_setpoint = None
        self.used_setpoints = []

        self.proposed_demand = None

        self.saturation_perc_limit = 0.5493411704104555 #0.2
        # 不再抬高设定点：原 +0.12°C 会在「刚好到设定」时仍产生正误差，经负增益推出负制冷需求
        self.added_temp_to_setpoint = 0.0
        # ---- 冷机保底 / 决策室温（可由网页 chesca_agent_config 覆盖）----
        # 动力学过热时的最小制冷（相对额定功率 / 每 °C）
        self.min_cool_per_c_overheat = 0.12
        # 室外开环保底：默认较弱；系数=0 即关闭
        self.min_cool_per_c_outdoor_gap = 0.03
        self.outdoor_gap_deadband_c = 5.0
        # 过热低于该值才叠室外保底（允许负过热，见 outdoor_floor_allow_when_under_setpoint）
        self.outdoor_floor_max_overheat_c = 0.5
        # 冷负荷前馈比例；系数=0 即关闭
        self.cooling_demand_feedforward_frac = 0.10
        # False：观测/控制未过热时仍可用冷负荷前馈（缓解 LSTM 决策滞后）
        self.demand_feedforward_only_when_overheat = False
        # True：室外保底在 overheat<0（贴设定的观测）时仍可启用
        self.outdoor_floor_allow_when_under_setpoint = True
        # True：恢复旧行为——overheat<0 时清掉一切开环保底
        self.clear_open_loop_floor_when_under_setpoint = False
        # True：PID 优先用上一拍已落地的动力学室温 building.indoor[-2]
        self.use_lagged_dynamics_indoor = True
        # True：仅当 [-2] 比 [-1] 更热超过 margin 时才用滞后室温（兼容不同 step 时序）
        self.lagged_indoor_only_when_hotter = False
        self.lagged_indoor_hotter_margin_c = 0.3

    def apply_comfort_floor_params(self, params):
        """从 Agent params / chesca_agent_config 覆盖保底 / 决策室温相关可调参数。"""
        if not params:
            return
        bool_attrs = {
            'demand_feedforward_only_when_overheat',
            'outdoor_floor_allow_when_under_setpoint',
            'clear_open_loop_floor_when_under_setpoint',
            'use_lagged_dynamics_indoor',
            'lagged_indoor_only_when_hotter',
        }
        float_attrs = {
            'min_cool_per_c_overheat',
            'min_cool_per_c_outdoor_gap',
            'outdoor_gap_deadband_c',
            'outdoor_floor_max_overheat_c',
            'cooling_demand_feedforward_frac',
            'lagged_indoor_hotter_margin_c',
        }
        for attr in bool_attrs:
            if attr in params and params[attr] is not None:
                setattr(self, attr, bool(params[attr]))
        for attr in float_attrs:
            if attr in params and params[attr] is not None:
                setattr(self, attr, float(params[attr]))

    def step(self):
        self.seen_steps += 1

    def _pick_lagged_dynamics_indoor(self, indoor_series):
        """
        选取 PID 用室内温：默认用上一拍已 LSTM 落地的 [-2]。

        CityLearn（apply→next）下决策时 [-1] 常仍是理想占位（贴设定），
        而 [-2] 才是上一步动作后的真实动力学室温。
        """
        n = len(indoor_series)
        cur = float(indoor_series[-1])
        if n < 2 or not bool(self.use_lagged_dynamics_indoor):
            return cur, 'building.indoor[-1]'
        prev = float(indoor_series[-2])
        if bool(self.lagged_indoor_only_when_hotter):
            margin = float(self.lagged_indoor_hotter_margin_c)
            if prev < cur + margin:
                return cur, 'building.indoor[-1]'
        return prev, 'building.indoor[-2]'

    def _resolve_control_temperatures(self, obs, names, env=None):
        """
        解析 PID 用的室内温 / 制冷设定。

        优先用 buildings 动力学序列；开启 use_lagged_dynamics_indoor 时用 [-2]
        对齐「上一拍已落地」室温，缓解决策观测贴设定、KPI 却很热的问题。
        """
        indoor_obs = float(observation_value(obs, names, f'indoor_dry_bulb_temperature_{self.b}'))
        set_obs = float(
            observation_value(obs, names, f'indoor_dry_bulb_temperature_set_point_{self.b}')
        )
        indoor = indoor_obs
        setpoint = set_obs
        indoor_source = 'obs.indoor'
        set_source = 'obs.set_point'

        real_env = resolve_citylearn_env(env)
        if real_env is not None and self.b < len(getattr(real_env, 'buildings', []) or []):
            building = real_env.buildings[self.b]
            try:
                indoor_series = building.indoor_dry_bulb_temperature
                if indoor_series is not None and len(indoor_series) > 0:
                    indoor, indoor_source = self._pick_lagged_dynamics_indoor(indoor_series)
            except Exception:
                pass
            try:
                cool_series = building.indoor_dry_bulb_temperature_cooling_set_point
                if cool_series is not None and len(cool_series) > 0:
                    cool_sp = float(cool_series[-1])
                    if np.isfinite(cool_sp) and cool_sp > 0:
                        setpoint = cool_sp
                        set_source = 'building.cooling_set_point[-1]'
            except Exception:
                pass

        return indoor, setpoint, indoor_obs, set_obs, indoor_source, set_source

    def find_best_action(self, obs, pred_out_temp, last_step_demand, outage_details,
                         expected_available_elec, env=None):
        """
        Given the current state, find the action that leads to the setpoint.
        state: [direct_solar_irradiance, diffuse_solar_irradiance, outdoor_temp, indoor_temp, action (cooling demand - not real action)]
        """

        names = self.observation_names_b
        indoor_temp, temp_setpoint, indoor_obs, set_obs, indoor_source, set_source = (
            self._resolve_control_temperatures(obs, names, env=env)
        )
        self.setpoint_history.append(temp_setpoint)

        if self.proposed_demand is not None:
            if self.proposed_demand > 0:
                saturated_perc = (abs(last_step_demand - self.proposed_demand) / self.proposed_demand)
            else:
                saturated_perc = 0.0
            if saturated_perc < self.saturation_perc_limit:
                saturated_perc = 0.0
        else:
            saturated_perc = 0.0
        outage_details['saturation_perc'] = saturated_perc
        if not outage_details['saturated_previously'] and saturated_perc >= self.saturation_perc_limit:
            outage_details['saturated_previously'] = True

        use_mode_setpoint = False
        if use_mode_setpoint:
            # set the mode of the last 4 hours
            mode, count = stats.mode(self.setpoint_history[-4:])
            if count > 1:
                used_setpoint = mode
            else:
                used_setpoint = temp_setpoint
        else:
            used_setpoint = temp_setpoint
        self.used_setpoints.append(used_setpoint)

        # CASE 1: No outage: use PID controller as normal
        reduced_setpoint = used_setpoint + self.added_temp_to_setpoint  # FOr outage

        if not outage_details['outage_flag']:
            # If after outage, we are higher from setpoint, reset integral and prev_error
            after_outage = outage_details['outage_previously'] and outage_details['time_since_last_outage'] == 0
            if after_outage and outage_details['saturated_previously']:
                self.pid_controller.integral = 0
                self.pid_controller.updated_integral = 0
                self.pid_controller.prev_error = 0
                self.pid_controller.updated_prev_error = 0
                outage_details['saturated_previously'] = False

            demand_action = self.pid_controller.get_actions(self.b, indoor_temp, reduced_setpoint, 0.0, False, pred_out_temp)

        # CASE 2: Outage but no saturation
        elif saturated_perc < self.saturation_perc_limit:
            # check if batteries will give enough
            demand_action = self.pid_controller.get_actions(self.b, indoor_temp, reduced_setpoint, 0.0, False,
                                                            pred_out_temp)
            if demand_action < expected_available_elec:
                pass  # enough battery and gen: use as normal
            else:
                # Then we will surely enter in saturation if outage continues
                diff_temp = indoor_temp - used_setpoint
                if diff_temp > 1.5:
                    demand_action = self.pid_controller.get_actions(self.b, indoor_temp, reduced_setpoint, 0.0, True, pred_out_temp)
                else:
                    demand_action = self.pid_controller.get_actions(self.b, indoor_temp, reduced_setpoint, 0.0, False, pred_out_temp)

        # CASE 3: Outage and saturation: use PID controller with reduced action, see how the diff temp is
        else:
            # check if next step battery will be enough as a not outage flag
            # demand_action = self.pid_controller.get_actions(self.b, indoor_temp, used_setpoint, saturated_perc, False, pred_out_temp)

            # if demand_action < expected_available_elec:
            #    pass # enough battery and gen: use as normal even we had saturation

            # else: # Not enough battery and gen. In this case, maybe we are getting out from outage in the next step... so be careful
            diff_temp = indoor_temp - used_setpoint
            if diff_temp>1.5:
                demand_action = self.pid_controller.get_actions(self.b, indoor_temp, reduced_setpoint, saturated_perc, True, pred_out_temp)
            else:
                demand_action = self.pid_controller.get_actions(self.b, indoor_temp, reduced_setpoint, saturated_perc, False, pred_out_temp)

        # PID 原始输出（封顶 / 舒适下限之前），用于推演「供电不足 vs 需求本来就小」
        pid_raw_demand = float(demand_action)
        capped_by_available_elec = False
        if demand_action > expected_available_elec:
            demand_action = expected_available_elec
            capped_by_available_elec = True

        # 舒适保障：过热比例保底 + 室外/冷负荷开环保底（可在未过热时保留开环项）
        overheat = float(indoor_temp) - float(used_setpoint)
        outdoor_gap = float(pred_out_temp) - float(used_setpoint)
        min_cool = 0.0
        min_cool_applied = False
        comfort_floor_neg_cleared = False
        feedforward_from_demand = 0.0
        outdoor_floor_kwh = 0.0
        overheat_floor = 0.0
        if overheat > 0.0:
            if demand_action < 0.0:
                demand_action = 0.0
                comfort_floor_neg_cleared = True
                if self.pid_controller.integral < 0.0:
                    self.pid_controller.integral = 0.0
                    self.pid_controller.updated_integral = 0.0
            overheat_floor = max(
                abs(float(self.pid_controller.Kp)) * overheat,
                self.min_cool_per_c_overheat * overheat * float(self.cooling_nominal_powers),
            )
        # 注：overheat <= 0（室温未高于设定点）时**不做**「清需求」处理 —— P 项此时必为负，
        # 唯一可能把需求顶成正数的是积分 windup；硬清（清 0 / 减半）实测会让控制退化成
        # bang-bang（室温反复越过设定带、冷不适 0.04→0.12）。所以这里只靠积分限幅抑制，
        # 见文件头 INTEGRAL_LIMIT_FRAC 的实测数据。

        outdoor_excess = max(0.0, outdoor_gap - float(self.outdoor_gap_deadband_c))
        under_ok = overheat >= 0.0 or bool(self.outdoor_floor_allow_when_under_setpoint)
        outdoor_floor_ok = (
            float(self.min_cool_per_c_outdoor_gap) > 0.0
            and outdoor_excess > 0.0
            and under_ok
            and overheat < float(self.outdoor_floor_max_overheat_c)
        )
        if outdoor_floor_ok:
            outdoor_floor_kwh = (
                self.min_cool_per_c_outdoor_gap * outdoor_excess * float(self.cooling_nominal_powers)
            )

        allow_demand_ff = float(self.cooling_demand_feedforward_frac) > 0.0 and (
            overheat > 0.0 or not bool(self.demand_feedforward_only_when_overheat)
        )
        if allow_demand_ff:
            cooling_demand_obs = observation_value_optional(
                obs, names, f'cooling_demand_{self.b}', default=None
            )
            if cooling_demand_obs is None:
                cooling_demand_obs = last_step_demand
            try:
                self.get_cop(pred_out_temp)
                cop = float(self.cooling_cop) if float(self.cooling_cop) > 0 else 3.0
                feedforward_from_demand = (
                    float(self.cooling_demand_feedforward_frac)
                    * max(0.0, float(cooling_demand_obs))
                    / cop
                )
            except Exception:
                feedforward_from_demand = 0.0

        min_cool = max(overheat_floor, outdoor_floor_kwh, feedforward_from_demand)
        # 旧行为开关：低于设定时清掉开环项（仅保留过热保底，此时为 0）
        if overheat < 0.0 and bool(self.clear_open_loop_floor_when_under_setpoint):
            outdoor_floor_kwh = 0.0
            feedforward_from_demand = 0.0
            min_cool = overheat_floor

        if min_cool > 0.0 and demand_action < min_cool:
            demand_action = min_cool
            min_cool_applied = True
        if demand_action > expected_available_elec:
            demand_action = expected_available_elec
            capped_by_available_elec = True

        action = self.compute_cooling_action_given_elec_demand(demand_action)

        action = np.clip(action, 0.0, 1.0)

        pid_trace = getattr(self.pid_controller, '_trace_last', {}) or {}
        avail_trace = (
            None if not np.isfinite(float(expected_available_elec))
            else float(expected_available_elec)
        )
        self._trace_last = {
            **pid_trace,
            'indoor_temp': float(indoor_temp),
            'indoor_temp_obs': float(indoor_obs),
            'indoor_temp_source': indoor_source,
            'setpoint_temp': float(used_setpoint),
            'setpoint_temp_obs': float(set_obs),
            'setpoint_temp_source': set_source,
            'added_temp_to_setpoint': float(self.added_temp_to_setpoint),
            'cooling_nominal_power': float(self.cooling_nominal_powers),
            'expected_available_elec': avail_trace,
            'pid_raw_demand': pid_raw_demand,
            'pid_electrical_demand': float(demand_action),
            'capped_by_available_elec': bool(capped_by_available_elec),
            'overheat_c': float(overheat),
            'outdoor_gap_c': float(outdoor_gap),
            'min_cool_kwh': float(min_cool),
            'min_cool_applied': bool(min_cool_applied),
            'outdoor_floor_kwh': float(outdoor_floor_kwh),
            'feedforward_from_demand_kwh': float(feedforward_from_demand),
            'comfort_floor_neg_cleared': bool(comfort_floor_neg_cleared),
            'use_lagged_dynamics_indoor': bool(self.use_lagged_dynamics_indoor),
            'saturation_perc': float(saturated_perc),
            'tmp_action': float(action),
            'tmp_from_demand': float(action),
        }

        self.proposed_demand = self.compute_pred_cooling_consumption(action, pred_out_temp)[1]

        self.step()

        self.last_setpoint = temp_setpoint

        return action

    def compute_pred_cooling_consumption(self, TMP_action, outdoor_temp):
        self.get_cop(outdoor_temp)

        electric_power = TMP_action * self.cooling_nominal_powers
        # we are assuming available nominal power == all nominal power
        demand = min(electric_power, self.cooling_nominal_powers) * self.cooling_cop

        # Calculate device output energy and electricity consumption
        downward_electrical_flexibility = np.inf
        max_input_power = min(downward_electrical_flexibility, self.cooling_nominal_powers) * self.cooling_cop

        device_output = min(max_input_power, demand)

        electricity_consumption = device_output / self.cooling_cop

        return electricity_consumption, demand

    def get_cop(self, outdoor_temp):
        t_target_cooling = self.building_metadata['cooling_device']['target_cooling_temperature']
        cop = (t_target_cooling + 273.15) * self.cooling_device_efficiency / (outdoor_temp - t_target_cooling)
        if cop < 0 or cop > 20:
            cop = 20
        self.cooling_cop = cop

    def compute_cooling_action_given_elec_demand(self, cooling_elec_demand):
        return cooling_elec_demand / self.cooling_nominal_powers
