"""Read-only transition recording shared by community assessment policies."""
import csv
import json
import ast
import inspect
import textwrap
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np


def clean(value):
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (bool, str)) or value is None:
        return value
    return str(value)


def transition_timing(env_or_class):
    """Identify the installed executable step order; version strings are insufficient."""
    method = env_or_class.step
    tree = ast.parse(textwrap.dedent(inspect.getsource(inspect.unwrap(method))))
    calls = [(node.lineno, node.func.attr) for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr in ('next_time_step', 'apply_actions')]
    advance = [line for line, name in calls if name == 'next_time_step']
    apply = [line for line, name in calls if name == 'apply_actions']
    if len(advance) != 1 or len(apply) != 1:
        raise ValueError('unverified_environment_step_order')
    return 'advance_then_apply' if advance[0] < apply[0] else 'apply_then_advance'


def settled_index(building, timing='apply_then_advance'):
    if timing not in ('apply_then_advance', 'advance_then_apply'):
        raise ValueError('unverified_environment_step_order')
    return max(0, building.time_step - (timing == 'apply_then_advance'))


def settled_energy(building, timing='apply_then_advance'):
    index = settled_index(building, timing)
    return {'settled_net': clean(building.net_electricity_consumption[index]),
            'settled_solar': abs(clean(building.solar_generation[index])),
            'settled_non_shiftable': clean(building.non_shiftable_load[index]),
            'settled_battery': clean(building.electrical_storage.electricity_consumption[index])}


class AssessmentTrace:
    def __init__(self, env, schema, case):
        self.env, self.case = env, case
        self.start = int(schema['simulation_start_time_step'])
        self.seconds = float(schema.get('seconds_per_time_step', 3600))
        self.steps, self.energy = [], [[] for _ in env.buildings]
        self.timing = transition_timing(env) if hasattr(env, 'step') else 'apply_then_advance'

    def before(self):
        return [clean(building.observations(include_all=True)) for building in self.env.buildings]

    def record(self, before, action, transition, mode='policy'):
        names = [list(building.active_actions) for building in self.env.buildings]
        flat = [float(value) for row in action for value in np.asarray(row).reshape(-1)]
        offset, entries = 0, []
        step = self.start + len(self.steps)
        reward = clean(transition[1])
        for index, building in enumerate(self.env.buildings):
            after = clean(building.observations(include_all=True))
            values = flat[offset:offset + len(names[index])]
            offset += len(names[index])
            named = dict(zip(names[index], values))
            final = {key: named.get(name) for key, name in
                     [('dhw', 'dhw_storage'), ('ele', 'electrical_storage'), ('tmp', 'cooling_device')]}
            lines = [f"[观测] {self.case['label']}；室温={before[index].get('indoor_dry_bulb_temperature')}；电价={before[index].get('electricity_pricing')}",
                     f"[动作] {mode}；{json.dumps(named, ensure_ascii=False)}",
                     f"[状态] 执行后室温={after.get('indoor_dry_bulb_temperature')}；电池SOC={after.get('electrical_storage_soc')}",
                     f"[奖励] 环境返回={reward}（环境原始口径）"]
            entries.append({'building': index, 'control_mode': mode, 'observations': before[index],
                            'outage_flag': bool(before[index].get('power_outage', False)),
                            'next_observations': after, 'actions': {'final': final, 'named': named, 'raw': values},
                            'battery_soc': before[index].get('electrical_storage_soc'),
                            'dhw_soc': before[index].get('dhw_storage_soc'),
                            'decision_summary': self.case['label'] + ' / ' + mode, 'narrative_lines': lines})
            def current(attribute):
                value = building
                try:
                    for part in attribute.split('.'):
                        value = getattr(value, part)
                    return clean(value[settled_index(building, self.timing)])
                except (AttributeError, IndexError, TypeError):
                    return None
            # Read the settled index of this executable environment, not its version label.
            executed = dict(before[index])
            for field in executed:
                # power_outage is a scalar at the *new* timestep. Its settled
                # history is power_outage_signal, which includes generated
                # events absent from energy_simulation.power_outage.
                attribute = ('power_outage_signal' if field == 'power_outage'
                             else field.replace('_storage_soc', '_storage.soc')
                             if field.endswith('_storage_soc') else field)
                value = current(attribute)
                if value is None:
                    value = current('energy_simulation.' + field)
                if value is not None:
                    executed[field] = value
            entries[-1]['settled'] = {
                field: executed.get(field) for field in (
                    'indoor_dry_bulb_temperature', 'occupant_count', 'comfort_band',
                    'indoor_dry_bulb_temperature_cooling_set_point',
                    'indoor_dry_bulb_temperature_heating_set_point', 'power_outage',
                    'electrical_storage_soc', 'dhw_storage_soc', 'electricity_pricing')}
            entries[-1]['settled'].update(
                net_electricity_consumption=current('net_electricity_consumption'),
                electricity_cost=current('net_electricity_consumption_cost'),
                unserved_energy_kwh=None)
            energy_step = step + int(self.timing == 'advance_then_apply')
            entries[-1]['settled']['source_step'] = energy_step
            timestamp = (datetime(2026, 1, 1) + timedelta(seconds=energy_step*self.seconds)).isoformat(sep=' ')
            self.energy[index].append({**executed, 'timestamp': timestamp, 'source_step': energy_step,
                'decision_source_step': step, 'environment_step_order': self.timing,
                'next_source_step': step+1,
                'Net Electricity Consumption-kWh': current('net_electricity_consumption'),
                'Energy Production from PV-kWh': current('solar_generation'),
                'Non-shiftable Load-kWh': current('non_shiftable_load'),
                'Battery (Dis)Charge-kWh': current('electrical_storage.electricity_consumption')})
        self.steps.append({'episode': 1, 'step': step, 'hour': before[0].get('hour'),
                           'control_mode': mode, 'reward': reward, 'info': clean(transition[-1]),
                           'terminated': bool(transition[2]),
                           'truncated': bool(transition[3]),
                           'environment_next_observations': clean(transition[0]),
                           'phases': [{'phase': 1, 'name': '读取观测', 'summary': self.case['label']},
                                      {'phase': 2, 'name': '执行动作', 'summary': mode},
                                      {'phase': 3, 'name': '环境转移', 'summary': '记录实际下一状态与环境奖励'}],
                           'buildings': entries})

    def save(self, directory, detailed_steps=None):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if detailed_steps:
            policy_steps = [step for step in self.steps if step['control_mode'] == 'policy']
            for actual, detailed in zip(policy_steps, detailed_steps):
                actual['phases'] = detailed.get('phases', actual['phases'])
                for entry, detail in zip(actual['buildings'], detailed.get('buildings', [])):
                    detail = dict(detail)
                    feedback = entry['narrative_lines'][-2:]
                    detail['actions'] = {**detail.get('actions', {}), **entry['actions']}
                    for key in ('observations', 'next_observations'):
                        detail[key] = entry[key]
                    entry.update(detail)
                    entry['narrative_lines'] = list(entry.get('narrative_lines', [])) + feedback
                    if not detail.get('residual', {}).get('enabled'):
                        entry['narrative_lines'] = [line for line in entry['narrative_lines'] if 'MARL' not in line]
        save_dashboard_artifacts(directory, self.case['label'], self.steps, self.energy)


def save_dashboard_artifacts(directory, algorithm, steps, energy):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {'version': 2, 'slim': True, 'algorithm': algorithm,
               'n_buildings': len(energy), 'timestampKind': 'assigned',
               'timestampNote': '2026 reference calendar, source_step retains source index', 'steps': steps}
    (directory / 'decision_trace.json').write_text(json.dumps(clean(payload), ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    for index, rows in enumerate(energy, 1):
        if not rows:
            continue
        for suffix, fields in [('', list(dict.fromkeys(key for row in rows for key in row))),
                               ('_battery', ['timestamp', 'Battery (Dis)Charge-kWh'])]:
            with (directory / f'exported_data_building_{index}{suffix}_ep0.csv').open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)


def export_aac_dashboard(rows, directory):
    """Adapt recorded AAC transitions; no model inference or synthesized rewards."""
    building_names = sorted({row['building'] for row in rows}, key=lambda name: int(name.rsplit('_', 1)[-1]))
    grouped, energy = {}, [[] for _ in building_names]
    for row in rows:
        index = building_names.index(row['building'])
        before = json.loads(row.get('observation_json') or '{}')
        after = json.loads(row.get('next_observation_json') or '{}')
        action = json.loads(row.get('action_json') or '{}')
        proposed = json.loads(row.get('proposed_action_json') or '[]')
        final = {key: action.get(name) for key, name in [('dhw', 'dhw_storage'), ('ele', 'electrical_storage'), ('tmp', 'cooling_device')]}
        raw = dict(zip(('dhw', 'ele', 'tmp'), proposed))
        source_before = row.get('source_timestep_before')
        step = int(row['step'] if source_before in (None, '') else source_before)
        def number(key):
            try:
                value = float(row[key])
                return value if np.isfinite(value) else None
            except (KeyError, ValueError, TypeError):
                return None
        gates = {key: value for key, value in row.items() if key.startswith('execution_')}
        timing = row.get('environment_step_order') or 'apply_then_advance'
        prefix = 'after_' if timing == 'advance_then_apply' else 'before_'
        entry = {'building': index, 'control_mode': 'aacmadrl', 'observations': before,
                 'outage_flag': bool(before.get('power_outage', False)),
                 'next_observations': after, 'actions': {'final': final, 'raw': raw, 'named': action},
                 'reward': number('reward'), 'battery_soc': before.get('electrical_storage_soc'),
                 'dhw_soc': before.get('dhw_storage_soc'), 'decision_summary': 'AACMADRL recorded transition',
                 'narrative_lines': [f"[观测] 室温={before.get('indoor_dry_bulb_temperature')}；电价={before.get('electricity_pricing')}",
                                     f"[策略输出] {raw}", f"[执行动作] {final}；执行约束={gates}",
                                     f"[状态] 下一室温={after.get('indoor_dry_bulb_temperature')}；电池SOC={after.get('electrical_storage_soc')}",
                                     f"[奖励] 环境原始奖励={number('reward')}"], 'execution': gates}
        entry['settled'] = {
            'net_electricity_consumption': number('settled_net'),
            'unserved_energy_kwh': None,
            **{field: number(prefix + field) for field in (
                'indoor_dry_bulb_temperature', 'occupant_count', 'comfort_band',
                'indoor_dry_bulb_temperature_cooling_set_point',
                'indoor_dry_bulb_temperature_heating_set_point',
                'electricity_pricing', 'electrical_storage_soc', 'dhw_storage_soc')}}
        record = grouped.setdefault(step, {'episode': 1, 'step': step, 'hour': before.get('hour'),
            'terminated': str(row.get('terminated')).lower() in ('true', '1'),
            'truncated': str(row.get('truncated')).lower() in ('true', '1'),
            'info': json.loads(row.get('environment_info_json') or '{}'),
            'phases': [{'phase': 1, 'name': '观测与策略输出', 'summary': 'AACMADRL'},
                       {'phase': 2, 'name': '执行约束', 'summary': '保留原始与实际执行动作'},
                       {'phase': 3, 'name': '环境反馈', 'summary': '实际下一状态与奖励'}], 'buildings': []})
        record['buildings'].append(entry)
        source_after = int(row.get('source_timestep_after') or step+1)
        settled = row.get('settled_net') not in (None, '')
        energy_step = step + int(timing == 'advance_then_apply') if settled else source_after
        entry['settled']['source_step'] = energy_step
        readings = after if timing == 'advance_then_apply' or not settled else before
        entry['settled']['power_outage'] = readings.get('power_outage')
        energy[index].append({**readings,
                              'timestamp': (datetime(2026, 1, 1)+timedelta(hours=energy_step)).isoformat(sep=' '),
                              'source_step': energy_step, 'next_source_step': source_after,
                              'decision_source_step': step, 'environment_step_order': timing,
                              'energy_timing': 'executed_step' if settled else 'legacy_next_observation',
                              'Net Electricity Consumption-kWh': number('settled_net' if settled else 'net'),
                              'Energy Production from PV-kWh': number('settled_solar' if settled else 'solar'),
                              'Non-shiftable Load-kWh': number('settled_non_shiftable' if settled else 'non_shiftable'),
                              'Battery (Dis)Charge-kWh': number('settled_battery' if settled else 'battery')})
    save_dashboard_artifacts(directory, 'AACMADRL', [grouped[key] for key in sorted(grouped)], energy)
