"""ResMARL 状态相关**可学习门控头**（learned gating head）。

============================================================================
一句话
============================================================================
把 CHESCA 本体里那一处「净负荷超阈值 ⇒ 制冷动作 × (1 − TMP_max_reduction_percent)」
的**固定百分比削减**，在残差侧换成**学出来的、状态相关的保留系数** g_b(s)：

    a_final[冷却_b] = g_b(s) · a_base[冷却_b]        g_b ∈ [g_min, g_max]

- g_b ≡ 1  ⇒ 逐位等于 a_base（**恒等点**，退化为纯 CHESCA ✓）
- g_b < 1  ⇒ 把这个尖峰该削的「档位」交给策略决定（削多少、什么时候削）
- g_b > 1  ⇒ 允许在安全时刻恢复制冷（默认 g_max=1.0 ⇒ 只削不增）

============================================================================
为什么是「乘性」，不是「加性」
============================================================================
现有残差是加性的：``a_final = a_base + α·span·(mask ⊙ Δa)``。
加性残差在同一状态下的可切削量被 α 硬钉住（α=0.3 最多削 0.3），且与当前
动作大小无关；而峰值时刻真正需要的是「**按比例**把这一档压下去」。
headroom 探针（`_probe_shift_headroom.py`）已实测：
  · 峰值步制冷 = 2.41 kWh（额定一半 4.57）⇒ 基线**已削、但力度不足**；
  · 把该步制冷置 0.5 档反而**更差** ⇒ 力度是标定问题，不是「有没有动作」问题。
所以缺的是一个**状态相关的档位函数** g_b(s)，而不是又一份加性增量。

============================================================================
两种表示（同一个接口）
============================================================================
1. ``ParametricCausalGate`` —— 可解释、可拟合、可直接部署。
   触发信号刻意沿用探针**已验证**的因果量：该楼当步不可调负荷相对其参考值的比值。

       r_b = non_shiftable_load_b(当步) / ns_ref_b
       g_b = max(g_min, 1 − k · clip((r_b − tau)/w, 0, 1))

   k=1, tau=3, w→0 就退化成探针里的规则「不可调负荷 > 3×均值 ⇒ 关制冷」。
   ⇒ 探针那个「8.9% / 2.2%」是这条曲线上的一个**人工取点**；拟合就是找更好的点。

2. ``CoolingGateHead`` —— 供 MARL 用的 MLP，但**不是从零学**，而是
   「参数化先验 + 零初始化增量」：

       g_b = clip( g_prior(feat_b; params) + Δg_theta(feat_b), g_min, g_max )

   末层零初始化 ⇒ 初始策略**逐点等于**上面的参数化门控（有锚点、可热启动），
   训练只负责学「先验错在哪」。这与论文的主公式（残差 = 基准 + 增量）同构。

============================================================================
零侵入承诺
============================================================================
- 本模块只 **新增**，不改任何现有文件的行为；
- 默认 ``gate_mode='binary'``（= 现有 P0 二值门控），``learned`` 才启用本模块；
- 不依赖 CHESCA 内部对象：特征全部来自 ``observations`` / ``observation_names``
  与 ``chesca_state``（现有 correct() 已经在传），缺字段时**逐维置 0 并使 g=1**
  （即安全退化为恒等），不抛错、不静默改变基线。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

try:  # torch 只被 CoolingGateHead 用到；缺失时其余功能照常
    import torch
    from torch import nn
except Exception:  # pragma: no cover
    torch = None  # type: ignore
    nn = None  # type: ignore


EPS = 1e-6

# 每栋特征名（顺序即向量顺序，改动会破坏已存 checkpoint ⇒ 追加而非插入）
GATE_FEATURE_NAMES: Tuple[str, ...] = (
    'ns_ratio',   # 0 当步不可调负荷 / 参考值   ← 探针已验证的因果触发量
    'net_ratio',  # 1 当步净负荷 / 历史均值     ← CHESCA 自身阈值同款信号
    'a_cool',     # 2 基准制冷档（0..1）
    'soc',        # 3 电池 SOC
    'dhw_soc',    # 4 DHW 储热 SOC
    'hour_sin',   # 5 时刻
    'hour_cos',   # 6
    'price',      # 7 电价（原值；无则 0）
    'outage',     # 8 停电 0/1
    'cool_cap',   # 9 制冷额定电功率 kWh（尺度提示）
)
GATE_FEATURE_DIM = len(GATE_FEATURE_NAMES)

# 动作轴选择（动作向量为 [DHW, ELE, TMP] × n）
_AXIS_OFFSETS: Dict[str, Tuple[int, ...]] = {
    'dhw': (0,),
    'ele': (1,),
    'tmp': (2,),
    'cool': (2,),
    'cooling': (2,),
    'tmp_dhw': (0, 2),
    'dhw_tmp': (0, 2),
}


# ============================================================================
# 1) 特征构造（观测拼接）
# ============================================================================
def _obs_lookup(observations, observation_names, *candidates) -> Optional[float]:
    """按候选名在观测里取值（逐个试，取到第一个有限值）。取不到返回 None。"""
    if observations is None or not observation_names:
        return None
    try:
        obs = np.asarray(observations, dtype=float).reshape(-1)
    except Exception:
        return None
    names = list(observation_names)
    for cand in candidates:
        if cand not in names:
            continue
        i = names.index(cand)
        if 0 <= i < obs.size and np.isfinite(obs[i]):
            return float(obs[i])
    return None


def _seq_get(seq, i, default=0.0) -> float:
    try:
        v = float(seq[i])
    except (TypeError, ValueError, IndexError, KeyError):
        return default
    return v if np.isfinite(v) else default


def _forecast_ns(chesca_state: Dict[str, Any], b: int) -> Optional[float]:
    """从 CHESCA 注入的 forecasts 里取该楼当步不可调负荷**预测**，作为参考基准。"""
    fc = (chesca_state or {}).get('forecasts')
    if not fc:
        return None
    try:
        arr = fc[b]['non_shiftable_load']
        return float(np.asarray(arr, dtype=float).reshape(-1)[0])
    except Exception:
        return None


def build_gate_features(
    n_buildings: int,
    a_base: Sequence[float],
    observations: Optional[Sequence[float]] = None,
    observation_names: Optional[Sequence[str]] = None,
    chesca_state: Optional[Dict[str, Any]] = None,
    cool_capacity: Optional[Sequence[float]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """构造逐栋门控特征 (B, GATE_FEATURE_DIM)。

    返回 ``(feats, has_trigger)``：
      · feats        —— float32 (B, F)，缺失维度填 0
      · has_trigger  —— bool (B,)，该栋当步**是否拿到了不可调负荷**（即因果触发量可用）。
                        为 False 的楼栋，调用方应让 g=1（不做任何削减）——避免"没有状态就乱削"。
    """
    n = max(0, int(n_buildings))
    base = np.asarray(a_base, dtype=float).reshape(-1)
    st = dict(chesca_state or {})
    feats = np.zeros((n, GATE_FEATURE_DIM), dtype=np.float32)
    has_trigger = np.zeros(n, dtype=bool)

    hour = st.get('hour')
    if hour is None:
        v = _obs_lookup(observations, observation_names, 'hour')
        hour = v if v is not None else 12.0
    hh = (float(hour) - 1.0) % 24.0 / 24.0
    h_sin, h_cos = float(np.sin(2 * np.pi * hh)), float(np.cos(2 * np.pi * hh))

    price = _obs_lookup(observations, observation_names,
                        'electricity_pricing', 'pricing', 'electricity_pricing_predicted_1')
    price = 0.0 if price is None else float(price)

    soc_seq = st.get('cur_battery_soc') or []
    dhw_seq = st.get('cur_dhw_soc') or []
    net_mean_seq = st.get('net_load_mean') or []
    outage_seq = st.get('outage') or []
    ns_mean_seq = st.get('non_shiftable_load_mean') or []
    ns_now_seq = st.get('non_shiftable_load') or []
    net_now_seq = st.get('net_load_now') or []

    for b in range(n):
        # --- 当步不可调负荷（优先观测，其次 chesca_state 显式注入）---
        ns_src = _obs_lookup(observations, observation_names,
                             f'non_shiftable_load_{b}', f'non_shiftable_load_{b + 1}',
                             'non_shiftable_load')
        if ns_src is None and b < len(ns_now_seq):
            ns_src = _seq_get(ns_now_seq, b, default=None)
        ns_now = 0.0 if ns_src is None else float(ns_src)
        has_trigger[b] = ns_src is not None   # 缺信号 ⇒ 调用方令 g=1（不乱削）

        # --- 参考基准：显式均值 > CHESCA 的当步预测 ---
        ns_ref = None
        if b < len(ns_mean_seq):
            ns_ref = _seq_get(ns_mean_seq, b, default=None)
        if ns_ref is None:
            ns_ref = _forecast_ns(st, b)
        # 参考值不可用/为 0 ⇒ 用当步自身做分母 ⇒ ratio=1（不触发，恒等）
        if ns_ref is None or not np.isfinite(ns_ref) or ns_ref <= EPS:
            ns_ref = max(ns_now, EPS)

        ns_ratio = float(ns_now) / (float(ns_ref) + EPS)

        # --- 净负荷比（CHESCA 自己的阈口径）---
        net_now = _obs_lookup(observations, observation_names,
                              f'net_electricity_consumption_{b}',
                              f'net_electricity_consumption_{b + 1}',
                              'net_electricity_consumption')
        if net_now is None and b < len(net_now_seq):
            net_now = _seq_get(net_now_seq, b, default=None)
        net_mean = _seq_get(net_mean_seq, b, default=0.0) if b < len(net_mean_seq) else 0.0
        if net_now is None or not np.isfinite(net_mean) or net_mean <= EPS:
            net_ratio = 1.0
        else:
            net_ratio = float(net_now) / (float(net_mean) + EPS)

        cool = _seq_get(base, 3 * b + 2, default=0.0)
        cap = _seq_get(cool_capacity, b, default=1.0) if cool_capacity is not None else 1.0
        cap = cap if np.isfinite(cap) and cap > EPS else 1.0

        feats[b] = (
            ns_ratio, net_ratio, cool,
            _seq_get(soc_seq, b, default=0.0),
            _seq_get(dhw_seq, b, default=0.0),
            h_sin, h_cos,
            price,
            float(bool(_seq_get(outage_seq, b, default=0.0) >= 0.5)),
            float(cap),
        )
    return feats, has_trigger


# ============================================================================
# 2) 可解释参数化门控（先验 / 可直接部署）
# ============================================================================
@dataclass
class ParametricCausalGate:
    """g = max(g_min, 1 − k · clip((ns_ratio − tau)/w, 0, 1))。

    · k    ∈ [0, 1]  最大削减深度（k=1 ⇒ 可削到 g_min）
    · tau  ≥ 0       触发门限（不可调负荷相对参考值的倍数）
    · w    >  0      过渡宽度（越小越接近硬开关；探针的规则 = w→0）
    · g_min∈ [0, 1]  削减下限（>0 表示"保底留多少档"）
    · ns_feature_idx 用哪一维做触发量（默认 0 = ns_ratio）
    """

    k: float = 1.0
    tau: float = 3.0
    w: float = 1.0
    g_min: float = 0.0
    g_max: float = 1.0
    ns_feature_idx: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'kind': 'parametric',
            'k': float(self.k), 'tau': float(self.tau), 'w': float(self.w),
            'g_min': float(self.g_min), 'g_max': float(self.g_max),
            'ns_feature_idx': int(self.ns_feature_idx),
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> 'ParametricCausalGate':
        d = dict(d or {})
        g = cls()
        for key in ('k', 'tau', 'w', 'g_min', 'g_max'):
            if key in d and d[key] is not None:
                setattr(g, key, float(d[key]))
        if d.get('ns_feature_idx') is not None:
            g.ns_feature_idx = int(d['ns_feature_idx'])
        return g

    def factors(self, feats: np.ndarray, has_trigger: Optional[np.ndarray] = None) -> np.ndarray:
        f = np.asarray(feats, dtype=float)
        if f.ndim == 1:
            f = f[None, :]
        idx = int(np.clip(self.ns_feature_idx, 0, f.shape[1] - 1))
        r = f[:, idx]
        ramp = np.clip((r - float(self.tau)) / (float(self.w) + EPS), 0.0, 1.0)
        g = 1.0 - float(self.k) * ramp
        g = np.clip(g, float(self.g_min), float(self.g_max))
        if has_trigger is not None:
            ht = np.asarray(has_trigger, dtype=bool).reshape(-1)
            if ht.size == g.size:
                # 没有可观测触发信号的楼栋 ⇒ 不动它（g=1）
                g = np.where(ht, g, 1.0)
        return g

    def save(self, path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
        return p


# ============================================================================
# 3) MLP 残差门控头（先验 + 零初始化增量）——供 MARL 训练用
# ============================================================================
def _mlp(in_dim: int, hidden: int, out_dim: int):
    return nn.Sequential(
        nn.Linear(in_dim, hidden), nn.Tanh(),
        nn.Linear(hidden, hidden), nn.Tanh(),
        nn.Linear(hidden, out_dim),
    )


if nn is not None:
    class CoolingGateHead(nn.Module):
        """g = clip(g_prior(feat) + Δg_θ(feat), g_min, g_max)，Δg_θ 末层零初始化。

        ⇒ 初始状态**逐点等于**参数化先验（锚点 / 热启动）；训练只学"先验错在哪"。
        """

        def __init__(
            self,
            n_buildings: int,
            prior: Optional[ParametricCausalGate] = None,
            hidden: int = 64,
            feature_dim: int = GATE_FEATURE_DIM,
        ):
            super().__init__()
            self.n_buildings = int(n_buildings)
            self.feature_dim = int(feature_dim)
            self.prior = prior or ParametricCausalGate(k=0.0)  # k=0 ⇒ 先验即恒等
            self.delta = _mlp(self.feature_dim, hidden, 1)
            # 末层零初始化 ⇒ Δg ≡ 0 ⇒ 初始 = 先验（恒等锚点）
            last = self.delta[-1]
            nn.init.zeros_(last.weight)
            nn.init.zeros_(last.bias)

        @property
        def g_min(self) -> float:
            return float(self.prior.g_min)

        @property
        def g_max(self) -> float:
            return float(self.prior.g_max)

        def forward(self, feats) -> Any:
            """feats: (B, F) torch/np ⇒ (B,) 门控系数（torch）。"""
            if torch is None:  # pragma: no cover
                raise RuntimeError('torch 不可用')
            if not isinstance(feats, torch.Tensor):
                feats = torch.as_tensor(np.asarray(feats, dtype=np.float32))
            if feats.dim() == 1:
                feats = feats.unsqueeze(0)
            with torch.no_grad():
                prior = torch.as_tensor(
                    self.prior.factors(feats.detach().cpu().numpy()), dtype=feats.dtype)
            delta = self.delta(feats).squeeze(-1)
            g = torch.clamp(prior + delta, self.g_min, self.g_max)
            return g

        def factors(self, feats, has_trigger=None) -> np.ndarray:
            """numpy 便捷入口（推理用，不建图）。"""
            f = np.asarray(feats, dtype=np.float32)
            if f.ndim == 1:
                f = f[None, :]
            with torch.no_grad():
                g = self.forward(f).detach().cpu().numpy().astype(float).reshape(-1)
            if has_trigger is not None:
                ht = np.asarray(has_trigger, dtype=bool).reshape(-1)
                if ht.size == g.size:
                    g = np.where(ht, g, 1.0)
            return g

        def save(self, path) -> Path:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            torch.save({
                'kind': 'mlp',
                'state_dict': self.state_dict(),
                'n_buildings': self.n_buildings,
                'feature_dim': self.feature_dim,
                'prior': self.prior.to_dict(),
                'feature_names': list(GATE_FEATURE_NAMES),
            }, p)
            return p

        @classmethod
        def load(cls, path, device: str = 'cpu') -> 'CoolingGateHead':
            payload = torch.load(Path(path), map_location=device, weights_only=False)
            head = cls(
                n_buildings=int(payload.get('n_buildings', 1)),
                prior=ParametricCausalGate.from_dict(payload.get('prior')),
                feature_dim=int(payload.get('feature_dim', GATE_FEATURE_DIM)),
            )
            head.load_state_dict(payload['state_dict'])
            head.to(device)
            head.eval()
            return head
else:  # pragma: no cover
    class CoolingGateHead:  # type: ignore
        def __init__(self, *a, **k):
            raise RuntimeError('torch 不可用，无法构造 CoolingGateHead')


def load_gate(path):
    """按 payload 里的 kind 自动分派（参数化 / MLP）。"""
    p = Path(path)
    if p.suffix.lower() == '.json':
        return ParametricCausalGate.from_dict(json.loads(p.read_text(encoding='utf-8')))
    if torch is None:  # pragma: no cover
        raise RuntimeError('torch 不可用，无法加载 MLP 门控')
    payload = torch.load(p, map_location='cpu', weights_only=False)
    if payload.get('kind') == 'parametric':
        return ParametricCausalGate.from_dict(payload)
    return CoolingGateHead.load(p)


# ============================================================================
# 4) 合成：把 g 乘到动作上
# ============================================================================
def gate_axis_indices(n_buildings: int, axis: str = 'tmp') -> np.ndarray:
    """返回被门控的维度下标（长度 = n_buildings × len(offsets)）。"""
    offsets = _AXIS_OFFSETS.get(str(axis).lower(), (2,))
    idx: List[int] = []
    for b in range(int(n_buildings)):
        for off in offsets:
            idx.append(3 * b + off)
    return np.asarray(idx, dtype=int)


def apply_gate(
    a_base: Sequence[float],
    g: Sequence[float],
    axis: str = 'tmp',
    action_low: Optional[Sequence[float]] = None,
    action_high: Optional[Sequence[float]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """``a_final = a_base``，但把 ``axis`` 指定的维度**乘**上逐栋系数 g。

    返回 ``(a_final, applied_mask)``；``applied_mask`` 标记哪些维真的被改了
    （便于埋点，也便于"g≡1 ⇒ 零改动"断言）。
    """
    out = np.asarray(a_base, dtype=float).reshape(-1).copy()
    gv = np.asarray(g, dtype=float).reshape(-1)
    n_b = out.size // 3
    idx = gate_axis_indices(n_b, axis)
    applied = np.zeros(out.size, dtype=bool)
    if idx.size == 0 or gv.size == 0:
        return out, applied
    if gv.size < n_b:
        pad = np.ones(n_b, dtype=float)
        pad[: gv.size] = gv
        gv = pad
    gv = gv[:n_b]
    for b, dim in enumerate(idx):
        if dim >= out.size or b >= gv.size:
            break
        before = out[dim]
        out[dim] = before * gv[b]
        applied[dim] = abs(out[dim] - before) > 1e-12
    if action_low is not None and action_high is not None:
        low = np.asarray(action_low, dtype=float).reshape(-1)
        high = np.asarray(action_high, dtype=float).reshape(-1)
        m = min(out.size, low.size, high.size)
        out[:m] = np.clip(out[:m], low[:m], high[:m])
    return out, applied


# ============================================================================
# 5) 一步到位的入口：按配置决定要不要施加、怎么施加
# ============================================================================
def maybe_apply_learned_gate(
    a_base: Sequence[float],
    cfg: Any,
    *,
    observations: Optional[Sequence[float]] = None,
    observation_names: Optional[Sequence[str]] = None,
    chesca_state: Optional[Dict[str, Any]] = None,
    action_low: Optional[Sequence[float]] = None,
    action_high: Optional[Sequence[float]] = None,
    gate: Any = None,
    cool_capacity: Optional[Sequence[float]] = None,
) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
    """若 ``cfg.gate_mode == 'learned'`` 则返回 ``(a_final, diag)``；否则 ``(None, diag)``。

    调用方（两条 correct() 链路）拿到 None 就走原路径 ⇒ **默认零影响**。
    """
    mode = str(getattr(cfg, 'gate_mode', 'binary') or 'binary').lower()
    if mode != 'learned':
        return None, {'gate_mode': mode}

    base = np.asarray(a_base, dtype=float).reshape(-1)
    n_b = base.size // 3
    axis = str(getattr(cfg, 'gate_axis', 'tmp') or 'tmp')
    strength = float(getattr(cfg, 'gate_strength', 1.0) or 0.0)

    feats, has_trigger = build_gate_features(
        n_b, base, observations=observations, observation_names=observation_names,
        chesca_state=chesca_state, cool_capacity=cool_capacity,
    )

    head = gate
    if head is None:
        params = getattr(cfg, 'gate_params', None)
        head = ParametricCausalGate.from_dict(params) if params else ParametricCausalGate(k=0.0)
    g_raw = np.asarray(head.factors(feats, has_trigger=has_trigger), dtype=float).reshape(-1)
    # strength=0 ⇒ g=1 ⇒ 恒等（与 α=0 同款的"可关闭旋钮"）
    g = 1.0 - strength * (1.0 - g_raw)

    final, applied = apply_gate(base, g, axis=axis,
                               action_low=action_low, action_high=action_high)
    diag = {
        'gate_mode': mode,
        'gate_axis': axis,
        'gate_strength': strength,
        'g': g.tolist(),
        'g_min': float(g.min()) if g.size else 1.0,
        'n_applied': int(applied.sum()),
        'delta_abs_max': float(np.max(np.abs(final - base))) if final.size else 0.0,
        'head': type(head).__name__,
    }
    return final, diag
