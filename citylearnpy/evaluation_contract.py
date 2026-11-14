"""Task-owned evidence and an explicitly frozen, hash-checked Anchor registry.

This module never borrows another task's files or reconstructs historical facts
from KPI averages. A successful process and complete evaluation evidence are
separate states.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import inspect
import platform


FROZEN_ANCHOR_SHA256 = '3d9ebd7402c5ca8e3d0c8ebec2ccbc3ec853855c5a902349b0f30fa2f94402b1'
DEFAULT_ANCHOR_REGISTRY = Path(__file__).resolve().parent.parent / 'evaluation_registry' / 'anchors'
PHYSICAL_PROTOCOL_FIELDS = (
    'dataset_files_sha256', 'simulation_window', 'seconds_per_time_step',
    'building_ids', 'equipment_sha256', 'initial_state_sha256',
    'evaluator_version', 'cost_definition', 'warmup', 'action_contract',
    'environment_step_order',
    'outage_model_sha256',
)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def protocol_id(protocol):
    raw = json.dumps(protocol, sort_keys=True, ensure_ascii=False,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def physical_protocol(protocol):
    """Return comparison conditions independent of policy information access.

    A NoControl run has no policy-visible observation stream, but it can still
    be a valid physical reference for a controlled run when dataset, window,
    initial state, evaluator, action contract and step order are identical.
    Scoring against a learned Anchor remains stricter and still compares the
    full protocol including ``information_access``.
    """
    protocol = protocol or {}
    selected = {field: protocol[field] for field in PHYSICAL_PROTOCOL_FIELDS
                if field in protocol}
    # Keep legacy/minimal evidence fail-closed.  If it does not declare the
    # current physical fields, compare all declared fields except the one
    # intentionally relaxed policy-access label.
    return selected if set(PHYSICAL_PROTOCOL_FIELDS).issubset(protocol) else {
        key: value for key, value in protocol.items() if key != 'information_access'
    }


def physical_protocol_id(protocol):
    return protocol_id(physical_protocol(protocol))


def find_independent_nocontrol(output, protocol):
    """Find one complete, same-physics NoControl result beside a task.

    Task directories are siblings below the task output root.  Matching is
    deliberately conservative: zero matches or multiple matches are both
    treated as unknown so a stale or arbitrary baseline cannot be selected.
    """
    output = Path(output).resolve()
    parent = output.parent
    if not parent.is_dir():
        return None
    matches = []
    for candidate in sorted(parent.iterdir(), key=lambda item: item.name):
        if not candidate.is_dir() or candidate == output:
            continue
        result_path = candidate / 'evaluation_result.json'
        manifest_path = candidate / 'evaluation_manifest.json'
        if not result_path.is_file() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
            if not isinstance(manifest, dict) or manifest.get('artifact_status') != 'complete':
                continue
            artifacts = manifest.get('artifacts')
            if not isinstance(artifacts, dict) or 'evaluation_result.json' not in artifacts:
                continue
            if not all(isinstance(record, dict) for record in artifacts.values()):
                continue
            if not validate_manifest(manifest, candidate)['valid']:
                continue
            result = json.loads(result_path.read_text(encoding='utf-8-sig'))
            if not isinstance(result, dict) or result.get('algorithm') != 'NoControl':
                continue
            if manifest.get('algorithm') != 'NoControl' or not result.get('task_id'):
                continue
            if not isinstance(result.get('protocol'), dict) or not result['protocol']:
                continue
            if manifest.get('protocol') != result['protocol']:
                continue
            if physical_protocol_id(result.get('protocol')) != physical_protocol_id(protocol):
                continue
            if result.get('task_id') != manifest.get('task_id'):
                continue
            matches.append(result)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return matches[0] if len(matches) == 1 else None


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
                         encoding='utf-8')
    temporary.replace(path)


def validate_manifest(manifest: dict, artifact_root: Path) -> dict:
    """Verify bytes and actual trace coverage, not just a producer's counters."""
    root = Path(artifact_root).resolve()
    errors, warnings = [], []
    artifacts = manifest.get('artifacts', {})
    trace_path = None
    for name, record in artifacts.items():
        relative = PurePosixPath(name.replace('\\', '/'))
        path = (root / name).resolve()
        if relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(root):
            errors.append('unsafe_artifact_path:' + name)
            continue
        if not path.is_file():
            errors.append('missing_artifact:' + name)
            continue
        if file_sha256(path) != record.get('sha256'):
            errors.append('artifact_hash_mismatch:' + name)
        if path.name == 'decision_trace.json':
            trace_path = path
    coverage = manifest.get('coverage', {})
    if not coverage.get('terminated') or coverage.get('truncated'):
        errors.append('incomplete_episode')
    if trace_path is None:
        errors.append('missing_decision_trace')
    else:
        try:
            steps = json.loads(trace_path.read_text(encoding='utf-8-sig'))['steps']
            start, end = manifest['protocol']['simulation_window']
            expected = end - start
            indices = [step['step'] for step in steps]
            if indices != list(range(start, end)):
                errors.append('noncontiguous_trace_steps')
            if len(steps) != expected or coverage.get('recorded_transitions') != expected:
                errors.append('transition_count_mismatch')
            if coverage.get('expected_transitions') != expected:
                errors.append('expected_transition_count_mismatch')
            count = len(manifest['protocol']['building_ids'])
            if any(sorted(entry['building'] for entry in step['buildings']) != list(range(count))
                   for step in steps):
                errors.append('building_coverage_mismatch')
            if any(not all(key in step for key in ('info', 'terminated', 'truncated')) or
                   ('reward' not in step and not all('reward' in entry for entry in step['buildings']))
                   for step in steps):
                errors.append('missing_transition_feedback')
            if any(not all(isinstance(entry.get(key), dict) for key in
                           ('observations', 'next_observations', 'actions'))
                   or not isinstance(entry.get('actions', {}).get('named'), dict)
                   for step in steps for entry in step['buildings']):
                errors.append('missing_building_transition_evidence')
            if steps and not steps[-1].get('terminated'):
                errors.append('trace_terminal_flag_missing')
        except (ValueError, KeyError, TypeError):
            errors.append('malformed_decision_trace')
    if not artifacts:
        errors.append('missing_artifacts')
    return dict(valid=not errors, errors=errors, warnings=warnings, coverage=coverage)


def register_anchor(registry_root, anchor_id, result_path, checkpoint_path,
                    expected_checkpoint_sha256=FROZEN_ANCHOR_SHA256):
    """Explicit registration pins both weights and one scenario's result bytes.

    A different approved Anchor requires passing its predeclared weight digest;
    this is never inferred from whichever checkpoint happened to be available.
    """
    if not re.fullmatch(r'[A-Za-z0-9_-]+', anchor_id or ''):
        raise ValueError('invalid_anchor_id')
    result_path, checkpoint_path = Path(result_path).resolve(), Path(checkpoint_path).resolve()
    if file_sha256(checkpoint_path) != expected_checkpoint_sha256:
        raise ValueError('anchor_checkpoint_hash_mismatch')
    result = json.loads(result_path.read_text(encoding='utf-8-sig'))
    if not result.get('protocol') or not result.get('per_building'):
        raise ValueError('missing_anchor_evidence')
    identity = protocol_id(result['protocol'])
    entry = dict(anchor_id=anchor_id, protocol_id=identity,
                 result_path=str(result_path), result_sha256=file_sha256(result_path),
                 checkpoint_path=str(checkpoint_path),
                 anchor_checkpoint_sha256=expected_checkpoint_sha256)
    destination = Path(registry_root) / (identity + '.json')
    if destination.exists():
        prior = json.loads(destination.read_text(encoding='utf-8'))
        if prior != entry:
            raise ValueError('anchor_protocol_already_frozen')
    write_json(destination, entry)
    return entry


def load_anchor(registry_root, protocol):
    path = Path(registry_root) / (protocol_id(protocol) + '.json')
    if not path.is_file():
        return None
    entry = json.loads(path.read_text(encoding='utf-8'))
    if file_sha256(entry['result_path']) != entry['result_sha256']:
        raise ValueError('anchor_result_hash_mismatch')
    if file_sha256(entry['checkpoint_path']) != entry['anchor_checkpoint_sha256']:
        raise ValueError('anchor_checkpoint_hash_mismatch')
    result = json.loads(Path(entry['result_path']).read_text(encoding='utf-8-sig'))
    if protocol_id(result['protocol']) != protocol_id(protocol):
        raise ValueError('anchor_protocol_mismatch')
    return {**result, 'anchor_id': entry['anchor_id'],
            'anchor_checkpoint_sha256': entry['anchor_checkpoint_sha256'],
            'anchor_result_sha256': entry['result_sha256']}


def capture_runtime_equipment(env):
    """Retain actual initial metadata, removing only per-instance identifiers.

    Zero-sized devices remain visible: their random parameters are evidence,
    even when a later physical audit determines they cannot affect this run.
    """
    from assessment_trace import clean

    def without_uids(value):
        if isinstance(value, dict):
            return {key: without_uids(item) for key, item in value.items() if key != 'uid'}
        if isinstance(value, list):
            return [without_uids(item) for item in value]
        return value

    equipment = {}
    for building in env.buildings:
        metadata = without_uids(clean(building.get_metadata()))
        model = getattr(building, 'stochastic_power_outage_model', None)
        metadata['stochastic_power_outage_model'] = None if model is None else dict(
            model_class=f'{type(model).__module__}.{type(model).__qualname__}',
            **{key: clean(getattr(model, key, None))
               for key in ('random_seed', 'saifi', 'caidi', 'start_time_steps')})
        equipment[building.name] = metadata
    return equipment


def collect_runtime_audit(env, context):
    """Read realized history; never call the outage generator a second time."""
    from assessment_trace import clean
    start = context['protocol']['simulation_window'][0]
    outages = {}
    for building in env.buildings:
        values = clean(building.power_outage_signal)
        steps = list(range(start, start + len(values)))
        outages[building.name] = dict(
            source_steps=steps, values=values, sha256=protocol_id(values),
            outage_source_steps=[step for step, value in zip(steps, values) if value > .5])
    equipment = context.get('runtime_equipment')
    return dict(schema_version=1, scope='runtime_diagnostic_not_ranking_protocol',
                equipment_at_reset=equipment,
                equipment_at_reset_sha256=protocol_id(equipment) if equipment is not None else None,
                outages=outages)


def capture_context(env, information_access=None, warmup='none'):
    """Call immediately after reset, before the first action changes the state.

    Information access must be audited by the caller. None intentionally keeps
    the comparison unrankable instead of assuming a policy never reads future
    values from public environment objects.
    """
    from assessment_trace import clean, transition_timing
    from citylearn.citylearn import CityLearnEnv
    from citylearn.cost_function import CostFunction
    import citylearn
    schema = env.schema
    root = Path(env.root_directory or schema.get('root_directory') or '.').resolve()
    files = {}

    def visit(value):
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str):
            path = Path(value)
            if not path.is_absolute():
                path = root / path
            if path.is_file():
                files[str(path.relative_to(root)) if path.is_relative_to(root) else str(path)] = file_sha256(path)

    # Only selected buildings contribute: another disabled building must not
    # change a dataset fingerprint for this experiment.
    selected = {building.name: schema['buildings'][building.name] for building in env.buildings}
    visit(selected)
    if not files:
        raise ValueError('missing_dataset_files')
    # Use the selected building declarations as the physical equipment
    # fingerprint.  Runtime objects contain randomised sizing/efficiency
    # values and fresh UIDs, so hashing ``building.get_metadata()`` would make
    # two clean constructions of the same schema look incomparable.
    equipment = clean(selected)
    # A few optional devices are represented as either {} or null depending on
    # which controller wrapper created the environment.  Their empty state is
    # equivalent.  Device efficiency is a runtime-derived value and can vary
    # across CityLearn object construction even when the source files and seed
    # are identical, so it is not a protocol identity field.
    initial_excluded = {
        'heating_device_efficiency',
        'electric_vehicles_chargers_dict',
        'washing_machines_dict',
        'washing_machine_electricity_consumption',
    }
    initial_state = {}
    for building in env.buildings:
        observations = building.observations(include_all=True)
        stable = {key: value for key, value in observations.items()
                  if key not in initial_excluded}
        initial_state[building.name] = clean(stable)
    evaluator_hash = hashlib.sha256((
        inspect.getsource(CityLearnEnv.evaluate) + inspect.getsource(CostFunction.cost)
        + inspect.getsource(CostFunction.discomfort)).encode('utf-8')).hexdigest()
    window = [int(env.episode_tracker.episode_start_time_step),
              int(env.episode_tracker.episode_end_time_step)]
    runtime_equipment = capture_runtime_equipment(env)
    protocol = dict(
        dataset_files_sha256=files, simulation_window=window,
        seconds_per_time_step=float(env.seconds_per_time_step),
        building_ids=[building.name for building in env.buildings],
        equipment_sha256=protocol_id(equipment),
        initial_state_sha256=protocol_id(initial_state),
        evaluator_version=evaluator_hash,
        cost_definition='CityLearn native positive-cost ratio; full episode states including terminal; cash=settled transitions',
        information_access=information_access, warmup=warmup,
        action_contract=schema.get('actions'),
        environment_step_order=transition_timing(env),
        outage_model_sha256=protocol_id({
            name: metadata['stochastic_power_outage_model']
            for name, metadata in runtime_equipment.items()}),
    )
    return dict(protocol=protocol, initial_state=initial_state, equipment=equipment,
                runtime_equipment=runtime_equipment,
                runtime_versions=dict(python=platform.python_version(),
                                      citylearn=getattr(citylearn, '__version__', 'unknown')),
                evaluation_sources_sha256={str(Path(inspect.getfile(CityLearnEnv)).name):
                                           file_sha256(inspect.getfile(CityLearnEnv)),
                                           str(Path(inspect.getfile(env.buildings[0].__class__)).name):
                                           file_sha256(inspect.getfile(env.buildings[0].__class__))})


def finalize_evaluation(env, context, output, algorithm, task_id=None, resolved_parameters=None,
                        policy_id=None, registry_root=None):
    """Export unrounded native metrics, transition cash, score and completeness.

    Native Cost includes the states consumed by CityLearn's evaluator. Settled
    bill excludes the final observation, for which no action was executed.
    Both scopes are recorded; neither silently replaces the other.
    """
    output = Path(output)
    result = dict(task_id=task_id or output.name, algorithm=algorithm, policy_id=policy_id,
                  protocol=context['protocol'], per_building=collect_environment_metrics(env))
    context = {**context, 'runtime_audit': collect_runtime_audit(env, context)}
    return finalize_recorded_evaluation(result, context, output, env.terminated,
                                        task_id=task_id, resolved_parameters=resolved_parameters,
                                        registry_root=registry_root)


def collect_environment_metrics(env):
    import numpy as np
    from assessment_trace import clean, transition_timing, settled_index
    timing = transition_timing(env)
    per = {}
    for building in env.buildings:
        bill = np.asarray(building.net_electricity_consumption_cost, dtype=float)
        baseline = np.asarray(building.net_electricity_consumption_cost_without_storage_and_partial_load,
                              dtype=float)
        occupied = np.asarray(building.occupant_count) > 0
        temperature = np.asarray(building.indoor_dry_bulb_temperature, dtype=float)
        band = np.asarray(building.comfort_band, dtype=float)
        cold = temperature < np.asarray(building.indoor_dry_bulb_temperature_heating_set_point) - band
        hot = temperature > np.asarray(building.indoor_dry_bulb_temperature_cooling_set_point) + band
        count = int(occupied.sum())
        numerator, denominator = float(np.maximum(bill, 0).sum()), float(np.maximum(baseline, 0).sum())
        native = numerator / denominator if denominator > 0 and np.isfinite(denominator) else None
        per[building.name] = clean(dict(
            cost_total=native, native_positive_bill=numerator, native_baseline_bill=denominator,
            positive_bill=float(np.maximum(
                bill[1:building.time_step + 1] if timing == 'advance_then_apply'
                else bill[:building.time_step], 0).sum()),
            discomfort_proportion=float((occupied & (cold | hot)).sum() / count) if count else None,
            occupied_samples=count,
            service_diagnostics={'occupied_cold': int((occupied & cold).sum()),
                                 'occupied_hot': int((occupied & hot).sum())},
            terminal_state={'battery_soc': building.electrical_storage.soc[settled_index(building, timing)],
                            'dhw_soc': building.dhw_storage.soc[settled_index(building, timing)]}))
    return per


def finalize_recorded_evaluation(result, context, output, terminated, task_id=None,
                                 resolved_parameters=None, registry_root=None):
    """Publish evidence returned by a worker without rerunning its environment."""
    from assessment_trace import clean
    from evaluation_scoring import compute_score
    from evaluation_headroom import compute_headroom
    from evaluation_advice import build_advice_bundle, select_events
    output = Path(output)
    result = {**result, 'task_id': task_id or output.name}
    if result.get('protocol') != context.get('protocol'):
        raise ValueError('worker_protocol_mismatch')
    per = result['per_building']
    if context.get('runtime_audit') is not None:
        write_json(output / 'runtime_audit.json', context['runtime_audit'])
    write_json(output / 'evaluation_result.json', result)
    try:
        anchor = load_anchor(
            DEFAULT_ANCHOR_REGISTRY if registry_root is None else registry_root,
            context['protocol'])
        score = compute_score(result, anchor)
    except (OSError, ValueError, KeyError, TypeError) as error:
        score = dict(status='unavailable', score=None, rankable=False,
                     reason_codes=['anchor_verification_failed:' + str(error)])
    write_json(output / 'score_result.json', score)
    baseline = find_independent_nocontrol(output, context['protocol'])
    headroom = compute_headroom(result, baseline=baseline)
    write_json(output / 'headroom_result.json', headroom)
    artifacts = {}
    for path in output.rglob('*'):
        if path.is_file() and (path.suffix.lower() in ('.json', '.csv', '.gz', '.npz')) \
                and path.name != 'evaluation_manifest.json':
            artifacts[path.relative_to(output).as_posix()] = dict(sha256=file_sha256(path),
                                                                 bytes=path.stat().st_size)
    trace_path = next((output / name for name in artifacts
                       if Path(name).name == 'decision_trace.json'), None)
    steps = json.loads(trace_path.read_text(encoding='utf-8-sig')).get('steps', []) if trace_path else []
    window = context['protocol']['simulation_window']
    manifest = dict(schema_version=1, task_id=result['task_id'], algorithm=result['algorithm'], mode='evaluation',
                    protocol=context['protocol'], protocol_id=protocol_id(context['protocol']),
                    physical_protocol_id=physical_protocol_id(context['protocol']),
                    runtime_versions=context['runtime_versions'],
                    evaluation_sources_sha256=context['evaluation_sources_sha256'],
                    resolved_parameters=clean(resolved_parameters or {}),
                    policy_id=result.get('policy_id'), artifacts=artifacts,
                    coverage=dict(expected_transitions=window[1] - window[0],
                                  recorded_transitions=len(steps), terminated=bool(terminated),
                                  truncated=bool(steps[-1].get('truncated')) if steps else False))
    report = validate_manifest(manifest, output)
    manifest.update(execution_status='succeeded' if terminated else 'incomplete',
                    artifact_status='complete' if report['valid'] else 'incomplete',
                    validation=report)
    # Do not include the bundle's own hash inside itself. The final manifest
    # indexes the bundle after writing it, avoiding a circular hash dependency.
    bundle_manifest = {**manifest, 'per_building': per}
    bundle = build_advice_bundle(bundle_manifest, score, headroom,
                                 select_events(steps, context['protocol']['building_ids']))
    bundle_path = output / 'ai_analysis_bundle.json'
    write_json(bundle_path, bundle)
    manifest['artifacts'][bundle_path.name] = dict(sha256=file_sha256(bundle_path),
                                                  bytes=bundle_path.stat().st_size)
    write_json(output / 'evaluation_manifest.json', manifest)
    return manifest
