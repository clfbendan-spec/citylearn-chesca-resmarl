# ⚠️ 本文件是**精简注释版**（由 `_gen_marl_split.py` 生成 ✓）：全部「详注块」已整段删除 ✓，
#    代码与同目录的 `X.detailed.py` **逐字相同** ✓（AST 一致 ⇒ 行为一致 ✓）。
#    **改注释请改 `.detailed.py` 那份** ✗（本文件每次生成都会被覆盖 ✗），改完重跑 `_gen_marl_split.py` ✓。

# ============ 以下说明合并自 utils/train.py（docstring → 注释 ✓）============
# 训练阶段支撑：P-4 成本项 / 训练收尾汇总 / 把模型换成"最好一轮"的存档（2026-10-06 新建 ✓）。
#
# **为什么要有这个模块** ✗✓：`Multi-agent.py` 的 `__main__` 里，训练专属的代码占了近 900 行
# （收尾汇总 + 主循环 + 若干小函数 ✓）⇒ 入口读起来像一团线 ✗。这里先把"不需要循环状态"的
# 几块收进来 ✓，主循环随后也会搬进来（`run_training` ✓）。
#
# **边界（很重要 ✓）**：
# · 本模块**只服务训练入口** ✓ —— 评估入口（`Multi-agent-eval.py`）的生成过程会把
# `Multi-agent.py` 里调用本模块的那几段整段去掉 ✓ ⇒ 评估侧完全不感知本模块 ✓；
# · 常量一律从 `utils/config.py` 取 ✓（改判据去那里改 ✗，别改这里 ✓）；
# · 日志一律走传入的 `log` ✓（入口传 `log_console` ✓，测试传空实现 ✓）。
#
# **搬运时的原则** ✓：**逐字搬运** ✗，只做两处机械改动 ——
# ① 原来靠闭包拿的 `_p4_cost_ref` / `model` 等 ⇒ 改成**显式入参** ✓；
# ② 原来直接调 `log_console` ⇒ 改成调传入的 `log` ✓。
# 其余（含所有 fmt 串、判据、注释）一字不改 ✓ —— 这样"抽出前后行为一致"是可复核的 ✓。
# """

from __future__ import annotations

# ============ 以下正文：训练支撑（多段合并 ✓）============
"""训练与评估支撑：中期评估 / 无控制成本参照 / checkpoint 存取 / 训练主循环

本文件由 utils/ 下多个模块合并而来（2026-10-06 ✓，段名见下方各段横幅 ✓）：
  · mid_eval（见下方同名段 ✓）
  · cost_ref（见下方同名段 ✓）
  · action_hook（见下方同名段 ✓）
  · action_hook（见下方同名段 ✓）
  · checkpoint_utils（见下方同名段 ✓）
"""

# ============================================================================
# ==== 段：mid_eval（原 utils/train.py ✓）====
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# 训练中"中期评估"试跑：用当前策略贪心跑一段，得到与导出 KPI 用同一算法算出的读数。
# =====================================================================================
#
# 用途（训练期唯一可用的读数；选择指标与历次判决见 DECISIONS.md §10）：
#   · **best-ckpt 选择** —— 决定哪一版权重值得拿去正式评估（否则末次权重可能比历史最优差很多）
#   · **早停判据** ① 达标 / ② 投票停滞 / ③ 单栋恶化 / ④ 收敛 / ⑤ 崩坏
#   · **训练曲线** —— 看出缺口是"随训练下降（训练量不够）"还是"平着不动（收敛到错的点）"
#
# 两个入口：
#   · `run_mini_eval(model, env, steps)` —— 在**一个**试跑环境里贪心跑 `steps` 步
#   · `run_mid_eval(model, probes)`      —— 跑多个窗口，按「有人步数」加权合并
#
# 两套读数怎么来的：
#   · **主动读数**由奖励函数自己累加（`rf.kpi_snapshot()`）—— `calculate()` 拿到的是策略本步
#     真正喂给策略的那份观测 ⇒ 与推演记录 / 导出 KPI **同一来源** ✓
#   · **参考读数**（用 `read_building_series` 读楼栋对象算的）只用于自检对比，**判据不使用**；
#     它在自定义窗口下曾与真实轨迹不符（差 3.8~18 倍），保留是为了把那个坑永久守住 ✓
#   · 必须"同数据集 / 同步数 / 贪心"才能跨轮比较；这一段怎么取 = 整段跑（由调用方的
#     `MID_EVAL_WINDOWS` 决定 ✓）
#   · 返回值里 `stats['kpi']` 同时带主动读数（`hot/cold/occ/mean_T`）与参考读数（`legacy_*`）✓
#
# 本模块**不含任何配置常量**：窗口、步数、阈值一律由调用方（`Multi-agent.py` 的
# `MINI_EVAL_*` / `MID_*`）决定 ✓


from typing import Any, Mapping, Sequence

import numpy as np

from utils.env import unwrap_action, unwrap_citylearn_env
from utils.base import log_console, log_kpi_read_err


# 按候选属性名读楼栋第 idx 个值，兼容三种形态： ✓
def read_building_series(building, names, idx):
    bt = None
    try:
        bt = int(getattr(building, 'time_step', -1))
    except Exception:
        bt = None
    for name in names:
        for holder in (building, getattr(building, 'energy_simulation', None)):
            if holder is None:
                continue
            try:
                raw = getattr(holder, name, None)
            except Exception as exc:
                log_kpi_read_err(name, exc)
                continue
            if raw is None:
                continue
            try:
                arr = np.asarray(raw, dtype=float).reshape(-1)
            except Exception as exc:
                log_kpi_read_err(name, exc)
                continue
            if arr.size == 0:
                continue
            for k in (idx, bt, arr.size - 1):
                if k is None:
                    continue
                k = int(min(max(int(k), 0), arr.size - 1))
                v = float(arr[k])
                if np.isfinite(v):
                    return v
    return float('nan')


# 训练中「小评估」：用当前策略贪心跑 steps 步，返回 (平均回报, 奖励统计) ✓
def run_mini_eval(model, env, steps: int):
    citylearn_env = unwrap_citylearn_env(env)
    rf = getattr(citylearn_env, 'reward_function', None) if citylearn_env is not None else None
    if rf is not None and hasattr(rf, 'stats_reset'):
        rf.stats_reset()
    if rf is not None and hasattr(rf, 'kpi_reset'):
        rf.kpi_reset()
    observations, _ = env.reset()
    ordered_ids = list(getattr(env, '_agent_ids', None) or list(observations.keys()))
    buildings = list(getattr(citylearn_env, 'buildings', []) or []) if citylearn_env is not None else []
    n_b = len(buildings)
    # ---- 影子统计（旧路径，不参与判据；用于证明/否证两套读数是否一致）----
    s_hot_n = [0] * n_b
    s_cold_n = [0] * n_b
    s_occ_n = [0] * n_b
    s_t_sum = 0.0
    s_t_cnt = 0
    s_samples = []      # 首个楼步的原始读数（自检报警时打印，用于钉死根因）
    steps_run = 0
    total = 0.0
    n = 0
    for _ in range(int(steps)):
        if getattr(env, 'terminated', False):
            break
        actions = {
            p: unwrap_action(model.compute_single_action(observations[p], policy_id=p, explore=False))
            for p in ordered_ids
            if p in observations
        }
        observations, rewards, _, _, _ = env.step(actions)
        steps_run += 1
        if isinstance(rewards, dict):
            total += float(sum(float(v) for v in rewards.values()))
            n += len(rewards)
        else:
            total += float(np.sum(rewards))
            n += 1
        # ---- 影子统计（旧路径）：仅用于自检对比，不参与判据 ----
        # 保留原因：623a9e8d/b30240d4 实测这套读数在自定义窗口下与真实轨迹不符，保留它才能
        #   在日志里同时看到两套值，从而永久性地守住这个坑（而不是直接删掉、失去证据）。
        #   （完整实测记录见 DECISIONS.md §9.2）
        ts = max(0, int(getattr(citylearn_env, 'time_step', 1) or 1) - 1)
        for i, b in enumerate(buildings):
            T = read_building_series(b, ('indoor_dry_bulb_temperature',), ts)
            if not np.isfinite(T):
                continue
            csp = read_building_series(
                b, ('indoor_dry_bulb_temperature_cooling_set_point',), ts
            )
            hsp = read_building_series(
                b, ('indoor_dry_bulb_temperature_heating_set_point',), ts
            )
            band = read_building_series(b, ('comfort_band',), ts)
            occ = read_building_series(b, ('occupant_count',), ts)
            if not np.isfinite(band):
                band = 2.0
            if not np.isfinite(csp) or not np.isfinite(hsp):
                continue
            if not np.isfinite(occ):
                occ = 1.0      # 读不到占用 → 按"有人"计（保守：不放过任何不适步）
            if len(s_samples) <= i:
                s_samples.append({'T': T, 'csp': csp, 'hsp': hsp,
                                  'band': float(band), 'occ': float(occ)})
            s_t_sum += float(T)
            s_t_cnt += 1
            if occ <= 0.0:
                continue
            s_occ_n[i] += 1
            if T > csp + band:
                s_hot_n[i] += 1
            if T < hsp - band:
                s_cold_n[i] += 1
    stats = rf.stats_snapshot() if rf is not None and hasattr(rf, 'stats_snapshot') else {}
    # ---- P1′：主动读数 = 奖励侧累计（以它为准）----
    kpi_new = {}
    if rf is not None and hasattr(rf, 'kpi_snapshot'):
        try:
            kpi_new = rf.kpi_snapshot() or {}
        except Exception:
            kpi_new = {}
    o_new = list(kpi_new.get('occ') or [])
    h_new = list(kpi_new.get('hot') or [])
    c_new = list(kpi_new.get('cold') or [])
    nb_new = max(len(o_new), n_b)
    while len(o_new) < nb_new:
        o_new.append(0)
    while len(h_new) < nb_new:
        h_new.append(0)
    while len(c_new) < nb_new:
        c_new.append(0)
    # 注意：影子统计「不」补齐到 nb_new —— 保持它自己的长度，这样在楼栋对象列表
    #   读不到任何数据时它是空列表（而不是一串 nan），mid-eval 的自检就不会误报。
    _t_cnt_new = int(kpi_new.get('t_cnt') or 0)
    stats['kpi'] = {
        # 主动读数（判据用）：奖励函数在每一步内部按 CityLearn 的 KPI 算法累加
        'hot': [h_new[i] / o_new[i] if o_new[i] else float('nan') for i in range(nb_new)],
        'cold': [c_new[i] / o_new[i] if o_new[i] else float('nan') for i in range(nb_new)],
        'occ': o_new,
        'mean_T': (float(kpi_new.get('t_sum') or 0.0) / _t_cnt_new) if _t_cnt_new else float('nan'),
        'steps_run': steps_run,
        'src': 'reward',
        # 参考读数（只供自检对比，判据不用）；没有有效数据时给空列表而不是 nan，
        #   否则 mid-eval 的 `if _lg_hot` 会误判为"有数据"并打出假警告。
        'legacy_hot': ([s_hot_n[i] / s_occ_n[i] for i in range(len(s_occ_n))] if s_occ_n and sum(s_occ_n) else []),
        'legacy_cold': ([s_cold_n[i] / s_occ_n[i] for i in range(len(s_occ_n))] if s_occ_n and sum(s_occ_n) else []),
        'legacy_occ': (s_occ_n if s_occ_n and sum(s_occ_n) else []),
        'legacy_mean_T': (s_t_sum / s_t_cnt) if s_t_cnt else float('nan'),
        # ---- 首个楼步的原始读数：仅在自检报警时打印，用于钉死两套读数为何不一致 ----
        'samples': list(kpi_new.get('samples') or []),   # 奖励侧（策略真正用的那份观测）
        'legacy_samples': s_samples,                     # 旧楼栋对象读数
    }
    return (total / n if n else 0.0), stats


# 跑多段"试跑"并把统计合并起来 ✓
def run_mid_eval(model, probes):
    agg: dict = {}
    rets = []
    hot_acc = cold_acc = occ_acc = None
    s_hot_acc = s_cold_acc = s_occ_acc = None
    samples_first = []          # 主侧原始读数（取第一个窗口的首个楼步）
    legacy_samples_first = []   # 影子侧原始读数
    t_wsum = 0.0
    t_wn = 0
    steps_run_total = 0

    # 把某窗口的逐栋比例按「该窗口有人步数」加权累加（跨窗口合并用） ✓
    def _acc_one(h, c, o, hot_a, cold_a, occ_a):
        if hot_a is None:
            hot_a, cold_a, occ_a = [0.0] * len(h), [0.0] * len(c), [0] * len(o)
        while len(hot_a) < len(h):
            hot_a.append(0.0)
            cold_a.append(0.0)
            occ_a.append(0)
        for i in range(len(h)):
            oi = int(o[i]) if i < len(o) else 0
            occ_a[i] += oi
            hot_a[i] += (float(h[i]) if np.isfinite(h[i]) else 0.0) * oi
            cold_a[i] += (float(c[i]) if np.isfinite(c[i]) else 0.0) * oi
        return hot_a, cold_a, occ_a

    for pr in probes or []:
        try:
            ret_i, st_i = run_mini_eval(model, pr['env'], int(pr['run_steps']))
        except Exception as exc:
            log_console(f"[中期评估] 窗口 {pr.get('where')} 跑失败（跳过）: {exc}")
            continue
        rets.append(ret_i)
        for k, v in (st_i or {}).items():
            if k == 'kpi':
                continue
            agg[k] = (agg.get(k) or 0) + (v or 0)
        kpi = (st_i or {}).get('kpi') or {}
        _sr = int(kpi.get('steps_run') or 0)
        steps_run_total += _sr
        _mt = kpi.get('mean_T')
        if np.isfinite(_mt) and _sr:
            t_wsum += float(_mt) * _sr
            t_wn += _sr
        # 主动读数（奖励侧算的，判据用它）
        h, c, o = (list(kpi.get(k) or []) for k in ('hot', 'cold', 'occ'))
        hot_acc, cold_acc, occ_acc = _acc_one(h, c, o, hot_acc, cold_acc, occ_acc)
        # 参考读数（按每栋老办法算的，只供自检对比）
        h, c, o = (list(kpi.get(k) or []) for k in ('legacy_hot', 'legacy_cold', 'legacy_occ'))
        s_hot_acc, s_cold_acc, s_occ_acc = _acc_one(h, c, o, s_hot_acc, s_cold_acc, s_occ_acc)
        if not samples_first:
            samples_first = list(kpi.get('samples') or [])
            legacy_samples_first = list(kpi.get('legacy_samples') or [])

    # 算 num/den 的比值；分母无效或为 0 时返回 0 ✓
    def _ratio(num, den):
        cnt = max(len(num or []), len(den or []))
        out = []
        for i in range(cnt):
            d = den[i] if den and i < len(den) else 0
            v = num[i] if num and i < len(num) else float('nan')
            out.append((v / d) if d else float('nan'))
        return out

    kpi_out = {
        # ---- 主动读数（"选最好一轮" + 早停判据用它）----
        'hot': _ratio(hot_acc, occ_acc),
        'cold': _ratio(cold_acc, occ_acc),
        'occ': occ_acc or [],
        'mean_T': (t_wsum / t_wn) if t_wn else float('nan'),
        'steps_run': steps_run_total,
        'src': 'reward',
        # ---- 参考读数（只打日志做对比，任何判据都不用）----
        'legacy_hot': _ratio(s_hot_acc, s_occ_acc),
        'legacy_cold': _ratio(s_cold_acc, s_occ_acc),
        'legacy_occ': s_occ_acc or [],
        'samples': samples_first,
        'legacy_samples': legacy_samples_first,
    }
    return (float(np.mean(rets)) if rets else 0.0), agg, kpi_out


# -----------------------------------------------------------------------------
# 指标查找助手（2026-10-05 从 Multi-agent.py 下沉到本模块 ✓）
#   用途：RLlib train() 返回的是多层嵌套 dict，指标埋在深处 ⇒ 递归找第一个命中的数值 ✓；
#   入口用 `from utils.train import find_metric` 引入 ⇒ 诊断脚本的 `ma.find_metric`
#   照旧可用 ✓（原先它定义在入口脚本里 ✓）
# -----------------------------------------------------------------------------
# 在 RLlib train() 返回的（多层嵌套）结果字典里递归查找第一个命中的数值指标 ✓
def find_metric(result, *key_names, default=None):
    if not isinstance(result, dict):
        return default
    for key in key_names:
        val = result.get(key)
        if isinstance(val, (int, float)):
            return val
    for val in result.values():
        got = find_metric(val, *key_names, default=None)
        if got is not None:
            return got
    return default

# ============================================================================
# ==== 段：cost_ref（原 utils/train.py ✓）====
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# "什么都不控制"的成本参照（P-4：把原始电费 `cost_raw` 换算成 0~1 的成本率）。
# =====================================================================
#
# 做法：在**同一段试跑**里，用「恒定制冷动作 a=0.5」跑一遍 —— 当前 P-1 映射下
#   a=0.5 ⇒ applied = a_ref（恒等跟随）⇒ 正是无控制基线（热泵不控、按数据集理想负荷
#   交付）的行为；储能维给 0（无控制基线也不动电池）✓
# 返回 `{'raw': Σprice×max(0,net), 'by_b': [逐栋], 'steps': 实跑步数}`；
# 任何失败返回 `{}`，调用方据此**自动关闭**成本项（不影响训练）✓
#
# 调用方是训练期"选最好一轮"的指标（成本项"超过目标线才罚"，见 `utils/config.py` 的
# `P4_COST_HINGE`）；评估脚本里没有调用点 ✓


from utils.env import unwrap_citylearn_env

# P-4：本场景"什么都不控制"的成本参照（把原始电费 cost_raw 换算成 0~1 的成本率） ✓
def run_nocontrol_cost_ref(env, steps: int) -> dict:
    try:
        ce = unwrap_citylearn_env(env)
        if ce is None:
            return {}
        rf = getattr(ce, 'reward_function', None)
        if rf is None or not hasattr(rf, 'cost_snapshot'):
            return {}
        if hasattr(rf, 'stats_reset'):
            rf.stats_reset()
        env.reset()
        ids = list(getattr(env, '_agent_ids', None) or [])
        bl = list(getattr(ce, 'buildings', []) or [])
        acts = {}
        for i, aid in enumerate(ids):
            names = list(getattr(bl[i], 'active_actions', None) or []) if i < len(bl) else []
            vec = np.zeros(max(1, len(names)), dtype=np.float32)
            if 'cooling_device' in names:
                vec[names.index('cooling_device')] = 0.5      # P-1 下 = 恒等跟随负荷
            acts[aid] = vec
        run = 0
        for _ in range(int(steps)):
            if getattr(env, 'terminated', False):
                break
            env.step(acts)
            run += 1
        snap = rf.cost_snapshot() or {}
        return {'raw': float(snap.get('raw') or 0.0),
                'by_b': list(snap.get('by_b') or []), 'steps': run}
    except Exception:
        return {}

# ============================================================================
# ==== 段：action_hook（原 utils/train.py ✓）====
#============================================================================
# ==== 段：action_hook（原 utils/train.py ✓）====
#============================================================================

# 本段（动作注入钩子）原住在 utils/env.py，那里的 import **不会**跟着搬过来 ✓
#   ⇒ 在这里补上它用到的外部名字，否则 install_action_hook 运行时会 NameError ✗
#     （静态检查脚本 _q_mod_undef.py 也会报可疑的未定义名字 ✓）
from citylearn.wrappers import RLlibMultiAgentEnv
from utils.env import _cool_thermal_capacity, _ideal_a_ref


# 补丁当前状态：'not_installed' / 'installed' / 'already_installed' / 'no_step_attr' ✓
def action_hook_status() -> str:
    return _STATUS


# 把 action_dict（{agent_i: 动作向量}）按楼栋顺序解析后交给奖励函数 ✓
def pass_actions_to_reward(rllib_env: Any, action_dict: Mapping[Any, Any]) -> None:
    if not isinstance(action_dict, dict):
        return
    ce = unwrap_citylearn_env(rllib_env)
    if ce is None:
        return
    rf = getattr(ce, 'reward_function', None)
    if rf is None or not hasattr(rf, 'note_pending_actions'):
        return

    keys = list(getattr(rllib_env, '_agent_ids', None) or action_dict.keys())
    buildings = list(getattr(ce, 'buildings', []) or [])
    parsed = []
    for i, building in enumerate(buildings):
        key = keys[i] if i < len(keys) else None
        vec = action_dict.get(key) if key is not None else None
        vec = unwrap_action(vec)
        names = list(getattr(building, 'active_actions', None) or [])
        item = {}
        if vec is not None and names:
            try:
                arr = np.asarray(vec, dtype=float).reshape(-1)
                for j, name in enumerate(names):
                    if j < arr.size and np.isfinite(arr[j]):
                        item[f'{name}_action'] = float(arr[j])
            except (TypeError, ValueError):
                pass
        parsed.append(item)
    rf.note_pending_actions(parsed)

    # -------------------------------------------------------------------------
    # Step 2（2026-09-29）：把「本步热容量」交给奖励 —— 让 a_need 能由物理量导出
    #   a_need = cooling_demand ÷ 热容量，热容量 = 额定电功率 × 当前 COP。
    #   COP 随室外温度在 3.1~10.2 间变化（实测），所以必须逐时算、不能用额定值。
    #   与 _pending_acts 同一通道写入 rf._cool_capacity；任何失败都只静默跳过
    #   （奖励侧会自动退回老的 'const' 算法，不影响仿真）。
    # -------------------------------------------------------------------------
    try:
        _caps = []
        _refs = []
        _npws = []
        for _b in buildings:
            _cd = getattr(_b, 'cooling_device', None)
            _npw = float(getattr(_cd, 'nominal_power', 0.0) or 0.0)
            _idx = int(getattr(_b, 'time_step', 0) or 0) + 1    # 本步（step 尚未推进）
            _caps.append(_cool_thermal_capacity(_b, _npw, _idx))
            _refs.append(_ideal_a_ref(_b, _npw, _idx))
            # 额定电功率 —— 制冷电耗 = 施加开度 × 额定电功率（与 a_ref 同尺度）
            _npws.append(_npw)
        rf._cool_capacity = _caps
        rf._cool_a_ref = _refs
        rf._cool_nominal_power = _npws
    except Exception:
        pass

    # -------------------------------------------------------------------------
    # P3′（2026-09-29）：把**电池规格**也交给奖励 —— 套利项要把动作换算成 kWh
    #   与 CityLearn 的 update_electrical_storage 同式：energy = action × nominal_power × dt(h)
    #   任何失败只静默跳过（奖励侧会自动不生效，不影响仿真）。
    # -------------------------------------------------------------------------
    try:
        _bp = []
        _bdt = []
        _bc = []
        _br = []
        for _b in buildings:
            _es = getattr(_b, 'electrical_storage', None)
            _bp.append(float(getattr(_es, 'nominal_power', 0.0) or 0.0))
            # 容量：奖励侧要用 SOC×容量 给放电封顶（否则会奖励"幻影电量"）
            _bc.append(float(getattr(_es, 'capacity', 0.0) or 0.0))
            # time_step_ratio：把观测里的「数据集分辨率」能量换算到本步（CityLearn 内部同用）
            _br.append(float(getattr(_es, 'time_step_ratio', 1.0) or 1.0))
            _sec = float(getattr(_b, 'seconds_per_time_step', 3600) or 3600)
            _bdt.append(_sec / 3600.0)
        rf._bat_power = _bp
        rf._bat_dt = _bdt
        rf._bat_cap = _bc
        rf._bat_ratio = _br
    except Exception:
        pass


# 包装 RLlibMultiAgentEnv.step（重复调用也没副作用）。返回状态字符串，供日志展示 ✓
def install_action_hook() -> str:
    global _STATUS
    target = RLlibMultiAgentEnv
    orig = getattr(target, 'step', None)
    if orig is None:
        _STATUS = 'no_step_attr'
        return _STATUS
    if getattr(orig, '_custom_reward_action_hook', False):
        _STATUS = 'already_installed'
        return _STATUS

    # 包住 RLlibMultiAgentEnv.step：真步进前先把动作喂给奖励（奖励才看得见 act ✓），喂失败也不影响仿真 ✓
    def step(self, action_dict):
        try:
            pass_actions_to_reward(self, action_dict)
        except Exception:
            pass  # 注入失败不影响仿真，只是动作项读不到 act
        return orig(self, action_dict)

    step._custom_reward_action_hook = True
    step.__wrapped__ = orig
    target.step = step
    _STATUS = 'installed'
    return _STATUS

# ============================================================================
# ==== 段：checkpoint_utils（原 utils/train.py ✓）====
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# Multi-Agent SAC 的 **checkpoint 存取**（存 / 取 / 找最新）—— 本项目公共一份 ✓
#
# 【为什么单独成模块】
#   这一套原先寄居在 `multi_agent_runner_copy.py`（那份文件的身份是
#   "CHESCA-ResMARL 残差修正" ✗）⇒ 只想"加载一个模型"的入口脚本，
#   却得去 import 一个 CHESCA 专名模块 ✗。2026-10-05 抽到本模块 ✓：
#     · `Multi-agent.py` / `Multi-agent-train.py` / `Multi-agent-eval.py` 从这里 import ✓
#     · `multi_agent_runner_copy.py` 也从这里 import（它自己要建/加载 SAC ✓，CHESCA 链路不变 ✓）
#
# 【谁在用】
#   · `Multi-agent-train.py`   ：`save_multi_agent_checkpoint()` 存盘 ✓
#   · `Multi-agent-eval.py`    ：`load_multi_agent_checkpoint()` 加载模型 ✓
#   · `multi_agent_runner_copy.py`（CHESCA-ResMARL）：建/加载 SAC 时用 ✓
#
# 【⚠️ 两条必须守住的事】
#   ① `prepare_ray_env()` 要在 Ray 真正起来之前跑 ✓（Windows 的 resource 补丁 + PYTHONPATH +
#      Ray 环境变量）。本模块**不在顶层 import ray** ✓，全部放在函数内按需 import ✓
#      ⇒ "先准备环境、再 import ray" 的顺序天然成立 ✓；本模块 import 时也会调一次
#      （重复执行也没副作用 ✓，与抽出来之前的 `multi_agent_runner_copy` 行为一致 ✓）
#   ② `_CHECKPOINT_MARKERS` 与入口脚本里的 `_is_ckpt_dir()` 是**同一条规则的两份副本** ✗
#      （入口那边要用它做"找最新 checkpoint"）⇒ 改标记名时**两处同改** ✓
#
# 【与"奖励怎么算"的分工】✗ 别混
#   本模块只管"**模型**从哪来" ✓；训练时的**奖励配置**另有机制 —— checkpoint 目录旁的
#   `reward_config.json`（训练写 ✓ / 评估读回 ✓，见 DECISIONS §15）✓。两者正交 ✓。


import sys
from pathlib import Path
from typing import Callable, Optional, Union

# Ray 启动前的环境准备（2026-10-02 收拢到 utils/base.py，本项目只此一份 ✓）：
#   · Windows resource 补丁（stdlib 无 getrlimit/setrlimit ⇒ Ray.init 会崩 ✗）
#   · 把 citylearnpy 写进 PYTHONPATH / sys.path ⇒ worker 子进程才能 import 本地模块
#   · 设 RAY_DISABLE_DASHBOARD=1 / RAY_DEDUP_LOGS=0（Windows 上 dashboard/prometheus 易崩）
from utils.base import prepare_ray_env, ray_runtime_env   # noqa: E402

prepare_ray_env()

LogFn = Callable[[str], None]

# RLlib checkpoint 目录的判定标记（见文件头 ⚠️②：与入口脚本里那份同规则 ✓）
_CHECKPOINT_MARKERS = (
    'rllib_checkpoint.json',
    'algorithm_state.pkl',
    '.is_checkpoint',
)


# 确保 Ray 已初始化（启动前先做 Ray 环境准备，见 utils/process_env） ✓
def ensure_ray_initialized(log_console: Optional[LogFn] = None) -> None:
    # ⚠️ 必须在 import ray / ray.init 之前：补 resource 补丁 + 写 PYTHONPATH +
    #   设 Ray 环境变量。原先这三件事散在本函数内（还与脚本顶部重复一份 ✗），
    #   2026-10-02 收拢到 utils/process_env.prepare_ray_env() ✓
    #   副作用说明：现在这三件事**无条件**执行（原先要等 `ray.is_initialized()` 为 False
    #   才做）—— 它们重复执行也没副作用，对已初始化的 Ray 无影响 ✓；好处是"只 import 本模块、
    #   不走 ray.init"的调用方也能拿到正确的 PYTHONPATH ✓
    prepare_ray_env()
    import ray

    if ray.is_initialized():
        return
    log = log_console or (lambda _msg: None)
    log('初始化 Ray（本地模式）...')
    init_kwargs = dict(
        ignore_reinit_error=True,
        include_dashboard=False,
        logging_level='ERROR',
    )
    # Windows：把 PYTHONPATH 等显式传给 worker 子进程
    # （worker 是独立进程，只继承环境变量、不带父进程的 sys.path ✗）
    if sys.platform == 'win32':
        init_kwargs['runtime_env'] = ray_runtime_env()
    ray.init(**init_kwargs)


# 把"用户给的路径"解析成真正的 RLlib checkpoint 目录 ✓
def resolve_multi_agent_checkpoint_path(path: Union[str, Path]) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f'Multi-Agent SAC checkpoint 不存在: {p}')

    if p.is_file():
        p = p.parent

    # 判断一个目录是不是 RLlib checkpoint（看那三个标记文件 ✓）✓
    def _is_ckpt_dir(d: Path) -> bool:
        return d.is_dir() and any((d / m).exists() for m in _CHECKPOINT_MARKERS)

    if _is_ckpt_dir(p):
        return p

    children = sorted(
        [c for c in p.iterdir() if c.is_dir() and (
            c.name.startswith('checkpoint') or _is_ckpt_dir(c)
        )],
        key=lambda x: x.name,
    )
    # 优先带 marker 的目录
    with_markers = [c for c in children if _is_ckpt_dir(c)]
    if with_markers:
        return with_markers[-1]
    if children:
        return children[-1]
    raise FileNotFoundError(
        f'目录下未找到可用的 RLlib checkpoint（需含 rllib_checkpoint.json 等）: {p}'
    )


# 保存 RLlib Algorithm 断点，返回实际写盘的目录（供 `--checkpoint` 复用 ✓） ✓
def save_multi_agent_checkpoint(algo, checkpoint_dir: Union[str, Path], log_console: Optional[LogFn] = None) -> Path:
    log = log_console or (lambda _msg: None)
    dest = Path(checkpoint_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    result = algo.save(checkpoint_dir=str(dest))
    saved: Optional[Path] = None
    if hasattr(result, 'checkpoint') and result.checkpoint is not None:
        ckpt = result.checkpoint
        path_attr = getattr(ckpt, 'path', None) or getattr(ckpt, 'local_path', None)
        if path_attr:
            saved = Path(str(path_attr))
    if saved is None and isinstance(result, (str, Path)):
        saved = Path(result)
    if saved is None:
        # 兜底：在 dest 下找最新的子目录 / 或者 dest 本身就是断点
        try:
            saved = resolve_multi_agent_checkpoint_path(dest)
        except FileNotFoundError:
            saved = dest

    # 顺手把「本次实际生效」的奖励配置写进 checkpoint 目录（评估端会读回它 ✓，见 DECISIONS §15）
    #   ⚠️ 2026-10-08：原先这是独立函数 `_write_reward_sidecar()`（**已于 2026-10-08 删除** ✓ "把奖励配置写进断点目录" ✓，住在 utils/config.py ✓）——
    #     它只被训练侧用到 ⇒ 已并入本函数 ✓（评估入口因此不再 import 它 ✓，那个名字也消失 ✓）。
    #   为什么必须存：奖励在【训练】时是学习目标、在【评估】时只是打分记录项 ⇒ 两边要用
    #     同一套奖励配置，否则决策推演记录里的 reward 数字没有意义 ✗。失败只提示、不影响训练 ✓。
    try:
        _sp = Path(saved)
        if _sp.suffix:                 # RLlib 有时返回 state 文件路径 ⇒ 退回其所在目录
            _sp = _sp.parent
        _sp.mkdir(parents=True, exist_ok=True)
        (_sp / REWARD_CONFIG_SIDECAR).write_text(
            json.dumps(
                {
                    'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'saved_by': Path(sys.argv[0]).name,
                    'reward_kwargs': dict(CUSTOM_REWARD_KWARGS),
                },
                ensure_ascii=False, indent=2, sort_keys=True,
            ) + '\n',
            encoding='utf-8',
        )
    except Exception as exc:
        log(f'[奖励口径] sidecar 写入失败（忽略）: {type(exc).__name__}: {exc}')
    log(f'Multi-Agent SAC checkpoint 已保存: {saved}')
    return saved.resolve()


# 从 checkpoint 恢复 RLlib Algorithm（评估/残差用：只加载，不训练 ✓） ✓
def load_multi_agent_checkpoint(
    checkpoint_path: Union[str, Path],
    log_console: Optional[LogFn] = None,
    *,
    eval_mode: bool = False,
):
    log = log_console or (lambda _msg: None)
    ensure_ray_initialized(log_console=log)
    resolved = resolve_multi_agent_checkpoint_path(checkpoint_path)
    log(f'加载 Multi-Agent SAC checkpoint: {resolved}')
    from ray.rllib.algorithms.algorithm import Algorithm
    model = Algorithm.from_checkpoint(str(resolved))
    if eval_mode:
        # 下面两行是**评估专用措辞** ✓（CHESCA 调用方不传 eval_mode ⇒ 不会走到这里 ✓）
        log('（本脚本不训练；要训练请运行 Multi-agent-train.py）')
        log(f'奖励动作注入={action_hook_status()}'
            f'（评估阶段动作注入只影响奖励统计展示，不影响 KPI）')
    return model


# ============================================================================
# ==== 段：训练断点与"最好一轮"存档 CkptManager（2026-10-06 从 Multi-agent.py 抽出 ✓）====
# ============================================================================
# 为什么抽出来 ✗✓：这一组（8 个函数 ≈ 200 行）原来是 train 入口 `__main__` 里的**局部定义** ✓，
#   入口因此又长又难读 ✗；它们只依赖"自己的状态"（目录 / 开关 / best 指标 / model ✓）
#   ⇒ 收成一个对象后，入口只剩"建对象 + 几次调用" ✓。
# ⚠️ 行为与抽出前**逐字一致** ✓：
#   · 一切失败都只 `log` 提示、**绝不抛出** ✗（存档出问题不许打断训练 ✓）；
#   · 路径与文件格式一字不改 ✓（`train_progress.json` / `best_meta.json` /
#     `multi_agent_resume_best/` ✓，meta 字段名也不改 ⇒ 旧断点仍能续训 ✓）。
# ⚠️ `model` 会被替换（续训恢复 / best 恢复 ✓）⇒ 放在 `self.model` 上，
#   调用方在 model 变化后赋值一次即可 ✓。
# ⚠️ 常量全部来自 `utils/config.py` ✓ —— 改判据请改那里 ✗，不要改本文件 ✓。

_CKPT_MARKERS = ('rllib_checkpoint.json', 'algorithm_state.pkl', '.is_checkpoint')

# 本段自带的依赖（就地 import ✓：读这一段时不必翻到文件头 ✓）：
#   · 只引 `utils.config` 的常量 ✓（config 只依赖 stdlib + utils.base ⇒ 无环 ✓）；
#   · `ray.rllib` 的 SAC **不在这里** import ✗ —— 那会让 eval 入口在 import 期就把 ray 拉起来 ✓，
#     所以只在 restore_best() 真正要恢复那份存档时才 import ✓（与本文件 load_multi_agent_checkpoint 同款 ✓）。
import json      # noqa: E402
import time      # noqa: E402

from utils.config import (          # noqa: E402
    BEST_CKPT_DIR_NAME,
    BEST_CKPT_META,
    BEST_CKPT_METRIC_VER,
    BEST_CKPT_TARGET_SUM,
    BEST_CKPT_TIEBREAK,
    CKPT_PROGRESS,
    P4_COST_WEIGHT,
    CUSTOM_REWARD_KWARGS,
    REWARD_CONFIG_SIDECAR,
)
from utils.env import get_cool_floor_scale, set_cool_floor_scale   # noqa: E402


# RLlib checkpoint 目录标记（与 utils/checkpoint_utils 里的标记一致 ✓） ✓
def is_ckpt_dir(d) -> bool:
    return Path(d).is_dir() and any((Path(d) / m).exists() for m in _CKPT_MARKERS)


# 把 root 解析成真正的 RLlib checkpoint 目录（找不到返回 None ✓） ✓
def resolve_ckpt_dir(root):
    root = Path(root)
    if is_ckpt_dir(root):
        return root
    if not root.is_dir():
        return None
    cands = sorted(
        (c for c in root.iterdir()
         if c.is_dir() and (c.name.startswith('checkpoint') or is_ckpt_dir(c))),
        key=lambda x: x.name,
    )
    for c in reversed(cands):
        if is_ckpt_dir(c):
            return c
    return None


class CkptManager:
    """训练期的 checkpoint / best 快照管家（原 Multi-agent.py 里 8 个嵌套函数 ✓）。"""

    # CkptManager 的构造：记下 checkpoint 目录、是否启用、总轮数、best 开关与日志函数 ✓
    def __init__(self, ckpt_dir: Union[str, Path], *, enabled: bool, train_epochs: int,
                 best_enabled: bool = False, model: Any = None,
                 log: Optional[LogFn] = None) -> None:
        self.log = log or (lambda _msg: None)
        self.dir = Path(ckpt_dir)
        self.enabled = bool(enabled)
        self.train_epochs = int(train_epochs)
        self.model = model
        self.progress_path = self.dir / CKPT_PROGRESS
        # "最好一轮"的存档与 ckpt_dir **同级** ✓：只在「中期评估创新低」时写入，不被定期保存覆盖 ✓，
        #   训练结束后用它替换 model 做正式评估（治"末次权重比历史最优差很多"的漂移问题 ✓）。
        self.best_enabled = bool(best_enabled)
        self.best_dir = self.dir.parent / BEST_CKPT_DIR_NAME
        self.best_meta_path = self.best_dir / BEST_CKPT_META
        # "最好一轮"的评选指标（写进 train_progress 文件 + 续训跨进程继承）✓：
        #   metric = Σ max(0, 各栋「高温+低温」合计 − BEST_CKPT_TARGET_SUM)
        #            + BEST_CKPT_TIEBREAK × Σ(各栋合计)                    ← 用它选（判据见 config.py）
        #   worst  = max(高温) + max(低温)                                ← 仅记录/日志
        #   用**可变容器**而非普通变量 ✓：write_progress 要读到最新值 ✓。
        #   另含 'src' —— 指标来源（'full' = 用整段评估算的真 KPI / 'mid' = 中期试跑的粗略值 ✓）：
        #   续训时若来源变了，两者数值量级不可比 ⇒ 必须重置基线 ✓。
        self.best_state = {'metric': None, 'epoch': None, 'worst': None, 'src': None}

    # ---- train_progress.json ------------------------------------------------
    # 读 train_progress.json（已训练轮数 / best 成绩 / 历史 ✓）；没有就返回空 dict ✓
    def read_progress(self) -> dict:
        try:
            with open(self.progress_path, encoding='utf-8') as fh:
                return json.load(fh) or {}
        except Exception:
            return {}

    # 把已训练轮数 / best 成绩 / 中期评估历史写进 train_progress.json ✓
    def write_progress(self, epochs_done: int, best_score=None, history=None) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            prev = self.read_progress()
            # P19-1（续训继承曲线修复）：本次没产生新的中期评估（history 为空/None）时，
            #   保留断点里已有的曲线，绝不用空数组覆盖 ✓。触发场景：
            #     · 续训且 epochs_done ≥ 目标轮数 → 跳过训练直接评估 ⇒ 本进程没有新 mid-eval；
            #     · 中期评估试跑创建失败 / MINI_EVAL_EVERY<=0 ⇒ 循环里从不追加历史；
            #     · CKPT_EVERY 定期保存在第一个 mid-eval 之前（此时历史为空 ✓）。
            #   旧写法用 `history is not None` 判断 ⇒ 空列表会被当成"有效值" ✗ →
            #   把源任务积累的曲线清空，且此后每次续训继承到的都是空曲线（曲线永久丢失 ✗）。
            _prev_hist = prev.get('mid_eval_history') or []
            _hist_out = history if history else _prev_hist
            payload = {
                'epochs_done': int(epochs_done),
                'best_score': (float(best_score) if best_score is not None
                               else prev.get('best_score')),
                # best-ckpt 的选择指标（最大单栋合计）+ 对应轮号。
                #   本进程有值用本进程的，否则沿用断点里的（续训未产生新 mid-eval 时不清空 ✓）。
                'best_metric': (float(self.best_state['metric'])
                                if self.best_state['metric'] is not None
                                else prev.get('best_metric')),
                # 指标算法版本号 —— 续训时用它判断断点里的 best_metric 还能不能直接比 ✓
                #   （算法变了就拒绝继承，否则旧算法的极小值会压住新算法保存的所有存档 ✗）。
                'best_metric_ver': int(BEST_CKPT_METRIC_VER),
                'best_metric_epoch': (int(self.best_state['epoch'])
                                      if self.best_state['epoch'] is not None
                                      else prev.get('best_metric_epoch')),
                # 指标来源（'full'/'mid'）。续训时用它判断基线是否可比 ✓
                'best_metric_src': (str(self.best_state.get('src'))
                                    if self.best_state.get('src') is not None
                                    else prev.get('best_metric_src')),
                'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
                'train_epochs_target': int(self.train_epochs),
                # 中期评估历史（逐次逐栋 hot/cold）：续训时用它把「不适曲线 + 早停判据基线」
                #   一起继承 ✓ —— 以前只存轮数/最好分 ⇒ 续训后曲线从断点处重新开始、
                #   逐栋历史最优与各计数器全部丢失（判据③的基线等于被重置 ✗）。
                'mid_eval_history': _hist_out,
            }
            with open(self.progress_path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.log(f'[checkpoint] 写 {CKPT_PROGRESS} 失败（忽略）: {exc}')

    # ---- 保存 / 恢复 --------------------------------------------------------
    # 保存 RLlib SAC 状态 + 轮数进度 + 中期评估历史（失败只提示 ✓） ✓
    def save(self, tag: str, epochs_done: int, best_score=None, history=None) -> None:
        if not self.enabled:
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            # 存断点 + 顺手写奖励配置（两件事都在这个函数里 ✓，2026-10-08 合并 ✓）
            save_multi_agent_checkpoint(self.model, self.dir, log_console=self.log)
            self.write_progress(epochs_done, best_score, history)
            saved = resolve_ckpt_dir(self.dir) or self.dir
            self.log(f'[checkpoint] {tag}：已保存到 {saved}（累计 {epochs_done} 轮）')
        except Exception as exc:
            self.log(f'[checkpoint] {tag}：保存失败（忽略，不影响训练）: '
                     f'{type(exc).__name__}: {exc}')

    # 读 best_meta.json（best 轮号 / 选择指标 / 逐栋合计 ✓）；没有就返回空 dict ✓
    def read_best_meta(self) -> dict:
        try:
            with open(self.best_meta_path, encoding='utf-8') as fh:
                return json.load(fh) or {}
        except Exception:
            return {}

    # "超标面积"创新低时保存"最好一轮"的存档（失败只提示 ✓） ✓
    def save_best(self, epoch: int, metric: float, sums, worst_sum=None,
                  src: str = 'mid', cost_term: float = 0.0) -> None:
        if not self.best_enabled:
            return
        try:
            self.best_dir.mkdir(parents=True, exist_ok=True)
            # 存"最好一轮"的存档 + 顺手把奖励配置写进断点目录 ✓
            save_multi_agent_checkpoint(self.model, self.best_dir, log_console=self.log)

            # 把值转成 float；转不了就给 0.0 ✓
            def _num(v):
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    return None
                return float(fv) if np.isfinite(fv) else None

            payload = {
                'best_epoch': int(epoch),
                # best_metric = 选择指标；best_score 保留"最差和"（兼容旧读取方 + 日志对比 ✓）
                'best_metric': float(metric),
                'best_score': (_num(worst_sum) if worst_sum is not None
                               and np.isfinite(worst_sum) else _num(metric)),
                'best_sums': [_num(v) for v in sums] if sums else [],
                'best_metric_src': str(src),      # 'full' / 'mid'
                # 指标第三项（P4_COST_WEIGHT×成本率）+ 权重 ⇒ 便于事后判断"这次选择
                #   是被舒适还是被成本决定的" ✓。
                'best_cost_term': _num(cost_term),
                'p4_cost_weight': float(P4_COST_WEIGHT),
                # 记下那次存档训练时的下界衰减系数 ✓：正式评估前恢复它，保证"评估所用的
                #   动作映射"与"该权重训练时的映射"一致（best 落在衰减期内时为 0~1 ✓）。
                #   ⚠️ 走 getter 读 utils/env.py 的**当前**值：import 进来的
                #   COOL_FLOOR_SCALE 只是当时的取值副本 ✗，会与真值悄悄不一致 ✗。
                'cool_floor_scale': get_cool_floor_scale(),
                'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            with open(self.best_meta_path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            # 交给 write_progress 写进文件（续训时跨进程继承 ✓）
            self.best_state['metric'] = float(metric)
            self.best_state['epoch'] = int(epoch)
            self.best_state['worst'] = (_num(worst_sum) if worst_sum is not None
                                        and np.isfinite(worst_sum) else None)
            self.best_state['src'] = str(src)
            saved = resolve_ckpt_dir(self.best_dir) or self.best_dir
            _sum_txt = (' / '.join(f'B{k + 1} {v:.1%}' for k, v in enumerate(sums))
                        if sums else 'na')
            _ws_txt = (f'最差和={float(worst_sum):.3f}，'
                       if worst_sum is not None and np.isfinite(worst_sum) else '')
            _src_txt = ('全口径 KPI 评估' if str(src) == 'full' else 'mid-eval 代理')
            # 把第三项（成本项）也打出来 —— 否则日志里"分量和 ≠ 指标"会被误读 ✗。
            _cost_txt = ''
            try:
                _ct = float(cost_term or 0.0)
            except (TypeError, ValueError):
                _ct = 0.0
            if _ct and float(P4_COST_WEIGHT) > 0.0:
                _cost_txt = (f' + {float(P4_COST_WEIGHT):g}×成本率'
                             f' {_ct / float(P4_COST_WEIGHT):.4f} = {_ct:.4f}')
            # 把指标的两个分量都打出来 —— 否则"全部达标时指标非 0"会被误读 ✗。
            try:
                _prim = (float(sum(max(0.0, float(v) - BEST_CKPT_TARGET_SUM) for v in sums))
                         if sums else float('nan'))
                _sum_all = float(sum(float(v) for v in sums)) if sums else float('nan')
            except (TypeError, ValueError):
                _prim = _sum_all = float('nan')
            self.log(
                f'[best-ckpt] 第 {epoch} 轮创新低（{_src_txt}，指标={metric:.4f}'
                f' = 超标面积 {_prim:.4f} + {BEST_CKPT_TIEBREAK:g}×Σ合计 {_sum_all:.4f}'
                f'{_cost_txt}，'
                f'{_ws_txt}逐栋 {_sum_txt}）→ 已存最优快照到 {saved}'
            )
        except Exception as exc:
            self.log(f'[best-ckpt] 保存失败（忽略，不影响训练）: '
                     f'{type(exc).__name__}: {exc}')

    # 训练结束、正式评估前：如果有"最好一轮"的存档就加载替换 model。返回 (model, meta) ✓
    def restore_best(self):
        if not self.best_enabled:
            return None, None
        meta = self.read_best_meta()
        resolved = resolve_ckpt_dir(self.best_dir)
        # 优先看 best_metric，兼容 P5-A 之前只写 best_score 的旧 meta ✓
        if resolved is None or not (meta.get('best_metric') or meta.get('best_score')):
            self.log('[best-ckpt] 未找到可用最优快照 → 仍用末次权重评估')
            return None, None
        try:
            from ray.rllib.algorithms.sac import SAC   # 就地 import ✓：不拖累 eval 入口的 import 期 ✓
            best_model = SAC.from_checkpoint(str(resolved))
            # 恢复那次存档训练时的下界衰减系数 ✓ —— 评估阶段的环境会读这个模块级值；
            #   否则用 SCALE=0 的映射去跑"在 SCALE>0 下训练出的权重"会不自洽 ✗。
            try:
                _sc_saved = meta.get('cool_floor_scale')
                if _sc_saved is not None:
                    # ⚠️ 必须走 setter：COOL_FLOOR_SCALE 住在 utils/env.py，环境类
                    #   读的是**那里的**模块全局 ⇒ 在本文件里直接赋值只会写到一个没人读的名字上 ✗
                    _sc_restored = set_cool_floor_scale(_sc_saved)
                    self.log(
                        f'[best-ckpt] 已恢复该快照的下界系数 scale={_sc_restored:.3f}'
                    )
            except (TypeError, ValueError):
                pass
            return best_model, meta
        except Exception as exc:
            self.log(f'[best-ckpt] 加载失败（改用末次权重评估）: '
                     f'{type(exc).__name__}: {exc}')
            return None, None


#============================================================================
# 奖励算法 / 动作映射 总览（2026-10-07 从 Multi-agent.py 的 `__main__` 抽出 ✓）
#============================================================================
#   原处那 50 行只做一件事：把**本次实际生效**的奖励配置与动作映射打给人看 ✓。抽到这里的理由：
#     · 它只读常量 + action_hook_status()（就在本文件 ✓）⇒ 无环境/训练态依赖 ✓；
#     · 训练入口 `__main__` 因此少 49 行 ✓；评估入口的那一段由生成器的 EVAL_SETUP_BLOCK
#       整段替换 ⇒ **评估入口不会调用本函数** ✓（所以下面的导入在评估侧也会被一起裁掉 ✓）；
#     · 打印内容与语序**逐字未改** ✓（有专门的比对脚本 ✓：见 _q 系列脚本的 banner 比对 ✓）。
#   ⚠️ 调用点必须与抽取前**同位置**：`log_console(初始化 SAC 多智能体…)` 之后、
#      `训练 schema=…` 之前 ✓（顺序一换，日志行序就变了 ✗）。
#============================================================================
# 打印"奖励怎么算 + 动作怎么映射"总览（内容逐字搬自 Multi-agent.py ✓） ✓
def log_reward_banner(log: Callable[[str], None] = log_console) -> None:
    from utils.config import CUSTOM_REWARD_KWARGS, USE_CUSTOM_REWARD
    from utils.env import (        # noqa: E402
        COOL_FLOOR_ENABLE,
        COOL_LOAD_CENTERED_ENABLE,
        COOL_LOAD_MAX_FRAC,
        COOL_LOAD_MIN_FRAC,
        COOL_REMAP_FLOOR,
        COOL_REMAP_SPAN,
        COOL_SPAN_ENABLE,
    )

    if not USE_CUSTOM_REWARD:
        log('奖励函数=数据集 schema 默认 ComfortReward（USE_CUSTOM_REWARD=False）')
        return
    log(
        f'奖励函数=CustomComfortReward（替换数据集默认，参数={CUSTOM_REWARD_KWARGS}；'
        f'可用 --check-reward 自检与原版一致性）'
    )
    log(
        '[奖励] P3′ 电池套利项：'
        + (f'启用（择时权重={CUSTOM_REWARD_KWARGS.get("bat_weight")}，'
           f'损耗权重={CUSTOM_REWARD_KWARGS.get("bat_loss_weight")}；'
           f'r_arb = −w×max(0, price−p_ref)×(充电−有效放电)'
           f' ⇒ 平价中性、高峰(16~18时)放=大奖、高峰充=重罚；'
           f'r_loss = −w_loss×price×(充电−有效放电) ⇒ 给净循环(买了未用于负载的电)定价；'
           f'只含电池、与制冷解耦）'
           if float(CUSTOM_REWARD_KWARGS.get('bat_weight') or 0.0) > 0.0 else
           '关闭（bat_weight=0）⇒ 储能维无引导（= 0e6894aa 的现状：B2 吞吐 760kWh、成本 +15.6%）')
    )
    log(
        f'奖励动作注入={action_hook_status()}（过热保底/过冷关冷项需要读到 act_cool；'
        f'决策推演里应能看到 R_act_hot / 目标开度 a_need）'
    )
    log(
        f'[动作重标定] P-1：'
        + (f'负荷跟随映射 applied = a_ref × ({COOL_LOAD_MIN_FRAC:g} + '
           f'{COOL_LOAD_MAX_FRAC - COOL_LOAD_MIN_FRAC:g}×a)（**全局统一**；'
           f'a_ref = 本步理想负荷所需开度，a=0.5 ⇒ 倍率 1.0 = 恒等跟随 = 无控制基线）'
           if COOL_LOAD_CENTERED_ENABLE else
           (f'P2 动作缩放=span {COOL_REMAP_SPAN:g}（**全局统一**，applied = span×a）'
            if COOL_SPAN_ENABLE else
            '重标定已关闭 → 冷却动作 = 策略原始输出'))
        + (f' ｜ 回退映射 floor {COOL_REMAP_FLOOR:g} / span {COOL_REMAP_SPAN:g}'
           f'（仅在 a_ref 取不到的步生效）'
           if COOL_LOAD_CENTERED_ENABLE else
           (f' ｜ 动作下界=floor {COOL_REMAP_FLOOR:g}（**全局统一**）'
            if COOL_FLOOR_ENABLE else ' ｜ 动作下界已关闭'))
        + '\n  生效范围：训练/中期评估/全口径评估/正式评估（四处同用 _AGENT_ENV_CLS）'
        + (
            '\n  目标开度 a_need：口径=load（Step 2 理想负荷导出：'
            'a_ref = 数据集预计算理想负荷 ÷ 本步热容量，热容量=额定功率×当前COP；'
            '逐时逐栋由物理量算出 ⇒ 无手挑常数、无按楼写死值）'
            if str(CUSTOM_REWARD_KWARGS.get('hot_a_need_mode', 'const')).lower() == 'load' else
            '\n  目标开度 a_need：口径=const（旧常数式 hot_act_floor + hot_a_per_c×over）'
        )
        + (f'\n  Step2A 过吹罚：权重={CUSTOM_REWARD_KWARGS.get("hot_over_weight")}'
           f' 容差={CUSTOM_REWARD_KWARGS.get("hot_over_tol")}'
           f'（开度 > a_ref+容差 时罚，仅在过热保底未生效时计入）'
           if float(CUSTOM_REWARD_KWARGS.get('hot_over_weight') or 0.0) > 0.0 else
           '\n  Step2A 过吹罚：已关闭（hot_over_weight=0）')
    )

# ============ 以下正文合并自 utils/train.py ============
# -*- coding: utf-8 -*-

import time
from typing import Any, Callable, Optional, Sequence

import numpy as np

from utils.config import (
    BEST_CKPT_TIEBREAK,
    MID_CONVERGE_PATIENCE,
    MID_CONVERGE_SUM,
    MID_TARGET_COLD,
    MID_TARGET_HOT,
    MID_VOTE_PATIENCE,
    MID_VOTE_RATIO,
    MID_WORSEN_MARGIN,
    MID_WORSEN_PATIENCE,
    MIN_SAMPLE_TIMESTEPS_PER_ITERATION,
    P4_COST_HINGE,
    P4_COST_WEIGHT,
    ROLLOUT_FRAGMENT_LENGTH,
    TRAIN_BATCH_SIZE,
    TRAIN_INTENSITY,
)
from utils.env import unwrap_citylearn_env
from utils.base import log_console
from dataclasses import dataclass
from utils.config import (
    BEST_CKPT_ENABLE,
    BEST_CKPT_METRIC_VER,
    BEST_CKPT_MIN_GAIN,
    BEST_CKPT_TARGET_SUM,
    CKPT_ENABLE,
    CKPT_EVERY,
    CKPT_PROGRESS,
    CKPT_STORE_REPLAY_BUFFER,
    CRASH_GUARD_EPOCH,
    CRASH_GUARD_MAX_COLD,
    CRASH_GUARD_MAX_HOT,
    MID_EVAL_WINDOWS,
    MID_KPI_SRC_TOL,
    MID_MIN_GAIN,
    MID_PATIENCE,
    MID_STOP_BY_SCORE,
    MID_STOP_BY_VOTE,
    MID_STOP_ON_CRASH,
    MID_STOP_ON_WORSEN,
    MID_STOP_WHEN_CONVERGED,
    MID_STOP_WHEN_GOOD,
    MINI_EVAL_EVERY,
    MINI_EVAL_STEPS,
    MIN_SAMPLE_BEFORE_LEARN,
    Path,
    TRAIN_BATCHES_PER_ROUND_MIN,
    _SAMPLE_TARGET_BASE,
    __file__,
    log_console,
    time,
)
from utils.env import (
    COOL_FLOOR_ENABLE,
    COOL_REMAP_FLOOR,
    _AGENT_ENV_CLS,
    build_probe_env,
    np,
    update_cool_floor_scale,
)
from dataclasses import dataclass

LogFn = Callable[[str], None]


# ---------------------------------------------------------------------------
# P-4：无控制基线的成本项（原为 `__main__` 里的嵌套函数 `_p4_cost_term` ✓）
# ---------------------------------------------------------------------------
# P-4：成本项 = 权重 × 成本率（线性） + P-13 的"超过目标线才罚"部分 ✓
def p4_cost_term(stats_like: Any, p4_cost_ref: Any) -> float:
    try:
        ref = float((p4_cost_ref or {}).get('raw') or 0.0)
        cur = float((stats_like or {}).get('cost_raw') or 0.0)
        if ref <= 0.0 or cur <= 0.0:
            return 0.0
        ratio = cur / ref
        term = 0.0
        if float(P4_COST_WEIGHT) > 0.0:
            term += float(P4_COST_WEIGHT) * ratio
        _hw = float(P4_COST_HINGE.get('w') or 0.0)
        if _hw > 0.0:
            # 只在超过目标线时给分 ⇒ 达标轮之间仍按舒适排序 ✓
            term += _hw * max(0.0, ratio - float(P4_COST_HINGE.get('target') or 0.0))
        return float(term)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# 训练收尾汇总（原为 `__main__` 里循环之后的一大段 print ✓）
# ---------------------------------------------------------------------------
# 把训练结束后的这段时间里"人最想知道的几件事"一次打完 ✓（早停原因 / 曲线 / 收敛 / 采样量 / 奖励统计） ✓
def log_training_summary(
    *,
    log: Optional[LogFn] = None,
    model: Any,
    stopped_reason: Optional[str],
    last_epoch: int,
    start_epoch: int,
    train_epochs: int,
    train_secs: float,
    sampled: float = 0,
    mid_best: Optional[float] = None,
    mid_prev_sums: Optional[Sequence[float]] = None,
    mid_vote_stale: int = 0,
    mid_best_sums: Optional[Sequence[float]] = None,
    mid_worsen: Optional[Sequence[int]] = None,
    mid_conv: Optional[Sequence[int]] = None,
) -> None:
    log = log or (lambda _msg: None)
    if stopped_reason:
        _remain_min = ((train_epochs - last_epoch) * train_secs
                       / max(1, last_epoch - start_epoch) / 60)
        log(
            f'[早停] 训练提前结束：{stopped_reason}'
            f'（实际跑到 {last_epoch}/{train_epochs} 轮，省下约 {_remain_min:.1f} 分钟）'
        )
    # 训练后是否值得继续跑正式评估：给一句明确结论，便于人工判断
    if mid_best is not None:
        log(
            f'[中期评估] 训练期最好「最差和」={float(mid_best):.3f}'
            f'（= max高温 + max低温，达标线 {MID_TARGET_HOT + MID_TARGET_COLD:.2f}）'
        )
    if mid_prev_sums is not None:
        _need_all = max(1, int(np.ceil(MID_VOTE_RATIO * len(mid_prev_sums))))
        log(
            '[中期评估] 末次逐栋合计(高温+低温)='
            + ' / '.join(f'B{k + 1} {v:.1%}' for k, v in enumerate(mid_prev_sums))
            + f' | 投票未过线计数 {mid_vote_stale}/{MID_VOTE_PATIENCE}'
            f'（判定线：优于上次的楼数 ≥{_need_all}/{len(mid_prev_sums)}）'
        )
    if mid_best_sums:
        log(
            '[中期评估] 逐栋历史最优合计(高温+低温)='
            + ' / '.join(f'B{k + 1} {v:.1%}' for k, v in enumerate(mid_best_sums))
            + ' | 末次恶化计数 '
            + ' / '.join(f'B{k + 1} {v}/{MID_WORSEN_PATIENCE}'
                         for k, v in enumerate(mid_worsen or []))
            + f'（判定线：高于自身最优 +{MID_WORSEN_MARGIN:.0%} 连续 {MID_WORSEN_PATIENCE} 次即停）'
        )
    if mid_conv:
        log(
            '[中期评估] 末次收敛标记 '
            + ' / '.join(
                f'B{k + 1} {"已收敛" if c >= MID_CONVERGE_PATIENCE else "未收敛"}'
                f'（连续 {c}/{MID_CONVERGE_PATIENCE}）'
                for k, c in enumerate(mid_conv)
            )
            + f'（阈值 合计<{MID_CONVERGE_SUM:.0%}；全楼已收敛才停训）'
        )

    _epochs_ran = last_epoch     # 已跑到的绝对轮数（早停时会 < train_epochs）
    _ran_this = max(0, _epochs_ran - start_epoch)   # 本次进程实跑的轮数
    log(
        f'训练用时 {train_secs / 60:.1f} 分钟（本次实跑 {_ran_this} 轮，'
        f'累计 {_epochs_ran}/{train_epochs} 轮，'
        f'平均 {train_secs / max(1, _ran_this):.1f}s/轮）'
        f' | 训练累计采样={int(sampled)} env-step（agent-step ≈ ×楼栋数）'
        f' | C′-3 口径（旧文案"每轮采样量=fragment×env_runners"已被证伪 ✗，该旋钮也已撤下 ✓）：'
        f'每轮采样量 ≈ max(min_sample_timesteps_per_iteration({MIN_SAMPLE_TIMESTEPS_PER_ITERATION})，'
        f'采样权重×fragment({ROLLOUT_FRAGMENT_LENGTH}))（单进程采样 ⇒ worker 数恒为 1 ✓）；'
        f'每轮训练批数 = ⌈min_sample ÷(采样权重×fragment)⌉ × 训练权重'
        f'（train_batch_size={TRAIN_BATCH_SIZE}，training_intensity={TRAIN_INTENSITY:.4g}）。'
        f'逐轮真实值看进度行的「重放比≈X(env口径)」与「训练=N批/轮」'
    )

    # 训练阶段「奖励项是否真的生效」的关键诊断：
    # 读到动作的次数应远大于 0；若为 0，说明动作注入在训练时没生效（那 B1 就不会学开冷）。
    train_env = getattr(model, 'env_runner', None)
    train_env = getattr(train_env, 'env', train_env)
    ce_train = unwrap_citylearn_env(train_env)
    rf_train = getattr(ce_train, 'reward_function', None) if ce_train is not None else None
    if rf_train is not None and hasattr(rf_train, 'stats_summary'):
        log('[训练阶段] ' + rf_train.stats_summary())
        rf_train.stats_reset()
    else:
        log('[训练阶段] 未取到训练环境奖励函数，跳过统计（不影响训练）')


# ---------------------------------------------------------------------------
# P2-D：把 model 换成训练期表现最好的那一版存档
# ---------------------------------------------------------------------------
# 训练结束、正式评估前：如果有"最好一轮"的存档就返回它（否则返回 None ⇒ 调用方仍用末次权重 ✓） ✓
def restore_best_model(ckpt: Any, *, last_epoch: int,
                       log: Optional[LogFn] = None) -> Any:
    log = log or (lambda _msg: None)
    _best_model, _best_meta = ckpt.restore_best()
    if _best_model is None:
        return None
    _b_sums = _best_meta.get('best_sums') or []
    _sum_txt = ('，逐栋合计 ' + ' / '.join(
        f'B{k + 1} {"na" if v is None else f"{float(v):.1%}"}'
        for k, v in enumerate(_b_sums))) if _b_sums else ''
    # 优先展示选择指标（超标面积），并附最差和供跨版本对比；
    # 再标注指标来源 —— 'full' = 用整段评估算的真 KPI（可信）；'mid' = 中期试跑的粗略值
    #   （与真 KPI 没有单调关系；看到 'mid' 就说明这次没用整段评估，结论要打折）。
    _bm = _best_meta.get('best_metric')
    _bs = _best_meta.get('best_score')
    _bsrc = _best_meta.get('best_metric_src')
    _bsrc_txt = ('全口径 KPI 评估' if _bsrc == 'full'
                 else ('mid-eval 代理' if _bsrc == 'mid' else '来源未知(旧快照)'))
    if _bm is not None:
        _metric_txt = f'超标面积={float(_bm):.3f}（来源：{_bsrc_txt}）'
        if _bs is not None:
            _metric_txt += f'（最差和={float(_bs):.3f}）'
    elif _bs is not None:
        _metric_txt = f'最差和={float(_bs):.3f}（旧快照，无超标面积指标）'
    else:
        _metric_txt = '指标=na'
    log(
        f'[best-ckpt] 正式评估改用最优快照：第 {_best_meta.get("best_epoch")} 轮，'
        f'{_metric_txt}{_sum_txt}'
        f'（末次权重为第 {last_epoch} 轮；--no-best-ckpt 可关闭此行为）'
    )
    return _best_model


# ---------------------------------------------------------------------------
# 训练试跑 / 累加器准备 + 训练主循环（2026-10-06 从 Multi-agent.py 整段搬来 ✓）
# ---------------------------------------------------------------------------
# 搬运方式（关键 ✗✓）：
#   · 段内代码**一字未改** ✓ —— 需要的名字全部由**函数签名**声明（关键字参数 ⇒ 同名局部 ✓），
#     结果再打包成 TrainOutcome 返回 ✓。这样就不用在 1200 行里改名 ✗
#     （改名最容易改坏：f-string 里的表达式、关键字参数、属性基名 ✗）。
#   · 本段在 eval 生成时本来就整段被替换掉 ✓ ⇒ 搬到哪都不会影响评估入口 ✓。
#   · 日志仍走 `log_console` 这个名字 ✓：函数开头把它指到传入的 `log` ✓（段内一字不改 ✓）。
# ---------------------------------------------------------------------------
@dataclass


# ---------------------------------------------------------------------------
# 训练试跑 / 累加器准备 + 训练主循环（2026-10-06 从 Multi-agent.py 整段搬来 ✓）
# ---------------------------------------------------------------------------
# 搬运方式（关键 ✗✓）：
#   · 段内代码**一字未改** ✓ —— 需要的名字全部由**函数签名**声明（关键字参数 ⇒ 同名局部 ✓），
#     结果再打包成 TrainOutcome 返回 ✓。这样就不用在 1200 行里改名 ✗
#     （改名最容易改坏：f-string 里的表达式、关键字参数、属性基名 ✗）。
#   · 本段在 eval 生成时本来就整段被替换掉 ✓ ⇒ 搬到哪都不会影响评估入口 ✓。
#   · 日志仍走 `log_console` 这个名字 ✓：函数开头把它指到传入的 `log` ✓（段内一字不改 ✓）。
# ---------------------------------------------------------------------------
@dataclass
class TrainOutcome:
    """训练主循环结束后，调用方（收尾汇总 / 存盘 / best 快照替换）还需要的那几个量 ✓。"""

    _last_epoch: Any = None
    _mid_best: Any = None
    _mid_best_sums: Any = None
    _mid_conv: Any = None
    _mid_eval_hist: Any = None
    _mid_prev_sums: Any = None
    _mid_vote_stale: Any = None
    _mid_worsen: Any = None
    _sampled_prev: Any = None
    _start_epoch: Any = None
    _stopped_reason: Any = None
    _t_train0: Any = None
    ckpt: Any = None
    ckpt_dir: Any = None
    model: Any = None


# 训练试跑准备 + 主循环（原封不动搬自 Multi-agent.py 的 `__main__` ✓，见段头说明 ✓） ✓
def run_training(
    *,
    log: Optional[LogFn] = None,
    _rb_kwargs: Any,
    args: Any,
    eval_schema: Any,
    min_train_epochs: Any,
    output_dir: Any,
    seed: Any,
    train_env_config: Any,
    train_epochs: Any,
) -> TrainOutcome:
    log_console = log or (lambda _msg: None)   # 段内仍写作 log_console(...) ✓ ⇒ 一字不改
    # 段内用到的 ray 侧名字：**就地 import** ✓（本模块只被训练入口 import ✓，
    # 所以不会像放在文件顶部那样把 ray 拖进评估入口的 import 期 ✗）
    from ray.rllib.algorithms.sac import SACConfig as Config
    from ray.rllib.policy.policy import PolicySpec
    from utils.env import unwrap_citylearn_env as _unwrap_citylearn_env
    probe = _AGENT_ENV_CLS(train_env_config)
    config = (
        Config()
        .environment(_AGENT_ENV_CLS, env_config=train_env_config)
        .multi_agent(
            policies={a: PolicySpec() for a in probe._agent_ids},
            policy_mapping_fn=lambda agent_id, episode, worker, **kwargs: agent_id,
        )
        # 训练量：每轮采样多少步 + 开始学习前先攒多少步（方案②）
        .training(
            train_batch_size=TRAIN_BATCH_SIZE,
            # C′-2：把训练强度写死（None = 用 RLlib 默认权重 [1,1]，
            #   含义与两条重要性质见文件顶部 TRAIN_INTENSITY 处注释）
            training_intensity=TRAIN_INTENSITY,
            num_steps_sampled_before_learning_starts=MIN_SAMPLE_BEFORE_LEARN,
            # 经验池随 checkpoint 保存/恢复（治"续训后策略翻转"，
            #   机制与实测证据见文件顶部 CKPT_STORE_REPLAY_BUFFER 处注释）
            store_buffer_in_checkpoints=CKPT_STORE_REPLAY_BUFFER,
            **_rb_kwargs,
        )
        # 采样进程数固定 0 = driver 单进程（Windows 下最稳 ✓）；`--env-runners` 已于 2026-10-07 撤下 ✗
        .rollouts(
            # 单进程采样 ✓（`--env-runners` 已于 2026-10-07 撤下 ✗：Ray worker 装不上动作注入钩子、
            #   也读不到 COOL_FLOOR_SCALE 这类模块级全局 ⇒ 会让奖励的动作项**静默为 0** ✗）
            num_rollout_workers=0,
            rollout_fragment_length=ROLLOUT_FRAGMENT_LENGTH,
        )
        # C′-3：每轮采样目标。SACConfig 默认把它设成 100 —— 这正是"每轮采样固定 100"的来源
        .reporting(
            min_sample_timesteps_per_iteration=MIN_SAMPLE_TIMESTEPS_PER_ITERATION,
        )
    )
    # 默认 seed=1（DEFAULT_SEED），每次运行都显式固定，便于复现与多次实验对比
    config = config.debugging(seed=int(seed))
    # 进度行要按「楼栋数」把 env-step 折算成 agent-step，先记下来（probe 马上就删）
    _n_buildings = len(probe._agent_ids)
    del probe
    # ---- P16-1 诊断：打印 learner 侧真正生效的超参 + 预期重放比 -------------------
    try:
        _diag_keys = (
            'train_batch_size', 'num_epochs', 'minibatch_size', 'num_sgd_iter',
            'training_intensity', 'rollout_fragment_length', 'num_rollout_workers',
            'num_envs_per_worker', 'count_steps_by',
            # C′-2：下面三个共同决定「每轮采样量 / 每轮训练量」，其中
            'min_sample_timesteps_per_iteration', 'min_train_timesteps_per_iteration',
            'batch_mode',
        )
        _diag = {}
        for _k in _diag_keys:
            try:
                _diag[_k] = getattr(config, _k)
            except Exception:
                _diag[_k] = '(该版本无此键)'
        log_console('[诊断] learner 有效超参: '
                    + ' | '.join(f'{k}={v}' for k, v in _diag.items()))
        _nb = _diag.get('train_batch_size')
        _fr = _diag.get('rollout_fragment_length')
        # "auto" 在 build 之后才解析成具体值（本版=100），这里用官方 API 拿解析后的数
        if not isinstance(_fr, (int, float)):
            try:
                _fr = config.get_rollout_fragment_length()
            except Exception:
                _fr = None
            log_console(
                f'[诊断] rollout_fragment_length 配置值={_diag.get("rollout_fragment_length")} '
                f'→ 解析后={_fr}（请与进度行的「本轮采样」对照：本版 auto 应为 100 env-step/轮）'
            )
        if isinstance(_nb, (int, float)) and isinstance(_fr, (int, float)) and _fr > 0:
            _sampled = (float(_fr)
                        * max(int(_diag.get('num_rollout_workers') or 0), 1)
                        * int(_diag.get('num_envs_per_worker') or 1))
            if _sampled > 0:
                log_console(
                    '[诊断] 自然重放比(env-step 口径) = train_batch_size/(fragment×workers×envs/worker) = '
                    f'{float(_nb):.0f}/{_sampled:.0f} = {float(_nb) / _sampled:.2f}'
                    '（training_intensity=None 时 calculate_rr_weights 用 [1,1]，'
                    '即每轮只做 1 次 train_batch_size 的训练迭代）'
                )
                log_console(
                    '[诊断] 预期重放比(agent-step 口径, 进度行打印的就是它) = '
                    f'{float(_nb):.0f}/({_sampled:.0f}×{_n_buildings} 楼) = '
                    f'{float(_nb) / (_sampled * _n_buildings):.2f}'
                    '（<1 = 每轮学习量小于新采数据量）'
                )
                # ---- C′-2：把两处采样权重显式打出来（一眼能查到底用了多少）----
                _workers_d = int(_diag.get('num_rollout_workers') or 0)
                _envs_d = int(_diag.get('num_envs_per_worker') or 1)
                # 注意两个 worker 计数不同，别混用：
                _native_d = float(_nb) / max(1e-9, float(_fr) * _envs_d * max(_workers_d + 1, 1))
                _inten_d = float(TRAIN_INTENSITY or 0.0)
                if not _inten_d:
                    _weights_d = [1, 1]
                else:
                    _s_d = _inten_d / _native_d
                    _weights_d = ([int(np.round(1.0 / _s_d)), 1] if _s_d < 1
                                  else [1, int(np.round(_s_d))])
                # ★ 每次训练步的真实采样量 = 采样权重 × fragment × 并环境数 × 最大(worker,1)
                _per_step = (float(_weights_d[0]) * float(_fr) * _envs_d * max(_workers_d, 1))
                # C′-3：按「train() 反复调 training_step() 直到本轮采样 ≥ min_sample」预测每轮量
                _mst_raw = _diag.get('min_sample_timesteps_per_iteration')
                _mst_d = (float(_mst_raw) if isinstance(_mst_raw, (int, float))
                          else float(MIN_SAMPLE_TIMESTEPS_PER_ITERATION))
                _iters_d = max(1, int(np.ceil(_mst_d / max(1e-9, _per_step))))
                _samp_round = _iters_d * _per_step
                _batches_round = _iters_d * float(_weights_d[1])
                _trained_round = _batches_round * float(_nb)
                _utd_d = _trained_round / max(1e-9, _samp_round)
                # 配比自检：intensity 必须与「数据目标/训练目标」一致，否则配比被破坏
                _want_inten = float(_nb) * (_SAMPLE_TARGET_BASE / max(1e-9, _mst_d))
                _inten_ok = abs(_inten_d - _want_inten) < 1e-6 * max(1.0, _want_inten)
                _chk_txt = ('✓ 配比自检通过' if _inten_ok
                            else f'⚠ 配比自检不一致：按目标 intensity 应为 {_want_inten:.4g}')
                log_console(
                    f'[训练量] C′-3 口径：min_sample_timesteps_per_iteration={_mst_d:.0f}'
                    f'（SAC 默认 100）| TRAIN_INTENSITY={_inten_d:.4g}'
                    f' → round-robin 权重={_weights_d}\n'
                    f'  native_ratio = {float(_nb):.0f}/(fragment={float(_fr):.0f}'
                    f'×envs/worker={_envs_d}×max(workers+1,1)={max(_workers_d + 1, 1)}) = {_native_d:.2f}\n'
                    f'  每次 training_step：采样={_per_step:.0f} env-step、训练={_weights_d[1]} 批\n'
                    f'  预测每轮：迭代 {_iters_d} 次 → 采样≈{_samp_round:.0f} env-step、'
                    f'训练≈{_batches_round:.0f} 批={_trained_round:.0f} 条、'
                    f'trained/sampled≈{_utd_d:.0f}\n'
                    f'  {_chk_txt}（intensity = train_batch_size×(100/min_sample)，两者必须一起改）'
                )
    except Exception as _diag_exc:
        log_console(f'[诊断] 打印 learner 超参失败（忽略）: {_diag_exc}')
    # ---- checkpoint 目录（P14-1 的"续训"已于 2026-10-07 撤下 ✓）----------------
    ckpt_enabled = CKPT_ENABLE and not bool(getattr(args, 'no_checkpoint', False))
    # ⚠️ 2026-10-07 修 ✗：原先这里写的是 `Path(__file__).resolve().parent / ckpt_dir` ——
    #   本文件在 utils/ 下 ⇒ 那个基准是 **utils/** ✗✗ ⇒ 不传 --checkpoint-dir 时 checkpoint
    #   会落到 `utils/checkpoints/…`，而**评估侧**读的是 DEFAULT_CHECKPOINT_DIR
    #   （= CITYLEARNPY_DIR / CKPT_DIR = citylearnpy/checkpoints/… ✓）
    #   ⇒ 训练写一处、评估读另一处（"没传参数就找不到断点" ✗）。现在两边**同一个常量** ✓。
    from utils.config import DEFAULT_CHECKPOINT_DIR   # noqa: E402（与评估侧同源 ✓）
    if getattr(args, 'checkpoint_dir', None):
        ckpt_dir = Path(args.checkpoint_dir)          # 显式给了 ⇒ 相对路径仍以包根目录为基准 ✓
        if not ckpt_dir.is_absolute():
            from utils.base import CITYLEARNPY_DIR    # noqa: E402
            ckpt_dir = CITYLEARNPY_DIR / ckpt_dir
    else:
        ckpt_dir = Path(DEFAULT_CHECKPOINT_DIR)       # 没给 ⇒ 与评估侧**同一常量** ✓
    ckpt_progress_path = ckpt_dir / CKPT_PROGRESS
    _start_epoch = 0
    # "最好一轮"的评选指标（随训练进度写盘 ✓，给前端曲线与诊断看 ✓）
    # 训练存档（进度 / 定期存档 / "最好一轮"存档）已下沉到 utils/train.py 的 CkptManager ✓
    # （同一段曾被**粘贴两遍** —— 合并遗留 ✗；这里是去重后的唯一一份 ✓，定义见上方 ✓）
    _best_enabled = ckpt_enabled and BEST_CKPT_ENABLE and not bool(
        getattr(args, 'no_best_ckpt', False))
    # 就地 import ✓：只有训练侧用得到它（评估入口对应的那一段会被生成器整段去掉 ✓）
    from utils.train import CkptManager   # noqa: E402
    # 训练阶段用到的支撑（成本项 / 收尾汇总 / 把模型换成"最好一轮" ✓）
    from utils.train import (   # noqa: E402
        log_training_summary,
        p4_cost_term,
        restore_best_model,
    )
    ckpt = CkptManager(ckpt_dir, enabled=ckpt_enabled, train_epochs=train_epochs,
                       best_enabled=_best_enabled, log=log_console)
    ckpt_dir = ckpt.dir  # 老名字的别名 ✓（循环里仍在用）
    ckpt_progress_path = ckpt.progress_path  # 老名字的别名 ✓
    _best_state = ckpt.best_state             # 同一个 dict ✓ ⇒ 双向同步
    _best_ckpt_dir = ckpt.best_dir  # 老名字的别名 ✓
    _best_meta_path = ckpt.best_meta_path  # 老名字的别名 ✓
    log_console('构建 RLlib 模型...')
    model = config.build()
    if ckpt_enabled:
        log_console(f'[checkpoint] 保存=ON（每 {CKPT_EVERY} 轮 → {ckpt_dir}）')

    log_console(f'开始训练 SAC 模型，共 {train_epochs} 轮...')
    log_console(
        f'（每轮 = 1 次 model.train()；前 {MIN_SAMPLE_BEFORE_LEARN} 步只采样不学习，'
        f'跨过后才开始更新策略网络。下面每轮都会打印一行进度，便于判断是慢还是卡住）'
    )

    # ---- 训练中"中期评估"试跑（跑头/尾两段窗口，不渲染、不写 KPI）----
    mini_eval_every = max(0, int(MINI_EVAL_EVERY))
    mid_probes = []
    if mini_eval_every > 0:
        for where in (MID_EVAL_WINDOWS or ('head',)):
            try:
                penv, run_steps, desc = build_probe_env(eval_schema, output_dir, MINI_EVAL_STEPS, where)
                mid_probes.append({'env': penv, 'run_steps': run_steps, 'where': desc})
            except Exception as exc:
                log_console(f'[中期评估] {where} 探针创建失败（跳过该窗口）: {exc}')
        if mid_probes:
            log_console(
                f'训练中中期评估=ON（每 {mini_eval_every} 轮 × 窗口 '
                f'{"; ".join(p["where"] for p in mid_probes)}，贪心）\n'
                f'  输出 = 逐栋 KPI 口径「高温%/低温%」（有人步, band=comfort_band）'
                f' + 过热保底触发/平均缺口/平均罚\n'
                f'  早停：① 达标(全部楼 高温≤{MID_TARGET_HOT:.0%} 且 低温≤{MID_TARGET_COLD:.0%})即停；'
                f'② 投票制停滞——连续 {MID_VOTE_PATIENCE} 次中期评估里「优于上次的楼数」'
                f'< {max(1, int(np.ceil(MID_VOTE_RATIO * 3)))} 栋即停；'
                f'③ 单栋恶化——某栋连续 {MID_WORSEN_PATIENCE} 次高于「自身历史最优 +'
                f'{MID_WORSEN_MARGIN:.0%}」即停（防"1 栋崩、2 栋好"被多数票掩盖）；'
                f'④ 全楼稳定收敛——逐栋合计连续 {MID_CONVERGE_PATIENCE} 次 <'
                f'{MID_CONVERGE_SUM:.0%} 才停（单栋收敛只打标记，不停训）\n'
                f'        最小轮数 {min_train_epochs}（在此之前 ①②③④ 一律不停；'
                f'仅判据⑤崩坏止损可在 {CRASH_GUARD_EPOCH} 轮提前止损）、'
                f'最大轮数 {train_epochs}（硬上限）（都只跳训练，正式评估与 KPI 照常出）\n'
                f'  判读：平均缺口随轮数持续下降 → 只是训练量不够；一直平着不动 → 奖励口径问题'
            )
        else:
            log_console('训练中中期评估=OFF（探针全部创建失败）')

    # 中期评估是不是整段跑（'full'）—— 决定"最好一轮"的指标记成 'full' 还是 'mid'
    _mid_is_full = ('full' in tuple(MID_EVAL_WINDOWS or ()))

    # ---- P-4（2026-09-30）：无控制基线的成本参照（只算一次）---------------------
    _p4_cost_ref = {}
    # 参照用的试跑 = 中期评估那一段整跑（独立的 FULL_EVAL 已于 2026-10-08 删除 ✓）
    #   ⇒ 不再需要"有整段试跑就用整段"的分支 ✓；成本参考值 _p4_cost_ref 由它算出 ✓
    _p4_probe = mid_probes[0] if mid_probes else None
    if _p4_probe is not None:
        try:
            _t_ref = time.perf_counter()
            _p4_cost_ref = run_nocontrol_cost_ref(
                _p4_probe['env'], int(_p4_probe['run_steps'])) or {}
            _byb = [round(float(v), 1) for v in (_p4_cost_ref.get('by_b') or [])]
            log_console(
                '[P-4] 无控制基线成本参照='
                f'{_p4_cost_ref.get("raw", 0.0):.2f}（Σ电价×净用电；逐栋 {_byb}；'
                f'{time.perf_counter() - _t_ref:.0f}s）\n'
                + (f'  选择指标 = 超标面积 + {BEST_CKPT_TIEBREAK:g}×Σ合计'
                   f' + {float(P4_COST_WEIGHT):g}×成本率（成本率 = 本次 ÷ 该参照）'
                   if float(P4_COST_WEIGHT) > 0.0 else
                   f'  选择指标 = 超标面积 + {BEST_CKPT_TIEBREAK:g}×Σ合计（**纯舒适**；'
                   f'成本率仅作诊断打印，见 P4_COST_WEIGHT 处的判决记录）')
                if _p4_cost_ref else
                '[P-4] 成本参照取不到（成本率诊断不可用；选择指标不受影响）'
            )
        except Exception as exc:
            log_console(f'[P-4] 成本参照计算失败（诊断不可用）: {exc}')
            _p4_cost_ref = {}

    _t_train0 = time.perf_counter()
    _sampled_prev = 0
    _t_prev = _t_train0
    _learn_marked = False
    _mid_best = None         # 中期评估「最差和」历史最好值（越小越好）
    _mid_stale = 0           # （旧判据）连续多少次中期评估「最差和」没有实质进步
    _mid_prev_sums = None    # 上次中期评估的逐栋「高温+低温」合计（投票制判据用）
    _mid_vote_stale = 0      # 连续多少次中期评估"优于上次的楼数"没过线
    _mid_best_sums = None    # 逐栋「高温+低温」的自身历史最优（P8-2 单栋恶化保护用）
    _mid_worsen = []         # 逐栋"高于自身最优+margin"的连续次数
    _mid_conv = []           # 逐栋"合计低于 MID_CONVERGE_SUM"的连续次数（P9-4 收敛标记用）
    _mid_eval_hist = []  # 历次中期评估 [{round,hot,cold}]：随断点写盘（诊断 / 前端曲线用 ✓）
    _stopped_reason = None   # 早停原因；非 None 表示训练被提前结束（正式评估照常跑）

    # 不再用「采样速率」估算学习耗时（那会把整轮时间都算成采样，打出假的「学习≈0.0s」），
    # 改用 res['timers'] 的真实毫秒；同时分别跟踪 agent / env 两套训练样本计数。
    _trained_prev = 0.0      # 上轮累计 num_agent_steps_trained（显示用）
    _trained_env_prev = 0.0  # 上一轮累计的 num_env_steps_trained（用来核对两套计数）
    # 轮数多时隔 5 轮打一次（仍能及时发现卡顿）；轮数少时每轮都打
    _log_every = 1 if train_epochs <= 120 else 5
    _last_epoch = _start_epoch      # 已跑到的绝对轮数（早停 break 也能正确记录）
    # 把当前 model 交给管家 ✓（存档时才拿得到它 ✓）
    ckpt.model = model
    for i in range(_start_epoch, train_epochs):
        _last_epoch = i + 1
        # ---- P1：课程式下界衰减（必须在 model.train() 之前更新，使本轮采样与随后的
        #      中期评估读到的都是新系数；动机与实测证据见 COOL_FLOOR_ENABLE 处注释）----
        _sc_now = update_cool_floor_scale(i)
        if COOL_FLOOR_ENABLE and (
            (i + 1) % 20 == 0 or (i + 1) == _start_epoch + 1 or (i + 1) == train_epochs
        ):
            _fl_base = float(COOL_REMAP_FLOOR)
            log_console(
                f'[动作重标定] P1 课程式下界：第 {i + 1} 轮 scale={_sc_now:.3f} '
                f'→ 全楼 floor={_fl_base * _sc_now:.4f}'
                + ('（已归零 → applied = a）' if _sc_now <= 0 else '')
            )
        res = model.train()
        now = time.perf_counter()

        sampled = find_metric(
            res, 'num_env_steps_sampled_lifetime', 'num_env_steps_sampled', 'env_steps_sampled'
        )
        trained = find_metric(
            res, 'num_agent_steps_trained_lifetime', 'num_agent_steps_trained', 'agent_steps_trained'
        )
        # 同时取环境侧计数，用来核实"学习样本数"的真实含义（两套计数差多少倍）
        trained_env = find_metric(
            res, 'num_env_steps_trained_lifetime', 'num_env_steps_trained', 'env_steps_trained'
        )
        # 学习真正开始的那一刻单独标记（此前只是采样，不更新网络）
        if (not _learn_marked) and isinstance(sampled, (int, float)) \
                and float(sampled) >= MIN_SAMPLE_BEFORE_LEARN:
            _learn_marked = True
            log_console(
                f'[训练] 累计采样={int(sampled)} ≥ {MIN_SAMPLE_BEFORE_LEARN} → 从此开始更新策略网络'
            )
            # P16-1 一次性诊断：把训练样本数与计时的原始值全部打出来。
            try:
                _info = res.get('info') or {}
                _timers0 = res.get('timers') or {}
                log_console(f'[诊断] res[timers] 键={sorted(_timers0.keys())}')
                log_console(
                    '[诊断] 训练样本口径(原始值): '
                    + ' '.join(
                        f'{k}={_info.get(k, res.get(k, "(无该键)"))}'
                        for k in ('num_agent_steps_trained', 'num_env_steps_trained',
                                  'num_agent_steps_sampled', 'num_env_steps_sampled')
                    )
                )
                log_console(
                    '[诊断] 真实计时(本版 res[timers] 是「每轮均值」，单位 ms): '
                    + ' '.join(
                        f'{k}={_timers0.get(k, "(无该键)")}'
                        for k in ('sample_time_ms', 'learn_time_ms',
                                  'load_time_ms', 'training_iteration_time_ms')
                    )
                )
            except Exception as _dx:
                log_console(f'[诊断] 打印训练样本口径失败（忽略）: {_dx}')

        if ((i + 1) % _log_every == 0 or (i + 1) == train_epochs
                or (i + 1) == _start_epoch + 1):
            ret = find_metric(res, 'episode_return_mean')
            span = now - _t_prev
            step_part = ''
            delta = 0.0
            if isinstance(sampled, (int, float)):
                delta = float(sampled) - _sampled_prev
                _sampled_prev = float(sampled)
                step_part = f' | 本轮采样={delta:.0f}'
                if span > 0 and delta > 0:
                    step_part += f' 吞吐={delta / span:.1f} step/s'
            train_part = ''
            d_train = 0.0
            if isinstance(trained, (int, float)):
                d_train = float(trained) - _trained_prev
                _trained_prev = float(trained)
                train_part = f' | 学习样本=+{d_train:.0f}(agent)'
            # 同时打印环境侧计数，用来核实"学习样本数"到底指什么（当初两轮日志差 400 倍那件事）
            if isinstance(trained_env, (int, float)):
                d_tenv = float(trained_env) - _trained_env_prev
                _trained_env_prev = float(trained_env)
                train_part += f'/+{d_tenv:.0f}(env)'
            # 重放比（C′-2 修正）：分子取自 num_agent_steps_trained，但实测它与
            _rr_part = ''
            if _learn_marked and d_train > 0 and delta > 0 and _n_buildings:
                _rr_env = d_train / delta
                _rr_agent = d_train / (delta * _n_buildings)
                _bpr = d_train / max(1.0, float(TRAIN_BATCH_SIZE)) / max(1, _log_every)
                _rr_part = (f' | 重放比≈{_rr_env:.0f}(env口径)/{_rr_agent:.1f}(agent口径)'
                            f' | 训练={_bpr:.0f}批/轮')
                if _bpr < TRAIN_BATCHES_PER_ROUND_MIN:
                    _rr_part += f' ⚠训练量塌陷(<{TRAIN_BATCHES_PER_ROUND_MIN}批/轮，' \
                                f'见 TRAIN_INTENSITY 注释)'
            avg = (now - _t_train0) / max(1, i + 1 - _start_epoch)
            eta = avg * (train_epochs - (i + 1))
            # 真实计时（本版 res['timers'] = 每轮均值，单位 ms）。
            # 旧实现用「采样速率」估算学习耗时，会把整轮时间都算成采样，打出假的「学习≈0.0s」。
            _timers_now = res.get('timers') or {}
            _sms = _timers_now.get('sample_time_ms')
            _lms = _timers_now.get('learn_time_ms')
            _ims = _timers_now.get('training_iteration_time_ms')
            _timing = ''
            if any(isinstance(v, (int, float)) for v in (_sms, _lms, _ims)):
                _timing = ' | 计时(ms/轮):'
                if isinstance(_sms, (int, float)):
                    _timing += f' 采样={_sms:.0f}'
                if isinstance(_lms, (int, float)):
                    _timing += f' 学习={_lms:.0f}'
                if isinstance(_ims, (int, float)):
                    _timing += f' 整轮={_ims:.0f}'
            log_console(
                f'[训练] 第 {i + 1}/{train_epochs} 轮 | 本轮 {span:.1f}s'
                + step_part
                + train_part
                + _rr_part
                + (f' | 累计采样={int(sampled)}' if isinstance(sampled, (int, float)) else '')
                + (f' | 回报={ret:.3f}' if isinstance(ret, (int, float)) else '')
                + _timing
                + f' | 均 {avg:.1f}s/轮 预计剩余 {eta / 60:.1f} 分钟'
            )
            _t_prev = now

        # ---- 训练中「中期评估」+ 早停判据：判断当前模型够不够好 ----------------
        if mid_probes and ((i + 1) % mini_eval_every == 0 or (i + 1) == train_epochs):
            try:
                _t_mid = time.perf_counter()
                mid_ret, mid_stats, mid_kpi = run_mid_eval(model, mid_probes)
                m_steps = max(1, int(mid_stats.get('steps', 0) or 0))
                m_trig = int(mid_stats.get('hot_trig', 0) or 0)
                m_def = float(mid_stats.get('hot_deficit', 0.0) or 0.0)
                m_pay = float(mid_stats.get('hot_pay', 0.0) or 0.0)
                hot = list(mid_kpi.get('hot') or [])
                cold = list(mid_kpi.get('cold') or [])

                # 记入中期评估历史（随断点一起写盘 ✓，给前端曲线与诊断用 ✓）。
                # 非有限值存 null —— json 规范没有 NaN，别写进去。
                # 把历史里的值转成 float；转不了或非有限值就返回 None ✓
                def _hist_val(v):
                    try:
                        fv = float(v)
                    except (TypeError, ValueError):
                        return None
                    return float(fv) if np.isfinite(fv) else None

                _mid_eval_hist.append({
                    'round': i + 1,
                    'hot': [_hist_val(v) for v in hot],
                    'cold': [_hist_val(v) for v in cold],
                })

                # 把比例格式化成百分比（如 0.123 → '12.3%' ✓）；无效值显示 ' na ' ✓
                def _pct(v):
                    return ' na ' if (v is None or not np.isfinite(v)) else f'{v:5.1%}'

                per_b = ' '.join(
                    f'B{k + 1}:{_pct(hot[k])}/{_pct(cold[k])}' for k in range(len(hot))
                )
                _mt = mid_kpi.get('mean_T')
                _t_part = (
                    f' 平均室温={float(_mt):.2f}°C' if np.isfinite(_mt) else ' 平均室温=na'
                )
                log_console(
                    f'[中期评估] 第 {i + 1}/{train_epochs} 轮 | 高温/低温 {per_b} '
                    f'(KPI 口径, 有人步 n={mid_kpi.get("occ")}) '
                    f'| 步数={mid_kpi.get("steps_run")}{_t_part}'
                )
                log_console(
                    f'           过热保底触发={m_trig / m_steps:.1%} '
                    f'平均缺口={m_def / max(1, m_trig):.3f} '
                    f'平均罚={m_pay / max(1, m_trig):.2f} | 回报={mid_ret:.1f} '
                    f'| {time.perf_counter() - _t_mid:.0f}s'
                )
                # 试跑健康检查：步数为 0 或比例全是 na ⇒ 说明读数没取到，直接提示
                _sr = int(mid_kpi.get('steps_run') or 0)
                if _sr <= 0 or not any(np.isfinite(v) for v in list(hot) + list(cold)):
                    log_console(
                        '[中期评估][警告] 本次探针数据不可用（步数=%d，比例 =na）→ '
                        '该行不能用于判断模型好坏，请检查窗口构建/占用人数读取（见上方一次性提示）'
                        % _sr
                    )

                # ---- P1′ 自检：主动读数（奖励侧算的）vs 参考读数（按每栋老办法算的）----
                _lg_hot = list(mid_kpi.get('legacy_hot') or [])
                _lg_cold = list(mid_kpi.get('legacy_cold') or [])
                # 只在影子侧「确有有限值」时才做对比，否则静默跳过（避免无数据时误报）
                _has_lg = any(np.isfinite(v) for v in _lg_hot + _lg_cold)
                if _has_lg:
                    _nb = min(len(hot), len(_lg_hot), len(_lg_cold))
                    _dmax = 0.0
                    for _k in range(_nb):
                        for _a, _b in ((hot[_k], _lg_hot[_k]), (cold[_k], _lg_cold[_k])):
                            try:
                                _fa, _fb = float(_a), float(_b)
                            except (TypeError, ValueError):
                                continue
                            if not (np.isfinite(_fa) and np.isfinite(_fb)):
                                continue
                            _dmax = max(_dmax, abs(_fa - _fb))
                    _main_txt = ' '.join(
                        f'B{k + 1}:{_pct(hot[k])}/{_pct(cold[k])}' for k in range(_nb)
                    )
                    _lg_txt = ' '.join(
                        f'B{k + 1}:{_pct(_lg_hot[k])}/{_pct(_lg_cold[k])}' for k in range(_nb)
                    )
                    if _dmax > MID_KPI_SRC_TOL:
                        log_console(
                            f'[中期评估][自检-警告] KPI 口径两套读数不一致 Δmax={_dmax:.1%}'
                            f'（判据采用「奖励侧」）| 奖励侧 {_main_txt} | 旧楼栋读数 {_lg_txt}'
                        )
                        log_console(
                            '[中期评估][自检-警告] 楼栋对象取值路径在自定义窗口下不可靠'
                            '（P1′ 已把判据切到奖励侧，判据本身不受影响）；'
                            '若「奖励侧」与决策推演/导出 KPI 仍有偏差，请继续排查。'
                        )
                        # 打印两套「首个楼步原始读数」——这是钉死根因的关键证据
                        _rs = list(mid_kpi.get('samples') or [])
                        _ls = list(mid_kpi.get('legacy_samples') or [])

                        # 把策略原始动作（温度 / 冷设定点 / 热设定点 / 舒适带半宽 / 有人与否）写成一段可读文字，标注 (raw=…) ✓
                        def _raw_txt(s):
                            if not s:
                                return 'na'
                            try:
                                return (f"T={float(s.get('T')):.2f} csp={float(s.get('csp')):.2f} "
                                        f"hsp={float(s.get('hsp')):.2f} band={float(s.get('band')):.2f} "
                                        f"occ={float(s.get('occ')):.0f}")
                            except (TypeError, ValueError):
                                return 'na'

                        if _rs or _ls:
                            log_console(
                                '[中期评估][自检-警告] 首个楼步原始读数：'
                                + ' | '.join(
                                    f'B{_k + 1} 奖励侧[{_raw_txt(_rs[_k]) if _k < len(_rs) else "na"}]'
                                    f' 旧路径[{_raw_txt(_ls[_k]) if _k < len(_ls) else "na"}]'
                                    for _k in range(max(len(_rs), len(_ls)))
                                )
                            )
                    else:
                        log_console(
                            f'[中期评估][自检] KPI 口径两套读数一致 Δmax={_dmax:.1%}'
                            f'| 奖励侧 {_main_txt}'
                        )

                score = (max(hot) + max(cold)) if hot and cold else float('nan')
                # ---- 逐栋投票：本次「高温+低温」合计是否优于上次 ----
                # 3 栋里 ≥ceil(0.6×3)=2 栋低于上次 → 视为仍在进步；否则"未过线"计数 +1。
                _sums = [float(h) + float(c) for h, c in zip(hot, cold)]
                _need = max(1, int(np.ceil(MID_VOTE_RATIO * len(_sums))))
                _better = []
                if _mid_prev_sums is not None and len(_mid_prev_sums) == len(_sums):
                    _better = [k for k in range(len(_sums)) if _sums[k] < _mid_prev_sums[k]]
                    _mid_vote_stale = 0 if len(_better) >= _need else _mid_vote_stale + 1
                    _vote_txt = (
                        f' | 优于上次 {len(_better)}/{len(_sums)} 栋（需≥{_need}；'
                        f'{"、".join(f"B{k + 1}" for k in _better) or "无"}）'
                        f' 未过线计数 {_mid_vote_stale}/{MID_VOTE_PATIENCE}'
                    )
                else:
                    _vote_txt = ' | 首次中期评估（无对比基线）'
                _mid_prev_sums = _sums
                # ---- 判据③ 单栋恶化保护（P8-2）：逐栋跟踪自身历史最优 ----
                _worsen_txt = ''
                if _mid_best_sums is None or len(_mid_best_sums) != len(_sums):
                    _mid_best_sums = list(_sums)
                    _mid_worsen = [0] * len(_sums)
                else:
                    for k in range(len(_sums)):
                        if _sums[k] < _mid_best_sums[k]:
                            _mid_best_sums[k] = float(_sums[k])
                            _mid_worsen[k] = 0
                        elif _sums[k] > _mid_best_sums[k] + MID_WORSEN_MARGIN:
                            _mid_worsen[k] += 1
                        else:
                            _mid_worsen[k] = 0
                    _worsen_txt = (
                        ' | 单栋最优 '
                        + ' / '.join(f'B{k + 1} {_mid_best_sums[k]:.1%}' for k in range(len(_sums)))
                        + ' | 恶化计数 '
                        + ' / '.join(f'B{k + 1} {_mid_worsen[k]}/{MID_WORSEN_PATIENCE}'
                                     for k in range(len(_sums)))
                    )
                log_console(
                    '[中期评估] 逐栋合计(高温+低温)='
                    + ' / '.join(f'B{k + 1} {v:.1%}' for k, v in enumerate(_sums))
                    + _vote_txt + _worsen_txt
                )
                # ---- 判据④ 逐栋收敛标记（P9-4）：合计 < MID_CONVERGE_SUM 的连续次数 ----
                if not _mid_conv or len(_mid_conv) != len(_sums):
                    _mid_conv = [0] * len(_sums)
                for k in range(len(_sums)):
                    _mid_conv[k] = (_mid_conv[k] + 1) if _sums[k] < MID_CONVERGE_SUM else 0
                log_console(
                    '[中期评估] 收敛标记 '
                    + ' / '.join(
                        f'B{k + 1} {"已收敛" if _mid_conv[k] >= MID_CONVERGE_PATIENCE else "未收敛"}'
                        f'({_sums[k]:.1%}，连续 {_mid_conv[k]}/{MID_CONVERGE_PATIENCE})'
                        for k in range(len(_sums))
                    )
                    + f'（阈值 合计<{MID_CONVERGE_SUM:.0%}；全楼都"已收敛"才停训）'
                )
                # ---- P1′（2026-09-28）：中期评估已是"整段跑完"的读数 ⇒ 直接拿它选最好一轮 ----
                _cur_prim = (float(sum(max(0.0, s - BEST_CKPT_TARGET_SUM) for s in _sums))
                             if _sums else float('nan'))
                _cur_sum_all = float(sum(_sums)) if _sums else float('nan')
                # 加入成本项（成本率 = 本次 cost_raw ÷ 无控制基线参照）
                _cur_cost_term = p4_cost_term(mid_stats, _p4_cost_ref)
                _cur_metric = (_cur_prim + BEST_CKPT_TIEBREAK * _cur_sum_all + _cur_cost_term
                               if _sums else float('nan'))
                if np.isfinite(_cur_metric):
                    # P-14（2026-10-01）：**逐楼成本率**日志（只读诊断，不参与任何判据）----
                    _byb_txt = ''
                    try:
                        _penv = (mid_probes[0] or {}).get('env') if mid_probes else None
                        _prf = getattr(_unwrap_citylearn_env(_penv), 'reward_function', None)
                        _snap = (_prf.cost_snapshot()
                                 if (_prf is not None and hasattr(_prf, 'cost_snapshot')) else {})
                        _cur_b = list(_snap.get('by_b') or [])
                        _ref_b = list((_p4_cost_ref or {}).get('by_b') or [])
                        _bparts = []
                        for _k in range(min(len(_cur_b), len(_ref_b))):
                            if float(_ref_b[_k] or 0.0) > 0.0:
                                _bparts.append(f'B{_k + 1} '
                                               f'{float(_cur_b[_k]) / float(_ref_b[_k]):.3f}')
                        if _bparts:
                            _byb_txt = '｜逐楼成本率 ' + ' / '.join(_bparts)
                    except Exception:
                        _byb_txt = ''
                    _cost_txt = ''
                    _ref_raw = float((_p4_cost_ref or {}).get('raw') or 0.0)
                    _cur_raw = float((mid_stats or {}).get('cost_raw') or 0.0)
                    if _ref_raw > 0.0 and _cur_raw > 0.0:
                        _ratio_now = _cur_raw / _ref_raw
                        if _cur_cost_term > 0.0:
                            _cparts = []
                            if float(P4_COST_WEIGHT) > 0.0:
                                _cparts.append(
                                    f'{float(P4_COST_WEIGHT):g}×成本率 {_ratio_now:.4f}'
                                    f'={float(P4_COST_WEIGHT) * _ratio_now:.4f}')
                            _hw = float(P4_COST_HINGE.get('w') or 0.0)
                            if _hw > 0.0:
                                _ht = float(P4_COST_HINGE.get('target') or 0.0)
                                _ov = max(0.0, _ratio_now - _ht)
                                _cparts.append(
                                    f'{_hw:g}×max(0, 成本率 −{_ht:g})={_hw * _ov:.4f}'
                                    + ('（超线 ✗）' if _ov > 0 else '（达标，不加分 ✓）'))
                            _cost_txt = (' + ' + ' + '.join(_cparts)
                                         + f'｜成本率 {_ratio_now:.4f}'
                                           f'（本次 {_cur_raw:.2f} / 基线 {_ref_raw:.2f}）')
                        else:
                            # 成本项关闭时仍打印成本率（诊断；不参与选择）
                            _cost_txt = (f'｜成本率 {_ratio_now:.4f}'
                                         f'（本次 {_cur_raw:.2f} / 基线 {_ref_raw:.2f}，仅诊断）')
                    _cost_txt += _byb_txt          # 追加逐楼成本率（只读诊断）
                    log_console(
                        f'[中期评估] 指标={_cur_metric:.4f}（超标面积 {_cur_prim:.4f}'
                        f' + {BEST_CKPT_TIEBREAK:g}×Σ合计 {_cur_sum_all:.4f}{_cost_txt}）'
                        + ('（整段口径，参与 best-ckpt 选择）' if _mid_is_full
                           else '（非整段口径，仅趋势参考）')
                    )
                if _mid_is_full and np.isfinite(_cur_metric) and (
                    _best_state['metric'] is None
                    or _best_state['src'] != 'full'      # 来源不一致 → 直接刷新（见 _best_state 注释）
                    or _cur_metric < float(_best_state['metric']) - BEST_CKPT_MIN_GAIN
                ):
                    ckpt.save_best(
                        i + 1, _cur_metric, _sums,
                        worst_sum=(float(max(hot) + max(cold))
                                   if hot and cold else None),
                        src='full', cost_term=_cur_cost_term)
                # 判据①：达标即停（"成功"停止）
                if (
                    MID_STOP_WHEN_GOOD and (i + 1) >= min_train_epochs
                    and hot and cold
                    and all(np.isfinite(v) for v in hot + cold)
                    and max(hot) <= MID_TARGET_HOT and max(cold) <= MID_TARGET_COLD
                ):
                    _stopped_reason = (
                        f'达标：全部楼 高温≤{MID_TARGET_HOT:.0%} 且 低温≤{MID_TARGET_COLD:.0%} '
                        f'（最差 高温 {max(hot):.1%} / 低温 {max(cold):.1%}）'
                    )
                    log_console(f'[早停] 第 {i + 1} 轮 {_stopped_reason} → 提前结束训练，直接进正式评估')
                    break
                # 判据④：全楼都稳定收敛 → 停（P9-4；"成功"停止）
                if (
                    MID_STOP_WHEN_CONVERGED and (i + 1) >= min_train_epochs
                    and _mid_conv
                    and all(c >= MID_CONVERGE_PATIENCE for c in _mid_conv)
                ):
                    _stopped_reason = (
                        f'全楼稳定收敛：逐栋「高温+低温」合计连续 {MID_CONVERGE_PATIENCE} 次低于 '
                        f'{MID_CONVERGE_SUM:.0%}（当前 '
                        + ' / '.join(f'B{k + 1} {v:.1%}' for k, v in enumerate(_sums)) + '）'
                    )
                    log_console(f'[早停] 第 {i + 1} 轮 {_stopped_reason} → 提前结束训练，直接进正式评估')
                    break
                # 判据⑤：崩坏止损（P17-1）—— 只在 CRASH_GUARD_EPOCH 体检一次，
                if (
                    MID_STOP_ON_CRASH
                    and (i + 1) == CRASH_GUARD_EPOCH
                    and hot and cold and len(hot) == len(cold)
                ):
                    _sat = []
                    for _k in range(len(hot)):
                        if np.isfinite(hot[_k]) and float(hot[_k]) > CRASH_GUARD_MAX_HOT:
                            _sat.append(f'B{_k + 1} 高温 {float(hot[_k]):.1%} > '
                                        f'{CRASH_GUARD_MAX_HOT:.0%}')
                        if np.isfinite(cold[_k]) and float(cold[_k]) > CRASH_GUARD_MAX_COLD:
                            _sat.append(f'B{_k + 1} 低温 {float(cold[_k]):.1%} > '
                                        f'{CRASH_GUARD_MAX_COLD:.0%}')
                    if _sat:
                        _stopped_reason = (
                            f'崩坏止损（第 {i + 1} 轮体检）：策略已饱和在单一极端 —— '
                            + '；'.join(_sat)
                        )
                        log_console(
                            f'[早停] 第 {i + 1} 轮 {_stopped_reason} → 提前结束训练'
                            f'（对照：可用模型同轮次 max低温 0.38~0.40、max高温 0.62~0.74；'
                            f'崩坏模型 0.93+）'
                        )
                        break
                # 判据②：投票制停滞止损（最小训练轮数之前一律不生效）
                if (
                    MID_STOP_BY_VOTE
                    and (i + 1) >= min_train_epochs
                    and _mid_vote_stale >= MID_VOTE_PATIENCE
                ):
                    _stopped_reason = (
                        f'停滞（投票制）：连续 {_mid_vote_stale} 次中期评估里，'
                        f'"高温+低温优于上一次"的楼数都没到 {_need}/{len(_sums)} 栋'
                        f'（当前 ' + ' / '.join(f'B{k + 1} {v:.1%}' for k, v in enumerate(_sums)) + '）'
                    )
                    log_console(f'[早停] 第 {i + 1} 轮 {_stopped_reason} → 提前结束训练')
                    break
                # 判据③：单栋恶化保护（P8-2；最小训练轮数之前不生效）
                if MID_STOP_ON_WORSEN and (i + 1) >= min_train_epochs and _mid_worsen:
                    _bad = [k for k in range(len(_sums))
                            if _mid_worsen[k] >= MID_WORSEN_PATIENCE]
                    if _bad:
                        _stopped_reason = (
                            '单栋恶化：' + '、'.join(f'B{k + 1}' for k in _bad)
                            + f' 连续 {MID_WORSEN_PATIENCE} 次高于「自身历史最优 +'
                            f'{MID_WORSEN_MARGIN:.0%}」（'
                            + '；'.join(
                                f'B{k + 1} 最优 {_mid_best_sums[k]:.1%} → 当前 {_sums[k]:.1%}'
                                for k in _bad
                            ) + '）'
                        )
                        log_console(
                            f'[早停] 第 {i + 1} 轮 {_stopped_reason} → 提前结束训练'
                            f'（避免用更差的模型去跑正式评估）'
                        )
                        break
                # （P1-B 修复：best-ckpt 的评估与保存已**上移到所有早停判据之前**，
                if np.isfinite(score) and (
                    _mid_best is None or score < float(_mid_best) - MID_MIN_GAIN
                ):
                    _mid_best = float(score)
                    _mid_stale = 0
                else:
                    _mid_stale += 1
                if MID_STOP_BY_SCORE and _mid_stale >= MID_PATIENCE:
                    _stopped_reason = (
                        f'停滞：连续 {_mid_stale} 次中期评估「最差和」改善 < {MID_MIN_GAIN:.0%} '
                        f'（最好 {float(_mid_best):.3f}，当前 {score:.3f}）'
                    )
                    log_console(f'[早停] 第 {i + 1} 轮 {_stopped_reason} → 判定已收敛/无救，提前结束训练')
                    break
                if np.isfinite(score):
                    _mbt = f'{float(_mid_best):.3f}' if _mid_best is not None else 'na'
                    log_console(
                        f'[中期评估] 进展：最差和={score:.3f}（历史最好 {_mbt}；'
                        f'旧判据计数 {_mid_stale}/{MID_PATIENCE}）'
                        f' | 轮数 {i + 1}/{train_epochs}（最小 {min_train_epochs}：'
                        f'在此之前 ①②③④ 都不停）'
                    )
            except Exception as exc:      # 中期评估失败绝不影响训练/评估/KPI
                log_console(f'[中期评估] 第 {i + 1} 轮失败（忽略，继续训练）: {exc}')


        # ---- checkpoint 定期保存（P14-1）------------------------------------
        # 放在早停判断之后：触发早停就不会走到这里，由循环外的"训练结束"再存一次保底。
        if ckpt_enabled and CKPT_EVERY > 0 and (
            (i + 1) % CKPT_EVERY == 0 or (i + 1) == train_epochs
        ):
            ckpt.save('定期保存', i + 1, _mid_best, _mid_eval_hist)

    return TrainOutcome(
        _last_epoch=_last_epoch,
        _mid_best=_mid_best,
        _mid_best_sums=_mid_best_sums,
        _mid_conv=_mid_conv,
        _mid_eval_hist=_mid_eval_hist,
        _mid_prev_sums=_mid_prev_sums,
        _mid_vote_stale=_mid_vote_stale,
        _mid_worsen=_mid_worsen,
        _sampled_prev=_sampled_prev,
        _start_epoch=_start_epoch,
        _stopped_reason=_stopped_reason,
        _t_train0=_t_train0,
        ckpt=ckpt,
        ckpt_dir=ckpt_dir,
        model=model,
    )
