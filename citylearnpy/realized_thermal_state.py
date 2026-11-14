"""Explicit decision-time thermal feedback without changing simulator arrays.

At decision t>0, T[t-1] is the last completed outcome. T[t] may still be a
recorded placeholder in the installed simulator and is deliberately not read.
Current occupancy, setpoint and comfort band remain current exogenous inputs.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


FEATURE_NAMES = (
    'last_realized_temperature_c', 'current_setpoint_c', 'current_comfort_band_c',
    'current_occupants', 'last_cooling_electricity_kwh',
    'temperature_minus_current_setpoint_c', 'temperature_minus_reference_c',
    'measurement_age_steps', 'has_completed_measurement', 'has_reference',
)


def _value(series, index, name, constant=False):
    try:
        size = len(series)
    except TypeError:
        if index > 0 and not constant:
            raise ValueError(f'{name} has no timestamped history')
        value = float(series)
    else:
        if not size:
            raise ValueError(f'{name} is empty')
        position = 0 if constant and size == 1 else index
        if position >= size:
            raise ValueError(f'{name} has incomplete history')
        value = float(series[position])
    if not math.isfinite(value):
        raise ValueError(f'{name} is nonfinite')
    return value


@dataclass(frozen=True)
class RealizedThermalState:
    decision_step: int
    measurement_step: int
    temperature_c: float
    current_setpoint_c: float
    current_comfort_band_c: float
    current_occupants: float
    last_cooling_electricity_kwh: float
    has_completed_measurement: bool
    reference_temperature_c: float | None
    reference_measurement_step: int | None

    def feature_vector(self):
        return (
            self.temperature_c, self.current_setpoint_c, self.current_comfort_band_c,
            self.current_occupants, self.last_cooling_electricity_kwh,
            self.temperature_c-self.current_setpoint_c,
            0. if self.reference_temperature_c is None else self.temperature_c-self.reference_temperature_c,
            float(self.decision_step-self.measurement_step),
            float(self.has_completed_measurement),
            float(self.reference_temperature_c is not None),
        )


def extract(building, reference=None):
    """Read one aligned frame; no cache, simulator mutation or future access."""
    step = int(building.time_step)
    if step < 0:
        raise ValueError('Negative decision step')
    measured = max(0, step-1)
    temperature = _value(building.indoor_dry_bulb_temperature, measured, 'realized temperature')
    reference_temperature = None
    if reference is not None:
        if int(reference.time_step) != step:
            raise ValueError('Reference must have advanced to the same decision step')
        reference_temperature = _value(reference.indoor_dry_bulb_temperature, measured, 'reference temperature')
    band = _value(building.comfort_band, step, 'comfort band', constant=True)
    if band < 0:
        raise ValueError('Negative comfort band')
    return RealizedThermalState(
        decision_step=step, measurement_step=measured, temperature_c=temperature,
        current_setpoint_c=_value(building.indoor_dry_bulb_temperature_cooling_set_point, step, 'current setpoint', constant=True),
        current_comfort_band_c=band,
        current_occupants=_value(building.occupant_count, step, 'current occupancy', constant=True),
        last_cooling_electricity_kwh=0. if step == 0 else _value(building.cooling_device.electricity_consumption, measured, 'last cooling electricity'),
        has_completed_measurement=step > 0,
        reference_temperature_c=reference_temperature,
        reference_measurement_step=None if reference is None else measured,
    )
