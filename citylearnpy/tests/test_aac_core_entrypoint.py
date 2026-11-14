import os
import json
import csv
from pathlib import Path
import subprocess
import tempfile
import unittest
import numpy as np
import sys


class AACCoreEntrypointTest(unittest.TestCase):
    def test_forecast_price_rules_are_declared_in_actual_evaluation_protocol(self):
        root = Path(__file__).resolve().parents[1]
        interpreter = root.parents[1] / 'envs/aac_madrl/Scripts/python.exe'
        with tempfile.TemporaryDirectory() as directory:
            for flag in ('--predicted-price-charge-rule-override',
                         '--predicted-price-discharge-gate-override'):
                with self.subTest(flag=flag):
                    output = Path(directory) / (flag.lstrip('-') + '.json')
                    completed = subprocess.run([
                        str(interpreter), str(root / 'aacmadrl/core.py'),
                        '--evaluate', str(root / 'aacmadrl/anchor_checkpoint.pt'),
                        '--eval-output', str(output),
                        '--evaluation-dataset', str(root.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1'),
                        '--evaluation-end-time-step', '7', flag, 'on'],
                        capture_output=True, timeout=180)
                    self.assertEqual(completed.returncode, 0,
                                     completed.stderr.decode('utf-8', errors='replace'))
                    result = json.loads(output.read_text(encoding='utf-8'))
                    self.assertEqual(
                        result['platform_result']['protocol']['information_access'],
                        'current_observations_local_history_and_declared_price_forecasts')

    def test_learner_exposes_configurable_critic_learning_dynamics(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'aacmadrl'))
        from aacmadrl.core import Learner
        learner = Learner(
            49,
            [np.array([-1., 0., 1.])] * 3,
            actor_lr=2.e-4,
            critic_lr=3.e-4,
            discount=.97,
            tau=.02,
            reward_scale=4.,
        )
        self.assertAlmostEqual(learner.critic_opt.param_groups[0]['lr'], 3.e-4)
        self.assertAlmostEqual(learner.discount, .97)
        self.assertAlmostEqual(learner.tau, .02)
        self.assertAlmostEqual(learner.reward_scale, 4.)

    def test_runtime_probe_shows_saved_grid_is_legal_in_original_environment(self):
        root = Path(__file__).resolve().parents[1]
        interpreter = root.parents[1] / 'envs/aac_madrl/Scripts/python.exe'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'runtime-contract.json'
            completed = subprocess.run([
                str(interpreter), str(root.parent / 'tools/probe_citylearn_runtime.py'),
                '--output', str(output)], env=dict(os.environ, CITYLEARNPY_DIR=str(root)),
                capture_output=True, timeout=120)
            self.assertEqual(completed.returncode, 0,
                             completed.stderr.decode('utf-8', errors='replace'))
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(report['context']['protocol']['environment_step_order'],
                             'advance_then_apply')
            self.assertTrue(all(row['saved_grid_legal'] for row in report['action_grid_checks']))

    def test_common_runtime_is_rejected_even_when_checkpoint_actions_are_legal(self):
        root = Path(__file__).resolve().parents[1]
        interpreter = root.parents[1] / 'envs/cl2/python.exe'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'shared-runtime'
            completed = subprocess.run([
                str(interpreter), str(root / 'AACMADRL_eval.py'), '--output-dir', str(output),
                '--checkpoint', str(root / 'aacmadrl/anchor_checkpoint.pt'),
                '--train-steps', '144', '--eval-steps', '8',
                '--train-schema', str(root.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_local_evaluation'),
                '--eval-schema', str(root.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1')],
                env=dict(os.environ, CITYLEARNPY_DIR=str(root)), capture_output=True, timeout=180)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn(b'AAC runtime incompatible', completed.stderr)
            self.assertFalse(output.exists())

    def test_core_subprocess_imports_shared_modules_outside_repository_cwd(self):
        root = Path(__file__).resolve().parents[1]
        interpreter = root.parents[1] / 'envs/aac_madrl/Scripts/python.exe'
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run([str(interpreter), str(root / 'aacmadrl/core.py'), '--help'],
                                       cwd=directory, env=environment, capture_output=True, timeout=90)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode('utf-8', errors='replace'))
        self.assertIn(b'--batch-size', completed.stdout)
        self.assertIn(b'--learning-starts', completed.stdout)

    def test_real_evaluation_worker_returns_protocol_metrics_and_task_owned_bundle(self):
        root = Path(__file__).resolve().parents[1]
        interpreter = root.parents[1] / 'envs/aac_madrl/Scripts/python.exe'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'worker-eval'
            completed = subprocess.run([
                str(interpreter), str(root / 'AACMADRL_eval.py'), '--output-dir', str(output),
                '--checkpoint', str(root / 'aacmadrl/anchor_checkpoint.pt'),
                '--train-steps', '720', '--eval-steps', '8',
                '--train-schema', str(root.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_local_evaluation'),
                '--eval-schema', str(root.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1')],
                env=dict(os.environ, CITYLEARNPY_DIR=str(root)), capture_output=True, timeout=180)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode('utf-8', errors='replace'))
            path = output / 'evaluation_manifest.json'
            self.assertTrue(path.is_file(), 'AAC task did not publish a shared evaluation manifest')
            manifest = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(manifest['artifact_status'], 'complete')
            self.assertEqual(manifest['coverage']['recorded_transitions'], 7)
            self.assertEqual(manifest['algorithm'], 'AACMADRL')
            self.assertIn('ai_analysis_bundle.json', manifest['artifacts'])
            result = json.loads((output / 'evaluation_result.json').read_text(encoding='utf-8'))
            for index, name in enumerate(result['protocol']['building_ids'], 1):
                with (output / f'exported_data_building_{index}_ep0.csv').open(
                        encoding='utf-8', newline='') as stream:
                    rows = list(csv.DictReader(stream))
                bill = sum(max(float(row['Net Electricity Consumption-kWh']) *
                               float(row['electricity_pricing']), 0.) for row in rows)
                self.assertAlmostEqual(bill, result['per_building'][name]['positive_bill'], places=6)
            self.assertEqual(result['protocol']['environment_step_order'], 'advance_then_apply')

    def test_configured_learning_start_reaches_real_training_updates(self):
        root = Path(__file__).resolve().parents[1]
        interpreter = root.parents[1] / 'envs/aac_madrl/Scripts/python.exe'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'training-task'
            completed = subprocess.run([
                str(interpreter), str(root / 'AACMADRL_train.py'),
                '--output-dir', str(output), '--train-epochs', '1',
                '--train-steps', '144', '--learning-starts', '128',
                '--train-batch-size', '128', '--optimizer-updates-per-step', '1',
                '--train-schema', str(root.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_local_evaluation')],
                env=dict(os.environ, CITYLEARNPY_DIR=str(root)), capture_output=True, timeout=180)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode('utf-8', errors='replace'))
            manifest = json.loads((output / 'checkpoints/aacmadrl/model_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['config']['learning_starts'], 128)
            self.assertGreater(manifest['selection']['updates'], 0,
                               'A 143-transition run must update when learning starts at 128')

    def test_platform_constraint_parameters_reach_training_and_evaluation_provenance(self):
        root = Path(__file__).resolve().parents[1]
        interpreter = root.parents[1] / 'envs/aac_madrl/Scripts/python.exe'
        dataset = root.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_local_evaluation'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'constraint-task'
            completed = subprocess.run([
                str(interpreter), str(root / 'AACMADRL_train.py'),
                '--output-dir', str(output), '--train-epochs', '1',
                '--train-steps', '144', '--learning-starts', '128',
                '--train-batch-size', '128', '--optimizer-updates-per-step', '1',
                '--init-checkpoint', str(root.parent /
                    'AAC_MADRL/experiments/kl_warmstart_corrected_v2_20261105/separate_critic_kl10_seed54_zeroinit/checkpoint_02.pt'),
                '--expected-init-sha256', 'a97011eaab5fcb3ff1ee90724f70c3afd06838cb9c6b4ea62d10d10539690ea3',
                '--behavior-kl-penalty', '1', '--train-schema', str(dataset),
                '--dual-lr', '.2', '--dual-max', '3',
                '--dual-start-episode', '1', '--dual-cost-target', '.85',
                '--dual-discomfort-target', '.09'],
                capture_output=True, timeout=180)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode('utf-8', errors='replace'))
            protocol = json.loads((output / 'training/protocol.json').read_text(encoding='utf-8'))
            self.assertEqual(protocol['dual_learning_rate'], .2)
            self.assertEqual(protocol['discomfort_dual_learning_rate'], .2)
            self.assertEqual(protocol['dual_maximum'], 3.)
            self.assertEqual(protocol['dual_start_episode'], 1)
            self.assertEqual(protocol['dual_cost_target'], .85)
            self.assertEqual(protocol['dual_discomfort_target'], .09)
            self.assertEqual([len(grid) for grid in protocol['action_grids']], [21, 21, 11])
            self.assertEqual(protocol['action_grids'][1][-1], .48787879943847656)
            updates = [json.loads(line) for line in
                       (output / 'training/dual_updates.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([row['episode'] for row in updates], [1])
            self.assertTrue(all(0 <= value <= 3 for row in updates
                                for value in row['cost'] + row['discomfort']))
            evaluation = Path(directory) / 'eval-task'
            evaluated = subprocess.run([
                str(interpreter), str(root / 'AACMADRL_eval.py'),
                '--output-dir', str(evaluation),
                '--checkpoint', str(output / 'checkpoints/aacmadrl/model.pt'),
                '--train-schema', str(dataset), '--eval-schema', str(dataset),
                '--train-steps', '144', '--eval-steps', '8'],
                capture_output=True, timeout=180)
            self.assertEqual(evaluated.returncode, 0, evaluated.stderr.decode('utf-8', errors='replace'))
            config = json.loads((evaluation / 'agent_config.json').read_text(encoding='utf-8'))
            self.assertEqual(config['dual_lr'], .2)
            self.assertEqual(config['train_epochs'], 1)
            self.assertEqual(json.loads((evaluation / 'aacmadrl_config.json').read_text(
                encoding='utf-8'))['train_epochs'], 1)
            self.assertEqual(config['dual_max'], 3.)
            self.assertEqual(config['dual_start_episode'], 1)
            self.assertEqual(config['dual_cost_target'], .85)
            self.assertEqual(config['dual_discomfort_target'], .09)
            self.assertEqual(config['behavior_kl_penalty'], 1.)
            self.assertEqual(config['initialization_source'], 'explicit_checkpoint')
            self.assertEqual(config['initialization_checkpoint_sha256'],
                             'a97011eaab5fcb3ff1ee90724f70c3afd06838cb9c6b4ea62d10d10539690ea3')
            import hashlib
            self.assertEqual(hashlib.sha256((output / 'initialization/model.pt').read_bytes()).hexdigest(),
                             config['initialization_checkpoint_sha256'])

    def test_invalid_constraint_values_fail_before_creating_task_artifacts(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            for flag, value in (
                    ('--dual-lr', 'nan'), ('--dual-lr', '-.1'),
                    ('--dual-max', 'inf'), ('--dual-max', '0'),
                    ('--dual-start-episode', '0'), ('--dual-cost-target', '.91'),
                    ('--dual-discomfort-target', '.11')):
                with self.subTest(flag=flag, value=value):
                    output = Path(directory) / 'not-created'
                    result = subprocess.run([
                        sys.executable, str(root / 'AACMADRL_train.py'),
                        '--output-dir', str(output), flag, value],
                        capture_output=True, timeout=30)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
