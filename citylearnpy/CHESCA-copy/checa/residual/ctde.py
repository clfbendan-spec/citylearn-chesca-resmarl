"""
CHESCA-ResMARL · CTDE 落地版（Central Critic + Decentralized Actor）。

【设计动机】
原 ResidualActorCritic（policy.py）是 CTCE（集中 actor + 集中 critic），
输入 joint state 输出 joint action ⇒ 训练/部署都需要 joint state。

论文 v2 §五 要求：**actor 分散**（每栋楼只看 own_obs）+ **critic 集中**
（训时看 joint_state 算 V(s) 解非平稳性）。本模块是这一架构的独立落地。

【零侵入铁律】
`_ctde_enabled()` 读环境变量 `CITYLEARN_CTDE_ENABLED`（默认 False）⇒ OFF 时本
模块对外接口完全等价于 ResidualActorCritic（同样的 `load/save/act/forward` 形态），
不替换已有 import 也不创建任何副作用。ON 时由调用方显式 import 本模块。

【关键设计】
1. Actor 分散：每栋楼一个 own_state → tanh(Δele) 残差，clip 到 [-clip, +clip]；
   楼级 ID 嵌入 + 共享 backbone 让同结构学出异质策略。
2. Critic 集中：joint_state → V(s)，仅在训练时使用；部署时 critic 不存在。
3. Residual clip：默认 `residual_clip=0.1`（论文 v2 §六.2 承诺 [-0.1, +0.1]）。
4. 接口对齐：本模块暴露 `CentralCriticMAPPOActorCritic`，其 `act(per_building_obs, ...)`
   与原 `ResidualActorCritic.act(state, ...)` 同形态（返回 delta + value 备选）。

【架构示意】
   ┌──── CHESCA Rule (frozen) ────┐
   │ 输出: a_ch (基础动作)         │
   │                               │
   │   + ┌── CTDE Per-Building Actor ──┐
   │     │ 观测: own_obs 仅本栋        │
   │     │ ID 嵌入: building_id        │
   │     │ 输出: delta_ele 夹断 [-c,+c]│
   │     │ 累加: a_final = a_ch+delta  │
   │     └────────────────┬───────────┘
   └───────────────────────┼─────────────┘
                           ↓
                      env.step(a_final)
                           ↓
   ┌──────── Critic (joint_state → V) ────────┐ (仅训练时存在)
   │ 观测: joint_state (所有 9 栋 obs+残差)   │
   │ 输出: V(s) ⇒ PPO advantage baseline      │
   └──────────────────────────────────────────┘

【论文对应】
- CHESCA-论文定位与缺口claim.md §0 / §三 缺点 F / §五 完整架构
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple, Union, Sequence, List

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Normal


# ============================================================================
# 默认开关：环境变量 CITYLEARN_CTDE_ENABLED（默认关 ⇒ 零侵入）
# ============================================================================
def _ctde_enabled() -> bool:
    """读环境变量 CITYLEARN_CTDE_ENABLED，默认 False。"""
    v = os.environ.get('CITYLEARN_CTDE_ENABLED', '0').strip().lower()
    return v in ('1', 'true', 'yes', 'on')


# ============================================================================
# CTDE 配置（与原 ResidualConfig 解耦，避开 cherry-pick 风险）
# ============================================================================
class CTDEConfig:
    """CTDE 参数集（独立于 ResidualConfig，便于将来替换/对比）。

    默认与论文 v2 §六.2 措辞候选一致：
      - residual_clip = 0.1（"夹断到 [-0.1, +0.1]"）
      - actor_hidden = 128
      - critic_hidden = 256
      - log_std_init = -0.5（与原 policy.py 对齐）
    """

    def __init__(
        self,
        *,
        actor_hidden: int = 128,
        critic_hidden: int = 256,
        residual_clip: float = 0.1,
        log_std_init: float = -0.5,
        use_actor_log_std: bool = False,
    ):
        self.actor_hidden = int(actor_hidden)
        self.critic_hidden = int(critic_hidden)
        self.residual_clip = float(residual_clip)
        self.log_std_init = float(log_std_init)
        # use_actor_log_std=True 时启用 SAC 风格的 stochastic 输出，
        # 默认 False（与 ResidualActorCritic.act 的 deterministic=True 一致）。
        self.use_actor_log_std = bool(use_actor_log_std)


# ============================================================================
# 分散 actor：per-building MLP + 楼级 ID 嵌入
# ============================================================================
class PerBuildingActor(nn.Module):
    """每栋楼的 actor（共享 backbone + 楼级 head）。

    Input:  own_state  (..., own_dim)
            building_id (...,)  long
    Output: per_building_logit  (..., n_buildings)
            （调用方按 building_id 取出对应列）
    """

    def __init__(self, own_dim: int, n_buildings: int, hidden: int = 128,
                 log_std_init: float = -0.5, use_log_std: bool = False):
        super().__init__()
        self.n_buildings = int(n_buildings)
        self.own_dim = int(own_dim)
        self.use_log_std = bool(use_log_std)
        self.shared = nn.Sequential(
            nn.Linear(self.own_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
        )
        # n_buildings 个 head 列：building_id 选第 id 列（per-building 异质策略）
        self.head = nn.Linear(hidden, self.n_buildings)
        self.id_embed = nn.Embedding(self.n_buildings, hidden)
        if self.use_log_std:
            # SAC 风格：每个 (building, obs) 一个 log_std
            self.log_std_head = nn.Linear(hidden, self.n_buildings)
            # 注册 buffer 让 load_state_dict 兼容
            self.register_buffer('_init_log_std', torch.tensor(float(log_std_init)))

    def forward(self, own_state: torch.Tensor, building_id: torch.Tensor):
        """Returns: per_building_logit  (..., n_buildings)."""
        h = self.shared(own_state)  # (..., hidden)
        # ID 嵌入相加（与 backbone 的输出对齐）
        h = h + self.id_embed(building_id)  # (..., hidden)
        logits = self.head(h)  # (..., n_buildings)
        return logits


# ============================================================================
# 集中 critic：joint_state → V(s)
# ============================================================================
class CentralCritic(nn.Module):
    """输入 joint_state → 输出标量 V。"""

    def __init__(self, joint_dim: int, hidden: int = 256):
        super().__init__()
        self.joint_dim = int(joint_dim)
        self.net = nn.Sequential(
            nn.Linear(self.joint_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
            nn.Linear(hidden, 1),
        )

    def forward(self, joint_state: torch.Tensor) -> torch.Tensor:
        return self.net(joint_state).squeeze(-1)


# ============================================================================
# CTDE 包装：PerBuildingActor + CentralCritic
# ============================================================================
class CentralCriticMAPPOActorCritic(nn.Module):
    """CTDE 主类（actor 分散 + critic 集中）。

    训练：
        actor_out = actor(own_obs, b_id)        → 仅取出第 b_id 列 → Δele
        v         = critic(joint_state)         → PPO baseline

    部署（actor 路径）：
        delta_b = actor(own_obs_b, b_id)        → 加上 CHESCA a_base ⇒ a_final
    """

    def __init__(
        self,
        own_dim: int,
        joint_dim: int,
        n_buildings: int,
        cfg: Optional[CTDEConfig] = None,
    ):
        super().__init__()
        if joint_dim <= 0:
            raise ValueError(f'joint_dim must be positive, got {joint_dim}')
        self.cfg = cfg or CTDEConfig()
        self.own_dim = int(own_dim)
        self.joint_dim = int(joint_dim)
        self.n_buildings = int(n_buildings)
        self.actor = PerBuildingActor(
            self.own_dim, self.n_buildings,
            hidden=self.cfg.actor_hidden,
            log_std_init=self.cfg.log_std_init,
            use_log_std=self.cfg.use_actor_log_std,
        )
        self.critic = CentralCritic(self.joint_dim, hidden=self.cfg.critic_hidden)
        # 训练时 sanity：own_dim, joint_dim 都应 > 0
        assert self.own_dim > 0, f'own_dim must be > 0, got {self.own_dim}'

    # ---- actor 路径 --------------------------------------------------------
    def per_building_delta(
        self,
        own_state: Union[np.ndarray, torch.Tensor],
        building_id: Union[int, torch.Tensor],
        deterministic: bool = True,
    ) -> Tuple[np.ndarray, Optional[torch.Tensor], Optional[torch.Tensor]]:
        """单栋楼 actor 推理：返回 (delta_ele, log_prob=None, value=None)。

        与 ResidualActorCritic.act 同形态（delta=ndarray），便于替代。
        """
        # 1) 转为 tensor
        if isinstance(own_state, np.ndarray):
            x = torch.as_tensor(own_state, dtype=torch.float32)
            if x.dim() == 1:
                x = x.unsqueeze(0)
        else:
            x = own_state if own_state.dim() == 2 else own_state.unsqueeze(0)

        if isinstance(building_id, int):
            b = torch.full((x.shape[0],), int(building_id), dtype=torch.long)
        else:
            b = torch.as_tensor(building_id, dtype=torch.long)
            if b.dim() == 0:
                b = b.unsqueeze(0).expand(x.shape[0])
            elif b.shape[0] != x.shape[0]:
                b = b.expand(x.shape[0])

        # 2) actor 推理
        logits = self.actor(x, b)  # (B, n_buildings)
        idx = b.long().unsqueeze(-1)
        gathered = logits.gather(1, idx).squeeze(-1)  # (B,)

        # 3) 输出夹断
        raw = gathered.clamp(-10.0, 10.0)  # 防 tanh 溢出
        delta = torch.tanh(raw) * self.cfg.residual_clip
        delta_np = delta.detach().cpu().numpy().astype(np.float32).reshape(-1)

        # 与 ResidualActorCritic.act 形态对齐：deterministic=True 时 log_prob=None
        if deterministic:
            return delta_np, None, None

        # 非 deterministic 路径（暂不支持，未实现 SAC 输出路径）
        return delta_np, None, None

    # ---- critic 路径（仅训练）----------------------------------------------
    def value(self, joint_state: Union[np.ndarray, torch.Tensor]) -> torch.Tensor:
        """集中 critic：joint_state → V(s)。返回 tensor（B,）。"""
        if isinstance(joint_state, np.ndarray):
            x = torch.as_tensor(joint_state, dtype=torch.float32)
            if x.dim() == 1:
                x = x.unsqueeze(0)
        else:
            x = joint_state if joint_state.dim() == 2 else joint_state.unsqueeze(0)
        return self.critic(x)  # (B,)

    # ---- PPO 训练用：评估已采样动作 ------------------------------------------
    def evaluate_actions(
        self,
        own_obs: torch.Tensor,           # (B, own_dim)
        joint_obs: torch.Tensor,         # (B, joint_dim)
        building_ids: torch.Tensor,      # (B,) long
        actions: torch.Tensor,           # (B,) 已采样的 tanh 残差
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """PPO 更新时算 log_prob / entropy / value。

        log_prob/entropy：对 **raw** logits（非 tanh）做高斯 ⇒ 与 SAC 一致；
        近似策略 (mean, std) = (gathered_raw, fixed σ)。
        """
        logits = self.actor(own_obs, building_ids)  # (B, n_buildings)
        idx = building_ids.long().unsqueeze(-1)
        mu_raw = logits.gather(1, idx).squeeze(-1)  # (B,)
        std = torch.exp(torch.tensor(self.cfg.log_std_init, device=mu_raw.device))
        std = std.expand_as(mu_raw)
        dist = Normal(mu_raw, std)
        eps = 1e-6
        a_clip = actions.clamp(-self.cfg.residual_clip + eps,
                               self.cfg.residual_clip - eps)
        # 把 tanh 动作反推回 raw 高斯（PPO 常用做法）
        a_clip_n = a_clip / self.cfg.residual_clip
        a_clip_n = a_clip_n.clamp(-1 + eps, 1 - eps)
        raw = 0.5 * (torch.log1p(a_clip_n) - torch.log1p(-a_clip_n))
        log_prob = dist.log_prob(raw)
        entropy = dist.entropy()
        value = self.critic(joint_obs)
        return log_prob, entropy, value

    # ---- 持久化 ------------------------------------------------------------
    def save(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'state_dict': self.state_dict(),
            'own_dim': self.own_dim,
            'joint_dim': self.joint_dim,
            'n_buildings': self.n_buildings,
            'cfg': {
                'actor_hidden': self.cfg.actor_hidden,
                'critic_hidden': self.cfg.critic_hidden,
                'residual_clip': self.cfg.residual_clip,
                'log_std_init': self.cfg.log_std_init,
                'use_actor_log_std': self.cfg.use_actor_log_std,
            },
        }
        torch.save(payload, path)
        return path

    @classmethod
    def load(cls, path: Union[str, Path], device: str = 'cpu') -> 'CentralCriticMAPPOActorCritic':
        path = Path(path)
        payload = torch.load(path, map_location=device, weights_only=False)
        cfg = CTDEConfig(**dict(payload.get('cfg') or {}))
        m = cls(
            own_dim=int(payload['own_dim']),
            joint_dim=int(payload['joint_dim']),
            n_buildings=int(payload['n_buildings']),
            cfg=cfg,
        )
        m.load_state_dict(payload['state_dict'])
        m.to(device)
        m.eval()
        return m


# ============================================================================
# 与 ResidualCorrector 的零侵入衔接（仅当 _ctde_enabled() 时挂入）
# ============================================================================
def try_replace_corrector_actor(corrector: Any) -> bool:
    """若 CTDE 启用 + 配置文件载入了 ctde checkpoint，则替换 corrector 的 actor。

    默认 OFF：函数体内直接 return False ⇒ corrector 原 actor 不变 ⇒ 行为零差异。
    """
    if not _ctde_enabled():
        return False

    cfg = getattr(corrector, '_cfg', None) or getattr(corrector, 'cfg', None)
    if cfg is None:
        return False

    # 找 ctde checkpoint 路径（与原 resmarl_policy_path 同款约定）
    ctde_path = getattr(cfg, 'ctde_policy_path', None) or \
                getattr(cfg, 'resmarl_ctde_policy_path', None)
    if not ctde_path:
        return False
    p = Path(str(ctde_path))
    if not p.is_file():
        return False

    try:
        m = CentralCriticMAPPOActorCritic.load(p)
    except Exception:
        return False

    # 用 CTDE 模块替换 corrector 的 actor（如有 `.policy` / `.actor` 字段）
    replaced = False
    for attr in ('policy', 'actor', '_policy', '_actor'):
        if hasattr(corrector, attr):
            try:
                setattr(corrector, attr, m)
                replaced = True
                break
            except Exception:
                pass
    if not replaced:
        # corrector 没有 actor 字段就不替换（保持 backward compat）
        return False
    return True
