from types import SimpleNamespace as NS
import pytest
from realized_thermal_state import extract, FEATURE_NAMES


class PastOnly:
    def __init__(self, values):
        self.values = values
    def __len__(self):
        return len(self.values)
    def __getitem__(self, index):
        if index >= len(self.values):
            raise AssertionError('Unrealized outcome accessed')
        return self.values[index]


def building(step=2):
    return NS(time_step=step, indoor_dry_bulb_temperature=PastOnly([26., 27.]),
              indoor_dry_bulb_temperature_cooling_set_point=[25.,25.,24.],
              comfort_band=[2.], occupant_count=[1.,1.,0.],
              cooling_device=NS(electricity_consumption=PastOnly([.4,.7])))


def test_reads_completed_outcome_and_current_exogenous_inputs():
    s = extract(building(), building())
    assert (s.measurement_step, s.temperature_c, s.current_setpoint_c, s.current_occupants) == (1,27.,24.,0.)
    assert s.last_cooling_electricity_kwh == .7
    assert len(s.feature_vector()) == len(FEATURE_NAMES) == 10
    assert s.feature_vector()[-3:] == (1.,1.,1.)


def test_reset_returns_initial_measurement_without_completed_energy():
    s = extract(building())
    initial = extract(building(0))
    assert s.measurement_step == 1
    assert initial.measurement_step == 0 and not initial.has_completed_measurement
    assert initial.last_cooling_electricity_kwh == 0
    assert initial.feature_vector()[-3:] == (0.,0.,0.)


def test_unrealized_temperature_and_future_inputs_do_not_change_features():
    a = building()
    b = building()
    b.indoor_dry_bulb_temperature = [26.,27.,-100.,100.]
    b.cooling_device.electricity_consumption = [.4,.7,999.]
    b.occupant_count += [100.]
    b.indoor_dry_bulb_temperature_cooling_set_point += [-100.]
    assert extract(a).feature_vector() == extract(b).feature_vector()


def test_reference_alignment_and_invalid_values_are_rejected():
    with pytest.raises(ValueError, match='same decision'):
        extract(building(), building(1))
    b = building()
    b.indoor_dry_bulb_temperature = [26.,float('nan')]
    with pytest.raises(ValueError, match='nonfinite'):
        extract(b)
    b.indoor_dry_bulb_temperature = [26.]
    with pytest.raises(ValueError, match='incomplete history'):
        extract(b)
