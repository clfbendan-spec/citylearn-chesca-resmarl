import numpy as np

# CityLearn 2.5 内置 phase 2 数据集用 1/2/3 步预测列名，CHESCA 原代码用 6h/12h/24h
OBSERVATION_NAME_FALLBACKS = {
    'direct_solar_irradiance_predicted_6h': ['direct_solar_irradiance_predicted_1'],
    'diffuse_solar_irradiance_predicted_6h': ['diffuse_solar_irradiance_predicted_1'],
    'direct_solar_irradiance_predicted_12h': ['direct_solar_irradiance_predicted_2'],
    'diffuse_solar_irradiance_predicted_12h': ['diffuse_solar_irradiance_predicted_2'],
    'direct_solar_irradiance_predicted_24h': ['direct_solar_irradiance_predicted_3'],
    'diffuse_solar_irradiance_predicted_24h': ['diffuse_solar_irradiance_predicted_3'],
}


def _observation_name_aliases(name):
    aliases = list(OBSERVATION_NAME_FALLBACKS.get(name, ()))
    if 'indoor_dry_bulb_temperature_set_point_' in name:
        aliases.append(
            name.replace(
                'indoor_dry_bulb_temperature_set_point_',
                'indoor_dry_bulb_temperature_cooling_set_point_',
            )
        )
    return aliases


def observation_index(observation_names, name):
    if name in observation_names:
        return observation_names.index(name)
    for alt in _observation_name_aliases(name):
        if alt in observation_names:
            return observation_names.index(alt)
    raise ValueError(f'{name!r} is not in list')


def observation_value(observations, observation_names, name):
    return observations[observation_index(observation_names, name)]


def get_observation_names_with_building(observation_names):
    """
    Returns the observation names for a specific building
    """
    observation_names_by_building = observation_names.copy()
    for i, name in enumerate(observation_names_by_building):
        ocu = 0
        for j in range(i+1, len(observation_names_by_building)):
            if name == observation_names_by_building[j]:
                ocu += 1
                observation_names_by_building[j] = f"{name}_{ocu}"
                observation_names_by_building[i] = f"{name}_{0}"

    return observation_names_by_building


