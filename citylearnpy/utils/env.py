# ⚠️ 本文件是**精简注释版**（由 `_gen_marl_split.py` 生成 ✓）：全部「详注块」已整段删除 ✓，
#    代码与同目录的 `X.detailed.py` **逐字相同** ✓（AST 一致 ⇒ 行为一致 ✓）。
#    **改注释请改 `.detailed.py` 那份** ✗（本文件每次生成都会被覆盖 ✗），改完重跑 `_gen_marl_split.py` ✓。
# 注：本模块原名 utils/env.py（2026-10-07 utils 整理：按功能改名，内容未改 ✓）
from __future__ import annotations

# -*- coding: utf-8 -*-



from typing import Any, Optional


# RLlib 部分版本 compute_single_action 返回 (action, state, info)，只取动作本体 ✓
def unwrap_action(action: Any) -> Any:
    if isinstance(action, tuple) and len(action) > 0:
        return action[0]
    return action


# 从 RLlibMultiAgentEnv 逐层 .env 找到带 buildings/reward_function 的 CityLearnEnv ✓
def unwrap_citylearn_env(rllib_env: Any) -> Optional[Any]:
    env = getattr(rllib_env, 'env', None)
    for _ in range(6):
        if env is None:
            return None
        if hasattr(env, 'reward_function') and hasattr(env, 'buildings'):
            return env
        env = getattr(env, 'env', None)
    return None

# ============================================================================
# ==== 段：context_env（原 utils/context_env.py ✓）====



import numpy as np
from citylearn.wrappers import RLlibMultiAgentEnv
from gymnasium import spaces



# （2026-10-07 更新 ✓）原先 Multi-agent.py 里有一层老名字 `_unwrap_citylearn_env` 指向本函数 ✓；
#   这个老名字已删 ✗ ⇒ 那 20+ 处调用点与诊断脚本统一改用**新名字** `ma.unwrap_citylearn_env` ✓（同一个东西 ✓）。


# 本步热容量 [kWh/步] = 额定电功率 × 当前 COP，读不到返回 0.0 ✓
def _cool_thermal_capacity(building, nominal_power, idx) -> float:
    try:
        npw = float(nominal_power or 0.0)
        if npw <= 0.0:
            return 0.0
        tout = np.asarray(getattr(getattr(building, 'weather', None),
                                  'outdoor_dry_bulb_temperature', []), dtype=float).ravel()
        t = min(max(int(idx), 0), tout.size - 1) if tout.size else 0
        to = float(tout[t]) if tout.size else 25.0
        cop = float(np.asarray(building.cooling_device.get_cop(to, heating=False)).reshape(-1)[0])
        return max(0.0, npw * cop)
    except Exception:
        return 0.0


# "刚够用"的开度 a_ref = 理想负荷 ÷ 本步热容量，范围 0~1；读不到就返回 0.0 ✓
def _ideal_a_ref(building, nominal_power, idx) -> float:
    try:
        ideal = np.asarray(getattr(getattr(building, 'energy_simulation', None),
                                   'cooling_demand_without_control', []), dtype=float).ravel()
        cap = _cool_thermal_capacity(building, nominal_power, idx)
        if not ideal.size or cap <= 1e-9:
            return 0.0
        t = min(max(int(idx), 0), ideal.size - 1)
        return float(min(max(ideal[t] / cap, 0.0), 1.0))
    except Exception:
        return 0.0




# =============================================================================
# 给每个 agent 的观测追加"这栋是谁"的信息 —— 制冷能力比值 + 楼栋身份（one-hot）
OBS_CONTEXT_ENABLE = True
OBS_CONTEXT_CAPACITY = True       # ① 制冷能力比值维度
OBS_CONTEXT_IDENTITY = True       # ② 楼栋 one-hot 维度
# ③ Step2B（2026-09-29）：算出这一步"刚够用"的开度 a_ref（每步现算，由物理量推出）
OBS_CONTEXT_A_REF = True

# =============================================================================
# C′-4「制冷动作下界（floor）」：实测证明不行、已改回；这里只留结论与判据
COOL_FLOOR_ENABLE = True                   # floor 托举总开关（**必须开**：floor=0 + 纯缩放会早期自锁）
# Step 1（2026-09-29）：**三栋统一**，不再按楼栋查表 —— 见下方"三栋共用同一条映射"的说明块。
COOL_REMAP_FLOOR = 0.05                    # 所有楼栋共用同一动作下界；**必须明显低于中立开度 0.15**
COOL_FLOOR_UNTIL = 0                       # 0 = 不衰减（全程保持 floor；衰减会在撤除后立刻打回死锁）
COOL_FLOOR_SCALE = 1.0                     # 运行时衰减系数 0~1；训练循环每轮更新，评估前按 best_meta 恢复

# -----------------------------------------------------------------------------
# 动作映射（SPAN）：为什么用"乘一个倍率"而不是"砍一个下界"
COOL_SPAN_ENABLE = True                    # 动作缩放总开关
COOL_REMAP_SPAN = 0.40                     # 所有楼栋共用同一缩放系数（1.0 = 不缩放）

# =============================================================================
# P-1（2026-09-29）：把映射的「中立点」由**固定开度**改为**逐时负荷跟随**
COOL_LOAD_CENTERED_ENABLE = True  # P-1 总开关（True = 真实施加的开度以"本步刚够用"为中心）
# 倍率区间取 ±25%（[0.75, 1.25]）：实测三栋实际用到的倍率是 0.77 / 1.05 / 1.00
COOL_LOAD_MIN_FRAC = 0.75  # a=0 ⇒ 0.75×a_ref（比"刚够用"最多少吹 25%）
# P-2（2026-09-29）：上沿 1.25 → 1.10 —— ⚠️ **已实测证明不行，2026-09-30 改回 1.25**
COOL_LOAD_MAX_FRAC = 1.25  # a=1 ⇒ 1.25×a_ref（比"刚够用"最多多吹 25%，用来提前预冷）
# ---- P-6′(i)（2026-09-30）：把"a_ref 正好是 0"与"a_ref 读不到"分开处理 ----
#   事故（7c7ae2b2 trace 逐组分解，脚本 _q_b2cold.py + _q_fallback.py）：B2 低温步 99 步里
COOL_LOAD_NOLOAD_MAX = 0.08  # a_ref 正好为 0 时：真实施加 = 0.08×a（a=0.5 时约 0.04）


# -----------------------------------------------------------------------------
# Step 1（2026-09-29）：动作换算不再**按楼栋各用一套**，三栋共用同一条映射


class ContextRLlibEnv(RLlibMultiAgentEnv):
    """P6-A：在 RLlibMultiAgentEnv 之上，为每个 agent 的观测追加 [负载率, 身份one-hot]。

    · 观测空间同步扩展（RLlib 会用 self.observation_space 建模型输入层）；
    · 负载率取「本楼」的实时 cooling_demand / nominal_power，按步刷新；
    · 身份 one-hot 固定不变，仅用于让策略知道"这是第几栋楼"。
    """

    # 初始化环境包装：记住每栋的 id 与额定制冷能力（换算成 0~1 的比值），并准备好"额外观测"开关 ✓
    def __init__(self, env_config):
        super().__init__(env_config)
        self._ctx_ids = list(getattr(self, '_agent_ids', None) or [])
        self._ctx_n_b = len(self._ctx_ids)
        # 每栋的额定制冷能力（nominal_power）→ 换算成 0~1 的比值（①，常量 ✓）
        _caps = []
        ce = self.env.unwrapped                      # 最内层 CityLearnEnv
        for b in getattr(ce, 'buildings', []) or []:
            _c = 0.0
            try:
                _c = float(getattr(getattr(b, 'cooling_device', None), 'nominal_power', 0.0) or 0.0)
            except (TypeError, ValueError):
                _c = 0.0
            _caps.append(_c)
        _mx = max(_caps) if _caps and max(_caps) > 1e-9 else 1.0
        self._ctx_cap_ratio = [min(max(c / _mx, 0.0), 1.0) for c in _caps]
        self._ctx_nominal = list(_caps)                        # 每栋额定电功率（Step2 用）
        self._ctx_buildings = list(getattr(ce, 'buildings', []) or [])
        # 新增维度数 = 能力比值(0/1 维) + 身份(n_b 维)
        n_extra = (1 if OBS_CONTEXT_CAPACITY else 0) + \
                  (self._ctx_n_b if OBS_CONTEXT_IDENTITY else 0) + \
                  (1 if OBS_CONTEXT_A_REF else 0)
        self._ctx_n_extra = n_extra
        if n_extra > 0:
            try:
                base_sp = dict(self.observation_space)
            except Exception:
                base_sp = {}
            if base_sp:
                self.observation_space = spaces.Dict({
                    k: spaces.Box(
                        low=np.concatenate([np.asarray(v.low, dtype=np.float32),
                                            np.zeros(n_extra, dtype=np.float32)]),
                        high=np.concatenate([np.asarray(v.high, dtype=np.float32),
                                             np.ones(n_extra, dtype=np.float32)]),
                        dtype=np.float32,
                    )
                    for k, v in base_sp.items()
                })
        # ---- C′-4：制冷动作下界（Step 1 起是**全局一个数**，见文件顶部 COOL_REMAP_FLOOR 处）----
        #   self._cool_dim[i]   = 第 i 个 agent 的动作向量里 'cooling_device' 的下标
        #   self._cool_floor[i] = 该楼制冷动作的下界（0 = 不做换算，原样使用）
        self._cool_dim = []
        self._cool_floor = []
        self._cool_span = []
        # ---- P-1（2026-09-29）：跟着负荷走的映射（"中间值"= 本步刚够用的 a_ref；见文件顶部说明）----
        self._cool_centered = bool(COOL_LOAD_CENTERED_ENABLE)
        self._cool_load_min_frac = float(COOL_LOAD_MIN_FRAC)
        self._cool_load_max_frac = float(COOL_LOAD_MAX_FRAC)
        self._cool_load_noload_max = float(COOL_LOAD_NOLOAD_MAX)
        try:
            _blist = list(getattr(ce, 'buildings', []) or [])
            for _i in range(self._ctx_n_b):
                _names = list(getattr(_blist[_i], 'active_actions', None) or []) \
                    if _i < len(_blist) else []
                self._cool_dim.append(_names.index('cooling_device')
                                      if 'cooling_device' in _names else None)
                # Step 1：全局一个数（不再按楼栋查表）⇒ 三栋拿到同一条映射
                _fl = float(COOL_REMAP_FLOOR) if COOL_FLOOR_ENABLE else 0.0
                self._cool_floor.append(min(max(_fl, 0.0), 0.99))
                # 动作缩放系数（1.0 = 不缩放）。用线性缩放把"中立开度"放到 a=0.5，
                #   也就是 tanh 梯度最大的地方（学得最快）—— 动机与实测见文件顶部 COOL_REMAP_SPAN 处。
                _sp = 1.0
                if COOL_SPAN_ENABLE:
                    try:
                        _sp = float(COOL_REMAP_SPAN)
                    except (TypeError, ValueError):
                        _sp = 1.0
                self._cool_span.append(min(max(_sp, 0.0), 1.0))
        except Exception:
            self._cool_dim = []
            self._cool_floor = []
            self._cool_span = []

    # ---- 拼接逻辑 ----------------------------------------------------------
    # 按开关把该栋的附加特征（制冷能力比 / 身份 one-hot / 刚够用开度 a_ref ✓）拼成一个数组 ✓
    def _ctx_extra(self, agent_id: str) -> np.ndarray:
        if self._ctx_n_extra <= 0:
            return np.zeros(0, dtype=np.float32)
        try:
            i = self._ctx_ids.index(agent_id)
        except ValueError:
            i = 0
        parts = []
        if OBS_CONTEXT_CAPACITY:
            cap = self._ctx_cap_ratio[i] if i < len(self._ctx_cap_ratio) else 1.0
            parts.append(np.array([cap], dtype=np.float32))
        if OBS_CONTEXT_IDENTITY:
            onehot = np.zeros(self._ctx_n_b, dtype=np.float32)
            if 0 <= i < self._ctx_n_b:
                onehot[i] = 1.0
            parts.append(onehot)
        if OBS_CONTEXT_A_REF:
            # Step2B：把「本步理想负荷所需开度」喂给策略（见文件顶部 OBS_CONTEXT_A_REF 注释）。
            _ref = 0.0
            try:
                _b = self._ctx_buildings[i] if i < len(self._ctx_buildings) else None
                if _b is not None:
                    _npw = self._ctx_nominal[i] if i < len(self._ctx_nominal) else 0.0
                    _ref = _ideal_a_ref(_b, _npw, int(getattr(_b, 'time_step', 0) or 0))
            except Exception:
                _ref = 0.0
            parts.append(np.array([_ref], dtype=np.float32))
        return np.concatenate(parts).astype(np.float32) if parts else np.zeros(0, np.float32)

    # 把额外信息拼进每栋的观测里（旧的 obs dict → 新的 obs dict ✓）✓
    def _ctx_augment(self, observations):
        if self._ctx_n_extra <= 0 or not isinstance(observations, dict):
            return observations
        out = {}
        for k, o in observations.items():
            try:
                base = np.asarray(o, dtype=np.float32)
                out[k] = np.concatenate([base, self._ctx_extra(k)]).astype(np.float32)
            except Exception:
                out[k] = o
        return out

    # 重置环境；返回前把额外信息拼进观测 ✓
    def reset(self, *, seed=None, options=None):
        obs, info = super().reset(seed=seed, options=options)
        return self._ctx_augment(obs), info

    # 这一步第 i 栋"刚好够用"的制冷开度 a_ref（与奖励用的是同一个函数 _ideal_a_ref ✓）
    def _cool_a_ref_now(self, i: int):
        try:
            _bl = getattr(self, '_ctx_buildings', None) or []
            if not (0 <= i < len(_bl)):
                return None
            _b = _bl[i]
            _npw = float(getattr(getattr(_b, 'cooling_device', None),
                                 'nominal_power', 0.0) or 0.0)
            _idx = int(getattr(_b, 'time_step', 0) or 0) + 1
            return float(_ideal_a_ref(_b, _npw, _idx))
        except Exception:
            return None

    # 把制冷动作换算成真实施加的开度；按开关三选一（见文件顶部对应常量的注释）： ✓
    def _cool_action_apply(self, action):
        _fl_list = getattr(self, '_cool_floor', None) or []
        _sp_list = getattr(self, '_cool_span', None) or []
        _centered = bool(getattr(self, '_cool_centered', False))
        _has_floor = bool(COOL_FLOOR_ENABLE and any(_fl_list))
        _has_span = bool(COOL_SPAN_ENABLE
                         and any(abs(float(v) - 1.0) > 1e-9 for v in _sp_list))
        if ((not _centered and not _has_floor and not _has_span)
                or not isinstance(action, dict)):
            return action
        # 课程式衰减系数（仅 C′-4 下界用）—— 现读模块级变量，不做缓存
        _scale = float(min(max(float(COOL_FLOOR_SCALE), 0.0), 1.0))
        _dim_list = getattr(self, '_cool_dim', None) or []
        out = {}
        for _aid, _vec in action.items():
            try:
                _i = self._ctx_ids.index(_aid)
            except ValueError:
                _i = -1
            _dim = _dim_list[_i] if 0 <= _i < len(_dim_list) else None
            _fl = (float(_fl_list[_i]) * _scale
                   if (_has_floor and 0 <= _i < len(_fl_list)) else 0.0)
            _sp = (float(_sp_list[_i])
                   if (_has_span and 0 <= _i < len(_sp_list)) else 1.0)
            # P-1 / P-6′(i)：这一步的 a_ref —— **None = 读不到**（改走旧的兜底映射：按固定倍率算）；
            #   合法数值（含 0）⇒ 走负荷跟随式，不再把"合法的 0"误当成"取不到"
            _aref = self._cool_a_ref_now(_i) if (_centered and _i >= 0) else None
            _has_ref = bool(_centered and _aref is not None and np.isfinite(_aref))
            _use_load = bool(_has_ref and _aref > 0.0)
            if _dim is None or (not _has_ref and _fl <= 0.0 and abs(_sp - 1.0) <= 1e-9):
                out[_aid] = _vec
                continue
            try:
                _arr = np.array(_vec, dtype=np.float32, copy=True).reshape(-1)
                if _dim < _arr.size:
                    _a = min(max(float(_arr[_dim]), 0.0), 1.0)   # 冷却维原始范围就是 [0,1]
                    if _use_load:
                        # 真实施加的开度 = a_ref × 倍率；倍率随策略输出 a 在 [MIN_FRAC, MAX_FRAC] 之间线性变化
                        _lo = float(self._cool_load_min_frac)
                        _hi = float(self._cool_load_max_frac)
                        _a = _aref * (_lo + (_hi - _lo) * _a)
                    elif _has_ref:
                        # P-6′(i)：a_ref 可以**正好是 0**（这一步刚够用就是不用制冷 ✓）
                        _a = float(self._cool_load_noload_max) * _a
                    else:
                        if _sp < 1.0:
                            _a = _sp * _a                        # 缩放 → 工作点 a≈0.5
                        if _fl > 0.0:
                            _a = _fl + (1.0 - _fl) * _a          # C′-4：抬下界（默认关）
                    _arr[_dim] = min(max(_a, 0.0), 1.0)
                out[_aid] = _arr
            except Exception:
                out[_aid] = _vec
        return out

    # 走一步：先把策略给的制冷动作换算成"真实施加的开度"，再让环境推进一步，最后把额外信息拼进新观测 ✓
    def step(self, action):
        action = self._cool_action_apply(action)
        obs, reward, terminated, truncated, info = super().step(action)
        return self._ctx_augment(obs), reward, terminated, truncated, info




# P1：按已完成轮数更新冷却下界的衰减系数（模块级，供 ContextRLlibEnv 读取） ✓
def update_cool_floor_scale(epochs_done: int) -> float:
    global COOL_FLOOR_SCALE
    try:
        until = float(COOL_FLOOR_UNTIL)
        s = 1.0 if until <= 0 else max(0.0, 1.0 - float(epochs_done) / until)
    except Exception:
        s = 1.0
    COOL_FLOOR_SCALE = float(min(max(s, 0.0), 1.0))
    return COOL_FLOOR_SCALE


# 当前冷却下界衰减系数（∈[0,1]）。C′-4 下界按它缩放；`COOL_FLOOR_UNTIL=0` 时恒为 1.0 ✓
def get_cool_floor_scale() -> float:
    return float(min(max(float(COOL_FLOOR_SCALE), 0.0), 1.0))


# 写入冷却下界衰减系数（训练循环每轮 / 评估前按 best_meta 恢复时调用）✓
def set_cool_floor_scale(value) -> float:
    global COOL_FLOOR_SCALE
    COOL_FLOOR_SCALE = float(min(max(float(value), 0.0), 1.0))
    return COOL_FLOOR_SCALE






# 训练/评估/中期评估三处统一使用的环境类（RLlib 的 .environment() 也接受类对象）
_AGENT_ENV_CLS = ContextRLlibEnv if OBS_CONTEXT_ENABLE else RLlibMultiAgentEnv


# ---- _make_agent_env / _AGENT_ENV_CLS（2026-10-02 自入口脚本搬来）----


# 按开关选择环境类：P6-A 开启时用含楼栋上下文的子类 ✓
def _make_agent_env(env_config):
    cls = ContextRLlibEnv if OBS_CONTEXT_ENABLE else RLlibMultiAgentEnv
    return cls(env_config)


# 训练/评估/中期评估三处统一使用的环境类（RLlib 的 .environment() 也接受类对象）
_AGENT_ENV_CLS = ContextRLlibEnv if OBS_CONTEXT_ENABLE else RLlibMultiAgentEnv

# ============================================================================
# ==== 段：schema_patch（原 utils/schema_patch.py ✓）====


import json
from pathlib import Path


# 按数据集名定位 schema.json（CityLearn 缓存目录 / 包内 datasets）。找不到返回 None ✓
def resolve_schema_path(schema: str):
    roots = [
        Path.home() / 'AppData' / 'Local' / 'intelligent-environments-lab' / 'citylearn',
        Path.home() / '.citylearn',
    ]
    for root in roots:
        try:
            if Path(root).is_dir():
                hits = sorted(Path(root).glob(f'**/{schema}/schema.json'))
                if hits:
                    return hits[-1]
        except Exception:
            pass
    try:
        import citylearn
        cand = Path(citylearn.__file__).resolve().parent / 'datasets' / schema / 'schema.json'
        if cand.is_file():
            return cand
    except Exception:
        pass
    return None


# 按 P7-1 修改 schema；返回 (schema 对象, root_directory 或 None) ✓
def patch_schema_observations(schema, extra_active, temp_delta):
    if isinstance(schema, dict):
        data, root = schema, None
    else:
        path = resolve_schema_path(schema)
        if path is None:
            return schema, None
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
        except Exception:
            return schema, None
        root = path.parent
    try:
        obs = data.setdefault('observations', {})
        for key in (extra_active or ()):
            item = obs.get(key)
            if not isinstance(item, dict):
                item = {}
            item['active'] = True
            item.setdefault('shared_in_central_agent', False)
            obs[key] = item
        if temp_delta and float(temp_delta) > 0.0:
            bl = data.get('buildings')
            items = bl.values() if isinstance(bl, dict) else (bl or [])
            for b in items:
                if isinstance(b, dict):
                    b['maximum_temperature_delta'] = float(temp_delta)
    except Exception:
        pass
    return data, root


# 把 Building.maximum_temperature_delta 强制成 `temp_delta`（P7-1）。返回状态字符串 ✓
def install_temp_delta_override(temp_delta):
    if not (temp_delta and float(temp_delta) > 0.0):
        return 'skipped(temp_delta off)'
    try:
        import citylearn.building as _clb
    except Exception as exc:
        return f'import failed: {exc}'
    prop = _clb.Building.maximum_temperature_delta
    if getattr(_clb.Building, '_temp_delta_patched', False):
        return 'already'
    fget_orig, fset_orig = prop.fget, prop.fset

    # 读 Building.maximum_temperature_delta；若已强制指定 temp_delta 就直接返回它 ✓
    def _get(self):
        val = temp_delta
        if val and float(val) > 0.0:
            return float(val)
        return fget_orig(self)

    # 写 Building.maximum_temperature_delta；若已强制指定 temp_delta 则写 temp_delta ✓
    def _set(self, value):
        fset_orig(self, temp_delta if (temp_delta and float(temp_delta) > 0.0) else value)

    _clb.Building.maximum_temperature_delta = property(
        _get, _set, prop.fdel, prop.__doc__
    )
    _clb.Building._temp_delta_patched = True
    return 'installed'

# ============================================================================
# ==== 段：env_config（原 utils/env_config.py ✓）====


from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper

from utils.config import (
    CUSTOM_REWARD_KWARGS,
    _CUSTOM_REWARD_MODULE,
    USE_CUSTOM_REWARD,
)



# 注：原来这里的 `_KPI_READ_ERR_LOGGED` + `_log_kpi_read_err`（"只提示一次"的
OBS_EXTRA_ACTIVE = (
    'indoor_dry_bulb_temperature_cooling_delta',   # T − 制冷设定点（策略最缺的信号）
    'indoor_dry_bulb_temperature_heating_delta',  # T − 制热设定点（算法与制冷侧一样，只是换成制热设定点）
    'comfort_band',                                # 舒适带（本数据集恒为 2.0）
)
TEMP_DELTA = 20.0    # 每栋 maximum_temperature_delta（CityLearn 默认值）；None/<=0 = 不改
# P9-1′（归因步骤）：3.0 → 20.0（退回默认）。依据两次运行对照：
_TEMP_DELTA_STATUS = install_temp_delta_override(TEMP_DELTA)




# 注：给观测加特征 / 改特征这件事，已抽成 utils/schema_patch.patch_schema_observations() ✓


# 组装 CityLearn 环境配置（数据集 / 步数 / 输出目录 / 渲染 / 用哪个奖励 ✓）—— 训练与评估都走它 ✓
def build_env_config(
    schema: str,
    episode_time_steps,          # int 或 None（None ⇒ 用数据集自带长度，见下）
    output_dir: Path,
    enable_render: bool,
    record_details: bool = True,
) -> dict:
    # 打开"偏差类"观测 + 把温度缩放的宽度改窄（细节见上方说明）
    schema_obj, schema_root = patch_schema_observations(schema, OBS_EXTRA_ACTIVE, TEMP_DELTA)
    env_kwargs = {
        'schema': schema_obj,
    }
    # episode_time_steps：**给了就用给定值；给 None 就不传**，交给 CityLearn 用数据集自带长度
    if episode_time_steps is not None:
        env_kwargs['episode_time_steps'] = int(episode_time_steps)
    if schema_root is not None:
        env_kwargs['root_directory'] = str(schema_root)
    if USE_CUSTOM_REWARD:
        # 用本文件的 CustomComfortReward 覆盖 schema.json 里的默认奖励（训练/评估同时生效）。
        # 注意：CityLearn 按「模块.类名」字符串 + reward_function_kwargs 实例化。
        env_kwargs['reward_function'] = f'{_CUSTOM_REWARD_MODULE}.CustomComfortReward'
        env_kwargs['reward_function_kwargs'] = dict(CUSTOM_REWARD_KWARGS, record_details=bool(record_details))
    if enable_render:
        env_kwargs.update({
            'render_mode': 'end',
            'render_directory': output_dir,
            'render_session_name': '.',
        })
    return {
        'env_kwargs': env_kwargs,
        'wrappers': [NormalizedObservationWrapper, ClippedObservationWrapper],
    }

# ============================================================================
# ==== 段：probe_env（原 utils/probe_env.py ✓）====

from utils.base import log_console






# 构建中期评估用的"试跑"环境。返回 (env, 跑多少步, 这段怎么取) ✓
def build_probe_env(schema: str, output_dir: Path, steps: int, where: str):
    steps = max(4, int(steps))
    path = resolve_schema_path(schema)
    if path is not None:
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            full_end = int(data.get('simulation_end_time_step') or (steps - 1))
            if where == 'tail':
                end = full_end
                start = max(0, end - steps + 1)
            elif where == 'full':
                start = 0
                end = full_end
            else:
                start = 0
                end = min(full_end, steps - 1)
            data['simulation_start_time_step'] = int(start)
            data['simulation_end_time_step'] = int(end)
            data['root_directory'] = str(Path(path).parent)
            n = int(end) - int(start) + 1
            cfg = build_env_config(data, n, output_dir, enable_render=False, record_details=False)
            return (
                _AGENT_ENV_CLS(cfg),
                max(1, n - 1),
                f'{where}[{start}-{end}] {n - 1}步',
            )
        except Exception as exc:
            log_console(f'[中期评估] {where} 窗口构建失败，回退到前 {steps} 步: {exc}')
    # 定位不到 schema.json（罕见）：不猜步数 ✓
    if where == 'full':
        cfg = build_env_config(schema, None, output_dir, enable_render=False, record_details=False)
        penv = _AGENT_ENV_CLS(cfg)
        n_steps = int(getattr(penv.env.unwrapped, 'episode_time_steps', 0) or 0) or steps
        return penv, max(1, n_steps - 1), f'{where}(回退·数据集自带) {max(1, n_steps - 1)}步'
    cfg = build_env_config(schema, int(steps), output_dir, enable_render=False, record_details=False)
    return _AGENT_ENV_CLS(cfg), max(1, int(steps) - 1), f'{where}(回退) {int(steps) - 1}步'

# ============================================================================
# 原模块文档串（原样保留 ✓）：



from typing import Any


_STATUS = 'not_installed'
