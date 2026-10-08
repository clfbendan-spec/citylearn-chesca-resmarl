"""
Multi-agent 动作安全投影
========================

在策略网络输出之后、环境 step 之前，按当前楼栋状态硬约束动作：

1) 温控安全投影（cooling_device，通常 ∈[0,1]）
   - 过热（cooling_delta > comfort_band）：抬高制冷动作下限
   - 过冷（heating_delta < -comfort_band）：强制制冷动作 = 0

2) 停电硬投影（electrical_storage，通常 ∈[-1,1]，负=放电，正=充电）
   - 停电且 SOC ≥ 下限：强制放电（动作 ≤ -discharge_magnitude）

与 CityLearn 2023 动作顺序一致：
  active_actions ≈ ['dhw_storage', 'electrical_storage', 'cooling_device']
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from utils.report import getattr_path, series_value


@dataclass
class SafetyProjectionConfig:
    """投影超参；可按实验再调。"""

    # --- 温控 ---
    enable_cooling_projection: bool = True
    # 过热时 cooling_device 下限；并随超出 band 的温差线性抬升
    hot_cool_action_floor: float = 0.40
    hot_cool_action_per_c: float = 0.10  # 每超过 band 1°C 再加
    hot_cool_action_cap: float = 0.85
    # 过冷时强制关闭制冷
    cold_force_cool_off: bool = True

    # --- 停电电池 ---
    enable_outage_projection: bool = True
    soc_discharge_min: float = 0.35
    # 强制放电动作幅度（越负放得越多，需落在动作空间内）
    outage_discharge_action: float = -0.35
    # 期望负荷过低时不强制放电（避免空放）
    outage_min_expected_load: float = 0.1


@dataclass
class ActionProjectionInfo:
    """单楼投影诊断，便于 step_trace / 日志。"""

    cooling_forced_min: bool = False
    cooling_forced_off: bool = False
    battery_forced_discharge: bool = False
    is_hot: bool = False
    is_cold: bool = False
    outage: bool = False
    soc: float = float('nan')
    cool_delta: float = float('nan')
    heat_delta: float = float('nan')
    action_before: Optional[np.ndarray] = None
    action_after: Optional[np.ndarray] = None


def _action_index(action_names: Sequence[str], key: str) -> Optional[int]:
    key_l = key.lower()
    for i, name in enumerate(action_names):
        if str(name).lower() == key_l:
            return i
    # 模糊匹配
    for i, name in enumerate(action_names):
        n = str(name).lower()
        if key_l in n or n in key_l:
            return i
    return None


def building_comfort_outage_state(building: Any, time_step: int) -> Dict[str, float]:
    """读取投影所需的当前楼栋状态。"""
    indoor = series_value(getattr_path(building, 'indoor_dry_bulb_temperature'), time_step)
    cool_sp = series_value(
        getattr_path(building, 'indoor_dry_bulb_temperature_cooling_set_point'), time_step
    )
    heat_sp = series_value(
        getattr_path(building, 'indoor_dry_bulb_temperature_heating_set_point'), time_step
    )
    # comfort_band 在 CityLearn 中常为整段时序数组，不能用 `or` / float(array)
    band = series_value(getattr(building, 'comfort_band', None), time_step, default=2.0)
    if not np.isfinite(band) or band <= 0:
        band = 2.0
    cool_delta = indoor - cool_sp if np.isfinite(indoor) and np.isfinite(cool_sp) else float('nan')
    heat_delta = indoor - heat_sp if np.isfinite(indoor) and np.isfinite(heat_sp) else float('nan')
    occupied = series_value(getattr_path(building, 'energy_simulation', 'occupant_count'), time_step)
    if not np.isfinite(occupied):
        occupied = 1.0
    outage = series_value(getattr_path(building, 'power_outage'), time_step)
    soc = series_value(getattr_path(building, 'electrical_storage', 'soc'), time_step)

    cooling_demand = series_value(getattr_path(building, 'energy_simulation', 'cooling_demand'), time_step)
    heating_demand = series_value(getattr_path(building, 'energy_simulation', 'heating_demand'), time_step)
    dhw_demand = series_value(getattr_path(building, 'energy_simulation', 'dhw_demand'), time_step)
    nsl = series_value(getattr_path(building, 'energy_simulation', 'non_shiftable_load'), time_step)
    expected = 0.0
    for v in (cooling_demand, heating_demand, dhw_demand, nsl):
        if np.isfinite(v):
            expected += max(0.0, float(v))

    is_hot = bool(occupied > 0 and np.isfinite(cool_delta) and cool_delta > band)
    is_cold = bool(occupied > 0 and np.isfinite(heat_delta) and heat_delta < -band)
    return {
        'band': band,
        'cool_delta': float(cool_delta) if np.isfinite(cool_delta) else float('nan'),
        'heat_delta': float(heat_delta) if np.isfinite(heat_delta) else float('nan'),
        'is_hot': float(is_hot),
        'is_cold': float(is_cold),
        'outage': float(outage >= 0.5) if np.isfinite(outage) else 0.0,
        'soc': float(soc) if np.isfinite(soc) else float('nan'),
        'expected_load': float(expected),
        'occupied': float(occupied),
    }


def project_building_action(
    action: Sequence[float],
    action_names: Sequence[str],
    state: Mapping[str, float],
    config: Optional[SafetyProjectionConfig] = None,
    action_low: Optional[Sequence[float]] = None,
    action_high: Optional[Sequence[float]] = None,
) -> Tuple[np.ndarray, ActionProjectionInfo]:
    """对单栋动作向量做温控/停电投影。"""
    cfg = config or SafetyProjectionConfig()
    out = np.asarray(action, dtype=np.float64).reshape(-1).copy()
    info = ActionProjectionInfo(
        action_before=out.copy(),
        is_hot=bool(state.get('is_hot', 0.0)),
        is_cold=bool(state.get('is_cold', 0.0)),
        outage=bool(state.get('outage', 0.0)),
        soc=float(state.get('soc', float('nan'))),
        cool_delta=float(state.get('cool_delta', float('nan'))),
        heat_delta=float(state.get('heat_delta', float('nan'))),
    )

    cool_i = _action_index(action_names, 'cooling_device')
    bat_i = _action_index(action_names, 'electrical_storage')

    def _clip_idx(i: int, v: float) -> float:
        lo = float(action_low[i]) if action_low is not None and i < len(action_low) else None
        hi = float(action_high[i]) if action_high is not None and i < len(action_high) else None
        if cool_i is not None and i == cool_i:
            lo = 0.0 if lo is None else lo
            hi = 1.0 if hi is None else hi
        if bat_i is not None and i == bat_i:
            lo = -1.0 if lo is None else lo
            hi = 1.0 if hi is None else hi
        if lo is not None:
            v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
        return v

    # ----- 温控 -----
    if cfg.enable_cooling_projection and cool_i is not None and cool_i < out.size:
        if info.is_cold and cfg.cold_force_cool_off:
            out[cool_i] = _clip_idx(cool_i, 0.0)
            info.cooling_forced_off = True
        elif info.is_hot:
            band = float(state.get('band', 2.0))
            if not np.isfinite(band) or band <= 0:
                band = 2.0
            excess = max(0.0, float(state.get('cool_delta', 0.0)) - band)
            floor = min(
                cfg.hot_cool_action_cap,
                cfg.hot_cool_action_floor + cfg.hot_cool_action_per_c * excess,
            )
            if out[cool_i] < floor:
                out[cool_i] = _clip_idx(cool_i, floor)
                info.cooling_forced_min = True

    # ----- 停电电池 -----
    if (
        cfg.enable_outage_projection
        and bat_i is not None
        and bat_i < out.size
        and info.outage
        and np.isfinite(info.soc)
        and info.soc >= cfg.soc_discharge_min
        and float(state.get('expected_load', 0.0)) >= cfg.outage_min_expected_load
    ):
        target = float(cfg.outage_discharge_action)
        # 若策略已在更大力度放电，则保留更负的动作
        if out[bat_i] > target:
            out[bat_i] = _clip_idx(bat_i, target)
            info.battery_forced_discharge = True

    info.action_after = out.copy()
    return out.astype(np.float32, copy=False), info


def project_rllib_action_dict(
    citylearn_env: Any,
    action_dict: Mapping[str, np.ndarray],
    config: Optional[SafetyProjectionConfig] = None,
    agent_ids: Optional[Sequence[str]] = None,
) -> Tuple[Dict[str, np.ndarray], Dict[str, ActionProjectionInfo]]:
    """
    对 RLlib 多智能体动作字典做投影。

    agent_id 约定为 agent_0..agent_{n-1}，与 buildings 下标对齐。
    """
    cfg = config or SafetyProjectionConfig()
    buildings = list(getattr(citylearn_env, 'buildings', []) or [])
    time_step = int(getattr(citylearn_env, 'time_step', 0))
    keys = list(agent_ids) if agent_ids is not None else list(action_dict.keys())

    projected: Dict[str, np.ndarray] = {}
    infos: Dict[str, ActionProjectionInfo] = {}

    for i, building in enumerate(buildings):
        # 优先 agent_i，否则按 keys 顺序
        key = f'agent_{i}'
        if key not in action_dict:
            key = keys[i] if i < len(keys) else None
        if key is None or key not in action_dict:
            continue

        action_names = list(getattr(building, 'active_actions', None) or [])
        if not action_names:
            # 回退：2023 challenge 常见顺序
            action_names = ['dhw_storage', 'electrical_storage', 'cooling_device']

        low = high = None
        try:
            space = building.action_space
            low = np.asarray(space.low, dtype=float).reshape(-1)
            high = np.asarray(space.high, dtype=float).reshape(-1)
        except Exception:
            pass

        state = building_comfort_outage_state(building, time_step)
        new_act, info = project_building_action(
            action_dict[key],
            action_names,
            state,
            config=cfg,
            action_low=low,
            action_high=high,
        )
        projected[key] = new_act
        infos[key] = info

    # 原字典里未映射到的键原样保留
    for k, v in action_dict.items():
        if k not in projected:
            projected[k] = np.asarray(v, dtype=np.float32)

    # 按 agent_0..n 稳定排序，避免 .values() 顺序错配楼栋
    ordered_keys = sorted(
        projected.keys(),
        key=lambda x: int(str(x).split('_')[-1]) if '_' in str(x) and str(x).split('_')[-1].isdigit() else str(x),
    )
    projected = {k: projected[k] for k in ordered_keys}
    return projected, infos


try:
    from citylearn.wrappers import RLlibMultiAgentEnv as _CityLearnRLlibMAEnv
except (ModuleNotFoundError, ImportError):
    _CityLearnRLlibMAEnv = None


class SafetyProjectedRLlibMultiAgentEnv:  # noqa: B903 — 保留符号供旧导入兼容
    """
    已弃用：勿再作为 RLlib 的 env_class。

    外包/子类化都会导致 RLlib 把 Dict(agent→Box) 误当成单个策略动作空间，
    SAC 报 UnsupportedSpaceException。请改用：
      - 训练：原生 RLlibMultiAgentEnv
      - 评估：project_rllib_action_dict(...) 后再 env.step
    """

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            'SafetyProjectedRLlibMultiAgentEnv 已弃用。'
            '请使用 RLlibMultiAgentEnv + project_rllib_action_dict。'
        )
