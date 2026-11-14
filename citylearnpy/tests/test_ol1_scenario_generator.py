import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ol1_scenario_generator import GenerationCancelled, generate, preview, verify_package

TEMPLATE = Path(__file__).resolve().parents[3] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1'


class GeneratorTest(unittest.TestCase):
    def test_managed_package_always_uses_online1_model_and_network_configuration(self):
        prototype = json.loads((TEMPLATE / 'schema.json').read_text())['buildings']['Building_3']
        cfg = {'steps': 24, 'managedBuildings': [
            {'id': 21, 'name': 'Office', 'prototype': 'Building_3', 'devices': {},
             'legacyEquipment': True,
             'definition': {'type': 'citylearn.building.Building',
                            'dynamics': {'type': 'citylearn.dynamics.LSTMDynamics',
                                         'attributes': {'filename': 'uploaded.pth', 'hidden_size': 999}}},
             'modelAsset': {'base64': 'invalid', 'sha256': 'wrong'}}]}
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            generate(TEMPLATE, out, cfg)
            building = json.loads((out / 'schema.json').read_text())['buildings']['Building_1']
            self.assertEqual(building['type'], prototype['type'])
            expected = dict(prototype['dynamics']['attributes'], filename='Building_1.pth')
            self.assertEqual(building['dynamics']['attributes'], expected)
            self.assertEqual((out / 'Building_1.pth').read_bytes(), (TEMPLATE / 'Building_3.pth').read_bytes())

    def test_managed_package_inherits_saved_global_settings_and_outage_configuration(self):
        cfg = {'steps': 24, 'managedBuildings': [
            {'id': 31, 'name': 'Building_1', 'prototype': 'Building_1', 'devices': {},
             'legacyEquipment': True, 'definition': {'power_outage': {
                 'simulate_power_outage': False, 'stochastic_power_outage': False}}}],
            'community': {'schema': {'central_agent': False, 'random_seed': 99}}}
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            generate(TEMPLATE, out, cfg)
            schema = json.loads((out / 'schema.json').read_text())
            self.assertFalse(schema['central_agent'])
            self.assertEqual(schema['random_seed'], 99)
            self.assertFalse(schema['buildings']['Building_1']['power_outage']['simulate_power_outage'])

    def test_managed_buildings_inherit_equipment_and_keep_distinct_prototype_assets(self):
        devices = {'pv': {'type': 'citylearn.energy_model.PV', 'autosize': False,
                          'attributes': {'nominal_power': 7}}}
        cfg = {'steps': 24, 'managedBuildings': [
            {'id': 21, 'name': 'Office', 'prototype': 'Building_3', 'devices': devices},
            {'id': 22, 'name': 'Office 2', 'prototype': 'Building_3', 'devices': devices}],
            'community': {'timezone': 'Asia/Shanghai', 'currency': 'CNY', 'intervalSeconds': 3600}}
        result = preview(TEMPLATE, cfg)
        self.assertEqual(result['buildingCount'], 2)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            generate(TEMPLATE, out, cfg)
            schema = json.loads((out / 'schema.json').read_text())
            self.assertEqual(len(schema['buildings']), 2)
            for building in schema['buildings'].values():
                self.assertEqual(building['pv']['attributes']['nominal_power'], 7)
                self.assertNotIn('electrical_storage', building)
                self.assertTrue((out / building['energy_simulation']).is_file())
                self.assertEqual((out / building['dynamics']['attributes']['filename']).read_bytes(),
                                 (TEMPLATE / 'Building_3.pth').read_bytes())
            self.assertEqual(verify_package(out)['configuration']['community']['currency'], 'CNY')

    def test_aligned_window_preserves_history_models_and_source(self):
        before = hashlib.sha256((TEMPLATE / 'Building_1.csv').read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            manifest = generate(TEMPLATE, out, {'startStep': 24, 'steps': 48, 'buildings': ['Building_1']})
            schema = json.loads((out / 'schema.json').read_text())
            self.assertEqual(schema['simulation_start_time_step'], 0)
            self.assertEqual(schema['simulation_end_time_step'], 71)
            self.assertEqual(manifest['scoreStartStep'], 24)
            self.assertEqual(manifest['scoreSteps'], 48)
            self.assertEqual((out / 'Building_1.csv').read_bytes(), b''.join((TEMPLATE / 'Building_1.csv').read_bytes().splitlines(keepends=True)[:73]))
            self.assertEqual((out / 'Building_1.pth').read_bytes(), (TEMPLATE / 'Building_1.pth').read_bytes())
            self.assertEqual(list(schema['buildings']), ['Building_1'])
            self.assertEqual(hashlib.sha256((TEMPLATE / 'Building_1.csv').read_bytes()).hexdigest(), before)

    def test_reproducible_transform_and_device_scaling(self):
        with tempfile.TemporaryDirectory() as temporary:
            cfg = {'startStep': 0, 'steps': 48, 'loadMultiplier': 1.1, 'pvMultiplier': 2, 'batteryCapacity': 8}
            a, b = Path(temporary) / 'a', Path(temporary) / 'b'
            ma, mb = generate(TEMPLATE, a, cfg), generate(TEMPLATE, b, cfg)
            self.assertEqual(ma['contentHash'], mb['contentHash'])
            with (a / 'Building_1.csv').open() as stream:
                row = next(csv.DictReader(stream))
            self.assertAlmostEqual(float(row['non_shiftable_load']), 0.39189612)
            self.assertEqual(json.loads((a / 'schema.json').read_text())['buildings']['Building_1']['electrical_storage']['attributes']['capacity'], 8)

    def test_invalid_config_leaves_no_release(self):
        cases = [{'steps': 99999}, {'startStep': -1}, {'loadMultiplier': float('nan')}, {'buildings': ['../bad']}, {'steps': 1}, {'unexpected': 1}, {'steps': 2.5}]
        with tempfile.TemporaryDirectory() as temporary:
            for i, cfg in enumerate(cases):
                out = Path(temporary) / str(i)
                with self.assertRaises(ValueError):
                    generate(TEMPLATE, out, cfg)
                self.assertFalse(out.exists())

    def test_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileExistsError):
                generate(TEMPLATE, Path(temporary), {})

    def test_preview_describes_source_window_without_writing(self):
        result = preview(TEMPLATE, {'startStep': 24, 'steps': 48})
        self.assertEqual(result['historySteps'], 24)
        self.assertEqual(result['timeSteps'], 72)
        self.assertEqual(result['scoreSteps'], 48)
        self.assertEqual(result['sourceMode'], 'synthetic_ol1')
        self.assertEqual(len(result['curves']['Building_1']), 48)
        self.assertGreater(result['curves']['Building_1'][0]['sourceLoad'], 0)

    def test_fixed_outage_uses_source_steps_and_retains_calendar(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            generate(TEMPLATE, out, {'startStep': 24, 'steps': 48, 'outageMode': 'fixed', 'outageEvents': [{'startStep': 30, 'steps': 2}]})
            with (out / 'Building_1.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([int(float(r['power_outage'])) for r in rows[29:33]], [0, 1, 1, 0])
            self.assertEqual(rows[24]['hour'], '1')
            schema = json.loads((out / 'schema.json').read_text())
            self.assertFalse(schema['buildings']['Building_1']['power_outage']['stochastic_power_outage'])

    def test_manifest_detects_mutated_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            generate(TEMPLATE, out, {'steps': 48})
            self.assertEqual(verify_package(out)['timeSteps'], 48)
            with (out / 'Building_1.csv').open('a') as stream:
                stream.write('bad\n')
            with self.assertRaises(ValueError):
                verify_package(out)

    def test_manifest_cannot_claim_unperformed_runtime_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            manifest = generate(TEMPLATE, out, {'steps': 48})
            manifest['readyForEvaluation'] = True
            manifest['runtimeValidation'] = 'passed'
            (out / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                verify_package(out)

    def test_cancelled_generation_cleans_staging_and_never_publishes(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            with self.assertRaises(GenerationCancelled):
                generate(TEMPLATE, out, {'steps': 48}, cancelled=lambda: True)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_transforms_do_not_rewrite_model_weather_or_pv_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            generate(TEMPLATE, out, {'steps': 48, 'pvMultiplier': 1.5, 'dhwMultiplier': 1.1, 'outageMode': 'off'})
            self.assertEqual((out / 'weather.csv').read_bytes(), b''.join((TEMPLATE / 'weather.csv').read_bytes().splitlines(keepends=True)[:49]))
            with (out / 'Building_1.csv').open() as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row['solar_generation'], '0.0')
            self.assertAlmostEqual(float(row['dhw_demand']), 0.0613035247)
            schema = json.loads((out / 'schema.json').read_text())
            self.assertAlmostEqual(schema['buildings']['Building_1']['pv']['attributes']['nominal_power'], 3.6)
            self.assertFalse(schema['buildings']['Building_1']['power_outage']['simulate_power_outage'])


if __name__ == '__main__':
    unittest.main()
