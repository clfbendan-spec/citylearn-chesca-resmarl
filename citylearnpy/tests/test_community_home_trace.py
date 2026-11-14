import csv
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from community_assessment import HOME_TRACE_COLUMNS, write_home_trace_csv


class CommunityHomeTraceTest(unittest.TestCase):
    def test_writes_home_chart_and_action_fields_without_internal_trace_payload(self):
        row = {
            'episode': 1, 'step': 0, 'hour': 9, 'building': 2,
            'actual_outdoor_temp': 31.5, 'actual_solar': 2.4,
            'actual_load': 1.2, 'actual_dhw': 0.3,
            'action_dhw_final': 0.1, 'action_ele_final': -0.2,
            'action_tmp_final': 0.7, 'decision_narrative': 'large internal payload',
        }
        with tempfile.TemporaryDirectory() as directory:
            path = write_home_trace_csv([row], Path(directory) / 'home_trace.csv', 5088, (5100, 5200))
            with path.open(encoding='utf-8-sig', newline='') as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(tuple(reader.fieldnames), HOME_TRACE_COLUMNS)
                saved = next(reader)
        self.assertEqual(saved['building'], '2')
        self.assertEqual(saved['step'], '5088')
        self.assertEqual(saved['score_eligible'], 'false')
        self.assertEqual(saved['action_applied'], 'false')
        self.assertEqual(saved['control_mode'], 'common_baseline_warmup')
        self.assertEqual(saved['action_tmp_final'], '0.7')
        self.assertNotIn('decision_narrative', saved)


if __name__ == '__main__':
    unittest.main()
