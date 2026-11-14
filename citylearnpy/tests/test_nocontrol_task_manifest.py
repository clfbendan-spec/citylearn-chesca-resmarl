import json
import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class NoControlTaskManifestTest(unittest.TestCase):
    def test_real_entrypoint_keeps_nonzero_window_and_baseline_action_identity(self):
        code = Path(__file__).resolve().parents[1]
        dataset = code.parents[1] / 'datasets/citylearn_challenge_2023_phase_2_online_evaluation_1/schema.json'
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / 'result'
            run = subprocess.run([sys.executable, str(code / 'NOCONTROL.py'),
                                  '--schema', str(dataset), '--simulation-start-time-step', '10',
                                  '--simulation-end-time-step', '12', '--seed', '42',
                                  '--output-dir', str(output)],
                                 env=dict(os.environ, CITYLEARN_PYTHON_PATH=str(code)),
                                 capture_output=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr.decode('utf-8', errors='replace'))
            path = output / 'evaluation_manifest.json'
            self.assertTrue(path.exists(), 'NoControl did not export task-owned evaluation evidence')
            manifest = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(manifest['protocol']['simulation_window'], [10, 12])
            self.assertEqual(manifest['artifact_status'], 'complete')
            self.assertEqual(manifest['resolved_parameters']['random_seed'], 42)
            self.assertEqual(manifest['resolved_parameters']['active_actions'], [[]])
            result = json.loads((output / 'evaluation_result.json').read_text())
            self.assertEqual(set(result['per_building']), {'Building_1', 'Building_2', 'Building_3'})
            kpis_file = next(output.rglob('exported_kpis.csv'))
            with kpis_file.open(encoding='utf-8-sig', newline='') as stream:
                cost = next(row for row in csv.DictReader(stream) if row['KPI'] == 'cost_total')
            for building, row in result['per_building'].items():
                self.assertAlmostEqual(row['cost_total'], float(cost[building]), delta=.00051)


if __name__ == '__main__':
    unittest.main()
