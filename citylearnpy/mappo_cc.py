# -*- coding: utf-8 -*-
"""CHESCA-ResMARL · MAPPO 集中 critic（CTDE）落地模块。

【为什么要有这个文件】
现有 MARL 训练管道（Multi-agent-train.detailed.py → utils/train.py::run_training）
用的是 RLlib **独立 SAC**：每栋楼一个策略、各自的 critic 只看各自 obs，
**没有集中 critic**（训练期看不到其它楼的 obs/动作 ⇒ 存在非平稳性）。

论文 v2 §五 要求「actor 分散 + critic 集中」的 CTDE 架构。本模块按 RLlib 官方
`examples/centralized_critic.py` 的**规范做法**落地：
  - actor：仍是一栋楼一个策略（分散执行，obs 只看自己 ✓）；
  - critic：训练期把「其它楼的 obs + 动作」拼进来算集中 value（集中训练 ✓）；
  - 部署：只导出 actor，critic 不存在（推理路径不变 ✓）。

【实现机制（与官方 example 逐字同构）】
  - `CentralizedCriticModel(TorchModelV2)`：policy head 用本楼 obs；
    `central_value_function(own_obs, other_obs, other_action)` 用全局信息算 V。
  - `CentralizedCriticPPOPolicy(PPOTorchPolicy)`：覆写 `postprocess_trajectory`
    （用 `other_agent_batches` 把其它楼的 obs/动作塞进 sample_batch，并用集中 VF
    重算 VF_PREDS 后做 GAE）与 `loss`（用集中 VF 替代默认 value_function）。
  - `CentralizedCriticPPO(PPO)`：只把默认 policy 换成上面那个。

【零侵入铁律】
  - 本文件是**独立新增模块**，不 import 时对项目零影响；
  - 由新入口 `Multi-agent-train-mappo.py` 在 `--algorithm mappo` 时显式加载；
  - 现有 SAC 路径、checkpoint 格式、评估入口**一个字节都不改** ✓。

【已知边界（诚实声明）】
  - 本模块实现的是**训练期集中 critic**（CTDE 的"集中训练"半边）；
  - 评估侧仍需复用现有 `Multi-agent-eval.py` 的 checkpoint 加载（PPO checkpoint 的
    目录标记与 SAC 一致 ⇒ 理论上兼容，但需实测验证 `PPO.from_checkpoint` 路径）；
  - 完整「训练→评估→KPI 对比」端到端跑通与「vs 独立 SAC 的 ΔKPI」需单独一轮实验。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# 就地 import ray/torch（本模块只在显式开启 MAPPO 时被 import，不拖累其它入口的 import 期）
from ray.rllib.algorithms.ppo import PPO
from ray.rllib.algorithms.ppo.ppo_torch_policy import PPOTorchPolicy
from ray.rllib.evaluation.postprocessing import Postprocessing, compute_advantages
from ray.rllib.models.modelv2 import ModelV2
from ray.rllib.models.torch.fcnet import FullyConnectedNetwork as TorchFC
from ray.rllib.models.torch.misc import SlimFC
from ray.rllib.models.torch.torch_modelv2 import TorchModelV2
from ray.rllib.policy.sample_batch import SampleBatch
from ray.rllib.utils.annotations import override
from ray.rllib.utils.framework import try_import_torch
from ray.rllib.utils.torch_utils import convert_to_torch_tensor

torch, nn = try_import_torch()

# 在 sample_batch 里额外存储的键（集中 critic 用）
OTHER_OBS = "other_obs"
OTHER_ACTION = "other_action"


# ============================================================================
# 集中 critic 模型（policy head 分散 + value 集中）
# ============================================================================
class CentralizedCriticModel(TorchModelV2, nn.Module):
    """MAPPO 集中 critic 模型。

    - `forward`：policy head，只用本楼 obs ⇒ 输出动作 logits（分散执行 ✓）；
    - `central_value_function(own_obs, other_obs, other_action)`：集中 VF，
      把「本楼 obs + 其它楼 obs + 其它楼动作」拼起来算 value（集中训练 ✓）。
    """

    def __init__(self, obs_space, action_space, num_outputs, model_config, name):
        TorchModelV2.__init__(
            self, obs_space, action_space, num_outputs, model_config, name
        )
        nn.Module.__init__(self)

        # 本楼 policy 网络（与 SAC 的 actor 同构：MLP → logits）
        self.model = TorchFC(obs_space, action_space, num_outputs, model_config, name)

        # 集中 VF：输入 = 本楼 obs + 所有其它楼的 obs(拼接) + 其它楼动作(拼接)。
        # 其它楼栋数 N-1 由 custom_model_config["n_agents"] 传入（build_mappo_config 填）。
        obs_size = int(np.prod(obs_space.shape))
        act_size = int(np.prod(action_space.shape))
        _cc = model_config.get("custom_model_config") or {}
        n_agents = int(_cc.get("n_agents", 2)) if isinstance(_cc, dict) else 2
        n_others = max(n_agents - 1, 1)
        central_in = obs_size + n_others * obs_size + n_others * act_size
        self._central_vf_in = central_in
        self.central_vf = nn.Sequential(
            SlimFC(central_in, 256, activation_fn=nn.Tanh),
            SlimFC(256, 256, activation_fn=nn.Tanh),
            SlimFC(256, 1),
        )

    @override(ModelV2)
    def forward(self, input_dict, state, seq_lens):
        model_out, _ = self.model(input_dict, state, seq_lens)
        return model_out, []

    def central_value_function(
        self,
        own_obs: torch.Tensor,
        other_obs: torch.Tensor,
        other_action: torch.Tensor,
    ) -> torch.Tensor:
        """集中 VF：(own_obs, other_obs, other_action) → value (B,)。"""
        inp = torch.cat([own_obs, other_obs, other_action], dim=-1)
        return torch.reshape(self.central_vf(inp), [-1])

    @override(ModelV2)
    def value_function(self):
        # 默认 value 不被使用（loss 里被集中 VF 替换），保留一个可用的兜底
        return self.model.value_function()


# ============================================================================
# 集中 critic 策略（覆写 postprocess_trajectory + loss）
# ============================================================================
class CentralizedValueMixin:
    """给 policy 加 `compute_central_vf`，从模型里取集中 value。"""

    def __init__(self):
        self.compute_central_vf = self.model.central_value_function


def centralized_critic_postprocessing(
    policy, sample_batch, other_agent_batches=None, episode=None
):
    """把其它楼的 obs/动作塞进本楼 sample_batch，并用集中 VF 重算 VF_PREDS 后做 GAE。

    与 RLlib `examples/centralized_critic.py::centralized_critic_postprocessing` 同构；
    差别：对手不止一个（N-1 栋）⇒ 其它楼的 obs/动作**按楼拼接**成一个向量再拼进
    集中 VF 输入；若某步/某片缺少某些其它楼（truncate 边界），按**零填充**补齐到
    (N-1) 栋，保证集中 VF 的输入维恒定（= own + (N-1)·obs + (N-1)·act）。
    """
    own_obs = sample_batch[SampleBatch.CUR_OBS]
    obs_size = int(own_obs.shape[-1])
    act_size = int(sample_batch[SampleBatch.ACTIONS].shape[-1])

    if hasattr(policy, "compute_central_vf") and other_agent_batches:
        # 其它楼的 obs/动作：按 agent 顺序拼接成一个「全局」向量
        other_obs_list = []
        other_act_list = []
        for _pid, ob in other_agent_batches.values():
            other_obs_list.append(
                np.asarray(ob[SampleBatch.CUR_OBS], dtype=np.float32)
            )
            other_act_list.append(
                np.asarray(ob[SampleBatch.ACTIONS], dtype=np.float32)
            )

        n = own_obs.shape[0]
        if other_obs_list:
            other_obs = np.concatenate(other_obs_list, axis=-1)[:n].astype(np.float32)
            other_act = np.concatenate(other_act_list, axis=-1)[:n].astype(np.float32)
        else:
            other_obs = np.zeros((n, 0), dtype=np.float32)
            other_act = np.zeros((n, 0), dtype=np.float32)

        # 零填充到 (N-1) 栋，保证集中 VF 输入维恒定
        n_agents = _policy_n_agents(policy)
        n_others = max(n_agents - 1, 0)
        need_obs = n_others * obs_size
        need_act = n_others * act_size
        if other_obs.shape[-1] < need_obs:
            pad = np.zeros((n, need_obs - other_obs.shape[-1]), dtype=np.float32)
            other_obs = np.concatenate([other_obs, pad], axis=-1)
        if other_act.shape[-1] < need_act:
            pad = np.zeros((n, need_act - other_act.shape[-1]), dtype=np.float32)
            other_act = np.concatenate([other_act, pad], axis=-1)

        sample_batch[OTHER_OBS] = other_obs
        sample_batch[OTHER_ACTION] = other_act

        # 用集中 VF 重算 VF_PREDS（替换默认的分散 value）
        sample_batch[SampleBatch.VF_PREDS] = (
            policy.compute_central_vf(
                convert_to_torch_tensor(own_obs, policy.device),
                convert_to_torch_tensor(other_obs, policy.device),
                convert_to_torch_tensor(other_act, policy.device),
            )
            .cpu()
            .detach()
            .numpy()
        )
    else:
        # policy 尚未初始化 / 无其它楼 ⇒ 用零占位（与官方 example 一致）
        n_agents = _policy_n_agents(policy)
        n_others = max(n_agents - 1, 0)
        n = own_obs.shape[0]
        sample_batch[OTHER_OBS] = np.zeros(
            (n, n_others * obs_size), dtype=np.float32
        )
        sample_batch[OTHER_ACTION] = np.zeros(
            (n, n_others * act_size), dtype=np.float32
        )
        sample_batch[SampleBatch.VF_PREDS] = np.zeros_like(
            sample_batch[SampleBatch.REWARDS], dtype=np.float32
        )

    completed = sample_batch[SampleBatch.TERMINATEDS][-1]
    last_r = 0.0 if completed else sample_batch[SampleBatch.VF_PREDS][-1]

    return compute_advantages(
        sample_batch,
        last_r,
        policy.config["gamma"],
        policy.config["lambda"],
        use_gae=policy.config["use_gae"],
    )


def _policy_n_agents(policy) -> int:
    """从 policy 的 model config 里取 agent 数（build_mappo_config 写入）。"""
    try:
        cc = policy.config.get("model", {}).get("custom_model_config", {}) or {}
        n = int(cc.get("n_agents", 0))
        if n > 0:
            return n
    except Exception:
        pass
    # 兜底：从 model 的集中 VF 输入维反推（不可靠，但至少不崩）
    try:
        m = policy.model
        in_dim = getattr(m, "_central_vf_in", None)
        if in_dim is None:
            m = m.model if hasattr(m, "model") else m
            in_dim = getattr(m, "_central_vf_in", None)
    except Exception:
        in_dim = None
    # 返回 2（至少假设有 1 个其它 agent），调用方会据此 zero-pad；集中 VF 用同样
    # 的 n_agents 构造 ⇒ 输入维仍一致（只要构造与 postprocess 用同一 n_agents）。
    return 2


def loss_with_central_critic(policy, base_policy, model, dist_class, train_batch):
    """用集中 VF 替代默认 value_function 计算 PPO loss（与官方 example 同构）。"""
    vf_saved = model.value_function
    model.value_function = lambda: policy.model.central_value_function(
        train_batch[SampleBatch.CUR_OBS],
        train_batch[OTHER_OBS],
        train_batch[OTHER_ACTION],
    )
    policy._central_value_out = model.value_function()
    loss = base_policy.loss(model, dist_class, train_batch)
    model.value_function = vf_saved
    return loss


def central_vf_stats(policy, train_batch):
    from ray.rllib.utils.torch_utils import explained_variance as _torch_ev

    central_out = getattr(policy, "_central_value_out", None)
    if central_out is None:
        return {}
    ev = float(
        _torch_ev(
            train_batch[Postprocessing.VALUE_TARGETS],
            central_out.detach(),
        )
    )
    return {"vf_explained_var": ev}


class CentralizedCriticPPOPolicy(CentralizedValueMixin, PPOTorchPolicy):
    """集中 critic 的 PPO torch 策略。"""

    def __init__(self, observation_space, action_space, config):
        PPOTorchPolicy.__init__(self, observation_space, action_space, config)
        CentralizedValueMixin.__init__(self)

    @override(PPOTorchPolicy)
    def loss(self, model, dist_class, train_batch):
        return loss_with_central_critic(self, super(), model, dist_class, train_batch)

    @override(PPOTorchPolicy)
    def postprocess_trajectory(
        self, sample_batch, other_agent_batches=None, episode=None
    ):
        return centralized_critic_postprocessing(
            self, sample_batch, other_agent_batches, episode
        )

    @override(PPOTorchPolicy)
    def stats_fn(self, train_batch: SampleBatch):
        stats = super().stats_fn(train_batch)
        stats.update(central_vf_stats(self, train_batch))
        return stats


class CentralizedCriticPPO(PPO):
    """把默认 policy 换成集中 critic 策略的 PPO 算法。"""

    @classmethod
    @override(PPO)
    def get_default_policy_class(cls, config):
        return CentralizedCriticPPOPolicy


# ============================================================================
# 构建 MAPPO 配置（与 utils/train.py 里 SAC 配置同构的 on-policy 版本）
# ============================================================================
def build_mappo_config(
    *,
    env_cls: Any,
    env_config: Dict[str, Any],
    agent_ids: List[str],
    train_batch_size: int,
    rollout_fragment_length: Any,
    num_rollout_workers: int,
    min_sample_timesteps_per_iteration: int,
    seed: int,
    model_config: Optional[Dict[str, Any]] = None,
    gamma: float = 0.99,
    lambda_: float = 0.95,
    lr: float = 5e-4,
    clip_param: float = 0.2,
    vf_clip_param: float = 10.0,
    entropy_coeff: float = 0.01,
    vf_loss_coeff: float = 0.5,
    kl_coeff: float = 0.2,
    centralized: bool = True,
):
    """构造集中 critic 的 PPOConfig。

    与 utils/train.py::run_training 里的 SACConfig 保持同一组训练规模参数语义，
    只是把算法换成 on-policy PPO + 集中 critic 策略 + 自定义模型。

    `centralized=False` 时不挂自定义模型 ⇒ 得到 **IPPO 基线**（PPO + 分散 critic：
    每栋楼的 value function 只看自己的 obs）。除 critic 是否集中外，其余配置逐项相同，
    便于把 IPPO→MAPPO 的差干净地归因到 CTDE。
    """
    from ray.rllib.algorithms.ppo.ppo import PPOConfig as _PC
    PPOConfig = _PC
    from ray.rllib.policy.policy import PolicySpec

    model_cfg = dict(model_config or {})
    if centralized:
        model_cfg.setdefault("custom_model", "mappo_cc_model")
        # 把 agent 数传给集中 critic 模型（决定"其它楼 obs/动作"的拼接维度）
        _cc = dict(model_cfg.get("custom_model_config") or {})
        _cc.setdefault("n_agents", len(agent_ids))
        model_cfg["custom_model_config"] = _cc

    from ray.rllib.algorithms.ppo.ppo import PPOConfig as _PC
    from ray.rllib.policy.policy import PolicySpec

    model_cfg = dict(model_config or {})
    if centralized:
        model_cfg.setdefault("custom_model", "mappo_cc_model")
        # 把 agent 数传给集中 critic 模型（决定"其它楼 obs/动作"的拼接维度）
        _cc = dict(model_cfg.get("custom_model_config") or {})
        _cc.setdefault("n_agents", len(agent_ids))
        model_cfg["custom_model_config"] = _cc

    # ★ 2026-10-13 修补：拆 chain（避免 RLlib experimental() 内部对名字的 monkey-patch）
    config = _PC()
    config = config.experimental(_enable_new_api_stack=False)
    # ★ 2026-10-13 修补：先 build 一个 env 实例来拿 obs_space/action_space，再传给 PolicySpec。
    #   否则 ray worker 里 get_multi_agent_setup 拿不到 spaces（env 是 remote pickle 过来的，
    #   初始 _disable_preprocessor_api 改动后行为有微调，env.observation_space 不可用）⇒
    #   "observation_space not provided in PolicySpec for default_policy"。
    try:
        _probe = env_cls(env_config)
        _obs_sp = _probe.observation_space
        _act_sp = _probe.action_space
        del _probe
    except Exception:
        _obs_sp = None
        _act_sp = None
    if _obs_sp is not None:
        _policies = {
            a: PolicySpec(observation_space=_obs_sp[a], action_space=_act_sp[a])
            for a in agent_ids
        }
    else:
        _policies = {a: PolicySpec() for a in agent_ids}
    config = config.environment(env_cls, env_config=env_config, disable_env_checking=True)
    config = config.framework("torch")
    config = config.multi_agent(
        policies=_policies,
        policy_mapping_fn=lambda agent_id, episode, worker, **kwargs: agent_id,
    )
    config = config.training(
        gamma=gamma, lr=lr, lambda_=lambda_, clip_param=clip_param,
        vf_clip_param=vf_clip_param, entropy_coeff=entropy_coeff,
        vf_loss_coeff=vf_loss_coeff, kl_coeff=kl_coeff,
        train_batch_size=train_batch_size, model=model_cfg,
    )
    config = config.rollouts(
        num_rollout_workers=num_rollout_workers,
        rollout_fragment_length=rollout_fragment_length,
        batch_mode="complete_episodes",
        # 集中 critic 的 postprocess_trajectory 需要完整的 other_agent_batches，
        # 与官方 example 一致：关 connectors，用旧 API 栈
        enable_connectors=False,
    )
    config = config.reporting(
        min_sample_timesteps_per_iteration=min_sample_timesteps_per_iteration,
    )
    config = config.resources(num_gpus=int(os.environ.get("RLLIB_NUM_GPUS", "0")))
    config = config.debugging(seed=int(seed))
    # ★ 2026-10-13 修补：关掉 RLlib preprocessor 转换（auto-prep 把 Dict[agent_id → Box]
    #   当 DictFlatteningPreprocessor 处理，会与本框架 per-agent 直传 obs 切片（OrderedDict）
    #   不一致 ⇒ 'two structures don't have the same nested structure'）。
    #   preprocessor_pref 是**属性**（不是 method，默认 "deepmind"）⇒ 直接赋值 None。
    #   效果：rollout_worker.preprocessing_enabled=False ⇒ preprocessors[pid]=None
    #   ⇒ sampler._process_observations 不调 transform（model 直接吃原始 obs slice）。
    #   本框架 actor MLP 自适配 obs dim，与 utils/train.py SAC 路径同款。
    config.preprocessor_pref = None
    return config


def build_ippo_config(**kwargs):
    """IPPO 基线：与 `build_mappo_config` **完全同参**，只把 critic 换回分散（默认）版本。

    用途：作为 MAPPO 的对照臂 ⇒ IPPO vs MAPPO 的唯一差异 = critic 是否集中，
    这样 Δ(MPPO−IPPO) 才能干净地归因到 CTDE，而不是"算法/超参不同"。
    返回的 PPOConfig 不带自定义模型 ⇒ 用默认 `PPOTorchPolicy`（value 只看本楼 obs）。
    """
    kwargs["centralized"] = False
    return build_mappo_config(**kwargs)


def register_mappo_model() -> None:
    """把自定义模型注册进 RLlib ModelCatalog（幂等）。"""
    from ray.rllib.models import ModelCatalog

    ModelCatalog.register_custom_model("mappo_cc_model", CentralizedCriticModel)
