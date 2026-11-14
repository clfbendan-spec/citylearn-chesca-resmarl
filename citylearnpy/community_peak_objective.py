"""Undiscounted community peak objective, separate from legacy price rewards."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PeakObjectiveConfig:
    peak_weight: float = 1.
    comfort_weight: float = 1.
    throughput_weight: float = .001
    terminal_energy_weight: float = 10.
    terminal_soc: float = .6

    def __post_init__(self):
        if min(self.peak_weight, self.comfort_weight, self.throughput_weight, self.terminal_energy_weight) < 0 or not 0 <= self.terminal_soc <= 1:
            raise ValueError('Invalid peak objective configuration')


class CommunityPeakObjective:
    def __init__(self, config=None):
        self.config = config or PeakObjectiveConfig()
        self.peak = 0.

    def update(self, power, occupied_violations=0, throughput=0., terminal_shortfall=0.):
        if min(occupied_violations, throughput, terminal_shortfall) < 0:
            raise ValueError('Penalty inputs must be nonnegative')
        new_peak = max(self.peak, float(power), 0.)
        terms = dict(peak=-self.config.peak_weight*(new_peak-self.peak),
                     comfort=-self.config.comfort_weight*float(occupied_violations),
                     throughput=-self.config.throughput_weight*float(throughput),
                     terminal=-self.config.terminal_energy_weight*float(terminal_shortfall))
        self.peak = new_peak
        terms['total'] = sum(terms.values())
        return terms
