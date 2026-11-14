import copy
import unittest

from aacmadrl.runtime_contract import (
    EXPECTED_LOCAL, validate_runtime_contract, validate_local_regression,
    inherit_training_parameters)


class AACRuntimeContractTest(unittest.TestCase):
    def test_runtime_requires_both_version_and_executable_step_order(self):
        validate_runtime_contract('2.3.1', 'advance_then_apply')
        for version, timing in [('2.5.0', 'apply_then_advance'),
                                ('2.3.1', 'apply_then_advance'),
                                ('2.5.0', 'advance_then_apply')]:
            with self.assertRaisesRegex(ValueError, 'AAC runtime'):
                validate_runtime_contract(version, timing)

    def regression_result(self):
        return dict(
            dataset_sha256='ebaf5a18299d759bd9a369680199d40c4451aa9c9af523cf4e97e31a374ab567',
            checkpoint_sha256='3d9ebd7402c5ca8e3d0c8ebec2ccbc3ec853855c5a902349b0f30fa2f94402b1',
            simulation_window=[0, 719], transitions=719,
            per_building=copy.deepcopy(EXPECTED_LOCAL),
            mechanism={name: dict(cooling_kwh=1.) for name in EXPECTED_LOCAL})

    def test_local_regression_rejects_wrong_dataset_weights_and_coverage(self):
        validate_local_regression(self.regression_result())
        for key, value in [('dataset_sha256', 'wrong'), ('checkpoint_sha256', 'wrong'),
                           ('transitions', 718), ('simulation_window', [0, 718])]:
            result = self.regression_result()
            result[key] = value
            with self.assertRaises(ValueError):
                validate_local_regression(result)

    def test_local_regression_rejects_changed_physical_behavior(self):
        for value in [.3, float('nan')]:
            result = self.regression_result()
            result['per_building']['Building_1']['discomfort_proportion'] = value
            with self.assertRaises(ValueError):
                validate_local_regression(result)

    def test_eval_inherits_actual_training_epochs_without_overwriting_eval_seed(self):
        evaluation = dict(train_epochs=5, seed=855, actor_lr=.0001)
        inherit_training_parameters(evaluation, dict(train_epochs=3, seed=49, actor_lr=.0003))
        self.assertEqual(evaluation['train_epochs'], 3)
        self.assertEqual(evaluation['actor_lr'], .0003)
        self.assertEqual(evaluation['seed'], 855)

    def test_local_regression_rejects_missing_or_unsettled_device_feedback(self):
        for value in [0., float('nan'), None]:
            result = self.regression_result()
            result['mechanism']['Building_1']['cooling_kwh'] = value
            with self.assertRaises(ValueError):
                validate_local_regression(result)
        result = self.regression_result()
        result['mechanism'] = {}
        with self.assertRaises(ValueError):
            validate_local_regression(result)


if __name__ == '__main__':
    unittest.main()
