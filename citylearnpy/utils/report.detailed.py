# 注：本模块原名 utils/report.py（2026-10-07 utils 整理：按功能改名，内容未改 ✓）
from __future__ import annotations

# -*- coding: utf-8 -*-
# [详注-BEGIN]（生成简版时整段删除）
# 记录与输出：逐步采集 / 决策推演 / KPI 打印
#
# 本文件由 utils/ 下多个模块合并而来（2026-10-06 ✓，合并映射见每段横幅 ✓）：
#   · trace.py
#   · trace.py
#   · trace.py
#   · trace.py
#

# ============================================================================
# ==== 段：eval_step_trace（原 utils/report.py ✓）====
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# 评估阶段逐步诊断轨迹导出（Multi-agent / NOCONTROL 共用）。
#
# 写出 step_trace.csv，每行 = 某楼在某仿真小时的关键量，便于对比：
#   室温/设定点/舒适带、制冷用电、净用电、电价、SOC、电池充放、停电、动作、奖励。
# [详注-END]



import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

import numpy as np


# 把任意值尽量转成 float；转不了（None / 坏字符串）就返回默认值（默认 NaN）✓
def _as_float(v: Any, default: float = float('nan')) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


# 读取 CityLearn 时序字段在「刚完成的一步」上的值 ✓
def series_value(obj: Any, time_step: int, default: float = float('nan')) -> float:
    # [详注-BEGIN]（生成简版时整段删除）
    #
    # 读取 CityLearn 时序字段在「刚完成的一步」上的值。
    #
    # step 结束后 env.time_step 已 +1，运行量写在 [time_step-1]；
    # 与 checa.utils.citylearn_current_series_value 同一约定。
    #
    # [详注-END]
    if obj is None:
        return default
    try:
        arr = np.asarray(obj, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return _as_float(obj, default)
    if arr.size == 0:
        return default
    idx = 0 if int(time_step) <= 0 else min(int(time_step) - 1, arr.size - 1)
    return float(arr[idx])


# 沿属性名一层层往下取（root.a.b…）；中途缺任何一层就返回 None ✓
def getattr_path(root: Any, *names: str) -> Any:
    cur = root
    for name in names:
        if cur is None or not hasattr(cur, name):
            return None
        cur = getattr(cur, name)
    return cur


# 把一条动作向量写进 `action_<名字><后缀>` 列（顺序 = building.active_actions ✓） ✓
def _fill_action_fields(
    row: Dict[str, Any],
    action_names: Sequence[str],
    action_vec: Optional[Sequence[float]],
    *,
    suffix: str = '',
) -> None:
    # [详注-BEGIN]（生成简版时整段删除）
    # 把一条动作向量写进 `action_<名字><后缀>` 列（顺序 = building.active_actions ✓）。
    #
    # `action_vec=None` 时也写 NaN 占位 ⇒ 字段永远存在，界面不必判空 ✓
    #
    # [详注-END]
    if action_vec is None:
        for name in action_names:
            row[f'action_{name}{suffix}'] = float('nan')
        return
    vec = np.asarray(action_vec, dtype=float).reshape(-1)
    for i, name in enumerate(action_names):
        row[f'action_{name}{suffix}'] = float(vec[i]) if i < vec.size else float('nan')
    for i in range(len(action_names), int(vec.size)):
        row[f'action_{i}{suffix}'] = float(vec[i])


# 从单栋 Building 抽取一步诊断字段 ✓
def building_step_snapshot(
    building: Any,
    *,
    time_step: int,
    step_count: int,
    building_id: str,
    action_vec: Optional[Sequence[float]] = None,
    raw_action_vec: Optional[Sequence[float]] = None,
    reward: Optional[float] = None,
) -> Dict[str, Any]:
    # [详注-BEGIN]（生成简版时整段删除）
    # 从单栋 Building 抽取一步诊断字段。
    #
    # 动作写**两列**（P0-B 协议 ✓）：
    #   · `action_vec`     = 建筑**实际执行**的动作（= 奖励算动作项用的那份 ✓，
    #                        来源 `rf._pending_acts`，由 install_action_hook 在 env.step 内注入 ✓）
    #   · `raw_action_vec` = 策略网络的**原始输出**（可能还经过映射/重标定才落地 ✓）
    # ⇒ 两者不等即说明中间存在改写（推演界面会附 `(raw=…)` 标注，见 marl_decision_trace ✓）
    #
    # [详注-END]
    indoor = series_value(getattr_path(building, 'indoor_dry_bulb_temperature'), time_step)
    cool_sp = series_value(
        getattr_path(building, 'indoor_dry_bulb_temperature_cooling_set_point'), time_step
    )
    heat_sp = series_value(
        getattr_path(building, 'indoor_dry_bulb_temperature_heating_set_point'), time_step
    )
    band = series_value(getattr(building, 'comfort_band', None), time_step, default=2.0)
    if not np.isfinite(band) or band <= 0:
        band = 2.0
    cool_delta = indoor - cool_sp if np.isfinite(indoor) and np.isfinite(cool_sp) else float('nan')
    heat_delta = indoor - heat_sp if np.isfinite(indoor) and np.isfinite(heat_sp) else float('nan')
    hot = 1.0 if (np.isfinite(cool_delta) and cool_delta > band) else 0.0
    cold = 1.0 if (np.isfinite(heat_delta) and heat_delta < -band) else 0.0

    soc = series_value(getattr_path(building, 'electrical_storage', 'soc'), time_step)
    bat_elec = series_value(
        getattr_path(building, 'electrical_storage', 'electricity_consumption'), time_step
    )
    # CityLearn：电池 electricity_consumption >0 充电，<0 放电
    bat_charge = max(bat_elec, 0.0) if np.isfinite(bat_elec) else float('nan')
    bat_discharge = max(-bat_elec, 0.0) if np.isfinite(bat_elec) else float('nan')

    hour = series_value(getattr_path(building, 'energy_simulation', 'hour'), time_step)
    if not np.isfinite(hour):
        hour = series_value(getattr_path(building, 'hour'), time_step)

    row: Dict[str, Any] = {
        'step': int(step_count),
        'env_time_step': int(time_step),
        'building_id': str(building_id),
        'hour': hour,
        'occupant_count': series_value(
            getattr_path(building, 'energy_simulation', 'occupant_count'), time_step
        ),
        'power_outage': series_value(getattr_path(building, 'power_outage'), time_step),
        'electricity_pricing': series_value(
            getattr_path(building, 'pricing', 'electricity_pricing'), time_step
        ),
        'net_electricity_consumption': series_value(
            getattr_path(building, 'net_electricity_consumption'), time_step
        ),
        'cooling_electricity_consumption': series_value(
            getattr_path(building, 'cooling_electricity_consumption'), time_step
        ),
        'cooling_demand': series_value(
            getattr_path(building, 'energy_simulation', 'cooling_demand'), time_step
        ),
        'heating_demand': series_value(
            getattr_path(building, 'energy_simulation', 'heating_demand'), time_step
        ),
        'dhw_electricity_consumption': series_value(
            getattr_path(building, 'dhw_electricity_consumption'), time_step
        ),
        'solar_generation': series_value(
            getattr_path(building, 'solar_generation'), time_step
        ),
        'indoor_temp': indoor,
        'cooling_setpoint': cool_sp,
        'heating_setpoint': heat_sp,
        'comfort_band': band,
        'cooling_delta': cool_delta,
        'heating_delta': heat_delta,
        'is_hot': hot,
        'is_cold': cold,
        'soc': soc,
        'battery_elec': bat_elec,
        'battery_charge': bat_charge,
        'battery_discharge': bat_discharge,
        'reward': _as_float(reward, float('nan')),
    }

    action_names = list(getattr(building, 'active_actions', None) or [])
    _fill_action_fields(row, action_names, action_vec)                       # 实际执行值 ✓
    if raw_action_vec is not None:
        _fill_action_fields(row, action_names, raw_action_vec, suffix='_raw')  # 策略原始值 ✓

    return row


# 对当前 CityLearnEnv 的全部楼栋各写一行 ✓
def collect_citylearn_step_rows(
    citylearn_env: Any,
    *,
    step_count: int,
    actions_by_building: Optional[Mapping[Union[str, int], Sequence[float]]] = None,
    rewards_by_building: Optional[Mapping[Union[str, int], float]] = None,
    action_list: Optional[Sequence[Sequence[float]]] = None,
    raw_action_list: Optional[Sequence[Sequence[float]]] = None,
    reward_list: Optional[Sequence[float]] = None,
) -> List[Dict[str, Any]]:
    # [详注-BEGIN]（生成简版时整段删除）
    #
    # 对当前 CityLearnEnv 的全部楼栋各写一行。
    #
    # `action_list`     = 建筑**实际执行**的动作 ⇒ 写 `action_<名字>` ✓
    # `raw_action_list` = 策略**原始输出** ⇒ 写 `action_<名字>_raw`（供 `(raw=…)` 标注 ✓）
    #
    # 动作/奖励查找顺序：
    #   1) action_list / reward_list 按下标（最稳，推荐 Multi-agent 使用）
    #   2) actions_by_building / rewards_by_building 按 name / 下标 / 其它键
    #
    # [详注-END]
    time_step = int(getattr(citylearn_env, 'time_step', step_count))
    buildings = list(getattr(citylearn_env, 'buildings', []) or [])
    rows: List[Dict[str, Any]] = []
    for i, building in enumerate(buildings):
        bid = str(getattr(building, 'name', None) or f'Building_{i + 1}')
        action_vec = None
        raw_action_vec = None
        reward = None
        if action_list is not None and i < len(action_list):
            action_vec = action_list[i]
        if raw_action_list is not None and i < len(raw_action_list):
            raw_action_vec = raw_action_list[i]
        if reward_list is not None and i < len(reward_list):
            reward = reward_list[i]
        if action_vec is None and actions_by_building is not None:
            action_vec = (
                actions_by_building.get(bid)
                or actions_by_building.get(i)
                or actions_by_building.get(str(i))
            )
        if reward is None and rewards_by_building is not None:
            if bid in rewards_by_building:
                reward = rewards_by_building[bid]
            elif i in rewards_by_building:
                reward = rewards_by_building[i]
            elif str(i) in rewards_by_building:
                reward = rewards_by_building[str(i)]
        rows.append(
            building_step_snapshot(
                building,
                time_step=time_step,
                step_count=step_count,
                building_id=bid,
                action_vec=action_vec,
                raw_action_vec=raw_action_vec,
                reward=reward,
            )
        )
    return rows


# 将逐步行写入 CSV（UTF-8）。空行则不写文件 ✓
def write_step_trace_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    # [详注-BEGIN]（生成简版时整段删除）
    # 将逐步行写入 CSV（UTF-8）。空行则不写文件。
    # [详注-END]
    row_list = list(rows)
    path = Path(path)
    if not row_list:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    # 稳定表头：先固定核心列，再按出现顺序补其余列
    preferred = [
        'step', 'env_time_step', 'building_id', 'hour', 'occupant_count', 'power_outage',
        'electricity_pricing', 'net_electricity_consumption',
        'cooling_electricity_consumption', 'cooling_demand', 'heating_demand',
        'dhw_electricity_consumption', 'solar_generation',
        'indoor_temp', 'cooling_setpoint', 'heating_setpoint', 'comfort_band',
        'cooling_delta', 'heating_delta', 'is_hot', 'is_cold',
        'soc', 'battery_elec', 'battery_charge', 'battery_discharge', 'reward',
    ]
    keys: List[str] = []
    seen = set()
    for k in preferred:
        if any(k in r for r in row_list):
            keys.append(k)
            seen.add(k)
    for r in row_list:
        for k in r.keys():
            if k not in seen:
                keys.append(k)
                seen.add(k)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        for r in row_list:
            writer.writerow({k: r.get(k, '') for k in keys})
    return path

# ============================================================================
# ==== 段：marl_decision_trace（原 utils/report.py ✓）====
# [详注-BEGIN]（生成简版时整段删除）
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# Multi-agent SAC → 模型优选「决策推演」日志（decision_trace.json）。
#
# 与 CHESCA 的 decision_trace.json schema 对齐，供前端 DecisionTraceLog 渲染：
#   - narrative_lines[0]：[观测动作] T/coolSP/dT/…/R（悬停展示 REWARD_KWARGS）
#   - narrative_lines[1:-1]：[奖励计算] 本步分项过程与结果
#   - narrative_lines[-1]：[状态] 室温/舒适带/高低温判定/制冷供需/电池/电价/停电 → 一句话判定
# [详注-END]



import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence



# 把数值格式化成固定小数位的字符串；NaN / 坏值一律显示成 nan ✓
def _fmt(v: Any, nd: int = 2) -> str:
    try:
        x = float(v)
        if x != x:  # NaN
            return 'nan'
        return f'{x:.{nd}f}'
    except (TypeError, ValueError):
        return 'nan'


# 把值改成能写进 JSON 的形式（NaN / Inf → null，list / dict 递归处理）✓
def _json_safe(v: Any) -> Any:
    if isinstance(v, (str, int, bool)) or v is None:
        return v
    if isinstance(v, float):
        if v != v or v in (float('inf'), float('-inf')):
            return None
        return v
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _json_safe(val) for k, val in v.items()}
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


# 同 _as_float：宽松地把值转成 float，失败就给默认值 ✓
def _float(v: Any, default: float = float('nan')) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


# P0-B：当「策略原始动作 ≠ 建筑实际执行动作」时，附上 (raw=…) 标注 ✓
def _raw_act_tag(row: Mapping[str, Any], name: str) -> str:
    # [详注-BEGIN]（生成简版时整段删除）
    # P0-B：当「策略原始动作 ≠ 建筑实际执行动作」时，附上 (raw=…) 标注。
    #
    # action_{name}     = 建筑本步**实际执行**的动作（= 奖励算动作项用的那份）
    # action_{name}_raw = 策略网络的**原始输出**（可能经过映射/重标定才落到执行值）
    #
    # 两者不同，说明中间存在改写（例如 C′-4 的 applied = floor + (1−floor)×a）。
    # 若不标注，很容易把"策略输出"误读成"建筑在做什么"——88809afe 的 B1 就是
    # raw 0.004 而实际 0.1436（差 36 倍），一整套诊断因此走偏。
    #
    # [详注-END]
    r = row.get(f'action_{name}_raw')
    if r is None:
        return ''
    a = row.get(f'action_{name}')
    try:
        if a is not None and abs(float(r) - float(a)) < 5e-4:
            return ''
        return f"(raw={_fmt(r, 3)}) "
    except (TypeError, ValueError):
        return ''


# 状态行：室温/舒适带/高低温判定/制冷供需/电池/电价/停电 → 一句话判定建筑处于什么状态 ✓
def format_state_line(row: Mapping[str, Any]) -> str:
    # [详注-BEGIN]（生成简版时整段删除）
    # 状态行：室温/舒适带/高低温判定/制冷供需/电池/电价/停电 → 一句话判定建筑处于什么状态。
    #
    # 追加在每步的最后一行，便于直接看「是否高温、差多少、有没有在制冷」。
    #
    # [详注-END]
    T = _float(row.get('indoor_temp'))
    band = _float(row.get('comfort_band'))
    cool_sp = _float(row.get('cooling_setpoint'))
    heat_sp = _float(row.get('heating_setpoint'))
    occ = _float(row.get('occupant_count'))
    outage = float(row.get('power_outage', 0) or 0) >= 0.5
    hot = float(row.get('is_hot', 0) or 0) >= 0.5
    cold = float(row.get('is_cold', 0) or 0) >= 0.5

    hi = cool_sp + band if np.isfinite(cool_sp) and np.isfinite(band) else float('nan')
    lo = heat_sp - band if np.isfinite(heat_sp) and np.isfinite(band) else float('nan')
    hot_over = T - hi if np.isfinite(T) and np.isfinite(hi) else float('nan')
    cold_over = lo - T if np.isfinite(T) and np.isfinite(lo) else float('nan')

    price = _float(row.get('electricity_pricing'))
    high_price = '高价' if np.isfinite(price) and price >= 0.05 else '平价'
    occupied = '有人%g' % occ if np.isfinite(occ) and occ > 0 else '无人'

    has_T = bool(np.isfinite(T))
    if not has_T:
        verdict = '数据缺失（室温不可用）'
    elif hot:
        verdict = f'高温（超上限+{_fmt(hot_over, 2)}°C）'
    elif cold:
        verdict = f'低温（低于下限-{_fmt(cold_over, 2)}°C）'
    else:
        verdict = '舒适（带内）'
    if has_T and not (np.isfinite(occ) and occ > 0):
        verdict += '·无人（不计舒适）'
    if outage:
        verdict += '·停电无法供冷'
    hot_txt = '?' if not has_T else ('是' if hot else '否')
    cold_txt = '?' if not has_T else ('是' if cold else '否')

    return (
        f"> [状态] 室温T={_fmt(T, 2)}°C 舒适带[{_fmt(lo, 2)},{_fmt(hi, 2)}] "
        f"偏差={_fmt(T - cool_sp, 2)}°C 高温={hot_txt} 低温={cold_txt} "
        f"(band={_fmt(band, 2)}) | {occupied} | "
        f"制冷: 需求={_fmt(row.get('cooling_demand'), 2)}kWh 用电={_fmt(row.get('cooling_electricity_consumption'), 2)}kWh "
        f"动作={_fmt(row.get('action_cooling_device'), 3)} | "
        f"电池: SOC={_fmt(row.get('soc'), 3)} 充={_fmt(row.get('battery_charge'), 2)} 放={_fmt(row.get('battery_discharge'), 2)} | "
        f"电价={_fmt(price, 4)}({high_price}) 净用电={_fmt(row.get('net_electricity_consumption'), 2)} "
        f"光伏={_fmt(row.get('solar_generation'), 2)} | 停电={'是' if outage else '否'} "
        f"| 判定={verdict}"
    )


# 首行：观测/动作的数值（与控制台每步诊断的字段对齐 ✓）✓
def format_obs_action_line(row: Mapping[str, Any]) -> str:
    # [详注-BEGIN]（生成简版时整段删除）
    # 首行：观测/动作的数值（与控制台每步诊断的字段对齐 ✓）✓
    # [详注-END]
    outage = float(row.get('power_outage', 0) or 0) >= 0.5
    hot = float(row.get('is_hot', 0) or 0) >= 0.5
    cold = float(row.get('is_cold', 0) or 0) >= 0.5
    tags = []
    if hot:
        tags.append('过热')
    if cold:
        tags.append('过冷')
    if outage:
        tags.append('停电')
    tag_s = ','.join(tags) if tags else '正常'
    return (
        f"> [观测动作] "
        f"T={_fmt(row.get('indoor_temp'))} "
        f"coolSP={_fmt(row.get('cooling_setpoint'))} "
        f"dT={_fmt(row.get('cooling_delta'))} "
        f"band={_fmt(row.get('comfort_band'))} "
        f"occ={_fmt(row.get('occupant_count'), 0)} "
        f"out={1 if outage else 0} "
        f"act_cool={_fmt(row.get('action_cooling_device'), 3)} "
        f"{_raw_act_tag(row, 'cooling_device')}"
        f"act_bat={_fmt(row.get('action_electrical_storage'), 3)} "
        f"cool_kWh={_fmt(row.get('cooling_electricity_consumption'))} "
        f"cool_dem={_fmt(row.get('cooling_demand'))} "
        f"net={_fmt(row.get('net_electricity_consumption'))} "
        f"price={_fmt(row.get('electricity_pricing'), 4)} "
        f"SOC={_fmt(row.get('soc'), 3)} "
        f"R={_fmt(row.get('reward'), 3)} "
        f"| {tag_s}"
    )




# 从一行数据里取楼栋序号（'Building_1' → 0、'agent_0' → 0）；取不到用 fallback ✓
def building_index_from_row(row: Mapping[str, Any], fallback: int = 0) -> int:
    bid = row.get('building_id')
    if bid is None:
        return fallback
    s = str(bid)
    if s.isdigit():
        return int(s)
    # Building_1 / agent_0 等
    for sep in ('_', '-'):
        if sep in s:
            tail = s.rsplit(sep, 1)[-1]
            if tail.isdigit():
                n = int(tail)
                # Building_1 → 0-based index 0
                return n - 1 if n >= 1 and 'building' in s.lower() else n
    return fallback


# 把一行逐步数据组装成界面要展示的「楼栋条目」（状态行 + 奖励各项明细 + 汇总）✓
def build_building_entry(
    row: Mapping[str, Any],
    *,
    building_idx: int,
    reward_detail: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    status = format_obs_action_line(row)
    calc_lines: List[str] = []
    if reward_detail and reward_detail.get('calc_lines'):
        calc_lines = [str(x) for x in reward_detail['calc_lines']]
    elif row.get('reward') is not None:
        calc_lines = [
            f"> [奖励计算] 本步环境回报 R={_fmt(row.get('reward'), 4)} "
            f"（无分项明细：奖励函数未写入 _last_details）"
        ]

    # 行序约定：首行[观测动作]（鼠标悬停可看奖励参数）→ [奖励计算]各项明细 → 末尾[状态]汇总
    narrative_lines = [status] + calc_lines + [format_state_line(row)]
    outage = float(row.get('power_outage', 0) or 0) >= 0.5
    cool_act = row.get('action_cooling_device')
    bat_act = row.get('action_electrical_storage')
    try:
        ele = float(bat_act) if bat_act is not None else 0.0
    except (TypeError, ValueError):
        ele = 0.0
    try:
        tmp = float(cool_act) if cool_act is not None else 0.0
    except (TypeError, ValueError):
        tmp = 0.0

    summary_parts = [
        f"T={_fmt(row.get('indoor_temp'))}",
        f"R={_fmt(row.get('reward'), 3)}",
    ]
    if reward_detail:
        summary_parts.append(
            f"Rt={_fmt(reward_detail.get('r_temp'), 3)} "
            f"Rah={_fmt(reward_detail.get('r_act_hot'), 3)} "
            f"Rac={_fmt(reward_detail.get('r_act_cold'), 3)} "
            f"Rb={_fmt(reward_detail.get('r_below'), 3)} "
            f"Ract={_fmt(reward_detail.get('r_act'), 3)} "
            f"Rc={_fmt(reward_detail.get('r_cost'), 3)} "
            f"Rbat={_fmt(reward_detail.get('r_bat'), 3)}"
        )
        # κ-EMA 摘要：便于日志流一列扫能力尺度
        if reward_detail.get('kappa') is not None or reward_detail.get('e_ref') is not None:
            path = reward_detail.get('kappa_path') or '-'
            upd_flag = '↑' if reward_detail.get('kappa_updated') else '·'
            summary_parts.append(
                f"κ={_fmt(reward_detail.get('kappa'), 3)}{upd_flag} "
                f"Eref={_fmt(reward_detail.get('e_ref'), 3)} "
                f"Eneed={_fmt(reward_detail.get('e_need'), 3)} "
                f"a_need={_fmt(reward_detail.get('a_need'), 2)} "
                f"path={path}"
            )

    return {
        'building': int(building_idx),
        'control_mode': 'outage' if outage else 'marl',
        'outage_flag': bool(outage),
        'decision_summary': ' | '.join(summary_parts),
        'narrative_lines': narrative_lines,
        'battery_soc': row.get('soc'),
        'dhw_soc': None,
        'actions': {
            'init': {'dhw': 0.0, 'ele': ele, 'tmp': tmp},
            'final': {'dhw': 0.0, 'ele': ele, 'tmp': tmp},
        },
        'forecast': {},
        'refine': {'applied': False, 'skip_reason': 'multi_agent_no_refine'},
        'residual': {'enabled': False},
    }


# 把某一步的「全部楼栋条目 + 阶段摘要」组装成一条记录（给 decision_trace.json 用）✓
def build_step_record(
    *,
    step: int,
    hour: Any,
    building_rows: Sequence[Mapping[str, Any]],
    reward_details: Optional[Sequence[Mapping[str, Any]]] = None,
    episode: int = 0,
    reward_label: Optional[str] = None,
) -> Dict[str, Any]:
    buildings = []
    for i, row in enumerate(building_rows):
        b_idx = building_index_from_row(row, fallback=i)
        detail = None
        if reward_details:
            if b_idx < len(reward_details):
                detail = reward_details[b_idx]
            elif i < len(reward_details):
                detail = reward_details[i]
        buildings.append(build_building_entry(row, building_idx=b_idx, reward_detail=detail))

    # 阶段摘要：本方案没有 CHESCA 的五段，只按"观测 → 奖励"两段说明
    r_sum = 0.0
    n_r = 0
    for b in buildings:
        # 从 summary 不好解析；用 narrative 首行 R=
        for ln in b.get('narrative_lines') or []:
            if 'R=' in ln and '[观测动作]' in ln:
                try:
                    part = ln.split('R=')[1].split()[0]
                    r_sum += float(part)
                    n_r += 1
                except (IndexError, ValueError):
                    pass
                break

    phases = [
        {
            'phase': 1,
            'name': 'SAC 策略动作',
            'summary': f'本步 {len(buildings)} 栋楼由独立 Policy 输出 cooling/battery 动作（无规则改写）',
        },
        {
            'phase': 2,
            'name': str(reward_label or 'SymmetricComfortReward'),
            'summary': (
                f'R=R_temp+R_act（κ 上快下慢，E_ref 有地板；冷侧单独封顶）；'
                f'本步各楼回报合计≈{_fmt(r_sum, 3)}（n={n_r}）'
            ),
        },
    ]
    try:
        hour_v = int(hour) if hour is not None and str(hour) != 'nan' else int(step) % 24
    except (TypeError, ValueError):
        hour_v = int(step) % 24

    return {
        'episode': int(episode),
        'step': int(step),
        'hour': hour_v,
        'refine_applied': False,
        'refine_skip_reason': 'multi_agent_no_refine',
        'phases': phases,
        'buildings': buildings,
    }


class MarlDecisionTraceRecorder:
    """逐步收集 Multi-agent 决策推演，结束时落盘 decision_trace.json。

    也支持「内存缓存 + 隔一定步数落盘」：调用 record_step 只追加到内存，
    需要时再调 save() 写整份 JSON（文件始终完整可解析，供界面边跑边看）。
    """

    # 记下楼栋数 / 用的哪套奖励 / 标签，并准备一个空的逐步记录列表 ✓
    def __init__(
        self,
        n_buildings: int,
        reward_kwargs: Mapping[str, Any],
        reward_label: Optional[str] = None,
    ):
        self.n_buildings = int(n_buildings)
        self.reward_kwargs = dict(reward_kwargs)
        self.reward_label = reward_label
        self.steps: List[Dict[str, Any]] = []

    # 把这一步追加进内存里的逐步记录（这一步先不写文件 ✓）✓
    def record_step(
        self,
        *,
        step: int,
        building_rows: Sequence[Mapping[str, Any]],
        reward_details: Optional[Sequence[Mapping[str, Any]]] = None,
        hour: Any = None,
        episode: int = 0,
    ) -> None:
        if hour is None and building_rows:
            hour = building_rows[0].get('hour')
        self.steps.append(
            build_step_record(
                step=step,
                hour=hour,
                building_rows=building_rows,
                reward_details=reward_details,
                episode=episode,
                reward_label=self.reward_label,
            )
        )

    # 把整个记录整理成 decision_trace.json 的顶层结构（版本 / 楼栋数 / 全部步 ✓）✓
    def to_payload(self) -> Dict[str, Any]:
        return {
            'version': 2,
            'agent': 'multi_agent',
            'n_buildings': self.n_buildings,
            'slim': True,
            'reward_kwargs': _json_safe(self.reward_kwargs),
            'steps': self.steps,
        }

    # 把 to_payload() 的结果写成 JSON 文件（整份覆盖 ⇒ 文件任何时候都能解析 ✓）✓
    def save(self, file_path: Path) -> Path:
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(self.to_payload(), ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8',
        )
        return file_path


# -----------------------------------------------------------------------------
# 记录器的"工厂"（2026-10-05 从 Multi-agent.py 下沉到本模块 ✓）
# [详注-BEGIN]（生成简版时整段删除）
#   原先它定义在入口脚本里 ⇒ 诊断脚本用 `ma.build_decision_recorder(...)` 调用；
#   下沉后入口用 `from utils.report import build_decision_recorder` 引入
#   ⇒ `ma.build_decision_recorder` **依然可用** ✓（无需垫片 ✓）
# -----------------------------------------------------------------------------
# [详注-END]
# 按实际楼栋数与奖励函数建好"决策推演"记录器（决定要不要记录这一步），并打印一行开关状态 ✓
def build_decision_recorder(
    citylearn_env: Any,
    *,
    enabled: bool = True,
    every: Optional[int] = None,
    off_reason: str = '',
    log_console: Optional[Callable[[str], None]] = None,
) -> Optional[MarlDecisionTraceRecorder]:
    # [详注-BEGIN]（生成简版时整段删除）
    # 按实际楼栋数与奖励函数建好"决策推演"记录器（决定要不要记录这一步），并打印一行开关状态 ✓
    #
    # 2026-10-06：把入口脚本里那对 ON / OFF 日志**收进本函数** ✓（调用点于是只剩一次调用 ✓）：
    #   · `enabled=False` ⇒ **什么都不建**、返回 `None` ✓，并打印 OFF；
    #     原因由调用方通过 `off_reason` 给全（实调用法：`'--no-trace'` /
    #     `'决策推演依赖模块不可用'` ✓ —— 两个原因都可能，且措辞要能对上现场 ✗）。
    #   · `enabled=True`  ⇒ 建对象 ✓，并打印 ON（含落盘间隔 `every` 与奖励函数名 ✓；
    #     `every=None` ⇒ 取 `DECISION_TRACE_EVERY` ✓，避免调用方为了打日志而多传一个参数 ✓）。
    #
    # 兼容性（重要 ✗）：新参数**全带默认值** ⇒ 旧的 `build_decision_recorder(env)`（诊断脚本
    #   `_smoke_test_decision_trace.py` / `_smoke_test_state_line.py` ✓）行为**不变** ✓；
    #   而 `log_console=None` 时**一句都不打印** ✓ ⇒ 探针不会被日志打扰 ✓。
    #
    # 仍然**不写盘** ✓：写盘由调用方按间隔触发（utils/report.py ✓）。
    #
    # [详注-END]
    if not enabled:
        if log_console is not None:
            log_console(f'决策推演日志=OFF（{off_reason or "未启用"}；KPI 不受影响）')
        return None

    n_buildings = len(getattr(citylearn_env, 'buildings', []) or [])
    # 描述只算一次 ✓：类名直接复用描述里的字段 —— 原先 `type(rf).__name__` 在这里和
# [详注-BEGIN]（生成简版时整段删除）
    #   describe_reward_function 里各算了一遍 ✗，且"没有奖励函数"时两处口径还不一致
    #   （这边 'NoneType' / 描述里 'unknown'）⇒ 现在统一为 'unknown' ✓
# [详注-END]
    from utils.config import describe_reward_function
    info = describe_reward_function(citylearn_env)
    recorder = MarlDecisionTraceRecorder(n_buildings, info, reward_label=info['reward_function'])
    if log_console is not None:
        if every is None:
            from utils.config import DECISION_TRACE_EVERY
            every = DECISION_TRACE_EVERY
        log_console(
            f'决策推演日志=ON（每 {every} 步落盘一次，'
            f'奖励函数={recorder.reward_label or "unknown"}）'
        )
    return recorder

# ============================================================================
# ==== 段：decision_trace（原 utils/report.py ✓）====
# [详注-BEGIN]（生成简版时整段删除）
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# 决策推演「逐步采集」入口（Multi-agent 训练/评估共用）。
# =====================================================
#
# 把仿真某一步的关键量按**楼栋顺序**采成一行，追加进
# `MarlDecisionTraceRecorder` 的内存缓存；**只做内存追加、不写盘** ——
# 写盘由调用方按间隔统一触发（常量 `DECISION_TRACE_EVERY`，默认 144 步；
# 2026-10-05 起它**不再是命令行参数** ✓，见 DECISIONS §17），
# 避免逐步写盘的 IO 开销（文件始终完整可解析，供界面边跑边看）。
#
# 采到的每栋一行（约 30 项）：室温 / 冷热设定点 / 舒适带 / 温差与高低温判定 /
# 动作分量 / 制冷用电 / 冷热负荷 / 净用电 / 光伏 / 电价 / SOC 与电池充放 /
# 是否有人 / 停电 / 奖励；奖励分项明细取自奖励对象的 `_last_details`。
# 字段清单见 `utils.eval_step_trace.building_step_snapshot`。
#
# 顺序契约（重要）
# ----------------
# `ordered_keys` 必须与环境的 agent 顺序一致（Multi-agent.py 传 `env._agent_ids`）：
# `actions` / `rewards` 是 RLlib 那套 `{agent_id: …}` 字典，本模块按下标对齐成列表，
# 顺序错了会把某栋的动作/奖励记到别栋上。这类错位不易察觉，只能靠逐组分解
# `decision_trace.json` 定位（历史事故与判据见 DECISIONS.md §9.6.2、§11.5）。
# [详注-END]



from typing import Any, List, Mapping, Optional, Sequence


# 把奖励侧「实际执行动作」(`rf._pending_acts`) 还原成与楼栋同序的向量列表 ✓
def _applied_action_vectors(citylearn_env: Any) -> Optional[List[Any]]:
    # [详注-BEGIN]（生成简版时整段删除）
    # 把奖励侧「实际执行动作」(`rf._pending_acts`) 还原成与楼栋同序的向量列表。
    #
    # 钩子 `install_action_hook` 在 `env.step` 内部，把每栋的动作按 `active_actions` 的名字
    # 写成 `{'cooling_device_action': 0.5, …}` ⇒ 这里按**同一套名字顺序**还原成向量，
    # 与 `building_step_snapshot` 写列的顺序天然一致 ✓（顺序错了会把动作记到别栋 ✗）
    #
    # 取不到（未装钩子 / 楼栋数不齐）⇒ 返回 None，调用方回退成"只写原始值一列" ✓
    #
    # [详注-END]
    rf = getattr(citylearn_env, 'reward_function', None)
    pending = list(getattr(rf, '_pending_acts', None) or [])
    if not pending:
        return None
    out: List[Any] = []
    for i, building in enumerate(list(getattr(citylearn_env, 'buildings', []) or [])):
        names = list(getattr(building, 'active_actions', None) or [])
        item = pending[i] if i < len(pending) else None
        if not names or not isinstance(item, dict):
            out.append(None)
            continue
        out.append([item.get(f'{name}_action', float('nan')) for name in names])
    return out


# 把本步关键参数（室温/设定点/温差/动作/制冷用电/电价/SOC/回报）缓存进内存 ✓
def record_step_trace(
    recorder: MarlDecisionTraceRecorder,
    citylearn_env: Any,
    *,
    step_count: int,
    ordered_keys: Sequence[Any],
    actions: Mapping[Any, Sequence[float]],
    rewards: Any,
) -> None:
    # [详注-BEGIN]（生成简版时整段删除）
    # 把本步关键参数（室温/设定点/温差/动作/制冷用电/电价/SOC/回报）缓存进内存。
    #
    # 只做内存追加，不写盘；写盘由调用方按间隔统一触发，保证效率。
    #
    # `rewards` 是 RLlib 多智能体 `env.step()` 的返回字典（`{agent_id: 标量}`）；
    # 不是 dict 时留空 ⇒ 快照里 reward 为 NaN（不报错）。
    #
    # 动作写**两列**（P0-B 协议 ✓）：
    #   · `action_<名字>`     = 建筑**实际执行**的动作（取自奖励侧 `rf._pending_acts`，
    #                          由 install_action_hook 在 env.step 内注入 ✓）
    #   · `action_<名字>_raw` = 策略网络的**原始输出**（= 调用方传进来的 `actions` ✓）
    #   ⇒ 取不到"实际执行值"时退回只写原始列，且**不**写 `_raw` ⇒ 界面不会附 `(raw=…)` ✓
    #
    # [详注-END]
    raw_list = [actions.get(k) for k in ordered_keys]        # 策略原始输出（调用方给的就是它 ✓）
    applied_list = _applied_action_vectors(citylearn_env)    # 建筑实际执行值（只有奖励侧看得见 ✓）
    reward_list = None
    if isinstance(rewards, dict):
        reward_list = [rewards.get(k) for k in ordered_keys]
    rows = collect_citylearn_step_rows(
        citylearn_env,
        step_count=step_count,
        action_list=applied_list or raw_list,                 # 有实际执行值就用它 ✓
        raw_action_list=raw_list if applied_list else None,   # 否则不写 `_raw` 列 ✓
        reward_list=reward_list,
    )
    rf = getattr(citylearn_env, 'reward_function', None)
    recorder.record_step(
        step=step_count,
        building_rows=rows,
        reward_details=list(getattr(rf, '_last_details', None) or []) or None,
    )


# "决策推演"（把每步观测/动作/奖励写成一条记录）的文件放哪：优先 CityLearn 渲染目录，没有就放 --output-dir ✓
def decision_trace_path(citylearn_env, output_dir: Path) -> Path:
    # [详注-BEGIN]（生成简版时整段删除）
    # "决策推演"（把每步观测/动作/奖励写成一条记录）的文件放哪：优先 CityLearn 渲染目录，没有就放 --output-dir ✓
    # [详注-END]
    folder = getattr(citylearn_env, 'new_folder_path', None)
    return (Path(folder) if folder else Path(output_dir)) / 'decision_trace.json'

# ============================================================================
# ==== 段：kpi_output（原 utils/report.py ✓）====
# [详注-BEGIN]（生成简版时整段删除）
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# 把评估结果 KPI 表按 Java 平台可解析的格式输出（`outputkpi` 行）。
# =====================================================================
#
# `Multi-agent-eval.py` 跑完仿真后会调用它：先打一行 `outputkpi` 作为标记，再把 KPI
# DataFrame 的每个索引行打成 `索引 值1 值2 …`（数值统一 `%.6g`，缺失打 `NaN`）✓
# 平台侧按这两类行解析出指标表 ✓
#
# 原先该函数内联在入口脚本里（生成的 train/eval 各存一份 ✗）；抽到此处后三个入口
# 共用一份实现 ✓
# [详注-END]



import pandas as pd

from utils.base import log_console

# 按平台的 outputkpi 协议把 KPI 逐行打印出来（Java 侧据此解析 ✓）✓
def print_kpis_for_java(kpis_df):
    log_console('outputkpi')
    for idx in kpis_df.index:
        vals = []
        for col in kpis_df.columns:
            v = kpis_df.loc[idx, col]
            vals.append('NaN' if pd.isna(v) else f'{float(v):.6g}')
        print(f'{idx} {" ".join(vals)}', flush=True)

