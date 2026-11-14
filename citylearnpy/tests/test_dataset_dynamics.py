import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dataset_dynamics import prepare_package, generate_package, sequence_batch

TEMPLATE = Path('E:/citylearn-work/datasets/citylearn_challenge_2023_phase_2_online_evaluation_1')


def test_sequence_alignment_uses_previous_temperature_with_current_weather():
    values = np.arange(40, dtype=np.float32).reshape(20, 2)
    x, y = sequence_batch(values, np.array([3, 19]), 3, 0)
    np.testing.assert_array_equal(x[:, :, 0].numpy(), values[[[0, 1, 2], [16, 17, 18]], 0])
    np.testing.assert_array_equal(x[:, :, 1].numpy(), values[[[1, 2, 3], [17, 18, 19]], 1])
    np.testing.assert_array_equal(y.numpy().ravel(), values[[3, 19], 0])


def package(tmp_path, hours=96):
    schema = json.loads((TEMPLATE / 'schema.json').read_text())
    building = schema['buildings']['Building_1']
    building.pop('dynamics')
    building['type'] = 'citylearn.building.Building'
    schema['buildings'] = {'Building_1': building}
    schema['simulation_end_time_step'] = hours - 1
    schema['central_agent'] = True
    (tmp_path / 'schema.json').write_text(json.dumps(schema))
    (tmp_path / 'manifest.json').write_text(json.dumps({'sources': [{'buildingId': 999}]}))
    for name in ['Building_1.csv', 'weather.csv', 'pricing.csv', 'carbon_intensity.csv']:
        pd.read_csv(TEMPLATE / name).iloc[:hours].to_csv(tmp_path / name, index=False)
    return tmp_path


def test_defaults_preserve_bounds_devices_and_preview_does_not_copy_weights(tmp_path):
    root = package(tmp_path)
    schema = json.loads((root / 'schema.json').read_text())
    schema['buildings']['Building_1'].pop('electrical_storage')
    (root / 'schema.json').write_text(json.dumps(schema))
    result = prepare_package(root, TEMPLATE)
    schema = json.loads((root / 'schema.json').read_text())
    original = json.loads((TEMPLATE / 'schema.json').read_text())
    assert schema['central_agent'] == original['central_agent']
    assert schema['reward_function'] == original['reward_function']
    assert schema['simulation_end_time_step'] == 95
    assert 'electrical_storage' not in schema['buildings']['Building_1']
    assert 'electrical_storage' in schema['buildings']['Building_1']['inactive_actions']
    assert result['modelGenerationRequired']
    assert not list(root.glob('*.pth'))


def test_generated_weights_load_and_do_not_use_template_weights(tmp_path):
    root = package(tmp_path)
    prepare_package(root, TEMPLATE)
    result = generate_package(root, epochs=2)
    assert result['status'] == 'generated'
    from citylearn.citylearn import CityLearnEnv
    env = CityLearnEnv(str(root / 'schema.json'))
    env.reset()
    for _ in range(20):
        env.step([[0., 0., .5]])
    assert env.buildings[0].simulate_dynamics
    manifest = json.loads((root / 'manifest.json').read_text())
    assert manifest['thermalModel'] == 'LSTMDynamics'
    assert manifest['sources'] == [{'buildingId': 999}]
    assert len(manifest['modelAssets']) == 1
    assert 'Building_1.pth' in manifest['files']
    assert (root / 'Building_1.pth').read_bytes() != (TEMPLATE / 'Building_1.pth').read_bytes()


def test_short_or_missing_temperature_fails_without_creating_model(tmp_path):
    root = package(tmp_path, hours=30)
    with pytest.raises(ValueError, match='72'):
        prepare_package(root, TEMPLATE)
    assert not list(root.glob('*.pth'))
    package(root)
    df = pd.read_csv(root / 'Building_1.csv')
    df.loc[5, 'indoor_dry_bulb_temperature'] = float('nan')
    df.to_csv(root / 'Building_1.csv', index=False)
    with pytest.raises(ValueError, match='indoor_dry_bulb_temperature'):
        prepare_package(root, TEMPLATE)
