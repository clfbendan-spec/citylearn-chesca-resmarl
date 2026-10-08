# -*- coding: utf-8 -*-
# ⚠️ 本文件是**精简注释版**（由 `_gen_marl_split.py` 生成 ✓）：全部「详注块」已整段删除 ✓，
#    代码与同目录的 `X.detailed.py` **逐字相同** ✓（AST 一致 ⇒ 行为一致 ✓）。
#    **改注释请改 `.detailed.py` 那份** ✗（本文件每次生成都会被覆盖 ✗），改完重跑 `_gen_marl_split.py` ✓。
# CustomComfortReward —— 自定义舒适度奖励（从 Multi-agent.py 抽出，内容逐字未改）。

import numpy as np

from citylearn.reward_function import ComfortReward



# =============================================================================
# 自定义奖励函数：CustomComfortReward
def _clamp_temp_penalty(value: float, cap: float) -> float:
    # 把带外温度罚封顶（cap<=0 表示不封顶）。
    # P5-1：原版 −δ²(热)/−δ³(冷) 的取值跨度极大（深冷 δ=5 → −125、δ=8 → −512），
    if cap and cap > 0.0 and value < -cap:
        return -cap
    return value




def _cap_txt(cap: float) -> str:
    # 推演叙事用：只在真的开启封顶时才显示"封顶 xx"，避免打印"封顶0"误导。
    return f', 封顶{cap:g}' if cap and cap > 0.0 else ''




class CustomComfortReward(ComfortReward):
    # 与数据集默认 ComfortReward 逻辑一致，并额外加入「依赖制冷动作」的奖励项。
    # 温度项与原版逐位一致（--check-reward 可验证）；动作项可用权重置 0 关闭。

    def __init__(
        self,
        env_metadata,
        band: float = None,
        lower_exponent: float = None,
        higher_exponent: float = None,
        # ---------------------------------------------------------------------
        # ⚠️ 动手前必读：下面这些**形参默认值不是**项目实际配置 ✗
        hot_act_floor: float = 0.30,
        hot_a_per_c: float = 0.11,
        hot_a_cap: float = 0.60,
        hot_act_weight: float = 110.0,
        hot_act_penalty_cap: float = 130.0,
        hot_act_min_over_c: float = 0.25,
        # a_need 口径：'load' = 由 a_ref 导出（理想负荷 ÷ 热容量，环境逐时注入）/ 'const' = 旧常数式
        #   取不到 a_ref 时自动退回 'const'（不会崩）；曾误用观测 cooling_demand 的教训见 §9.3
        hot_a_need_mode: str = 'load',
        # --- 过吹罚（治"开度超过理想负荷所需"）：只罚超出的一侧（依据见 §2 的 Step2A）---
        hot_over_weight: float = 30.0,
        hot_over_tol: float = 0.03,           # 绝对容差（允许小幅超吹，避免噪声/预冷被罚）
        hot_over_tol_frac: float = 0.0,       # 相对容差（比例 × a_ref；低负荷步自动收紧）
        hot_over_penalty_cap: float = 60.0,   # 单步封顶
        # --- 带外温度罚封顶（≤0 = 不封顶，回到原版 −δ² / −δ³）---
        hot_temp_cap: float = 0.0,
        cold_temp_cap: float = 0.0,
        # --- 过冷关冷（三区判定见 calculate 的「③ 过冷」段；P5-B 已证伪回滚见 §3）---
        cold_cool_weight: float = 75.0,     # (c) 带外基础权重
        cold_w_out_frac: float = 0.3,       # (c) 带外轻罚区系数（× 基础权重）
        cold_gap_gain: float = 1.0,         # (c) 低于下限每 1°C 的放大倍数
        cold_stop_margin_c: float = 0.50,   # (c) 带下沿再往下多少度算"死区"
        cold_maintain_act: float = 0.05,    # (b)(c) 允许的维持开度
        trans_zone_c: float = 0.10,         # cold_lower 边界过渡半带宽（0 = 关闭）
        cold_penalty_cap: float = 120.0,    # (c) 该项封顶
        cold_near_weight: float = 45.0,         # (b) 带内关冷权重
        cold_near_free_frac: float = 0.5,       # (b) 带内免罚窗半宽（× band）
        # --- 电费项：cost_weight 罚 net 用电（含电池，已证伪置 0 见 §4）；
        #             cool_cost_weight 只罚制冷电耗（与电池解耦，见 §5）---
        cost_weight: float = 0.0,
        cool_cost_weight: float = 0.0,
        # --- 电池：bat_weight = 价差择时项（必须带 max(0,·)，见 §6）；
        #           bat_loss_weight = 净循环量定价（三种形式均已证伪，见 §7）---
        bat_weight: float = 50.0,
        bat_loss_weight: float = 0.0,
        # --- 其它 ---
        act_hot_only_when_occupied: bool = False,
        record_details: bool = True,
        # mid-eval「KPI 口径」用的舒适带缺省值（仅在观测里读不到 comfort_band 时使用）。
        #   ⚠️ 与 self.band（奖励带）是两个不同口径：奖励带是塑形尺度（本任务 1.0），
        kpi_band_default: float = 2.0,
        **kwargs,
    ):
        # 交给父类处理 band / 指数 的缺省与属性存储（band 为 None 时逐楼用 comfort_band）
        super().__init__(
            env_metadata,
            band=band,
            lower_exponent=lower_exponent,
            higher_exponent=higher_exponent,
        )
        # ---- 过热动作保底参数 ----
        self.hot_act_floor = float(max(0.0, hot_act_floor))
        self.hot_a_per_c = float(max(0.0, hot_a_per_c))
        # 目标开度上限不低于 floor，否则温差放大被截断
        self.hot_a_cap = float(min(1.0, max(self.hot_act_floor, hot_a_cap)))
        self.hot_act_weight = float(max(0.0, hot_act_weight))
        self.hot_act_penalty_cap = float(max(0.0, hot_act_penalty_cap))
        self.hot_act_min_over_c = float(max(0.0, hot_act_min_over_c))
        # ---- Step 2：目标开度口径 + 每栋"本步热容量"（由环境逐时注入）----
        self.hot_a_need_mode = str(hot_a_need_mode or 'const')
        # _cool_capacity[i] = 该楼本步热容量 [kWh/步] = 额定电功率 × 当前 COP，
        #   由 Multi-agent.py 的 pass_actions_to_reward 在每步 step 之前写入
        self._cool_capacity = []
        # _cool_a_ref[i] = 该楼本步「理想负荷所需开度」∈[0,1]（数据集理想负荷 ÷ 热容量），
        #   亦由环境每步注入；Step2 的 a_need 与 Step2A 的"过吹"罚都用它。
        self._cool_a_ref = []
        self.hot_over_weight = float(max(0.0, hot_over_weight))
        self.hot_over_tol = float(max(0.0, hot_over_tol))
        self.hot_over_tol_frac = float(max(0.0, hot_over_tol_frac))
        self.hot_over_penalty_cap = float(max(0.0, hot_over_penalty_cap))
        # ---- 带外温度罚封顶（P6-0 默认关闭：0 = 不封顶，回到原版 −δ²/−δ³）----
        self.hot_temp_cap = float(max(0.0, hot_temp_cap))
        self.cold_temp_cap = float(max(0.0, cold_temp_cap))
        # ---- 过冷关冷参数 ----
        self.cold_cool_weight = float(max(0.0, cold_cool_weight))
        # 带外轻罚区基准权重系数（cold_w_out = cold_cool_weight × 本值）。
        #   0.6 时 cold_w_out=51 > cold_near=45 → 罚分随"离 SP 越远"单调递增，
        self.cold_w_out_frac = float(min(1.0, max(0.0, cold_w_out_frac)))
        self.cold_gap_gain = float(max(0.0, cold_gap_gain))   # 低于下限每 1°C 放大倍数
        self.cold_stop_margin_c = float(max(0.0, cold_stop_margin_c))
        self.cold_maintain_act = float(min(1.0, max(0.0, cold_maintain_act)))
        self.cold_penalty_cap = float(max(0.0, cold_penalty_cap))
        # P1 改动：cold_lower 边界过渡带宽（0 = 关闭，按 P13-1 旧逻辑）
        self.trans_zone_c = float(max(0.0, trans_zone_c))
        # 带内（SP−band < T < SP）制冷罚权重：此时关冷没有舒适代价（温度仍在带内、
        # 且升温风险由过热项管），继续吹冷纯属浪费并会把楼推向低温 → 只罚超出维持开度的部分。
        self.cold_near_weight = float(max(0.0, cold_near_weight))
        # 带内「免罚窗口」半宽（相对 band 的比例）。
        #   0.5 → [SP−0.5, SP) 不罚（允许贴近 SP 的轻度预冷）；
        self.cold_near_free_frac = float(min(1.0, max(0.0, cold_near_free_frac)))
        # ---- P2：电费项权重（0 = 关闭，回到 P2 之前的行为）----
        self.cost_weight = float(max(0.0, cost_weight))
        # 制冷电费权重 + 逐楼额定电功率通道（由 Multi-agent 的 pass_actions_to_reward 注入）
        self.cool_cost_weight = float(max(0.0, cool_cost_weight))
        self._cool_nominal_power = []
        self.bat_weight = float(max(0.0, bat_weight))
        self.bat_loss_weight = float(max(0.0, bat_loss_weight))
        # 电池规格（由 pass_actions_to_reward 注入）：逐栋额定功率 kW / 每步小时数 / 容量 kWh
        self._bat_power = []
        self._bat_dt = []
        self._bat_cap = []
        self._bat_ratio = []
        # 价格滑动均值（参考价 p_ref）—— 状态量，reset() 里清零
        self._price_sum = 0.0
        self._price_n = 0
        # P-4（2026-09-30）：逐栋累计成本 Σprice×max(0,net)（**与 cost_weight 无关**）
        #   用途：best-ckpt 的选择指标要按它挑"既舒适又便宜"的快照（见 Multi-agent.py 的
        self._cost_raw_by_b = []
        # ---- 其它 ----
        self.act_hot_only_when_occupied = bool(act_hot_only_when_occupied)
        # 训练阶段关掉明细构建（加速）；评估阶段保持 True 供决策推演
        self.record_details = bool(record_details)
        # 诊断缓存：长度 = 楼栋数，供 marl_decision_trace 读取（无副作用）
        self._last_details = []
        # 本步动作缓存：由 install_action_hook() 在 reward.calculate 之前写入
        self._pending_acts = []
        # 运行统计（诊断用）：确认动作注入在「训练」阶段是否真的生效、
        # 以及过热保底/过冷关冷项被触发多少、平均罚多少分。
        self._stats = {
            'steps': 0,        # calculate 处理的楼步数
            'act_seen': 0,     # 其中读到有效 act_cool 的次数（=0 说明动作注入没生效！）
            'hot_trig': 0,     # 过热保底触发次数
            'hot_pay': 0.0,    # 过热保底累计罚分（负值）
            'hot_deficit': 0.0,  # 过热保底累计缺口 Σmax(0, a_need−act)；平均缺口=累计/触发次数
            'hot_need_load': 0,  # Step 2：其中用「负荷导出」口径算出 a_need 的次数（=0 ⇒ 退回了旧口径）
            # Step2A 过吹罚：确认它在真实运行时被触发、罚了多少、覆盖多少超额开度
            'over_trig': 0,
            'over_pay': 0.0,
            'over_excess': 0.0,
            'cold_trig': 0,    # 过冷关冷触发次数
            'cold_pay': 0.0,   # 过冷关冷累计罚分（负值）
            'cold_near_trig': 0,   # 带内(低于设定点)仍吹冷的触发次数（P3#2 起为"影子统计"）
            'cold_near_pay': 0.0,  # 该项累计"影子罚分"（P3#2 带内已放开、不计入 reward，仅供诊断）
            # P2 电费项：确认它在真实运行时被触发、罚了多少、覆盖多少电量
            'cost_trig': 0,        # 触发次数（price>0 且 净用电>0）
            'cost_pay': 0.0,       # 累计罚分（负值）
            'cost_kwh': 0.0,       # 累计被计费净用电 Σmax(0, net)，kWh
            'cost_raw': 0.0,       # 累计 Σ(price×max(0,net))，未乘权重的"货币"量
            # P-8（2026-09-30）：**制冷电费**项（只算制冷电耗、不含电池）
            'cool_cost_trig': 0,   # 触发次数
            'cool_cost_pay': 0.0,  # 累计罚分（负值）
            'cool_cost_kwh': 0.0,  # 累计制冷电耗 Σ(act × 额定电功率)，kWh
            # P3′ 电池套利项：充放电量、有效放电、以及"放电加权均价"（判断是否真在峰时放）
            'bat_trig': 0,         # 触发次数
            'bat_pay': 0.0,        # 累计项值（正=放电收益，负=充电成本）
            'bat_chg': 0.0,        # 累计充电能量 kWh
            'bat_dis': 0.0,        # 累计放电能量 kWh
            'bat_credit': 0.0,     # 累计「有效放电」（被负载真正吸收的部分）kWh
            'bat_dis_price_w': 0.0,  # Σ price×有效放电（算放电加权均价用）
            'bat_chg_price_w': 0.0,  # Σ price×充电
            # P-1 价差口径：参考价（价格滑动均值）与按价差加权的充放量
            'bat_pref': 0.0,           # 最近一次用到的参考价
            'bat_margin_credit': 0.0,  # Σ (price−p_ref)×有效放电（越大越好：说明放对了时段）
            'bat_margin_chg': 0.0,     # Σ (price−p_ref)×充电（越负越好：说明充在便宜时段）
            # 择时项 / 损耗项 的拆分，以及净循环量（诊断"是否过度循环"）
            'bat_arb_pay': 0.0,        # 择时项累计（正=靠高峰放电赚到）
            'bat_loss_pay': 0.0,       # 损耗项累计（负=为净循环付的代价）
            'bat_net_cycle': 0.0,      # Σ(充电 − 有效放电) kWh
        }
        # ---- KPI 口径累计（mid-eval 的「高温/低温%」由本类自己累加，P1′）-----------
        # 为什么不用"读楼栋对象"那条路：在自定义窗口（head/tail 探针）下它会与策略真实轨迹
        self.kpi_band_default = float(kpi_band_default)
        self._kpi = {
            'n_b': 0,
            'occ': [],      # 每栋有人步数
            'hot': [],      # 每栋高温步数
            'cold': [],     # 每栋低温步数
            't_sum': 0.0,   # 平均室温（所有楼步，与旧实现同语义）
            't_cnt': 0,
            'samples': [],  # 首个楼步的原始读数（供一次性自检，定位读数来源）
        }

    # -------------------------------------------------------------------------
    def reset(self):
        # 回合开始清空诊断/动作缓存（奖励本身无内部状态）。
        self._last_details = []
        self._pending_acts = []
        super().reset()

    # -------------------------------------------------------------------------
    def note_pending_actions(self, parsed) -> None:
        # 收下本步动作（按楼栋顺序），键名形如 `cooling_device_action`。
        # 由 install_action_hook() 在 env.step 内部、reward.calculate 之前调用。
        self._pending_acts = list(parsed or [])

    def stats_snapshot(self) -> dict:
        # 返回统计快照（训练后 / 评估后各取一次，便于对比两个阶段的触发情况）。
        return dict(self._stats)

    def stats_reset(self) -> None:
        # 清零统计（训练结束、进入评估前调用）。
        for key in self._stats:
            self._stats[key] = 0 if isinstance(self._stats[key], int) else 0.0
        # 价格滑动均值也随回合重置，避免跨 episode 串味
        self._price_sum = 0.0
        self._price_n = 0
        # 逐栋成本累计也随回合清零
        self._cost_raw_by_b = []

    def stats_summary(self) -> str:
        # 一行式统计摘要，供控制台打印。
        s = self._stats
        steps = max(1, int(s['steps']))
        hot = max(1, int(s['hot_trig']))
        cold = max(1, int(s['cold_trig']))
        return (
            f"奖励统计: 楼步={s['steps']} 读到act={s['act_seen']}({s['act_seen'] / steps:.1%}) "
            f"| 过热保底触发={s['hot_trig']}({s['hot_trig'] / steps:.1%}) 平均罚={s['hot_pay'] / hot:.2f} "
            f"平均缺口={s.get('hot_deficit', 0.0) / hot:.3f} "
            f"其中负荷导出={s.get('hot_need_load', 0) / hot:.1%}(口径={self.hot_a_need_mode}) "
            f"| 过吹罚触发={s.get('over_trig', 0)}({s.get('over_trig', 0) / steps:.1%}) "
            f"累计罚={s.get('over_pay', 0.0):.1f} 超额均值="
            f"{s.get('over_excess', 0.0) / max(1, s.get('over_trig', 0)):.4f}（权重={self.hot_over_weight:g}）"
            f"| 过冷关冷触发={s['cold_trig']}({s['cold_trig'] / steps:.1%}) 平均罚={s['cold_pay'] / cold:.2f} "
            f"| 带内吹冷(影子)触发={s.get('cold_near_trig', 0)}({s.get('cold_near_trig', 0) / steps:.1%}) "
            f"影子均罚={s.get('cold_near_pay', 0.0) / max(1, s.get('cold_near_trig', 0)):.2f}"
            f"[P3#2 带内已不罚，仅统计] "
            f"| 电费项触发={s.get('cost_trig', 0)}({s.get('cost_trig', 0) / steps:.1%}) "
            f"累计罚={s.get('cost_pay', 0.0):.1f} 计费电量={s.get('cost_kwh', 0.0):.0f}kWh "
            f"成本原值={s.get('cost_raw', 0.0):.2f}（权重={self.cost_weight:g}；"
            f"原值供 best-ckpt 选择，与权重无关）"
            f"| 制冷电费(P-8)触发={s.get('cool_cost_trig', 0)}"
            f"({s.get('cool_cost_trig', 0) / steps:.1%}) "
            f"累计罚={s.get('cool_cost_pay', 0.0):.1f} "
            f"制冷电量={s.get('cool_cost_kwh', 0.0):.0f}kWh（权重={self.cool_cost_weight:g}）"
            f"| 电池项触发={s.get('bat_trig', 0)}({s.get('bat_trig', 0) / steps:.1%}) "
            f"充={s.get('bat_chg', 0.0):.0f}kWh 放={s.get('bat_dis', 0.0):.0f}kWh "
            f"有效放={s.get('bat_credit', 0.0):.0f}kWh 项值={s.get('bat_pay', 0.0):.1f} "
            f"放电加权均价="
            f"{s.get('bat_dis_price_w', 0.0) / max(s.get('bat_credit', 0.0), 1e-9):.4f} "
            f"参考价={s.get('bat_pref', 0.0):.4f} "
            f"价差×有效放={s.get('bat_margin_credit', 0.0):+.2f} "
            f"价差×充={s.get('bat_margin_chg', 0.0):+.2f} "
            f"净循环={s.get('bat_net_cycle', 0.0):.0f}kWh "
            f"[择时{s.get('bat_arb_pay', 0.0):+.1f} 损耗{s.get('bat_loss_pay', 0.0):+.1f}]"
            f"（权重={self.bat_weight:g}/损耗权重={self.bat_loss_weight:g}；平价 0.0302 / 高价 0.0661）"
        )

    # -------------------------------------------------------------------------
    # KPI 口径累计（供 mid-eval 判据 + 评估阶段自检使用）
    @staticmethod
    def _as_float(v, default=float('nan')) -> float:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return default
        return f if np.isfinite(f) else default

    def _kpi_accumulate(self, i, indoor, cool_sp, heat_sp, band_obs, occ_obs) -> None:
        # 按 CityLearn KPI 口径累加「本楼本步」的不适计数（只统计有人步）。
        k = self._kpi
        while len(k['occ']) <= i:
            k['occ'].append(0)
            k['hot'].append(0)
            k['cold'].append(0)
        k['n_b'] = max(int(k['n_b']), i + 1)
        T = self._as_float(indoor)
        csp = self._as_float(cool_sp)
        hsp = self._as_float(heat_sp)
        band = self._as_float(band_obs, self.kpi_band_default)
        if not np.isfinite(band) or band <= 0.0:
            band = self.kpi_band_default
        # 读不到占用 → 按"有人"计（保守：不放过任何不适步）
        occ = self._as_float(occ_obs, 1.0)
        if np.isfinite(T):
            k['t_sum'] += float(T)
            k['t_cnt'] += 1
        if len(k['samples']) <= i:
            # 首个楼步的原始读数：一次性自检用（定位读数来源，见 mid-eval 的自检打印）
            k['samples'].append({'T': T, 'csp': csp, 'hsp': hsp, 'band': band, 'occ': occ})
        if occ <= 0.0:
            return
        k['occ'][i] += 1
        if np.isfinite(T) and np.isfinite(csp) and T > csp + band:
            k['hot'][i] += 1
        if np.isfinite(T) and np.isfinite(hsp) and T < hsp - band:
            k['cold'][i] += 1

    def cost_snapshot(self) -> dict:
        # P-4：成本累计快照（Σprice×max(0,net)），供 best-ckpt 选择指标使用。
        # 与 cost_weight 无关（即使电费项关闭也照常累计）⇒ 选择指标始终拿得到成本信号。
        return {
            'raw': float(self._stats.get('cost_raw', 0.0) or 0.0),
            'kwh': float(self._stats.get('cost_kwh', 0.0) or 0.0),
            'by_b': [float(v) for v in (self._cost_raw_by_b or [])],
        }

    def kpi_snapshot(self) -> dict:
        # 返回 KPI 累计快照（深拷贝 list，避免调用方误改内部状态）。
        return {key: (list(val) if isinstance(val, list) else val)
                for key, val in self._kpi.items()}

    def kpi_reset(self) -> None:
        # 清零 KPI 累计（每个探针窗口跑之前调用，保证是本窗口而非累计值）。
        n_b = int(self._kpi.get('n_b') or 0)
        self._kpi = {
            'n_b': n_b,
            'occ': [0] * n_b,
            'hot': [0] * n_b,
            'cold': [0] * n_b,
            't_sum': 0.0,
            't_cnt': 0,
            'samples': [],
        }

    def kpi_summary(self) -> str:
        # 一行式 KPI 口径摘要（与导出 discomfort_* 同定义），供评估阶段交叉自检。
        k = self._kpi

        def _pct(v):
            return ' na ' if not np.isfinite(v) else f'{v:5.1%}'

        parts = []
        for i in range(int(k.get('n_b') or 0)):
            n = k['occ'][i] if i < len(k['occ']) else 0
            h = (k['hot'][i] / n) if n else float('nan')
            c = (k['cold'][i] / n) if n else float('nan')
            parts.append(f'B{i + 1} {_pct(h)}/{_pct(c)}')
        mt = (k['t_sum'] / k['t_cnt']) if k['t_cnt'] else float('nan')
        mt_txt = 'na' if not np.isfinite(mt) else f'{mt:.2f}'
        return (f'KPI口径(奖励侧自算): {" ".join(parts)} '
                f'| 有人步 n={list(k["occ"])} 平均室温={mt_txt}°C')

    def _read_cool_act(self, b_idx: int, o) -> float:
        # 读取本楼本步制冷动作；拿不到返回 nan（拿不到就不加动作罚）。
        pending = self._pending_acts or []
        if 0 <= b_idx < len(pending):
            item = pending[b_idx] or {}
            if isinstance(item, dict):
                for key in (
                    'cooling_device_action',
                    'cooling_or_heating_device_action',
                    'cooling_action',
                    'cooling_device',
                ):
                    if key in item:
                        try:
                            return float(max(0.0, min(1.0, float(item[key]))))
                        except (TypeError, ValueError):
                            break
        # 兜底：万一上游把动作塞进了观测
        for key in ('cooling_device_action', 'cooling_or_heating_device_action'):
            if key in o:
                try:
                    return float(max(0.0, min(1.0, float(o[key]))))
                except (TypeError, ValueError):
                    break
        return float('nan')

    def _read_storage_act(self, b_idx: int, o) -> float:
        # 读取本楼本步电池动作 ∈[−1,1]（正=充电，负=放电）；拿不到返回 nan。
        pending = self._pending_acts or []
        if 0 <= b_idx < len(pending):
            item = pending[b_idx] or {}
            if isinstance(item, dict):
                for key in ('electrical_storage_action', 'electrical_storage', 'battery_action'):
                    if key in item:
                        try:
                            return float(max(-1.0, min(1.0, float(item[key]))))
                        except (TypeError, ValueError):
                            break
        for key in ('electrical_storage_action', 'electrical_storage'):
            if key in o:
                try:
                    return float(max(-1.0, min(1.0, float(o[key]))))
                except (TypeError, ValueError):
                    break
        return float('nan')

    # -------------------------------------------------------------------------
    def calculate(self, observations):
        # 按原版 ComfortReward 规则计算奖励。
        # Parameters
        reward_list = []
        details = []

        for b_idx, o in enumerate(observations):   # b_idx = 楼栋序号（读本楼动作用）
            self._stats['steps'] += 1
            # ---- 读取本步原始量 -------------------------------------------------
            heating_demand = o.get('heating_demand', 0.0)
            cooling_demand = o.get('cooling_demand', 0.0)
            # 原版用「热负荷 > 冷负荷」判断当前更像制热场景（影响带内线性罚的方向）
            heating = heating_demand > cooling_demand
            hvac_mode = o['hvac_mode']              # 0=off/自动, 1=制冷, 2=制热
            indoor = o['indoor_dry_bulb_temperature']
            cool_sp = o['indoor_dry_bulb_temperature_cooling_set_point']
            heat_sp = o['indoor_dry_bulb_temperature_heating_set_point']
            # band：显式给了就用显式值，否则用本步观测里的舒适带
            band = self.band if self.band is not None else o['comfort_band']

            # ---- P1′：KPI 口径累计（mid-eval 判据的唯一来源，见 __init__ 里 self._kpi 注释）----
            #   用观测里的 comfort_band（KPI 判定口径，本数据集 2.0），与奖励带 band 无关。
            self._kpi_accumulate(
                b_idx, indoor, cool_sp, heat_sp,
                o.get('comfort_band', None), o.get('occupant_count', None),
            )

            # 记录用（不参与奖励计算）
            set_point = cool_sp
            delta = 0.0
            branch = ''

            # ================= 分支 A：单一模式（制冷或制热）=================
            if hvac_mode in [1, 2]:
                # 制冷模式看制冷设定点，制热模式看制热设定点
                set_point = cool_sp if hvac_mode == 1 else heat_sp
                lower = set_point - band            # 舒适区下界
                upper = set_point + band            # 舒适区上界
                delta = abs(indoor - set_point)     # 距离设定点的绝对偏差

                if indoor < lower:
                    # ① 带外偏冷（制冷模式=过冷；制热模式=欠热）
                    #    制冷模式用 higher_exponent（本任务 3.0，立方重罚）
                    exponent = self.lower_exponent if hvac_mode == 2 else self.higher_exponent
                    reward = _clamp_temp_penalty(-(delta ** exponent), self.cold_temp_cap)
                    branch = (f'①T<SP−band → −δ^{exponent:g}（过冷/偏冷'
                              f'{_cap_txt(self.cold_temp_cap)}）')

                elif lower <= indoor < set_point:
                    # ② 带内但低于设定点：制冷模式=偏冷（线性轻罚）；制热模式=舒适（0）
                    reward = 0.0 if heating else -delta
                    branch = '②SP−band≤T<SP → ' + ('0（制热语义）' if heating else '−δ（带内偏冷）')

                elif set_point <= indoor <= upper:
                    # ③ 带内且不低于设定点：制冷模式=舒适（0）；制热模式=偏热（线性轻罚）
                    reward = -delta if heating else 0.0
                    branch = '③SP≤T≤SP+band → ' + ('−δ（制热语义）' if heating else '0（带内舒适）')

                else:
                    # ④ 带外偏热（制冷模式=过热，用 lower_exponent=2.0 平方罚）
                    exponent = self.higher_exponent if heating else self.lower_exponent
                    reward = _clamp_temp_penalty(-(delta ** exponent), self.hot_temp_cap)
                    branch = (f'④T>SP+band → −δ^{exponent:g}（过热'
                              f'{_cap_txt(self.hot_temp_cap)}）')

            # ================= 分支 B：无单一模式（hvac_mode 0/其它）=================
            else:
                # 舒适区 = [制热设定点−band, 制冷设定点+band]；两设定点之间不罚
                lower = heat_sp - band
                upper = cool_sp + band
                cooling_delta = indoor - cool_sp      # 相对制冷设定点（带符号）
                heating_delta = indoor - heat_sp      # 相对制热设定点（带符号）
                delta = cooling_delta
                set_point = cool_sp

                if indoor < lower:
                    exponent = self.higher_exponent if not heating else self.lower_exponent
                    reward = _clamp_temp_penalty(-(abs(heating_delta) ** exponent), self.cold_temp_cap)
                    branch = f'①T<heatSP−band → −|Δh|^{exponent:g}（过冷{_cap_txt(self.cold_temp_cap)}）'

                elif lower <= indoor < heat_sp:
                    reward = -(abs(heating_delta))
                    branch = '②heatSP−band≤T<heatSP → −|Δh|'

                elif heat_sp <= indoor <= cool_sp:
                    reward = 0.0
                    branch = '③heatSP≤T≤coolSP → 0（舒适）'

                elif cool_sp < indoor < upper:
                    reward = -(abs(cooling_delta))
                    branch = '④coolSP<T<coolSP+band → −|Δc|'

                else:
                    exponent = self.higher_exponent if heating else self.lower_exponent
                    reward = _clamp_temp_penalty(-(abs(cooling_delta) ** exponent), self.hot_temp_cap)
                    branch = f'⑤T>coolSP+band → −|Δc|^{exponent:g}（过热{_cap_txt(self.hot_temp_cap)}）'

            # =====================================================================
            # ★ 新增 ②：过热「动作保底」项 —— 让"过热就加大 act_cool"变成硬梯度
            act = self._read_cool_act(b_idx, o)          # 拿不到动作 → nan → 本项不生效
            if np.isfinite(act):
                self._stats['act_seen'] += 1
            try:
                outage = float(o.get('power_outage', 0.0) or 0.0)
            except (TypeError, ValueError):
                outage = 0.0
            over = indoor - (cool_sp + band)             # 超出制冷舒适带上界的温差
            occupied = True
            if self.act_hot_only_when_occupied:
                try:
                    occupied = float(o.get('occupant_count', 1.0) or 0.0) > 0.0
                except (TypeError, ValueError):
                    occupied = True

            r_act_hot = 0.0
            a_need = float('nan')
            _need_txt = ''          # Step 2：a_need 的口径说明（供推演叙事）
            deficit = 0.0
            if (
                self.hot_act_weight > 0.0
                and over > self.hot_act_min_over_c
                and outage < 0.5
                and occupied
                and np.isfinite(act)
            ):
                # Step 2：目标开度 a_need 的两种口径（实现见下方 max(...) 那一行）
                #   · 'load'（默认）：a_need = **本步理想负荷所需开度** a_ref
                _need_src = 'const'
                _need_const = self.hot_act_floor + self.hot_a_per_c * over
                a_need = _need_const
                if (str(getattr(self, 'hot_a_need_mode', 'const')).lower() == 'load'
                        and b_idx < len(self._cool_a_ref)
                        and float(self._cool_a_ref[b_idx] or 0.0) > 0.0):
                    # ---- P-5b（2026-09-30）：修「load 口径丢掉 over 增量」的 bug --------
                    #   旧写法 `a_need = a_ref` 是**覆盖** ⇒ 与"现在有多热"无关 ⇒ 策略永远
                    a_need = max(float(self._cool_a_ref[b_idx]), _need_const)
                    _need_src = 'load'
                    self._stats['hot_need_load'] = self._stats.get('hot_need_load', 0) + 1
                a_need = min(self.hot_a_cap, max(0.0, float(a_need)))
                _need_txt = (
                    f'Step2 理想负荷导出：a_ref={float(self._cool_a_ref[b_idx]):.3f}'
                    if _need_src == 'load' else
                    f'旧常数式：floor={self.hot_act_floor:g}+{self.hot_a_per_c:g}·over'
                )
                deficit = max(0.0, a_need - float(act))
                r_act_hot = -self.hot_act_weight * deficit
                if self.hot_act_penalty_cap > 0.0 and r_act_hot < -self.hot_act_penalty_cap:
                    r_act_hot = -self.hot_act_penalty_cap
                self._stats['hot_trig'] += 1
                self._stats['hot_pay'] += float(r_act_hot)
                self._stats['hot_deficit'] += float(deficit)
                reward += r_act_hot
            # ---- P-6′(ii)（2026-09-30）：修 `_hot_fired` 语义 --------------------
            #   旧语义 = "过热保底模块跑过"（`isfinite(a_need)`）⇒ 把"算得出 a_need"误判成
            try:
                _hot_fired = bool(np.isfinite(a_need) and float(deficit) > 0.0)
            except (NameError, TypeError, ValueError):
                _hot_fired = False

            # ★ 过冷「关冷」项 —— 治"过冷还制冷"（B2 夜间的典型病）；以下是**当前**分档定义
            #   记 cold_lower = SP − band（舒适带下沿）。罚的是"室温已在舒适侧、却仍在制冷"的开度：
            r_act_cold = 0.0
            cold_gap = 0.0
            cold_mult = 1.0
            cold_lower = cool_sp - band                    # 舒适带下沿（奖励口径，band=1.0）
            # 带内「免罚窗」下界，提前算好供诊断块安全引用（否则诊断块无法区分"受限窗"与"免罚窗"）
            cold_near_floor = cool_sp - band * self.cold_near_free_frac
            r_act_near = 0.0
            # 带内"影子罚分"——按旧规则本应罚多少，**仅供决策推演诊断、绝不计入 reward**；
            #   初值 0.0 保证 outage/非有限动作时诊断块也能安全引用
            shadow_near = 0.0
            # ---- 计算 cold_lower ± trans_zone 内的有效权重（cold_w_out → cold_near 平滑）----
            # 系数可配（cold_w_out_frac）。当前 cold_w_out(22.5) < cold_near(45) 的"倒挂"是
            cold_w_out = self.cold_cool_weight * self.cold_w_out_frac   # 带外轻罚基准权重
            cold_w_in = self.cold_near_weight              # 带内基准权重
            dist_lower = indoor - cold_lower               # T - cold_lower；负=带外，正=带内
            if self.trans_zone_c > 0.0 and cold_w_in > 0.0:
                half = self.trans_zone_c
                if -half <= dist_lower <= half:
                    t = (dist_lower + half) / (2.0 * half)        # 0~1 线性
                    t_smooth = t * t * (3.0 - 2.0 * t)             # smoothstep
                    effective_cold_weight = cold_w_out + (cold_w_in - cold_w_out) * t_smooth
                elif dist_lower < -half:
                    effective_cold_weight = cold_w_out
                else:
                    effective_cold_weight = cold_w_in
            else:
                # trans_zone=0（关闭 P1）或 cold_near_weight=0：保留 P13-1 旧的两段逻辑
                effective_cold_weight = cold_w_in if dist_lower >= 0.0 else cold_w_out
            if (
                (self.cold_cool_weight > 0.0 or self.cold_near_weight > 0.0)
                and outage < 0.5
                and np.isfinite(act)
                and indoor < cool_sp
            ):
                margin = max(0.05, self.cold_stop_margin_c)
                if indoor <= cold_lower - margin:
                    # 死区（带外深处）：原样强罚，越冷越重（设计意图）
                    penalized_act = float(act)
                    cold_gap = float((cold_lower - margin) - indoor)
                    cold_mult = 1.0 + self.cold_gap_gain * cold_gap
                    r_act_cold = -self.cold_cool_weight * penalized_act * cold_mult
                elif indoor < cold_lower:
                    # 带外轻罚区（margin < T < cold_lower）：P1 平滑权重
                    penalized_act = max(0.0, float(act) - self.cold_maintain_act)
                    r_act_cold = -effective_cold_weight * penalized_act
                else:
                    # 带内两段（免罚窗宽度 = band×cold_near_free_frac，默认 0.5 → SP−0.5）：
                    #   · [SP−band×free_frac, SP)          → 不罚（允许"贴近 SP 的轻度预冷"）
                    penalized_near = max(0.0, float(act) - self.cold_maintain_act)
                    shadow_near = -effective_cold_weight * penalized_near
                    if indoor < cold_near_floor:
                        r_act_near = shadow_near
                    if shadow_near < 0.0:
                        self._stats['cold_near_trig'] += 1
                        self._stats['cold_near_pay'] += float(shadow_near)
                if self.cold_penalty_cap > 0.0 and r_act_cold < -self.cold_penalty_cap:
                    r_act_cold = -self.cold_penalty_cap
                if self.cold_penalty_cap > 0.0 and r_act_near < -self.cold_penalty_cap:
                    r_act_near = -self.cold_penalty_cap
                if r_act_near < 0.0:
                    # 带内受限窗口的实际罚（与带外一起计入冷侧总罚统计）
                    self._stats['cold_trig'] += 1
                    self._stats['cold_pay'] += float(r_act_near)
                    reward += r_act_near
                if r_act_cold < 0.0:
                    self._stats['cold_trig'] += 1
                    self._stats['cold_pay'] += float(r_act_cold)
                reward += r_act_cold

            # ★ Step2A（2026-09-29）：过吹罚 —— 开度不应超过「理想负荷所需」a_ref
            #   依据（9cc92345 与 NOCONTROL 逐时对照）：NOCONTROL 开度 ≡ a_ref（比值 0.993）
            r_act_over = 0.0
            _over_txt = '未启用（权重=0 / 无 a_ref / 过热保底已生效）'
            if (self.hot_over_weight > 0.0 and not _hot_fired
                    and b_idx < len(self._cool_a_ref) and np.isfinite(act)):
                _a_ref = float(self._cool_a_ref[b_idx] or 0.0)
                if _a_ref > 0.0:
                    # P-5（2026-09-30）：容差 = 相对（tol_frac × a_ref）+ 绝对（tol）——
                    #   纯绝对 0.03 在低负荷步（B2 的 a_ref p10 = 0.03）等于免罚（容差比需求还大）
                    _tol = _a_ref * self.hot_over_tol_frac + self.hot_over_tol
                    _excess = float(act) - _a_ref - _tol
                    if _excess > 0.0:
                        r_act_over = -self.hot_over_weight * _excess
                        if (self.hot_over_penalty_cap > 0.0
                                and r_act_over < -self.hot_over_penalty_cap):
                            r_act_over = -self.hot_over_penalty_cap
                        reward += r_act_over
                        self._stats['over_trig'] = self._stats.get('over_trig', 0) + 1
                        self._stats['over_pay'] = (self._stats.get('over_pay', 0.0)
                                                   + float(r_act_over))
                        self._stats['over_excess'] = (self._stats.get('over_excess', 0.0)
                                                      + float(_excess))
                    _over_txt = (f'a_ref={_a_ref:.3f} act={float(act):.3f} '
                                 f'超出={_excess:+.3f} → R_over={r_act_over:.4f}')

            # ★ P2（2026-09-28）：电费项 —— 让策略为能耗负责
            #   r_cost = −cost_weight × price × max(0, net)。**已证伪，当前 cost_weight=0（关闭）**：
            r_cost = 0.0
            price = 0.0
            net = 0.0
            # P-4（2026-09-30）：**无论 cost_weight 是否为 0，都累计成本统计** ——
            #   best-ckpt 的选择指标（P4_COST_WEIGHT）要按成本挑快照，而 cost_raw 原先只在
            price = self._as_float(o.get('electricity_pricing', 0.0), 0.0)
            net = self._as_float(o.get('net_electricity_consumption', 0.0), 0.0)
            billable = max(0.0, net)
            if price > 0.0 and billable > 0.0:
                self._stats['cost_trig'] += 1
                self._stats['cost_kwh'] += float(billable)
                self._stats['cost_raw'] += float(price * billable)
                try:
                    while len(self._cost_raw_by_b) <= b_idx:
                        self._cost_raw_by_b.append(0.0)
                    self._cost_raw_by_b[b_idx] += float(price * billable)
                except Exception:
                    pass
                if self.cost_weight > 0.0:
                    r_cost = -self.cost_weight * price * billable
                    reward += r_cost
                    self._stats['cost_pay'] += float(r_cost)

            # ★ P-8（2026-09-30）：**制冷电费**项 —— 只罚"制冷用了多少电"，不碰电池
            #   r_cool_cost = −w × (act × 额定电功率)   ← 平摊电量、不乘电价（现行 P-8′ 口径）
            r_cool_cost = 0.0
            _cool_cost_txt = '未启用（权重=0 / 无额定功率 / 热侧正在要求多吹）'
            if (self.cool_cost_weight > 0.0 and not _hot_fired
                    and np.isfinite(act) and b_idx < len(self._cool_nominal_power)):
                _npw_c = float(self._cool_nominal_power[b_idx] or 0.0)
                if _npw_c > 0.0:
                    _kwh_c = float(act) * _npw_c
                    # P-8′（现行）：**平摊电量**（不乘电价）。P-8″（价加权 + net>0 闸门）已证伪：
                    #   P-8′ 0.969 ✓ / 价加权 1.033 ✗ / 加闸门 1.054 ✗✗（40 轮）
                    r_cool_cost = -self.cool_cost_weight * _kwh_c
                    reward += r_cool_cost
                    self._stats['cool_cost_trig'] = self._stats.get('cool_cost_trig', 0) + 1
                    self._stats['cool_cost_pay'] = (self._stats.get('cool_cost_pay', 0.0)
                                                    + float(r_cool_cost))
                    self._stats['cool_cost_kwh'] = (self._stats.get('cool_cost_kwh', 0.0)
                                                    + float(_kwh_c))
                    _cool_cost_txt = (f'act={float(act):.3f} npw={_npw_c:.2f}kW '
                                      f'→ {_kwh_c:.3f}kWh × w={self.cool_cost_weight:g} '
                                      f'→ R={r_cool_cost:.4f}')

            # ★ P-1 修订（2026-09-29）：电池项由「绝对电价」改为「**价差**」口径
            #   r_bat = −w × max(0, price − p_ref) × (chg − credit)，p_ref = 价格滑动均值(≈0.0334)
            r_bat = 0.0
            _bat_txt = '未启用（权重=0 / 无电池动作 / 无电池规格）'
            _p_ref_txt = 'na'
            _margin_txt = 'na'
            if self.bat_weight > 0.0:
                _bact = self._read_storage_act(b_idx, o)
                if (np.isfinite(_bact) and 0 <= b_idx < len(self._bat_power)
                        and float(self._bat_power[b_idx] or 0.0) > 0.0):
                    _bp = float(self._bat_power[b_idx])
                    _bdt = (float(self._bat_dt[b_idx])
                            if b_idx < len(self._bat_dt) and self._bat_dt[b_idx] else 1.0)
                    _bpr = self._as_float(o.get('electricity_pricing', 0.0), 0.0)
                    _bnet = self._as_float(o.get('net_electricity_consumption', 0.0), 0.0)
                    # ★ 用**环境给的电池真实充放流**（electrical_storage_electricity_consumption，
                    #   符号：正=充电 / 负=放电；已被 SOC 物理约束 —— 电池空后动作 −1、流量=0）
                    _br = (float(self._bat_ratio[b_idx])
                           if (b_idx < len(self._bat_ratio) and self._bat_ratio[b_idx]) else 1.0)
                    _e_obs = self._as_float(
                        o.get('electrical_storage_electricity_consumption', float('nan')),
                        float('nan'))
                    if np.isfinite(_e_obs):
                        _e = float(_e_obs) / max(_br, 1e-9)
                    else:
                        _e = float(_bact) * _bp * _bdt          # 兜底：退回动作估算
                    _chg = max(0.0, _e)
                    _dis = max(0.0, -_e)
                    # 不含电池的净用电 ≈ net − 充 + 放（用于给"有效放电"封顶）
                    _load = max(0.0, _bnet - _chg + _dis)
                    _credit = min(_dis, _load)
                    if _bpr > 0.0 and (_chg > 0.0 or _credit > 0.0):
                        # 按**价差**计价 —— margin = max(0, price − 参考价)
                        #   ⚠️ 必须取 max(0,·)：允许 margin 为负时"平价充电"会拿到**正**收益
                        _p_ref = (self._price_sum / self._price_n
                                  if self._price_n > 0 else _bpr)
                        # 两侧都取 max(0,·)（**对称**形式）—— ⚠️ 非对称版（放电侧用原始价差）
                        #   已实测证伪：放电均价 0.0408→0.0388、价差×有效放 +5.25→+2.81、
                        _margin = max(0.0, _bpr - _p_ref)
                        _margin_chg = _margin
                        # 择时项 + 损耗项
                        #   择时：只对"高于参考价"的窗口计价（高峰放=正、高峰充=负）
                        _net_cycle = _chg - _credit
                        _r_arb = -self.bat_weight * _margin * _net_cycle
                        # ⚠️ 损耗项**只按充电量**计价（不掺放电）—— 首版写成 price×(chg−credit)
                        #   会崩掉择时（"多放就少罚"= 奖励"随便在哪里放电"）：放电均价 0.0408→0.0332、
                        _r_loss = -self.bat_loss_weight * _bpr * _chg
                        r_bat = _r_arb + _r_loss
                        reward += r_bat
                        self._stats['bat_trig'] += 1
                        self._stats['bat_pay'] += float(r_bat)
                        self._stats['bat_arb_pay'] += float(_r_arb)
                        self._stats['bat_loss_pay'] += float(_r_loss)
                        self._stats['bat_net_cycle'] += float(_net_cycle)
                        self._stats['bat_chg'] += float(_chg)
                        self._stats['bat_dis'] += float(_dis)
                        self._stats['bat_credit'] += float(_credit)
                        self._stats['bat_dis_price_w'] += float(_bpr * _credit)
                        self._stats['bat_chg_price_w'] += float(_bpr * _chg)
                        self._stats['bat_margin_credit'] += float(_margin * _credit)
                        self._stats['bat_margin_chg'] += float(_margin_chg * _chg)
                        self._stats['bat_pref'] = float(_p_ref)
                        _p_ref_txt = f'{_p_ref:.4f}'
                        _margin_txt = f'{_margin:+.4f}/充侧{_margin_chg:+.4f}'
                    # 价格滑动均值：本步不参与自己的参考价（放在项计算之后更新）
                    #   注：奖励按楼循环调用，价格三栋相同 ⇒ 重复累加不改变均值
                    if _bpr > 0.0:
                        self._price_sum += float(_bpr)
                        self._price_n += 1
                    _bat_txt = (f'充={_chg:.3f} 有效放={_credit:.3f}（放={_dis:.3f}）kWh '
                                f'电价={_bpr:.4f} 参考价={_p_ref_txt} 价差={_margin_txt} '
                                f'权重={self.bat_weight:g} → R_bat={r_bat:.4f}')

            # =====================================================================
            # ★★★ 可修改区：继续加你自己的项 ★★★

            reward_list.append(reward)

            if not self.record_details:
                # 训练阶段：跳过明细构建与字符串格式化（纯开销，不影响奖励值与学习）
                continue

            # ---- 诊断（供 decision_trace.json 的 [奖励计算] 行展示）--------------
            # r_temp 是用"总回报 − 其它项"反推的，加入电费项后必须一起减掉，
            r_temp = float(reward - r_act_hot - r_act_cold - r_act_near - r_cost - r_act_over)
            # 带内制冷那一行的文案：P4/修复 —— 如实区分两段，不再一律说"不罚"
            #   · [cold_lower, cold_near_floor) → 受限窗，**实际罚** r_act_near
            if np.isfinite(act) and cold_lower <= indoor < cold_near_floor:
                _near_txt = (
                    f'T={indoor:.2f} ∈ [带下沿={cold_lower:.2f}, 免罚窗下界={cold_near_floor:.2f}) '
                    f'→ 受限窗，实际罚 −{effective_cold_weight:.1f}×'
                    f'{max(0.0, act - self.cold_maintain_act):.3f}={r_act_near:.4f}'
                    f'（免罚窗半宽=band×free_frac={band * self.cold_near_free_frac:.2f}°C）'
                )
            elif np.isfinite(act) and cold_near_floor <= indoor < cool_sp:
                _near_txt = (
                    f'T={indoor:.2f} ∈ [免罚窗下界={cold_near_floor:.2f}, SP={cool_sp:.2f}) '
                    f'→ 免罚窗，R_act_near=0；影子罚={shadow_near:.4f}'
                )
            else:
                _near_txt = f'未触发（T={indoor:.2f}，R_act_near={r_act_near:.4f}）'
            details.append({
                'r_temp': r_temp,
                'delta': float(delta),
                'set_point': float(set_point),
                'band': float(band) if band is not None else None,
                'hvac_mode': int(hvac_mode) if hvac_mode is not None else None,
                'is_hot': bool(indoor > cool_sp + band),
                'is_cold': bool(indoor < heat_sp - band),
                'act_cool': float(act) if np.isfinite(act) else None,
                'a_need': float(a_need) if np.isfinite(a_need) else None,
                'deficit': float(deficit),
                'over': float(over),
                'r_act_hot': float(r_act_hot),
                'r_act_cold': float(r_act_cold),
                'r_act_near': float(r_act_near),
                'r_below': 0.0,
                'r_act': float(r_act_hot + r_act_cold + r_act_near),
                'r_cost': float(r_cost), 'r_bat': float(r_bat),
                'r_act_over': float(r_act_over),
                'calc_lines': [
                    f'> [奖励计算] T={indoor:.2f}°C 设定点={set_point:.2f} 带=±{band:.2f} '
                    f'hvac={hvac_mode} 冷/热负荷={cooling_demand:.2f}/{heating_demand:.2f} '
                    f'act_cool={"na" if not np.isfinite(act) else f"{act:.3f}"}',
                    f'> [奖励计算] 命中{branch} → R_temp={r_temp:.4f}',
                    (
                        f'> [奖励计算] 过热保底: 超出带={over:+.2f}°C → 目标开度 a_need='
                        f'{a_need:.3f}（{_need_txt}，cap={self.hot_a_cap:g}） 缺口={deficit:.3f} '
                        f'→ R_act_hot=−{self.hot_act_weight:g}×缺口={r_act_hot:.4f}'
                        if np.isfinite(a_need) else
                        f'> [奖励计算] 过热保底: 未触发（over={over:+.2f}°C, '
                        f'act={"na" if not np.isfinite(act) else f"{act:.3f}"}, outage={int(outage >= 0.5)}）'
                    ),
                    (
                        f'> [奖励计算] 过冷关冷(带外 T<SP−band): ' + (
                            f'T={indoor:.2f} ≤ 带下沿−margin='
                            f'{cold_lower - max(0.05, self.cold_stop_margin_c):.2f} '
                            f'→ 目标开度 0（死区关冷），低于下限={cold_gap:.2f}°C 放大×{cold_mult:.2f}'
                            f'，R_act_cold={r_act_cold:.4f}'
                            if indoor <= cold_lower - max(0.05, self.cold_stop_margin_c) else
                            (f'带下沿−margin < T={indoor:.2f} < 带下沿={cold_lower:.2f} → 允许维持≤'
                             f'{self.cold_maintain_act:g}，P1 平滑权重'
                             f'−{effective_cold_weight:.1f}'
                             f'（cold_cool({self.cold_cool_weight:g})×w_out_frac({self.cold_w_out_frac:g})'
                             f'={cold_w_out:g} → cold_near={cold_w_in:g}, '
                             f'trans_zone={self.trans_zone_c:g}）'
                             f'×penalized_act，R_act_cold={r_act_cold:.4f}'
                             if indoor < cold_lower else
                             f'T={indoor:.2f} ≥ 带下沿={cold_lower:.2f} → 未触发（不限制制冷），'
                             f'R_act_cold={r_act_cold:.4f}')
                        )
                    ),
                    f'> [奖励计算] 带内制冷(SP−band ≤ T < SP): ' + _near_txt,
                    (f'> [奖励计算] 电费项(P2): price={price:.4f} 净用电={net:.3f}kWh '
                     f'→ R_cost=−{self.cost_weight:g}×{price * max(0.0, net):.5f}={r_cost:.4f}'
                     if self.cost_weight > 0.0 else
                     '> [奖励计算] 电费项(P2): 未启用（cost_weight=0）'),
                    f'> [奖励计算] 制冷电费(P-8): {_cool_cost_txt}',
                    f'> [奖励计算] 过吹罚(Step2A): {_over_txt}',
                    f'> [奖励计算] 电池套利(P3′): {_bat_txt}',
                    f'> [奖励计算] 合计 R=R_temp({r_temp:.4f})+R_act_hot({r_act_hot:.4f})'
                    f'+R_act_cold({r_act_cold:.4f})+R_act_near({r_act_near:.4f})'
                    f'+R_over({r_act_over:.4f})+R_cost({r_cost:.4f})'
                    f'+R_cool_cost({r_cool_cost:.4f})+R_bat({r_bat:.4f})={reward:.4f}',
                ],
            })

        # ---- 与原版一致：central_agent 时把各楼奖励求和 ------------------------
        if self.central_agent:
            reward = [sum(reward_list)]
            details = [details[0] if details else {}]
        else:
            reward = reward_list

        self._last_details = details
        return reward


# =============================================================================
# 奖励自检：CustomComfortReward 与数据集原版 ComfortReward 的数值等价性校验
def check_reward_equivalence(reward_kwargs, verbose: bool = True) -> float:
    # 自检：CustomComfortReward 与数据集原版 ComfortReward 是否逐位一致。
    # ⚠️ `reward_kwargs` **必须显式传入**（通常就是脚本里的 CUSTOM_REWARD_KWARGS），
    meta = {'central_agent': False}
    cases = []
    for hvac in (0, 1, 2):
        for cool_sp, heat_sp in ((24.0, 20.0), (27.22, 24.44)):
            for t in (heat_sp - 3.0, cool_sp - 3.5, cool_sp - 1.0, cool_sp - 0.5,
                      cool_sp, cool_sp + 0.5, cool_sp + 1.0, cool_sp + 1.5, cool_sp + 4.0):
                for heat_d, cool_d in ((0.0, 1.0), (1.0, 0.0)):
                    cases.append({
                        'hvac_mode': hvac,
                        'indoor_dry_bulb_temperature': t,
                        'indoor_dry_bulb_temperature_cooling_set_point': cool_sp,
                        'indoor_dry_bulb_temperature_heating_set_point': heat_sp,
                        'comfort_band': 2.0,
                        'heating_demand': heat_d,
                        'cooling_demand': cool_d,
                    })

    worst = 0.0
    # 注 1：下面用例不带动作（_pending_acts 为空）→ 动作项读不到 act，自动不生效，
    #       因此这里比的是「温度项」是否与原版逐位一致。
    _kw_no_cap = dict(reward_kwargs, hot_temp_cap=0.0, cold_temp_cap=0.0)
    _band_now = float(reward_kwargs.get('band') or 0.0)
    _band_txt = f'{_band_now:g}'
    for label, kw_mine, kw_orig in (
        (f'温度项 band={_band_txt}（两侧同 band，封顶已关闭）', dict(_kw_no_cap),
         {'band': reward_kwargs.get('band'), 'lower_exponent': reward_kwargs.get('lower_exponent'),
          'higher_exponent': reward_kwargs.get('higher_exponent')}),
        ('温度项 band=None（逐楼用观测 comfort_band，封顶已关闭）', dict(_kw_no_cap, band=None),
         {'band': None, 'lower_exponent': reward_kwargs.get('lower_exponent'),
          'higher_exponent': reward_kwargs.get('higher_exponent')}),
    ):
        mine = CustomComfortReward(meta, **kw_mine)
        orig = ComfortReward(meta, **kw_orig)
        a = np.asarray(mine.calculate(cases), dtype=float).reshape(-1)
        b = np.asarray(orig.calculate(cases), dtype=float).reshape(-1)
        diff = float(np.max(np.abs(a - b))) if a.size else 0.0
        worst = max(worst, diff)
        if verbose:
            print(f'[奖励自检] {label}: n={a.size} 最大绝对差={diff:.3e} '
                  f'{"一致" if diff == 0.0 else "不一致"}')

    # ---- 动作项效果演示：过热状态下「加大 act_cool」是否真的提高回报 ----
    if verbose:
        print('\n[奖励自检] 过热状态下的动作梯度演示 '
              f'（T=33.0, SP=24.44, band={_band_txt}, hvac=1, 有冷负荷）:')
        demo = CustomComfortReward(meta, **reward_kwargs)
        o_hot = {
            'hvac_mode': 1,
            'indoor_dry_bulb_temperature': 33.0,
            'indoor_dry_bulb_temperature_cooling_set_point': 24.44,
            'indoor_dry_bulb_temperature_heating_set_point': 20.0,
            'comfort_band': 2.0,
            'heating_demand': 0.0,
            'cooling_demand': 1.0,
            'power_outage': 0.0,
            'occupant_count': 2.0,
        }
        over = 33.0 - (24.44 + _band_now)
        a_need = min(demo.hot_a_cap, demo.hot_act_floor + demo.hot_a_per_c * over)
        print(f'    超出带 = {over:.2f}°C → 目标开度 a_need = {a_need:.3f}'
              f'（floor={demo.hot_act_floor:g}+{demo.hot_a_per_c:g}·over，cap={demo.hot_a_cap:g}）')
        prev = None
        for act in (0.0, 0.2, 0.35, 0.5, 0.7, 0.9, 1.0):
            demo.note_pending_actions([{'cooling_device_action': act}])
            r = float(demo.calculate([o_hot])[0])
            gain = '' if prev is None else f'  Δ={r - prev:+.3f}'
            print(f'    act_cool={act:.2f} → R={r:9.3f}{gain}')
            prev = r
        print('    → act_cool 低于 a_need 时 ∂R/∂act_cool = +hot_act_weight '
              f'= +{demo.hot_act_weight:g}，回报随开度单调上升（这就是"加大开冷的意愿"）')

        print(f'\n[奖励自检] 过冷状态下的关冷梯度演示'
              f'（T=22.0, SP=24.44, band={_band_txt}）:')
        o_cold = dict(o_hot, indoor_dry_bulb_temperature=22.0)
        for act in (0.0, 0.2, 0.4, 0.6):
            demo.note_pending_actions([{'cooling_device_action': act}])
            r = float(demo.calculate([o_cold])[0])
            print(f'    act_cool={act:.2f} → R={r:9.3f}')

    if verbose:
        print(f'\n[奖励自检] 温度项总体最大绝对差 = {worst:.3e}')
    return worst
