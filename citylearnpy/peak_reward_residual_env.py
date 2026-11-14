"""Explicit opt-in team peak reward for the causal baseline residual environment."""
import numpy as np
from causal_peak_residual_env import CausalPeakResidualEnv
from community_peak_objective import CommunityPeakObjective, PeakObjectiveConfig
from utils.env import unwrap_citylearn_env


class PeakRewardResidualEnv(CausalPeakResidualEnv):
    def __init__(self, env_config):
        self._objective_config = PeakObjectiveConfig(**dict(env_config.get('community_peak_reward', {})))
        self._objective = CommunityPeakObjective(self._objective_config)
        self.last_objective_terms = {}
        self.episode_objective_terms = {}
        super().__init__(env_config)

    def reset(self, *, seed=None, options=None):
        obs, info = super().reset(seed=seed, options=options)
        self._objective = CommunityPeakObjective(self._objective_config)
        self.last_objective_terms = {}
        self.episode_objective_terms = {key:0. for key in ('peak','comfort','throughput','terminal','total')}
        return obs, info

    def step(self, action_dict):
        ce = unwrap_citylearn_env(self)
        index = int(ce.time_step)
        obs, old_reward, terminated, truncated, info = super().step(action_dict)
        done = terminated.get('__all__',False) or truncated.get('__all__',False)
        indices = [index]
        # Existing KPI traces include the terminal observation at n+1 as well.
        if done and int(ce.time_step)>index:
            indices.append(int(ce.time_step))
        terms = {key:0. for key in self.episode_objective_terms}
        for j, t in enumerate(indices):
            power = sum(float(b.net_electricity_consumption[t]) for b in ce.buildings)
            violations = 0
            throughput = 0.
            for b in ce.buildings:
                band = float(np.asarray(b.comfort_band).ravel()[0])
                occupied = float(b.energy_simulation.occupant_count[t])>0
                violations += int(occupied and abs(float(b.indoor_dry_bulb_temperature[t])-float(b.indoor_dry_bulb_temperature_cooling_set_point[t]))>band)
                throughput += abs(float(b.electrical_storage_electricity_consumption[t]))
            shortfall = 0.
            if done and j==len(indices)-1:
                for b in ce.buildings:
                    s=b.electrical_storage
                    energy=float(s.soc[max(0,s.time_step-1)])*s.capacity
                    target=max(float(s.initial_soc),self._objective_config.terminal_soc)*s.capacity
                    shortfall+=max(0.,target-energy)
            current = self._objective.update(power,violations,throughput,shortfall)
            for key in terms:
                terms[key]+=current[key]
        self.last_objective_terms = terms
        for key in terms:
            self.episode_objective_terms[key]+=terms[key]
        # Identical community reward for each independent actor, not summed 3x.
        reward = {key:float(terms['total']) for key in obs}
        return obs, reward, terminated, truncated, info
