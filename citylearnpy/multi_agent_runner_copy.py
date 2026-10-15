"""
CHESCA-ResMARL：Multi-Agent SAC 残差修正模块
============================================

【在整体流程中的位置】
  CHESCA.evaluate_chesca() 在仿真开始前调用本模块：
    setup_chesca_multi_agent_residual()  → 加载预存 SAC + 挂载残差器 + 创建 multi_env
  仿真循环中每步：
    sync_multi_env_step()                → 旁路环境与主环境同步观测
  每步 Checa.predict 阶段 5：
    MultiAgentResidualCorrector.correct() → a_final = 合成(残差) → 安全投影 → clip

【公式】（additive：把 SAC 输出**当残差**解释，而不是当绝对动作）
  additive（默认 residual_mode='additive'）：
      a_final = clip( a_base + α · span · (mask ⊙ a_rl) )
  blend（旧行为，仅供 A/B 对照 residual_mode='blend'）：
      a_final = clip( (1−α)·a_base + α · a_rl_masked )
  · a_base：CHESCA 阶段 1～4 输出（规则 + refine）
  · a_rl：agent_0/1/2 各 SAC 输出 [DHW,ELE,TMP]；在 additive 语义下表示"残差方向 × 幅度"
  · mask 关闭的维残差恒为 0；α=0 → 纯 CHESCA；span 控制残差物理尺度（与 α 解耦）
  · 关键差异 ✗✓：blend 式下网络输出 0 ⇒ 0.85·a_base（**不等于基线**、无恒等点 ✗）；
    additive 式下网络输出 0 ⇒ **精确等于 a_base** ✓ ⇒ 策略可以"什么都不改"，
    于是学习目标退化为"往哪个方向偏、偏多少"，而不是"把基线那一份也一起学会"。
  · 数学上 (1−α)a_base + α·a_rl ≡ a_base + α(a_rl − a_base)，**只改公式写法没有任何行为变化** ——
    真正的差别是"网络输出的语义"（绝对动作 vs 残差），上面两行才是本模块的实质差异。
  · 安全投影（action_safety_projection）只在残差真正生效（α>0）的路径上施加，见 after_safety。

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
        → predict_delta()          ：各 agent SAC 根据 multi_observations 输出 a_rl
        → 合成                       ：additive 残差 a_base + α·span·(mask⊙a_rl)
                                     （或 blend 对照 (1−α)·a_base + α·a_target）
        → _apply_safety_projection()：温控 / 停电硬投影（可用 after_safety 调顺序）
        → clip 到 action_low/high

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
        # 安全投影上下文（由评估内核 set_safety_context 每步注入；
        # 未注入时投影自动跳过，并只提示一次 ⇒ 不会静默失效 ✗）
        self._safety_buildings: List[Any] = []
        self._safety_time_step: int = 0
        self._safety_warned: bool = False
        self.last_safety_infos: Dict[str, Any] = {}
        # P0 门控：首次命中提示一次、并逐楼栋累计命中步数（供日志/事后核对 duty cycle ✓）
        self._gate_warned: bool = False
        self.gate_stats: Dict[str, int] = {'steps': 0, 'blocked_buildings': 0}
        # 可学习门控（gate_mode='learned'）：加载 MLP checkpoint；无则用 gate_params / 恒等
        self.gate = None
        self._try_load_gate(getattr(config, 'gate_policy_path', None))

    def _try_load_gate(self, path: Optional[str]) -> None:
        if not path:
            self.gate = None
            return
        try:
            from pathlib import Path
            p = Path(path)
            if not p.is_file():
                self.gate = None
                return
            from checa.residual.gate_head import load_gate
            self.gate = load_gate(p)
        except Exception:
            self.gate = None

    def _note_gate(self, gate_reasons: Sequence[str]) -> None:
        """累计门控命中情况；首次命中在控制台提示一次（避免"接了但看不出来" ✗）。"""
        self.gate_stats['steps'] = int(self.gate_stats.get('steps', 0)) + 1
        hits = sum(1 for r in gate_reasons if str(r) not in ('none', 'gate_off'))
        if hits <= 0:
            return
        self.gate_stats['blocked_buildings'] = (
            int(self.gate_stats.get('blocked_buildings', 0)) + hits
        )
        if self._gate_warned:
            return
        self._gate_warned = True
        try:
            from checa.residual.config import summarize_gate_reasons
            from utils.base import log_console
            log_console(
                'ℹ️ 残差门控已生效（停电 / SOC 触界 ⇒ 该楼栋本步 α=0）：'
                f'{summarize_gate_reasons(gate_reasons)}'
            )
        except Exception:
            pass

    def set_observation_names(self, names: Optional[List[str]]) -> None:
        self._observation_names = names

    def set_multi_observations(self, observations: Optional[Dict[str, Any]]) -> None:
        self.multi_observations = dict(observations or {})

    def set_safety_context(
        self,
        buildings: Optional[Sequence[Any]] = None,
        time_step: Optional[int] = None,
    ) -> None:
        """
        注入安全投影所需的楼栋对象与当前步号（由评估内核每步调用）。

        buildings 稳定 ⇒ 只需注入一次；time_step 每步变化 ⇒ 每步都要刷新。
        传入 None 表示"该项不变"（便于只刷新 time_step）。
        """
        if buildings is not None:
            self._safety_buildings = list(buildings)
        if time_step is not None:
            self._safety_time_step = int(time_step)

    def _masked_delta(self, a_out: np.ndarray) -> np.ndarray:
        """
        把网络输出当作残差：mask 关闭维置 0，并长度对齐到 3*n_buildings。

        与 checa.residual.corrector.ResidualCorrector._masked_delta 同一语义，
        保证两套残差实现（SAC additive / PPO additive）对 mask 的解释一致。
        """
        out = np.asarray(a_out, dtype=float).reshape(-1).copy()
        expected = 3 * self.n_buildings
        if out.shape[0] > expected:
            out = out[:expected]
        elif out.shape[0] < expected:
            padded = np.zeros(expected, dtype=float)
            padded[: out.shape[0]] = out
            out = padded
        mask = self.config.action_mask
        for b in range(self.n_buildings):
            if not mask.get('dhw', False):
                out[3 * b] = 0.0
            if not mask.get('ele', True):
                out[3 * b + 1] = 0.0
            if not mask.get('tmp', False):
                out[3 * b + 2] = 0.0
        return out

    def _apply_safety_projection(
        self,
        action: np.ndarray,
        action_low: Optional[Sequence[float]] = None,
        action_high: Optional[Sequence[float]] = None,
    ) -> np.ndarray:
        """
        对动作做温控 / 停电硬投影（action_safety_projection.project_building_action）。

        仅在残差真正生效（enabled 且 α>0）的路径上被调用 ⇒ α=0 与纯 CHESCA 逐位一致。
        未注入楼栋上下文时**显式提示一次**再跳过（避免"接了但静默不生效" ✗）。
        """
        if not self._safety_buildings:
            if not self._safety_warned:
                self._safety_warned = True
                try:
                    from utils.base import log_console
                    log_console(
                        '⚠️ 安全投影已启用但缺少楼栋上下文（未调用 set_safety_context），本步跳过。'
                    )
                except Exception:
                    pass
            return action

        try:
            from action_safety_projection import (
                SafetyProjectionConfig,
                building_comfort_outage_state,
                project_building_action,
            )
        except Exception:
            return action

        params = self.config.safety_projection_params or {}
        try:
            cfg = SafetyProjectionConfig(**params)
        except TypeError:
            cfg = SafetyProjectionConfig()

        out = np.asarray(action, dtype=float).reshape(-1).copy()
        infos: Dict[str, Any] = {}
        for b, building in enumerate(self._safety_buildings):
            start = 3 * b
            if start + 3 > out.size:
                break
            action_names = list(getattr(building, 'active_actions', None) or [])
            if not action_names:
                action_names = ['dhw_storage', 'electrical_storage', 'cooling_device']
            state = building_comfort_outage_state(building, self._safety_time_step)
            low = high = None
            if action_low is not None and len(action_low) >= start + 3:
                low = np.asarray(action_low, dtype=float)[start:start + 3]
            if action_high is not None and len(action_high) >= start + 3:
                high = np.asarray(action_high, dtype=float)[start:start + 3]
            new_act, info = project_building_action(
                out[start:start + 3],
                action_names,
                state,
                config=cfg,
                action_low=low,
                action_high=high,
            )
            out[start:start + 3] = new_act
            infos[f'agent_{b}'] = info
        self.last_safety_infos = infos
        return out

    def predict_delta(
        self,
        a_base: Sequence[float],
        observations: Optional[Sequence[float]] = None,
        chesca_state: Optional[Dict[str, Any]] = None,
    ) -> np.ndarray:
        """
        阶段 5 子步骤：各 agent SAC 根据 multi_observations 推理网络输出 a_rl。

        返回值在 correct() 中按 residual_mode 解释：
          · 'additive'（默认）= 残差方向 × 幅度：mask 外置零 → ×α×span → 叠加到 a_base；
          · 'blend'（旧）     = 绝对动作：与 a_base 按 α 混合。
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

        流程：predict_delta(a_rl)
              → 合成（additive：a_base + α·span·(mask⊙a_rl)；blend：(1−α)a_base + α·a_target）
              → 安全投影（after_safety=False 作用于合成结果；True 作用于 a_base）
              → clip 到 action_low / action_high

        示例（单维 ELE）：a_base=0.20, a_rl=0.50, α=0.2, span=1.0
          · additive（默认）：a_final = 0.20 + 0.2·0.50 = 0.30
          · blend（旧）      ：a_final = 0.8·0.20 + 0.2·0.50 = 0.26
        恒等点 ✗✓：additive 下网络输出 0 ⇒ a_final = a_base（有恒等点 ✓）；
                  blend 下网络输出 0 ⇒ a_final = 0.8·a_base（**无恒等点** ✗）。
        """
        from checa.residual.config import evaluate_residual_gate, summarize_gate_reasons
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

        # α=0：仍推理网络输出供日志展示（只影响 trace，不施加任何修正）
        if alpha <= 0.0:
            raw_out = self.predict_delta(base, observations, chesca_state)
            self.last_trace = ResidualTrace(
                applied=False,
                skip_reason='alpha_zero',
                alpha=alpha,
                delta=[0.0] * len(base),
                raw_delta=np.asarray(raw_out, dtype=float).reshape(-1).tolist(),
                a_base=base.tolist(),
                a_final=base.tolist(),
                action_mask=dict(self.config.action_mask),
                policy_loaded=policy_loaded,
            )
            return base

        raw_out = self.predict_delta(base, observations, chesca_state)
        # P0 门控：命中「停电 / SOC 触界」的楼栋本步 α=0（α_eff = α · gate）
        gate, gate_reasons = evaluate_residual_gate(self.n_buildings, self.config, chesca_state)
        self._note_gate(gate_reasons)
        mode = str(getattr(self.config, 'residual_mode', 'additive'))
        span = float(getattr(self.config, 'span', 1.0))
        n = len(base)

        # 可学习门控（gate_mode='learned'）：先对 a_base 指定轴做乘性档位削减，再叠加加性残差。
        # 默认 'binary' ⇒ 返回 None ⇒ base_eff = base ⇒ 与改动前逐位相同 ✓
        from checa.residual.corrector import _maybe_gate
        base_gated, g_diag = _maybe_gate(
            base, self.config, observations=observations,
            observation_names=self._observation_names, chesca_state=chesca_state,
            action_low=action_low, action_high=action_high, gate=self.gate,
        )
        gate_active = base_gated is not None
        base_eff = np.asarray(base if not gate_active else base_gated, dtype=float).reshape(-1)
        final = base_eff.copy()

        if mode == 'blend':
            # 旧行为（仅供 A/B 对照）：把网络输出当**绝对动作**，与 a_base 按 α 混合。
            # 无恒等点：网络输出 0 ⇒ 0.85·a_base ✗（门控处 α_eff=0 ⇒ 退回 a_base ✓）
            target = self._blend_target(raw_out, base_eff)
            m = min(len(target), n)
            alpha_vec = alpha * gate[:m]
            final[:m] = (1.0 - alpha_vec) * base_eff[:m] + alpha_vec * target[:m]
        else:
            # 默认：把网络输出当**残差** ⇒ 输出 0 精确等于 a_base（有恒等点 ✓）
            delta = self._masked_delta(raw_out) * gate
            m = min(len(delta), n)
            final[:m] = base_eff[:m] + alpha * span * delta[:m]

        # 加性增量（相对 base_eff）；可学习门控的乘性效果已体现在 base_eff 里
        scaled_add = final - base_eff

        # 安全投影（温控 / 停电硬约束）：只在残差真正生效的路径上施加
        # ⇒ α=0 / resmarl_enabled=False 仍逐位等于纯 CHESCA ✓
        if bool(getattr(self.config, 'safety_projection_enabled', True)):
            if bool(getattr(self.config, 'after_safety', False)):
                # 投影先作用于（已门控的）基准，再叠加同一份加性增量
                proj_base = self._apply_safety_projection(base_eff, action_low, action_high)
                final = proj_base + scaled_add
            else:
                # 默认：残差先合成、再整段投影 ⇒ 最终动作保证落在安全域内 ✓
                final = self._apply_safety_projection(final, action_low, action_high)
            scaled = final - base

        if action_low is not None and action_high is not None:
            low = np.asarray(action_low, dtype=float).reshape(-1)
            high = np.asarray(action_high, dtype=float).reshape(-1)
            n_clip = min(len(final), len(low), len(high))
            final[:n_clip] = np.clip(final[:n_clip], low[:n_clip], high[:n_clip])
            scaled = final - base

        applied = bool(np.any(np.abs(scaled) > 1e-12))
        if not policy_loaded and not gate_active:
            skip = 'zero_delta_policy'
        elif not bool(np.any(gate > 0.0)) and not gate_active:
            skip = 'gated'
        elif applied:
            skip = 'none'
        else:
            skip = 'zero_delta_policy'

        self.last_trace = ResidualTrace(
            applied=applied,
            skip_reason=skip,
            alpha=alpha,
            delta=scaled.tolist(),
            # 网络原始输出：additive 语义下 = "残差方向 × 幅度"；blend 语义下 = 绝对动作
            raw_delta=np.asarray(raw_out, dtype=float).reshape(-1).tolist(),
            a_base=base.tolist(),
            a_final=final.tolist(),
            action_mask=dict(self.config.action_mask),
            policy_loaded=policy_loaded,
            gate=gate.reshape(-1).tolist(),
            gate_reason=summarize_gate_reasons(gate_reasons),
            gate_learned=(g_diag.get('g') if gate_active else None),
            gate_learned_diag=(dict(g_diag) if gate_active else {}),
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
    # 安全投影所需的楼栋对象在这里尽力注入（步号由评估内核每步刷新）；
    # 取不到就留空 ⇒ 投影会显式提示一次并跳过，而不是静默失效 ✗
    try:
        ma_corrector.set_safety_context(buildings=agent.env.buildings)
    except Exception:
        pass
    agent.residual_corrector = ma_corrector
    agent.residual_config = residual_config

    ckpt = str(agent_config.get('multi_agent_checkpoint') or '').strip()
    log_console(
        f'CHESCA-ResMARL 已启用：加载预存 Multi-Agent SAC，'
        f'α={residual_config.alpha}，mode={residual_config.residual_mode}，'
        f'span={residual_config.span}，after_safety={residual_config.after_safety}，'
        f'proj={residual_config.safety_projection_enabled}，'
        f'agents={agent_ids}，checkpoint={ckpt}'
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
