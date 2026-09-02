"""ResMARL 残差策略输入状态构造。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np


def residual_state_dim(n_buildings: int) -> int:
    """hour(2) + pricing(1) + per-building(soc,dhw_soc,a_dhw,a_ele,a_tmp,net_mean)=6*n"""
    return 3 + 6 * int(n_buildings)


def build_residual_state(
    n_buildings: int,
    a_base: Sequence[float],
    observations: Optional[Sequence[float]] = None,
    chesca_state: Optional[Dict[str, Any]] = None,
    observation_names: Optional[List[str]] = None,
) -> np.ndarray:
    """
    构造 Central ResMARL 状态向量（float32）。

    特征：
      [sin(h), cos(h), pricing] +
      每栋 [battery_soc, dhw_soc, a_dhw, a_ele, a_tmp, net_load_mean]
    """
    n_buildings = int(n_buildings)
    chesca_state = chesca_state or {}
    a_base = np.asarray(a_base, dtype=np.float32).reshape(-1)

    hour = chesca_state.get('hour')
    if hour is None and observations is not None and observation_names:
        try:
            hour = float(observations[observation_names.index('hour')])
        except (ValueError, IndexError, TypeError):
            hour = 12.0
    hour = float(hour if hour is not None else 12.0)
    # CityLearn hour 常为 1..24
    h = ((hour - 1.0) % 24.0) / 24.0
    feats: List[float] = [
        float(np.sin(2 * np.pi * h)),
        float(np.cos(2 * np.pi * h)),
    ]

    pricing = 0.0
    if observations is not None and observation_names and 'electricity_pricing' in observation_names:
        try:
            pricing = float(observations[observation_names.index('electricity_pricing')])
        except (ValueError, IndexError, TypeError):
            pricing = 0.0
    feats.append(pricing)

    bat = list(chesca_state.get('cur_battery_soc') or [0.0] * n_buildings)
    dhw = list(chesca_state.get('cur_dhw_soc') or [0.0] * n_buildings)
    net_mean = list(chesca_state.get('net_load_mean') or [0.0] * n_buildings)

    for b in range(n_buildings):
        feats.append(float(bat[b]) if b < len(bat) else 0.0)
        feats.append(float(dhw[b]) if b < len(dhw) else 0.0)
        idx = 3 * b
        feats.append(float(a_base[idx]) if idx < len(a_base) else 0.0)
        feats.append(float(a_base[idx + 1]) if idx + 1 < len(a_base) else 0.0)
        feats.append(float(a_base[idx + 2]) if idx + 2 < len(a_base) else 0.0)
        feats.append(float(net_mean[b]) if b < len(net_mean) else 0.0)

    out = np.asarray(feats, dtype=np.float32)
    expected = residual_state_dim(n_buildings)
    if out.shape[0] < expected:
        padded = np.zeros(expected, dtype=np.float32)
        padded[: out.shape[0]] = out
        return padded
    return out[:expected]
