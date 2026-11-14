"""Build immutable, aligned OL1 scenario packages without rewriting source assets."""

import argparse
import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile


TEMPLATE_ID = 'citylearn_challenge_2023_phase_2_online_evaluation_1'
VERSION = '1.0.0'
ACTIONS = ['dhw_storage', 'electrical_storage', 'cooling_device']
DEFAULTS = {'startStep': 0, 'steps': 168, 'buildings': ['Building_1', 'Building_2', 'Building_3'],
            'loadMultiplier': 1.0, 'dhwMultiplier': 1.0, 'pvMultiplier': 1.0,
            'batteryCapacity': None, 'batteryPower': None, 'outageMode': 'original',
            'outageEvents': [], 'seed': 2023, 'outageSeed': 43791,
            'managedBuildings': [], 'community': {}}
DEVICE_KEYS = {'electrical_storage', 'pv', 'cooling_device', 'heating_device', 'dhw_device',
               'cooling_storage', 'heating_storage', 'dhw_storage'}
ALLOWED_TYPES = {
    'citylearn.building.Building', 'citylearn.building.LSTMDynamicsBuilding', 'citylearn.dynamics.LSTMDynamics',
    'citylearn.energy_model.HeatPump', 'citylearn.energy_model.ElectricHeater',
    'citylearn.energy_model.StorageTank', 'citylearn.energy_model.Battery',
    'citylearn.energy_model.PV', 'citylearn.power_outage.ReliabilityMetricsPowerOutage',
    'citylearn.agents.sac.SACBasicRBC', 'citylearn.reward_function.ComfortReward',
    'citylearn.agents.sac.SAC', 'citylearn.agents.sac.SACRBC', 'citylearn.agents.rbc.RBC',
    'citylearn.agents.rbc.BasicRBC', 'citylearn.agents.rbc.OptimizedRBC', 'citylearn.agents.rbc.BasicBatteryRBC',
    'citylearn.reward_function.RewardFunction', 'citylearn.reward_function.MARL',
    'citylearn.reward_function.IndependentSACReward', 'citylearn.reward_function.SolarPenaltyReward',
    'citylearn.reward_function.SolarPenaltyAndComfortReward',
}


class GenerationCancelled(RuntimeError):
    pass


def _checkpoint(cancelled):
    if cancelled is not None and cancelled():
        raise GenerationCancelled('Scenario generation cancelled')


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer in [{minimum}, {maximum}]')
    return value


def _number(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be finite and in [{minimum}, {maximum}]')
    return value


def _file(root, name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name) or '..' in name:
        raise ValueError('Unsafe asset filename')
    result = (root / name).resolve()
    if result.parent != root.resolve() or not result.is_file():
        raise ValueError(f'Missing or unsafe asset: {name}')
    return result


def _check_types(value):
    if isinstance(value, dict):
        if 'type' in value and value['type'] not in ALLOWED_TYPES:
            raise ValueError('Unsupported template class')
        for item in value.values():
            _check_types(item)
    elif isinstance(value, list):
        for item in value:
            _check_types(item)


def _load_template(template):
    root = Path(template).resolve()
    schema_bytes = _file(root, 'schema.json').read_bytes()
    schema = json.loads(schema_bytes)
    _check_types(schema)
    if schema.get('seconds_per_time_step') != 3600 or schema.get('simulation_start_time_step') != 0:
        raise ValueError('Only the hourly OL1 template starting at step 0 is supported')
    buildings = schema.get('buildings', {})
    if list(buildings) != DEFAULTS['buildings']:
        raise ValueError('Expected the three OL1 building prototypes')
    if {key for key, value in schema.get('actions', {}).items() if value.get('active')} != set(ACTIONS):
        raise ValueError('Template must retain all three OL1 actions in order')
    assets = {'schema.json': schema_bytes}
    tables = {}
    for name, building in buildings.items():
        if building.get('type') != 'citylearn.building.LSTMDynamicsBuilding' or building.get('inactive_actions'):
            raise ValueError('OL1 dynamic building and action contract required')
        for field in ('energy_simulation', 'weather', 'pricing', 'carbon_intensity'):
            filename = building[field]
            assets.setdefault(filename, _file(root, filename).read_bytes())
        filename = building['dynamics']['attributes']['filename']
        assets.setdefault(filename, _file(root, filename).read_bytes())
    for name, data in assets.items():
        if not name.endswith('.csv'):
            continue
        reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
        rows = list(reader)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not rows:
            raise ValueError(f'Invalid CSV header or empty file: {name}')
        for row in rows:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Invalid CSV row: {name}')
            try:
                if not all(math.isfinite(float(value)) for value in row.values()):
                    raise ValueError('Nonfinite input')
            except (ValueError, TypeError) as exc:
                raise ValueError(f'Invalid numeric CSV input: {name}') from exc
        tables[name] = (reader.fieldnames, rows)
    lengths = {len(rows) for _, rows in tables.values()}
    if len(lengths) != 1 or schema.get('simulation_end_time_step') != next(iter(lengths)) - 1:
        raise ValueError('Template time series must be aligned with the schema window')
    return schema, assets, tables, next(iter(lengths))


def _config(config, available):
    if not isinstance(config, dict) or set(config) - set(DEFAULTS):
        raise ValueError('Unknown scenario configuration fields')
    cfg = copy.deepcopy(DEFAULTS)
    cfg.update(copy.deepcopy(config))
    _integer(cfg['startStep'], 'startStep', 0, available - 2)
    _integer(cfg['steps'], 'steps', 2, available - cfg['startStep'])
    for key in ('seed', 'outageSeed'):
        _integer(cfg[key], key, 0, 2**31 - 1)
    selected = cfg['buildings']
    if not isinstance(selected, list) or not selected or any(not isinstance(x, str) or x not in DEFAULTS['buildings'] for x in selected) or len(set(selected)) != len(selected):
        raise ValueError('Select distinct OL1 prototypes')
    cfg['buildings'] = [name for name in DEFAULTS['buildings'] if name in selected]
    if not isinstance(cfg['managedBuildings'], list) or not isinstance(cfg['community'], dict):
        raise ValueError('Invalid managed building configuration')
    ids = set()
    for building in cfg['managedBuildings']:
        if not isinstance(building, dict) or building.get('prototype') not in DEFAULTS['buildings']:
            raise ValueError('Invalid building prototype mapping')
        identifier = building.get('id')
        if type(identifier) is not int or identifier <= 0 or identifier in ids:
            raise ValueError('Select distinct managed buildings')
        ids.add(identifier)
        devices = building.get('devices')
        if not isinstance(devices, dict) or set(devices) - DEVICE_KEYS:
            raise ValueError('Invalid building equipment')
        _check_types(devices)
        _check_types(building.get('definition', {}))
    _check_types(cfg['community'].get('schema', {}))
    for key in ('loadMultiplier', 'dhwMultiplier'):
        _number(cfg[key], key, 0.8, 1.2)
    _number(cfg['pvMultiplier'], 'pvMultiplier', 0, 3)
    for key in ('batteryCapacity', 'batteryPower'):
        if cfg[key] is not None:
            _number(cfg[key], key, 0.1, 100)
    if cfg['outageMode'] not in ('original', 'off', 'fixed') or not isinstance(cfg['outageEvents'], list):
        raise ValueError('Unsupported outage mode or events')
    if cfg['outageMode'] != 'fixed' and cfg['outageEvents']:
        raise ValueError('Outage events require fixed mode')
    if len(cfg['outageEvents']) > 100 or (cfg['outageMode'] == 'fixed' and not cfg['outageEvents']):
        raise ValueError('Fixed mode requires between 1 and 100 events')
    for event in cfg['outageEvents']:
        if not isinstance(event, dict) or set(event) != {'startStep', 'steps'}:
            raise ValueError('Invalid outage event')
        _integer(event['startStep'], 'event.startStep', cfg['startStep'], cfg['startStep'] + cfg['steps'] - 1)
        _integer(event['steps'], 'event.steps', 1, cfg['startStep'] + cfg['steps'] - event['startStep'])
    cfg['outageEvents'].sort(key=lambda event: event['startStep'])
    return cfg


def _selected_buildings(cfg):
    if cfg['managedBuildings']:
        return [(f'Building_{i + 1}', item['prototype'], item)
                for i, item in enumerate(cfg['managedBuildings'])]
    return [(name, name, None) for name in cfg['buildings']]


def _equipment(building, managed):
    if managed is None:
        return
    if not managed.get('legacyEquipment'):
        for key in DEVICE_KEYS:
            building.pop(key, None)
    building.update(copy.deepcopy(managed['devices']))
    # Keep the prototype model and its matching architecture/normalization.
    building.update({key: copy.deepcopy(value) for key, value in managed.get('definition', {}).items()
                     if key not in ('type', 'dynamics')})


def _summary(cfg):
    end = cfg['startStep'] + cfg['steps']
    return {'version': 1, 'generatorVersion': VERSION, 'sourceMode': 'synthetic_ol1',
            'templateId': TEMPLATE_ID, 'configuration': cfg, 'buildingCount': len(_selected_buildings(cfg)),
            'building': {key: cfg['community'][key] for key in ('timezone', 'currency') if key in cfg['community']},
            'timeSteps': end, 'scoreStartStep': cfg['startStep'], 'scoreEndStepExclusive': end,
            'scoreSteps': cfg['steps'], 'historySteps': cfg['startStep'], 'secondsPerTimeStep': 3600,
            'timestampKind': 'source_calendar', 'forecastPolicy': 'preserve_source_causal_forecasts',
            'warnings': ['Prototype-derived sensitivity scenario; not a newly calibrated building.',
                         'History is retained; downstream evaluation must apply the declared score window.',
                         'Raw full-window startup and warmed-window scores must not be mixed.']}


def preview(template, config):
    schema, _, tables, available = _load_template(template)
    cfg = _config(config, available)
    result = _summary(cfg)
    result['availableSteps'] = available
    result['curves'] = {}
    stride = max(1, math.ceil(cfg['steps'] / 500))
    for name, prototype, managed in _selected_buildings(cfg):
        building = copy.deepcopy(schema['buildings'][prototype])
        _equipment(building, managed)
        rows = tables[building['energy_simulation']][1]
        source_pv = schema['buildings'][prototype].get('pv', {}).get('attributes', {}).get('nominal_power', 0)
        pv = building.get('pv', {}).get('attributes', {}).get('nominal_power', 0)
        result['curves'][name] = [
            {'step': i, 'month': int(rows[i]['month']), 'hour': int(rows[i]['hour']),
             'sourceLoad': float(rows[i]['non_shiftable_load']),
             'load': float(rows[i]['non_shiftable_load']) * cfg['loadMultiplier'],
             'sourceDhw': float(rows[i]['dhw_demand']), 'dhw': float(rows[i]['dhw_demand']) * cfg['dhwMultiplier'],
             'sourcePv': float(rows[i]['solar_generation']) * source_pv / 1000,
             'pv': float(rows[i]['solar_generation']) * pv * cfg['pvMultiplier'] / 1000}
            for i in range(cfg['startStep'], cfg['startStep'] + cfg['steps'], stride)]
    return result


def _build(staging, schema, assets, tables, cfg, cancelled):
    end = cfg['startStep'] + cfg['steps']
    schema = copy.deepcopy(schema)
    global_config = cfg['community'].get('schema', {})
    for key in ('central_agent', 'random_seed', 'observations', 'actions', 'reward_function', 'agent'):
        if key in global_config:
            schema[key] = copy.deepcopy(global_config[key])
    schema.update(root_directory=None, simulation_start_time_step=0, simulation_end_time_step=end - 1,
                  episode_time_steps=None, rolling_episode_split=False, random_episode_split=False,
                  random_seed=global_config.get('random_seed', cfg['seed']))
    source_buildings = schema['buildings']
    selected = _selected_buildings(cfg)
    schema['buildings'] = {name: copy.deepcopy(source_buildings[prototype]) for name, prototype, _ in selected}
    managed_by_name = {name: managed for name, _, managed in selected}
    used = set()
    for name, building in schema['buildings'].items():
        _checkpoint(cancelled)
        managed = managed_by_name[name]
        _equipment(building, managed)
        for device, attribute, key in (('pv', 'nominal_power', 'pvMultiplier'),
                                       ('electrical_storage', 'capacity', 'batteryCapacity'),
                                       ('electrical_storage', 'nominal_power', 'batteryPower')):
            if managed is None and cfg[key] is not None:
                building[device]['autosize'] = False
                value = building[device]['attributes'][attribute] * cfg[key] if key == 'pvMultiplier' else cfg[key]
                building[device]['attributes'][attribute] = value
        outage = building['power_outage']
        if managed is None or 'power_outage' not in managed.get('definition', {}):
            outage['simulate_power_outage'] = cfg['outageMode'] != 'off'
            outage['stochastic_power_outage'] = cfg['outageMode'] == 'original'
            outage['stochastic_power_outage_model']['attributes']['random_seed'] = cfg['outageSeed']
        if managed is not None:
            inactive = set(building.get('inactive_actions', []))
            for action in schema['actions']:
                if action == 'cooling_or_heating_device':
                    if not all(key in building for key in ('cooling_device', 'heating_device', 'dynamics')):
                        inactive.add(action)
                elif action not in building:
                    inactive.add(action)
            building['inactive_actions'] = sorted(inactive)
            inactive_obs = set(building.get('inactive_observations', []))
            for observation in schema['observations']:
                if observation.endswith('_soc') and observation[:-4] not in building:
                    inactive_obs.add(observation)
            building['inactive_observations'] = sorted(inactive_obs)
        source_filename = building['energy_simulation']
        filename = name + '.csv' if managed is not None else source_filename
        building['energy_simulation'] = filename
        headers, source = tables[source_filename]
        rows = copy.deepcopy(source[:end])
        changed = cfg['loadMultiplier'] != 1 or cfg['dhwMultiplier'] != 1 or cfg['outageMode'] == 'fixed'
        for i, row in enumerate(rows):
            for field, key in (('non_shiftable_load', 'loadMultiplier'), ('dhw_demand', 'dhwMultiplier')):
                if cfg[key] != 1:
                    row[field] = format(float(row[field]) * cfg[key], '.12g')
            if cfg['outageMode'] == 'fixed':
                row['power_outage'] = int(any(event['startStep'] <= i < event['startStep'] + event['steps'] for event in cfg['outageEvents']))
        if changed:
            output = io.StringIO(newline='')
            writer = csv.DictWriter(output, fieldnames=headers + ([] if 'power_outage' in headers or cfg['outageMode'] != 'fixed' else ['power_outage']), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
            (staging / filename).write_bytes(output.getvalue().encode('utf-8'))
        else:
            (staging / filename).write_bytes(b''.join(assets[source_filename].splitlines(keepends=True)[:end + 1]))
        used.add(filename)
        for field in ('weather', 'pricing', 'carbon_intensity'):
            filename = building[field]
            (staging / filename).write_bytes(b''.join(assets[filename].splitlines(keepends=True)[:end + 1]))
            used.add(filename)
        if building.get('dynamics'):
            source_filename = building['dynamics']['attributes']['filename']
            filename = name + '.pth' if managed is not None else source_filename
            data = assets[source_filename]
            building['dynamics']['attributes']['filename'] = filename
            (staging / filename).write_bytes(data)
            used.add(filename)
    _write_json(staging / 'schema.json', schema)
    _write_json(staging / 'generation_config.json', cfg)
    return used | {'schema.json', 'generation_config.json'}


def runtime_validate(directory, cancelled=None, progress=None):
    import numpy as np
    import torch
    from citylearn import __version__
    from citylearn.citylearn import CityLearnEnv
    torch.set_num_threads(1)
    _checkpoint(cancelled)
    directory = Path(directory).resolve()
    schema = json.loads((directory / 'schema.json').read_text(encoding='utf-8'))
    schema['root_directory'] = str(directory)
    env = CityLearnEnv(schema)
    transitions = 0
    try:
        chesca_root = Path(__file__).resolve().parent / 'CHESCA-copy'
        if str(chesca_root) not in sys.path:
            sys.path.insert(0, str(chesca_root))
        from checa.utils import observation_index

        active = [list(building.active_actions) for building in env.buildings]
        # CHESCA derives building suffixes from repeated central observations.
        # Single-building and decentralized environments cannot use that contract.
        chesca_supported = env.central_agent and len(active) > 1 and all(names == ACTIONS for names in active)
        shared_observations = {
            'hour', 'day_type', 'outdoor_dry_bulb_temperature',
            'direct_solar_irradiance', 'diffuse_solar_irradiance',
            *[f'{kind}_solar_irradiance_predicted_{hours}h'
              for kind in ('direct', 'diffuse') for hours in (6, 12, 24)],
        }
        building_observations = {
            'solar_generation', 'non_shiftable_load', 'net_electricity_consumption',
            'power_outage', 'electrical_storage_soc', 'dhw_storage_soc',
            'indoor_dry_bulb_temperature', 'indoor_dry_bulb_temperature_set_point',
        }
        compatibility_reasons = []
        if not chesca_supported:
            compatibility_reasons.append('CHESCA requires a central multi-building environment with OL1 actions.')
        # Resolve aliases with the same reader used by CHESCA. Building fields
        # carry suffixes in its central observation vector; shared fields do not.
        for building in env.buildings:
            names = list(building.active_observations)
            suffixed_names = [f'{name}_0' for name in names]
            missing = []
            for name in sorted(shared_observations | building_observations):
                try:
                    if name in building_observations:
                        observation_index(suffixed_names, f'{name}_0')
                    else:
                        observation_index(names, name)
                except ValueError:
                    missing.append(name)
            if missing:
                compatibility_reasons.append(f'{building.name}: missing observations: {", ".join(missing)}')
        chesca_supported = chesca_supported and not compatibility_reasons
        observations, _ = env.reset()
        while not env.terminated:
            _checkpoint(cancelled)
            actions = [[0.0] * len(env.action_names[0])] if env.central_agent else [[0.0] * len(names) for names in env.action_names]
            observations, reward, terminated, truncated, _ = env.step(actions)
            if any(not np.isfinite(np.asarray(values, dtype=float)).all() for values in observations) or not np.isfinite(reward).all():
                raise ValueError('Nonfinite observations or rewards')
            for building in env.buildings:
                state_step = max(0, env.time_step - 1)
                if not np.isfinite(building.indoor_dry_bulb_temperature[state_step]) or not np.isfinite(building.net_electricity_consumption[state_step]):
                    raise ValueError('Nonfinite building state')
                if 'electrical_storage' in schema['buildings'][building.name]:
                    soc = building.electrical_storage.soc[state_step]
                    if not np.isfinite(soc) or not -1e-5 <= soc <= 1.00001:
                        raise ValueError('Invalid battery SOC')
            transitions += 1
            if progress is not None and transitions % 24 == 0:
                progress('runtime_validation', transitions, env.time_steps - 1)
            if truncated and not terminated:
                raise ValueError('Unexpected truncated validation')
        if transitions != env.time_steps - 1:
            raise ValueError('Runtime transition count mismatch')
        import citylearn
        runtime_root = Path(citylearn.__file__).parent
        code_hashes = {name: _sha((runtime_root / name).read_bytes()) for name in
                       ('citylearn.py', 'building.py', 'energy_model.py', 'dynamics.py', 'data.py', 'power_outage.py', 'reward_function.py', 'agents/base.py')}
        if not chesca_supported:
            return {'runtimeValidation': 'passed', 'citylearnVersion': __version__, 'transitions': transitions,
                    'runtimeCodeHashes': code_hashes, 'timeSteps': env.time_steps, 'actionNames': active,
                    'controller': 'Zero-action validation policy', 'chescaSmokeTest': 'not_supported',
                    'chescaSmokeSteps': 0, 'chescaCompatibilityReason': '; '.join(compatibility_reasons),
                    'scope': 'Numerical validation passed; this equipment/action contract is not CHESCA-compatible.'}
        from agents.user_agent import SubmissionAgent
        from utils.ches_env import WrapperEnv
        smoke_env = CityLearnEnv(schema)
        try:
            smoke_observations, _ = smoke_env.reset()
            policy = SubmissionAgent(WrapperEnv(smoke_env), params={'tau': 1, 'balance_type': 'C'})
            smoke_steps = 0
            for _ in range(min(3, smoke_env.time_steps - 1)):
                action = policy.predict(smoke_observations, deterministic=True)
                if len(action) != len(smoke_env.action_space):
                    raise ValueError('CHESCA action grouping does not match the CityLearn environment')
                for index, values in enumerate(action):
                    values = np.asarray(values, dtype=float)
                    space = smoke_env.action_space[index]
                    if values.shape != space.shape or not np.isfinite(values).all():
                        raise ValueError('CHESCA returned an invalid action vector')
                    if np.any(values < space.low - 1e-6) or np.any(values > space.high + 1e-6):
                        raise ValueError('CHESCA action is outside the CityLearn action bounds')
                smoke_observations, reward, terminated, truncated, _ = smoke_env.step(action)
                if not np.isfinite(np.asarray(reward, dtype=float)).all():
                    raise ValueError('CHESCA smoke run returned a nonfinite reward')
                smoke_steps += 1
                if terminated or truncated:
                    break
            if smoke_steps < 1:
                raise ValueError('CHESCA smoke run performed no transitions')
        except GenerationCancelled:
            raise
        except Exception as error:
            _checkpoint(cancelled)
            return {'runtimeValidation': 'passed', 'citylearnVersion': __version__, 'transitions': transitions,
                    'runtimeCodeHashes': code_hashes, 'timeSteps': env.time_steps, 'actionNames': active,
                    'controller': 'Zero-action validation policy', 'chescaSmokeTest': 'not_supported',
                    'chescaSmokeSteps': 0, 'chescaCompatibilityReason': str(error),
                    'scope': 'Numerical validation passed; the CHESCA smoke test rejected this input contract.'}
        finally:
            smoke_env.close()
        return {'runtimeValidation': 'passed', 'citylearnVersion': __version__, 'transitions': transitions,
                'runtimeCodeHashes': code_hashes,
                'timeSteps': env.time_steps, 'actionNames': active[0], 'controller': 'Zero-action validation policy',
                'chescaSmokeTest': 'passed', 'chescaSmokeSteps': smoke_steps,
                'chescaActionGrouping': 'central agent flat vector in OL1 building/action order',
                'scope': 'Full-window numerical and device-contract validation; not a physical calibration certificate.'}
    finally:
        env.close()


def generate(template, output, config, *, cancelled=None, progress=None, validate_runtime=False):
    output = Path(output).resolve()
    template = Path(template).resolve()
    if output.exists():
        raise FileExistsError('Scenario output already exists')
    if output.is_relative_to(template):
        raise ValueError('Output must not be inside the source template')
    _checkpoint(cancelled)
    schema, assets, tables, available = _load_template(template)
    cfg = _config(config, available)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.' + output.name + '-', dir=output.parent))
    try:
        if progress is not None:
            progress('generating', 0, 1)
        files = _build(staging, schema, assets, tables, cfg, cancelled)
        _checkpoint(cancelled)
        report = runtime_validate(staging, cancelled, progress) if validate_runtime else {'runtimeValidation': 'not_requested'}
        _write_json(staging / 'validation_report.json', report)
        files.add('validation_report.json')
        manifest = _summary(cfg)
        manifest.update(sourceFiles={name: _sha(data) for name, data in sorted(assets.items())},
                        files={name: _sha((staging / name).read_bytes()) for name in sorted(files)},
                        readyForEvaluation=validate_runtime, runtimeValidation=report['runtimeValidation'],
                        chescaCompatible=report.get('chescaSmokeTest') == 'passed')
        manifest['contentHash'] = _sha(_canonical(manifest['files']))
        _write_json(staging / 'manifest.json', manifest)
        verify_package(staging)
        _checkpoint(cancelled)
        staging.rename(output)
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_package(directory):
    directory = Path(directory).resolve()
    manifest = json.loads(_file(directory, 'manifest.json').read_text(encoding='utf-8'))
    files = manifest.get('files')
    if not isinstance(files, dict) or not {'schema.json', 'generation_config.json', 'validation_report.json'} <= set(files):
        raise ValueError('Incomplete package manifest')
    for name, expected in files.items():
        if _sha(_file(directory, name).read_bytes()) != expected:
            raise ValueError(f'Package hash mismatch: {name}')
    if _sha(_canonical(files)) != manifest.get('contentHash'):
        raise ValueError('Package content hash mismatch')
    cfg = json.loads((directory / 'generation_config.json').read_text(encoding='utf-8'))
    if cfg != manifest.get('configuration'):
        raise ValueError('Manifest configuration mismatch')
    summary = _summary(_config(cfg, 2208))
    # Older releases predate optional managed-community fields.
    if any(manifest.get(key) != summary[key] for key in summary if key not in ('configuration', 'building')):
        raise ValueError('Manifest window or provenance mismatch')
    schema = json.loads((directory / 'schema.json').read_text(encoding='utf-8'))
    _check_types(schema)
    if schema['simulation_end_time_step'] + 1 != manifest['timeSteps'] or schema['simulation_start_time_step'] != 0:
        raise ValueError('Manifest/schema window mismatch')
    report = json.loads((directory / 'validation_report.json').read_text(encoding='utf-8'))
    passed = report.get('runtimeValidation') == 'passed'
    if manifest.get('runtimeValidation') != report.get('runtimeValidation') or manifest.get('readyForEvaluation') is not passed:
        raise ValueError('Manifest/runtime validation mismatch')
    if passed and (report.get('transitions') != manifest['timeSteps'] - 1 or not report.get('runtimeCodeHashes')):
        raise ValueError('Incomplete runtime evidence')
    smoke_passed = report.get('chescaSmokeTest') == 'passed' and report.get('chescaSmokeSteps', 0) >= 1
    if passed and manifest.get('chescaCompatible') is not smoke_passed:
        raise ValueError('CHESCA compatibility evidence does not match the manifest')
    if not passed and manifest.get('chescaCompatible') is not False:
        raise ValueError('Unvalidated packages cannot claim CHESCA compatibility')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['preview', 'generate', 'verify'])
    parser.add_argument('--template', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    if args.operation == 'verify':
        result = verify_package(args.output)
    else:
        if args.template is None or args.config is None:
            parser.error('--template and --config are required')
        config = json.loads(args.config.read_text(encoding='utf-8-sig'))
        if args.operation == 'preview':
            result = preview(args.template, config)
        else:
            if args.output is None:
                parser.error('--output is required')
            result = generate(args.template, args.output, config, validate_runtime=True,
                              progress=lambda stage, done, total: print(json.dumps({'stage': stage, 'done': done, 'total': total}), flush=True))
    print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
