"""
CHESCA-ResMARL：Multi-Agent SAC 残差修正模块
============================================

【在整体流程中的位置】
  local_evaluation_copy.evaluate_chesca() 在仿真开始前调用本模块：
    setup_chesca_multi_agent_residual()  → 训练 SAC + 挂载残差器 + 创建 multi_env
  仿真循环中每步：
    sync_multi_env_step()                → 旁路环境与主环境同步观测
  每步 Checa.predict 阶段 5：
    MultiAgentResidualCorrector.correct() → a_final = clip(a_base + α·mask·Δa)

【公式】
  a_final = clip(a_base + α · mask · Δa_MA)
  · a_base：CHESCA 阶段 1～4 输出（规则 + refine）
  · Δa_MA：agent_0/1/2 各 SAC 输出的 3 维 [DHW,ELE,TMP]，视为修正量
  · α=0 或 mask 关闭某维 → 该维不变，数值等同纯 CHESCA

【与 Multi-agent.py 的区别】
  Multi-agent.py：SAC 直接控制整段仿真（端到端）
  本模块：SAC 只在 CHESCA 的 predict 阶段 5 提供 Δa，不单独跑完整 MARL 仿真

【旁路 multi_env】
  仅用于给三 agent 提供与主环境对齐的观测；KPI 不算 multi_env 这一路。
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning, module='gymnasium')

from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper, RLlibMultiAgentEnv
from ray.rllib.algorithms.sac import SACConfig
from ray.rllib.policy.policy import PolicySpec


LogFn = Callable[[str], None]

# 与 local_evaluation_copy.SCHEMA_DEFAULT_EPISODE_STEPS 保持一致（避免循环导入）
_SCHEMA_DEFAULT_EPISODE_STEPS = {
    'warm_up': 720,
    'citylearn_challenge_2023_phase_1': 720,
    'citylearn_challenge_2023_phase_2_local_evaluation': 720,
    'citylearn_challenge_2023_phase_2_online_evaluation_1': 2208,
    'citylearn_challenge_2023_phase_2_online_evaluation_2': 2208,
    'citylearn_challenge_2023_phase_2_online_evaluation_3': 2208,
    'citylearn_challenge_2023_phase_3_1': 2208,
    'citylearn_challenge_2023_phase_3_2': 2208,
    'citylearn_challenge_2023_phase_3_3': 2208,
}


def build_multi_agent_env_config(
    config,
    enable_render: Optional[bool] = None,
    schema: Optional[str] = None,
    episode_time_steps: Optional[int] = None,
) -> dict:
    """构造 RLlibMultiAgentEnv 所需 env_config。"""
    output_dir = Path(getattr(config, 'RENDER_DIR', '.'))
    render_session = getattr(config, 'RENDER_SESSION', '.')
    if enable_render is None:
        enable_render = bool(getattr(config, 'ENABLE_RENDER', True))
    if schema is None:
        schema = getattr(config, 'SCHEMA', 'citylearn_challenge_2023_phase_2_local_evaluation')
    if episode_time_steps is None:
        episode_time_steps = _SCHEMA_DEFAULT_EPISODE_STEPS.get(schema, 720)
    episode_steps = int(episode_time_steps)

    env_kwargs = {
        'schema': schema,
        'episode_time_steps': episode_steps,
    }
    if enable_render:
        env_kwargs['render_mode'] = 'end'
        env_kwargs['render_directory'] = output_dir
        env_kwargs['render_session_name'] = render_session

    return {
        'env_kwargs': env_kwargs,
        'wrappers': [
            NormalizedObservationWrapper,
            ClippedObservationWrapper,
        ],
    }


def build_sac_multi_agent_model(
    env_config: dict,
    agent_config: Optional[dict] = None,
    log_console: Optional[LogFn] = None,
):
    """
    阶段 0-③：构建并训练 RLlib SAC（仿真开始前执行，不是跑完整 MARL 评估）。

    multi_agent_train_epochs：训练轮数，默认 20。
    训练完成后网络用于 predict 阶段 5 的 compute_single_action（推理 Δa）。
    """
    agent_config = agent_config or {}
    log = log_console or (lambda _msg: None)
    probe_env = RLlibMultiAgentEnv(env_config)
    agent_ids = list(probe_env._agent_ids)

    sac_cfg = (
        SACConfig()
        .environment(RLlibMultiAgentEnv, env_config=env_config)
        .multi_agent(
            policies={aid: PolicySpec() for aid in agent_ids},
            policy_mapping_fn=lambda agent_id, episode, worker, **kwargs: agent_id,
        )
    )
    algo = sac_cfg.build()

    train_epochs = int(agent_config.get('multi_agent_train_epochs', 20))
    if train_epochs < 1:
        train_epochs = 1
    log(f'开始 Multi-Agent SAC 训练（残差策略），共 {train_epochs} 轮...')
    for i in range(train_epochs):
        log(f'[Multi-Agent SAC 训练] 第 {i + 1}/{train_epochs} 轮...')
        _ = algo.train()
    log('Multi-Agent SAC 训练完成')

    return algo, agent_ids


def central_actions_to_multi(
    actions: Sequence,
    agent_ids: Sequence[str],
) -> Dict[str, np.ndarray]:
    """
    将 CHESCA central 动作 [[9 维]] 转为 RLlib 多智能体动作 dict。

    顺序：Building 0 → agent_0，每 agent [DHW, ELE, TMP]。
    """
    if not actions:
        return {aid: np.zeros(3, dtype=float) for aid in agent_ids}

    flat = actions[0] if isinstance(actions[0], (list, tuple, np.ndarray)) else actions
    flat = np.asarray(flat, dtype=float).reshape(-1)
    out: Dict[str, np.ndarray] = {}
    for i, agent_id in enumerate(agent_ids):
        base = 3 * i
        out[agent_id] = np.array([
            float(flat[base]) if base < len(flat) else 0.0,
            float(flat[base + 1]) if base + 1 < len(flat) else 0.0,
            float(flat[base + 2]) if base + 2 < len(flat) else 0.0,
        ], dtype=float)
    return out


class MultiAgentResidualCorrector:
    """
    Multi-Agent SAC 残差修正器（接口兼容 checa.residual.ResidualCorrector）。

    【在 predict 阶段 5 中的角色】
      Checa.apply_residual_correction() → correct()
        → predict_delta()：各 agent SAC 根据 multi_observations 输出原始 Δa
        → _masked_delta()：按 residual_action_mask 过滤维度
        → × α → 加 a_base → clip → a_final

    multi_observations 由 local_evaluation_copy 每步 _bind_multi_obs() 注入，
    来自旁路 multi_env（与主 env 用同一 a_final 同步推进）。
    """

    def __init__(
        self,
        n_buildings: int,
        config,
        sac_algo,
        agent_ids: Sequence[str],
        explore: bool = False,
    ):
        from checa.residual.corrector import ResidualTrace

        self.n_buildings = int(n_buildings)
        self.config = config
        self.sac_algo = sac_algo
        self.agent_ids = list(agent_ids)
        self.explore = bool(explore)
        self.multi_observations: Dict[str, Any] = {}
        self.last_trace = ResidualTrace()
        self.policy = sac_algo
        self.deterministic = not self.explore
        self.last_rollout = None
        self._observation_names = None

    def set_observation_names(self, names: Optional[List[str]]) -> None:
        self._observation_names = names

    def set_multi_observations(self, observations: Optional[Dict[str, Any]]) -> None:
        self.multi_observations = dict(observations or {})

    def predict_delta(
        self,
        a_base: Sequence[float],
        observations: Optional[Sequence[float]] = None,
        chesca_state: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """
        阶段 5 子步骤：各 agent SAC 根据 multi_observations 推理原始 Δa。

        注意：SAC 输出的是「修正建议」，不是最终环境动作；最终动作在 correct() 里与 a_base 合成。
        """
        expected = 3 * self.n_buildings
        if self.sac_algo is None:
            self.last_rollout = None
            return np.zeros(expected, dtype=float)

        delta = np.zeros(expected, dtype=float)
        for i, agent_id in enumerate(self.agent_ids):
            obs = self.multi_observations.get(agent_id)
            if obs is None:
                continue
            raw = self.sac_algo.compute_single_action(
                obs,
                policy_id=agent_id,
                explore=self.explore,
            )
            act = np.asarray(raw, dtype=float).reshape(-1)
            b = min(i, self.n_buildings - 1)
            for d in range(min(3, len(act))):
                delta[3 * b + d] = float(act[d])
        self.last_rollout = None
        return delta

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
        """
        阶段 5 入口（由 Checa.apply_residual_correction 调用）。

        流程：predict_delta → mask 过滤 → ×α → 加 a_base → clip → a_final

        示例（单维 ELE）：a_base=0.20, Δa=0.50, α=0.2 → a_final=0.20+0.1=0.30
        """
        from checa.residual.corrector import ResidualTrace

        base = np.asarray(a_base, dtype=float).reshape(-1).copy()
        alpha = float(self.config.alpha)
        policy_loaded = self.sac_algo is not None

        if not self.config.enabled:
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


def setup_chesca_multi_agent_residual(
    agent,
    agent_config: dict,
    config,
    log_console: LogFn,
    schema_plan: Optional[dict] = None,
) -> Tuple[RLlibMultiAgentEnv, List[str], Any]:
    """
    阶段 0-③～⑤：仿真开始前，为 CHESCA Agent 挂载 Multi-Agent SAC 残差层。

    schema_plan（方案 A 训测分离）：
      ③ SAC 在 train_schema 上训练（默认 local_evaluation，720h）
      ⑤ 旁路 multi_env 使用 eval_schema（与主 env 一致，默认 online_evaluation_1）
    """
    from checa.residual.config import parse_residual_config

    plan = schema_plan or {}
    train_schema = plan.get('train_schema') or getattr(config, 'TRAIN_SCHEMA', None)
    eval_schema = plan.get('eval_schema') or getattr(config, 'SCHEMA', None)
    train_steps = plan.get('train_episode_steps')
    eval_steps = plan.get('eval_episode_steps')

    if not train_schema:
        train_schema = 'citylearn_challenge_2023_phase_2_local_evaluation'
    if not eval_schema:
        eval_schema = train_schema
    if train_steps is None:
        train_steps = _SCHEMA_DEFAULT_EPISODE_STEPS.get(train_schema, 720)
    if eval_steps is None:
        eval_steps = _SCHEMA_DEFAULT_EPISODE_STEPS.get(eval_schema, 720)

    train_env_config = build_multi_agent_env_config(
        config,
        enable_render=False,
        schema=train_schema,
        episode_time_steps=train_steps,
    )
    sync_env_config = build_multi_agent_env_config(
        config,
        enable_render=False,
        schema=eval_schema,
        episode_time_steps=eval_steps,
    )

    if plan.get('schema_split_enabled'):
        log_console(
            f'CHESCA-ResMARL 训测分离：SAC 训练 schema={train_schema}({train_steps}步)，'
            f'仿真 schema={eval_schema}({eval_steps}步)'
        )
    else:
        log_console(f'CHESCA-ResMARL 单 schema：{eval_schema}({eval_steps}步)')

    multi_env = RLlibMultiAgentEnv(sync_env_config)

    sac_algo, agent_ids = build_sac_multi_agent_model(
        train_env_config,
        agent_config,
        log_console=log_console,
    )

    residual_config = parse_residual_config(agent.params)
    ma_corrector = MultiAgentResidualCorrector(
        agent.n_buildings,
        residual_config,
        sac_algo,
        agent_ids,
        explore=bool(agent_config.get('multi_agent_explore', False)),
    )
    ma_corrector.set_observation_names(agent.observation_names_b)
    agent.residual_corrector = ma_corrector
    agent.residual_config = residual_config

    log_console(
        f'CHESCA-ResMARL 已启用：Multi-Agent SAC 残差，'
        f'α={residual_config.alpha}，agents={agent_ids}'
    )
    return multi_env, agent_ids, sac_algo


def sync_multi_env_step(
    multi_env: RLlibMultiAgentEnv,
    actions: Sequence,
    agent_ids: Sequence[str],
) -> Dict[str, Any]:
    """
    阶段 2-2.2：主循环中，用与 central 主环境相同的 a_final 推进 multi_env。

    时机：env.step(a_final) 之后、下一小时 predict() 之前。
    目的：让各 agent 观测与主环境对齐，供阶段 5 SAC 推理 Δa。
    注意：multi_env 不参与 KPI 计算，仅作观测同步旁路。
    """
    multi_actions = central_actions_to_multi(actions, agent_ids)
    observations, _, _, _, _ = multi_env.step(multi_actions)
    return observations
