import json
from pathlib import Path
import tempfile
import unittest

import numpy as np


class DistrictEvaluationEvidenceTest(unittest.TestCase):
    def test_direct_evaluation_script_rejects_invalid_window_without_import_failure(self):
        import os
        import subprocess
        import sys
        script = Path(__file__).resolve().parents[1] / 'district_marl/district_eval.py'
        environment = dict(os.environ, PYTHONHASHSEED='0')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'must-not-exist'
            result = subprocess.run(
                [sys.executable, str(script), '--steps', '-1',
                 '--output-dir', str(output)],
                cwd=directory, env=environment, capture_output=True, timeout=90)
            self.assertEqual(result.returncode, 2, result.stderr.decode('utf-8', errors='replace')[-1500:])
            self.assertNotIn(b'ImportError', result.stderr)
            self.assertFalse(output.exists())

    def test_misspelled_task_parameters_cannot_be_silently_ignored(self):
        from district_marl.district_train import parse_args as train_args
        from district_marl.district_eval import parse_args as eval_args
        for parse in (train_args, eval_args):
            with self.subTest(parser=parse.__module__):
                with self.assertRaises(SystemExit) as raised:
                    parse(['--peak-wieght', '77'])
                self.assertEqual(raised.exception.code, 2)

    def test_invalid_sac_configuration_is_rejected_instead_of_using_defaults(self):
        from district_marl.district_train import parse_args
        for flag, value in (
                ('--sac-tau', 'nan'), ('--sac-tau', '0'), ('--sac-tau', '1.1'),
                ('--sac-n-step', '0'), ('--replay-buffer-cap', '-1'),
                ('--peak-weight', 'inf'), ('--team-share', '1.1'),
                ('--attribution', '-.1'), ('--peak-anchored', 'nan'),
                ('--train-epochs', '0'), ('--eval-every', '0')):
            with self.subTest(flag=flag, value=value):
                with self.assertRaises(SystemExit) as raised:
                    parse_args([flag, value])
                self.assertEqual(raised.exception.code, 2)

    def test_reference_action_reports_next_index_dataset_ground_truth(self):
        from types import SimpleNamespace
        from district_marl.district_env import DistrictContextRLlibEnv
        env = DistrictContextRLlibEnv.__new__(DistrictContextRLlibEnv)
        building = SimpleNamespace(
            time_step=0,
            energy_simulation=SimpleNamespace(
                cooling_demand_without_control=np.array([1., 2., 3.])),
            weather=SimpleNamespace(outdoor_dry_bulb_temperature=np.array([25., 26., 27.])),
            cooling_device=SimpleNamespace(
                nominal_power=10., get_cop=lambda *args, **kwargs: np.array([1.])))
        env._ctx_buildings = [building]
        env._cool_centered = True
        env.enable_information_audit()
        first = env._cool_a_ref_now(0)
        building.energy_simulation.cooling_demand_without_control[1] = 8.
        second = env._cool_a_ref_now(0)
        # Same decision time, same policy output; next-index ideal data changes the mapping.
        self.assertAlmostEqual(first, .2)
        self.assertAlmostEqual(second, .8)
        reads = env.drain_information_reads()
        self.assertEqual([row['requested_local_index'] for row in reads], [1, 1])
        self.assertEqual([row['ideal_cooling_demand'] for row in reads], [2., 8.])
        self.assertEqual([row['a_ref'] for row in reads], [.2, .8])
        audit = env.policy_information_audit()
        self.assertEqual(audit['access_tier'], 'simulator_privileged')
        self.assertIn('next_index_dataset_ideal_cooling', audit['information_access'])
        self.assertEqual(env.drain_information_reads(), [])

    def test_dataset_outage_seed_survives_reset_and_explicit_override_is_configurable(self):
        from district_marl.district_train import (
            build_district_env_config, DistrictContextRLlibEnv, _unwrap_citylearn_env)
        schema = Path(__file__).resolve().parents[3] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1/schema.json'
        from evaluation_contract import capture_context, physical_protocol_id
        protocols = []
        for override, expected in [(None, 43791), (90000, 90000), (123, 123)]:
            with self.subTest(override=override):
                kwargs = {} if override is None else {'power_outage_seed': override}
                env = DistrictContextRLlibEnv(build_district_env_config(
                    str(schema), 24, random_seed=2023, **kwargs))
                try:
                    env.reset()
                    self.assertEqual(
                        _unwrap_citylearn_env(env).buildings[0].stochastic_power_outage_model.random_seed,
                        expected)
                    protocols.append(capture_context(_unwrap_citylearn_env(env))['protocol'])
                finally:
                    env.close()
        self.assertNotEqual(physical_protocol_id(protocols[0]), physical_protocol_id(protocols[1]))

    def test_evaluation_inherits_checkpoint_training_parameters_only_for_defaults(self):
        from district_marl.district_eval import inherit_training_parameters, parse_args
        args = parse_args([])
        inherited = inherit_training_parameters(args, {
            'peak_weight': 77.0, 'team_share': .25,
            'peak_action_dim': 1,
        })
        self.assertEqual(args.peak_weight, 77.0)
        self.assertEqual(args.team_share, .25)
        self.assertEqual(args.peak_action_dim, 1)
        self.assertIn('peak_weight', inherited)
        # An explicit CLI override must win over the checkpoint snapshot.
        explicit = parse_args(['--peak-weight', '99'])
        inherited = inherit_training_parameters(explicit, {'peak_weight': 77.0})
        self.assertEqual(explicit.peak_weight, 99.0)
        self.assertNotIn('peak_weight', inherited)

    def test_explicit_default_value_is_not_overwritten_by_training_snapshot(self):
        from district_marl.district_eval import inherit_training_parameters, parse_args
        args = parse_args(['--peak-weight', '60'])
        inherited = inherit_training_parameters(args, {'peak_weight': 77.})
        self.assertEqual(args.peak_weight, 60.)
        self.assertNotIn('peak_weight', inherited)

    def test_seed_reaches_physical_environment(self):
        from district_marl.district_train import (
            build_district_env_config, DistrictContextRLlibEnv, _unwrap_citylearn_env)
        root = Path(__file__).resolve().parents[3]
        schema = root / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1/schema.json'
        config = build_district_env_config(str(schema), 24, random_seed=49)
        self.assertEqual(config['env_kwargs']['random_seed'], 49)
        env = DistrictContextRLlibEnv(config)
        try:
            self.assertEqual(_unwrap_citylearn_env(env).random_seed, 49)
        finally:
            env.close()

    def test_unwrap_returns_executable_citylearn_environment(self):
        from citylearn.citylearn import CityLearnEnv
        from district_marl.district_train import (
            build_district_env_config, DistrictContextRLlibEnv, _unwrap_citylearn_env)
        root = Path(__file__).resolve().parents[3]
        schema = root / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1/schema.json'
        env = DistrictContextRLlibEnv(build_district_env_config(str(schema), 24))
        try:
            self.assertIsInstance(_unwrap_citylearn_env(env), CityLearnEnv)
        finally:
            env.close()

    def test_training_parameters_reach_rllib_configuration(self):
        from district_marl.district_train import parse_args, build_algorithm_config
        args = parse_args(['--train-batch-size', '128', '--learning-starts', '144',
                           '--sample-steps-per-iteration', '24', '--training-intensity', '2',
                           '--train-steps', '144', '--ray-num-cpus', '1'])
        self.assertFalse(args.unknown_args)
        config = build_algorithm_config(args, {}, ['agent_0']).to_dict()
        self.assertEqual(config['train_batch_size'], 128)
        self.assertEqual(config['num_steps_sampled_before_learning_starts'], 144)
        self.assertEqual(config['min_sample_timesteps_per_iteration'], 24)
        self.assertEqual(config['training_intensity'], 2.)
        self.assertEqual(config['seed'], args.seed)

    def test_real_rollout_preserves_transitions_and_exports_complete_contract(self):
        from district_marl.district_train import (
            rollout_district, build_district_env_config, DistrictContextRLlibEnv)
        from utils.train import install_action_hook
        from evaluation_contract import finalize_recorded_evaluation
        install_action_hook()
        root = Path(__file__).resolve().parents[3]
        schema = root / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1/schema.json'
        config = build_district_env_config(str(schema), 24, record_details=True)

        class FixedPolicy:
            def compute_single_action(self, observation, **kwargs):
                return np.zeros(3, dtype=np.float32)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            evidence = {}
            metrics = rollout_district(
                FixedPolicy(), DistrictContextRLlibEnv, config, lambda _: 'shared',
                export_dir=output, evidence_out=evidence)
            self.assertEqual(metrics['eval_steps'], 23)
            trace = json.loads((output / 'decision_trace.json').read_text(encoding='utf-8'))
            self.assertEqual(len(trace['steps']), 23)
            first, last = trace['steps'][0], trace['steps'][-1]
            self.assertEqual(first['step'], 0)
            self.assertTrue(last['terminated'])
            self.assertFalse(first['terminated'])
            self.assertIn('policy_observations', first)
            self.assertIn('policy_raw_actions', first)
            self.assertIn('controller_information_reads', first)
            reference_reads = first['controller_information_reads']
            self.assertTrue(any(row['consumer'] == 'action_mapping' for row in reference_reads))
            self.assertTrue(any(row['consumer'] == 'policy_observation' for row in reference_reads))
            for step in trace['steps']:
                reads = step['controller_information_reads']
                self.assertEqual(len(reads), 6)
                self.assertEqual({row['decision_local_time_step'] for row in reads}, {step['step']})
                self.assertEqual(sum(row['consumer'] == 'action_mapping' for row in reads), 3)
            info_audit = json.loads((output / 'information_access_audit.json').read_text(encoding='utf-8'))
            self.assertEqual(info_audit['access_tier'], 'simulator_privileged')
            self.assertIn('next_index_dataset_ideal_cooling',
                          evidence['context']['protocol']['information_access'])
            self.assertEqual(set(first['reward']), {'agent_0', 'agent_1', 'agent_2'})
            for entry in first['buildings']:
                self.assertIn('next_observations', entry)
                self.assertIsNotNone(entry['settled']['net_electricity_consumption'])
                self.assertEqual(set(entry['actions']['named']),
                                 {'dhw_storage', 'electrical_storage', 'cooling_device'})
                self.assertIn('district', first)
            manifest = finalize_recorded_evaluation(
                evidence['result'], evidence['context'], output, evidence['terminated'])
            self.assertEqual(manifest['artifact_status'], 'complete', manifest['validation'])
            self.assertIn('runtime_audit.json', manifest['artifacts'])
            self.assertIn('information_access_audit.json', manifest['artifacts'])
            audit = json.loads((output / 'runtime_audit.json').read_text(encoding='utf-8'))
            self.assertEqual(len(audit['outages']['Building_1']['values']), 24)
            self.assertTrue((output / 'exported_data_building_1_ep0.csv').is_file())


if __name__ == '__main__':
    unittest.main()
