"""Versioned 54-feature environment with a shared reachable terminal SOC guard."""
import numpy as np
from gymnasium import spaces
from peak_reward_residual_env import PeakRewardResidualEnv
from causal_peak_controller import battery_post_energy
from utils.env import unwrap_citylearn_env

HORIZON_FEATURE_NAMES = ('remaining_fraction', 'remaining_hours_div24_clipped5')
FEATURE_VERSION = 'causal_peak_horizon_v2_54'


def horizon_features(step, state_count):
    actions = max(0, int(state_count)-1)
    remaining = max(0, actions-int(step))
    return np.array([remaining/max(1, actions), min(remaining/24., 5.)], dtype=np.float32)


def terminal_charge_action(storage, proposed, target_soc=.6):
    """Raise only an insufficient final action; never change the physical state."""
    target = max(float(storage.initial_soc), target_soc)*storage.capacity
    proposed = float(proposed)
    energy = battery_post_energy(storage, proposed*storage.nominal_power)
    if energy >= target:
        return proposed, dict(changed=False, feasible=True, target_energy=float(target))
    # Float32 action conversion must not turn an exact boundary into a tiny shortfall.
    goal = min(float(storage.capacity), float(target)+1e-6)
    if battery_post_energy(storage, storage.nominal_power) < goal:
        return 1., dict(changed=True, feasible=False, target_energy=float(target))
    low, high = proposed, 1.
    for _ in range(40):
        middle = (low+high)/2
        if battery_post_energy(storage, middle*storage.nominal_power) < goal:
            low = middle
        else:
            high = middle
    return high, dict(changed=True, feasible=True, target_energy=float(target))


class FiniteHorizonPeakEnv(PeakRewardResidualEnv):
    def __init__(self, env_config):
        self._terminal_prepare_diagnostics = []
        self._terminal_execution_diagnostics = []
        super().__init__(env_config)
        self.observation_space = spaces.Dict({
            key:spaces.Box(low=np.r_[space.low, [0.,0.]].astype(np.float32),
                           high=np.r_[space.high, [1.,5.]].astype(np.float32), dtype=np.float32)
            for key,space in dict(self.observation_space).items()})

    def _terminal_guard(self, action):
        ce=unwrap_citylearn_env(self)
        result=np.asarray(action,dtype=float).copy();diagnostics=[]
        if int(ce.time_step) != int(ce.episode_tracker.episode_time_steps)-2:
            return result,diagnostics
        for b,building in enumerate(ce.buildings):
            if building.power_outage:
                diagnostics.append(dict(changed=False,feasible=False,outage=True))
            else:
                result[3*b+1],diag=terminal_charge_action(building.electrical_storage,result[3*b+1],self._objective_config.terminal_soc)
                diagnostics.append(dict(**diag,outage=False))
        return result,diagnostics

    def _prepare_causal_baseline(self):
        super()._prepare_causal_baseline()
        self._a_base,self._terminal_prepare_diagnostics=self._terminal_guard(self._a_base)
        self._peak_diagnostics['strong_base']=self._a_base.tolist()

    def _finalize_composed_action(self,final,base):
        guarded=super()._finalize_composed_action(final,base)
        guarded,self._terminal_execution_diagnostics=self._terminal_guard(guarded)
        return guarded

    def _horizon_observations(self,obs):
        ce=unwrap_citylearn_env(self)
        extra=horizon_features(ce.time_step,ce.episode_tracker.episode_time_steps)
        return {key:np.r_[value,extra].astype(np.float32) for key,value in obs.items()}

    def reset(self,*,seed=None,options=None):
        self._terminal_prepare_diagnostics=[];self._terminal_execution_diagnostics=[]
        obs,info=super().reset(seed=seed,options=options)
        return self._horizon_observations(obs),info

    def step(self,action_dict):
        obs,reward,term,trunc,info=super().step(action_dict)
        return self._horizon_observations(obs),reward,term,trunc,info
