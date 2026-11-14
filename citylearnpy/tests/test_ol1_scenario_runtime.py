import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch
from citylearn.citylearn import CityLearnEnv

from community_assessment import run_case, score_window_metrics
from ol1_scenario_generator import GenerationCancelled, generate, runtime_validate

TEMPLATE = Path(__file__).resolve().parents[3] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1'


def rollout(schema, control=None):
    env = CityLearnEnv(copy.deepcopy(schema))
    try:
        obs, _ = env.reset()
        states = []
        while not env.terminated:
            actions = [[v for _ in env.buildings for v in (0, 0, 0)]] if control is None else [[v for _ in env.buildings for v in (0, control[0], control[1])]]
            obs, _, _, _, _ = env.step(actions)
            step = max(0, env.time_step - 1)
            states.append([value for building in env.buildings for value in (building.net_electricity_consumption[step], building.indoor_dry_bulb_temperature[step], building.electrical_storage.soc[step])])
        return np.asarray(states)
    finally:
        env.close()


class RuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)

    def test_default_derivation_matches_source_rollout(self):
        original = json.loads((TEMPLATE / 'schema.json').read_text())
        original['root_directory'] = str(TEMPLATE)
        original['simulation_end_time_step'] = 71
        expected = rollout(original)
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            generate(TEMPLATE, out, {'steps': 72})
            actual_schema = json.loads((out / 'schema.json').read_text())
            actual_schema['root_directory'] = str(out)
            np.testing.assert_allclose(rollout(actual_schema), expected, rtol=1e-6, atol=1e-6)

    def test_score_window_metrics_use_half_open_source_steps_only(self):
        from types import SimpleNamespace
        from citylearn.cost_function import CostFunction
        building = SimpleNamespace(
            name='Building_1',
            net_electricity_consumption_cost=np.array([100., 100., 2., 3., 100.]),
            net_electricity_consumption_cost_without_storage_and_partial_load=np.array([100., 100., 4., 6., 100.]),
            indoor_dry_bulb_temperature=np.array([50., 50., 26., 31., 50.]),
            indoor_dry_bulb_temperature_cooling_set_point=np.array([24., 24., 24., 24., 24.]),
            indoor_dry_bulb_temperature_heating_set_point=np.array([20., 20., 20., 20., 20.]),
            comfort_band=1.0,
            occupant_count=np.array([1, 1, 1, 1, 1]),
        )
        source_rows = [{'level': level, 'name': name, 'cost_function': metric, 'value': 1.}
                       for level, name in [('building', 'Building_1'), ('district', 'District')]
                       for metric in ('cost_total', 'discomfort_proportion')]
        rows = score_window_metrics([building], source_rows, 2, 4)
        by_metric = {(row['name'], row['cost_function']): row['value'] for row in rows}
        expected_cost = CostFunction.cost([2., 3.])[-1] / CostFunction.cost([4., 6.])[-1]
        expected_discomfort = CostFunction.discomfort(
            building.indoor_dry_bulb_temperature[2:4],
            building.indoor_dry_bulb_temperature_cooling_set_point[2:4],
            building.indoor_dry_bulb_temperature_heating_set_point[2:4],
            band=building.comfort_band,
            occupant_count=building.occupant_count[2:4])[0][-1]
        self.assertEqual(by_metric['Building_1', 'cost_total'], expected_cost)
        self.assertEqual(by_metric['Building_1', 'discomfort_proportion'], expected_discomfort)
        self.assertEqual(by_metric['District', 'cost_total'], expected_cost)
        self.assertEqual(by_metric['District', 'discomfort_proportion'], expected_discomfort)
        self.assertEqual(rows[0]['evaluationScope'], 'score_window')

    def test_policies_share_baseline_warmup_state_before_scoring(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / 'release'
            generate(TEMPLATE, package, {'steps': 48})
            schema = json.loads((package / 'schema.json').read_text())
            schema['root_directory'] = str(package)
            progress = lambda *args: None
            baseline = run_case(schema, {'id': 'no_control', 'label': 'NoControl'}, progress, score_window=(24, 48))
            chesca = run_case(schema, {'id': 'chesca', 'label': 'CHESCA', 'parameters': {'tau': 1, 'balance_type': 'C'}},
                              progress, Path(temporary) / 'chesca', (24, 48))
            self.assertEqual(baseline['evaluation']['warmupPolicy'], 'CityLearn BaselineAgent')
            self.assertEqual(chesca['evaluation']['warmupPolicy'], 'CityLearn BaselineAgent')
            self.assertEqual(baseline['evaluation']['scoreStartStateSha256'], chesca['evaluation']['scoreStartStateSha256'])
            trace = json.loads((Path(temporary) / 'chesca/cases/chesca/decision_trace.json').read_text(encoding='utf-8'))
            self.assertEqual(len(trace['steps']), 47)
            self.assertTrue(all(step['control_mode'] == 'common_baseline_warmup' for step in trace['steps'][:24]))
            self.assertTrue(all(step['buildings'][0]['actions']['named'] == {} for step in trace['steps'][:24]))
            self.assertEqual(trace['steps'][24]['step'], 24)

    def test_battery_and_cooling_actions_change_real_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            generate(TEMPLATE, out, {'steps': 48, 'outageMode': 'off'})
            schema = json.loads((out / 'schema.json').read_text())
            schema['root_directory'] = str(out)
            passive = rollout(schema, (0, 0))
            active = rollout(schema, (1, 0.5))
            self.assertGreater(float(np.max(np.abs(active[:, 2] - passive[:, 2]))), 0.1)
            self.assertGreater(float(np.max(np.abs(active[24:, 1] - passive[24:, 1]))), 0.1)
            self.assertGreater(float(np.max(np.abs(active[:, 0] - passive[:, 0]))), 0.1)

    def test_complete_validation_records_runtime_and_transition_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            manifest = generate(TEMPLATE, out, {'steps': 48}, validate_runtime=True)
            self.assertTrue(manifest['readyForEvaluation'])
            report = json.loads((out / 'validation_report.json').read_text())
            self.assertEqual(report['transitions'], 47)
            self.assertEqual(report['actionNames'], ['dhw_storage', 'electrical_storage', 'cooling_device'])
            self.assertEqual(len(report['runtimeCodeHashes']['building.py']), 64)
            self.assertEqual(report['chescaSmokeTest'], 'passed')
            self.assertTrue(manifest['chescaCompatible'])

    def test_cancellation_during_runtime_leaves_no_package(self):
        cancelled = []
        def progress(stage, done, total):
            if stage == 'runtime_validation':
                cancelled.append(True)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(GenerationCancelled):
                generate(TEMPLATE, Path(temporary) / 'release', {'steps': 72}, validate_runtime=True,
                         progress=progress, cancelled=lambda: bool(cancelled))
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_missing_solar_forecast_blocks_chesca_with_specific_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            generate(TEMPLATE, out, {'steps': 24})
            schema = json.loads((out / 'schema.json').read_text())
            schema['observations']['direct_solar_irradiance_predicted_1']['active'] = False
            (out / 'schema.json').write_text(json.dumps(schema), encoding='utf-8')
            report = runtime_validate(out)
            self.assertEqual(report['runtimeValidation'], 'passed')
            self.assertEqual(report['chescaSmokeTest'], 'not_supported')
            self.assertIn('chescaCompatibilityReason', report)
            self.assertIn('direct_solar_irradiance_predicted_6h', report['chescaCompatibilityReason'])

    def test_single_building_can_publish_without_claiming_chesca_compatibility(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'release'
            manifest = generate(TEMPLATE, out, {'steps': 24, 'buildings': ['Building_1']}, validate_runtime=True)
            report = json.loads((out / 'validation_report.json').read_text())
            self.assertTrue(manifest['readyForEvaluation'])
            self.assertEqual(report['runtimeValidation'], 'passed')
            self.assertFalse(manifest['chescaCompatible'])
            self.assertEqual(report['chescaSmokeTest'], 'not_supported')
            self.assertIn('chescaCompatibilityReason', report)


if __name__ == '__main__':
    unittest.main()
