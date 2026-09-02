"""ResMARL 残差修正器：加载策略网络，对 CHESCA 基准动作施加 Δa。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from checa.residual.config import ResidualConfig, parse_residual_config
from checa.residual.state_builder import build_residual_state


@dataclass
class ResidualTrace:
    """单步残差层埋点，供 Decision Trace 扩展。"""

    applied: bool = False
    skip_reason: str = 'disabled'
    alpha: float = 0.0
    delta: List[float] = field(default_factory=list)  # α·mask·Δa（已缩放，用于合成）
    raw_delta: List[float] = field(default_factory=list)  # SAC/策略原始 Δa（未×α、未 mask）
    a_base: List[float] = field(default_factory=list)
    a_final: List[float] = field(default_factory=list)
    action_mask: Dict[str, bool] = field(default_factory=dict)
    policy_loaded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            'applied': self.applied,
            'skip_reason': self.skip_reason,
            'alpha': self.alpha,
            'delta': list(self.delta),
            'raw_delta': list(self.raw_delta),
            'a_base': list(self.a_base),
            'a_final': list(self.a_final),
            'action_mask': dict(self.action_mask),
            'policy_loaded': self.policy_loaded,
        }


@dataclass
class ResidualRolloutStep:
    """训练时单步缓存（ELE 残差）。"""

    state: np.ndarray
    action_ele: np.ndarray
    log_prob: Any
    value: Any


class ResidualCorrector:
    """
    a_final = clip(a_base + α · mask · Δa)

    - enabled=False 或 α=0 → 恒等
    - 有 policy.pt → 网络输出 ELE 残差
    - 无 policy → Δa=0（阶段 0/1 行为）
    """

    def __init__(self, n_buildings: int, config: Optional[ResidualConfig] = None):
        self.n_buildings = int(n_buildings)
        self.config = config or ResidualConfig()
        self.last_trace = ResidualTrace()
        self.policy = None
        self.deterministic = True
        self.last_rollout: Optional[ResidualRolloutStep] = None
        self._observation_names: Optional[List[str]] = None
        self._try_load_policy(self.config.policy_path)

    @classmethod
    def from_params(cls, n_buildings: int, params: Optional[Dict[str, Any]] = None) -> 'ResidualCorrector':
        return cls(n_buildings, parse_residual_config(params))

    def set_observation_names(self, names: Optional[List[str]]) -> None:
        self._observation_names = names

    def _try_load_policy(self, path: Optional[str]) -> None:
        if not path:
            self.policy = None
            return
        p = Path(path)
        if not p.is_file():
            self.policy = None
            return
        try:
            from checa.residual.policy import ResidualActorCritic
            self.policy = ResidualActorCritic.load(p)
            self.policy.eval()
        except Exception:
            self.policy = None

    def load_policy(self, path: str, device: str = 'cpu') -> bool:
        from checa.residual.policy import ResidualActorCritic
        p = Path(path)
        if not p.is_file():
            self.policy = None
            return False
        self.policy = ResidualActorCritic.load(p, device=device)
        self.policy.eval()
        self.config.policy_path = str(p)
        return True

    def attach_policy(self, policy) -> None:
        """训练时注入可学习策略。"""
        self.policy = policy

    def ele_delta_to_full(self, delta_ele: np.ndarray) -> np.ndarray:
        full = np.zeros(3 * self.n_buildings, dtype=float)
        for b in range(self.n_buildings):
            if b < len(delta_ele):
                full[3 * b + 1] = float(delta_ele[b])
        return full

    def predict_delta(
        self,
        a_base: Sequence[float],
        observations: Optional[Sequence[float]] = None,
        chesca_state: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        expected = 3 * self.n_buildings
        if self.policy is None:
            self.last_rollout = None
            return np.zeros(expected, dtype=float)

        state = build_residual_state(
            self.n_buildings,
            a_base,
            observations=observations,
            chesca_state=chesca_state,
            observation_names=self._observation_names,
        )
        delta_ele, log_prob, value = self.policy.act(state, deterministic=self.deterministic)
        self.last_rollout = ResidualRolloutStep(
            state=state,
            action_ele=np.asarray(delta_ele, dtype=np.float32),
            log_prob=log_prob,
            value=value,
        )
        return self.ele_delta_to_full(delta_ele)

    def _masked_delta(self, delta: np.ndarray) -> np.ndarray:
        out = np.array(delta, dtype=float, copy=True)
        mask = self.config.action_mask
        for b in range(self.n_buildings):
            if not mask.get('dhw', False):
                out[3 * b] = 0.0
            if not mask.get('ele', True):
                out[3 * b + 1] = 0.0
            if not mask.get('tmp', False):
                out[3 * b + 2] = 0.0
        expected = 3 * self.n_buildings
        if out.shape[0] > expected:
            out = out[:expected]
        elif out.shape[0] < expected:
            padded = np.zeros(expected, dtype=float)
            padded[: out.shape[0]] = out
            out = padded
        return out

    def correct(
        self,
        a_base: Sequence[float],
        observations: Optional[Sequence[float]] = None,
        chesca_state: Optional[Dict[str, Any]] = None,
        action_low: Optional[Sequence[float]] = None,
        action_high: Optional[Sequence[float]] = None,
    ) -> np.ndarray:
        base = np.asarray(a_base, dtype=float).reshape(-1).copy()
        alpha = float(self.config.alpha)
        policy_loaded = self.policy is not None

        if not self.config.enabled:
            self.last_rollout = None
            self.last_trace = ResidualTrace(
                applied=False,
                skip_reason='disabled',
                alpha=alpha,
                delta=[0.0] * len(base),
                raw_delta=[0.0] * len(base),
                a_base=base.tolist(),
                a_final=base.tolist(),
                action_mask=dict(self.config.action_mask),
                policy_loaded=policy_loaded,
            )
            return base

        # α=0：仍推理原始 Δa 供日志展示，但不施加修正
        if alpha <= 0.0:
            raw_delta = self.predict_delta(base, observations, chesca_state)
            self.last_rollout = None
            self.last_trace = ResidualTrace(
                applied=False,
                skip_reason='alpha_zero',
                alpha=alpha,
                delta=[0.0] * len(base),
                raw_delta=np.asarray(raw_delta, dtype=float).reshape(-1).tolist(),
                a_base=base.tolist(),
                a_final=base.tolist(),
                action_mask=dict(self.config.action_mask),
                policy_loaded=policy_loaded,
            )
            return base

        raw_delta = self.predict_delta(base, observations, chesca_state)
        masked = self._masked_delta(raw_delta)
        scaled = alpha * masked
        final = base + scaled

        if action_low is not None and action_high is not None:
            low = np.asarray(action_low, dtype=float).reshape(-1)
            high = np.asarray(action_high, dtype=float).reshape(-1)
            n = min(len(final), len(low), len(high))
            final[:n] = np.clip(final[:n], low[:n], high[:n])

        applied = bool(np.any(np.abs(scaled) > 1e-12))
        if not policy_loaded:
            skip = 'zero_delta_policy'
        elif applied:
            skip = 'none'
        else:
            skip = 'zero_delta_policy'

        self.last_trace = ResidualTrace(
            applied=applied,
            skip_reason=skip,
            alpha=alpha,
            delta=scaled.tolist(),
            raw_delta=np.asarray(raw_delta, dtype=float).reshape(-1).tolist(),
            a_base=base.tolist(),
            a_final=final.tolist(),
            action_mask=dict(self.config.action_mask),
            policy_loaded=policy_loaded,
        )
        return final
