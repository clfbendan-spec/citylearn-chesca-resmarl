"""ResMARL 残差层配置解析（阶段 0）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


DEFAULT_RESIDUAL_ACTION_MASK = {
    'dhw': False,
    'ele': True,
    'tmp': False,
}


@dataclass
class ResidualConfig:
    """残差层运行时配置。"""

    enabled: bool = False
    alpha: float = 0.0
    # Δa 的物理尺度：a_final = a_base + α · span · (mask ⊙ Δa)
    #   span=1.0 ⇒ 网络输出拉满 ±1 时，残差最大为 ±α（占动作空间的比例）
    #   调小则残差同比收缩；与 alpha（信任度）解耦，避免"改幅度只能改 α"。
    span: float = 1.0
    # 合成语义：
    #   'additive'（默认）= 残差叠加 a_base + α·span·(mask⊙Δa)，输出 0 ⇒ 精确等于基线，有天然恒等点；
    #   'blend'          = 旧行为 (1-α)·a_base + α·a_rl（把网络输出当"绝对动作"），仅供 A/B 对照。
    # 注意：两种写法在 Δa := a_rl − a_base 时恒等，真正的差别是"网络输出的语义"（见上面两行）。
    residual_mode: str = 'additive'
    action_mask: Dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_RESIDUAL_ACTION_MASK))
    policy_path: Optional[str] = None
    # 安全投影（action_safety_projection）的执行顺序：
    #   False（默认）= 先叠加残差，再对 a_final 做温控/停电硬投影 ⇒ 最终动作保证落在安全域内
    #                 （与论文"安全投影进一步将动作裁剪至物理边界"一致）；
    #   True          = 投影只作用于 a_base，之后叠加残差 ⇒ 最终动作仍可能被残差推出安全域。
    after_safety: bool = False
    # 安全投影开关；仅在残差真正生效（enabled 且 α>0）的路径上施加 ⇒ α=0 与纯 CHESCA 逐位一致。
    safety_projection_enabled: bool = True
    # SafetyProjectionConfig 的字段覆盖（dict）；None ⇒ 用其自带默认值。
    safety_projection_params: Optional[Dict[str, Any]] = None

    # ---- P0 门控（2026-10-09）：命中条件的楼栋本步 α=0（残差整体置零）----
    #   α_eff[b] = α · gate[b]；gate=0 ⇒ 该楼栋 a_final 逐位等于 a_base（与纯 CHESCA 一致 ✓）
    #   两条规则各自可关：停电停机（保护 CHESCA 的保供电分支）、SOC 触界停机
    #   （触界时电池动作已被物理/策略夹死，残差只会把它推出可行域）。
    gate_enabled: bool = True
    gate_on_outage: bool = True
    gate_on_soc_bound: bool = True
    # SOC 上下界的余量：进入 [lo, lo+margin] 或 [hi-margin, hi] 即视为触界
    gate_soc_margin: float = 0.02
    # 上界取自 CHESCA 自己的口径（与 agent.params 同名，不另存一份 ✗）
    gate_max_soc_normal: float = 0.99
    gate_max_soc_outage: float = 0.87

    # ---- 状态相关可学习门控（2026-10-10）：把"固定百分比削减"换成学出来的档位 g(s) ----
    #   'binary'（默认）= 现有 P0 二值门控（α_eff = α · gate，gate ∈ {0,1}）⇒ 行为与改动前逐位相同；
    #   'learned'       = 在二值门控之外，再对 gate_axis 指定的动作维施加**乘性**门控：
    #                       a_final[axis][b] = g_b(s) · a_base[axis][b]
    #                     g_b 由 checa/residual/gate_head 给出（参数化先验或 MLP）。
    #   gate_strength=0 ⇒ g≡1 ⇒ 与 'binary' 逐位相同（可关闭旋钮，便于 A/B 对照）。
    #   恒等保证：g≡1 或 gate_mode='binary' ⇒ a_final 与改动前完全一致 ✓
    gate_mode: str = 'binary'
    gate_axis: str = 'tmp'          # tmp | dhw | ele | tmp_dhw
    gate_strength: float = 1.0      # g_eff = 1 − strength·(1 − g_raw)
    gate_min: float = 0.0
    gate_max: float = 1.0
    # 参数化门控的系数（gate_head.ParametricCausalGate，如 {'k':1.0,'tau':3.0,'w':1.0}）
    gate_params: Optional[Dict[str, Any]] = None
    # 或 MLP 门控 checkpoint（.pt）；与 gate_params 二选一，gate_policy_path 优先
    gate_policy_path: Optional[str] = None

    @property
    def is_active(self) -> bool:
        """是否实际会修改动作（启用且 α>0）。"""
        return bool(self.enabled) and float(self.alpha) > 0.0


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ('1', 'true', 'yes', 'on'):
        return True
    if s in ('0', 'false', 'no', 'off', ''):
        return False
    return default


def _as_alpha(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    alpha = float(value)
    if alpha < 0.0 or alpha > 1.0:
        raise ValueError(f'residual_alpha 须在 [0, 1] 之间，当前: {alpha}')
    return alpha


def _as_span(value: Any, default: float = 1.0) -> float:
    if value is None:
        return default
    span = float(value)
    if not (span > 0.0):
        raise ValueError(f'residual_span 必须 > 0，当前: {span}')
    return span


def _as_mode(value: Any, default: str = 'additive') -> str:
    mode = str(value if value is not None else default).strip().lower()
    if mode not in ('additive', 'blend'):
        raise ValueError(f"residual_mode 只能是 'additive' 或 'blend'，当前: {mode}")
    return mode


def _as_margin(value: Any, default: float = 0.02) -> float:
    """SOC 触界余量：必须 ≥ 0（0 表示"严格触到边界才算"）。"""
    if value is None:
        return default
    margin = float(value)
    if margin < 0.0:
        raise ValueError(f'residual_gate_soc_margin 必须 ≥ 0，当前: {margin}')
    return margin


def _as_soc_bound(value: Any, default: float) -> float:
    """SOC 上界：须落在 [0, 1]（写错会静默改变门控触发时机 ⇒ 宁可报错 ✗）。"""
    if value is None:
        return default
    bound = float(value)
    if bound < 0.0 or bound > 1.0:
        raise ValueError(f'门控 SOC 上界须在 [0, 1] 之间，当前: {bound}')
    return bound


_GATE_MODES = ('binary', 'learned')
_GATE_AXES = ('tmp', 'cool', 'cooling', 'dhw', 'ele', 'tmp_dhw', 'dhw_tmp')


def _as_gate_mode(value: Any, default: str = 'binary') -> str:
    """可学习门控模式：'binary'（现有二值门控）| 'learned'（乘性状态门控）。"""
    mode = str(value if value is not None else default).strip().lower()
    if mode not in _GATE_MODES:
        raise ValueError(f"residual_gate_mode 只能是 {_GATE_MODES}，当前: {mode}")
    return mode


def _as_gate_axis(value: Any, default: str = 'tmp') -> str:
    """被乘性门控的动作轴：默认 'tmp'（制冷），写错直接报错，避免静默作用到别的维 ✗。"""
    axis = str(value if value is not None else default).strip().lower()
    if axis not in _GATE_AXES:
        raise ValueError(f"residual_gate_axis 只能是 {_GATE_AXES}，当前: {axis}")
    return axis


def _as_unit(value: Any, default: float) -> float:
    """[0, 1] 区间标量（门控上下限 / 强度用）。"""
    if value is None:
        return default
    v = float(value)
    if v < 0.0 or v > 1.0:
        raise ValueError(f'门控参数须在 [0, 1] 之间，当前: {v}')
    return v


# SafetyProjectionConfig 的字段若以「扁平键」写在 params 里（CLI 友好），就按类型纠正后并入
_SP_FLAT_BOOL_KEYS = (
    'enable_cooling_projection',
    'enable_outage_projection',
    'cold_force_cool_off',
)
_SP_FLAT_FLOAT_KEYS = (
    'hot_cool_action_floor',
    'hot_cool_action_per_c',
    'hot_cool_action_cap',
    'soc_discharge_min',
    'outage_discharge_action',
    'outage_min_expected_load',
    # P0-1（2026-10-10）：停电期制冷下限封顶（0.0 = 停电期不强制制冷，让位给 CHESCA 保供）
    'outage_cooling_floor',
)


def flat_safety_projection_overrides(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    把 SafetyProjectionConfig 的字段从扁平键收集出来并做类型纠正。

    为什么需要 ✗：命令行传进来的 'false'/'0' 都是**字符串**，
    直接塞进 SafetyProjectionConfig(**params) 会因为"非空字符串恒为真"而静默失效。
    """
    params = params or {}
    out: Dict[str, Any] = {}
    for key in _SP_FLAT_BOOL_KEYS:
        if params.get(key) is not None:
            out[key] = _as_bool(params[key], True)
    for key in _SP_FLAT_FLOAT_KEYS:
        if params.get(key) is not None:
            out[key] = float(params[key])
    return out


def _as_mask(value: Any) -> Dict[str, bool]:
    mask = dict(DEFAULT_RESIDUAL_ACTION_MASK)
    if not isinstance(value, dict):
        return mask
    for key in ('dhw', 'ele', 'tmp'):
        if key in value:
            mask[key] = _as_bool(value[key], mask[key])
    return mask


def parse_residual_config(params: Optional[Dict[str, Any]] = None) -> ResidualConfig:
    """
    从 Agent params / chesca_agent_config.json 解析残差配置。

    支持键名：
      resmarl_enabled / residual_enabled
      residual_alpha / resmarl_alpha
      residual_span
      residual_mode                     （'additive' | 'blend'）
      residual_action_mask
      resmarl_policy_path / residual_policy_path
      resmarl_after_safety
      safety_projection_enabled
      safety_projection_params
      residual_gate_enabled / residual_gate_outage / residual_gate_soc_bound
      residual_gate_soc_margin
      max_soc_normal / max_soc_outage    （与 CHESCA 同名 ⇒ 门控上界直接沿用其口径 ✓）
      residual_gate_mode                 （'binary'（默认）| 'learned'）
      residual_gate_axis                 （'tmp'（默认）| 'dhw' | 'ele' | 'tmp_dhw'）
      residual_gate_strength / residual_gate_min / residual_gate_max
      residual_gate_params               （参数化门控系数 {'k','tau','w','g_min','g_max'}）
      residual_gate_policy_path          （MLP 门控 checkpoint .pt；优先于 gate_params）
      enable_cooling_projection / enable_outage_projection / outage_discharge_action 等
                                          （SafetyProjectionConfig 的字段也可用扁平键给 ✓）
    """
    params = params or {}
    enabled = _as_bool(
        params.get('resmarl_enabled', params.get('residual_enabled', False)),
        False,
    )
    alpha = _as_alpha(
        params.get('residual_alpha', params.get('resmarl_alpha', 0.0)),
        0.0,
    )
    span = _as_span(params.get('residual_span', 1.0), 1.0)
    residual_mode = _as_mode(params.get('residual_mode'), 'additive')
    policy_path = params.get('resmarl_policy_path', params.get('residual_policy_path'))
    if policy_path is not None:
        policy_path = str(policy_path).strip() or None
    after_safety = _as_bool(params.get('resmarl_after_safety', False), False)
    action_mask = _as_mask(params.get('residual_action_mask'))
    safety_projection_enabled = _as_bool(params.get('safety_projection_enabled', True), True)
    safety_projection_params = params.get('safety_projection_params')
    if not isinstance(safety_projection_params, dict):
        safety_projection_params = None
    flat_proj = flat_safety_projection_overrides(params)
    if flat_proj:
        safety_projection_params = {**(safety_projection_params or {}), **flat_proj}

    gate_enabled = _as_bool(params.get('residual_gate_enabled', True), True)
    gate_on_outage = _as_bool(params.get('residual_gate_outage', True), True)
    gate_on_soc_bound = _as_bool(params.get('residual_gate_soc_bound', True), True)
    gate_soc_margin = _as_margin(params.get('residual_gate_soc_margin', 0.02), 0.02)
    base = ResidualConfig()
    gate_max_soc_normal = _as_soc_bound(
        params.get('max_soc_normal', base.gate_max_soc_normal), base.gate_max_soc_normal)
    gate_max_soc_outage = _as_soc_bound(
        params.get('max_soc_outage', base.gate_max_soc_outage), base.gate_max_soc_outage)

    # 可学习门控（新增；默认 binary ⇒ 与改动前行为一致）
    gate_mode = _as_gate_mode(params.get('residual_gate_mode', base.gate_mode), base.gate_mode)
    gate_axis = _as_gate_axis(params.get('residual_gate_axis', base.gate_axis), base.gate_axis)
    gate_strength = _as_unit(params.get('residual_gate_strength', base.gate_strength),
                             base.gate_strength)
    gate_min = _as_unit(params.get('residual_gate_min', base.gate_min), base.gate_min)
    gate_max = _as_unit(params.get('residual_gate_max', base.gate_max), base.gate_max)
    if gate_min > gate_max:
        raise ValueError(f'residual_gate_min({gate_min}) 不得大于 residual_gate_max({gate_max})')
    gate_params = params.get('residual_gate_params')
    if not isinstance(gate_params, dict):
        gate_params = None
    gate_policy_path = params.get('residual_gate_policy_path', params.get('gate_policy_path'))
    if gate_policy_path is not None:
        gate_policy_path = str(gate_policy_path).strip() or None

    return ResidualConfig(
        enabled=enabled,
        alpha=alpha,
        span=span,
        residual_mode=residual_mode,
        action_mask=action_mask,
        policy_path=policy_path,
        after_safety=after_safety,
        safety_projection_enabled=safety_projection_enabled,
        safety_projection_params=safety_projection_params,
        gate_enabled=gate_enabled,
        gate_on_outage=gate_on_outage,
        gate_on_soc_bound=gate_on_soc_bound,
        gate_soc_margin=gate_soc_margin,
        gate_max_soc_normal=gate_max_soc_normal,
        gate_max_soc_outage=gate_max_soc_outage,
        gate_mode=gate_mode,
        gate_axis=gate_axis,
        gate_strength=gate_strength,
        gate_min=gate_min,
        gate_max=gate_max,
        gate_params=gate_params,
        gate_policy_path=gate_policy_path,
    )


def _as_seq(value: Any) -> Sequence[Any]:
    if isinstance(value, (list, tuple, np.ndarray)):
        return value
    return ()


def _at_float(seq: Sequence[Any], i: int) -> Optional[float]:
    if i >= len(seq):
        return None
    try:
        v = float(seq[i])
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _at_bool(seq: Sequence[Any], i: int) -> bool:
    if i >= len(seq):
        return False
    return bool(seq[i])


def summarize_gate_reasons(reasons: Sequence[str]) -> str:
    """把逐楼栋原因压成一行（如 'outage×2,soc_high×1'），供 trace / 日志记录。"""
    items = [str(r) for r in reasons if str(r) not in ('none', 'gate_off')]
    if not items:
        return 'none'
    counts: Dict[str, int] = {}
    for r in items:
        counts[r] = counts.get(r, 0) + 1
    return ','.join(f'{k}×{v}' for k, v in sorted(counts.items()))


def evaluate_residual_gate(
    n_buildings: int,
    config: Optional[ResidualConfig] = None,
    chesca_state: Optional[Dict[str, Any]] = None,
) -> Tuple[np.ndarray, List[str]]:
    """
    P0 门控：给出「逐动作维度」的门控系数，α_eff = α · gate。

    gate=1 ⇒ 该维度本步正常叠加残差；gate=0 ⇒ 本步该楼栋 α=0（a_final 逐位等于 a_base）。

    两条规则（可由 ResidualConfig 各自关闭 ✓）：
      · 停电     ：该楼栋本步停电 ⇒ 残差整体置零
                   （停电时 ELE 动作由 CHESCA 停电分支决定，残差叠加会打乱保供电策略 ✗）
      · SOC 触界 ：SOC 进入上界余量带或下界余量带 ⇒ 置零
                   上界 = 停电 ? max_soc_outage(0.87) : max_soc_normal(0.99)（与 CHESCA 同口径 ✓）
                   下界 = 硬件 DoD 下限 min_battery_soc（= 1 - depth_of_discharge）
                   （触界时电池动作已被物理/策略夹死，残差只会把它推出可行域 ⇒ 电网/舒适双输）

    状态来源：`chesca_state`（Checa.apply_residual_correction 每步注入 ✓）
      · cur_battery_soc[b] / min_battery_soc[b] / outage[b]
    缺字段时**逐条显式跳过**（reasons 记 'no_state'）⇒ 不静默失效 ✗。
    """
    n = max(0, int(n_buildings))
    cfg = config or ResidualConfig()
    gate = np.ones(3 * n, dtype=float)
    if not bool(getattr(cfg, 'gate_enabled', True)):
        return gate, ['gate_off'] * n

    state = dict(chesca_state or {})
    soc_seq = _as_seq(state.get('cur_battery_soc'))
    lo_seq = _as_seq(state.get('min_battery_soc'))
    outage_seq = _as_seq(state.get('outage'))
    margin = float(getattr(cfg, 'gate_soc_margin', 0.02) or 0.0)
    hi_normal = float(getattr(cfg, 'gate_max_soc_normal', 0.99))
    hi_outage = float(getattr(cfg, 'gate_max_soc_outage', 0.87))

    reasons: List[str] = []
    for b in range(n):
        outage = _at_bool(outage_seq, b)
        reason = 'none'
        if outage and bool(getattr(cfg, 'gate_on_outage', True)):
            reason = 'outage'
        elif bool(getattr(cfg, 'gate_on_soc_bound', True)):
            soc = _at_float(soc_seq, b)
            if soc is None:
                reason = 'no_state'
            else:
                hi = hi_outage if outage else hi_normal
                lo = _at_float(lo_seq, b)
                if soc >= hi - margin:
                    reason = 'soc_high'
                elif lo is not None and soc <= lo + margin:
                    reason = 'soc_low'
        if reason not in ('none', 'no_state'):
            gate[3 * b:3 * b + 3] = 0.0
        reasons.append(reason)
    return gate, reasons
