"""
CHESCA-ResMARL：Multi-Agent SAC 残差修正模块
============================================

【在整体流程中的位置】
  CHESCA.evaluate_chesca() 在仿真开始前调用本模块：
    setup_chesca_multi_agent_residual()  → 加载预存 SAC + 挂载残差器 + 创建 multi_env
  仿真循环中每步：
    sync_multi_env_step()                → 旁路环境与主环境同步观测
  每步 Checa.predict 阶段 5：
    MultiAgentResidualCorrector.correct() → a_final = clip((1−α)·a_base + α·a_rl)

【公式】（blend：SAC 输出绝对动作 a_rl，不做加法叠加强度）
  a_final = clip( (1−α)·a_base + α·a_rl_masked )
  · a_base：CHESCA 阶段 1～4 输出（规则 + refine）
  · a_rl：agent_0/1/2 各 SAC 输出的绝对动作 [DHW,ELE,TMP]
  · mask 关闭的维保持 a_base；α=0 → 纯 CHESCA；α=1 → 掩码维完全采用 SAC
  · 等价写法：a_final = a_base + α·(a_rl_masked − a_base)

【与 Multi-agent.py 的区别】
  Multi-agent.py：训练并保存 Multi-Agent SAC checkpoint
  本模块：评估侧只加载 multi_agent_checkpoint，不再现场 train

【预存模型】
  启用 ResMARL 时 multi_agent_checkpoint 必填；由 Multi-agent.py 训完后写入。

【旁路 multi_env】
  仅用于给三 agent 提供与主环境对齐的观测；KPI 不算 multi_env 这一路。
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning, module='gymnasium')

# Ray 启动前的环境准备（2026-10-02 收拢到 utils/base.py，本项目只此一份 ✓）：
#   · Windows resource 补丁（stdlib 无 getrlimit/setrlimit ⇒ Ray.init 会崩 ✗）
#   · 把 citylearnpy 写进 PYTHONPATH / sys.path ⇒ worker 子进程才能 import 本地模块
#   · 设 RAY_DISABLE_DASHBOARD=1 / RAY_DEDUP_LOGS=0（Windows 上 dashboard/prometheus 易崩）
# ⚠️ 必须在本文件的 `import ray` 之前调用 ✓
from utils.base import prepare_ray_env, ray_runtime_env   # noqa: E402

prepare_ray_env()

from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper, RLlibMultiAgentEnv
# 与训练/评估**同一个环境类**（utils/env.py 里按 OBS_CONTEXT_ENABLE 选）：
#   OBS_CONTEXT_ENABLE 打开时它是 ContextRLlibEnv ⇒ 每个 agent 的观测多 5 维
#   （制冷能力比值 + 楼栋 one-hot + 本步 a_ref）。
# 残差旁路环境必须用它，否则 SAC 收到的观测比训练时少维度 ⇒ 直接
# "mat1 and mat2 shapes cannot be multiplied (1x32 and 40x256)"（2026-10-08 实测踩到）。
from utils.env import _AGENT_ENV_CLS   # noqa: E402
from ray.rllib.algorithms.algorithm import Algorithm


# checkpoint 存取三件套（存 / 取 / 找最新）已于 2026-10-05 抽到 utils/train.py ✓ ——
#   原先它与 CHESCA 残差逻辑同住本文件 ⇒ 只想"加载模型"的入口也得 import 一个 CHESCA
#   专名模块 ✗；现在两边共用同一份实现 ✓（本文件继续复用它 ✓，CHESCA 链路不受影响 ✓）
from utils.train import (      # noqa: E402
    LogFn,
    ensure_ray_initialized,
    load_multi_agent_checkpoint,
    resolve_multi_agent_checkpoint_path,
    save_multi_agent_checkpoint,
)

# Multi-agent.py 默认落盘目录（与 --checkpoint-dir 默认一致）
DEFAULT_MULTI_AGENT_CHECKPOINT_DIR = (
    Path(__file__).resolve().parent / 'checkpoints' / 'multi_agent_sac'
)


# 与 CHESCA.SCHEMA_DEFAULT_EPISODE_STEPS 保持一致（避免循环导入）
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
    'citylearn_challenge_2026_jul_sep': 2208,
    'citylearn_challenge_2026_from_2022': 8760,
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

    # 延迟导入，避免本模块被无关脚本加载时强依赖 rewards
    from rewards.comfort_outage_reward import ComfortOutagePenaltyReward

    # 与训练/评估**同一口径地打观测补丁**（utils/env.build_env_config 里也是这一句）：
    #   直接传 schema 名字（不打补丁）会少掉"偏差类"观测 ⇒ SAC 收到的观测比训练时少维度。
    from utils.env import OBS_EXTRA_ACTIVE, TEMP_DELTA, patch_schema_observations

    schema_obj, schema_root = patch_schema_observations(schema, OBS_EXTRA_ACTIVE, TEMP_DELTA)

    env_kwargs = {
        'schema': schema_obj,
        'episode_time_steps': episode_steps,
        'reward_function': ComfortOutagePenaltyReward,
    }
    if schema_root is not None:
        env_kwargs['root_directory'] = str(schema_root)
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
    阶段 0-③：加载预存 Multi-Agent SAC（仿真开始前执行）。

    启用 ResMARL 时必须提供 agent_config.multi_agent_checkpoint；
    本地评估不再现场 train（训练请用 Multi-agent.py）。
    """
    agent_config = agent_config or {}
    log = log_console or (lambda _msg: None)
    ensure_ray_initialized(log_console=log)
    probe_env = _AGENT_ENV_CLS(env_config)
    agent_ids = list(probe_env._agent_ids)

    checkpoint = str(agent_config.get('multi_agent_checkpoint') or '').strip()
    if not checkpoint:
        raise ValueError(
            '启用 CHESCA-ResMARL 时必须配置 multi_agent_checkpoint（预存模型路径）。'
            '请先用 Multi-agent.py 训练并保存 checkpoint，再在配置页填写路径。'
            '本地评估（CHESCA）不再现场训练 Multi-Agent SAC。'
        )

    algo = load_multi_agent_checkpoint(checkpoint, log_console=log)
    log(f'已加载预存 Multi-Agent SAC：{checkpoint}')
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
        → predict_delta()：各 agent SAC 根据 multi_observations 输出绝对动作 a_rl
        → _blend_target()：mask 开启维用 a_rl，关闭维保留 a_base
        → a_final = clip((1−α)·a_base + α·a_target)

    multi_observations 由 CHESCA 每步 _bind_multi_obs() 注入，
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
        阶段 5 子步骤：各 agent SAC 根据 multi_observations 推理绝对动作 a_rl。

        返回值在 correct() 中与 a_base 按 α 混合（非加法残差）。
        方法名保留 predict_delta 以兼容 ResidualCorrector 接口。
        """
        expected = 3 * self.n_buildings
        if self.sac_algo is None:
            self.last_rollout = None
            return np.zeros(expected, dtype=float)

        a_rl = np.zeros(expected, dtype=float)
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
                a_rl[3 * b + d] = float(act[d])
        self.last_rollout = None
        return a_rl

    def _blend_target(self, a_rl: np.ndarray, a_base: np.ndarray) -> np.ndarray:
        """mask 开启维用 SAC 绝对动作，关闭维保留 a_base。"""
        base = np.asarray(a_base, dtype=float).reshape(-1)
        rl = np.asarray(a_rl, dtype=float).reshape(-1)
        expected = 3 * self.n_buildings
        if rl.shape[0] > expected:
            rl = rl[:expected]
        elif rl.shape[0] < expected:
            padded = np.zeros(expected, dtype=float)
            padded[: rl.shape[0]] = rl
            rl = padded
        out = base.copy()
        if out.shape[0] < expected:
            padded = np.zeros(expected, dtype=float)
            padded[: out.shape[0]] = out
            out = padded
        elif out.shape[0] > expected:
            out = out[:expected].copy()
        mask = self.config.action_mask
        for b in range(self.n_buildings):
            if mask.get('dhw', False):
                out[3 * b] = float(rl[3 * b])
            if mask.get('ele', True):
                out[3 * b + 1] = float(rl[3 * b + 1])
            if mask.get('tmp', False):
                out[3 * b + 2] = float(rl[3 * b + 2])
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

        流程：predict_delta(a_rl) → blend_target → (1−α)·a_base + α·a_target → clip

        示例（单维 ELE）：a_base=0.20, a_rl=0.50, α=0.2
          → a_final = 0.8·0.20 + 0.2·0.50 = 0.26
          （旧加法公式会得到 0.20+0.10=0.30，同向时更容易过头）
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

        # α=0：仍推理 a_rl 供日志展示，但不施加修正
        if alpha <= 0.0:
            raw_rl = self.predict_delta(base, observations, chesca_state)
            self.last_trace = ResidualTrace(
                applied=False,
                skip_reason='alpha_zero',
                alpha=alpha,
                delta=[0.0] * len(base),
                raw_delta=np.asarray(raw_rl, dtype=float).reshape(-1).tolist(),
                a_base=base.tolist(),
                a_final=base.tolist(),
                action_mask=dict(self.config.action_mask),
                policy_loaded=policy_loaded,
            )
            return base

        raw_rl = self.predict_delta(base, observations, chesca_state)
        target = self._blend_target(raw_rl, base)
        # 对齐长度后再混合
        n = min(len(base), len(target))
        final = base.copy()
        final[:n] = (1.0 - alpha) * base[:n] + alpha * target[:n]
        # 埋点：相对 a_base 的有效增量 α·(a_rl − a_base)
        scaled = final - base

        if action_low is not None and action_high is not None:
            low = np.asarray(action_low, dtype=float).reshape(-1)
            high = np.asarray(action_high, dtype=float).reshape(-1)
            n_clip = min(len(final), len(low), len(high))
            final[:n_clip] = np.clip(final[:n_clip], low[:n_clip], high[:n_clip])
            scaled = final - base

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
            raw_delta=np.asarray(raw_rl, dtype=float).reshape(-1).tolist(),
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

    加载预存 checkpoint；旁路 multi_env 与探测 env 均使用 eval_schema。
    """
    from checa.residual.config import parse_residual_config

    plan = schema_plan or {}
    eval_schema = plan.get('eval_schema') or getattr(config, 'SCHEMA', None)
    eval_steps = plan.get('eval_episode_steps')

    if not eval_schema:
        eval_schema = 'citylearn_challenge_2023_phase_2_local_evaluation'
    if eval_steps is None:
        eval_steps = _SCHEMA_DEFAULT_EPISODE_STEPS.get(eval_schema, 720)

    env_config = build_multi_agent_env_config(
        config,
        enable_render=False,
        schema=eval_schema,
        episode_time_steps=eval_steps,
    )

    log_console(f'CHESCA-ResMARL schema：{eval_schema}({eval_steps}步)')

    multi_env = _AGENT_ENV_CLS(env_config)

    sac_algo, agent_ids = build_sac_multi_agent_model(
        env_config,
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

    ckpt = str(agent_config.get('multi_agent_checkpoint') or '').strip()
    log_console(
        f'CHESCA-ResMARL 已启用：加载预存 Multi-Agent SAC，'
        f'α={residual_config.alpha}，agents={agent_ids}，checkpoint={ckpt}'
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
