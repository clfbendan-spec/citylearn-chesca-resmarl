import unittest
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.ches_frozen_gate import attach_frozen_gate


class FrozenGateTest(unittest.TestCase):
    def test_previous_realized_temperature_and_outage_protection(self):
        buildings = [SimpleNamespace(indoor_dry_bulb_temperature=[25., 19.],
                                    indoor_dry_bulb_temperature_cooling_set_point=[23., 23.])
                     for _ in range(3)]
        env = SimpleNamespace(time_step=1, buildings=buildings)
        updates = []
        controllers = [SimpleNamespace(compute_pred_cooling_consumption=lambda a, t: (a * 10, None)) for _ in buildings]
        agent = SimpleNamespace(
            apply_residual_correction=lambda actions, obs: updates.append('base') or actions,
            outage_details=[{'outage_flag': False}, {'outage_flag': True}, {'outage_flag': False}],
            predicted_cooling_demand=[0., 0., 0.], cooling_device_controller=controllers,
            forecasts={'outdoor_temp': [30.]})
        attach_frozen_gate(agent, env)
        result = np.array(agent.apply_residual_correction([0., .1, .9, 0., .2, .5, 0., .3, .5], [])).reshape(3, 3)
        np.testing.assert_allclose(result[:, 2], [1., .5, .6])
        np.testing.assert_allclose(result[:, 1], [.1, .2, .3])
        self.assertEqual(updates, ['base'])
        np.testing.assert_allclose(agent.predicted_cooling_demand, [10., 0., 6.])

    def test_threshold_is_strict(self):
        building = SimpleNamespace(indoor_dry_bulb_temperature=[23.5],
                                   indoor_dry_bulb_temperature_cooling_set_point=[23.])
        agent = SimpleNamespace(apply_residual_correction=lambda a, o: a,
                                outage_details=[{'outage_flag': False}])
        attach_frozen_gate(agent, SimpleNamespace(time_step=0, buildings=[building]))
        self.assertEqual(agent.apply_residual_correction([0., 0., .5], []), [0., 0., .5])


if __name__ == '__main__':
    unittest.main()
