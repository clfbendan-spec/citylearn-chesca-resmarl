import unittest
from types import SimpleNamespace
from assessment_trace import settled_energy


class TransitionTimingTest(unittest.TestCase):
    def test_aac_settled_outage_uses_observation_for_executable_step_order(self):
        import json
        import tempfile
        from pathlib import Path
        from assessment_trace import export_aac_dashboard
        for timing, expected in [('apply_then_advance', 1), ('advance_then_apply', 0)]:
            with self.subTest(timing=timing), tempfile.TemporaryDirectory() as temporary:
                export_aac_dashboard([dict(
                    building='Building_1', step=1, source_timestep_before=0,
                    source_timestep_after=1, settled_net=0,
                    environment_step_order=timing,
                    observation_json=json.dumps({'power_outage': 1}),
                    next_observation_json=json.dumps({'power_outage': 0}),
                )], temporary)
                trace = json.loads((Path(temporary) / 'decision_trace.json').read_text(encoding='utf-8'))
                self.assertEqual(trace['steps'][0]['buildings'][0]['settled'].get('power_outage'), expected)

    def test_step_csv_uses_settled_outage_history_at_event_boundary(self):
        from utils.report import building_step_snapshot
        building = SimpleNamespace(
            power_outage=False, power_outage_signal=[0., 1., 0.],
            active_actions=[])
        row = building_step_snapshot(
            building, time_step=2, step_count=1, building_id='Building_1')
        self.assertEqual(row['power_outage'], 1.)

    def test_generated_outage_is_not_replaced_by_zero_dataset_column(self):
        from pathlib import Path
        from citylearn.citylearn import CityLearnEnv
        from citylearn.agents.base import BaselineAgent
        from assessment_trace import AssessmentTrace
        dataset = Path(__file__).resolve().parents[3] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1/schema.json'
        env = CityLearnEnv(str(dataset), central_agent=True, random_seed=2023)
        try:
            observations, _ = env.reset()
            agent = BaselineAgent(env)
            trace = AssessmentTrace(env, {'simulation_start_time_step': 0},
                                    {'label': 'NoControl'})
            found = False
            while not env.terminated:
                before = trace.before()
                actions = agent.predict(observations)
                transition = env.step(actions)
                observations = transition[0]
                if before[0]['power_outage']:
                    self.assertEqual(
                        float(env.buildings[0].energy_simulation.power_outage[env.time_step - 1]), 0.)
                    trace.record(before, actions, transition, 'no_control')
                    self.assertEqual(trace.energy[0][-1]['power_outage'], 1.)
                    self.assertEqual(trace.steps[-1]['buildings'][0]['settled']['power_outage'], 1.)
                    found = True
                    break
            self.assertTrue(found, 'Fixture must exercise a real generated outage')
        finally:
            env.close()

    def test_information_regimes_are_explicit_and_not_silently_comparable(self):
        from evaluation_scoring import PROTOCOL_FIELDS
        self.assertIn('information_access', PROTOCOL_FIELDS)
        self.assertIn('environment_step_order', PROTOCOL_FIELDS)

    def test_advance_first_reads_newly_settled_index_instead_of_previous_step(self):
        building = SimpleNamespace(
            time_step=1, net_electricity_consumption=[2., 9.],
            solar_generation=[-.1, -.4], non_shiftable_load=[1., 3.],
            electrical_storage=SimpleNamespace(electricity_consumption=[.3, -.8]))
        row = settled_energy(building, timing='advance_then_apply')
        self.assertEqual(row['settled_net'], 9.)
        self.assertEqual(row['settled_battery'], -.8)

    def test_installed_step_order_is_detected_from_executable_method(self):
        from citylearn.citylearn import CityLearnEnv
        from assessment_trace import transition_timing
        self.assertEqual(transition_timing(CityLearnEnv), 'apply_then_advance')


if __name__ == '__main__':
    unittest.main()
