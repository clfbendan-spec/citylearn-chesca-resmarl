"""
CHESCA 决策链路 trace 记录与导出（Decision Trace）。

- chesca_trace.csv：宽表，每步×每建筑一行，供图表分析
- decision_trace.json：按步聚合的决策推演日志，供网页时间线展示
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from checa.narrative_code_refs import build_narrative_entries
from checa.utils import building_net_electricity_consumption

TRACE_COLUMNS = [
    'episode',
    'step',
    'hour',
    'building',
    'outage_flag',
    'control_mode',
    'refine_skip_reason',
    'actual_outdoor_temp',
    'forecast_outdoor_temp',
    'forecast_outdoor_next',
    'abs_pct_error_outdoor_temp',
    'actual_solar',
    'forecast_solar',
    'forecast_solar_next',
    'abs_pct_error_solar',
    'actual_load',
    'forecast_load',
    'forecast_load_next',
    'abs_pct_error_load',
    'actual_dhw',
    'forecast_dhw',
    'forecast_dhw_next',
    'abs_pct_error_dhw',
    'battery_soc',
    'dhw_soc',
    'action_dhw_init',
    'action_ele_init',
    'action_tmp_init',
    'action_dhw_final',
    'action_ele_final',
    'action_tmp_final',
    'refine_applied',
    'trigger_reduce_load',
    'trigger_increase_load',
    'net_load_next',
    'net_load_mean',
    'net_load_std',
    'battery_search_cost',
    'balance_type',
    'tau',
    'B_low',
    'B_high',
    'TMP_max_reduction_percent',
    # 冷机 PID 推演（观测「供电不足 / 需求过小」）
    'pid_error',
    'pid_P',
    'pid_I',
    'pid_D',
    'pid_raw_output',
    'pid_raw_demand',
    'pid_electrical_demand',
    'pid_saturated_perc',
    'pid_anti_windup_frozen',
    'pid_outage_flag',
    'overheat_c',
    'min_cool_kwh',
    'min_cool_applied',
    'capped_by_available_elec',
    'expected_available_elec',
    'cooling_nominal_power',
    # 本步高温不适判定（对齐 CityLearn discomfort_hot_proportion）
    'kpi_indoor_temp',
    'kpi_indoor_temp_obs',
    'kpi_indoor_source',
    'kpi_cooling_set_point',
    'kpi_heating_set_point',
    'kpi_comfort_band',
    'kpi_occupant_count',
    'kpi_setpoint_source',
    'kpi_dynamics_note',
    'kpi_cooling_delta',
    'kpi_hot_threshold',
    'kpi_is_occupied',
    'kpi_is_hot_discomfort',
    'kpi_hot_discomfort_skip_reason',
    'decision_summary',
    'decision_narrative',
    'resmarl_enabled',
    'residual_alpha',
    'residual_applied',
    'residual_skip_reason',
    'residual_delta_dhw',
    'residual_delta_ele',
    'residual_delta_tmp',
    'residual_raw_delta_dhw',
    'residual_raw_delta_ele',
    'residual_raw_delta_tmp',
    'residual_base_dhw',
    'residual_base_ele',
    'residual_base_tmp',
    'residual_final_dhw',
    'residual_final_ele',
    'residual_final_tmp',
]

PHASE_NAMES = {
    1: '时序预测',
    2: '初稿动作',
    3: '未来用电估计',
    4: '电池 Refine',
    5: '净负荷更新',
    6: 'ResMARL 残差',
}


def _fmt(value: Any) -> str:
    if value is None or value == '':
        return ''
    if isinstance(value, (bool, np.bool_)):
        return '1' if value else '0'
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return ''
        return f'{float(value):.6g}'
    return str(value)


def _abs_pct_error(actual: Optional[float], predicted: Optional[float]) -> Optional[float]:
    if actual is None or predicted is None:
        return None
    if np.isnan(actual) or np.isnan(predicted):
        return None
    denom = abs(actual) if abs(actual) > 1e-9 else 1.0
    return abs(actual - predicted) / denom


def _fmt_num(value: Any, digits: int = 3) -> str:
    if value is None or value == '':
        return '-'
    try:
        n = float(value)
        if np.isnan(n):
            return '-'
        return f'{n:.{digits}f}'
    except (TypeError, ValueError):
        return str(value)


def _truthy(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value in (None, ''):
        return False
    if isinstance(value, (int, float, np.floating, np.integer)):
        try:
            return bool(float(value))
        except (TypeError, ValueError):
            return False
    return str(value).strip().lower() in ('1', 'true', 'yes')


def _cooling_pid_narrative_lines(row: Dict[str, Any], mode: str = 'normal') -> List[str]:
    """
    冷机 PID 推演剧本行：先列入参与中间量，再写供电/需求结论。
    便于排查「冷机出力小」是 PID 需求本身小，还是可用电量封顶。
    """
    # 无 PID 埋点时跳过（旧 trace / 未跑过 find_best_action）
    has_pid = any(
        row.get(k) not in (None, '')
        for k in ('pid_error', 'pid_raw_output', 'pid_raw_demand', 'pid_electrical_demand')
    )
    if not has_pid:
        return []

    lines: List[str] = []
    indoor = row.get('pid_indoor_temp', row.get('indoor_temp'))
    setpoint = row.get('pid_setpoint_temp', row.get('setpoint_temp'))
    outdoor = row.get('pid_outdoor_temp', row.get('forecast_outdoor_next'))
    error = row.get('pid_error')
    sat = row.get('pid_saturated_perc', row.get('saturation_perc'))
    p_term = row.get('pid_P')
    i_term = row.get('pid_I')
    d_term = row.get('pid_D')
    outdoor_term = row.get('pid_outdoor_term')
    raw_out = row.get('pid_raw_output')
    raw_demand = row.get('pid_raw_demand', raw_out)
    final_demand = row.get('pid_electrical_demand')
    overheat = row.get('overheat_c')
    min_cool = row.get('min_cool_kwh')
    nominal = row.get('cooling_nominal_power')
    avail = row.get('expected_available_elec')
    tmp = row.get('tmp_action', row.get('action_tmp_init'))
    capped = _truthy(row.get('capped_by_available_elec'))
    min_cool_on = _truthy(row.get('min_cool_applied'))
    anti_wu = _truthy(row.get('pid_anti_windup_frozen'))
    # 以实际 get_actions 的 outage_flag 为准；旧数据缺失时再回退 control_mode
    if row.get('pid_outage_flag') not in (None, ''):
        outage_pid = _truthy(row.get('pid_outage_flag'))
    else:
        outage_pid = mode == 'outage'

    # 1) 入参
    indoor_obs = row.get('indoor_temp_obs')
    indoor_src = row.get('indoor_temp_source') or ''
    src_note = ''
    if indoor_src:
        src_note = f'（来源 {indoor_src}'
        if indoor_obs not in (None, '') and indoor not in (None, ''):
            try:
                if abs(float(indoor_obs) - float(indoor)) > 0.05:
                    src_note += f'；观测室温 {_fmt_num(indoor_obs, 2)}°C'
            except (TypeError, ValueError):
                pass
        src_note += '）'
    lines.append(
        f'> [冷机PID推演] 入参：室内 {_fmt_num(indoor, 2)}°C{src_note}，设定 {_fmt_num(setpoint, 2)}°C，'
        f'室外 {_fmt_num(outdoor, 1)}°C，error=设定-室内={_fmt_num(error, 3)}°C，'
        f'饱和度 saturated_perc={_fmt_num(sat, 3)}，'
        f'PID分支={"停电简化" if outage_pid else "正常PID"}。'
    )

    # 2) 中间量 P/I/D（或停电项）
    if outage_pid:
        lines.append(
            f'> [冷机PID推演] 计算：P={_fmt_num(p_term)}，'
            f'室外项 OutTempScaler*(室外-室内)={_fmt_num(outdoor_term)}，'
            f'PID原始输出={_fmt_num(raw_out)}（电功率需求粗值）。'
        )
    else:
        aw = '是（积分已冻结、未继续负向累积）' if anti_wu else '否'
        lines.append(
            f'> [冷机PID推演] 计算：P={_fmt_num(p_term)}，I={_fmt_num(i_term)}，'
            f'D={_fmt_num(d_term)}，PID原始输出={_fmt_num(raw_out)}；'
            f'负向anti-windup冻结积分={aw}。'
        )

    # 3) 封顶 / 舒适保底 → 最终电需求 → TMP
    avail_txt = (
        '无上限（正常工况）' if avail in (None, '') else _fmt_num(avail)
    )
    lines.append(
        f'> [冷机PID推演] 封顶与换算：PID需求 {_fmt_num(raw_demand)}，'
        f'过热 overheat={_fmt_num(overheat, 3)}°C，'
        f'最小制冷保底 min_cool={_fmt_num(min_cool)}'
        f'{"（已应用）" if min_cool_on else "（未触发）"}，'
        f'可用电量上限={avail_txt}'
        f'{"（已封顶↓）" if capped else "（未封顶）"}，'
        f'最终电需求={_fmt_num(final_demand)}，'
        f'额定功率={_fmt_num(nominal)}，'
        f'TMP=需求/额定={_fmt_num(tmp, 3)}。'
    )

    # 4) 结论：方便判断「供电不足」还是「需求本身就小」
    reason_bits: List[str] = []
    try:
        rd = float(raw_demand) if raw_demand not in (None, '') else None
        av = float(avail) if avail not in (None, '') else None
        fd = float(final_demand) if final_demand not in (None, '') else None
        oh = float(overheat) if overheat not in (None, '') else None
    except (TypeError, ValueError):
        rd = av = fd = oh = None

    if capped and rd is not None and av is not None and np.isfinite(av) and rd > av + 1e-9:
        reason_bits.append(
            f'可用电量不足：PID想要 {_fmt_num(rd)}，但只允许 {_fmt_num(av)}，出力被电力上限压低'
        )
    elif rd is not None and rd <= 1e-6:
        reason_bits.append(
            f'PID原始需求≈0（error={_fmt_num(error, 3)}），控制认为几乎不需要制冷，并非电力封顶'
        )
    elif rd is not None and fd is not None and abs(rd) < 0.15 and not capped:
        reason_bits.append(
            f'PID需求本身偏小（{_fmt_num(rd)}），未触达可用电量上限，冷机供电不足更可能来自控制需求过低'
        )
    if oh is not None and oh <= 1e-6 and not min_cool_on:
        reason_bits.append('观测过热≤0，舒适最小制冷保底未生效')
    if anti_wu:
        reason_bits.append('本拍触发负向anti-windup，积分未继续往负需求累积')
    if not reason_bits:
        reason_bits.append('见上方数值：对照「PID需求 vs 可用电量 vs TMP」判断瓶颈')

    lines.append(f'> [冷机PID推演] 结论：{"；".join(reason_bits)}。')
    return lines


def _hot_discomfort_narrative_lines(row: Dict[str, Any]) -> List[str]:
    """
    本步高温不适判定剧本（对齐 CityLearn discomfort_hot_proportion 单步逻辑）。

    公式：cooling_delta = indoor - cooling_set_point
          有人且 cooling_delta > comfort_band → 本步高温不适
    """
    indoor = row.get('kpi_indoor_temp')
    cooling_sp = row.get('kpi_cooling_set_point')
    # 无 KPI 埋点时跳过（旧 trace）
    if indoor in (None, '') and cooling_sp in (None, ''):
        return []

    lines: List[str] = []
    band = row.get('kpi_comfort_band')
    occupant = row.get('kpi_occupant_count')
    delta = row.get('kpi_cooling_delta')
    threshold = row.get('kpi_hot_threshold')
    occupied = _truthy(row.get('kpi_is_occupied'))
    is_hot = _truthy(row.get('kpi_is_hot_discomfort'))
    source = row.get('kpi_setpoint_source') or '-'
    skip = row.get('kpi_hot_discomfort_skip_reason') or ''

    lines.append(
        f'> [高温不适判定] 入参：室内 {_fmt_num(indoor, 2)}°C'
        f'（来源 {row.get("kpi_indoor_source") or "-"}），'
        f'制冷设定 cooling_set_point={_fmt_num(cooling_sp, 2)}°C'
        f'（来源 {source}），'
        f'舒适带宽 band={_fmt_num(band, 1)}°C，'
        f'占用人数 occupant={_fmt_num(occupant, 0)}。'
    )
    note = row.get('kpi_dynamics_note') or ''
    if note:
        lines.append(f'> [高温不适判定] 说明：{note}。')
    lines.append(
        f'> [高温不适判定] 计算：cooling_delta=室内-制冷设定='
        f'{_fmt_num(delta, 3)}°C；'
        f'过热阈值=制冷设定+band={_fmt_num(threshold, 2)}°C；'
        f'占用={("是" if occupied else "否")}；'
        f'判定条件为「占用且 cooling_delta > band」。'
    )

    if skip and not is_hot:
        lines.append(f'> [高温不适判定] 结论：本步不计为高温不适（{skip}）。')
    elif is_hot:
        lines.append(
            f'> [高温不适判定] 结论：是高温不适'
            f'（cooling_delta {_fmt_num(delta, 3)}°C > band {_fmt_num(band, 1)}°C），'
            f'本步会计入 discomfort_hot_proportion。'
        )
    else:
        try:
            d = float(delta) if delta not in (None, '') else None
            bd = float(band) if band not in (None, '') else None
            margin = (bd - d) if (d is not None and bd is not None) else None
        except (TypeError, ValueError):
            margin = None
        margin_txt = (
            f'距过热阈值还差 {_fmt_num(margin, 3)}°C'
            if margin is not None else '未超过带宽'
        )
        lines.append(
            f'> [高温不适判定] 结论：否（未达高温不适），{margin_txt}。'
        )
    return lines


def _build_decision_summary(
    row: Dict[str, Any],
    global_refine: bool,
) -> str:
    """生成单建筑、单步的中文决策摘要。"""
    parts: List[str] = []
    mode = row.get('control_mode') or ('outage' if row.get('outage_flag') else 'normal')
    parts.append('停电保冷' if mode == 'outage' else '正常工况')

    if row.get('forecast_load_next') not in (None, ''):
        parts.append(f"预测负荷 {_fmt_num(row.get('forecast_load_next'))} kWh")
    if row.get('forecast_solar_next') not in (None, ''):
        parts.append(f"预测光伏 {_fmt_num(row.get('forecast_solar_next'))} kWh")

    init = (
        f"DHW {_fmt_num(row.get('action_dhw_init'), 2)}"
        f"/ ELE {_fmt_num(row.get('action_ele_init'), 2)}"
        f"/ TMP {_fmt_num(row.get('action_tmp_init'), 2)}"
    )
    final = (
        f"DHW {_fmt_num(row.get('action_dhw_final'), 2)}"
        f"/ ELE {_fmt_num(row.get('action_ele_final'), 2)}"
        f"/ TMP {_fmt_num(row.get('action_tmp_final'), 2)}"
    )
    parts.append(f"初稿 [{init}]")

    if not global_refine:
        parts.append('Refine 跳过(首步无历史)')
    elif row.get('outage_flag'):
        parts.append('Refine 跳过(停电)')
    elif row.get('refine_applied'):
        parts.append(f"Refine 后 [{final}]")
        if row.get('trigger_reduce_load'):
            parts.append('触发 B_high 减负荷')
        elif row.get('trigger_increase_load'):
            parts.append('触发 B_low 增负荷')
        else:
            parts.append('净负荷在阈值带内')
        if row.get('battery_search_cost') not in (None, ''):
            parts.append(f"树搜索 cost {_fmt_num(row.get('battery_search_cost'), 4)}")
    else:
        parts.append(f"终稿 [{final}]")

    return '；'.join(parts)


def _load_intensity_label(kwh: Optional[float]) -> str:
    if kwh is None or kwh == '':
        return '未知'
    try:
        v = float(kwh)
        if np.isnan(v):
            return '未知'
    except (TypeError, ValueError):
        return '未知'
    if v >= 100:
        return '极高'
    if v >= 50:
        return '偏高'
    if v >= 20:
        return '适中'
    return '偏低'


def _battery_action_desc(action: Optional[float]) -> str:
    if action is None or action == '':
        return '维持待机'
    try:
        a = float(action)
    except (TypeError, ValueError):
        return '维持待机'
    if a < -0.05:
        return f'放电，基准动作：{_fmt_num(a, 2)}'
    if a > 0.05:
        return f'充电，基准动作：{_fmt_num(a, 2)}'
    return f'维持待机，基准动作：{_fmt_num(a, 2)}'


def _error_pct_hint(row: Dict[str, Any], field: str) -> str:
    err = row.get(field)
    if err in (None, ''):
        return ''
    try:
        return f'（上步预测误差 {_fmt_num(float(err) * 100, 1)}%）'
    except (TypeError, ValueError):
        return ''


def _build_decision_narrative_lines(
    row: Dict[str, Any],
    global_refine: bool,
    electricity_pricing: Optional[float] = None,
) -> List[str]:
    """生成分层、带时间戳的推演剧本（CHESCA + 可选 ResMARL 残差层）。"""
    hour = int(row.get('hour') or 0)
    b = int(row.get('building') or 0)
    building_name = f'Building_{b + 1}'
    lines: List[str] = [f'[{hour:02d}:00] 开始计算 {building_name} 动作...']

    actual_net = row.get('actual_net_load')
    if actual_net not in (None, ''):
        lines.append(
            f'> [本栋实况] 本栋实际上一步净用电 {_fmt_num(actual_net)} kWh'
            f'。'
        )

    community_actual = row.get('community_actual_net_load')
    community_pred = row.get('community_pred_net_next')
    if community_actual not in (None, '') or community_pred not in (None, ''):
        lines.append(
            f'> [社区负荷] 三栋实际上步净用电合计 {_fmt_num(community_actual)} kWh，'
            f'预测下步净用电合计 {_fmt_num(community_pred)} kWh。'
        )

    load_next = row.get('forecast_load_next')
    solar_next = row.get('forecast_solar_next')
    dhw_next = row.get('forecast_dhw_next')
    outdoor_next = row.get('forecast_outdoor_next')
    pred_net = None
    if load_next not in (None, '') and solar_next not in (None, ''):
        try:
            pred_net = float(load_next) - float(solar_next)
        except (TypeError, ValueError):
            pred_net = None

    forecast_parts = []
    if outdoor_next not in (None, ''):
        forecast_parts.append(
            f'下步室外温 {_fmt_num(outdoor_next, 1)}°C{_error_pct_hint(row, "abs_pct_error_outdoor_temp")}'
        )
    if load_next not in (None, ''):
        forecast_parts.append(
            f'不可调负荷 {_fmt_num(load_next)} kWh{_error_pct_hint(row, "abs_pct_error_load")}'
        )
    if solar_next not in (None, ''):
        forecast_parts.append(
            f'光伏 {_fmt_num(solar_next)} kWh{_error_pct_hint(row, "abs_pct_error_solar")}'
        )
    if dhw_next not in (None, ''):
        forecast_parts.append(
            f'DHW 需求 {_fmt_num(dhw_next)} kWh{_error_pct_hint(row, "abs_pct_error_dhw")}'
        )
    if pred_net is not None:
        intensity = _load_intensity_label(pred_net)
        forecast_parts.append(f'粗算净负荷 {intensity} ({_fmt_num(pred_net)} kWh，未含设备）')
    lines.append(f'> [预测层] ForecastAgent / XGBoost：{"，".join(forecast_parts) or "时序预测完成"}。')

    mode = row.get('control_mode') or ('outage' if row.get('outage_flag') else 'normal')
    indoor = row.get('indoor_temp')
    setpoint = row.get('setpoint_temp')
    pid_demand = row.get('pid_electrical_demand')
    tmp_init = row.get('action_tmp_init')
    pred_cool = row.get('pred_cooling_kwh') or row.get('pred_cooling_kwh_final')

    # 制冷(TMP)：先列温度等数据，再写判定与动作
    temp_prefix = (
        f'室内温度：{_fmt_num(indoor, 1)}°C，设定温度：{_fmt_num(setpoint, 1)}°C，'
        f'室外温度：{_fmt_num(outdoor_next, 1)}°C'
    )
    if mode == 'outage':
        lines.append(
            f'> [空调控制] {temp_prefix}；当前电网停电，进入节能保冷模式；'
            f'实际下发空调控制指令为 {_fmt_num(tmp_init, 2)}，预计耗电 {_fmt_num(pred_cool)} 度。'
        )
        expected_elec = row.get('expected_available_elec')
        max_batt_elec = row.get('max_elec_in_battery')
        avail_soc = row.get('available_battery_soc')
        if expected_elec not in (None, ''):
            lines.append(
                f'> [停电供电盘点] 电池剩余可用容量比例为 {_fmt_num(avail_soc, 2)}，'
                f'折合电量 {_fmt_num(max_batt_elec)} 度，'
                f'结合当前光伏发电，共有 {_fmt_num(expected_elec)} 度电可供系统调度。'
            )
    else:
        comfort = '室温数据未知，默认按低制冷需求处理'
        if indoor not in (None, '') and setpoint not in (None, ''):
            try:
                delta_t = float(indoor) - float(setpoint)
                if delta_t > 0:
                    comfort = f'室温过高（高于设定目标 {_fmt_num(abs(delta_t), 1)}°C），需要加强制冷'
                elif delta_t < 0:
                    comfort = f'室温偏低（低于设定目标 {_fmt_num(abs(delta_t), 1)}°C），制冷需求较小'
                else:
                    comfort = '室温已达标，维持最低制冷能耗即可'
            except (TypeError, ValueError):
                pass
        pid_hint = ''
        if pid_demand not in (None, ''):
            pid_hint = f'预估空调耗电需求为 {_fmt_num(pid_demand)} 度，'
        lines.append(
            f'> [空调控制] {temp_prefix}；{comfort}；'
            f'{pid_hint}实际下发空调控制指令为 {_fmt_num(tmp_init, 2)}，'
            f'预计耗电 {_fmt_num(pred_cool)} 度。'
        )

    # --- 本步高温不适判定（对齐 CityLearn discomfort_hot_proportion 单步）---
    lines.extend(_hot_discomfort_narrative_lines(row))

    # --- 冷机 PID 推演：入参 → 中间量 → 封顶/保底 → TMP（便于排查「供电不足」）---
    lines.extend(_cooling_pid_narrative_lines(row, mode=mode))

    # --- 供热(DHW) 剧本行：对应 agent 初稿里的规则控制（原 RBC）---
    # 规则（正常工况，见 agent.py）：
    #   heat_water = (预测需求 < 24h 均值) and (DHW SOC < 0.9)
    #   True  → heat_storage：用电加热储热水箱（DHW 动作为正）
    #   False → discharge_storage：从储热水箱放热满足热水（DHW 动作为负）
    # 此处只写叙事：先列判据用到的数据，再写策略结论与初稿动作 action_dhw_init
    # （最终 DHW 还可能被安全审查 / ResMARL 改写）
    dhw_strategy = row.get('dhw_strategy', '')
    dhw_init = row.get('action_dhw_init')
    dhw_soc = row.get('dhw_soc')
    building_dhw = row.get('building_dhw_demand')
    avg_dhw = row.get('avg_dhw_demand')
    heat_water = row.get('heat_water')
    pred_dhw = row.get('pred_dhw_kwh') or row.get('pred_dhw_kwh_final')
    # 判据三件套：本步预测热水需求、历史 24h 均值、储热罐荷电状态
    dhw_data = (
        f'预估热水需求为：{_fmt_num(building_dhw)} kWh，'
        f'过去24小时平均需求为：{_fmt_num(avg_dhw)} kWh，'
        f'当前水箱剩余容量比例为：{_fmt_num(dhw_soc, 2)}'
    )
    # 储热需同时满足：需求 < 均值 且 DHW SOC < 0.9；下列出各子条件是否成立
    demand_ok = None
    soc_ok = None
    try:
        if building_dhw not in (None, '') and avg_dhw not in (None, ''):
            demand_ok = float(building_dhw) < float(avg_dhw)
        if dhw_soc not in (None, ''):
            soc_ok = float(dhw_soc) < 0.9
    except (TypeError, ValueError):
        demand_ok = soc_ok = None
        
    demand_cmp = (
        f'当前需求 {_fmt_num(building_dhw)} '
        f'{"低于" if demand_ok else "达到或超过"} 平均值 {_fmt_num(avg_dhw)}'
        if demand_ok is not None else f'需求/平均值：{_fmt_num(building_dhw)}/{_fmt_num(avg_dhw)}'
    )
    soc_cmp = (
        f'水箱容量比例 {_fmt_num(dhw_soc, 2)} '
        f'{"低于" if soc_ok else "达到或超过"} 0.9'
        if soc_ok is not None else f'水箱容量比例：{_fmt_num(dhw_soc, 2)}'
    )
    heat_rule_check = f'{demand_cmp}，{soc_cmp}'

    if mode == 'outage':
        # 停电优先保冷机，DHW 策略降级（让路）
        lines.append(
            f'> [热水控制] {dhw_data}；当前电网停电，热水系统暂停加热以优先保障空调制冷；'
            f'实际下发热水控制指令为 {_fmt_num(dhw_init, 2)}，预计耗电 {_fmt_num(pred_dhw)} 度。'
        )
    elif dhw_strategy == 'heat_storage':
        # 需求偏低且罐未满 → 趁机储热（正动作 ≈ 加热耗电）
        lines.append(
            f'> [热水控制] {dhw_data}；满足提前加热条件（{heat_rule_check}），系统启动热水器进行储热；'
            f'实际下发热水控制指令为 {_fmt_num(dhw_init, 2)}，预计耗电 {_fmt_num(pred_dhw)} 度。'
        )
    elif dhw_strategy == 'discharge_storage':
        # 未满足储热条件 → 从罐中放热；写明哪条子条件未过
        fail_parts = []
        if demand_ok is False:
            fail_parts.append(f'需求未低于平均值（{demand_cmp}）')
        if soc_ok is False:
            fail_parts.append(f'水箱已接近满载（{soc_cmp}）')
        if fail_parts:
            fail_txt = '；'.join(fail_parts)
        else:
            fail_txt = heat_rule_check
        lines.append(
            f'> [热水控制] {dhw_data}；未满足提前加热条件（要求「需求低于均值」且「水箱容量低于0.9」，当前状态为：{fail_txt}），系统暂停加热，直接使用水箱内储存的热水；'
            f'实际下发热水控制指令为 {_fmt_num(dhw_init, 2)}，预计耗电 {_fmt_num(pred_dhw)} 度。'
        )
    else:
        # 兜底：未知 strategy 字符串（如旧 trace / 异常路径）
        lines.append(
            f'> [热水控制] {dhw_data}；执行常规热水控制规则（{heat_rule_check}）；'
            f'实际下发热水控制指令为 {_fmt_num(dhw_init, 2)}，预计耗电 {_fmt_num(pred_dhw)} 度。'
        )

    battery_soc = row.get('battery_soc')
    min_soc = row.get('min_battery_soc')
    soc_margin = None
    if battery_soc not in (None, '') and min_soc not in (None, ''):
        try:
            soc_margin = float(battery_soc) - float(min_soc)
        except (TypeError, ValueError):
            soc_margin = None
    if soc_margin is not None:
        lines.append(
            f'> [电池状态] 当前电池容量比例：{_fmt_num(battery_soc, 2)}，本小时允许降至的最低安全线：{_fmt_num(min_soc, 2)}，'
            f'实际可灵活调度的余量为：{_fmt_num(soc_margin, 2)}。'
        )

    ele_init = row.get('action_ele_init')
    pred_batt = row.get('pred_battery_kwh') or row.get('pred_battery_kwh_final')
    if mode == 'normal' and float(ele_init or 0) == 0.0:
        lines.append(
            f'> [初步计划] 电池初步控制指令设为 {_fmt_num(ele_init, 2)}，预计电池耗电：{_fmt_num(pred_batt)} 度；'
            f'正常工况下暂不直接干预，将充放电决策权交给后续的深度推演算法。'
        )

    if not global_refine:
        lines.append(
            '> [电池调度推演] 当前为运行首步，缺乏历史用电数据，暂不进行未来趋势推演。'
        )
    elif row.get('outage_flag'):
        lines.append(
            f'> [电池调度推演] 确认发生停电，当前电池容量比例：{_fmt_num(battery_soc, 2)}；'
            f'停电建筑将暂停常规的电池充放电深度推演。'
        )
    else:
        ele_search = row.get('ele_after_search', row.get('action_ele_final'))
        cost = row.get('battery_search_cost')
        net_before_batt = row.get('predicted_net_load_step1')
        ts_mean = row.get('tree_state_mean', row.get('net_load_mean'))
        ts_soc = row.get('tree_state_soc', battery_soc)
        ts_cur = row.get('tree_state_net_current')
        ts_s1 = row.get('tree_state_net_step1', net_before_batt)
        state_txt = (
            f'历史平均用电：{_fmt_num(ts_mean)} 度，当前电池容量比例：{_fmt_num(ts_soc, 2)}，'
            f'当前净用电：{_fmt_num(ts_cur)} 度，预计下步净用电：{_fmt_num(ts_s1)} 度'
        )
        tree_ctx = ''
        if net_before_batt not in (None, ''):
            tree_ctx = (
                f'预测下一步净用电为 {_fmt_num(net_before_batt)} 度（属于{_load_intensity_label(net_before_batt)}用电压力），'
                f'为了平稳整体电网波动，'
            )
        cost_txt = f'，该方案的系统评估代价分数为 {_fmt_num(cost, 4)}' if cost not in (None, '') else ''
        lines.append(
            f'> [电池调度推演] 综合评估以下状态：{state_txt}；{tree_ctx}'
            f'系统决定让电池{_battery_action_desc(ele_search)}{cost_txt}。'
        )

    pricing = electricity_pricing if electricity_pricing is not None else row.get('electricity_pricing')
    if pricing not in (None, ''):
        try:
            p = float(pricing)
            lines.append(
                f'> [电价参考] 当前电价为 {_fmt_num(p, 3)} 元/度'
                f'（注：当前规则控制未直接以电价作为优化目标，仅作背景参考）。'
            )
        except (TypeError, ValueError):
            pass

    ele_final = row.get('action_ele_final')
    dhw_final = row.get('action_dhw_final')
    tmp_final = row.get('action_tmp_final')
    ele_search = row.get('ele_after_search', ele_final)
    ele_delta = None
    try:
        if ele_search not in (None, '') and ele_final not in (None, ''):
            ele_delta = float(ele_final) - float(ele_search)
    except (TypeError, ValueError):
        ele_delta = None

    if ele_delta is not None and abs(ele_delta) > 0.01:
        direction = '追加放电' if ele_delta < 0 else '追加充电'
        lines.append(
            f'> [全局微调] 经过推演后，出于全局考虑对电池{direction} {_fmt_num(abs(ele_delta), 2)}，'
            f'最终下发的电池控制指令为 {_fmt_num(ele_final, 2)}。'
        )

    b_high = row.get('b_high_threshold')
    b_low = row.get('b_low_threshold')
    net_next = row.get('net_load_next')
    net_mean = row.get('net_load_mean')
    net_std = row.get('net_load_std')
    trigger_reduce = bool(row.get('trigger_reduce_load'))
    trigger_increase = bool(row.get('trigger_increase_load'))
    pred_cool_f = row.get('pred_cooling_kwh_final') or row.get('pred_cooling_kwh')
    pred_dhw_f = row.get('pred_dhw_kwh_final') or row.get('pred_dhw_kwh')
    pred_batt_f = row.get('pred_battery_kwh_final') or row.get('pred_battery_kwh')
    dhw_before = row.get('dhw_before_safety')
    tmp_before = row.get('tmp_before_safety')
    dhw_after = row.get('dhw_after_safety', dhw_final)
    tmp_after = row.get('tmp_after_safety', tmp_final)
    b_high_param = row.get('B_high')
    b_low_param = row.get('B_low')

    breakdown = ''
    if pred_cool_f not in (None, '') or pred_dhw_f not in (None, '') or pred_batt_f not in (None, ''):
        breakdown = (
            f'设备分解：冷机 {_fmt_num(pred_cool_f)} + DHW {_fmt_num(pred_dhw_f)} + '
            f'电池 {_fmt_num(pred_batt_f)} kWh'
        )
        if solar_next not in (None, ''):
            breakdown += f' − 光伏 {_fmt_num(solar_next)}'

    if not global_refine or row.get('outage_flag'):
        lines.append(
            f'> [安全审查] Refine 已执行={global_refine}，停电={bool(row.get("outage_flag"))}；'
            f'本步未执行社区 Refine，沿用初稿动作。'
        )
        if breakdown:
            lines.append(f'> [安全审查] {breakdown}。')
    elif trigger_reduce:
        tmp_cut = row.get('TMP_max_reduction_percent', 0)
        adj = []
        if dhw_before not in (None, '') and dhw_after not in (None, '') and float(dhw_after) != float(dhw_before):
            adj.append(f'DHW {_fmt_num(dhw_before, 2)}→{_fmt_num(dhw_after, 2)}')
        elif dhw_init not in (None, '') and dhw_final not in (None, '') and float(dhw_final) != float(dhw_init):
            adj.append(f'DHW {_fmt_num(dhw_init, 2)}→{_fmt_num(dhw_final, 2)}')
        if tmp_before not in (None, '') and tmp_after not in (None, '') and float(tmp_after) != float(tmp_before):
            adj.append(f'TMP {_fmt_num(tmp_before, 2)}→{_fmt_num(tmp_after, 2)}（削减 {float(tmp_cut or 0) * 100:.0f}%）')
        elif tmp_init not in (None, '') and tmp_final not in (None, '') and float(tmp_final) != float(tmp_init):
            adj.append(f'TMP {_fmt_num(tmp_init, 2)}→{_fmt_num(tmp_final, 2)}')
        adj_txt = '，'.join(adj) if adj else '尝试削减 DHW/TMP'
        threshold_txt = ''
        if net_mean not in (None, '') and net_std not in (None, '') and b_high_param not in (None, ''):
            threshold_txt = (
                f'，均值：{_fmt_num(net_mean)}，σ：{_fmt_num(net_std)}，'
                f'B_high×σ 上限：{_fmt_num(float(net_mean) + float(b_high_param) * float(net_std))}'
            )
        lines.append(
            f'> [安全审查] 净负荷：{_fmt_num(net_next)} kWh，B_high 警戒线：{_fmt_num(b_high)} kWh'
            f'{threshold_txt}；净负荷超过 B_high；{adj_txt}。'
        )
        if breakdown:
            lines.append(f'> [安全审查] {breakdown} → 净负荷 {_fmt_num(net_next)} kWh。')
    elif trigger_increase:
        threshold_txt = ''
        if net_mean not in (None, '') and net_std not in (None, '') and b_low_param not in (None, ''):
            threshold_txt = (
                f'，均值：{_fmt_num(net_mean)}，σ：{_fmt_num(net_std)}，'
                f'B_low×σ 下限：{_fmt_num(float(net_mean) - float(b_low_param) * float(net_std))}'
            )
        adj = ''
        if dhw_before not in (None, '') and dhw_after not in (None, '') and float(dhw_after) != float(dhw_before):
            adj = f'，DHW {_fmt_num(dhw_before, 2)}→{_fmt_num(dhw_after, 2)}'
        lines.append(
            f'> [安全审查] 净负荷：{_fmt_num(net_next)} kWh，B_low 下限：{_fmt_num(b_low)} kWh'
            f'{threshold_txt}；净负荷低于 B_low；增加 DHW 加热吸收多余电力{adj}。'
        )
        if breakdown:
            lines.append(f'> [安全审查] {breakdown} → 净负荷 {_fmt_num(net_next)} kWh。')
    else:
        threshold_txt = ''
        if net_mean not in (None, '') and net_std not in (None, ''):
            threshold_txt = f'，均值 μ={_fmt_num(net_mean)}，σ={_fmt_num(net_std)}'
        lines.append(
            f'> [安全审查] 净负荷：{_fmt_num(net_next)} kWh，'
            f'B_high：{_fmt_num(b_high)} kWh，B_low：{_fmt_num(b_low)} kWh{threshold_txt}；'
            f'净负荷在阈值带内，未触碰 B_high / B_low。'
        )
        if breakdown:
            lines.append(f'> [安全审查] {breakdown} → 净负荷 {_fmt_num(net_next)} kWh。')
        if dhw_before not in (None, '') and dhw_after not in (None, '') and float(dhw_after) == float(dhw_before):
            if tmp_before not in (None, '') and tmp_after not in (None, '') and float(tmp_after) == float(tmp_before):
                lines.append(
                    f'> [安全审查] DHW 动作：{_fmt_num(dhw_after, 2)}，TMP 动作：{_fmt_num(tmp_after, 2)}；'
                    f'未因 B_high/B_low 调整。'
                )
    # --- ResMARL 残差层（仅 enabled 时写入剧本；关闭时不出现）---
    lines.extend(_build_resmarl_narrative_lines(row, electricity_pricing))

    # --- 三行动作对照：CHESCA 基准 / MARL 残差 / 合成终稿 ---
    lines.extend(_build_action_compare_lines(row))

    tmp_changed = (
        tmp_init not in (None, '') and tmp_final not in (None, '')
        and abs(float(tmp_final) - float(tmp_init)) > 1e-6
    )
    aux_triggered = trigger_reduce and tmp_changed
    final_actions = (
        f'DHW {_fmt_num(dhw_final, 2)} / ELE {_fmt_num(ele_final, 2)} / TMP {_fmt_num(tmp_final, 2)}'
    )
    if mode == 'outage':
        exec_txt = f'{final_actions}；停电模式执行'
    elif aux_triggered:
        exec_txt = f'{final_actions}；TMP 削减已触发 (AUX)'
    elif global_refine and not row.get('outage_flag'):
        exec_txt = f'{final_actions}；TMP 削减 (AUX) 未触发，安全放行'
    else:
        exec_txt = f'{final_actions}；TMP 削减 (AUX) 未触发，安全放行'
    lines.append(f'> 最终执行：{exec_txt}')

    return lines


def _action_triplet_text(dhw, ele, tmp, digits: int = 3) -> str:
    """格式：DHW: x  ELE: y  TMP: z"""
    return (
        f'DHW: {_fmt_num(dhw, digits)}  '
        f'ELE: {_fmt_num(ele, digits)}  '
        f'TMP: {_fmt_num(tmp, digits)}'
    )


def _build_action_compare_lines(row: Dict[str, Any]) -> List[str]:
    """
    推演日志固定三行动作对照：

      [CHESCA动作]           ← a_base（阶段1～4 / Refine 后基准）
      [MARL动作]             ← 策略原始 Δa（未×α、未 mask）
      [CHESCA-RESMARL动作]   ← a_final（环境实际执行）
    """
    dhw_final = row.get('action_dhw_final')
    ele_final = row.get('action_ele_final')
    tmp_final = row.get('action_tmp_final')

    chesca_dhw = row.get('residual_base_dhw', dhw_final)
    chesca_ele = row.get('residual_base_ele', ele_final)
    chesca_tmp = row.get('residual_base_tmp', tmp_final)

    enabled = row.get('resmarl_enabled')
    resmarl_on = enabled not in (None, '', False, 0, '0', 'false', 'False')

    if resmarl_on:
        # 优先原始 Δa；旧 trace 无 raw 字段时回退到 scaled delta
        marl_dhw = row.get('residual_raw_delta_dhw', row.get('residual_delta_dhw', 0.0))
        marl_ele = row.get('residual_raw_delta_ele', row.get('residual_delta_ele', 0.0))
        marl_tmp = row.get('residual_raw_delta_tmp', row.get('residual_delta_tmp', 0.0))
        final_dhw = row.get('residual_final_dhw', dhw_final)
        final_ele = row.get('residual_final_ele', ele_final)
        final_tmp = row.get('residual_final_tmp', tmp_final)
    else:
        marl_dhw = marl_ele = marl_tmp = 0.0
        final_dhw, final_ele, final_tmp = dhw_final, ele_final, tmp_final

    return [
        f'> [CHESCA动作] {_action_triplet_text(chesca_dhw, chesca_ele, chesca_tmp)}',
        f'> [MARL动作] {_action_triplet_text(marl_dhw, marl_ele, marl_tmp)}',
        f'> [CHESCA-RESMARL动作] {_action_triplet_text(final_dhw, final_ele, final_tmp)}',
    ]


def _build_resmarl_narrative_lines(
    row: Dict[str, Any],
    electricity_pricing: Optional[float] = None,
) -> List[str]:
    """
    生成 [MARL层]/[残差生成] 剧本行。

    仅当 resmarl_enabled=True 时返回非空列表；关闭时不写入剧本（便于消融对照）。
    """
    enabled = row.get('resmarl_enabled')
    if enabled in (None, '', False, 0, '0', 'false', 'False'):
        return []

    lines: List[str] = []
    pricing = electricity_pricing if electricity_pricing is not None else row.get('electricity_pricing')
    alpha = row.get('residual_alpha', 0.0)
    skip = row.get('residual_skip_reason', '')
    mask = row.get('residual_action_mask') or {}
    if isinstance(mask, str):
        try:
            import json as _json
            mask = _json.loads(mask)
        except Exception:
            mask = {}

    obs_parts = []
    if pricing not in (None, ''):
        try:
            obs_parts.append(f'当前电价 {_fmt_num(float(pricing), 3)} $/kWh')
        except (TypeError, ValueError):
            pass
    if row.get('battery_soc') not in (None, ''):
        obs_parts.append(f'电池 SOC {_fmt_num(row.get("battery_soc"), 2)}')
    if row.get('net_load_next') not in (None, ''):
        obs_parts.append(f'审查后净负荷 {_fmt_num(row.get("net_load_next"))} kWh')
    mode_a = row.get('resmarl_after_safety', True)
    mode_txt = '模式 A（安全审查之后）' if mode_a not in (False, 0, '0', 'false') else '模式 B（配置为审查之前；当前实现仍按模式 A 执行）'
    obs_txt = '，'.join(obs_parts) if obs_parts else '观测上下文已就绪'
    lines.append(
        f'> [MARL层介入] α={_fmt_num(alpha, 2)}，{mode_txt}，{obs_txt}；ResMARL 启用。'
    )

    mask_on = [k.upper() for k in ('ele', 'tmp', 'dhw') if mask.get(k)]
    mask_txt = '/'.join(mask_on) if mask_on else '无'
    delta_dhw = row.get('residual_delta_dhw', 0.0)
    delta_ele = row.get('residual_delta_ele', 0.0)
    delta_tmp = row.get('residual_delta_tmp', 0.0)
    raw_dhw = row.get('residual_raw_delta_dhw', delta_dhw)
    raw_ele = row.get('residual_raw_delta_ele', delta_ele)
    raw_tmp = row.get('residual_raw_delta_tmp', delta_tmp)
    base_ele = row.get('residual_base_ele', row.get('action_ele_final'))
    final_ele = row.get('residual_final_ele', row.get('action_ele_final'))

    if skip in ('alpha_zero',):
        lines.append(
            f'> [残差生成] α=0，mask=[{mask_txt}]，'
            f'原始 Δa DHW/ELE/TMP={_fmt_num(raw_dhw, 3)}/'
            f'{_fmt_num(raw_ele, 3)}/{_fmt_num(raw_tmp, 3)}；'
            f'残差恒等，不改变基准动作。'
        )
    else:
        parts = []
        try:
            if abs(float(delta_ele or 0)) > 1e-9:
                direction = '追加放电' if float(delta_ele) < 0 else '追加充电'
                parts.append(
                    f'对电池{direction}残差 {_fmt_num(delta_ele, 3)}'
                    f'（ELE {_fmt_num(base_ele, 2)}→{_fmt_num(final_ele, 2)}）'
                )
            if abs(float(delta_tmp or 0)) > 1e-9:
                parts.append(f'对冷机残差 {_fmt_num(delta_tmp, 3)}')
            if abs(float(delta_dhw or 0)) > 1e-9:
                parts.append(f'对 DHW 残差 {_fmt_num(delta_dhw, 3)}')
        except (TypeError, ValueError):
            parts = []
        if parts:
            lines.append(
                f'> [残差生成] 原始 Δa DHW/ELE/TMP='
                f'{_fmt_num(raw_dhw, 3)}/{_fmt_num(raw_ele, 3)}/{_fmt_num(raw_tmp, 3)}，'
                f'mask=[{mask_txt}]；MARL {"，".join(parts)}。'
            )
        else:
            lines.append(
                f'> [残差生成] 原始 Δa DHW/ELE/TMP='
                f'{_fmt_num(raw_dhw, 3)}/{_fmt_num(raw_ele, 3)}/{_fmt_num(raw_tmp, 3)}，'
                f'mask=[{mask_txt}]；策略输出为零或尚无 checkpoint，终稿等于基准动作。'
            )

    return lines


def _build_step_phases(step_rows: List[Dict[str, Any]], global_refine: bool) -> List[Dict[str, Any]]:
    """为单步生成推演阶段摘要（1–5 CHESCA；启用 ResMARL 时追加阶段 6）。"""
    if not step_rows:
        return []
    sample = step_rows[0]
    buildings = step_rows

    phase1 = (
        f"室外温度实际 {_fmt_num(sample.get('actual_outdoor_temp'), 1)}°C"
        f"，上步预测 {_fmt_num(sample.get('forecast_outdoor_temp'), 1)}°C"
        f"，下步预测 {_fmt_num(sample.get('forecast_outdoor_next'), 1)}°C"
    )
    if sample.get('abs_pct_error_outdoor_temp') not in (None, ''):
        phase1 += f"（误差 {_fmt_num(float(sample.get('abs_pct_error_outdoor_temp', 0)) * 100, 1)}%）"

    init_lines = []
    for r in buildings:
        b = int(r.get('building', 0))
        init_lines.append(
            f"建筑{b + 1}[{r.get('control_mode', 'normal')}] "
            f"DHW {_fmt_num(r.get('action_dhw_init'), 2)} "
            f"ELE {_fmt_num(r.get('action_ele_init'), 2)} "
            f"TMP {_fmt_num(r.get('action_tmp_init'), 2)}"
        )
    phase2 = '；'.join(init_lines)

    phase3 = f"滚动预测 tau={sample.get('tau', 1)} 步冷机/DHW 用电，供电池树搜索使用"

    if not global_refine:
        phase4 = '首步无历史净负荷，跳过社区级电池树搜索'
    else:
        refine_lines = []
        for r in buildings:
            b = int(r.get('building', 0))
            if r.get('outage_flag'):
                refine_lines.append(f"建筑{b + 1} 停电跳过")
                continue
            flags = []
            if r.get('trigger_reduce_load'):
                flags.append('B_high 减负荷')
            if r.get('trigger_increase_load'):
                flags.append('B_low 增负荷')
            flag_txt = '、'.join(flags) if flags else '未触发阈值'
            # Refine 后 ELE 对应 residual_base_ele（若有），否则用终稿近似
            ele_after = r.get('residual_base_ele', r.get('action_ele_final'))
            refine_lines.append(
                f"建筑{b + 1} ELE {_fmt_num(r.get('action_ele_init'), 2)}→"
                f"{_fmt_num(ele_after, 2)}（{flag_txt}）"
            )
        phase4 = '；'.join(refine_lines)

    phase5 = '根据终稿动作更新净用电预测历史，供下一步 Refine 使用'

    phases = [
        {'phase': 1, 'name': PHASE_NAMES[1], 'summary': phase1},
        {'phase': 2, 'name': PHASE_NAMES[2], 'summary': phase2},
        {'phase': 3, 'name': PHASE_NAMES[3], 'summary': phase3},
        {'phase': 4, 'name': PHASE_NAMES[4], 'summary': phase4},
        {'phase': 5, 'name': PHASE_NAMES[5], 'summary': phase5},
    ]

    if sample.get('resmarl_enabled'):
        alpha = sample.get('residual_alpha', 0.0)
        marl_lines = []
        for r in buildings:
            b = int(r.get('building', 0))
            if r.get('residual_applied'):
                marl_lines.append(
                    f"建筑{b + 1} ELE {_fmt_num(r.get('residual_base_ele'), 2)}"
                    f"+Δ{_fmt_num(r.get('residual_delta_ele'), 3)}"
                    f"→{_fmt_num(r.get('residual_final_ele'), 2)}"
                )
            else:
                marl_lines.append(
                    f"建筑{b + 1} 跳过({r.get('residual_skip_reason', '')})"
                )
        phases.append({
            'phase': 6,
            'name': PHASE_NAMES[6],
            'summary': f"α={_fmt_num(alpha, 2)}；" + '；'.join(marl_lines),
        })

    return phases


class ChescaTraceRecorder:
    """在 episode 内逐步收集 Decision Trace。"""

    def __init__(self, n_buildings: int):
        self.n_buildings = n_buildings
        self.rows: List[Dict[str, Any]] = []
        self.episode = 0
        self._step = -1
        self._prev_forecasts: Optional[Dict[str, Any]] = None

    def begin_episode(self) -> None:
        self.episode += 1
        self._step = -1
        self._prev_forecasts = None

    def record_step(
        self,
        agent,
        observations: List[float],
        hour: int,
        initial_actions: List[float],
        final_actions: List[float],
        refine_applied: bool,
        refine_meta: Dict[int, Dict[str, Any]],
        initial_meta: Optional[Dict[int, Dict[str, Any]]] = None,
        electricity_pricing: Optional[float] = None,
    ) -> None:
        self._step += 1
        obs_names = agent.observation_names_b
        prev = self._prev_forecasts
        initial_meta = initial_meta or {}

        actual_outdoor = observations[obs_names.index('outdoor_dry_bulb_temperature')]
        forecast_outdoor = prev['outdoor_temp'][0] if prev else None
        forecast_outdoor_next = agent.forecasts['outdoor_temp'][0]

        step_rows: List[Dict[str, Any]] = []

        for b in range(self.n_buildings):
            outage_flag = observations[obs_names.index(f'power_outage_{b}')] == 1
            meta = refine_meta.get(b, {})
            init_meta = initial_meta.get(b, {})
            building_refine = refine_applied and not outage_flag
            control_mode = init_meta.get('control_mode') or ('outage' if outage_flag else 'normal')

            if not refine_applied:
                refine_skip_reason = 'first_step'
            elif outage_flag:
                refine_skip_reason = 'outage'
            elif building_refine:
                refine_skip_reason = 'none'
            else:
                refine_skip_reason = 'skipped'

            actual_solar = observations[obs_names.index(f'solar_generation_{b}')]
            actual_load = observations[obs_names.index(f'non_shiftable_load_{b}')]
            actual_dhw = observations[obs_names.index(f'dhw_demand_{b}')]

            forecast_solar = prev[b]['solar_generation'][0] if prev else None
            forecast_load = prev[b]['non_shiftable_load'][0] if prev else None
            forecast_dhw = prev[b]['dhw_demand'][0] if prev else None

            forecast_solar_next = agent.forecasts[b]['solar_generation'][0]
            forecast_load_next = agent.forecasts[b]['non_shiftable_load'][0]
            forecast_dhw_next = agent.forecasts[b]['dhw_demand'][0]

            row = {
                'episode': self.episode,
                'step': self._step,
                'hour': hour,
                'building': b,
                'outage_flag': outage_flag,
                'control_mode': control_mode,
                'refine_skip_reason': refine_skip_reason,
                'actual_outdoor_temp': actual_outdoor,
                'forecast_outdoor_temp': forecast_outdoor,
                'forecast_outdoor_next': forecast_outdoor_next,
                'abs_pct_error_outdoor_temp': _abs_pct_error(actual_outdoor, forecast_outdoor),
                'actual_solar': actual_solar,
                'forecast_solar': forecast_solar,
                'forecast_solar_next': forecast_solar_next,
                'abs_pct_error_solar': _abs_pct_error(actual_solar, forecast_solar),
                'actual_load': actual_load,
                'forecast_load': forecast_load,
                'forecast_load_next': forecast_load_next,
                'abs_pct_error_load': _abs_pct_error(actual_load, forecast_load),
                'actual_dhw': actual_dhw,
                'forecast_dhw': forecast_dhw,
                'forecast_dhw_next': forecast_dhw_next,
                'abs_pct_error_dhw': _abs_pct_error(actual_dhw, forecast_dhw),
                'battery_soc': agent.cur_battery_soc[b],
                'dhw_soc': agent.cur_dhw_soc[b],
                'action_dhw_init': initial_actions[3 * b],
                'action_ele_init': initial_actions[3 * b + 1],
                'action_tmp_init': initial_actions[3 * b + 2],
                'action_dhw_final': final_actions[3 * b],
                'action_ele_final': final_actions[3 * b + 1],
                'action_tmp_final': final_actions[3 * b + 2],
                'refine_applied': building_refine,
                'trigger_reduce_load': meta.get('trigger_reduce_load', False),
                'trigger_increase_load': meta.get('trigger_increase_load', False),
                'net_load_next': meta.get('net_load_next', ''),
                'net_load_mean': meta.get('net_load_mean', ''),
                'net_load_std': meta.get('net_load_std', ''),
                'battery_search_cost': meta.get('battery_search_cost', ''),
                'balance_type': agent.params.get('balance_type', ''),
                'tau': agent.params.get('tau', ''),
                'B_low': agent.params.get('B_low', ''),
                'B_high': agent.params.get('B_high', ''),
                'TMP_max_reduction_percent': agent.params.get('TMP_max_reduction_percent', ''),
            }
            for k, v in init_meta.items():
                if k not in row:
                    row[k] = v
            for k, v in meta.items():
                if k not in row:
                    row[k] = v
            if electricity_pricing is not None:
                row['electricity_pricing'] = electricity_pricing

            # ResMARL 残差埋点（整步共享，按建筑切分 delta）
            residual_meta = getattr(agent, '_trace_residual_meta', {}) or {}
            residual_cfg = getattr(agent, 'residual_config', None)
            row['resmarl_enabled'] = bool(getattr(residual_cfg, 'enabled', False)) if residual_cfg else False
            row['residual_alpha'] = float(getattr(residual_cfg, 'alpha', 0.0)) if residual_cfg else 0.0
            row['residual_action_mask'] = dict(getattr(residual_cfg, 'action_mask', {})) if residual_cfg else {}
            row['resmarl_after_safety'] = bool(getattr(residual_cfg, 'after_safety', True)) if residual_cfg else True
            row['residual_applied'] = bool(residual_meta.get('applied', False))
            row['residual_skip_reason'] = residual_meta.get('skip_reason', 'disabled')
            delta_vec = residual_meta.get('delta') or []
            raw_delta_vec = residual_meta.get('raw_delta') or []
            base_vec = residual_meta.get('a_base') or []
            final_vec = residual_meta.get('a_final') or []

            def _vec_at(vec, offset):
                idx = 3 * b + offset
                return float(vec[idx]) if idx < len(vec) else 0.0

            row['residual_delta_dhw'] = _vec_at(delta_vec, 0)
            row['residual_delta_ele'] = _vec_at(delta_vec, 1)
            row['residual_delta_tmp'] = _vec_at(delta_vec, 2)
            row['residual_raw_delta_dhw'] = _vec_at(raw_delta_vec, 0)
            row['residual_raw_delta_ele'] = _vec_at(raw_delta_vec, 1)
            row['residual_raw_delta_tmp'] = _vec_at(raw_delta_vec, 2)
            if base_vec:
                row['residual_base_dhw'] = _vec_at(base_vec, 0)
                row['residual_base_ele'] = _vec_at(base_vec, 1)
                row['residual_base_tmp'] = _vec_at(base_vec, 2)
            if final_vec:
                row['residual_final_dhw'] = _vec_at(final_vec, 0)
                row['residual_final_ele'] = _vec_at(final_vec, 1)
                row['residual_final_tmp'] = _vec_at(final_vec, 2)

            step_rows.append(row)

        community_actual_net = 0.0
        community_pred_net = 0.0
        for b in range(self.n_buildings):
            obs_net = float(observations[obs_names.index(f'net_electricity_consumption_{b}')])
            community_actual_net += float(building_net_electricity_consumption(
                agent.env, b, default=obs_net
            ))
            community_pred_net += float(
                agent.forecasts[b]['non_shiftable_load'][0]
                + agent.predicted_cooling_demand[b]
                + agent.predicted_dhw_device_demand[b]
                + agent.predicted_battery_demand[b]
                - agent.forecasts[b]['solar_generation'][0]
            )

        for row in step_rows:
            row['community_actual_net_load'] = community_actual_net
            row['community_pred_net_next'] = community_pred_net
            narrative_lines = _build_decision_narrative_lines(row, refine_applied, electricity_pricing)
            # 瘦身：只存剧本行与 tag，不嵌入 code_snippet（前端本地补全）
            narrative_entries = build_narrative_entries(narrative_lines, include_snippet=False)
            row['decision_narrative'] = '|||'.join(narrative_lines)
            row['decision_narrative_tags'] = '|||'.join(e['code_tag'] for e in narrative_entries)
            row['decision_narrative_entries'] = narrative_entries
            row['decision_summary'] = _build_decision_summary(row, refine_applied)
            self.rows.append(row)

        self._prev_forecasts = {
            'outdoor_temp': list(agent.forecasts['outdoor_temp']),
            **{
                b: {
                    'solar_generation': list(agent.forecasts[b]['solar_generation']),
                    'non_shiftable_load': list(agent.forecasts[b]['non_shiftable_load']),
                    'dhw_demand': list(agent.forecasts[b]['dhw_demand']),
                }
                for b in range(self.n_buildings)
            },
        }

    def backfill_hot_discomfort_from_env(self, env) -> Dict[str, Any]:
        """
        Episode 结束后，用与 env.evaluate() 相同的建筑温度序列回填高温不适判定。

        解决：决策时 WrapperEnv 无 buildings / 观测室温贴设定点，导致剧本全「否」，
        但 KPI discomfort_hot_proportion 仍约 95%+ 的口径不一致。
        """
        from checa.utils import compute_hot_discomfort_from_values, resolve_citylearn_env

        real_env = resolve_citylearn_env(env)
        if real_env is None or not getattr(real_env, 'buildings', None):
            return {'updated': 0, 'hot': 0, 'total': 0, 'error': 'no_buildings'}

        series_by_b = []
        for building in real_env.buildings:
            indoor = np.asarray(building.indoor_dry_bulb_temperature, dtype=float)
            cool = np.asarray(building.indoor_dry_bulb_temperature_cooling_set_point, dtype=float)
            band = np.asarray(building.comfort_band, dtype=float)
            occ = np.asarray(building.occupant_count, dtype=float)
            series_by_b.append({
                'indoor': indoor,
                'cool': cool,
                'band': band,
                'occ': occ,
                'n': int(min(len(indoor), len(cool))),
            })

        updated = 0
        hot = 0
        total = 0
        for row in self.rows:
            try:
                b = int(row.get('building', 0))
                step = int(row.get('step', -1))
            except (TypeError, ValueError):
                continue
            if b < 0 or b >= len(series_by_b) or step < 0:
                continue
            ser = series_by_b[b]
            if step >= ser['n']:
                continue

            indoor = float(ser['indoor'][step])
            cool_sp = float(ser['cool'][step])
            band = float(ser['band'][step]) if step < len(ser['band']) else 2.0
            occ = float(ser['occ'][step]) if step < len(ser['occ']) else 1.0
            indoor_obs = row.get('kpi_indoor_temp_obs', row.get('indoor_temp'))

            note = (
                f'已按 evaluate 温度序列回填：step={step}，'
                f'动力学室内={indoor:.2f}°C，制冷设定={cool_sp:.2f}°C'
            )
            if indoor_obs not in (None, ''):
                try:
                    obs_v = float(indoor_obs)
                    if abs(obs_v - indoor) > 0.05:
                        note += f'；决策时观测室内曾为 {obs_v:.2f}°C'
                except (TypeError, ValueError):
                    pass

            kpi = compute_hot_discomfort_from_values(
                indoor,
                cool_sp,
                band=band,
                occupant=occ,
                indoor_obs=indoor_obs,
                indoor_source='evaluate.indoor[step]',
                setpoint_source='evaluate.cooling_set_point[step]',
                dynamics_note=note,
            )
            row.update(kpi)
            total += 1
            updated += 1
            if kpi.get('kpi_is_hot_discomfort'):
                hot += 1

            # 重建剧本行（使 [高温不适判定] 与回填后的 kpi_* 一致）
            refine_applied = bool(row.get('refine_applied'))
            narrative_lines = _build_decision_narrative_lines(
                row, refine_applied, row.get('electricity_pricing')
            )
            narrative_entries = build_narrative_entries(narrative_lines, include_snippet=False)
            row['decision_narrative'] = '|||'.join(narrative_lines)
            row['decision_narrative_tags'] = '|||'.join(e['code_tag'] for e in narrative_entries)
            row['decision_narrative_entries'] = narrative_entries

        return {
            'updated': updated,
            'hot': hot,
            'total': total,
            'hot_rate': (hot / total) if total else 0.0,
        }

    def build_decision_trace_steps(self) -> List[Dict[str, Any]]:
        """将 flat rows 聚合为按步决策推演结构。"""
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in self.rows:
            key = f"{row.get('episode')}-{row.get('step')}"
            grouped.setdefault(key, []).append(row)

        steps: List[Dict[str, Any]] = []
        for key in sorted(grouped.keys(), key=lambda k: (int(k.split('-')[0]), int(k.split('-')[1]))):
            step_rows = sorted(grouped[key], key=lambda r: r.get('building', 0))
            sample = step_rows[0]
            global_refine = sample.get('refine_skip_reason') != 'first_step'
            steps.append(_json_safe_dict({
                'episode': sample.get('episode'),
                'step': sample.get('step'),
                'hour': sample.get('hour'),
                'refine_applied': global_refine,
                'refine_skip_reason': sample.get('refine_skip_reason') if not global_refine else 'none',
                'tau': sample.get('tau'),
                'balance_type': sample.get('balance_type'),
                'B_low': sample.get('B_low'),
                'B_high': sample.get('B_high'),
                'phases': _build_step_phases(step_rows, global_refine),
                'buildings': [
                    _json_safe_dict({
                        'building': r.get('building'),
                        'control_mode': r.get('control_mode'),
                        'outage_flag': r.get('outage_flag'),
                        'decision_summary': r.get('decision_summary'),
                        # 瘦身：只导出剧本行；悬停源码由前端 CODE_REF_META 按行文案补全
                        'narrative_lines': (
                            [ln for ln in str(r.get('decision_narrative', '')).split('|||') if ln]
                            if r.get('decision_narrative')
                            else [e.get('text', '') for e in _narrative_entries_from_row(r, global_refine)]
                        ),
                        'battery_soc': r.get('battery_soc'),
                        'dhw_soc': r.get('dhw_soc'),
                        'actions': {
                            'init': {
                                'dhw': r.get('action_dhw_init'),
                                'ele': r.get('action_ele_init'),
                                'tmp': r.get('action_tmp_init'),
                            },
                            'final': {
                                'dhw': r.get('action_dhw_final'),
                                'ele': r.get('action_ele_final'),
                                'tmp': r.get('action_tmp_final'),
                            },
                        },
                        'forecast': {
                            'load_next': r.get('forecast_load_next'),
                            'solar_next': r.get('forecast_solar_next'),
                            'dhw_next': r.get('forecast_dhw_next'),
                        },
                        'refine': {
                            'applied': r.get('refine_applied'),
                            'skip_reason': r.get('refine_skip_reason'),
                            'trigger_reduce': r.get('trigger_reduce_load'),
                            'trigger_increase': r.get('trigger_increase_load'),
                            'net_load_next': r.get('net_load_next'),
                            'net_load_mean': r.get('net_load_mean'),
                            'net_load_std': r.get('net_load_std'),
                            'battery_search_cost': r.get('battery_search_cost'),
                        },
                        'residual': {
                            'enabled': r.get('resmarl_enabled'),
                            'alpha': r.get('residual_alpha'),
                            'applied': r.get('residual_applied'),
                            'skip_reason': r.get('residual_skip_reason'),
                            'action_mask': r.get('residual_action_mask'),
                            'after_safety': r.get('resmarl_after_safety'),
                            'base': {
                                'dhw': r.get('residual_base_dhw'),
                                'ele': r.get('residual_base_ele'),
                                'tmp': r.get('residual_base_tmp'),
                            },
                            'delta': {
                                'dhw': r.get('residual_delta_dhw'),
                                'ele': r.get('residual_delta_ele'),
                                'tmp': r.get('residual_delta_tmp'),
                            },
                            'raw_delta': {
                                'dhw': r.get('residual_raw_delta_dhw'),
                                'ele': r.get('residual_raw_delta_ele'),
                                'tmp': r.get('residual_raw_delta_tmp'),
                            },
                            'final': {
                                'dhw': r.get('residual_final_dhw'),
                                'ele': r.get('residual_final_ele'),
                                'tmp': r.get('residual_final_tmp'),
                            },
                        },
                    })
                    for r in step_rows
                ],
            }))
        return steps


def _narrative_entries_from_row(row: Dict[str, Any], global_refine: bool) -> List[Dict[str, Any]]:
    stored = row.get('decision_narrative_entries')
    if stored:
        # 兼容旧内存数据：去掉可能存在的 code_snippet，避免再次写入胖 JSON
        slim: List[Dict[str, Any]] = []
        for e in stored:
            if not isinstance(e, dict):
                continue
            item = {k: v for k, v in e.items() if k != 'code_snippet'}
            slim.append(_json_safe_dict(item))
        return slim
    if row.get('decision_narrative'):
        lines = [ln for ln in str(row.get('decision_narrative', '')).split('|||') if ln]
    else:
        lines = _build_decision_narrative_lines(row, global_refine, row.get('electricity_pricing'))
    return [_json_safe_dict(e) for e in build_narrative_entries(lines, include_snippet=False)]


def _json_safe(value: Any) -> Any:
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.floating, float)):
        v = float(value)
        return None if np.isnan(v) else v
    if isinstance(value, (np.integer, int)):
        return int(value)
    return value


def _json_safe_dict(obj: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        if isinstance(v, dict):
            out[k] = _json_safe_dict(v)
        elif isinstance(v, list):
            out[k] = [_json_safe_dict(i) if isinstance(i, dict) else _json_safe(i) for i in v]
        else:
            out[k] = _json_safe(v)
    return out


def save_chesca_trace(recorder: ChescaTraceRecorder, file_path: Path) -> Path:
    """将 trace 宽表写入 CSV。"""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=TRACE_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        for row in recorder.rows:
            writer.writerow({col: _fmt(row.get(col, '')) for col in TRACE_COLUMNS})

    return file_path


def save_decision_trace_json(recorder: ChescaTraceRecorder, file_path: Path) -> Path:
    """
    将决策推演日志写入 JSON（瘦身版）。

    version=2：不嵌入每步 code_snippet / narrative_entries；
    使用紧凑 separators，避免 indent 膨胀。悬停源码由前端本地补全。
    """
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'version': 2,
        'n_buildings': recorder.n_buildings,
        'slim': True,
        'steps': recorder.build_decision_trace_steps(),
    }
    file_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
        encoding='utf-8',
    )
    return file_path
