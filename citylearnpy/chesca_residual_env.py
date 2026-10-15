"""CHESCA-在环 残差训练环境（路线 A，2026-10-10 新增）

【本文件的目标】
让 Multi-Agent SAC 在「CHESCA 在环」的语义下训练，而不是像现在这样
「按绝对动作端到端训练、部署时当 Δa 用」（详见 CHESCA-ResMARL重训配置单.md §0.2 项 2）。

合成公式（与评估侧 MultiAgentResidualCorrector.correct 逐项一致，
multi_agent_runner_copy.py:452-553）：

    final = a_base + α · span · (mask ⊙ a_rl) · gate      # additive
          → 安全投影 action_safety_projection.project_building_action()
          → clip(action_low, action_high)

    · a_base —— CHESCA（central_agent=True）每步动作，由本模块的**镜像环境**给出
    · a_rl   —— RLlib SAC 输出的动作（就是 RLlib 采样时选择的动作 ⇒ 直接进 replay buffer ✓）
    · gate   —— P0 门控（checa.residual.config.evaluate_residual_gate，与评估侧同一判据 ✓）

【为什么是这个形态（而不是"包装 RLlib 环境"做合成）】
action_safety_projection.py:283-296 明确记载：把 RLlib 环境**外包**成投影器，会让 RLlib 把
`Dict(agent→Box)` 误当成单策略动作空间 ⇒ SAC 抛 `UnsupportedSpaceException`。
项目给出的分工是「训练用原生 RLlibMultiAgentEnv；评估侧合成后 env.step」。
本模块取折中：**子类化** `_AGENT_ENV_CLS`（保留 Dict 观测/动作空间 ⇒ RLlib 仍按多智能体处理，
沿 ContextRLlibEnv 已有的成功做法），只在 `step()` 里改**动作语义**；
CHESCA 跑在一个与之同步推进的**镜像环境**上，只用来产生 `a_base`。

【镜像环境为什么需要】
CHESCA（Checa）要求 `WrapperEnv`（`buildings_metadata` / `observation_names[0]`）与
**central_agent=True** 的观测格式；而 RLlib 环境强制 `central_agent=False` 且观测被
NormalizedObservationWrapper 归一化、又被 ContextRLlibEnv 追加了上下文维。
直接在 RLlib 观测上拼出 CHESCA 要的输入，归一化与列序都极易错配 ⇒ 用镜像环境最稳。
评估侧本来就是"主环境 + 旁路环境同步推进"的同款做法（sync_multi_env_step ✓）。

【零侵入承诺】
本模块只 **import** 现有模块，不改任何现有文件。
行为开关全部来自 env_config['chesca_residual']（由入口 Multi-agent-train-residual.py 写入）；
未携带该键时本类退化为 `_AGENT_ENV_CLS` 的原行为（不建镜像、不合成）。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from gymnasium import spaces  # noqa: E402  (用于扩展 observation_space 尾部先验维)

# CHESCA-copy 上 sys.path（与 utils/ches_trace.py 同款做法；CHESCA.py 亦如此）
_HERE = Path(__file__).resolve().parent
for _p in (_HERE, _HERE / 'CHESCA-copy'):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from utils.env import _AGENT_ENV_CLS, unwrap_citylearn_env  # noqa: E402
from utils.report import getattr_path, series_value  # noqa: E402
from action_safety_projection import (  # noqa: E402
    SafetyProjectionConfig,
    building_comfort_outage_state,
    project_building_action,
)
from checa.residual.config import (  # noqa: E402
    ResidualConfig,
    evaluate_residual_gate,
    parse_residual_config,
    summarize_gate_reasons,
)


# ============================================================================
# 配置
# ============================================================================
@dataclass
class ChescaResidualTrainConfig:
    """训练期残差配置（只影响训练；评估侧仍读平台的 chesca_agent_config.json）。"""

    enabled: bool = True
    # --- 合成（与 MultiAgentResidualCorrector 同名同义）---
    alpha: float = 0.3
    span: float = 1.0
    residual_mode: str = 'additive'          # additive | blend（仅 A/B 对照）
    action_mask: Dict[str, bool] = field(
        default_factory=lambda: {'dhw': False, 'ele': True, 'tmp': False}
    )
    # --- 安全投影（默认参数与 SafetyProjectionConfig 同源）---
    safety_projection_enabled: bool = True
    safety_projection_params: Dict[str, Any] = field(default_factory=dict)
    # --- P0 门控 ---
    gate_enabled: bool = True
    gate_on_outage: bool = True
    gate_on_soc_bound: bool = True
    gate_soc_margin: float = 0.02
    # --- 可学习门控（gate_mode='learned' 时启用；'binary' = 现有行为）---
    gate_mode: str = 'binary'
    gate_axis: str = 'tmp'
    gate_strength: float = 1.0
    gate_min: float = 0.0
    gate_max: float = 1.0
    gate_params: Dict[str, Any] = field(default_factory=dict)
    gate_policy_path: Optional[str] = None
    # --- 镜像环境（CHESCA 本体）---
    schema: str = 'citylearn_challenge_2023_phase_2_online_evaluation_1'
    episode_time_steps: Optional[int] = None
    output_dir: str = '.'
    agent_params: Dict[str, Any] = field(default_factory=dict)
    # ★ 中和父类 ContextRLlibEnv 的制冷动作重映射（默认 True）。
    #   【为什么必须中和】父类 `_cool_action_apply` 把制冷维当成「a_ref 倍率」二次加工
    #   （P-1 设计，为**纯 MARL** 动作空间整形用）。但残差框架里 a_base = CHESCA 的**原始**
    #   制冷动作（[0,1] 开度），且部署侧 CHESCA 也是原样施加 ⇒ 若主环境再重映射，
    #   连 α=0 都复现不出 CHESCA：实测 soft(5,6)+DHW-fix 由 12.119@643 被改写为
    #   12.690@669（719/719 步制冷维被改写，见 `_diag_alpha_coolremap.py`）。
    #   置 False 可回到旧行为（仅供对照，勿用于正式结论）。
    neutralize_cool_remap: bool = True
    # ★ actor 观测中先验注入形式（v3 §十.1 #4 ablation 用）。
    #   'own_obs'   = 仅原生 obs + ContextRLlibEnv 的 [capacity/identity/a_ref]，与旧行为逐位一致
    #   '+a_ch'     = 额外拼入本栋 CHESCA 当步 a_ch（3 维，DHW/ELE/TMP）
    #   '+neighbors'= 额外拼入**所有**楼的 a_ch（3·n_b 维，self + neighbors）
    #   默认 'own_obs' 保留旧行为 ⇒ 实测前不需要修改任何既有命令。
    actor_prior_mode: str = 'own_obs'
    # 每 CKPT 步打印一次进度 / 诊断（0 = 不打印）
    log_every: int = 0

    # 供 evaluate_residual_gate 复用的 ResidualConfig（口径与评估侧同一份实现 ✓）
    def to_residual_config(self) -> ResidualConfig:
        params = {
            'resmarl_enabled': True,
            'residual_alpha': float(self.alpha),
            'residual_mode': str(self.residual_mode),
            'span': float(self.span),
            'residual_action_mask': dict(self.action_mask),
            'safety_projection_enabled': bool(self.safety_projection_enabled),
            'safety_projection_params': dict(self.safety_projection_params or {}),
            'residual_gate_enabled': bool(self.gate_enabled),
            'residual_gate_outage': bool(self.gate_on_outage),
            'residual_gate_soc_bound': bool(self.gate_on_soc_bound),
            'residual_gate_soc_margin': float(self.gate_soc_margin),
            'residual_gate_mode': str(self.gate_mode),
            'residual_gate_axis': str(self.gate_axis),
            'residual_gate_strength': float(self.gate_strength),
            'residual_gate_min': float(self.gate_min),
            'residual_gate_max': float(self.gate_max),
            'residual_gate_params': (dict(self.gate_params) or None),
            'residual_gate_policy_path': self.gate_policy_path,
        }
        return parse_residual_config(params)

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> 'ChescaResidualTrainConfig':
        cfg = cls()
        for k, v in dict(data or {}).items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg

    def to_dict(self) -> Dict[str, Any]:
        return {
            'enabled': self.enabled,
            'alpha': self.alpha,
            'span': self.span,
            'residual_mode': self.residual_mode,
            'action_mask': dict(self.action_mask),
            'safety_projection_enabled': self.safety_projection_enabled,
            'safety_projection_params': dict(self.safety_projection_params or {}),
            'gate_enabled': self.gate_enabled,
            'gate_on_outage': self.gate_on_outage,
            'gate_on_soc_bound': self.gate_on_soc_bound,
            'gate_soc_margin': self.gate_soc_margin,
            'gate_mode': self.gate_mode,
            'gate_axis': self.gate_axis,
            'gate_strength': self.gate_strength,
            'gate_min': self.gate_min,
            'gate_max': self.gate_max,
            'gate_params': dict(self.gate_params or {}),
            'gate_policy_path': self.gate_policy_path,
            'schema': self.schema,
            'episode_time_steps': self.episode_time_steps,
            'output_dir': str(self.output_dir),
            'agent_params': dict(self.agent_params or {}),
            'neutralize_cool_remap': bool(self.neutralize_cool_remap),
            'actor_prior_mode': str(self.actor_prior_mode),
            'log_every': self.log_every,
        }


# ============================================================================
# 纯函数：合成 + 投影（可单独单测，不依赖 RLlib）
# ============================================================================
def _agent_index(agent_id: Any) -> int:
    """'agent_2' → 2；取不到时给一个大数（排到最后，不改变其余顺序）。"""
    try:
        return int(str(agent_id).split('_')[-1])
    except (TypeError, ValueError):
        return 10 ** 9


def _sorted_agent_ids(agent_ids: Any) -> List[str]:
    """按 agent 下标排序 ⇒ 与 CityLearn 的楼栋顺序（agent_i ↔ buildings[i]）对齐 ✓。"""
    return sorted([str(a) for a in (agent_ids or [])], key=_agent_index)


def mask_vector(n_buildings: int, action_mask: Mapping[str, bool]) -> np.ndarray:
    """把 {dhw,ele,tmp} 掩码展开成 (3n,) 的逐维 0/1。顺序同 CHESCA：[DHW, ELE, TMP] × n。"""
    m = np.zeros(3 * int(n_buildings), dtype=float)
    for b in range(int(n_buildings)):
        if action_mask.get('dhw', False):
            m[3 * b] = 1.0
        if action_mask.get('ele', True):
            m[3 * b + 1] = 1.0
        if action_mask.get('tmp', False):
            m[3 * b + 2] = 1.0
    return m


def compose_action(
    a_base: Sequence[float],
    a_rl: Sequence[float],
    *,
    cfg: ChescaResidualTrainConfig,
    gate: Optional[Sequence[float]] = None,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """按 additive/blend 语义合成 a_base 与 a_rl（不含安全投影，便于单测）。"""
    base = np.asarray(a_base, dtype=float).reshape(-1).copy()
    rl = np.asarray(a_rl, dtype=float).reshape(-1)
    n_b = base.size // 3
    if rl.size < base.size:
        pad = np.zeros(base.size, dtype=float)
        pad[: rl.size] = rl
        rl = pad
    rl = rl[: base.size]
    mask = mask_vector(n_b, cfg.action_mask)
    g = np.ones(base.size, dtype=float) if gate is None else np.asarray(gate, dtype=float).reshape(-1)[: base.size]
    if g.size < base.size:
        pad = np.ones(base.size, dtype=float)
        pad[: g.size] = g
        g = pad

    if str(cfg.residual_mode) == 'blend':
        # 旧行为：把网络输出当**绝对动作**与 a_base 混合（无恒等点，仅对照用）
        target = base + mask * (rl - base)
        final = (1.0 - cfg.alpha) * base + cfg.alpha * target
    else:
        final = base + float(cfg.alpha) * float(cfg.span) * (mask * rl) * g

    return final, {
        'mask': mask,
        'gate': g,
        'scaled': final - base,
    }


def project_action(
    final: np.ndarray,
    buildings: Sequence[Any],
    time_step: int,
    *,
    cfg: ChescaResidualTrainConfig,
    action_low: Optional[Sequence[float]] = None,
    action_high: Optional[Sequence[float]] = None,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """逐栋调用 action_safety_projection.project_building_action（与评估侧同一实现 ✓）。"""
    out = np.asarray(final, dtype=float).reshape(-1).copy()
    proj_cfg = SafetyProjectionConfig(**dict(cfg.safety_projection_params or {}))
    infos: List[Dict[str, Any]] = []
    for b, building in enumerate(list(buildings)):
        start = 3 * b
        if start + 3 > out.size:
            break
        action_names = list(getattr(building, 'active_actions', None) or [])
        if not action_names:
            action_names = ['dhw_storage', 'electrical_storage', 'cooling_device']
        state = building_comfort_outage_state(building, int(time_step))
        low = np.asarray(action_low, dtype=float)[start:start + 3] if action_low is not None else None
        high = np.asarray(action_high, dtype=float)[start:start + 3] if action_high is not None else None
        new_act, info = project_building_action(
            out[start:start + 3], action_names, state, config=proj_cfg,
            action_low=low, action_high=high,
        )
        out[start:start + 3] = new_act
        infos.append(info.__dict__)
    return out, infos


def build_chesca_state(citylearn_env: Any, n_buildings: int) -> Dict[str, Any]:
    """构造 evaluate_residual_gate 需要的 chesca_state（字段名与 Checa 注入的一致 ✓）。"""
    buildings = list(getattr(citylearn_env, 'buildings', None) or [])
    t = int(getattr(citylearn_env, 'time_step', 0) or 0)
    soc: List[float] = []
    min_soc: List[float] = []
    outage: List[bool] = []
    for b in buildings[: int(n_buildings)]:
        es = getattr(b, 'electrical_storage', None)
        s = series_value(getattr_path(b, 'electrical_storage', 'soc'), t, default=float('nan'))
        soc.append(float(s) if np.isfinite(s) else float('nan'))
        dod = series_value(getattr_path(es, 'depth_of_discharge'), t, default=float('nan'))
        # 下界 = 1 - DoD（DoD 读不到时给 0.0，与"硬件下限未知"同义 ⇒ 门控按上界判）
        min_soc.append(float(1.0 - dod) if np.isfinite(dod) else 0.0)
        o = series_value(getattr_path(b, 'power_outage'), t, default=0.0)
        outage.append(bool(np.isfinite(o) and float(o) >= 0.5))
    return {
        'cur_battery_soc': soc,
        'min_battery_soc': min_soc,
        'outage': outage,
        'time_step': t,
    }


# ============================================================================
# CHESCA 镜像（只用来产生 a_base）
# ============================================================================
class _MirrorCfg:
    """create_citylearn_env 需要的最小 config 外形。"""

    def __init__(self, cfg: ChescaResidualTrainConfig):
        self.SCHEMA = cfg.schema
        self.EVAL_SCHEMA = cfg.schema
        self.episode_time_steps = cfg.episode_time_steps
        self.ENABLE_RENDER = False
        self.RENDER_DIR = cfg.output_dir
        self.RENDER_SESSION = 'chesca_residual_mirror'


def mirror_agent_params(cfg: ChescaResidualTrainConfig) -> Dict[str, Any]:
    """镜像 CHESCA agent 的构造参数（纯 CHESCA：显式关掉残差层，否则 a_base 会被污染）。"""
    params = {'tau': 1, 'balance_type': 'C'}
    params.update(dict(cfg.agent_params or {}))
    params['resmarl_enabled'] = False
    params['residual_alpha'] = 0.0
    return params


def build_chesca_mirror(cfg: ChescaResidualTrainConfig):
    """建「纯 CHESCA」镜像环境（残差关闭）⇒ 其 predict() 的输出就是 a_base。"""
    from utils.ches_env import create_citylearn_env
    from rewards.user_reward import SubmissionReward
    from agents.user_agent import SubmissionAgent

    env, wrapper_env = create_citylearn_env(
        _MirrorCfg(cfg), SubmissionReward,
        schema=cfg.schema, episode_time_steps=cfg.episode_time_steps,
    )
    agent = SubmissionAgent(wrapper_env, params=mirror_agent_params(cfg))
    return env, wrapper_env, agent


# ============================================================================
# 环境
# ============================================================================
# ★ 维度级先验注入（v3 §十.1 #9）：只把本栋 a_ch 的**某个子集维**拼进 actor obs。
#   a_ch 单栋 3 维，顺序 = [DHW, ELE, TMP]（与 _act_low[:3] 一致）。
#   默认不启用（actor_prior_mode 默认仍 'own_obs'）⇒ 零侵入，既有三档逐位不变。
_PRIOR_SUBSET_DIMS = {
    '+a_ch_dhw': (0,),
    '+a_ch_ele': (1,),
    '+a_ch_tmp': (2,),
}


class ChescaResidualEnv(_AGENT_ENV_CLS):
    """RLlib 环境：动作语义 = 「CHESCA 基准 + α·残差」，其余行为与 _AGENT_ENV_CLS 相同。

    env_config 需带 `chesca_residual`（dict）才会启用残差；否则退化为父类原行为。
    """

    def __init__(self, env_config: Mapping[str, Any]):
        super().__init__(env_config)
        raw = None
        try:
            raw = dict(env_config).get('chesca_residual')
        except Exception:
            raw = None
        self._r_cfg = ChescaResidualTrainConfig.from_dict(raw) if raw else None
        self._r_enabled = bool(self._r_cfg and self._r_cfg.enabled)
        # ⚠️ 必须按 agent 下标排序：RLlib 的 _agent_ids 可能是 set ⇒ 顺序不定，
        #    而 (3n,) 的拼接顺序是「楼栋顺序」，错序会把残差加到别的楼上（静默错 ✗）
        self._agent_ids_list = _sorted_agent_ids(getattr(self, '_agent_ids', None) or [])
        self._n_b = len(self._agent_ids_list)

        # ★ 残差框架语义修正：父类会把制冷动作当「a_ref 倍率」重映射，而 a_base 是原始动作
        #   ⇒ 必须中和，否则 α=0 都复现不出 CHESCA（见 ChescaResidualTrainConfig 注释）。
        if self._r_enabled and bool(getattr(self._r_cfg, 'neutralize_cool_remap', True)):
            self._neutralize_cool_remap()

        # 观测/动作边界：逐维 low/high（用于 clip，与评估侧同义）
        self._act_low, self._act_high = self._flat_action_bounds()

        # ★ 观测中先验注入形式（v3 §十.1 #4 / #9 ablation）
        #   'own_obs'            = 与旧行为逐位一致（_ctx_extra 不 override）
        #   '+a_ch'              = 拼本栋 a_ch (3 维 = [DHW, ELE, TMP])
        #   '+neighbors'         = 拼全部楼 a_ch (3·n_b 维)
        #   '+a_ch_dhw/_ele/_tmp'= 只拼本栋 a_ch 的**某一维**（v3 §十.1 #9 维度级）
        # ⚠️ 必须放在 _act_low/_act_high 之后：obs space 的先验维 low/high 要复用动作的
        #   真实 low/high（实测 a_ch 第一个分量 DHW 可达 −0.83 ⇒ 用 [0,1] 触发 obs check 报错）
        if self._r_enabled:
            self._prior_mode = str(getattr(self._r_cfg, 'actor_prior_mode', 'own_obs'))
            _allowed = ('own_obs', '+a_ch', '+neighbors') + tuple(_PRIOR_SUBSET_DIMS)
            if self._prior_mode not in _allowed:
                raise ValueError(
                    f"actor_prior_mode 必须是 {' / '.join(repr(x) for x in _allowed)} 之一，"
                    f"收到 {self._prior_mode!r}"
                )
            self._prior_dims = list(_PRIOR_SUBSET_DIMS.get(self._prior_mode, ()))
            if self._prior_mode == 'own_obs':
                self._prior_dim = 0
            elif self._prior_mode == '+a_ch':
                self._prior_dim = 3
            elif self._prior_mode == '+neighbors':
                self._prior_dim = 3 * int(self._n_b)
            else:  # '+a_ch_dhw' / '+a_ch_ele' / '+a_ch_tmp'
                self._prior_dim = len(self._prior_dims)
            if self._prior_dim > 0:
                # 按 agent 下标铺所有栋的动作 low/high（_act_low / _act_high 已是 3·n_b 维）
                if self._prior_mode == '+a_ch' or self._prior_dims:
                    # 每栋看到"自己的 a_ch" = 自己那 3 维的动作 low/high；
                    # 子集模式（#9）再按 _prior_dims 取相应维（DHW/ELE/TMP）
                    own_low = self._act_low[:3] if self._act_low.size >= 3 else np.array([-1.0, -1.0, 0.0])
                    own_high = self._act_high[:3] if self._act_high.size >= 3 else np.array([1.0, 1.0, 1.0])
                    if self._prior_dims:
                        _idx = list(self._prior_dims)
                        own_low = np.asarray(own_low, dtype=np.float32)[_idx]
                        own_high = np.asarray(own_high, dtype=np.float32)[_idx]
                    prior_low = np.asarray(own_low, dtype=np.float32)
                    prior_high = np.asarray(own_high, dtype=np.float32)
                else:  # '+neighbors'
                    prior_low = self._act_low[: self._prior_dim].astype(np.float32)
                    prior_high = self._act_high[: self._prior_dim].astype(np.float32)
                try:
                    _base_sp = dict(self.observation_space)
                except Exception:
                    _base_sp = {}
                if _base_sp:
                    self.observation_space = spaces.Dict({
                        k: spaces.Box(
                            low=np.concatenate([np.asarray(v.low, dtype=np.float32), prior_low]),
                            high=np.concatenate([np.asarray(v.high, dtype=np.float32), prior_high]),
                            dtype=np.float32,
                        )
                        for k, v in _base_sp.items()
                    })
        else:
            self._prior_mode = 'own_obs'
            self._prior_dim = 0
            self._prior_dims = []

        # 镜像（CHESCA）
        self._mirror_env = None
        self._mirror_agent = None
        self._mirror_wrapper = None
        self._mirror_params: Optional[Dict[str, Any]] = None
        self._a_base: Optional[np.ndarray] = None
        self._step_count = 0
        self._last_diag: Dict[str, Any] = {}
        # 可学习门控（gate_mode='learned'）：镜像观测与门控对象（默认 None ⇒ 零影响）
        self._gate = None
        self._mirror_obs_names: Optional[List[str]] = None
        self._m_obs: Any = None
        if self._r_enabled:
            self._build_mirror()
            self._load_gate()

    def _load_gate(self) -> None:
        """gate_mode='learned' 时加载门控（checkpoint 优先，否则用 gate_params）。"""
        cfg = self._r_cfg
        if str(getattr(cfg, 'gate_mode', 'binary')).lower() != 'learned':
            self._gate = None
            return
        path = getattr(cfg, 'gate_policy_path', None)
        if not path:
            self._gate = None
            return
        try:
            from pathlib import Path
            from checa.residual.gate_head import load_gate
            p = Path(path)
            self._gate = load_gate(p) if p.is_file() else None
        except Exception:
            self._gate = None

    # ---- 构造辅助 ----------------------------------------------------
    def _flat_action_bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        lows, highs = [], []
        space = getattr(self, 'action_space', None)
        for aid in self._agent_ids_list:
            box = None
            try:
                box = space[aid]
            except Exception:
                box = None
            if box is None:
                lows.extend([-1.0, -1.0, 0.0])
                highs.extend([1.0, 1.0, 1.0])
                continue
            lows.extend(np.asarray(box.low, dtype=float).reshape(-1)[:3].tolist())
            highs.extend(np.asarray(box.high, dtype=float).reshape(-1)[:3].tolist())
        return np.asarray(lows, dtype=float), np.asarray(highs, dtype=float)

    def _neutralize_cool_remap(self) -> None:
        """把父类 ContextRLlibEnv 的制冷动作重映射置为「不作用」（动作原样进 CityLearn）。

        【依据】父类 `_cool_action_apply` 只在满足
        `(centered 或 any(floor) 或 any(span≠1))` 时改写动作（其余情况原样返回）。
        这里把三条路径同时置为中立值 ⇒ 该函数必走早退分支，动作**逐位不变**：
          · `_cool_centered=False`          —— 关「负荷跟随式」（a → a_ref×(0.75+0.5a)）
          · `_cool_span=[1.0]×n`            —— 关缩放（abs(v-1)≤1e-9 ⇒ _has_span=False）
          · `_cool_floor=[0.0]×n`           —— 关托底（any 为假 ⇒ _has_floor=False）
          · `_cool_dim=[None]×n`            —— 兜底：制冷维下标未知 ⇒ 即便前三条被改也会早退

        这样 a_base 的制冷维与镜像/纯 CHESCA 施加的**逐位一致**（实测 α=0 复现 12.119@643）。
        """
        n_b = int(self._n_b)
        self._cool_centered = False
        self._cool_span = [1.0] * n_b
        self._cool_floor = [0.0] * n_b
        self._cool_dim = [None] * n_b

    # ---- ★ 先验注入（v3 §十.1 #4） -----------------------------------------
    def _prior_only_extra(self, agent_id: str):
        """只算 a_ch prior 部分（不重复 parent extra）；reset 路径下重 aug 时用它。"""
        if not self._r_enabled or self._prior_dim == 0 or self._a_base is None:
            return None
        try:
            i = self._agent_ids_list.index(agent_id)
        except ValueError:
            return None
        n_b = int(self._n_b)
        if self._prior_mode == '+a_ch':
            return np.asarray(self._a_base[3 * i:3 * i + 3], dtype=np.float32)
        if self._prior_dims:  # '+a_ch_dhw' / '+a_ch_ele' / '+a_ch_tmp'（v3 §十.1 #9）
            own = np.asarray(self._a_base[3 * i:3 * i + 3], dtype=np.float32)
            return own[list(self._prior_dims)].astype(np.float32)
        else:  # '+neighbors'
            return np.asarray(self._a_base[: 3 * n_b], dtype=np.float32).copy()

    def _ctx_extra(self, agent_id: str) -> np.ndarray:
        """永远只返回 parent extra（cap + identity + a_ref）—— **不**加 a_ch 先验。

        a_ch 先验由 reset() 在 _a_base 设置后**单独重做**一次 obs 拼接来加；
        这样无论 reset 是第几次被调（_a_base 可能已设），行为都是
        「super reset 一次 _ctx_augment（加 parent extra）+ 我手动加 a_ch（一次）」，
        不会被叠加两次或漏加。

        ⚠️ 'own_obs' 模式 ``self._prior_dim == 0`` ⇒ 我手动那段跳过 ⇒ 行为与父类一致 ✓
        """
        return super()._ctx_extra(agent_id)

    def _build_mirror(self) -> None:
        cfg = self._r_cfg
        self._mirror_env, self._mirror_wrapper, self._mirror_agent = build_chesca_mirror(cfg)
        self._mirror_params = mirror_agent_params(cfg)
        # 停电序列必须与主环境一致（主环境的 reset 已被 utils.env 钉了种子 ✓）
        self._pin_outage_seed(self._mirror_env)
        # 门控特征要用 CHESCA 口径的观测名（'non_shiftable_load_b' 等）⇒ 从镜像环境取
        names = getattr(self._mirror_env, 'observation_names', None)
        if names and isinstance(names[0], (list, tuple)):
            names = names[0]
        self._mirror_obs_names = list(names) if names else None

    @staticmethod
    def _pin_outage_seed(env: Any, seed: int = 90000) -> None:
        """把停电模型种子钉成固定值（与 utils.env.set_power_outage_seed 同值 ✓）。

        ⚠️ 刻意**不复用** utils.env.set_power_outage_seed：它内部走 unwrap_citylearn_env，
        而镜像环境是**裸 CityLearnEnv / WrapperEnv**（没有 .env 链）⇒ 会静默返回 None、
        一个种子都不设 ✗（镜像与主环境的停电时刻就会错位 ✗）。
        """
        ce = getattr(env, 'unwrapped', env)
        for b in getattr(ce, 'buildings', None) or []:
            model = getattr(b, 'stochastic_power_outage_model', None)
            if model is not None:
                model.random_seed = int(seed)

    # ---- 镜像 agent 的跨-episode 状态重置 ---------------------------------
    def _rebuild_mirror_agent(self) -> None:
        """每个 episode 重建镜像 CHESCA agent（彻底清空内部累积状态）。

        【为什么重建而不是只清列表】
        镜像 Checa 的跨-episode 内部状态不止「历史缓存」一处：
          · Checa.elec_consumption_history / ns_load_history / dist_ns_history /
            price_history / elec_consumption_prediction_history …
          · ForecastAgent.hourly_expected_values（每步 `np.mean` 消费，桶不断变大）
          · ForecastAgent.hist_data（每个日末 `np.stack` + **在线 XGBoost `fit_data` 重训全量历史**）
          · TimeSeriesEnsemble 里在线 XGBoost 的已训练状态
        逐项枚举既脆弱又漏；而 CityLearn 基类 `Agent.reset()`（citylearn/agents/base.py:234）
        只重置 `self.__actions`，完全不管这些 ⇒ 多个 episode 复用同一 agent 时状态只增不减，
        单步成本随累计步数上升（O(n²)），实测单轮 25s → 324s 线性爬升。

        重建 agent = 「每 episode 一个全新的 CHESCA」，与官方评估（每次 evaluate 新建 agent，
        只跑一个 episode）语义一致；单 episode 下与旧行为逐位等价，故不影响 α=0 自检等单集口径。
        """
        if self._mirror_wrapper is None:
            return
        try:
            from agents.user_agent import SubmissionAgent
            self._mirror_agent = SubmissionAgent(
                self._mirror_wrapper, params=dict(self._mirror_params or {})
            )
            # 观测名保持不变（来自 env，不随 agent 重建而变）
        except Exception:
            # 兜底：至少清掉最重的几项 O(n) 历史（见 _reset_mirror_episode_state）
            self._reset_mirror_episode_state()

    def _reset_mirror_episode_state(self) -> None:
        """清空镜像 CHESCA（Checa）的跨-episode 累积历史（重建失败时的兜底）。

        【为什么必须做】
        Checa 的历史缓存（`elec_consumption_history` / `ns_load_history` /
        `dist_ns_history` / `price_history` / `elec_consumption_prediction_history` 等）
        只在 `Checa.__init__` 里建立；而 CityLearn 基类 `Agent.reset()`
        （citylearn/agents/base.py:234）只重置 `self.__actions`，**不会清这些列表**。

        ⇒ 多个 episode 复用同一个 mirror agent 时，历史只增不减；而 `Checa.predict()`
        的 refine 阶段每步都会 `np.array(self.elec_consumption_history[b]).mean()/.std()`
        （checa/agent.py:1183-1184）⇒ 单步成本 O(累计步数) ⇒ 整段训练 O(n²)，越跑越慢
        （实测 2026-10-12：残差 IPPO 单轮 25s → 324s 线性爬升）。跨-episode 的历史还会
        污染 refine 的「负荷应维持水平」参考值 ⇒ 决策口径也不干净。

        【语义】
        这里在每个 episode 开始时把上述列表恢复为初始状态，等价于「每 episode 一个全新的
        CHESCA agent」，与官方评估（每 episode 重建 agent）一致。单 episode 下该重置不影响
        结果（首步历史本来就是空）⇒ 对 α=0 自检等单集口径无影响。
        """
        ag = self._mirror_agent
        if ag is None:
            return
        n_b = int(self._n_b)
        factories = (
            ('elec_consumption_history', lambda: [[] for _ in range(n_b)]),
            ('elec_consumption_history_per_hour', lambda: [[[] for _ in range(24)] for _ in range(n_b)]),
            ('ns_load_history', lambda: [[] for _ in range(n_b)]),
            ('elec_consumption_prediction_history', lambda: [[] for _ in range(n_b)]),
            ('dist_ns_history', list),
            ('price_history', list),
            ('_rebound_steps_left', lambda: [0 for _ in range(n_b)]),
            ('_rebound_ref', lambda: [0.0 for _ in range(n_b)]),
        )
        for name, make in factories:
            if hasattr(ag, name):
                try:
                    setattr(ag, name, make())
                except Exception:
                    pass
        if hasattr(ag, 'seen_steps'):
            try:
                ag.seen_steps = 0
            except Exception:
                pass

    # ---- RLlib 接口 ---------------------------------------------------
    def reset(self, *, seed: Optional[int] = None, options: Optional[Mapping[str, Any]] = None):
        obs, info = super().reset(seed=seed, options=options)
        self._step_count = 0
        if not self._r_enabled:
            return obs, info
        self._pin_outage_seed(self._mirror_env)
        # ★ 修复 O(n²)：官方 Agent.reset() 不清 Checa 的内部状态（历史缓存 + ForecastAgent
        #    的 hist_data / hourly_expected_values + 在线 XGBoost 已训状态）⇒ 每 episode 重建 agent
        self._rebuild_mirror_agent()
        m_obs, _ = self._mirror_env.reset()
        self._m_obs = m_obs
        self._a_base = self._flat(self._mirror_agent.register_reset(m_obs))
        # ★ v3 §十.1 #4：reset 路径下 super().reset() 先于 _a_base 赋值 ⇒ 父类 _ctx_augment
        #   调 _ctx_extra 时 _a_base 还是 None ⇒ obs 尾部先验维被填 0 ⇒ 第一帧 obs 没有 a_ch。
        #   修：_a_base 设完后**重做** obs 的先验维拼接（_prior_dim=0 时跳过 ⇒ own_obs 模式零开销）。
        #   注意：只补 prior 部分，**不重做父类 _ctx_extra**（否则 parent extra 会被加两次）。
        if self._prior_dim > 0:
            for _k in list(obs.keys()):
                _p = self._prior_only_extra(_k)
                if _p is not None:
                    obs[_k] = np.concatenate(
                        [np.asarray(obs[_k], dtype=np.float32), _p]
                    ).astype(np.float32)
        return obs, info

    def step(self, action_dict: Mapping[str, Any]):
        if not self._r_enabled or self._a_base is None:
            return super().step(action_dict)

        a_rl = self._flatten_rl(action_dict)
        base = self._a_base
        n_b = self._n_b

        _ce = unwrap_citylearn_env(self) or getattr(self, 'env', None)
        gate, reasons = evaluate_residual_gate(
            n_b, self._r_cfg.to_residual_config(),
            build_chesca_state(_ce, n_b),
        )
        final, diag = compose_action(base, a_rl, cfg=self._r_cfg, gate=gate)
        # 可学习门控（gate_mode='learned'）：对合成动作的指定轴再乘一个状态相关档位 g_b(s)。
        # 默认 'binary' ⇒ 返回 None ⇒ final 不变（与现有链路逐位一致 ✓）
        g_diag: Dict[str, Any] = {}
        if str(getattr(self._r_cfg, 'gate_mode', 'binary')).lower() == 'learned':
            try:
                from checa.residual.gate_head import maybe_apply_learned_gate
                ce = unwrap_citylearn_env(self) or getattr(self, 'env', None)
                m_obs = self._m_obs
                m_obs_flat = None
                if isinstance(m_obs, (list, tuple)) and len(m_obs) == 1:
                    m_obs_flat = m_obs[0]
                elif m_obs is not None:
                    m_obs_flat = m_obs
                gated, g_diag = maybe_apply_learned_gate(
                    final, self._r_cfg,
                    observations=m_obs_flat, observation_names=self._mirror_obs_names,
                    chesca_state=build_chesca_state(ce, n_b) if ce is not None else None,
                    action_low=self._act_low, action_high=self._act_high, gate=self._gate,
                )
                if gated is not None:
                    final = gated
            except Exception:
                g_diag = {}
        proj_infos: List[Dict[str, Any]] = []
        if bool(self._r_cfg.safety_projection_enabled):
            buildings = list(getattr(self, 'buildings', None) or [])
            t = int(getattr(self, 'time_step', 0) or 0)
            final, proj_infos = project_action(
                final, buildings, t, cfg=self._r_cfg,
                action_low=self._act_low, action_high=self._act_high,
            )
        final = np.clip(final, self._act_low, self._act_high)
        self._last_diag = {
            'alpha': float(self._r_cfg.alpha),
            'gate_reason': summarize_gate_reasons(list(reasons)),
            'delta_abs_max': float(np.max(np.abs(final - base))) if final.size else 0.0,
            'projected': bool(proj_infos),
            'mode': str(self._r_cfg.residual_mode),
            'gate_mode': str(getattr(self._r_cfg, 'gate_mode', 'binary')),
            'gate_learned_diag': dict(g_diag or {}),
            **{k: v for k, v in diag.items() if k not in ('mask', 'gate', 'scaled')},
        }

        composed = self._to_action_dict(final)
        obs, rew, term, trunc, info = super().step(composed)

        # 镜像与主环境用**同一份合成动作**推进 ⇒ 下一步的 a_base 状态对齐 ✓
        m_obs, *_ = self._mirror_env.step([final.tolist()])
        self._m_obs = m_obs
        self._a_base = self._flat(self._mirror_agent.predict(m_obs))
        self._step_count += 1

        # ★ v3 §十.1 #4：super step 返回的 obs 是父类 _ctx_augment 后的结果（只含 parent extra），
        #   在 +a_ch / +neighbors 模式下需要把 a_ch 先验维拼到 obs 尾部，与 reset 路径一致。
        #   必须在 self._a_base 更新**之后**做（保证用的是新一步的 a_ch），
        #   且与 reset 路径用同一种 _prior_only_extra（防止重复加 parent extra）。
        if self._prior_dim > 0:
            for _k in list(obs.keys()):
                _p = self._prior_only_extra(_k)
                if _p is not None:
                    obs[_k] = np.concatenate(
                        [np.asarray(obs[_k], dtype=np.float32), _p]
                    ).astype(np.float32)

        if self._r_cfg.log_every and (self._step_count % int(self._r_cfg.log_every) == 0):
            d = self._last_diag
            print(f'[ResidualEnv] step={self._step_count} alpha={d.get("alpha")} '
                  f'mode={d.get("mode")} |Δa|max={d.get("delta_abs_max"):.4f} '
                  f'gate={d.get("gate_reason")}', flush=True)
        return obs, rew, term, trunc, info

    # ---- 形态转换 ----------------------------------------------------
    @staticmethod
    def _flat(actions: Any) -> np.ndarray:
        """CHESCA/np 的嵌套动作 → (3n,) 一维。"""
        arr = np.asarray(actions, dtype=float)
        return arr.reshape(-1)

    def _flatten_rl(self, action_dict: Mapping[str, Any]) -> np.ndarray:
        """{agent_i: a_rl} → (3n,)，顺序按 agent 下标（与 CHESCA 的 3n 拼接一致 ✓）。"""
        out = np.zeros(3 * self._n_b, dtype=float)
        for aid, vec in dict(action_dict or {}).items():
            try:
                b = int(str(aid).split('_')[-1])
            except (TypeError, ValueError):
                continue
            if not (0 <= b < self._n_b):
                continue
            v = np.asarray(vec, dtype=float).reshape(-1)
            out[3 * b: 3 * b + min(3, v.size)] = v[:3]
        return out

    def _to_action_dict(self, flat: np.ndarray) -> Dict[str, np.ndarray]:
        """(3n,) → {agent_i: [DHW, ELE, TMP]}（RLlib 动作字典）。"""
        out: Dict[str, np.ndarray] = {}
        for b, aid in enumerate(self._agent_ids_list):
            out[aid] = np.asarray(flat[3 * b: 3 * b + 3], dtype=np.float32)
        return out
