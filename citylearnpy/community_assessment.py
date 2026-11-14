"""Full-episode, immutable-package preliminary CityLearn diagnostics."""
import argparse
import csv
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback

for _thread_variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_thread_variable] = '1'

C_REF = 0.796605975703795
D_REF = 0.04916529553031551
SCORE_SOURCE = Path(__file__).with_name('CHESCA-local综合评分诊断方案-20261104.md')
KNOWN_ACTIONS = {'cooling_storage', 'heating_storage', 'dhw_storage', 'electrical_storage', 'cooling_device', 'heating_device', 'cooling_or_heating_device'}


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def relative_change(reference, candidate):
    reference, candidate = finite(reference), finite(candidate)
    return None if reference is None or candidate is None or reference == 0 else (candidate - reference) / abs(reference)


def summarize_metrics(rows, building_names, undefined_metrics=None):
    undefined_metrics = undefined_metrics or {}
    def metric(level, name, key):
        if name + '.' + key in undefined_metrics:
            return None
        matches = [row for row in rows if row.get('level') == level and row.get('name') == name and row.get('cost_function') == key]
        return finite(matches[0].get('value')) if len(matches) == 1 else None
    cost = metric('district', 'District', 'cost_total')
    discomfort = metric('district', 'District', 'discomfort_proportion')
    buildings = []
    for name in building_names:
        c = metric('building', name, 'cost_total')
        d = metric('building', name, 'discomfort_proportion')
        status = 'missing metrics' if c is None or d is None else 'passed' if c < .90 and d < .10 else 'failed'
        buildings.append({'name': name, 'cost_total': c, 'discomfort_proportion': d,
                          'costMargin': None if c is None else .90-c, 'discomfortMargin': None if d is None else .10-d,
                          'constraintStatus': status})
    feasible = None if not buildings or any(b['constraintStatus'] == 'missing metrics' for b in buildings) else all(b['constraintStatus'] == 'passed' for b in buildings)
    return {'cost_total': cost, 'discomfort_proportion': discomfort,
            'score': None if cost is None or discomfort is None else .5*cost/C_REF + .5*discomfort/D_REF,
            'feasible': feasible, 'buildings': buildings, 'undefinedMetrics': undefined_metrics,
            'officialRows': [{key: finite(value) if key == 'value' else value for key, value in row.items()} for row in rows]}


def write_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    # Windows readers can briefly hold the old progress file without delete sharing.
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.025*(attempt+1))


def score_definition():
    return {'formula': 'J = 0.5*C/C_ref + 0.5*D/D_ref', 'lowerIsBetter': True,
            'costMetric': 'official district cost_total', 'discomfortMetric': 'official district discomfort_proportion',
            'C_ref': C_REF, 'D_ref': D_REF, 'strictPerBuildingConstraints': {'cost_total': '< 0.90', 'discomfort_proportion': '< 0.10'},
            'selectionOrder': 'All building constraints first, then minimum J among feasible candidates',
            'source': SCORE_SOURCE.name, 'sourceDate': '2026-11-04',
            'sourceSha256': hashlib.sha256(SCORE_SOURCE.read_bytes()).hexdigest() if SCORE_SOURCE.exists() else None,
            'warning': '固定历史 CHESCA local 参照尺度；不是当前社区基线、通用标准或理论最优，不能跨场景直接解释为改善比例。',
            'rewardIsScore': False, 'missingMetricPolicy': 'Missing/nonfinite official metrics stay null; no fabricated zeros or feasibility.',
            'zeroReferencePolicy': 'Relative changes are null when their reference is zero; fixed score denominators are positive.'}


class DiagnosticPolicy:
    """Small declared online rules using only current building sensor values."""
    def __init__(self, env, cooling_margin):
        self.env = env
        self.cooling_margin = cooling_margin
        self.price_history = [[] for _ in env.buildings]

    def predict(self, observations, deterministic=True):
        import numpy as np
        building_actions = []
        for index, building in enumerate(self.env.buildings):
            current = building.observations(include_all=True)
            price = finite(current.get('electricity_pricing'))
            history = self.price_history[index]
            if price is not None:
                history.append(price)
            low = float(np.quantile(history, .25)) if history else None
            high = float(np.quantile(history, .75)) if history else None
            temperature = finite(current.get('indoor_dry_bulb_temperature'))
            cooling_setpoint = finite(current.get('indoor_dry_bulb_temperature_cooling_set_point'))
            heating_setpoint = finite(current.get('indoor_dry_bulb_temperature_heating_set_point'))
            values = []
            for action in building.active_actions:
                if action.endswith('_storage'):
                    soc = finite(current.get(action + '_soc'))
                    value = .08 if low is not None and high > low and price <= low and soc is not None and soc < .8 else -.08 if high is not None and high > low and price >= high and soc is not None and soc > .2 else 0.0
                else:
                    value = 0.0
                    if action == 'cooling_device' and temperature is not None and cooling_setpoint is not None:
                        value = max(0.0, min(1.0, .45 + .25*(temperature-cooling_setpoint+self.cooling_margin)))
                    elif action == 'heating_device' and temperature is not None and heating_setpoint is not None:
                        value = max(0.0, min(1.0, .45 + .25*(heating_setpoint-temperature+self.cooling_margin)))
                    elif action == 'cooling_or_heating_device' and temperature is not None:
                        if cooling_setpoint is not None and temperature > cooling_setpoint:
                            value = -.6
                        elif heating_setpoint is not None and temperature < heating_setpoint:
                            value = .6
                values.append(value)
            building_actions.append(np.clip(np.asarray(values), building.action_space.low, building.action_space.high).tolist())
        return [[value for row in building_actions for value in row]] if self.env.central_agent else building_actions


def dataset_currency(directory):
    manifest = Path(directory) / 'manifest.json'
    try:
        value = json.loads(manifest.read_text(encoding='utf-8'))
        currency = value.get('building', {}).get('currency')
        return str(currency).strip() if currency and str(currency).strip() else '未知币种'
    except (OSError, ValueError, AttributeError):
        return '未知币种'


def optimization_opportunities(buildings, currency='未知币种'):
    """Summarize level-one NoControl screens; never present exposure as savings."""
    import numpy as np

    def trace(building, key):
        try:
            value = building
            for part in key.split('.'):
                value = getattr(value, part)
            values = np.asarray(value, dtype=float).ravel()
            return values if values.size and np.isfinite(values).all() else None
        except (AttributeError, TypeError, ValueError):
            return None

    rows = []
    unknown = '该轨迹字段缺失或无效，当前不能筛查。'
    caveat = '静态筛查信号，不是可实现节省额；不能直接当作可节省金额。'
    for building in buildings:
        name = building.name
        prices = trace(building, 'pricing.electricity_pricing')
        net = trace(building, 'net_electricity_consumption')
        outage = trace(building, 'power_outage_signal')
        battery = getattr(building, 'electrical_storage', None)
        capacity = finite(getattr(battery, 'capacity', None))
        power = finite(getattr(battery, 'nominal_power', None))
        eta = finite(getattr(battery, 'round_trip_efficiency', None))
        count, max_margin = None, None
        if prices is not None and net is not None:
            n = min(prices.size, net.size)
            usable = np.ones(n, dtype=bool)
            if outage is not None:
                usable &= outage[:n] < .5
            future_max = -np.inf
            candidate_margins = []
            for index in range(n - 1, -1, -1):
                if usable[index] and future_max > -np.inf and eta is not None:
                    margin = eta * future_max - prices[index]
                    if margin > 1e-9:
                        candidate_margins.append(float(margin))
                if usable[index] and net[index] > 0:
                    future_max = max(future_max, prices[index])
            count = len(candidate_margins)
            max_margin = max(candidate_margins) if candidate_margins else 0.0
        if capacity is None or power is None or capacity <= 0 or power <= 0:
            battery_status = '未配置有效电池'
            battery_evidence = f'电池容量 {capacity or 0:g} kWh，额定功率 {power or 0:g} kW。'
        elif count is None:
            battery_status, battery_evidence = '暂不可筛查', unknown
        elif count:
            battery_status = '发现有序价差候选'
            battery_evidence = f'容量 {capacity:g} kWh、功率 {power:g} kW；{count} 个“先低价充、后高价且有购电需求”的价差候选，最大单位毛收益约 {max_margin:.4g} {currency}/kWh。'
        else:
            battery_status = '本时段未发现正价差候选'
            battery_evidence = f'容量 {capacity:g} kWh、功率 {power:g} kW；按当前价序和参考净购电，未发现正单位毛收益候选。'
        rows.append({'building': name, 'category': '电池移峰', 'status': battery_status,
                     'evidence': battery_evidence, 'nextStep': '固定非电池负荷，按参考初末 SOC、功率/容量/效率及停电分段求解电池约束模型；计入 PV 外送机会成本并核验参考轨迹可嵌入后，再报告模型机会。',
                     'caveat': caveat, 'candidateChargeSteps': count, 'maxUnitMargin': max_margin})

        occupancy = trace(building, 'occupant_count')
        temperature = trace(building, 'indoor_dry_bulb_temperature')
        cooling_setpoint = trace(building, 'indoor_dry_bulb_temperature_cooling_set_point')
        heating_setpoint = trace(building, 'indoor_dry_bulb_temperature_heating_set_point')
        cooling_use = trace(building, 'cooling_electricity_consumption')
        heating_use = trace(building, 'heating_electricity_consumption')
        thermal_fields = (occupancy, temperature, cooling_setpoint, heating_setpoint, cooling_use, heating_use, prices)
        if any(value is None for value in thermal_fields):
            thermal_evidence = unknown
            thermal_status = '冷热筛查数据不足'
            unoccupied_steps = overcool_steps = high_price_exposure = None
        else:
            n = min(value.size for value in thermal_fields)
            high_price = prices[:n] >= np.quantile(prices[:n], .75)
            unoccupied = occupancy[:n] <= 0
            cooling_on = cooling_use[:n] > 1e-9
            overcool = (temperature[:n] < cooling_setpoint[:n]) & (occupancy[:n] > 0) & cooling_on
            high_price_exposure = float(np.sum(np.maximum(cooling_use[:n] + heating_use[:n], 0)[high_price] * prices[:n][high_price])) if np.all(prices[:n] >= 0) else None
            unoccupied_steps = int(np.sum(unoccupied & cooling_on))
            overcool_steps = int(np.sum(overcool))
            thermal_status = '发现静态候选' if unoccupied_steps or overcool_steps or high_price_exposure else '本时段未发现明显静态候选'
            thermal_evidence = f'无人时仍制冷 {unoccupied_steps} 步；有人时制冷且室温低于制冷设定点 {overcool_steps} 步；高价时段冷热设备电耗费用暴露 {high_price_exposure:.4g} {currency}。' if high_price_exposure is not None else f'无人时仍制冷 {unoccupied_steps} 步；有人时制冷且室温低于制冷设定点 {overcool_steps} 步；负电价存在，简化费用暴露不适用。'
        rows.append({'building': name, 'category': '冷热负荷', 'status': thermal_status, 'evidence': thermal_evidence,
                     'nextStep': '对预先选定的代表事件尝试减一档/延迟一步，恢复参考控制并覆盖后续恢复期；记录不适、欠供和末端温度。',
                     'caveat': caveat, 'unoccupiedCoolingSteps': unoccupied_steps, 'occupiedOvercoolSteps': overcool_steps,
                     'highPriceExposure': high_price_exposure})

        dhw_use = trace(building, 'dhw_electricity_consumption')
        if dhw_use is None or prices is None:
            dhw_status, dhw_evidence, dhw_exposure = '热水筛查数据不足', unknown, None
        elif float(getattr(getattr(building, 'dhw_device', None), 'nominal_power', 0) or 0) <= 0:
            dhw_status, dhw_evidence, dhw_exposure = '未配置有效热水设备', '热水设备额定功率为 0。', None
        else:
            n = min(dhw_use.size, prices.size)
            high_price = prices[:n] >= np.quantile(prices[:n], .75)
            dhw_exposure = float(np.sum(np.maximum(dhw_use[:n], 0)[high_price] * prices[:n][high_price])) if np.all(prices[:n] >= 0) else None
            dhw_status = '发现高价时段用电' if np.any(high_price & (dhw_use[:n] > 1e-9)) else '本时段未发现明显静态候选'
            dhw_evidence = f'高价时段热水设备耗电费用暴露 {dhw_exposure:.4g} {currency}。' if dhw_exposure is not None else '存在负电价，简化费用暴露不适用。'
        rows.append({'building': name, 'category': '热水负荷', 'status': dhw_status, 'evidence': dhw_evidence,
                     'nextStep': '结合热水需求、SOC、待机损失及欠供，验证提前/延迟充热；保留服务量和末端库存检查。',
                     'caveat': caveat, 'highPriceExposure': dhw_exposure})

    rows.append({'building': '社区', 'category': '联合调度', 'status': '待完整环境回放',
                 'evidence': '当前 NoControl 只建立参考，不足以识别电池、冷热和热水之间的交互收益。',
                 'nextStep': '在同一时段、初始状态和信息预算下完成 NoControl、仅电池、仅冷热/热水、联合控制四臂回放，再计算交互收益。',
                 'caveat': '单项筛查值不可相加成社区总优化空间。'})
    return rows


def diagnostics(env, declared_buildings, official_rows, currency='未知币种'):
    import numpy as np
    def series(value):
        array = np.asarray(value, dtype=float)
        return array if array.size and np.isfinite(array).all() else None
    net = series(env.net_electricity_consumption)
    buildings = []
    for index, building in enumerate(env.buildings):
        terminal = {}
        # Building SOC histories include the post-action terminal value. Do not read
        # ideal-load sensor CSV placeholders as realized storage state.
        for name in ('electrical_storage', 'cooling_storage', 'heating_storage', 'dhw_storage'):
            if declared_buildings[index].get(name) is None:
                continue
            storage = getattr(building, name, None)
            soc = series(getattr(storage, 'soc', [])) if storage is not None else None
            terminal[name] = None if soc is None else float(soc[-1])
        costs = series(getattr(building, 'net_electricity_consumption_cost', []))
        emissions = series(getattr(building, 'net_electricity_consumption_emission', []))
        buildings.append({'name': building.name, 'terminalSOC': terminal,
                          'positiveCost': None if costs is None else finite(np.maximum(costs, 0).sum()),
                          'carbonEmissions': None if emissions is None else finite(np.maximum(emissions, 0).sum()),
                          'netCost': None if costs is None else finite(costs.sum())})
    def district_total(key):
        values = [building[key] for building in buildings]
        return finite(math.fsum(values)) if values and all(value is not None for value in values) else None
    keys = {'discomfort_cold_proportion', 'discomfort_hot_proportion', 'power_outage_normalized_unserved_energy_total', 'annual_normalized_unserved_energy_total', 'one_minus_thermal_resilience_proportion'}
    official_diagnostics = [{**row, 'value': finite(row.get('value'))} for row in official_rows if row.get('cost_function') in keys]
    return {'districtPeakElectricity': None if net is None else float(net.max()),
            'districtAbsoluteRamping': None if net is None else float(np.abs(np.diff(net)).sum()),
            'buildings': buildings,
            'district': {key: district_total(key) for key in ('positiveCost', 'carbonEmissions')},
            'units': {'positiveCost': currency, 'carbonEmissions': 'kgCO2'},
            'optimizationOpportunities': optimization_opportunities(env.buildings, currency),
            'officialComfortAndOutage': official_diagnostics,
            'note': 'Peak/ramping are realized raw electricity diagnostics, not extra score terms; terminal SOC may explain finite-horizon gains.'}


def score_window_metrics(buildings, rows, start_step, end_step_exclusive):
    """Replace the score KPIs with CityLearn-equivalent values over source steps [start, end)."""
    import numpy as np
    from citylearn.cost_function import CostFunction

    start, end = int(start_step), int(end_step_exclusive)
    if start < 0 or end <= start:
        raise ValueError('Invalid score window')
    output = [dict(row) for row in rows]
    building_values = {}
    for building in buildings:
        suffix = '_without_storage_and_partial_load' if hasattr(building, 'net_electricity_consumption_cost_without_storage_and_partial_load') else '_without_storage'
        control = np.asarray(building.net_electricity_consumption_cost, dtype=float)[start:end]
        baseline = np.asarray(getattr(building, 'net_electricity_consumption_cost' + suffix), dtype=float)[start:end]
        if control.size != end-start or baseline.size != end-start:
            raise ValueError('Score window exceeds simulated cost history')
        control_cost = float(CostFunction.cost(control)[-1])
        baseline_cost = float(CostFunction.cost(baseline)[-1])
        cost_ratio = None if baseline_cost == 0 or not math.isfinite(baseline_cost) else control_cost / baseline_cost
        occupied = np.asarray(building.occupant_count, dtype=float)[start:end]
        temperatures = np.asarray(building.indoor_dry_bulb_temperature, dtype=float)[start:end]
        cooling = np.asarray(building.indoor_dry_bulb_temperature_cooling_set_point, dtype=float)[start:end]
        heating = np.asarray(building.indoor_dry_bulb_temperature_heating_set_point, dtype=float)[start:end]
        band = building.comfort_band
        if not np.isscalar(band):
            band = np.asarray(band, dtype=float)[start:end]
        if any(values.size != end-start for values in (occupied, temperatures, cooling, heating)):
            raise ValueError('Score window exceeds simulated comfort history')
        discomfort = float(CostFunction.discomfort(temperatures, cooling, heating, band=band, occupant_count=occupied)[0][-1])
        building_values[building.name] = {'cost_total': cost_ratio, 'discomfort_proportion': discomfort}
    for row in output:
        metric = row.get('cost_function')
        name = row.get('name')
        if metric not in ('cost_total', 'discomfort_proportion'):
            continue
        if row.get('level') == 'building' and name in building_values:
            row['value'] = building_values[name][metric]
            row['evaluationScope'] = 'score_window'
        elif row.get('level') == 'district':
            values = [value[metric] for value in building_values.values()]
            row['value'] = None if not values or any(value is None or not math.isfinite(value) for value in values) else float(np.mean(values))
            row['evaluationScope'] = 'score_window'
    return output


def undefined_metrics(env, score_window=None):
    """Do not interpret a runtime's 0/0 -> 1 convention as a defined cost ratio."""
    import numpy as np
    from citylearn.building import DynamicsBuilding
    undefined = {}
    for building in env.buildings:
        suffix = '_without_storage_and_partial_load' if isinstance(building, DynamicsBuilding) else '_without_storage'
        reference = np.asarray(getattr(building, 'net_electricity_consumption_cost' + suffix), dtype=float)
        occupied = np.asarray(building.occupant_count, dtype=float)
        if score_window is not None:
            start, end = score_window
            reference = reference[start:end]
            occupied = occupied[start:end]
        denominator = float(np.maximum(reference, 0).sum())
        if not np.isfinite(reference).all() or not math.isfinite(denominator) or denominator == 0:
            reason = 'zero or nonfinite official no-control cost denominator; raw official convention retained in officialRows'
            undefined[building.name + '.cost_total'] = reason
            undefined['District.cost_total'] = reason
        if not np.isfinite(occupied).all() or not np.any(occupied > 0):
            reason = 'no occupied samples or nonfinite occupancy; discomfort ratio is not diagnostically defined'
            undefined[building.name + '.discomfort_proportion'] = reason
            undefined['District.discomfort_proportion'] = reason
    return undefined


HOME_TRACE_COLUMNS = (
    'episode', 'step', 'hour', 'building', 'actual_outdoor_temp',
    'actual_solar', 'actual_load', 'actual_dhw', 'action_dhw_final',
    'action_ele_final', 'action_tmp_final', 'score_eligible',
    'action_applied', 'control_mode',
)


def write_home_trace_csv(rows, path, source_start_step=0, score_window=None):
    """Write only the time-series and final actions needed by the homepage."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=HOME_TRACE_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            output = {key: row.get(key) for key in HOME_TRACE_COLUMNS}
            output['step'] = int(source_start_step) + int(row.get('step', 0))
            score_eligible = score_window is None or score_window[0] <= output['step'] < score_window[1]
            output['score_eligible'] = str(score_eligible).lower()
            output['action_applied'] = str(score_window is None or score_eligible).lower()
            output['control_mode'] = 'policy' if score_window is None or score_eligible else 'common_baseline_warmup'
            writer.writerow(output)
    return path


def _observations_only(value):
    return value[0] if isinstance(value, tuple) else value


def _score_state_hash(env, observations):
    import numpy as np
    sensors = []
    for building in env.buildings:
        values = building.observations(include_all=True)
        sensors.append({
            'name': building.name,
            'indoorTemperature': finite(values.get('indoor_dry_bulb_temperature')),
            'storageSoc': {name: finite(values.get(name + '_soc')) for name in
                           ('cooling_storage', 'heating_storage', 'dhw_storage', 'electrical_storage')},
        })
    state = {'timeStep': int(env.time_step),
             'observations': np.asarray(observations, dtype=float).tolist(),
             'buildings': sensors}
    return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def run_case(schema, case, progress, output_directory=None, score_window=None, task_output=None):
    from citylearn.citylearn import CityLearnEnv
    from citylearn.agents.base import BaselineAgent
    from citylearn.agents.rbc import BasicRBC
    import numpy as np
    env = CityLearnEnv(copy.deepcopy(schema))
    from evaluation_contract import capture_context, finalize_evaluation, protocol_id
    task_context = capture_context(env, information_access='no_control_no_policy_observations'
                                   if case['id'] == 'no_control' else 'current_observations_and_declared_forecasts',
                                   warmup='shared_baseline_prefix' if score_window else 'none') if task_output else None
    from assessment_trace import AssessmentTrace
    trace = AssessmentTrace(env, schema, case) if output_directory is not None else None
    started = time.monotonic()
    try:
        original_actions = [list(building.active_actions) for building in env.buildings]
        actions = {name for names in original_actions for name in names}
        if case['id'] != 'no_control' and not actions:
            return {**case, 'status': 'skipped', 'reason': '所选场景没有启用可控动作。'}
        if case['id'] == 'basic_rbc' and any('hour' not in names for names in env.observation_names):
            return {**case, 'status': 'skipped', 'reason': 'BasicRBC 需要每个控制器观测中存在 hour。'}
        if case['id'] != 'no_control' and not actions.issubset(KNOWN_ACTIONS):
            return {**case, 'status': 'skipped', 'reason': '当前诊断策略不支持动作: ' + ', '.join(sorted(actions-KNOWN_ACTIONS))}
        simulation_start = int(schema['simulation_start_time_step'])
        score_start = score_window[0] if score_window else simulation_start
        warmup_steps = score_start - simulation_start
        warmup_observations = []
        score_state_sha256 = None
        if case['id'] == 'no_control':
            policy = BaselineAgent(env)
            policy_class = 'citylearn.agents.base.BaselineAgent'
            observations = _observations_only(env.reset())
        else:
            if warmup_steps > 0:
                reference_policy = BaselineAgent(env)
                observations = _observations_only(env.reset())
                progress(case['id'], 0, warmup_steps, '执行统一 NoControl 预热')
                for step in range(warmup_steps):
                    warmup_observations.append(copy.deepcopy(observations))
                    before = trace.before() if trace else None
                    warmup_action = reference_policy.predict(observations, deterministic=True)
                    transition = env.step(warmup_action)
                    if trace:
                        trace.record(before, warmup_action, transition, 'common_baseline_warmup')
                    observations, reward = transition[0], transition[1]
                    if not all(np.isfinite(np.asarray(row)).all() for row in observations) or not np.isfinite(np.asarray(reward)).all():
                        raise ValueError('Reference warmup returned nonfinite observations or rewards')
                    if transition[2] or (len(transition) >= 5 and transition[3]):
                        raise ValueError('Reference warmup ended before the score window')
                score_state_sha256 = _score_state_hash(env, observations)
                for building, active_names in zip(env.buildings, original_actions):
                    for name in building.action_metadata:
                        building.action_metadata[name] = name in active_names
                    building.action_space = building.estimate_action_space()
                    building.observation_space = building.estimate_observation_space()
            else:
                observations = _observations_only(env.reset())
                score_state_sha256 = _score_state_hash(env, observations) if score_window else None
        if case['id'] == 'no_control':
            policy_class = 'citylearn.agents.base.BaselineAgent'
        elif case['id'] == 'chesca':
            sys.path.insert(0, str(Path(__file__).resolve().parent / 'CHESCA-copy'))
            from agents.user_agent import SubmissionAgent
            from utils.ches_env import WrapperEnv
            from checa.trace_exporter import ChescaTraceRecorder, save_chesca_trace
            policy = SubmissionAgent(WrapperEnv(env), params=case.get('parameters', {}))
            if case.get('parameters', {}).get('frozen_gate'):
                from utils.ches_frozen_gate import attach_frozen_gate
                attach_frozen_gate(policy, env)
            policy.trace_recorder = ChescaTraceRecorder(len(env.buildings))
            policy.trace_recorder.begin_episode()
            policy_class = 'CHESCA.SubmissionAgent'
        elif case['id'] == 'basic_rbc':
            policy = BasicRBC(env)
            policy_class = 'citylearn.agents.rbc.BasicRBC'
        else:
            policy = DiagnosticPolicy(env, case['coolingMargin'])
            policy_class = __name__ + '.DiagnosticPolicy'
            for building in env.buildings:
                current = building.observations(include_all=True)
                needed = []
                for action in building.active_actions:
                    if action == 'cooling_device':
                        needed.extend(['indoor_dry_bulb_temperature', 'indoor_dry_bulb_temperature_cooling_set_point'])
                    elif action == 'heating_device':
                        needed.extend(['indoor_dry_bulb_temperature', 'indoor_dry_bulb_temperature_heating_set_point'])
                    elif action == 'cooling_or_heating_device':
                        needed.extend(['indoor_dry_bulb_temperature', 'indoor_dry_bulb_temperature_cooling_set_point', 'indoor_dry_bulb_temperature_heating_set_point'])
                if any(finite(current.get(name)) is None for name in needed):
                    return {**case, 'status': 'skipped', 'reason': 'HVAC 反馈规则所需当前温度或设定值不可用。'}
        if case['id'] != 'no_control' and warmup_observations:
            if hasattr(policy, 'reset'):
                policy.reset()
            for historical_observation in warmup_observations:
                policy.predict(historical_observation, deterministic=True)
            if case['id'] == 'chesca':
                # Replay initializes the policy only; those predictions were never executed.
                policy.trace_recorder = ChescaTraceRecorder(len(env.buildings))
                policy.trace_recorder.begin_episode()
        expected_steps = int(schema['simulation_end_time_step'])-int(schema['simulation_start_time_step'])
        steps = warmup_steps if case['id'] != 'no_control' else 0
        if score_window and warmup_steps == 0:
            score_state_sha256 = _score_state_hash(env, observations)
        while True:
            before = trace.before() if trace else None
            action = policy.predict(observations, deterministic=True)
            transition = env.step(action)
            if trace:
                trace.record(before, action, transition, 'no_control' if case['id'] == 'no_control' else 'policy')
            observations, reward = transition[:2]
            if not all(np.isfinite(np.asarray(row)).all() for row in observations) or not np.isfinite(np.asarray(reward)).all():
                raise ValueError('Runtime returned nonfinite observations or rewards')
            steps += 1
            if case['id'] == 'no_control' and score_window and steps == warmup_steps:
                score_state_sha256 = _score_state_hash(env, observations)
            if steps % 48 == 0 or steps == expected_steps:
                progress(case['id'], steps, expected_steps, '正在执行完整回合')
            if transition[2] or (len(transition) >= 5 and transition[3]):
                break
            if steps > expected_steps:
                raise ValueError('Runtime exceeded requested immutable source bounds')
        if steps != expected_steps:
            raise ValueError('Episode terminated before full source bounds: ' + str(steps) + '/' + str(expected_steps))
        rows = env.evaluate().to_dict('records')
        if score_window is not None:
            rows = score_window_metrics(env.buildings, rows, *score_window)
        if case['id'] == 'chesca' and output_directory is not None:
            output_directory = Path(output_directory)
            output_directory.mkdir(parents=True, exist_ok=True)
            for row in policy.trace_recorder.rows:
                row['step'] += simulation_start + warmup_steps
            save_chesca_trace(policy.trace_recorder, output_directory / 'chesca_trace.csv')
            write_home_trace_csv(
                policy.trace_recorder.rows,
                output_directory / 'home_trace.csv',
                0,
                score_window,
            )
        if trace:
            case_directory = Path(output_directory) / 'cases' / case['id']
            detailed = policy.trace_recorder.build_decision_trace_steps() if case['id'] == 'chesca' else None
            trace.save(case_directory, detailed)
            if case['id'] == 'chesca':
                save_chesca_trace(policy.trace_recorder, case_directory / 'chesca_trace.csv')
            if task_output:
                trace.save(Path(task_output), detailed)
                if case['id'] == 'chesca':
                    save_chesca_trace(policy.trace_recorder, Path(task_output) / 'chesca_trace.csv')
                parameters = case.get('parameters', {})
                finalize_evaluation(env, task_context, task_output,
                                    'NOCONTROL' if case['id'] == 'no_control' else 'CHESCA',
                                    resolved_parameters=parameters, policy_id=protocol_id(parameters))
        declared_buildings = [definition for definition in schema['buildings'].values() if definition.get('include', True)]
        return {**case, 'status': 'succeeded', 'policyClass': policy_class, 'steps': steps,
                'seconds': time.monotonic()-started, 'originalActions': original_actions,
                'effectiveActions': [list(building.active_actions) for building in env.buildings],
                'metrics': summarize_metrics(rows, [building.name for building in env.buildings], undefined_metrics(env, score_window)),
                'diagnostics': diagnostics(env, declared_buildings, rows, dataset_currency(schema.get('root_directory', '.'))),
                'evaluation': {'simulationStartStep': int(schema['simulation_start_time_step']),
                               'simulationEndStepExclusive': int(schema['simulation_end_time_step']) + 1,
                               'scoreStartStep': score_window[0] if score_window else int(schema['simulation_start_time_step']),
                               'scoreEndStepExclusive': score_window[1] if score_window else int(schema['simulation_end_time_step']) + 1,
                               'scoreWindowOnlyFor': ['cost_total', 'discomfort_proportion'] if score_window else 'full_episode',
                               'otherOfficialKpisScope': 'full_episode',
                               'warmupPolicy': 'CityLearn BaselineAgent' if warmup_steps else 'none',
                               'scoreStartStateSha256': score_state_sha256}}
    finally:
        env.close()


def optimization_recommendations(baseline, cases):
    notes = []
    metrics = baseline.get('metrics', {})
    for building in metrics.get('buildings', []):
        name = building['name']
        cost, discomfort = finite(building.get('cost_total')), finite(building.get('discomfort_proportion'))
        if cost is None or discomfort is None:
            notes.append(name + ' 的逐栋约束不可判定；先核对费用参考分母、占用人数和缺失指标，再比较策略。')
            continue
        if cost >= .9:
            notes.append(name + ' 的 NoControl 成本比为 ' + format(cost, '.4f') + '；达到 C<0.90 至少还需降低 ' + format((cost-.9)/abs(cost)*100, '.1f') + '% 并严格越过边界。先核对分时电价、可移负荷与储能容量，这只是约束差距，不是已证明的节能潜力。')
        if discomfort >= .1:
            notes.append(name + ' 的 NoControl 不适比例为 ' + format(discomfort*100, '.1f') + '%，超过 10% 边界；优先核查占用时段、温度设定值和热动态模型，再调 HVAC 控制。')
    baseline_devices = {item['name']: item.get('terminalSOC', {}) for item in baseline.get('diagnostics', {}).get('buildings', [])}
    for case in cases:
        if case.get('status') != 'succeeded':
            continue
        current = case.get('metrics', {})
        cost = relative_change(metrics.get('cost_total'), current.get('cost_total'))
        discomfort = relative_change(metrics.get('discomfort_proportion'), current.get('discomfort_proportion'))
        parts = []
        for label, delta in [('成本比', cost), ('不适比例', discomfort)]:
            if delta is not None:
                parts.append(label + ('降低' if delta < 0 else '上升' if delta > 0 else '变化') + format(abs(delta)*100, '.1f') + '%')
        if parts:
            notes.append('“' + case['label'] + '”相对 NoControl：' + '，'.join(parts) + '。' + ('存在成本与舒适权衡，应先满足逐栋约束再调整策略。' if cost is not None and discomfort is not None and cost*discomfort < 0 else '该结果仅代表本时段已测规则，不外推为理论优化空间。'))
        for building in case.get('diagnostics', {}).get('buildings', []):
            reference = baseline_devices.get(building['name'], {})
            for device, value in building.get('terminalSOC', {}).items():
                before, after = finite(reference.get(device)), finite(value)
                if before is not None and after is not None and after < before-.05:
                    notes.append('“' + case['label'] + '”的 ' + building['name'] + '/' + device + ' 末端 SOC 比 NoControl 低 ' + format((before-after)*100, '.1f') + ' 个百分点；需统一末端电量或做连续多回合复核，避免将放空储能计为持续收益。')
        outages = case.get('diagnostics', {}).get('officialComfortAndOutage', [])
        if any(row.get('cost_function') == 'power_outage_normalized_unserved_energy_total' and (finite(row.get('value')) or 0) > 0 for row in outages):
            notes.append('“' + case['label'] + '”存在官方停电未供能记录；需要单独检查备用电量和关键负荷保障，不能仅按 J 选策略。')
    return notes


def render_report(result):
    definition = result['scoreDefinition']
    lines = ['# 社区初步评估报告', '', '状态：' + result['status'], '',
             '数据源：`' + result['source']['schema'] + '`', '',
             '全部候选执行完整仿真上下文；计分起点前共享同一条 BaselineAgent 参考预热轨迹，候选策略按因果顺序接收预热观测。成本比值与舒适度按登记的计分窗口计算，其余官方 KPI 与诊断仍是全回合口径。NoControl 使用安装版本的 BaselineAgent，禁用控制动作并按源理想负荷运行 HVAC。', '',
             '计分窗口：源 step [' + str(result['source'].get('scoreStartStep')) + ', ' + str(result['source'].get('scoreEndStepExclusive')) + ')；结束不含。', '',
             '## 评分口径', '', definition['formula'] + '，越低越好。', '',
             '固定 C_ref=' + str(C_REF) + '，D_ref=' + str(D_REF) + '。先检查每栋 C<0.90 且 D<0.10，等于边界也不合格，再比较可行候选 J。', '',
             '来源：' + definition['source'] + '。' + definition['warning'], '',
             '| 方案 | 状态 | C | D | J | 逐栋约束 |', '| --- | --- | ---: | ---: | ---: | --- |']
    def number(value):
        return '不可用' if value is None else format(value, '.9g')
    for case in [result.get('baseline')] + result.get('cases', []):
        if not case:
            continue
        metric = case.get('metrics', {})
        lines.append('| ' + case['label'] + ' | ' + case['status'] + ' | ' + ' | '.join(number(metric.get(key)) for key in ('cost_total', 'discomfort_proportion', 'score')) + ' | ' + {True: '通过', False: '未通过', None: '不可判定'}[metric.get('feasible')] + ' |')
        if case.get('reason') or case.get('error'):
            lines += ['', case['label'] + '：' + case.get('reason', case.get('error', '')), '']
    for case in [result.get('baseline')] + result.get('cases', []):
        if not case or case.get('status') != 'succeeded':
            continue
        lines += ['', '## ' + case['label'], '', '实际执行 ' + str(case['steps']) + ' 次转换。', '', '| 建筑 | C | D | 成本余量 | 不适余量 | 约束 |', '| --- | ---: | ---: | ---: | ---: | --- |']
        for building in case['metrics']['buildings']:
            lines.append('| ' + building['name'] + ' | ' + ' | '.join(number(building.get(key)) for key in ('cost_total', 'discomfort_proportion', 'costMargin', 'discomfortMargin')) + ' | ' + building['constraintStatus'] + ' |')
        lines += ['', '峰值、爬坡、费用与末端 SOC：', '', '```json', json.dumps(case['diagnostics'], ensure_ascii=False, indent=2), '```']
        if case['metrics'].get('undefinedMetrics'):
            lines += ['', '指标不可判定原因：', '', '```json', json.dumps(case['metrics']['undefinedMetrics'], ensure_ascii=False, indent=2), '```']
    lines += ['', '## 初步建议', ''] + ['- ' + value for value in result.get('recommendations', [])]
    lines += ['', '## 限制', ''] + ['- ' + value for value in result['limitations']]
    if result.get('error'):
        lines += ['', '## 失败原因', '', '```text', result['error'], '```']
    return '\n'.join(lines) + '\n'


def run_assessment(schema_path, output_directory, algorithm=None, parameters=None, start_step=None, end_step=None,
                   score_start_step=None, score_end_step_exclusive=None, task_output=None):
    import torch
    torch.set_num_threads(1)
    if parameters and parameters.get('frozen_gate'):
        import random
        import numpy as np
        seed = int(parameters.get('frozen_gate_seed', 0))
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
    if parameters is not None:
        if parameters.get('dhw_storage_fix'):
            os.environ['CITYLEARN_DHW_STORAGE_FIX'] = '1'
        else:
            os.environ.pop('CITYLEARN_DHW_STORAGE_FIX', None)
    schema_path = Path(schema_path).resolve(strict=True)
    # Published packages can contain the platform's approved device adapters.
    if str(schema_path.parent) not in sys.path:
        sys.path.insert(0, str(schema_path.parent))
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw = json.loads(schema_path.read_text(encoding='utf-8'))
    package_manifest_path = schema_path.parent / 'manifest.json'
    package_manifest = json.loads(package_manifest_path.read_text(encoding='utf-8')) if package_manifest_path.is_file() else {}
    if package_manifest.get('sourceMode') == 'synthetic_ol1':
        declared_start = int(package_manifest['scoreStartStep'])
        declared_end = int(package_manifest['scoreEndStepExclusive'])
        if score_start_step is not None and int(score_start_step) != declared_start:
            raise ValueError('Score start does not match the immutable generated scenario manifest')
        if score_end_step_exclusive is not None and int(score_end_step_exclusive) != declared_end:
            raise ValueError('Score end does not match the immutable generated scenario manifest')
        score_start_step, score_end_step_exclusive = declared_start, declared_end
    schema = copy.deepcopy(raw)
    schema['root_directory'] = str(schema_path.parent)
    if start_step is not None:
        if start_step < int(schema.get('simulation_start_time_step', 0)):
            raise ValueError('Start outside source bounds')
        schema['simulation_start_time_step'] = start_step
    if end_step is not None:
        if end_step > int(schema['simulation_end_time_step']):
            raise ValueError('End outside source bounds')
        schema['simulation_end_time_step'] = end_step
    start = int(schema.get('simulation_start_time_step', 0))
    end = int(schema['simulation_end_time_step'])
    if end <= start:
        raise ValueError('Source needs at least two time points')
    schema['episode_time_steps'] = end-start+1
    score_window = None
    if score_start_step is not None or score_end_step_exclusive is not None:
        score_start = start if score_start_step is None else int(score_start_step)
        score_end = end + 1 if score_end_step_exclusive is None else int(score_end_step_exclusive)
        if score_start < start or score_end > end + 1 or score_end <= score_start:
            raise ValueError('Score window must be a non-empty half-open interval within the simulated source bounds')
        if score_start == start and score_end == end + 1:
            score_window = None
        else:
            score_window = (score_start, score_end)
    schema['rolling_episode_split'] = False
    schema['random_episode_split'] = False
    currency = dataset_currency(schema_path.parent)
    result = {'status': 'running', 'source': {'schema': str(schema_path), 'currency': currency, 'schemaSha256': hashlib.sha256(schema_path.read_bytes()).hexdigest(),
               'simulationStart': start, 'simulationEnd': end, 'timeSteps': end-start+1, 'seed': raw.get('random_seed'),
               'scoreStartStep': score_window[0] if score_window else start,
               'scoreEndStepExclusive': score_window[1] if score_window else end+1,
               'scorePolicy': 'Full context is retained; all candidates share a BaselineAgent prefix and candidate policies are initialized from its past observations. Only cost_total and discomfort_proportion use the half-open score window.' if score_window else 'Full episode is simulated and scored.',
               'originalEpisodeConfiguration': {key: raw.get(key) for key in ('episode_time_steps', 'rolling_episode_split', 'random_episode_split')},
               'evaluationEpisodeOverride': 'One complete episode spanning declared simulation bounds; training splits disabled only in memory.',
               'stepCountDefinition': 'timeSteps counts inclusive source state points; case.steps counts env.step action transitions (timeSteps - 1).'},
              'baseline': None, 'cases': [], 'scoreDefinition': score_definition(), 'recommendations': [],
              'limitations': ['这是有限、预先声明的确定性策略诊断，不含 SAC 训练、未来信息或理论最优证明。',
                              '固定历史 local 评分分母用于本报告尺度，不能当成通用最优标准；任务 reward 与评分 J 不同。',
                              '官方缺失或非有限 KPI 保留 null；零成本参考下不能将归一化结果解释为节省比例。',
                              '末端 SOC 降低可能解释有限回合收益，本报告不将其认定为长期改进。']}
    result['limitations'].append('温差规则读取模拟器当前传感器值（包括源配置中未激活的观测），未认证挑战赛 observations-only 接口合规性；不读取未来序列。')
    if raw.get('random_seed') is None:
        result['limitations'].append('源场景未指定 random_seed；保留原值，随机停电等跨策略比较可能不可重复。')
    cases = [{'id': 'no_control', 'label': 'NoControl（真实 BaselineAgent）'},
             {'id': 'basic_rbc', 'label': '内置 BasicRBC 时段规则'},
             {'id': 'feedback_balanced', 'label': '当前温差与历史电价储能规则', 'coolingMargin': 0.0,
              'description': 'HVAC action clip(0.45 + 0.25*current temperature error,0,1); storage +/-0.08 at observed-price quartiles with SOC bounds0.2/0.8; ties hold. No future prices.'},
             {'id': 'feedback_comfort', 'label': '偏舒适温差与历史电价储能规则', 'coolingMargin': .5,
              'description': 'Same rule with +0.5C comfort margin; combined HVAC uses +/-0.6 beyond current setpoints. No future prices.'}]
    def progress(case_id, completed, total, message):
        write_json(output / 'progress.json', {'stage': case_id, 'completed': completed, 'total': total, 'message': message,
                                              'caseId': case_id, 'caseIndex': next((i for i, c in enumerate(cases, 1) if c['id'] == case_id), 0), 'caseCount': len(cases)})
    try:
        if algorithm == 'NOCONTROL':
            cases = [cases[0]]
        elif algorithm == 'CHESCA':
            cases = [cases[0], {'id': 'chesca', 'label': 'CHESCA', 'parameters': parameters or {}}]
        for case in cases:
            progress(case['id'], 0, end-start, '开始评估完整源时段')
            try:
                selected_task_output = task_output if ((algorithm == 'NOCONTROL' and case['id'] == 'no_control')
                                                       or (algorithm == 'CHESCA' and case['id'] == 'chesca')) else None
                if algorithm == 'NOCONTROL':
                    case['parameters'] = parameters or {}
                completed = run_case(schema, case, progress, output, score_window, selected_task_output)
            except Exception:
                completed = {**case, 'status': 'failed', 'error': traceback.format_exc()}
                if case['id'] == 'no_control':
                    result['baseline'] = completed
                    raise RuntimeError('Mandatory NoControl evaluation failed: ' + completed['error'])
            if case['id'] == 'no_control':
                result['baseline'] = completed
            else:
                result['cases'].append(completed)
            write_json(output / 'result.json', result)
        if algorithm == 'CHESCA' and any(c.get('status') != 'succeeded' for c in result['cases']):
            raise RuntimeError('CHESCA evaluation failed; see case error')
        candidates = [case for case in result['cases'] if case.get('status') == 'succeeded' and case['metrics']['feasible'] is True and case['metrics']['score'] is not None]
        best = min(candidates, key=lambda case: case['metrics']['score']) if candidates else None
        result['bestFeasibleCase'] = None if best is None else best['id']
        if best:
            result['recommendations'].append('本次已测可行候选中 J 最低的是“' + best['label'] + '”；仅支持该候选集合与当前数据时段。')
        else:
            result['recommendations'].append('本次候选没有获得满足全部逐栋约束且指标完整的方案；保留原场景，先检查逐栋成本/舒适瓶颈。')
        result['recommendations'].extend(optimization_recommendations(result['baseline'], result['cases']))
        for case in result['cases']:
            if case.get('status') == 'succeeded':
                case['relativeToNoControl'] = {key: relative_change(result['baseline']['metrics'].get(key), case['metrics'].get(key)) for key in ('cost_total', 'discomfort_proportion', 'score')}
        result['recommendations'].append('进一步控制前先核对峰值、爬坡、停电未供能和末端 SOC；简单规则收益不代表跨楼协同或强化学习必然有效。')
        result['status'] = 'succeeded'
    except Exception:
        result['status'] = 'failed'
        result['error'] = traceback.format_exc()
    finally:
        write_json(output / 'result.json', result)
        (output / 'report.md').write_text(render_report(result), encoding='utf-8')
        progress(result['status'], len(cases) if result['status'] == 'succeeded' else 0, len(cases), '初步评估完成' if result['status'] == 'succeeded' else '评估失败，未生成成功结论')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--algorithm', choices=['CHESCA'])
    parser.add_argument('--parameters', default='{}')
    parser.add_argument('--parameters-base64')
    parser.add_argument('--start-step', type=int)
    parser.add_argument('--end-step', type=int)
    parser.add_argument('--score-start-step', type=int)
    parser.add_argument('--score-end-step-exclusive', type=int)
    arguments = parser.parse_args()
    encoded = json.loads(__import__('base64').b64decode(arguments.parameters_base64).decode('utf-8')) if arguments.parameters_base64 else json.loads(arguments.parameters)
    result = run_assessment(arguments.schema, arguments.output_dir, arguments.algorithm, encoded, arguments.start_step, arguments.end_step,
                            arguments.score_start_step, arguments.score_end_step_exclusive)
    print(json.dumps({'status': result['status'], 'outputDirectory': str(Path(arguments.output_dir).resolve())}, ensure_ascii=True))
    return 0 if result['status'] == 'succeeded' else 1


if __name__ == '__main__':
    sys.exit(main())
