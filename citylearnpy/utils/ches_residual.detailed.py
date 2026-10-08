# -*- coding: utf-8 -*-
# CHESCA-ResMARL 的「残差层」：要不要叠加 RL 修正、怎么挂、每步怎么同步（2026-10-08 从 CHESCA.py 抽出 ✓）
# 用法：`residual = build_residual_layer(agent_config, marl_mode)`，之后
#       `residual.apply_agent_params(params)` → `residual.attach(agent, config, schema_plan)`
#       → 每局 `residual.reset()` → 每步 `residual.bind()` / `residual.sync(actions)`
# [详注-BEGIN]（生成简版时整段删除）
# """为什么抽出来 ✓
#
#   `CHESCA.py` 的定位是**纯 CHESCA 入口**（Java 直接启动它 ⇒ 只跑规则控制 a_final = a_base ✓）；
#   它之所以还留着 ResMARL 分支，只是因为 `CHESCA_ResMARL.py` / `20260914153739.py` /
#   `ablation_resmarl.py` 拿它的 `evaluate()` 当评估内核 ✓（传 --marl_mode multi_agent ✓）。
#
#   于是把"残差"这件事整体挪到这里 ✓ ⇒ CHESCA.py 里只剩**一处开关 + 几行调用** ✓：
#     · 开关        `build_residual_layer(agent_config, marl_mode)`（marl_mode != 'multi_agent' ⇒ 全空操作 ✓）
#     · agent 参数  `residual.apply_agent_params(agent_params)`（resmarl_enabled / α / 掩码 ✓）
#     · 挂载        `residual.attach(agent, config, schema_plan)`（加载 SAC + 换残差器 + 建旁路 env ✓）
#     · 运行期      `residual.reset()` / `residual.bind()` / `residual.sync(actions)`（纯 CHESCA 全是空操作 ✓）
#
#   **懒导入** ✓：`multi_agent_runner_copy`（会拖 Ray / RLlib / torch ✗）只在**残差真的启用时**才 import ✓
#   ⇒ 纯 CHESCA 的启动不再付 Ray 的代价 ✓（原先 CHESCA.py 顶部就 import 它 ✗）。
#
#   行为不变 ✓：搬运是**逐字**的 ✓（错误文案、日志文案、调用顺序、参数都照抄 ✓）；
#   唯一的界面差异是"日志行顺序不变、真值不变" ✓ —— 已用**控制台指纹比对**验证 ✓。
# """
# [详注-END]

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from utils.base import log_console
from utils.ches_config import DEFAULT_RESIDUAL_ALPHA


# 训练任务的模型落盘约定（与 Java 侧 BaseDataService.MARL_CKPT_REL_DIR 一致）
# [详注-BEGIN]（生成简版时整段删除）
#   平台训练子任务的目录是 `<输出根>/<父任务id>-train` ✓，Java 会把 `--checkpoint-dir` 钉成
#   `<该目录>/checkpoints/multi_agent_resume` ✓ ⇒ 评估侧「按训练任务 id 找模型」要用同一相对路径 ✓。
#   放在本模块的理由：本模块正是**加载 SAC 模型**的那一层（见 ChesResidualLayer.attach ✓），
#   且这里只依赖 pathlib ✓（不会把 ray / torch 拖进纯 CHESCA 的启动路径 ✓）。
# [详注-END]
MARL_CKPT_REL_DIR = Path('checkpoints') / 'multi_agent_resume'

# 训练期最优快照的兄弟目录（找不到"最新一版"时才退回它）
MARL_CKPT_BEST_REL_DIR = MARL_CKPT_REL_DIR.parent / 'multi_agent_resume_best'


# 判断一个目录是不是 RLlib checkpoint 目录
# [详注-BEGIN]（生成简版时整段删除）
#   `--train-task-id` 既允许填"任务 id"，也允许直接填"目录" ✓ ⇒ 需要一个判据把
#   「任务目录里的杂物」（日志 / 导出 csv …）和真正的模型目录区分开：
#   只认带 `rllib_checkpoint.json` 的目录 ✓（RLlib 每份 checkpoint 都会写它 ✓）；
#   同时兼容"给的是父目录"这种情况（下一层才是 checkpoint ✓）。
# [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    #   状态 ✓：active（这次要不要叠加 RL ✓）、agent（挂载目标 ✓）、multi_env / multi_agent_ids
    #   （旁路环境 ✓，只在 active 时非空 ✓）、multi_observations（旁路观测 ✓，每步更新 ✓）。
    #   ⚠️ 旁路 multi_env **不参与 KPI** ✗：它只是让 SAC 看到"与主环境对齐的观测" ✓。
    # [详注-END]

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
        # [详注-BEGIN]（生成简版时整段删除）
        #   原先是 CHESCA.evaluate_chesca 里 if/else 两块（约 12 行 ✓），现在合到一处 ✓：
        #     · 启用时：resmarl_enabled=True、α=配置值（缺省 0.15）、可选 action_mask / after_safety ✓
        #     · 不启用：resmarl_enabled=False、α=0.0（**恒等** ⇒ a_final = a_base ✓）
        #   调用点放在"参数组装 if/else 之后" ✓ ⇒ 日志行顺序与原先**完全一致** ✓
        #   （原先残差那几行本来就在各分支末尾 ✓）。
        # [详注-END]
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
        # [详注-BEGIN]（生成简版时整段删除）
        #   ③ 加载预存 Multi-Agent SAC（multi_agent_checkpoint，必填 ✓）
        #   ④ 换上 MultiAgentResidualCorrector（替换 agent.residual_corrector ✓）
        #   ⑤ 创建旁路 multi_env（无 render，仅同步三 agent 观测，不算 KPI ✓）
        #   ⚠️ `multi_agent_runner_copy` 在这里**懒导入** ✓ ⇒ 纯 CHESCA 完全不碰 Ray ✓。
        # [详注-END]
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
        # [详注-BEGIN]（生成简版时整段删除）
        #   为什么需要它 ✓：阶段 5 的 SAC 用**旁路**观测推理 Δa（不是拿 central 的 9 维动作当最终动作 ✓）
        #   ⇒ 每次 predict 之前把最新旁路观测塞进 agent.residual_corrector ✓。
        # [详注-END]
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
