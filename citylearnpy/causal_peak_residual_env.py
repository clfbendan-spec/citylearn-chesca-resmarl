"""Opt-in residual environment around the verified causal peak rule baseline."""
import numpy as np
from gymnasium import spaces
from chesca_residual_env import ChescaResidualEnv
from utils.env import unwrap_citylearn_env
from causal_peak_controller import (CausalPeakConfig, PRESSURE_FEATURE_NAMES,
    prepare_causal_peak, pressure_features, guard_residual)


class CausalPeakResidualEnv(ChescaResidualEnv):
    def __init__(self, env_config):
        self._preserve_dataset_outages = True
        self._peak_config = CausalPeakConfig(**dict(env_config.get('causal_peak', {})))
        self._peak_diagnostics = {}
        self._peak_guard_diagnostics = {}
        super().__init__(env_config)
        if not self._r_enabled:
            raise ValueError('CausalPeakResidualEnv requires enabled chesca_residual')
        if self._r_cfg.safety_projection_enabled:
            raise ValueError('Use the shared causal reserve guard, not an additional safety projection')
        mask = self._r_cfg.action_mask
        if mask.get('dhw') or mask.get('tmp'):
            raise ValueError('The verified causal baseline only supports battery residuals')
        self.observation_space = spaces.Dict({
            key: spaces.Box(low=np.r_[space.low, np.full(len(PRESSURE_FEATURE_NAMES), -5.)].astype(np.float32),
                            high=np.r_[space.high, np.full(len(PRESSURE_FEATURE_NAMES), 5.)].astype(np.float32), dtype=np.float32)
            for key, space in dict(self.observation_space).items()})

    @staticmethod
    def _pin_outage_seed(env, seed=90000):
        """The opt-in environment retains schema outage seeds on BOTH paths."""
        return None

    def _prepare_causal_baseline(self):
        ce = unwrap_citylearn_env(self)
        raw = dict(zip(self._mirror_agent.observation_names_b, np.asarray(self._m_obs).ravel()))
        forecast = self._mirror_agent.forecasts
        next_ns = sum(float(forecast[b]['non_shiftable_load'][0]) for b in range(self._n_b))
        self._a_base, self._peak_diagnostics = prepare_causal_peak(
            ce.buildings, raw, self._a_base, int(ce.time_step), self._peak_config, next_ns)

    def _augment_causal_observations(self, obs):
        ce = unwrap_citylearn_env(self)
        out = {}
        for b, key in enumerate(self._agent_ids_list):
            own = np.asarray(obs[key], dtype=np.float32).copy()
            # Parent already appended prior from raw CHESCA; replace with the stronger baseline.
            if self._prior_dim:
                own[-self._prior_dim:] = self._prior_only_extra(key)
            out[key] = np.r_[own, pressure_features(ce.buildings[b], b, self._peak_diagnostics, self._peak_config)].astype(np.float32)
        return out

    def reset(self, *, seed=None, options=None):
        self._peak_diagnostics = {}
        self._peak_guard_diagnostics = {}
        obs, info = super().reset(seed=seed, options=options)
        self._prepare_causal_baseline()
        return self._augment_causal_observations(obs), info

    def _finalize_composed_action(self, final, base):
        ce = unwrap_citylearn_env(self)
        guarded, self._peak_guard_diagnostics = guard_residual(ce.buildings, final, base, self._peak_config)
        return guarded

    def step(self, action_dict):
        obs, reward, terminated, truncated, info = super().step(action_dict)
        # Parent has advanced both environments and produced raw CHESCA for the new state.
        self._prepare_causal_baseline()
        return self._augment_causal_observations(obs), reward, terminated, truncated, info
