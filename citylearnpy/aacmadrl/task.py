"""AACMADRL platform contract. All files belong to an individual task."""
import argparse
import csv
import gzip
import hashlib
import json
import math
import importlib
import os
import sys
import re
import shutil
import subprocess
from aacmadrl.control_profiles import HISTORICAL_PROFILE
from aacmadrl.runtime_contract import (
    inspect_runtime, validate_local_regression, inherit_training_parameters,
    LOCAL_SHA256)
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))
CORE = Path(__file__).with_name('core.py')
MODEL_DIR = Path('checkpoints/aacmadrl')
FROZEN_ANCHOR_PATH = Path(__file__).with_name('anchor_checkpoint.pt')
FROZEN_ANCHOR_SHA256 = '3d9ebd7402c5ca8e3d0c8ebec2ccbc3ec853855c5a902349b0f30fa2f94402b1'
DEFAULT_TRAIN = 'citylearn_challenge_2023_phase_2_local_evaluation'
DEFAULT_EVAL = 'citylearn_challenge_2023_phase_2_online_evaluation_1'
HISTORICAL_TRAIN_SHA256 = 'ebaf5a18299d759bd9a369680199d40c4451aa9c9af523cf4e97e31a374ab567'
HISTORICAL_BASELINE_COSTS = {
    'Building_1': 33.894485857206746,
    'Building_2': 19.82718759198906,
    'Building_3': 29.60129014123231,
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def digest(directory):
    value = hashlib.sha256()
    for path in sorted(p for p in directory.rglob('*') if p.is_file()):
        value.update(path.relative_to(directory).as_posix().encode())
        value.update(path.read_bytes())
    return value.hexdigest()


def resolve_dataset(value, citylearnpy_root=ROOT):
    candidate = Path(value)
    if candidate.is_file() and candidate.name == 'schema.json':
        return candidate.resolve().parent
    for path in [candidate, citylearnpy_root.parent.parent / 'datasets' / value,
                 citylearnpy_root / 'datasets' / value,
                 citylearnpy_root / 'CHESCA-copy/data/schemas' / value,
                 citylearnpy_root / 'CHESCA-main/data/schemas' / value,
                 citylearnpy_root / 'data/schemas' / value]:
        if (path / 'schema.json').is_file():
            return path.resolve()
    raise FileNotFoundError(f'找不到数据集 schema.json: {value}')


def validate_window(schema, start, steps):
    low = int(schema.get('simulation_start_time_step', 0))
    high = int(schema['simulation_end_time_step'])
    start = low if start is None else start
    end = high if steps == 0 else start + steps - 1
    if steps < 0 or not low <= start < end <= high:
        raise ValueError(f'窗口必须在 [{low}, {high}] 内，且至少两条状态记录')
    return start, end


def no_control_baseline_costs(env, window, expected_transitions):
    """Evaluate CityLearn's reference bill after a full no-control rollout."""
    import numpy as np
    env.reset()
    done = False
    for _ in range(expected_transitions):
        _, _, done, truncated, _ = env.step(
            [[0.0] * len(building.active_actions) for building in env.buildings])
        if truncated:
            raise RuntimeError('无控制基线环境提前截断')
        if done:
            break
    if not done:
        raise RuntimeError('无控制基线未在 schema 终点结束')

    costs = {}
    start, end = window
    for building in env.buildings:
        reference = np.asarray(
            building.net_electricity_consumption_cost_without_storage_and_partial_load,
            dtype=float)
        if end >= len(reference):
            raise ValueError(f'{building.name} 的基线长度不足以覆盖窗口 {window}')
        bill = float(np.maximum(reference[start:end + 1], 0).sum())
        if bill <= 0 or not math.isfinite(bill):
            raise ValueError(f'{building.name} 无有效正购电基线')
        costs[building.name] = bill
    return costs


def resolve_checkpoint(task_root, task_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', task_id or ''):
        raise ValueError('非法训练任务 ID')
    for name in [task_id, task_id + '-train']:
        directory = task_root / name / MODEL_DIR
        manifest = directory / 'model_manifest.json'
        if not manifest.is_file():
            continue
        info = json.loads(manifest.read_text(encoding='utf-8'))
        path = directory / info.get('checkpoint', '')
        if info.get('algorithm') != 'AACMADRL' or path.name != 'model.pt':
            raise ValueError('训练任务不是受支持的 AACMADRL 模型')
        if path.is_file():
            expected = info.get('checkpoint_sha256')
            if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('模型文件哈希与训练清单不一致')
            return path
    raise FileNotFoundError(f'训练任务 {task_id} 没有 AACMADRL 模型；不使用全局兜底')


def select_checkpoint(rows, target, selector='comfort_then_cost', anchor=None, local_results=None):
    if selector not in ('comfort_then_cost', 'piecewise'):
        raise ValueError('未知模型选择规则')
    if selector == 'piecewise' and (anchor is None or local_results is None):
        raise ValueError('分段评分选点需要预声明Anchor和训练侧完整评估')
    candidates = []
    for row in rows:
        if row.get('episode', 0) < 1 or row.get('updates', 0) < 1:
            continue
        per = row.get('training_local_per_building', row['per_building'])
        costs = [float(v['cost_total']) for v in per.values()]
        ds = [float(v['discomfort_proportion']) for v in per.values()]
        if not costs or not all(math.isfinite(v) for v in costs + ds):
            raise ValueError('选点指标缺失或非有限值')
        qualified = all(d < target for d in ds)
        item = dict(episode=row['episode'], updates=row['updates'],
                    mean_cost=sum(costs) / len(costs), max_discomfort=max(ds),
                    comfort_qualified=qualified, selector_dataset='training_only')
        value = item['mean_cost']
        if selector == 'piecewise':
            result = local_results.get(row['episode'])
            if result is None or set(result.get('per_building', {})) != set(per):
                raise ValueError('训练侧完整评估与选点摘要不一致')
            for name, metrics in per.items():
                for key in ('cost_total', 'discomfort_proportion'):
                    actual = result['per_building'][name].get(key)
                    if actual is None or not math.isclose(float(actual), float(metrics[key]),
                                                          rel_tol=1.e-9, abs_tol=1.e-9):
                        raise ValueError('训练侧完整评估与选点摘要指标不一致')
            value = comparison_score(result, anchor, 1.)['score']
        item.update(selection_metric=selector, selection_value=value)
        rank = (0 if qualified else 1, 0 if qualified else max(ds), value, row['episode'])
        candidates.append((rank, item))
    if not candidates:
        raise ValueError('没有发生梯度更新的训练模型；增加训练轮数/窗口，不能把初始模型当成已训练模型')
    return min(candidates, key=lambda entry: entry[0])[1]


def penalty(d):
    return min(d, 3) + 3 * min(max(d - 3, 0), 2) + 5 * min(max(d - 5, 0), 3) + 10 * max(d - 8, 0)


def comparison_score(result, anchor, alpha):
    from evaluation_scoring import compute_score
    score = compute_score(result, anchor, alpha)
    if score['status'] != 'available':
        raise ValueError(';'.join(score['reason_codes']))
    return score


def export_kpis(result, output):
    values = {}
    names = []
    for row in result['official_kpi']:
        name = row['name']
        if name not in names:
            names.append(name)
        values.setdefault(row['cost_function'], {})[name] = row['value']
    names.sort(key=lambda name: (name == 'District', name))
    with (output / 'exported_kpis.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['KPI'] + names)
        for metric, row in sorted(values.items()):
            writer.writerow([metric] + [row.get(name) for name in names])
    print('outputkpi', flush=True)
    for metric, row in sorted(values.items()):
        print(metric + ' ' + ' '.join(f'{float(row[name]):.12g}' if row.get(name) is not None else 'NaN'
                                      for name in ['Building_1', 'Building_2', 'Building_3', 'District']), flush=True)


def export_trace(result, output):
    path = Path(result['audit_log']['file'])
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != result['audit_log']['expected_rows']:
        raise ValueError('逐步日志行数不完整')
    for building in result['per_building']:
        selected = [row for row in rows if row['building'] == building]
        with (output / f'aacmadrl_trace_{building}_ep1.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(selected[0]))
            writer.writeheader()
            writer.writerows(selected)
    with (output / 'aacmadrl_step_log.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    from assessment_trace import export_aac_dashboard
    export_aac_dashboard(rows, output)


def prepare_environment(dataset, window):
    import numpy as np
    from citylearn.citylearn import CityLearnEnv
    data_module = importlib.import_module('citylearn.data')
    original_read_csv = __import__('pandas').read_csv

    def aac_read_csv(path, *args, **kwargs):
        frame = original_read_csv(path, *args, **kwargs)
        if 'Month' in frame.columns and Path(path).name.startswith('Building_'):
            aliases = {
                'month': 'month', 'hour': 'hour', 'day_type': 'day_type',
                'daylight_savings_status': 'daylight_savings_status',
                'indoor temperature (c)': 'indoor_dry_bulb_temperature',
                'average unmet cooling setpoint difference (c)': 'average_unmet_cooling_setpoint_difference',
                'indoor relative humidity (%)': 'indoor_relative_humidity',
                'equipment electric power (kwh)': 'non_shiftable_load',
                'dhw heating (kwh)': 'dhw_demand', 'cooling load (kwh)': 'cooling_demand',
                'heating load (kwh)': 'heating_demand', 'solar generation (w/kw)': 'solar_generation',
                'occupant count (people)': 'occupant_count',
                'temperature set point (c)': 'indoor_dry_bulb_temperature_cooling_set_point',
                'hvac mode (off/cooling/heating)': 'hvac_mode',
            }
            source = {str(column).strip().lower(): column for column in frame.columns}
            out = frame.rename(columns={source[key]: target for key, target in aliases.items() if key in source})
            out['daylight_savings_status'] = out.get('daylight_savings_status', np.zeros(len(out)))
            out['indoor_dry_bulb_temperature_heating_set_point'] = out[
                'indoor_dry_bulb_temperature_cooling_set_point'] - 2.
            out['comfort_band'] = np.full(len(out), 2.)
            out['power_outage'] = np.zeros(len(out))
            out['temperature_difference'] = out['indoor_dry_bulb_temperature'] - out[
                'indoor_dry_bulb_temperature_cooling_set_point']
            out['heating_temperature_difference'] = out['indoor_dry_bulb_temperature'] - out[
                'indoor_dry_bulb_temperature_heating_set_point']
            out['cooling_setpoint_difference'] = out['temperature_difference']
            out['heating_setpoint_difference'] = out['heating_temperature_difference']
            out['indoor_dry_bulb_temperature_heating_set_point_without_control'] = out[
                'indoor_dry_bulb_temperature_heating_set_point']
            out['indoor_dry_bulb_temperature_cooling_set_point_without_control'] = out[
                'indoor_dry_bulb_temperature_cooling_set_point']
            return out
        if 'Outdoor Drybulb Temperature (C)' in frame.columns:
            aliases = {
                'Outdoor Drybulb Temperature (C)': 'outdoor_dry_bulb_temperature',
                'Outdoor Relative Humidity (%)': 'outdoor_relative_humidity',
                'Diffuse Solar Radiation (W/m2)': 'diffuse_solar_irradiance',
                'Direct Solar Radiation (W/m2)': 'direct_solar_irradiance',
            }
            for prefix, suffix in [('6h', '1'), ('12h', '2'), ('24h', '3')]:
                for field, output in [('Outdoor Drybulb Temperature', 'outdoor_dry_bulb_temperature'),
                                      ('Outdoor Relative Humidity', 'outdoor_relative_humidity'),
                                      ('Diffuse Solar Radiation', 'diffuse_solar_irradiance'),
                                      ('Direct Solar Radiation', 'direct_solar_irradiance')]:
                    aliases[f'{prefix} {field} ({"C" if "Temperature" in field else "%" if "Humidity" in field else "W/m2"})'] = f'{output}_predicted_{suffix}'
            aliases = {key: val for key, val in aliases.items() if key in frame.columns}
            return frame.rename(columns=aliases)
        if 'Electricity Pricing ($/kWh)' in frame.columns:
            return frame.rename(columns={
                'Electricity Pricing ($/kWh)': 'electricity_pricing',
                '6h Electricity Pricing ($/kWh)': 'electricity_pricing_predicted_1',
                '12h Electricity Pricing ($/kWh)': 'electricity_pricing_predicted_2',
                '24h Electricity Pricing ($/kWh)': 'electricity_pricing_predicted_3'})
        if 'Carbon Intensity (kg_CO2/kWh)' in frame.columns:
            return frame.rename(columns={'Carbon Intensity (kg_CO2/kWh)': 'carbon_intensity'})
        return frame

    citylearn_module = importlib.import_module('citylearn.citylearn')
    old_env_csv, old_data_csv = citylearn_module.pd.read_csv, data_module.pd.read_csv
    citylearn_module.pd.read_csv = aac_read_csv
    try:
        env = CityLearnEnv(str(dataset / 'schema.json'), central_agent=False, random_seed=41)
    finally:
        citylearn_module.pd.read_csv = old_env_csv
    try:
        if any(b.active_actions != ['dhw_storage', 'electrical_storage', 'cooling_device'] for b in env.buildings):
            raise ValueError('当前 AACMADRL 支持依次为 DHW、电池、制冷的三个动作；其它设备需单独适配')
        dataset_sha256 = digest(dataset)
        schema_window = (int(json.loads((dataset / 'schema.json').read_text(encoding='utf-8'))
                             .get('simulation_start_time_step', 0)),
                         int(json.loads((dataset / 'schema.json').read_text(encoding='utf-8'))
                             ['simulation_end_time_step']))
        if (dataset_sha256 == HISTORICAL_TRAIN_SHA256 and window == schema_window
                and set(HISTORICAL_BASELINE_COSTS) == {b.name for b in env.buildings}):
            costs = dict(HISTORICAL_BASELINE_COSTS)
            baseline_method = 'historical_aac_fixed_baseline'
        else:
            costs = no_control_baseline_costs(env, window, env.time_steps - 1)
            baseline_method = 'citylearn_no_control_rollout'
    finally:
        env.close()
    child_env = os.environ.copy()
    child_env.update(AACMADRL_DATA=str(dataset), AACMADRL_DATA_SHA256=dataset_sha256,
                     AACMADRL_BASELINE_COSTS=json.dumps(costs), PYTHONHASHSEED='0',
                     AACMADRL_BASELINE_METHOD=baseline_method,
                     OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    return child_env, costs


def parser(mode):
    p = argparse.ArgumentParser(description=f'AACMADRL 平台{mode}，CPU 单线程任务')
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--control-profile', choices=('none', HISTORICAL_PROFILE), default='none')
    p.add_argument('--train-schema', default=DEFAULT_TRAIN)
    p.add_argument('--eval-schema', default=DEFAULT_EVAL)
    p.add_argument('--train-epochs', type=int, default=5)
    p.add_argument('--train-batch-size', type=int, choices=(128, 256), default=256)
    p.add_argument('--seed', type=int, default=49)
    p.add_argument('--actor-lr', type=float, default=.0001)
    p.add_argument('--critic-lr', type=float, default=.001)
    p.add_argument('--discount', type=float, default=.99)
    p.add_argument('--tau', type=float, default=.005)
    p.add_argument('--reward-scale', type=float, default=10.)
    p.add_argument('--history', choices=('on', 'off'), default='on')
    p.add_argument('--actor-architecture', choices=('shared', 'building_heads'), default='shared')
    p.add_argument('--critic-objective', choices=('scalarized', 'separate'), default='separate')
    p.add_argument('--discomfort-weight', type=float, default=1.)
    p.add_argument('--discomfort-target', type=float, default=.1)
    p.add_argument('--dual-lr', type=float, default=0.,
                   help='根据训练侧约束偏差更新成本/舒适权重；0保留原默认行为')
    p.add_argument('--dual-max', type=float, default=4.)
    p.add_argument('--dual-start-episode', type=int, default=2)
    p.add_argument('--dual-cost-target', type=float, default=.9)
    p.add_argument('--dual-discomfort-target', type=float, default=.1)
    p.add_argument('--init-checkpoint', type=Path)
    p.add_argument('--expected-init-sha256',
                   help='可选：预声明初始化权重SHA256，不匹配时训练前失败')
    p.add_argument('--warm-start-anchor', choices=('on', 'off'), default='on')
    p.add_argument('--selector', choices=('comfort_then_cost', 'piecewise'),
                   default='comfort_then_cost')
    p.add_argument('--selection-anchor-result', type=Path,
                   help='分段评分选点的已登记训练侧Anchor；不得用Online结果选点')
    p.add_argument('--behavior-kl-penalty', type=float, default=0.)
    p.add_argument('--warmup-policy', choices=('uniform', 'anchor_epsilon_greedy'), default='uniform')
    p.add_argument('--optimizer-updates-per-step', type=int, choices=(1, 2), default=2)
    p.add_argument('--learning-starts', type=int, default=719,
                   help='回放池达到该条数后才更新；默认保留历史 719 步 warm-up')
    p.add_argument('--train-steps', type=int, default=0)
    p.add_argument('--eval-steps', type=int, default=0)
    p.add_argument('--simulation-start-time-step', type=int)
    p.add_argument('--evaluation-start-time-step', type=int)
    p.add_argument('--train-task-id')
    p.add_argument('--checkpoint', type=Path)
    p.add_argument('--frozen-anchor', choices=('on', 'off'), default='off',
                   help='只评估预声明指纹的固定 Anchor，不训练、不接受其它模型来源')
    p.add_argument('--anchor-result', type=Path)
    p.add_argument('--score-alpha', type=float, default=1.)
    return p


def resolve_initialization(args):
    """Identify the actual starting weights, before creating training artifacts."""
    if args.warm_start_anchor == 'off':
        if (args.init_checkpoint or args.expected_init_sha256 or args.behavior_kl_penalty
                or args.warmup_policy == 'anchor_epsilon_greedy'):
            raise ValueError('关闭初始化时不能同时指定初始化模型、哈希、KL或Anchor预热')
        return dict(initialization_source='random', initialization_checkpoint=None,
                    initialization_checkpoint_sha256=None)
    path = (args.init_checkpoint or FROZEN_ANCHOR_PATH).resolve()
    if not path.is_file():
        raise FileNotFoundError(f'初始化权重不存在: {path}')
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = args.expected_init_sha256
    if expected and (not re.fullmatch(r'[0-9a-fA-F]{64}', expected)
                     or actual != expected.lower()):
        raise ValueError('初始化权重SHA256与预声明不符')
    if args.init_checkpoint is None and actual != FROZEN_ANCHOR_SHA256:
        raise ValueError('默认初始化Anchor指纹不匹配')
    return dict(initialization_source='explicit_checkpoint' if args.init_checkpoint else 'frozen_anchor',
                initialization_checkpoint=str(path), initialization_checkpoint_sha256=actual)


def resolve_selection_anchor(args):
    if args.selector != 'piecewise':
        if args.selection_anchor_result:
            raise ValueError('只有分段评分选点使用selection-anchor-result')
        return None
    if not args.selection_anchor_result:
        raise ValueError('分段评分选点必须预声明selection-anchor-result')
    from evaluation_contract import DEFAULT_ANCHOR_REGISTRY, load_anchor, file_sha256
    path = args.selection_anchor_result.resolve()
    result = json.loads(path.read_text(encoding='utf-8-sig'))
    registry = os.environ.get('CITYLEARN_ANCHOR_REGISTRY') or DEFAULT_ANCHOR_REGISTRY
    anchor = load_anchor(registry, result['protocol'])
    if anchor is None or file_sha256(path) != anchor['anchor_result_sha256']:
        raise ValueError('选点Anchor必须是预先冻结登记的结果')
    return anchor


def resolve_evaluation_model(args, task_root):
    """Exactly one source; the reference policy cannot be replaced by a file path."""
    frozen = args.frozen_anchor == 'on'
    if sum((frozen, bool(args.train_task_id), args.checkpoint is not None)) != 1:
        raise ValueError('评估必须且只能选择一个模型来源：训练任务、checkpoint 或固定 Anchor')
    if frozen:
        model = FROZEN_ANCHOR_PATH.resolve()
        if not model.is_file():
            raise FileNotFoundError('固定 Anchor 权重缺失')
        if hashlib.sha256(model.read_bytes()).hexdigest() != FROZEN_ANCHOR_SHA256:
            raise ValueError('固定 Anchor SHA256 不匹配，拒绝替换基准')
        return model
    if args.train_task_id:
        return resolve_checkpoint(task_root, args.train_task_id)
    if not args.checkpoint.is_file():
        raise FileNotFoundError(f'评估模型不存在: {args.checkpoint}')
    return args.checkpoint.resolve()


def main(mode):
    # 平台编排层：验证输入 -> 冻结配置 -> 启动实际学习/推理子进程 -> 发布统一产物。
    # 此处的mode决定训练还是评估；不要把后面的KPI导出误认为梯度学习。
    args = parser(mode).parse_args()
    runtime = inspect_runtime()
    if mode == 'train' and args.frozen_anchor == 'on':
        raise ValueError('固定 Anchor 只用于评估；继续训练请使用 warm-start-anchor')
    if args.train_epochs < 1 or not 0 < args.discomfort_target <= .1:
        raise ValueError('训练轮数必须为正，不适阈值必须在 (0, 0.1]')
    if (args.learning_starts < 1 or not math.isfinite(args.actor_lr) or args.actor_lr <= 0
            or not math.isfinite(args.critic_lr) or args.critic_lr <= 0
            or not 0 <= args.discount <= 1 or not 0 < args.tau <= 1
            or not math.isfinite(args.reward_scale) or args.reward_scale <= 0
            or not math.isfinite(args.score_alpha) or args.score_alpha < 0
            or not math.isfinite(args.behavior_kl_penalty) or args.behavior_kl_penalty < 0):
        raise ValueError('训练率、折扣、软更新或奖励尺度参数无效')
    if (not math.isfinite(args.dual_lr) or args.dual_lr < 0
            or not math.isfinite(args.dual_max) or args.dual_max <= 0
            or args.dual_start_episode < 1
            or not 0 < args.dual_cost_target <= .9
            or not 0 < args.dual_discomfort_target <= .1):
        raise ValueError('动态约束参数无效：学习率非负、权重上限为正、起始轮次至少1，目标成本在(0,.9]、不适在(0,.1]')
    initialization = resolve_initialization(args) if mode == 'train' else {}
    selection_anchor = resolve_selection_anchor(args) if mode == 'train' else None
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'runtime_preflight.json', runtime)
    training = resolve_dataset(args.train_schema)
    schema = json.loads((training / 'schema.json').read_text(encoding='utf-8'))
    training_window = validate_window(schema, args.simulation_start_time_step, args.train_steps)
    env, baseline = prepare_environment(training, training_window)
    if mode == 'train' and args.control_profile == HISTORICAL_PROFILE:
        # Fixed Local-only regression; Online evaluation never informs training.
        local = resolve_dataset(DEFAULT_TRAIN)
        if digest(local) != LOCAL_SHA256:
            raise ValueError('Historical AAC preflight requires the pinned Local dataset')
        preflight = output / 'preflight'
        preflight.mkdir(parents=True, exist_ok=True)
        destination = preflight / 'local_anchor.json'
        if hashlib.sha256(FROZEN_ANCHOR_PATH.read_bytes()).hexdigest() != FROZEN_ANCHOR_SHA256:
            raise ValueError('Historical AAC preflight checkpoint hash mismatch')
        command = [sys.executable, str(CORE), '--evaluate', str(FROZEN_ANCHOR_PATH),
                   '--eval-output', str(destination), '--evaluation-dataset', str(local),
                   '--expected-evaluation-dataset-sha256', LOCAL_SHA256,
                   '--evaluation-start-time-step', '0', '--evaluation-end-time-step', '719',
                   '--seed', '855', '--control-profile', HISTORICAL_PROFILE]
        subprocess.run(command, env=env, check=True)
        reference = json.loads(destination.read_text(encoding='utf-8'))
        validate_local_regression(reference)
        write_json(preflight / 'validation.json', dict(
            status='passed', dataset='Local', seed=855, transitions=719,
            checkpoint_sha256=reference['checkpoint_sha256'],
            per_building=reference['per_building'], mechanism=reference['mechanism']))
        print('AAC runtime and Local historical regression preflight passed', flush=True)
    snapshot = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    snapshot.update(algorithm='AACMADRL', mode=mode, device='cpu', torch_threads=1,
                    training_dataset_path=str(training), training_dataset_sha256=env['AACMADRL_DATA_SHA256'],
                    reward_baseline_costs=baseline,
                    reward_baseline_method=env['AACMADRL_BASELINE_METHOD'],
                    core_sha256=hashlib.sha256(CORE.read_bytes()).hexdigest())
    snapshot.update(initialization)
    if selection_anchor:
        snapshot.update(selection_anchor_id=selection_anchor['anchor_id'],
                        selection_anchor_sha256=selection_anchor['anchor_result_sha256'],
                        selection_alpha=1.)
        write_json(output / 'selection_anchor.json', selection_anchor)
    write_json(output / 'aacmadrl_config.json', snapshot)
    if mode == 'train':
        # 每个任务拥有自己的training目录，避免多个训练相互覆盖。
        # warm-start是从已有权重继续学习，并不意味着新模型仍是固定Anchor。
        run = output / 'training'
        command = [sys.executable, str(CORE), '--output', str(run), '--episodes', str(args.train_epochs),
                   '--batch-size', str(args.train_batch_size), '--seed', str(args.seed),
                   '--actor-lr', str(args.actor_lr), '--actor-architecture', args.actor_architecture,
                   '--critic-lr', str(args.critic_lr), '--discount', str(args.discount),
                   '--tau', str(args.tau), '--reward-scale', str(args.reward_scale),
                   '--critic-objective', args.critic_objective, '--discomfort-weight', str(args.discomfort_weight),
                   '--discomfort-target', str(args.discomfort_target), '--warmup-policy', args.warmup_policy,
                   '--optimizer-updates-per-step', str(args.optimizer_updates_per_step),
                   '--learning-starts', str(args.learning_starts),
                   '--dual-lr', str(args.dual_lr), '--dual-max', str(args.dual_max),
                   '--dual-start-episode', str(args.dual_start_episode),
                   '--dual-cost-target', str(args.dual_cost_target),
                   '--dual-discomfort-target', str(args.dual_discomfort_target),
                   '--simulation-start-time-step', str(training_window[0]),
                   '--simulation-end-time-step', str(training_window[1]), '--no-early-stop', '--comfort-priority']
        command.extend(['--control-profile', args.control_profile])
        if args.history == 'on':
            command.append('--history')
        if args.warm_start_anchor == 'on':
            # Freeze task-owned bytes so later changes to the historical file cannot
            # silently change this run's initialization.
            init_checkpoint = output / 'initialization/model.pt'
            init_checkpoint.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(initialization['initialization_checkpoint'], init_checkpoint)
            if hashlib.sha256(init_checkpoint.read_bytes()).hexdigest() != initialization['initialization_checkpoint_sha256']:
                raise ValueError('初始化权重在冻结期间发生变化')
            command.extend(['--init-checkpoint', str(init_checkpoint), '--behavior-kl-penalty', str(args.behavior_kl_penalty)])
        subprocess.run(command, env=env, check=True)
        # 只依据训练侧Local评估选择检查点，不能用Online测试结果挑最好的一轮。
        # 默认保留旧Cost规则；显式piecewise按预声明Local Anchor和alpha=1选点。
        rows = [json.loads(line) for line in (run / 'experience.jsonl').read_text(encoding='utf-8').splitlines()]
        local_results = None
        if selection_anchor:
            local_results = {}
            for row in rows:
                if row.get('episode', 0) > 0 and row.get('updates', 0) > 0:
                    local = json.loads((run / f"eval_local_{row['episode']:02d}.json").read_text(encoding='utf-8'))
                    local_results[row['episode']] = local['platform_result']
        selected = select_checkpoint(rows, args.discomfort_target, args.selector,
                                     selection_anchor, local_results)
        directory = output / MODEL_DIR
        directory.mkdir(parents=True, exist_ok=True)
        model = directory / 'model.pt'
        shutil.copy2(run / f"checkpoint_{selected['episode']:02d}.pt", model)
        manifest = dict(algorithm='AACMADRL', checkpoint='model.pt',
                        checkpoint_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
                        config=snapshot, selection=selected)
        write_json(directory / 'model_manifest.json', manifest)
        # Standard task progress, separate from RLlib checkpoints.
        write_json(directory / 'train_progress.json', dict(epochs_done=args.train_epochs,
                   train_epochs_target=args.train_epochs, best_score=selected['selection_value'],
                   updated=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   mid_eval_history=rows, selection=selected))
        result = json.loads((run / f"eval_local_{selected['episode']:02d}.json").read_text(encoding='utf-8'))
    else:
        # 固定基准直接加载冻结权重；普通模型仍绑定真实训练任务，不补造训练记录。
        model = resolve_evaluation_model(args, output.parent)
        snapshot['evaluation_model_source'] = ('frozen_anchor' if args.frozen_anchor == 'on'
                                               else 'training_task' if args.train_task_id else 'checkpoint')
        snapshot['frozen_anchor_sha256'] = FROZEN_ANCHOR_SHA256 if args.frozen_anchor == 'on' else None
        # Evaluation must expose the training hyperparameters that produced the
        # checkpoint.  Parser defaults describe this eval invocation only and
        # must not silently overwrite the model's training provenance.
        training_config = {}
        model_manifest = model.parent / 'model_manifest.json'
        if model_manifest.is_file():
            try:
                training_config = json.loads(model_manifest.read_text(encoding='utf-8')).get('config', {})
            except (OSError, ValueError, TypeError):
                training_config = {}
        inherit_training_parameters(snapshot, training_config)
        trained_profile = training_config.get('control_profile', 'none')
        if trained_profile != 'none' and args.control_profile != trained_profile:
            raise ValueError('Evaluation control profile must match the training task')
        snapshot['trained_model_manifest'] = str(model_manifest) if model_manifest.is_file() else None
        write_json(output / 'aacmadrl_config.json', snapshot)
        evaluation = resolve_dataset(args.eval_schema)
        eval_window = validate_window(json.loads((evaluation / 'schema.json').read_text(encoding='utf-8')),
                                      args.evaluation_start_time_step, args.eval_steps)
        destination = output / 'aacmadrl_evaluation.json'
        command = [sys.executable, str(CORE), '--evaluate', str(model), '--eval-output', str(destination),
                   '--evaluation-dataset', str(evaluation), '--expected-evaluation-dataset-sha256', digest(evaluation),
                   '--evaluation-start-time-step', str(eval_window[0]), '--evaluation-end-time-step', str(eval_window[1]),
                   '--seed', str(args.seed)]
        command.extend(['--control-profile', args.control_profile])
        subprocess.run(command, env=env, check=True)
        result = json.loads(destination.read_text(encoding='utf-8'))
    # 同一份真实运行结果产生界面KPI和轨迹，避免图表与日志来自不同任务。
    # export_trace做格式适配；它不能从KPI均值重建没有记录过的动作。
    export_kpis(result, output)
    export_trace(result, output)
    meta = dict(algorithm='AACMADRL', mode=mode, dataset_sha256=result['dataset_sha256'],
                simulation_window=result['simulation_window'], checkpoint_sha256=result['checkpoint_sha256'],
                per_building=result['per_building'], mechanism=result['mechanism'],
                comfort_qualified=all(v['discomfort_proportion'] < args.discomfort_target for v in result['per_building'].values()),
                score_status='missing_anchor', score=None,
                evaluation_action_overrides=result.get('evaluation_action_overrides', {}),
                selection_dataset='predeclared_frozen_anchor' if args.frozen_anchor == 'on' else 'training_only')
    if args.anchor_result:
        from evaluation_contract import load_anchor, file_sha256
        registry = os.environ.get('CITYLEARN_ANCHOR_REGISTRY')
        current = result.get('platform_result')
        anchor = load_anchor(registry, current['protocol']) if registry and current else None
        if anchor is None or file_sha256(args.anchor_result) != anchor['anchor_result_sha256']:
            raise ValueError('anchor-result 必须是预先冻结登记、且与完整协议匹配的场景结果')
        meta.update(score_status='available', score=comparison_score(current, anchor, args.score_alpha),
                    score_sensitivity=[comparison_score(current, anchor, a) for a in (.5, 1., 2.)],
                    anchor_sha256=hashlib.sha256(args.anchor_result.read_bytes()).hexdigest())
    write_json(output / 'evaluation_metadata.json', meta)
    agent_config = {key: snapshot.get(key) for key in (
        'algorithm', 'mode', 'device', 'train_epochs', 'control_profile',
        'train_batch_size', 'seed', 'actor_lr', 'history', 'actor_architecture',
        'critic_objective', 'critic_lr', 'discount', 'tau', 'reward_scale',
        'discomfort_weight', 'discomfort_target',
        'dual_lr', 'dual_max', 'dual_start_episode', 'dual_cost_target', 'dual_discomfort_target',
        'initialization_source', 'initialization_checkpoint', 'initialization_checkpoint_sha256',
        'behavior_kl_penalty', 'selector', 'selection_anchor_id', 'selection_anchor_sha256', 'selection_alpha',
        'warm_start_anchor', 'warmup_policy', 'optimizer_updates_per_step', 'learning_starts',
        'train_steps', 'eval_steps', 'simulation_start_time_step',
        'evaluation_start_time_step', 'score_alpha', 'evaluation_model_source',
        'frozen_anchor', 'frozen_anchor_sha256', 'trained_model_manifest')}
    agent_config['aac_train_schema'] = snapshot.get('train_schema')
    agent_config['aac_eval_schema'] = snapshot.get('eval_schema')
    agent_config.update(training_dataset_sha256=snapshot['training_dataset_sha256'],
                        evaluation_dataset_sha256=result['dataset_sha256'],
                        simulation_window=result['simulation_window'],
                        checkpoint_sha256=result['checkpoint_sha256'],
                        reward_baseline_costs=baseline,
                        comfort_qualified=meta['comfort_qualified'],
                        selection_dataset=meta['selection_dataset'])
    if args.frozen_anchor == 'on':
        agent_config['training_parameters_status'] = 'unknown_for_frozen_checkpoint'
        for key in ('train_epochs', 'train_batch_size', 'actor_lr', 'critic_lr', 'discount',
                    'tau', 'reward_scale', 'critic_objective', 'discomfort_weight',
                    'dual_lr', 'dual_max', 'dual_start_episode', 'dual_cost_target', 'dual_discomfort_target',
                    'initialization_source', 'initialization_checkpoint', 'initialization_checkpoint_sha256',
                    'behavior_kl_penalty', 'selector', 'selection_anchor_id', 'selection_anchor_sha256', 'selection_alpha',
                    'warm_start_anchor', 'warmup_policy', 'optimizer_updates_per_step', 'learning_starts'):
            agent_config[key] = None
    write_json(output / 'agent_config.json', agent_config)
    if result.get('platform_context') and result.get('platform_result'):
        # 清单发布会核对文件哈希、转移覆盖和终止状态，并生成评分/空间/AI资料。
        # 子进程退出0、产物完整、舒适合格、可排名，是四个不同判断。
        from evaluation_contract import finalize_recorded_evaluation
        finalize_recorded_evaluation(
            result['platform_result'], result['platform_context'], output,
            result.get('platform_terminated', False), resolved_parameters=agent_config,
            registry_root=os.environ.get('CITYLEARN_ANCHOR_REGISTRY'))
    print(json.dumps(dict(state='completed', **meta), ensure_ascii=False), flush=True)
    return 0
