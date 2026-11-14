import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from community_assessment import run_case
from aacmadrl.task import export_trace
from assessment_trace import AssessmentTrace, settled_energy
from types import SimpleNamespace


class AssessmentDashboardTest(unittest.TestCase):
    def test_energy_uses_executed_index_instead_of_unsettled_next_state(self):
        building = SimpleNamespace(time_step=1, active_actions=['electrical_storage'],
            observations=lambda **kwargs: {'net_electricity_consumption': 0., 'electrical_storage_soc': .8},
            net_electricity_consumption=[2.5, 0.], solar_generation=[-.4, -.6], non_shiftable_load=[1., 2.],
            electrical_storage=SimpleNamespace(electricity_consumption=[.3, 0.], soc=[.6, .8]))
        trace = AssessmentTrace(SimpleNamespace(buildings=[building]), {'simulation_start_time_step': 10}, {'label': 'Recorded'})
        trace.record([{'net_electricity_consumption': 0., 'electrical_storage_soc': .2}], [[.1]], ([], [-2.5], False, False, {}))
        row = trace.energy[0][0]
        self.assertEqual(row['Net Electricity Consumption-kWh'], 2.5)
        self.assertEqual(row['source_step'], 10)
        self.assertEqual(row['electrical_storage_soc'], .6)
        self.assertEqual(trace.steps[0]['buildings'][0]['next_observations']['electrical_storage_soc'], .8)
        self.assertEqual(settled_energy(building)['settled_net'], 2.5)

    def test_aac_audit_exports_dashboard_without_losing_proposed_actions(self):
        row = {'step': 1, 'building': 'Building_1', 'source_timestep_before': 10,
               'source_timestep_after': 11, 'observation_json': json.dumps({'hour': 11, 'indoor_dry_bulb_temperature': 25}),
               'next_observation_json': json.dumps({'indoor_dry_bulb_temperature': 24, 'electrical_storage_soc': .5}),
               'action_json': json.dumps({'dhw_storage': .1, 'electrical_storage': -.2, 'cooling_device': .6}),
               'proposed_action_json': json.dumps([.1, -.4, .8]), 'reward': -.7,
               'net': 1.5, 'solar': .3, 'non_shiftable': .7, 'battery': -.2,
               'settled_net': 2.5, 'settled_solar': .4, 'settled_non_shiftable': .8, 'settled_battery': -.3,
               'environment_info_json': '{}', 'terminated': True, 'truncated': False}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audit = root / 'audit.csv'
            with audit.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(row)); writer.writeheader(); writer.writerow(row)
            export_trace({'audit_log': {'file': str(audit), 'expected_rows': 1}, 'per_building': {'Building_1': {}}}, root)
            self.assertTrue((root / 'decision_trace.json').is_file(), 'AAC audit is not exposed as a decision log')
            payload = json.loads((root / 'decision_trace.json').read_text(encoding='utf-8'))
            entry = payload['steps'][0]['buildings'][0]
            self.assertEqual(entry['actions']['final']['tmp'], .6)
            self.assertEqual(entry['actions']['raw']['tmp'], .8)
            self.assertEqual(entry['observations']['indoor_dry_bulb_temperature'], 25)
            self.assertTrue((root / 'exported_data_building_1_ep0.csv').is_file())
            with (root / 'exported_data_building_1_ep0.csv').open(newline='', encoding='utf-8') as stream:
                saved = next(csv.DictReader(stream))
            self.assertEqual(saved['source_step'], '10')
            self.assertEqual(float(saved['Net Electricity Consumption-kWh']), 2.5)

    def test_each_policy_exports_its_own_real_transitions_and_energy(self):
        template = Path(__file__).resolve().parents[3] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1'
        schema = json.loads((template / 'schema.json').read_text())
        schema.update(root_directory=str(template), simulation_end_time_step=7, episode_time_steps=None)
        with tempfile.TemporaryDirectory() as temporary:
            for case in ({'id': 'no_control', 'label': 'NoControl'},
                         {'id': 'basic_rbc', 'label': 'BasicRBC'},
                         {'id': 'feedback_balanced', 'label': 'Feedback', 'coolingMargin': 0},
                         {'id': 'chesca', 'label': 'CHESCA'}):
                with self.subTest(policy=case['id']):
                    result = run_case(copy.deepcopy(schema), case, lambda *args: None, Path(temporary))
                    self.assertEqual(result['status'], 'succeeded')
                    root = Path(temporary) / 'cases' / case['id']
                    self.assertTrue((root / 'decision_trace.json').is_file(), 'missing decision log')
                    log = json.loads((root / 'decision_trace.json').read_text(encoding='utf-8'))
                    self.assertEqual(len(log['steps']), 7)
                    entry = log['steps'][0]['buildings'][0]
                    self.assertTrue(entry['narrative_lines'])
                    if case['id'] != 'chesca':
                        self.assertIn('observations', entry)
                        self.assertIn('next_observations', entry)
                        self.assertIn('reward', log['steps'][0])
                    with (root / 'exported_data_building_1_ep0.csv').open(newline='', encoding='utf-8') as stream:
                        rows = list(csv.DictReader(stream))
                    self.assertEqual(len(rows), 7)
                    self.assertIn('Net Electricity Consumption-kWh', rows[0])
                    self.assertIn('timestamp', rows[0])
                    cost = sum(max(float(row['Net Electricity Consumption-kWh']) * float(row['electricity_pricing']), 0) for row in rows)
                    self.assertAlmostEqual(cost, result['diagnostics']['buildings'][0]['positiveCost'], places=5)


if __name__ == '__main__':
    unittest.main()
