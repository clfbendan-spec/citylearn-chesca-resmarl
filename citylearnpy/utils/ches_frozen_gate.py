"""Opt-in replay of the frozen 2026-11-04 CHESCA temperature gate."""
import numpy as np


def attach_frozen_gate(agent, env):
    original = agent.apply_residual_correction

    def correction(actions, observations):
        base = np.asarray(original(actions, observations), dtype=float).reshape(len(env.buildings), 3)
        final = base.copy()
        t = int(env.time_step)
        for j, building in enumerate(env.buildings):
            if agent.outage_details[j]['outage_flag']:
                continue
            previous = float(building.indoor_dry_bulb_temperature[max(0, t - 1)])
            setpoint = float(building.indoor_dry_bulb_temperature_cooling_set_point[t])
            if previous - setpoint > 0.5:
                final[j, 2] = np.clip(base[j, 2] * 1.2, 0., 1.)
            if abs(final[j, 2] - base[j, 2]) > 1e-12:
                agent.predicted_cooling_demand[j], _ = agent.cooling_device_controller[j].compute_pred_cooling_consumption(
                    final[j, 2], agent.forecasts['outdoor_temp'][0])
        return final.ravel().tolist()

    agent.apply_residual_correction = correction
