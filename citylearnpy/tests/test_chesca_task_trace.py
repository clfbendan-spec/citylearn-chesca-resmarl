"""Real entrypoint regression for decision evidence, using a short local schema."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ChescaTaskTraceTest(unittest.TestCase):
    def test_detailed_entrypoint_exports_complete_task_evidence(self):
        code_root = Path(__file__).resolve().parents[1]
        dataset = code_root.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            completed = subprocess.run(
                [sys.executable, str(code_root / 'CHESCA.detailed.py'),
                 '--eval-schema', str(dataset / 'schema.json'),
                 '--output-dir', str(output), '--episode-time-steps', '8',
                 '--no-render', '--pid_kp', '-0.41'],
                env=dict(os.environ, CITYLEARN_PYTHON_PATH=str(code_root)),
                capture_output=True, timeout=120, cwd=directory)
            self.assertEqual(completed.returncode, 0,
                             completed.stderr.decode('utf-8', errors='replace'))
            manifest = json.loads((output / 'evaluation_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['artifact_status'], 'complete')
            self.assertEqual(manifest['resolved_parameters']['pid_kp'], -0.41)
            self.assertEqual(manifest['coverage']['recorded_transitions'], 7)
            from evaluation_contract import validate_manifest
            self.assertTrue(validate_manifest(manifest, output)['valid'])

    def test_nondefault_cli_parameters_reach_task_snapshot_and_manifest(self):
        code_root = Path(__file__).resolve().parents[1]
        dataset = code_root.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1'
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'configured-output'
            completed = subprocess.run(
                [sys.executable, str(code_root / 'CHESCA.py'),
                 '--eval-schema', str(dataset / 'schema.json'),
                 '--output-dir', str(output), '--episode-time-steps', '8',
                 '--no-render', '--B_high', '1.7',
                 '--peak_trigger_mode', 'ns_spike',
                 '--tau', '2', '--rebound_window', '3'],
                env=dict(os.environ, CITYLEARN_PYTHON_PATH=str(code_root)),
                capture_output=True, timeout=120)
            self.assertEqual(completed.returncode, 0,
                             completed.stderr.decode('utf-8', errors='replace'))
            config = json.loads((output / 'chesca_agent_config.json').read_text(encoding='utf-8'))
            self.assertEqual(config['B_high'], 1.7)
            self.assertEqual(config['peak_trigger_mode'], 'ns_spike')
            self.assertEqual(config['tau'], 2)
            self.assertEqual(config['rebound_window'], 3)
            manifest = json.loads((output / 'evaluation_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['artifact_status'], 'complete')
            self.assertEqual(manifest['resolved_parameters']['B_high'], 1.7)
            self.assertEqual(manifest['coverage']['recorded_transitions'], 7)

    def test_standalone_task_trace_contains_actual_environment_transition(self):
        code_root = Path(__file__).resolve().parents[1]
        dataset = code_root.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1'
        schema = json.loads((dataset / 'schema.json').read_text(encoding='utf-8'))
        schema.update(root_directory=str(dataset), simulation_start_time_step=0,
                      simulation_end_time_step=7, episode_time_steps=None)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            schema_file = Path(directory) / 'schema.json'
            schema_file.write_text(json.dumps(schema), encoding='utf-8')
            environment = dict(os.environ, CITYLEARN_PYTHON_PATH=str(code_root))
            completed = subprocess.run(
                [sys.executable, str(code_root / 'CHESCA.py'), '--eval-schema', str(schema_file),
                 '--output-dir', str(output)], env=environment, capture_output=True, timeout=120)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode('utf-8', errors='replace'))
            trace = json.loads((output / 'decision_trace.json').read_text(encoding='utf-8'))
            self.assertEqual(len(trace['steps']), 7)
            for step in trace['steps']:
                self.assertIn('reward', step)
                self.assertIn('info', step)
                self.assertIn('truncated', step)
                for building in step['buildings']:
                    self.assertIn('observations', building)
                    self.assertIn('next_observations', building)
                    self.assertIn('named', building['actions'])
            self.assertTrue(trace['steps'][-1]['terminated'])
            manifest_file = output / 'evaluation_manifest.json'
            self.assertTrue(manifest_file.is_file(), 'Task evaluation manifest is missing')
            manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
            self.assertEqual(manifest['artifact_status'], 'complete')
            self.assertEqual(manifest['coverage']['recorded_transitions'], 7)
            self.assertEqual(manifest['protocol']['simulation_window'], [0, 7])
            score = json.loads((output / 'score_result.json').read_text())
            self.assertIsNone(score['score'])
            self.assertIn('missing_anchor', score['reason_codes'])


if __name__ == '__main__':
    unittest.main()
