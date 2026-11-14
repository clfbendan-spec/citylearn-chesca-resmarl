"""Fixed COP approximation for ingested exogenous thermal demand."""
import numpy as np
from citylearn.energy_model import HeatPump


class FixedCopHeatPump(HeatPump):
    def __init__(self, fixed_cop, **kwargs):
        self.fixed_cop = float(fixed_cop)
        if not np.isfinite(self.fixed_cop) or not 0 < self.fixed_cop <= 20:
            raise ValueError("fixed_cop must be in (0, 20]")
        super().__init__(**kwargs)

    def get_cop(self, outdoor_dry_bulb_temperature, heating):
        return np.full_like(np.asarray(outdoor_dry_bulb_temperature), self.fixed_cop, dtype=float)
