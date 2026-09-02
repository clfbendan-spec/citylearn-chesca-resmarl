"""ResMARL Central Actor-Critic（输出每栋建筑的 ELE 残差）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Normal


def _mlp(in_dim: int, hidden: int, out_dim: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(in_dim, hidden),
        nn.Tanh(),
        nn.Linear(hidden, hidden),
        nn.Tanh(),
        nn.Linear(hidden, out_dim),
    )


class ResidualActorCritic(nn.Module):
    """
    输入：build_residual_state 向量
    Actor 输出无界均值，经 tanh 映射到 (-1,1) 作为 ELE 残差；
    再由 α·mask 缩放到动作空间。
    """

    def __init__(self, state_dim: int, n_buildings: int, hidden: int = 128, log_std_init: float = -0.5):
        super().__init__()
        self.n_buildings = int(n_buildings)
        self.state_dim = int(state_dim)
        self.actor = _mlp(self.state_dim, hidden, self.n_buildings)
        self.critic = _mlp(self.state_dim, hidden, 1)
        self.log_std = nn.Parameter(torch.full((self.n_buildings,), float(log_std_init)))

    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        mu = self.actor(state)
        value = self.critic(state).squeeze(-1)
        return mu, value

    def act(
        self,
        state: Union[np.ndarray, torch.Tensor],
        deterministic: bool = True,
    ) -> Tuple[np.ndarray, Optional[torch.Tensor], Optional[torch.Tensor]]:
        """返回 (delta_ele[n_buildings], log_prob, value)。"""
        if isinstance(state, np.ndarray):
            state_t = torch.as_tensor(state, dtype=torch.float32).unsqueeze(0)
        else:
            state_t = state if state.dim() == 2 else state.unsqueeze(0)

        mu, value = self.forward(state_t)
        std = self.log_std.exp().unsqueeze(0).expand_as(mu)
        dist = Normal(mu, std)

        if deterministic:
            raw = mu
            action = torch.tanh(raw)
            log_prob = None
        else:
            raw = dist.rsample()
            action = torch.tanh(raw)
            log_prob = dist.log_prob(raw) - torch.log(1 - action.pow(2) + 1e-6)
            log_prob = log_prob.sum(dim=-1)

        delta = action.squeeze(0).detach().cpu().numpy().astype(np.float32)
        val = value.squeeze(0).detach() if value is not None else None
        return delta, log_prob, val

    def evaluate_actions(
        self,
        states: torch.Tensor,
        actions: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """PPO：给定 states 与已采样的 tanh 动作，返回 log_prob / entropy / value。"""
        mu, value = self.forward(states)
        std = self.log_std.exp().unsqueeze(0).expand_as(mu)
        eps = 1e-6
        actions_clipped = actions.clamp(-1 + eps, 1 - eps)
        raw = 0.5 * (torch.log1p(actions_clipped) - torch.log1p(-actions_clipped))
        dist = Normal(mu, std)
        log_prob = dist.log_prob(raw) - torch.log(1 - actions_clipped.pow(2) + eps)
        log_prob = log_prob.sum(dim=-1)
        entropy = dist.entropy().sum(dim=-1)
        return log_prob, entropy, value

    def save(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'state_dict': self.state_dict(),
            'state_dim': self.state_dim,
            'n_buildings': self.n_buildings,
        }
        torch.save(payload, path)
        return path

    @classmethod
    def load(cls, path: Union[str, Path], device: str = 'cpu') -> 'ResidualActorCritic':
        path = Path(path)
        payload = torch.load(path, map_location=device, weights_only=False)
        model = cls(
            state_dim=int(payload['state_dim']),
            n_buildings=int(payload['n_buildings']),
        )
        model.load_state_dict(payload['state_dict'])
        model.to(device)
        model.eval()
        return model
