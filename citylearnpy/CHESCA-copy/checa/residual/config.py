"""ResMARL 残差层配置解析（阶段 0）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


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
    action_mask: Dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_RESIDUAL_ACTION_MASK))
    policy_path: Optional[str] = None
    after_safety: bool = True  # 模式 A：安全审查之后再施加残差

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
      residual_action_mask
      resmarl_policy_path / residual_policy_path
      resmarl_after_safety
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
    policy_path = params.get('resmarl_policy_path', params.get('residual_policy_path'))
    if policy_path is not None:
        policy_path = str(policy_path).strip() or None
    after_safety = _as_bool(params.get('resmarl_after_safety', True), True)
    action_mask = _as_mask(params.get('residual_action_mask'))

    return ResidualConfig(
        enabled=enabled,
        alpha=alpha,
        action_mask=action_mask,
        policy_path=policy_path,
        after_safety=after_safety,
    )
