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

        self._dm_peak: Optional[float] = None
        self._dm_peak_sum: float = 0.0
        self._dm_over_steps: int = 0
        self._dm_over_amount: float = 0.0
        self._dm_steps: int = 0
        self._dm_last_district_net: float = 0.0

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

    # ---- 是否真正启用区域项（供日志/自检） --------------------------------
    @property
    def district_active(self) -> bool:
        return (self.district_peak_weight > 0.0
                or self.district_team_share > 0.0
                or self.district_stagger_weight > 0.0
                or self.district_attribution > 0.0
                or self.district_peak_anchored > 0.0)

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
            f'分摊={self.district_attribution:g} 峰锚={self.district_peak_anchored:g})'
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
        }
