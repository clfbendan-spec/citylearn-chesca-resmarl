from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np


class DistrictReferenceModeTest(unittest.TestCase):
    def test_disabled_reference_preserves_shape_without_reading_ideal_demand(self):
        from district_marl.district_env import DistrictContextRLlibEnv
        from district_marl.district_train import build_district_env_config
        schema = (Path(__file__).resolve().parents[3] / 'datasets' /
                  'citylearn_challenge_2023_phase_2_online_evaluation_1/schema.json')
        config = build_district_env_config(str(schema), 24, random_seed=2023)
        config['cooling_reference_mode'] = 'disabled'
        env = DistrictContextRLlibEnv(config)
        legacy = DistrictContextRLlibEnv(build_district_env_config(
            str(schema), 24, random_seed=2023))
        try:
            legacy_obs, _ = legacy.reset()
            env.enable_information_audit()
            # Intercept the actual source boundary; reset and action mapping must
            # not read ideal demand even when it would produce a nonzero value.
            with patch('utils.env._ideal_a_ref', return_value=.8) as ideal_read:
                observations, _ = env.reset()
                actions = {aid: np.array([0., 0., .5], dtype=np.float32)
                           for aid in observations}
                mapped = env._cool_action_apply(actions)
                env.step(actions)
                self.assertEqual(ideal_read.call_count, 0)
            for aid, observation in observations.items():
                self.assertEqual(observation.shape, legacy_obs[aid].shape)
                # Nine district features follow the retained, zeroed a_ref slot.
                self.assertEqual(float(observation[-10]), 0.)
                self.assertAlmostEqual(float(mapped[aid][2]), .24, places=6)
            self.assertEqual(env.drain_information_reads(), [])
            audit = env.policy_information_audit()
            self.assertEqual(audit['cooling_reference_mode'], 'disabled')
            self.assertFalse(audit['policy_observation_reference'])
            self.assertFalse(audit['action_mapping_reference'])
            self.assertEqual(audit['sources'], [])
            self.assertNotEqual(audit['access_tier'], 'simulator_privileged')
        finally:
            env.close()
            legacy.close()

    def test_configuration_rejects_unknown_reference_mode(self):
        from district_marl.district_env import DistrictContextRLlibEnv
        with self.assertRaisesRegex(ValueError, 'cooling_reference_mode'):
            DistrictContextRLlibEnv({'cooling_reference_mode': 'typo'})

    def test_train_and_eval_parsers_accept_reference_mode(self):
        from district_marl import district_train, district_eval
        for module in (district_train, district_eval):
            with self.subTest(module=module.__name__):
                args = module.parse_args(['--cooling-reference-mode', 'disabled'])
                self.assertEqual(args.unknown_args, [])
                self.assertEqual(args.cooling_reference_mode, 'disabled')

    def test_evaluation_inherits_matching_mode_and_defaults_old_models_to_legacy(self):
        from district_marl.district_eval import inherit_training_parameters, parse_args
        for snapshot, expected in [({}, 'dataset_ideal'),
                                   ({'cooling_reference_mode': 'disabled'}, 'disabled')]:
            with self.subTest(snapshot=snapshot):
                args = parse_args([])
                inherit_training_parameters(args, snapshot)
                self.assertEqual(args.cooling_reference_mode, expected)

    def test_explicit_reference_mode_cannot_reinterpret_checkpoint_actions(self):
        from district_marl.district_eval import inherit_training_parameters, parse_args
        for explicit, snapshot in [
                ('disabled', {}),
                ('dataset_ideal', {'cooling_reference_mode': 'disabled'})]:
            with self.subTest(explicit=explicit):
                args = parse_args(['--cooling-reference-mode', explicit])
                with self.assertRaisesRegex(ValueError, 'cooling.reference.mode'):
                    inherit_training_parameters(args, snapshot)

    def test_explicit_matching_reference_mode_is_accepted(self):
        from district_marl.district_eval import inherit_training_parameters, parse_args
        args = parse_args(['--cooling-reference-mode', 'disabled'])
        inherit_training_parameters(args, {'cooling_reference_mode': 'disabled'})
        self.assertEqual(args.cooling_reference_mode, 'disabled')


if __name__ == '__main__':
    unittest.main()
