"""
CHESCA-ResMARL 阶段 2：Central PPO 训练 ELE 残差策略。

每步由 CHESCA 产出 a_base（含树搜索 Refine），再由 ResidualActorCritic 学习
Δa_ELE；最终 a_final = clip(a_base + α · mask · Δa)。

用法（在 citylearnpy/ 下，conda env cl2）：

  # 冒烟（约数分钟）
  python train_chesca_resmarl.py --smoke

  # 短训并导出权重
  python train_chesca_resmarl.py --updates 20 --rollout-steps 48 --alpha 0.15 \\
      --output checkpoints/resmarl_policy.pt
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import torch
import torch.nn as nn

# Windows 控制台 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
warnings.filterwarnings('ignore', category=UserWarning, module='gymnasium')

ROOT = Path(__file__).resolve().parent
CHESCA = ROOT / 'CHESCA-copy'
sys.path.insert(0, str(CHESCA))
sys.path.insert(0, str(ROOT))

from citylearn.citylearn import CityLearnEnv  # noqa: E402

from agents.user_agent import SubmissionAgent  # noqa: E402
from checa.residual.policy import ResidualActorCritic  # noqa: E402
from checa.residual.state_builder import residual_state_dim  # noqa: E402
from local_evaluation_copy import WrapperEnv, DEFAULT_SCHEMA  # noqa: E402
from rewards.user_reward import SubmissionReward  # noqa: E402


@dataclass
class TrainConfig:
    schema: str = DEFAULT_SCHEMA
    alpha: float = 0.15
    updates: int = 5
    rollout_steps: int = 24
    episode_time_steps: int = 72
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    lr: float = 3e-4
    epochs: int = 4
    batch_size: int = 64
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    seed: int = 0
    output: Path = ROOT / 'checkpoints' / 'resmarl_policy.pt'
    device: str = 'cpu'


def _flatten_obs(observations) -> np.ndarray:
    if isinstance(observations, (list, tuple)) and len(observations) == 1:
        return np.asarray(observations[0], dtype=np.float32)
    return np.asarray(observations, dtype=np.float32)


def _scalar_reward(reward) -> float:
    """CityLearn central_agent 常返回 list/ndarray；取均值作标量。"""
    if reward is None:
        return 0.0
    arr = np.asarray(reward, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr))


def build_env(cfg: TrainConfig) -> tuple:
    env = CityLearnEnv(
        cfg.schema,
        reward_function=SubmissionReward,
        central_agent=True,
        episode_time_steps=cfg.episode_time_steps,
    )
    wrapper = WrapperEnv(env)
    return env, wrapper


def build_agent(wrapper: WrapperEnv, cfg: TrainConfig, policy: ResidualActorCritic) -> SubmissionAgent:
    params = {
        'tau': 1,
        'balance_type': 'C',
        'resmarl_enabled': True,
        'residual_alpha': cfg.alpha,
        'residual_action_mask': {'dhw': False, 'ele': True, 'tmp': False},
        'resmarl_after_safety': True,
        'resmarl_policy_path': None,
    }
    agent = SubmissionAgent(wrapper, params=params)
    agent.residual_corrector.attach_policy(policy)
    agent.residual_corrector.deterministic = False
    agent.residual_corrector.config.enabled = True
    agent.residual_corrector.config.alpha = float(cfg.alpha)
    return agent


def compute_gae(
    rewards: List[float],
    values: List[float],
    dones: List[bool],
    last_value: float,
    gamma: float,
    gae_lambda: float,
) -> tuple:
    advantages = []
    gae = 0.0
    next_value = last_value
    for t in reversed(range(len(rewards))):
        mask = 0.0 if dones[t] else 1.0
        delta = rewards[t] + gamma * next_value * mask - values[t]
        gae = delta + gamma * gae_lambda * mask * gae
        advantages.insert(0, gae)
        next_value = values[t]
    advantages_t = torch.as_tensor(advantages, dtype=torch.float32)
    values_t = torch.as_tensor(values, dtype=torch.float32)
    returns = advantages_t + values_t
    return advantages_t, returns


def ppo_update(
    policy: ResidualActorCritic,
    optimizer: torch.optim.Optimizer,
    states: torch.Tensor,
    actions: torch.Tensor,
    old_log_probs: torch.Tensor,
    advantages: torch.Tensor,
    returns: torch.Tensor,
    cfg: TrainConfig,
) -> dict:
    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
    n = states.shape[0]
    idx = np.arange(n)
    stats = {'policy_loss': 0.0, 'value_loss': 0.0, 'entropy': 0.0, 'n': 0}

    policy.train()
    for _ in range(cfg.epochs):
        np.random.shuffle(idx)
        for start in range(0, n, cfg.batch_size):
            batch = idx[start : start + cfg.batch_size]
            s = states[batch]
            a = actions[batch]
            old_lp = old_log_probs[batch]
            adv = advantages[batch]
            ret = returns[batch]

            log_prob, entropy, value = policy.evaluate_actions(s, a)
            ratio = torch.exp(log_prob - old_lp)
            surr1 = ratio * adv
            surr2 = torch.clamp(ratio, 1.0 - cfg.clip_eps, 1.0 + cfg.clip_eps) * adv
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = nn.functional.mse_loss(value, ret)
            entropy_loss = -entropy.mean()
            loss = policy_loss + cfg.vf_coef * value_loss + cfg.ent_coef * entropy_loss

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), cfg.max_grad_norm)
            optimizer.step()

            stats['policy_loss'] += float(policy_loss.item())
            stats['value_loss'] += float(value_loss.item())
            stats['entropy'] += float(entropy.mean().item())
            stats['n'] += 1

    policy.eval()
    if stats['n']:
        for k in ('policy_loss', 'value_loss', 'entropy'):
            stats[k] /= stats['n']
    return stats


def collect_rollout(env, agent: SubmissionAgent, policy: ResidualActorCritic, cfg: TrainConfig):
    """reset → predict → step，对齐 CHESCA 评估循环。"""
    from checa.residual.state_builder import build_residual_state

    states, actions, log_probs, values, rewards, dones = [], [], [], [], [], []

    observations, _ = env.reset()
    agent.reset()
    steps = 0
    ep_reward = 0.0

    while steps < cfg.rollout_steps:
        agent.residual_corrector.deterministic = False
        actions_env = agent.predict(observations)
        rollout = agent.residual_corrector.last_rollout
        if rollout is None:
            raise RuntimeError(
                '残差层未采样到动作。请确认 resmarl_enabled=True 且 residual_alpha>0，并已 attach_policy。'
            )
        states.append(np.asarray(rollout.state, dtype=np.float32))
        actions.append(np.asarray(rollout.action_ele, dtype=np.float32))
        log_probs.append(float(rollout.log_prob.detach().cpu().item()))
        values.append(float(rollout.value.detach().cpu().item()))

        step_out = env.step(actions_env)
        if len(step_out) == 5:
            observations, reward, terminated, truncated, _info = step_out
        else:
            observations, reward, done, _info = step_out
            terminated, truncated = bool(done), False

        r = _scalar_reward(reward)
        done = bool(terminated or truncated)
        rewards.append(r)
        dones.append(done)
        ep_reward += r
        steps += 1

        if done:
            observations, _ = env.reset()
            agent.reset()

    last_value = 0.0
    if not dones[-1]:
        with torch.no_grad():
            # 用当前 Agent 状态构造 bootstrap，不调用 predict（避免再 step）
            a_dummy = [0.0] * (3 * agent.n_buildings)
            st = build_residual_state(
                agent.n_buildings,
                a_dummy,
                observations=_flatten_obs(observations),
                chesca_state={
                    'hour': None,
                    'cur_battery_soc': list(agent.cur_battery_soc),
                    'cur_dhw_soc': list(agent.cur_dhw_soc),
                    'net_load_mean': [
                        float(np.mean(agent.elec_consumption_history[b])) if agent.elec_consumption_history[b] else 0.0
                        for b in range(agent.n_buildings)
                    ],
                },
                observation_names=agent.observation_names_b,
            )
            _, _, val = policy.act(st, deterministic=True)
            last_value = float(val.detach().cpu().item()) if val is not None else 0.0

    return states, actions, log_probs, values, rewards, dones, last_value, ep_reward


def train(cfg: TrainConfig) -> Path:
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    print(f'[ResMARL] schema={cfg.schema} alpha={cfg.alpha} updates={cfg.updates} '
          f'rollout={cfg.rollout_steps} episode_len={cfg.episode_time_steps}', flush=True)

    env, wrapper = build_env(cfg)
    n_buildings = len(wrapper.buildings_metadata)
    state_dim = residual_state_dim(n_buildings)
    policy = ResidualActorCritic(state_dim, n_buildings).to(cfg.device)
    optimizer = torch.optim.Adam(policy.parameters(), lr=cfg.lr)
    agent = build_agent(wrapper, cfg, policy)

    t0 = time.perf_counter()
    for upd in range(1, cfg.updates + 1):
        states, actions, log_probs, values, rewards, dones, last_value, ep_r = collect_rollout(
            env, agent, policy, cfg
        )
        advantages, returns = compute_gae(
            rewards, values, dones, last_value, cfg.gamma, cfg.gae_lambda
        )
        stats = ppo_update(
            policy,
            optimizer,
            torch.as_tensor(np.stack(states), dtype=torch.float32),
            torch.as_tensor(np.stack(actions), dtype=torch.float32),
            torch.as_tensor(np.asarray(log_probs), dtype=torch.float32),
            advantages,
            returns,
            cfg,
        )
        mean_r = float(np.mean(rewards)) if rewards else 0.0
        print(
            f'[update {upd}/{cfg.updates}] mean_r={mean_r:.4f} ep_r={ep_r:.4f} '
            f'pi={stats["policy_loss"]:.4f} v={stats["value_loss"]:.4f} H={stats["entropy"]:.4f}',
            flush=True,
        )

    out = Path(cfg.output)
    policy.eval()
    policy.save(out)
    elapsed = time.perf_counter() - t0
    print(f'[ResMARL] saved {out.resolve()} ({elapsed:.1f}s)', flush=True)
    env.close()
    return out


def parse_args(argv: Optional[List[str]] = None) -> TrainConfig:
    p = argparse.ArgumentParser(description='Train CHESCA-ResMARL ELE residual with Central PPO')
    p.add_argument('--schema', default=DEFAULT_SCHEMA)
    p.add_argument('--alpha', type=float, default=0.15)
    p.add_argument('--updates', type=int, default=5)
    p.add_argument('--rollout-steps', type=int, default=24)
    p.add_argument('--episode-time-steps', type=int, default=72)
    p.add_argument('--lr', type=float, default=3e-4)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--output', type=str, default=str(ROOT / 'checkpoints' / 'resmarl_policy.pt'))
    p.add_argument('--smoke', action='store_true', help='极短冒烟：2 updates × 8 steps')
    args = p.parse_args(argv)

    cfg = TrainConfig(
        schema=args.schema,
        alpha=args.alpha,
        updates=args.updates,
        rollout_steps=args.rollout_steps,
        episode_time_steps=args.episode_time_steps,
        lr=args.lr,
        seed=args.seed,
        output=Path(args.output),
    )
    if args.smoke:
        cfg.updates = 2
        cfg.rollout_steps = 8
        cfg.episode_time_steps = 24
        cfg.epochs = 2
        cfg.batch_size = 8
        cfg.output = ROOT / 'checkpoints' / 'resmarl_policy_smoke.pt'
    return cfg


def main(argv: Optional[List[str]] = None) -> None:
    cfg = parse_args(argv)
    train(cfg)


if __name__ == '__main__':
    main()
