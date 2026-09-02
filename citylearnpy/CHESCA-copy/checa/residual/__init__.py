"""
CHESCA-ResMARL 残差层（阶段 2：Central PPO + checkpoint 推理）。

默认关闭：resmarl_enabled=False 或 residual_alpha=0 时，对动作零影响。
启用且配置 resmarl_policy_path 时，加载 ResidualActorCritic 对 ELE 施加残差。
"""

from checa.residual.config import (
    DEFAULT_RESIDUAL_ACTION_MASK,
    ResidualConfig,
    parse_residual_config,
)
from checa.residual.corrector import ResidualCorrector, ResidualTrace

__all__ = [
    'DEFAULT_RESIDUAL_ACTION_MASK',
    'ResidualConfig',
    'ResidualCorrector',
    'ResidualTrace',
    'parse_residual_config',
]
