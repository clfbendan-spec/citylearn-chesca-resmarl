import sys
import importlib.util
from pathlib import Path

import unittest


ROOT = Path(__file__).resolve().parents[1]
COPY_ROOT = ROOT / 'CHESCA-copy'
for path in (ROOT, COPY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from utils.ches_config import load_agent_config
from checa.cooling_device_controller.cooling_device_controller import CoolingDeviceController


def _metadata():
    return {
        'cooling_device': {
            'nominal_power': 10.0,
            'efficiency': 0.4,
            'target_cooling_temperature': 12.8,
        }
    }


class ChescaPidConfigTest(unittest.TestCase):
    def test_pid_parameters_reject_nonfinite_values(self):
        for key in ('pid_kp', 'pid_ki', 'pid_kd', 'pid_out_temp_scaler', 'pid_kp_outage'):
            for value in (float('nan'), float('inf'), float('-inf')):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ValueError):
                        load_agent_config(None, {key: value})

    def test_detailed_source_preserves_pid_overrides(self):
        spec = importlib.util.spec_from_file_location(
            'ches_config_detailed', ROOT / 'utils' / 'ches_config.detailed.py')
        detailed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(detailed)
        config = detailed.build_agent_config({
            'pid_kp': -0.41, 'pid_ki': -1.7, 'pid_kd': 0.02,
            'pid_out_temp_scaler': 0.07, 'pid_kp_outage': -0.22,
        })
        controller = CoolingDeviceController(_metadata(), 0, [], params=config)
        self.assertAlmostEqual(controller.pid_controller.Kp, -0.41)
        self.assertAlmostEqual(controller.pid_controller.Ki, -1.7)
        self.assertAlmostEqual(controller.pid_controller.Kd, 0.02)
        self.assertAlmostEqual(controller.pid_controller.OutTempScaler, 0.07)
        self.assertAlmostEqual(controller.pid_controller.Kp_outage, -0.22)

    def test_pid_parameters_are_parsed_and_reach_runtime_controller(self):
        config = load_agent_config(None, {
            'min_soc_per_hour': {str(i): 0.5 for i in range(24)},
            'pid_kp': -0.41,
            'pid_ki': -1.7,
            'pid_kd': 0.02,
            'pid_out_temp_scaler': 0.07,
            'pid_kp_outage': -0.22,
        })
        self.assertAlmostEqual(config['pid_kp'], -0.41)
        controller = CoolingDeviceController(_metadata(), 0, [], params=config)
        self.assertAlmostEqual(controller.pid_controller.Kp, -0.41)
        self.assertAlmostEqual(controller.pid_controller.Ki, -1.7)
        self.assertAlmostEqual(controller.pid_controller.Kd, 0.02)
        self.assertAlmostEqual(controller.pid_controller.OutTempScaler, 0.07)
        self.assertAlmostEqual(controller.pid_controller.Kp_outage, -0.22)
        self.assertAlmostEqual(controller.aux_pid_controller.Kp, -0.41)

