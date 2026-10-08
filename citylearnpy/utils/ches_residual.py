# -*- coding: utf-8 -*-
# ⚠️ 本文件是**精简注释版**（由 `_gen_marl_split.py` 生成 ✓）：全部「详注块」已整段删除 ✓，
#    代码与同目录的 `X.detailed.py` **逐字相同** ✓（AST 一致 ⇒ 行为一致 ✓）。
#    **改注释请改 `.detailed.py` 那份** ✗（本文件每次生成都会被覆盖 ✗），改完重跑 `_gen_marl_split.py` ✓。
# CHESCA-ResMARL 的「残差层」：要不要叠加 RL 修正、怎么挂、每步怎么同步（2026-10-08 从 CHESCA.py 抽出 ✓）
# 用法：`residual = build_residual_layer(agent_config, marl_mode)`，之后
#       `residual.apply_agent_params(params)` → `residual.attach(agent, config, schema_plan)`
#       → 每局 `residual.reset()` → 每步 `residual.bind()` / `residual.sync(actions)`

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from utils.base import log_console
from utils.ches_config import DEFAULT_RESIDUAL_ALPHA


# 训练任务的模型落盘约定（与 Java 侧 BaseDataService.MARL_CKPT_REL_DIR 一致）
MARL_CKPT_REL_DIR = Path('checkpoints') / 'multi_agent_resume'

# 训练期最优快照的兄弟目录（找不到"最新一版"时才退回它）
MARL_CKPT_BEST_REL_DIR = MARL_CKPT_REL_DIR.parent / 'multi_agent_resume_best'


# 判断一个目录是不是 RLlib checkpoint 目录
def is_checkpoint_dir(path: Any) -> bool:
    p = Path(path)
    if not p.is_dir():
        return False
    if (p / 'rllib_checkpoint.json').is_file():
        return True
    return any(sub.is_dir() and (sub / 'rllib_checkpoint.json').is_file() for sub in p.iterdir())


# 残差层工具类（CHESCA-ResMARL 的全部"脏活"都在这里 ✓）
class ChesResidualLayer:
    # 残差层：开关 + 校验 + agent 参数 + 挂载 + 运行期观测同步。

    def __init__(self, agent_config: Optional[Dict[str, Any]], marl_mode: str = 'none', log=None):
        self.agent_config: Dict[str, Any] = dict(agent_config or {})
        self.marl_mode = marl_mode
        # 只有显式 multi_agent 才启用（纯 CHESCA 入口恒为 none ✓）
        self.active = (marl_mode == 'multi_agent')
        self.log = log or log_console
        self.agent: Any = None
        self.multi_env: Any = None
        self.multi_agent_ids: List[str] = []
        self.multi_observations: Dict[str, Any] = {}
        if self.active:
            self._require_checkpoint()

    # 启用残差时必须给出训练好的 Multi-Agent SAC checkpoint（文案与原先逐字一致 ✓）
    def _require_checkpoint(self) -> str:
        ckpt = str(self.agent_config.get('multi_agent_checkpoint') or '').strip()
        if not ckpt:
            raise ValueError(
                '启用 CHESCA-ResMARL 时必须配置 multi_agent_checkpoint。'
                '本地评估不再现场训练 Multi-Agent SAC，请先用 Multi-agent.py 训练并填写路径。'
            )
        return ckpt

    # 把「RL 修正」的开关与强度写进 agent 参数（纯 CHESCA ⇒ 恒 False / α=0 ✓）
    def apply_agent_params(self, agent_params: Dict[str, Any]) -> Dict[str, Any]:
        if self.active:
            agent_params['resmarl_enabled'] = True
            agent_params['residual_alpha'] = self.agent_config.get(
                'residual_alpha', DEFAULT_RESIDUAL_ALPHA)
            self.log(f"已加载 CHESCA-ResMARL residual_alpha={agent_params['residual_alpha']}")
            if self.agent_config.get('residual_action_mask') is not None:
                agent_params['residual_action_mask'] = self.agent_config['residual_action_mask']
            if self.agent_config.get('resmarl_after_safety') is not None:
                agent_params['resmarl_after_safety'] = self.agent_config['resmarl_after_safety']
        else:
            agent_params['resmarl_enabled'] = False
            agent_params['residual_alpha'] = 0.0
        return agent_params

    # 阶段 0-③～⑤：加载 SAC、换上残差器、建旁路 multi_env（纯 CHESCA ⇒ 空操作 ✓）
    def attach(self, agent, config, schema_plan: Optional[dict] = None):
        self.agent = agent
        if not self.active:
            return None
        from multi_agent_runner_copy import setup_chesca_multi_agent_residual

        self.multi_env, self.multi_agent_ids, _ = setup_chesca_multi_agent_residual(
            agent,
            self.agent_config,
            config,
            self.log,
            schema_plan=schema_plan,
        )
        return self.multi_env

    # 每局开始：旁路环境也 reset（纯 CHESCA ⇒ 空操作 ✓）
    def reset(self) -> Dict[str, Any]:
        self.multi_observations = {}
        if self.multi_env is not None:
            self.multi_observations, _ = self.multi_env.reset()
        return self.multi_observations

    # 把旁路环境的三 agent 观测交给「RL 修正器」（predict 阶段 5 用 ✓；纯 CHESCA ⇒ 空操作 ✓）
    def bind(self) -> None:
        if self.active and self.agent is not None and hasattr(self.agent, 'residual_corrector'):
            self.agent.residual_corrector.set_multi_observations(self.multi_observations)

    # 主循环里用同一个 a_final 推进旁路环境，取回下一步的三 agent 观测（纯 CHESCA ⇒ 空操作 ✓）
    def sync(self, actions: Sequence) -> Dict[str, Any]:
        if self.multi_env is not None:
            from multi_agent_runner_copy import sync_multi_env_step

            self.multi_observations = sync_multi_env_step(
                self.multi_env, actions, self.multi_agent_ids
            )
        return self.multi_observations


# 建残差层（与 utils/ches_env、utils/ches_trace 的 build_* 同一写法 ✓）
def build_residual_layer(agent_config: Optional[Dict[str, Any]],
                         marl_mode: str = 'none',
                         log=None) -> ChesResidualLayer:
    return ChesResidualLayer(agent_config, marl_mode, log=log)
