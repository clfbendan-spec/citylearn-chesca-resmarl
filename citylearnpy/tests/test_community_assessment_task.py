import base64
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class CommunityTaskTest(unittest.TestCase):
    def test_both_task_entries_export_results_and_decision_artifacts(self):
        root = Path(__file__).resolve().parents[1]
        template = root.parent.parent / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1'
        parameters = {'tau': 1, 'balance_type': 'C', 'frozen_gate': True, 'frozen_gate_seed': 0}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for asset in template.iterdir():
                if asset.is_file():
                    shutil.copy2(asset, directory / asset.name)
            schema = json.loads((directory / 'schema.json').read_text(encoding='utf-8'))
            schema.update(simulation_end_time_step=23, episode_time_steps=None)
            (directory / 'schema.json').write_text(json.dumps(schema), encoding='utf-8')
            for algorithm in ('NOCONTROL', 'CHESCA'):
                output = directory / algorithm
                output.mkdir()
                report = directory / (algorithm + '-report')
                command = [sys.executable, str(root / (algorithm + '.py')),
                           '--community-assessment-schema', str(directory / 'schema.json'),
                           '--community-assessment-output', str(report),
                           '--community-assessment-parameters', base64.b64encode(json.dumps(parameters).encode()).decode(),
                           '--output-dir', str(output)]
                completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                           errors='replace', timeout=120)
                self.assertEqual(completed.returncode, 0, completed.stderr[-5000:])
                result = json.loads((report / 'result.json').read_text(encoding='utf-8'))
                manifest = json.loads((output / 'evaluation_manifest.json').read_text(encoding='utf-8'))
                import hashlib
                for filename, evidence in manifest['artifacts'].items():
                    self.assertEqual(hashlib.sha256((output / filename).read_bytes()).hexdigest(), evidence['sha256'], filename)
                self.assertEqual(result['status'], 'succeeded')
                self.assertEqual(len(result['cases']), 1 if algorithm == 'CHESCA' else 0)
                self.assertEqual(manifest['artifact_status'], 'complete', manifest['validation'])
                self.assertTrue(manifest['resolved_parameters']['frozen_gate'])
                for filename in ('exported_kpis.csv', 'decision_trace.json', 'exported_data_building_1_ep0.csv'):
                    self.assertTrue((output / filename).is_file(), filename)
