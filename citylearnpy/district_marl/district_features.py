# -*- coding: utf-8 -*-
"""区域级（District）观测特征层 —— MARL 协同的"信息前提"。

【问题：现有 MARL 为什么协同不起来】
  现有流水线里每个 agent 只看到"本楼"观测，看不到社区聚合状态。于是它：
    · 不知道社区此刻是否处于尖峰 ⇒ 不知道"该不该现在放电"；
    · 不知道别人是否已经在削峰 ⇒ 无法判断自己的**边际贡献**；
    · 不知道自己的 SOC 在楼群中偏高还是偏低 ⇒ 无法错峰（轮流充/放）。
  结果就是"独立学习"：形式上多智能体，学习机制上等价于把一个单智能体
  问题按楼拆开分别学。

【解法：把区域级指标从"评估口径"搬进"决策口径"】
  每个 agent 每步额外拿到 9 维区域特征，其中：
    · 5 维**全楼共享**（共同知识）：社区净用电、距本局峰值的距离、是否尖峰/谷底；
    · 4 维**本楼专属**（差异化信号）：本楼用量、占社区份额、用量排名、SOC 排名。
  共享维给出"我们一起处在什么状态"，专属维给出"我在这件事里该扮演什么角色"。
  两者缺一不可：只给共享维 ⇒ 三栋学出同一个策略（同质化，等于没协同）；
  只给专属维 ⇒ 不知道全局约束在哪。

【设计约束】
  1) 纯 numpy，**不 import ray / citylearn** ⇒ 可脱离仿真做单元测试；
  2) 所有特征裁剪到 [-1, 1] ⇒ 观测空间固定为 Box(-1, 1)，
     不随数据量级漂移而失效（也不触发 RLlib 的越界检查）；
  3) 特征**不含未来信息** ⇒ 只用"本步及之前"的量，不引入前视泄漏。

【特征清单】（顺序即观测向量顺序，勿随意调整 —— 改了就与旧 checkpoint 不兼容）
  0 dist_net_ratio       社区净用电 / net_scale（带符号）
  1 dist_net_over_peak   社区净用电 / 本局迄今峰值（≤1）
  2 dist_headroom        距本局峰值还剩多少（归一，≥0）
  3 dist_is_peak         社区是否处于尖峰（0/1）
  4 dist_is_valley       社区是否处于谷底（0/1）
  5 own_net_ratio        本楼净用电 / net_scale（带符号）
  6 own_net_share        本楼占社区净用电的份额（带符号）
  7 own_net_rank         本楼用电在楼群中的排名（0 = 最小，1 = 最大）
  8 own_soc_rank         本楼 SOC 在楼群中的排名（0 = 最低，1 = 最高）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# 特征名（顺序 = 观测向量顺序）
FEATURE_NAMES: Tuple[str, ...] = (
    'dist_net_ratio',
    'dist_net_over_peak',
    'dist_headroom',
    'dist_is_peak',
    'dist_is_valley',
    'own_net_ratio',
    'own_net_share',
    'own_net_rank',
    'own_soc_rank',
)

N_FEATURES = len(FEATURE_NAMES)


@dataclass
class DistrictFeatureConfig:
    """区域特征配置（与 district_marl.district_config 的默认值同源）。"""

    net_scale: float = 9.0
    peak_net: float = 6.0
    valley_net: float = 4.0
    clip: float = 1.0

    def normalized(self) -> 'DistrictFeatureConfig':
        """把不合法/缺失的配置夹到安全区间（构造时调用一次）。"""
        try:
            scale = float(self.net_scale)
        except (TypeError, ValueError):
            scale = 9.0
        try:
            peak = float(self.peak_net)
        except (TypeError, ValueError):
            peak = 6.0
        try:
            valley = float(self.valley_net)
        except (TypeError, ValueError):
            valley = 4.0
        try:
            clip = float(self.clip)
        except (TypeError, ValueError):
            clip = 1.0
        return DistrictFeatureConfig(
            net_scale=scale if scale > 1e-9 else 1.0,
            peak_net=peak,
            valley_net=valley,
            clip=clip if clip > 1e-9 else 1.0,
        )


def rank_norm(values: Sequence[float]) -> np.ndarray:
    """把一维量做**升序排名归一化**：最小 → 0.0，最大 → 1.0。

    · 单元素 / 全相等 ⇒ 全部返回 0.5（信息量为零，居中不偏袒）；
    · 用"平均名次"处理并列，保证对输入顺序不敏感（避免分楼顺序制造伪差异）。
    """
    arr = np.asarray(values, dtype=float).reshape(-1)
    n = arr.size
    if n <= 1:
        return np.full(n, 0.5, dtype=float)
    finite = np.isfinite(arr)
    if not finite.all():
        # 非有限值一律当"最低"处理，避免 NaN 传播
        arr = np.where(finite, arr, -np.inf)
    order = np.argsort(arr, kind='mergesort')
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(n, dtype=float)
    # 并列取平均名次
    sorted_vals = arr[order]
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        if j > i:
            avg = (i + j) / 2.0
            ranks[order[i:j + 1]] = avg
        i = j + 1
    span = float(n - 1)
    out = ranks / span if span > 1e-9 else np.full(n, 0.5, dtype=float)
    if np.allclose(arr, arr[0]):
        return np.full(n, 0.5, dtype=float)
    return np.clip(out, 0.0, 1.0)


class DistrictFeatureExtractor:
    """按步生成区域特征矩阵 (n_buildings, N_FEATURES)。

    持有**跨步状态** `running_peak`（本局迄今的社区净用电峰值），
    因此每局开始必须调用 `reset()`（district_env 在环境 reset 时自动调用）。
    """

    n_features = N_FEATURES

    def __init__(self, n_buildings: int, config: Optional[DistrictFeatureConfig] = None):
        self.n_buildings = max(0, int(n_buildings))
        self.cfg = (config or DistrictFeatureConfig()).normalized()
        self._running_peak: Optional[float] = None
        self._last_district_net: float = 0.0
        self._steps: int = 0

    # ---- 状态生命周期 -------------------------------------------------------
    def reset(self) -> None:
        """每局开始清零跨步状态（社区峰值必须重算，否则跨局污染）。"""
        self._running_peak = None
        self._last_district_net = 0.0
        self._steps = 0

    @property
    def running_peak(self) -> float:
        """本局迄今的社区净用电峰值（None 时按 0 处理）。"""
        return 0.0 if self._running_peak is None else float(self._running_peak)

    @property
    def steps(self) -> int:
        return int(self._steps)

    def last_step(self) -> Tuple[float, float, np.ndarray]:
        """上一步的区域聚合量：(社区净用电, 本局峰值, 各楼归属掩码)。"""
        return (
            float(self._last_district_net),
            self.running_peak,
            np.ones(self.n_buildings, dtype=float),
        )

    # ---- 核心：按步计算 -----------------------------------------------------
    def update(
        self,
        net_by_building: Sequence[float],
        soc_by_building: Optional[Sequence[float]] = None,
    ) -> np.ndarray:
        """用**当前步**各楼的净用电/电池 SOC 计算区域特征矩阵。

        参数
        ----
        net_by_building : 长度 n_buildings；每栋当前步净用电（买电>0 / 卖电<0）
        soc_by_building : 长度 n_buildings；每栋电池 SOC ∈ [0,1]（可选；
                          缺失时 SOC 排名维恒为 0.5 = "不知道"，不制造伪信号）

        返回
        ----
        np.ndarray, shape = (n_buildings, N_FEATURES)，dtype=float32，值域 [-1,1]
        """
        n = self.n_buildings
        if n <= 0:
            return np.zeros((0, N_FEATURES), dtype=np.float32)

        cfg = self.cfg
        net = self._as_vec(net_by_building, n, 0.0)
        soc = self._as_vec(soc_by_building, n, None if soc_by_building is None else 0.5)

        # ---- ① 社区层（全楼共享） ----
        district_net = float(np.sum(net))
        if self._running_peak is None:
            self._running_peak = district_net
        else:
            self._running_peak = max(float(self._running_peak), district_net)
        # 峰值下界取业务阈值：既避免 0 除，也让"距峰值"在开局就有一个合理的参考
        peak_ref = max(float(self._running_peak), float(cfg.peak_net), 1e-6)

        f0 = district_net / cfg.net_scale
        f1 = district_net / peak_ref
        f2 = max(0.0, peak_ref - district_net) / cfg.net_scale
        is_peak = 1.0 if district_net >= float(cfg.peak_net) else 0.0
        is_valley = 1.0 if district_net <= float(cfg.valley_net) else 0.0

        # ---- ② 本楼专属 ----
        abs_sum = float(np.sum(np.abs(net)))
        rank_net = rank_norm(net)
        if soc_by_building is None:
            rank_soc = np.full(n, 0.5, dtype=float)
        else:
            rank_soc = rank_norm(soc)

        out = np.zeros((n, N_FEATURES), dtype=np.float32)
        for i in range(n):
            own = float(net[i])
            share = own / abs_sum if abs_sum > 1e-9 else 0.0
            out[i, 0] = f0
            out[i, 1] = f1
            out[i, 2] = f2
            out[i, 3] = is_peak
            out[i, 4] = is_valley
            out[i, 5] = own / cfg.net_scale
            out[i, 6] = share
            out[i, 7] = rank_net[i]
            out[i, 8] = rank_soc[i]

        self._last_district_net = district_net
        self._steps += 1
        return np.clip(out, -cfg.clip, cfg.clip).astype(np.float32)

    # ---- 工具 --------------------------------------------------------------
    @staticmethod
    def _as_vec(values: Optional[Sequence[float]], n: int, default) -> np.ndarray:
        """把任意长度的输入整理成长度 n 的 float 向量（缺位补 default）。"""
        out = np.full(n, 0.0 if default is None else float(default), dtype=float)
        if values is None:
            return out
        try:
            arr = np.asarray(values, dtype=float).reshape(-1)
        except (TypeError, ValueError):
            return out
        m = min(n, arr.size)
        if m > 0:
            out[:m] = arr[:m]
        return out

    def describe(self) -> Dict[str, object]:
        """给日志/审计用的一行摘要。"""
        return {
            'n_buildings': self.n_buildings,
            'n_features': N_FEATURES,
            'features': list(FEATURE_NAMES),
            'net_scale': self.cfg.net_scale,
            'peak_net': self.cfg.peak_net,
            'valley_net': self.cfg.valley_net,
            'running_peak': self.running_peak,
        }
