"""Compatibility checks for checkpoints learned in the Phase 2 runtime."""
import hashlib
from importlib.metadata import version
import math
from pathlib import Path
import sys

EXPECTED_LOCAL = {
    'Building_1': dict(cost_total=.7183273156887241,
                       discomfort_proportion=.08695652173913043),
    'Building_2': dict(cost_total=.8832162801792699,
                       discomfort_proportion=.08022388059701492),
    'Building_3': dict(cost_total=.751805417057175,
                       discomfort_proportion=.04326123128119801),
}
LOCAL_SHA256 = 'ebaf5a18299d759bd9a369680199d40c4451aa9c9af523cf4e97e31a374ab567'
ANCHOR_SHA256 = '3d9ebd7402c5ca8e3d0c8ebec2ccbc3ec853855c5a902349b0f30fa2f94402b1'
TRAINING_PARAMETERS = (
    'train_epochs', 'history', 'actor_lr', 'critic_lr', 'discount', 'tau',
    'reward_scale', 'actor_architecture', 'critic_objective', 'train_batch_size',
    'learning_starts', 'optimizer_updates_per_step', 'dual_lr', 'dual_max',
    'dual_start_episode', 'dual_cost_target', 'dual_discomfort_target',
    'initialization_source', 'initialization_checkpoint', 'initialization_checkpoint_sha256',
    'behavior_kl_penalty', 'warm_start_anchor', 'warmup_policy',
    'selector', 'selection_anchor_id', 'selection_anchor_sha256', 'selection_alpha')


def validate_runtime_contract(citylearn_version, step_order):
    if citylearn_version != '2.3.1' or step_order != 'advance_then_apply':
        raise ValueError(
            f'AAC runtime incompatible: CityLearn={citylearn_version}, step={step_order}; '
            'require CityLearn 2.3.1 / advance_then_apply. '
            'Set CITYLEARN_AAC_PYTHON to envs/aac_madrl/Scripts/python.exe.')


def inspect_runtime():
    import citylearn
    from citylearn.citylearn import CityLearnEnv
    from assessment_trace import transition_timing
    runtime_version = version('citylearn')
    timing = transition_timing(CityLearnEnv)
    validate_runtime_contract(runtime_version, timing)
    package = Path(citylearn.__file__).parent
    return dict(executable=sys.executable, citylearn_version=runtime_version,
                environment_step_order=timing,
                source_sha256={name: hashlib.sha256((package / name).read_bytes()).hexdigest()
                               for name in ('citylearn.py', 'building.py', 'energy_model.py',
                                            'dynamics.py', 'reward_function.py')},
                status='passed')


def validate_local_regression(result):
    if (result.get('dataset_sha256') != LOCAL_SHA256
            or result.get('checkpoint_sha256') != ANCHOR_SHA256
            or result.get('simulation_window') != [0, 719]
            or result.get('transitions') != 719):
        raise ValueError('AAC Local regression dataset/checkpoint/coverage mismatch')
    actual = result.get('per_building', {})
    if set(actual) != set(EXPECTED_LOCAL):
        raise ValueError('AAC Local regression building mismatch')
    for building, expected in EXPECTED_LOCAL.items():
        for key, reference in expected.items():
            value = actual[building].get(key)
            if (value is None or not math.isfinite(value)
                    or not math.isclose(value, reference, rel_tol=1.e-6, abs_tol=1.e-8)):
                raise ValueError(f'AAC Local regression mismatch: {building}.{key}={value}, expected {reference}')
    meters = result.get('mechanism', {})
    if set(meters) != set(EXPECTED_LOCAL):
        raise ValueError('AAC post-action feedback missing')
    for building, values in meters.items():
        cooling = values.get('cooling_kwh')
        if cooling is None or not math.isfinite(cooling) or cooling <= 0:
            raise ValueError(f'AAC post-action cooling feedback invalid: {building}')


def inherit_training_parameters(evaluation, training):
    for key in TRAINING_PARAMETERS:
        if key in training:
            evaluation[key] = training[key]
