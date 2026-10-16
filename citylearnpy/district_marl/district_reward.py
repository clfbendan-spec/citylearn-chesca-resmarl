# -*- coding: utf-8 -*-
"""DistrictPeakReward —— 把"区域级指标"显式写进奖励。

【为什么要在奖励里加，而不是只加观测】
  观测只解决"agent 看得到"，不解决"agent 有动机"。上一轮分析指出：现有奖励
  要么根本没有社区量（Multi-agent.py 用的 CustomComfortReward），要么只有被动
  标量（ComfortOutagePenaltyReward 的 district_peak 标志）。而区域峰值
  `district_peak = max_t Σ_i load_i(t)` 是**不可分解**的全局量，单靠局部奖励
  无法稳定逼近 ⇒ 必须显式给一个与它对齐的项。

【三个可调项，默认全部关闭（= 与原奖励逐位一致）】
  ① 社区尖峰惩罚  r -= w × max(0, 社区净用电 − 目标线)
       直接对齐 all_time_peak / daily_peak 类 KPI 的方向（越小越好）。
  ② 团队奖励混合  r_i ← (1−s)·r_i + s·mean(r)
       混入公共分量 ⇒ 压缩"各扫门前雪"的激励，治搭便车；
       代价是信用分配变糊（s 太大 ⇒ 谁都不愿多做），故默认 0、训练入口给 0.25。
  ③ 错峰引导     谷底期奖励 SOC 越低者越多
       区域谷底若三栋一起充，会把谷填平甚至造出新的次峰（rebound peak）。
       该项把"让最空的先充"变成一个可学的信号 ⇒ 错峰。
       需要观测含 own_soc_rank 才学得动（本包默认提供）。

  ④ 峰前储能预留（SOC reserve）  窗内 r_i -= w × max(0, 目标水位 − soc_i)
       【动机·实测】v4（0.8903）与 CHESCA（0.638）的社区峰值差 7.078 kW 里，
       电池一项占 4.384 kW（62%）；进入 v4 决定指标的那一步（#669, hour=22）时，
       三栋 SOC 只有 0.199/0.200/0.362，而 CHESCA 是 0.607/0.600/0.765
       —— 差距不是"动作空间不够"，而是**峰前没把电留住**。
       ⇒ 在窗口内对"低 SOC"直接给惩罚，把"留电"变成可学信号。
       【为什么 agent 学得动】奖励侧与策略侧观测都含 `hour`（1..24，
       step i ⇒ hour = i%24+1，实测确认），策略能分辨"现在是不是窗口内"。
       【诊断数据】#669 通道分解见 CHESCA-v4峰步通道分解.md。

  ⑤ 尖峰步豁免（ns gate）  Σ_i non_shiftable_load_i > 阈值 ⇒ 本步豁免 ④ 的罚
       【为什么需要（2026-10-16 实测）】④ 用"傍晚"当门控，但决定指标的 #669 是
       **无预警异常日**：当天 h21 社区不可移负荷仅 1.736 kW，h22 一步跳到 15.388 kW。
       实测判据可分性：当日累计 ns @h18/h20/h21 的全季分位只有 50.0%/43.3%/43.3%
       ⇒ **任何"基于已观测 ns 预测异常日"的门控都提前不了**（不可移负荷逐时独立）。
       但 CityLearn 的 obs **本步就带 `non_shiftable_load`**（实测确认）⇒ 根本不用预测：
       只要"平时要求水位、ns 高时豁免"，尖峰步自然会被放行去放电削峰。
       【等价于 CHESCA 的形态】规则派全天顶在高水位、尖峰来了再放 —— 本项把
       "全天高水位"换成"窗口内高水位 + 尖峰豁免"，方向一致而代价更小。
       【判据不可操纵】非可操纵量（外生不可移负荷），agent 无法通过削峰把自己
       "挤出豁免"（若用 net 判据就会出现这种自相矛盾）。
       ⚠️ 读不到 ns ⇒ 按 0 计 ⇒ 不豁免（保守：继续要求水位），不会静默失效成常数偏置。

  ⑥ 尖峰步充放计价（spike flow pricing）  豁免步 r_i -= w_s × flow_i
       【动机·实测（2026-10-16）】⑤ 的豁免是"无条件"的：尖峰步只免罚，不区分本栋在
       **充电还是放电**。这导致 B 组在 #690(h19, ns=9.848) 反充 1.74 kWh，自己把峰值
       从 #669 搬到了 #690 —— **打地鼠**。
       【为什么不是靠"判异常日"解决】实测：不可移负荷逐时独立，#669 当天 h21 社区 ns
       仅 1.736、h22 跳到 15.388（8.9 倍）⇒ 任何提前预测都不可能。但本步的
       `electrical_storage_electricity_consumption` 是**本步**值（实测：《_probe_bat_flow_phase.py》
       H1 残差 1.7e-2 vs H2（滞后一步）1.18，区分度 70×），所以"本栋此刻在干什么"
       **不需要预测**。
       【形态】豁免步把"什么都不做"换成本栋**电网侧净电池流**计价：
            flow_i > 0（充电，给社区加负荷）⇒ 罚
            flow_i < 0（放电，替社区削峰）  ⇒ 奖
       单位与 `net_electricity_consumption` 同源（实测 grid 侧 kWh），故该权重直接
       就是"每 kWh 电池流值多少分"。
       【为什么不破坏 #668 的预充】实测豁免集（gate=6，23 步）**不含 #668**（h21，
       ns=1.736 < 6）⇒ 预充步仍在④的罚区，预充动机原样保留；只有真正的尖峰步
       （#643 ns=9.096 / #669 ns=15.388 / #690 ns=9.848）才按本项计价。
       ⚠️ 读不到 flow ⇒ 按 0 计 ⇒ 与"豁免"完全等价，不会静默变成常数偏置。

【零改动承诺】
  继承 custom_comfort_reward.CustomComfortReward（**不修改**它）。
  因父类 __init__ 带 **kwargs，本类可安全接收并透传全部原奖励参数
  （例如 utils.config.CUSTOM_REWARD_KWARGS）。

【统计与可审计】
  每局累计：社区峰值、超目标线步数、超线累积量；由 district_summary() 输出。
"""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, Sequence

import numpy as np

from custom_comfort_reward import CustomComfortReward

from district_marl.district_features import rank_norm


def _as_hour_window(value) -> tuple:
    """把任意输入整理成 (lo, hi) 的小时窗口；非法输入 ⇒ (17.0, 22.0)。

    支持 tuple/list/字符串（'17,22'）。窗口按闭区间理解，允许跨午夜（lo > hi）。
    """
    lo, hi = 17.0, 22.0
    try:
        if isinstance(value, str):
            parts = [p for p in value.replace('，', ',').split(',') if p.strip() != '']
            value = parts
        seq = list(value)
        if len(seq) >= 2:
            lo, hi = float(seq[0]), float(seq[1])
    except Exception:
        lo, hi = 17.0, 22.0
    if not (np.isfinite(lo) and np.isfinite(hi)):
        lo, hi = 17.0, 22.0
    return (lo, hi)


def _read(o: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    """从观测字典安全读一个 float（缺键 / None / 非法 ⇒ default）。"""
    try:
        v = o.get(key, default)
        if v is None:
            return float(default)
        return float(v)
    except Exception:
        return float(default)


class DistrictPeakReward(CustomComfortReward):
    """社区尖峰惩罚 + 团队奖励混合 + 谷期错峰引导（可逐项关闭）。

    参数（除 env_metadata 外全部可选；默认 0 ⇒ 与 CustomComfortReward 逐位一致）
    --------------------------------------------------------------------------
    district_peak_weight   社区尖峰惩罚权重（0 = 关闭）
    district_peak_target   社区净用电的"目标线"，超过才罚
    district_valley_target 社区谷底判据（错峰引导只在谷底生效）
    district_net_scale     归一尺度（仅用于统计展示）
    district_team_share    团队奖励混合系数 s ∈ [0,1]（0 = 关闭）
    district_stagger_weight 错峰引导权重（0 = 关闭）
    district_stagger_soc_target 错峰引导的 SOC 目标（低于它才算"该先充"）
    district_soc_reserve_weight 峰前储能预留权重（0 = 关闭 ⇒ 逐位一致）
    district_soc_reserve_hours  预留窗口（hour 闭区间，hour 取值 1..24）
    district_soc_reserve_target 预留水位目标（SOC 低于它才罚）
    district_soc_reserve_ns_gate 尖峰步豁免阈值 kW（0 = 关闭 ⇒ 逐位一致）；
                                社区不可移负荷超过它时，本步豁免预留罚
    district_soc_reserve_spike_weight 尖峰(豁免)步的"电池流计价"权重（0 = 关闭 ⇒ 逐位一致）
                                豁免步 r_i -= w × electrical_storage_electricity_consumption_i
                                （充为正 ⇒ 罚；放为负 ⇒ 奖）
    **kwargs              原样透传给 CustomComfortReward（含原奖励全部可调项）
    """

    def __init__(
        self,
        env_metadata,
        district_peak_weight: float = 0.0,
        district_peak_target: float = 6.0,
        district_valley_target: float = 4.0,
        district_net_scale: float = 9.0,
        district_team_share: float = 0.0,
        district_stagger_weight: float = 0.0,
        district_stagger_soc_target: float = 0.85,
        # 【方案 5：峰前储能预留】傍晚窗内惩罚低 SOC（0 = 关闭 ⇒ 逐位一致）
        district_soc_reserve_weight: float = 0.0,
        district_soc_reserve_hours=(17.0, 22.0),
        district_soc_reserve_target: float = 0.60,
        # 【方案 6：尖峰步豁免】社区不可移负荷 > 阈值 ⇒ 本步豁免预留罚（允许放电）
        #   0 = 关闭（逐位一致，等价于方案 5 原样）
        district_soc_reserve_ns_gate: float = 0.0,
        # 【方案 7：尖峰步充放计价】豁免步不再"什么都不做"，而是按本栋电网侧净电池流计价
        #   flow > 0（充电，加负荷）⇒ 罚；flow < 0（放电，削峰）⇒ 奖
        #   0 = 关闭（逐位一致，等价于方案 6 原样）
        district_soc_reserve_spike_weight: float = 0.0,
        # 【方案 1：按贡献分摊】把"集体惩罚"按 own_net_i / dist_net 分摊
        #   0.0 = 退回旧的均摊（向后兼容原版）
        #   1.0 = 严格按"自己贡献的那部分"承担（a2 烧 50% 拿 50% 惩罚）
        district_attribution: float = 0.0,
        # 【方案 2：峰值-锚定】把"每步惩罚"按 (dist_net / episode_peak_so_far) 缩放
        #   0.0 = 关闭（按 over 量固定罚）
        #   1.0 = 接近/超过历史峰值的步罚更狠；远离峰值的步几乎不罚
        #   ⇒ 有效把"哪一步造成新峰"识别出来，n-step return 可向其反向传播
        district_peak_anchored: float = 0.0,
        **kwargs,
    ):
        # 父类带 **kwargs ⇒ 原奖励参数无痛透传（不修改父类即得全部原行为）
        super().__init__(env_metadata, **kwargs)

        self.district_peak_weight = float(max(0.0, district_peak_weight))
        self.district_peak_target = float(district_peak_target)
        self.district_valley_target = float(district_valley_target)
        self.district_net_scale = float(district_net_scale) if abs(district_net_scale) > 1e-9 else 1.0
        self.district_team_share = float(min(max(district_team_share, 0.0), 1.0))
        self.district_stagger_weight = float(max(0.0, district_stagger_weight))
        self.district_stagger_soc_target = float(
            min(max(district_stagger_soc_target, 0.0), 1.0))
        # 方案 1/2 新参数
        self.district_attribution = float(min(max(district_attribution, 0.0), 1.0))
        self.district_peak_anchored = float(min(max(district_peak_anchored, 0.0), 1.0))

        # 【方案 5】峰前储能预留：权重夹到 ≥0；窗口容错成 (lo, hi) 两个有限数
        self.district_soc_reserve_weight = float(max(0.0, district_soc_reserve_weight))
        self.district_soc_reserve_hours = _as_hour_window(district_soc_reserve_hours)
        self.district_soc_reserve_target = float(
            min(max(district_soc_reserve_target, 0.0), 1.0))
        # 【方案 6】尖峰步豁免阈值（0 = 关闭 ⇒ 逐位一致）
        self.district_soc_reserve_ns_gate = float(max(0.0, district_soc_reserve_ns_gate))
        # 【方案 7】尖峰(豁免)步的电池流计价权重（0 = 关闭 ⇒ 逐位一致）
        self.district_soc_reserve_spike_weight = float(
            max(0.0, district_soc_reserve_spike_weight))

        self._dm_peak: Optional[float] = None
        self._dm_peak_sum: float = 0.0
        self._dm_over_steps: int = 0
        self._dm_over_amount: float = 0.0
        self._dm_steps: int = 0
        self._dm_last_district_net: float = 0.0
        # 【方案 5】审计计数：窗口命中步数 / 累计缺口 / 窗口内 SOC 均值
        self._dm_reserve_steps: int = 0
        self._dm_reserve_deficit_sum: float = 0.0
        self._dm_reserve_soc_sum: float = 0.0
        # 【方案 6】审计：被"尖峰豁免"放行的步数 + 这些步的社区 ns 累计/最大值
        self._dm_reserve_exempt_steps: int = 0
        self._dm_reserve_exempt_ns_sum: float = 0.0
        self._dm_reserve_exempt_ns_max: float = 0.0
        # 【方案 7】审计：按电池流计价的豁免步数 / 累计流(kWh) / 充电步数 / 放电步数
        self._dm_reserve_spike_steps: int = 0
        self._dm_reserve_spike_flow_sum: float = 0.0
        self._dm_reserve_spike_chg_steps: int = 0
        self._dm_reserve_spike_dis_steps: int = 0

    # ---- 生命周期 -----------------------------------------------------------
    def reset(self) -> None:
        """每局重置：清空社区峰值与累计统计（父类统计同时复位）。"""
        try:
            super().reset()
        except Exception:
            pass
        self._dm_peak = None
        self._dm_peak_sum = 0.0
        self._dm_over_steps = 0
        self._dm_over_amount = 0.0
        self._dm_steps = 0
        self._dm_last_district_net = 0.0
        self._dm_reserve_steps = 0
        self._dm_reserve_deficit_sum = 0.0
        self._dm_reserve_soc_sum = 0.0
        self._dm_reserve_exempt_steps = 0
        self._dm_reserve_exempt_ns_sum = 0.0
        self._dm_reserve_exempt_ns_max = 0.0
        self._dm_reserve_spike_steps = 0
        self._dm_reserve_spike_flow_sum = 0.0
        self._dm_reserve_spike_chg_steps = 0
        self._dm_reserve_spike_dis_steps = 0

    # ---- 是否真正启用区域项（供日志/自检） --------------------------------
    @property
    def district_active(self) -> bool:
        return (self.district_peak_weight > 0.0
                or self.district_team_share > 0.0
                or self.district_stagger_weight > 0.0
                or self.district_attribution > 0.0
                or self.district_peak_anchored > 0.0
                or self.district_soc_reserve_weight > 0.0)

    # ---- 【方案 5】时刻读取与窗口判定 -------------------------------------
    @staticmethod
    def _dm_hour_now(observations) -> float:
        """读"当前步的小时"（1..24）。读不到 ⇒ nan（该项本步不生效）。

        只用 obs['hour']（CityLearn 原生字段，实测 step i ⇒ hour = i%24+1）。
        **不做任何"步数取模"的兜底**：猜错时刻比不生效更危险。
        """
        for o in observations or ():
            try:
                if isinstance(o, Mapping) and o.get('hour') is not None:
                    return float(o.get('hour'))
            except Exception:
                continue
        return float('nan')

    def _dm_in_reserve_hours(self, hour: float) -> bool:
        """hour 是否落在预留窗口内（闭区间；lo > hi 时按跨午夜理解）。"""
        if not np.isfinite(hour):
            return False
        lo, hi = self.district_soc_reserve_hours
        h = float(hour)
        if lo <= hi:
            return bool(lo <= h <= hi)
        return bool(h >= lo or h <= hi)

    # ---- 【方案 6】尖峰步豁免 -------------------------------------------------
    @staticmethod
    def _dm_district_ns(observations) -> float:
        """社区不可移负荷 Σ_i non_shiftable_load_i（读不到某栋 ⇒ 该栋按 0 计）。

        为什么用这个量而不是 net：net 含 agent 自己的动作 ⇒ 可被操纵，
        会出现"削峰削到自己失去豁免"的自相矛盾。non_shiftable_load 是外生的。
        """
        s = 0.0
        for o in observations or ():
            s += _read(o, 'non_shiftable_load', 0.0)
        return float(s)

    def _dm_reserve_exempt(self, observations) -> bool:
        """本步是否因"社区不可移负荷超阈值"而豁免预留罚。"""
        if self.district_soc_reserve_ns_gate <= 0.0:
            return False
        ns = self._dm_district_ns(observations)
        if ns <= self.district_soc_reserve_ns_gate:
            return False
        self._dm_reserve_exempt_steps += 1
        self._dm_reserve_exempt_ns_sum += ns
        self._dm_reserve_exempt_ns_max = max(self._dm_reserve_exempt_ns_max, ns)
        return True

    # ---- 核心 ---------------------------------------------------------------
    def calculate(self, observations: List[Mapping[str, Any]]) -> List[float]:
        """先算原舒适/电池奖励，再叠加区域项。"""
        rewards = list(super().calculate(observations))

        # central_agent（单智能体）下父类返回长度 1 ⇒ 区域项无法逐楼施加，原样返回
        if not observations or len(rewards) != len(observations):
            return rewards

        nets = [_read(o, 'net_electricity_consumption') for o in observations]
        district_net = float(np.sum(nets))
        self._dm_last_district_net = district_net

        if self._dm_peak is None:
            self._dm_peak = district_net
        else:
            self._dm_peak = max(float(self._dm_peak), district_net)
        self._dm_peak_sum += district_net
        self._dm_steps += 1

        # ① 社区尖峰惩罚（不可分解的全局量的显式代理）
        over = max(0.0, district_net - self.district_peak_target)
        peak_pen_total = self.district_peak_weight * over
        if over > 0.0:
            self._dm_over_steps += 1
            self._dm_over_amount += over

        # 【方案 2：峰值-锚定】把"接近/超过本局峰值的步"放大惩罚
        # 远离峰值的步几乎不罚 ⇒ 让 n-step return 能把"造成新峰的那步"识别出来
        if self.district_peak_anchored > 0.0 and self._dm_peak is not None and self._dm_peak > 1e-9:
            # ratio = dist_net / episode_peak ∈ (0, 1+]，>1 时表示本步破了本局纪录
            ratio = district_net / self._dm_peak
            # 0.7 是个温和的放大：ratio=1 时给 ~1.0 因子，ratio=0.5 时给 ~0.21
            anchor_w = self.district_peak_anchored * (max(0.0, ratio - 0.3) / 0.7)
            anchor_w = min(anchor_w, 1.0 + self.district_peak_anchored)  # 防止"破纪录步"权重失控
            peak_pen_total = peak_pen_total * (1.0 + anchor_w)
        else:
            anchor_w = 0.0

        # ③ 谷期错峰引导（让 SOC 最低的先充）
        stagger = np.zeros(len(rewards), dtype=float)
        if (self.district_stagger_weight > 0.0
                and district_net <= self.district_valley_target):
            socs = [_read(o, 'electrical_storage_soc', 0.5) for o in observations]
            ranks = rank_norm(socs)          # 0 = SOC 最低
            for i in range(len(rewards)):
                # SOC 越低 → 名次越小 → (1−rank) 越大 → 充电激励越强
                # 只对"低于目标"的楼给分，避免高 SOC 楼也被推着充
                gap = max(0.0, self.district_stagger_soc_target - float(socs[i]))
                stagger[i] = self.district_stagger_weight * gap * (1.0 - float(ranks[i]))

        # ② 团队奖励混合（在施加 ①②③ 之前做，保证"公共分量"来自真实回报）
        if self.district_team_share > 0.0 and len(rewards) > 1:
            mean_r = float(np.mean(rewards))
            s = self.district_team_share
            rewards = [(1.0 - s) * float(r) + s * mean_r for r in rewards]

        # 【方案 1：按贡献分摊】把 peak_pen_total 按 own_net_i / dist_net 分摊
        #   attribution=0 ⇒ 均摊（peak_pen_total / n）—— 旧行为
        #   attribution=1 ⇒ 严格按份额（a2 烧 50% 拿 50% 惩罚）—— 谁烧谁负责
        #   中间值 ⇒ attribution 部分按份额、剩余部分均摊（防止负 net 时分母异常）
        peak_pen_per_agent = np.zeros(len(rewards), dtype=float)
        if peak_pen_total > 0.0 and self.district_attribution > 0.0:
            eps = 1e-6
            n = max(len(rewards), 1)
            shares = np.asarray([max(ni, 0.0) for ni in nets], dtype=float) / max(district_net, eps)
            # 限制 shares 在 [0,1] 且 sum=1（异常时退回均匀）
            shares = np.clip(shares, 0.0, 1.0)
            s_sum = float(shares.sum())
            if s_sum < eps:
                shares = np.ones(n, dtype=float) / n
            else:
                shares = shares / s_sum
            # 线性插值：attribution 部分用份额，其余均摊
            uniform = np.ones(n, dtype=float) / n
            mix = (1.0 - self.district_attribution) * uniform + self.district_attribution * shares
            peak_pen_per_agent = peak_pen_total * mix
        elif peak_pen_total > 0.0:
            peak_pen_per_agent = np.full(len(rewards), peak_pen_total / max(len(rewards), 1),
                                         dtype=float)

        out = [float(rewards[i]) - float(peak_pen_per_agent[i]) + float(stagger[i])
               for i in range(len(rewards))]

        # ④ 峰前储能预留（默认关：weight=0 ⇒ 下面的代码**完全不进入**，
        #    out 与升级前逐位一致 —— 零侵入铁律）
        #    【方案 6】ns_gate=0 时 `_dm_reserve_exempt` 立即返回 False（且不计数）
        #    ⇒ 与"方案 5 原样"逐位一致。
        #    【方案 7】spike_weight=0 时"豁免分支"内**什么都不做**
        #    ⇒ 与"方案 6 原样"逐位一致（短路的调用时机也与旧 `and` 写法完全一致）。
        if self.district_soc_reserve_weight > 0.0:
            hour = self._dm_hour_now(observations)
            if self._dm_in_reserve_hours(hour):
                if self._dm_reserve_exempt(observations):
                    # ⑥ 尖峰(豁免)步的"电池流计价"：本栋此刻在充电 ⇒ 罚；在放电 ⇒ 奖
                    if self.district_soc_reserve_spike_weight > 0.0:
                        w_s = float(self.district_soc_reserve_spike_weight)
                        flow_sum = 0.0
                        for i in range(len(out)):
                            # 读不到 flow ⇒ 按 0 计 ⇒ 与"纯豁免"完全等价（不误伤）
                            flow = _read(
                                observations[i],
                                'electrical_storage_electricity_consumption', 0.0)
                            out[i] = float(out[i]) - w_s * flow
                            flow_sum += flow
                            if flow > 0.0:
                                self._dm_reserve_spike_chg_steps += 1
                            elif flow < 0.0:
                                self._dm_reserve_spike_dis_steps += 1
                        self._dm_reserve_spike_flow_sum += flow_sum
                        self._dm_reserve_spike_steps += 1
                else:
                    target = float(self.district_soc_reserve_target)
                    w = float(self.district_soc_reserve_weight)
                    soc_sum = 0.0
                    for i in range(len(out)):
                        # 读不到 SOC ⇒ 当"正好达标"（deficit=0）⇒ 不罚、不误伤
                        soc = _read(observations[i], 'electrical_storage_soc', target)
                        soc = float(min(max(soc, 0.0), 1.0))
                        deficit = max(0.0, target - soc)
                        out[i] = float(out[i]) - w * deficit
                        soc_sum += soc
                        self._dm_reserve_deficit_sum += deficit
                    self._dm_reserve_soc_sum += soc_sum / max(len(out), 1)
                    self._dm_reserve_steps += 1

        return out

    # ---- 统计输出 -----------------------------------------------------------
    def district_summary(self) -> str:
        """一行区域摘要（挂到评估收尾日志里，与 kpi_summary 并列使用）。"""
        steps = max(1, self._dm_steps)
        peak = 0.0 if self._dm_peak is None else float(self._dm_peak)
        return (
            f'[district-reward] 步数={self._dm_steps} '
            f'社区峰值={peak:.3f}(归一 {peak / self.district_net_scale:.3f}) '
            f'放电均值={self._dm_peak_sum / steps:.3f} '
            f'超目标线={self._dm_over_steps}步({self._dm_over_steps / steps:.1%}) '
            f'累计超线={self._dm_over_amount:.2f} '
            f'| 权重(尖峰={self.district_peak_weight:g} '
            f'团队={self.district_team_share:g} 错峰={self.district_stagger_weight:g} '
            f'分摊={self.district_attribution:g} 峰锚={self.district_peak_anchored:g} '
            f'预留={self.district_soc_reserve_weight:g})'
            + ('' if self.district_soc_reserve_weight <= 0.0 else
               f' | 预留窗=[{self.district_soc_reserve_hours[0]:g},'
               f'{self.district_soc_reserve_hours[1]:g}]h'
               f' 目标={self.district_soc_reserve_target:g}'
               f' 命中={self._dm_reserve_steps}步'
               f' 窗内SOC均值={self._dm_reserve_soc_sum / max(1, self._dm_reserve_steps):.3f}'
               f' 累计缺口={self._dm_reserve_deficit_sum:.2f}'
               + ('' if self.district_soc_reserve_ns_gate <= 0.0 else
                  f' | 尖峰豁免(gate={self.district_soc_reserve_ns_gate:g}kW)'
                  f' 豁免={self._dm_reserve_exempt_steps}步'
                  f' 豁免步ns最大={self._dm_reserve_exempt_ns_max:.2f}'
                  + ('' if self.district_soc_reserve_spike_weight <= 0.0 else
                     f' → 流计价(w={self.district_soc_reserve_spike_weight:g})'
                     f' {self._dm_reserve_spike_steps}步'
                     f' 净流={self._dm_reserve_spike_flow_sum:+.2f}kWh'
                     f'(充{self._dm_reserve_spike_chg_steps}/放'
                     f'{self._dm_reserve_spike_dis_steps})')))
        )

    def district_stats(self) -> dict:
        """结构化区域统计（供 CSV / JSON 落盘）。"""
        steps = max(1, self._dm_steps)
        return {
            'steps': self._dm_steps,
            'district_peak': 0.0 if self._dm_peak is None else float(self._dm_peak),
            'district_peak_norm': (0.0 if self._dm_peak is None
                                   else float(self._dm_peak) / self.district_net_scale),
            'district_net_mean': self._dm_peak_sum / steps,
            'over_target_steps': self._dm_over_steps,
            'over_target_ratio': self._dm_over_steps / steps,
            'over_target_amount': self._dm_over_amount,
            # 【方案 5】峰前储能预留的审计量（weight=0 时恒为 0）
            'reserve_weight': self.district_soc_reserve_weight,
            'reserve_hit_steps': self._dm_reserve_steps,
            'reserve_deficit_sum': self._dm_reserve_deficit_sum,
            'reserve_soc_mean': (self._dm_reserve_soc_sum / self._dm_reserve_steps
                                 if self._dm_reserve_steps else 0.0),
            # 【方案 6】尖峰豁免审计（gate=0 时恒为 0）
            'reserve_ns_gate': self.district_soc_reserve_ns_gate,
            'reserve_exempt_steps': self._dm_reserve_exempt_steps,
            'reserve_exempt_ns_sum': self._dm_reserve_exempt_ns_sum,
            'reserve_exempt_ns_max': self._dm_reserve_exempt_ns_max,
            # 【方案 7】尖峰步电池流计价审计（spike_weight=0 时恒为 0）
            'reserve_spike_weight': self.district_soc_reserve_spike_weight,
            'reserve_spike_steps': self._dm_reserve_spike_steps,
            'reserve_spike_flow_sum': self._dm_reserve_spike_flow_sum,
            'reserve_spike_chg_steps': self._dm_reserve_spike_chg_steps,
            'reserve_spike_dis_steps': self._dm_reserve_spike_dis_steps,
        }
