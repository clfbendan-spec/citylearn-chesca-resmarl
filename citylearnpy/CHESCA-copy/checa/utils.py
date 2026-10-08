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

# 与 CityLearn CostFunction.discomfort / EnergySimulation 默认一致
DEFAULT_COMFORT_BAND = 2.0


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


def observation_value_optional(observations, observation_names, name, default=None):
    """读取观测；名称及别名均不存在时返回 default，不抛错。"""
    try:
        return observation_value(observations, observation_names, name)
    except ValueError:
        return default


# CHESCA 面向 Challenge 2023：每楼 [DHW, ELE, TMP] 三动作 + 舒适/停电相关观测
CHESCA_REQUIRED_OBSERVATION_ROOTS = (
    'occupant_count',
    'cooling_demand',
    'dhw_demand',
    'indoor_dry_bulb_temperature',
    'power_outage',
    'dhw_storage_soc',
    'electrical_storage_soc',
    'solar_generation',
    'non_shiftable_load',
)
CHESCA_REQUIRED_ACTION_ROOTS = (
    'electrical_storage',
    'dhw_storage',
    'cooling_device',
)


def assert_chesca_schema_compatible(env):
    """
    校验当前 CityLearn / Wrapper 环境是否具备 CHESCA 所需观测与动作。

    Challenge 2022 phase_all 仅含电池动作，无 occupant_count / cooling_demand 等，
    与 CHESCA（2023 冷机+DHW+电池）不兼容；应提前失败并给出可操作提示。
    """
    if env is None:
        raise ValueError('env 为空，无法校验 CHESCA schema 兼容性')

    obs_names = getattr(env, 'observation_names', None)
    if not obs_names:
        raise ValueError('环境缺少 observation_names，无法校验 CHESCA 兼容性')
    flat_obs = obs_names[0] if isinstance(obs_names[0], (list, tuple)) else list(obs_names)
    obs_set = set(flat_obs)
    missing_obs = [name for name in CHESCA_REQUIRED_OBSERVATION_ROOTS if name not in obs_set]

    action_names = getattr(env, 'action_names', None)
    missing_actions = []
    if action_names:
        flat_act = action_names[0] if isinstance(action_names[0], (list, tuple)) else list(action_names)
        act_set = set(flat_act)
        missing_actions = [name for name in CHESCA_REQUIRED_ACTION_ROOTS if name not in act_set]

    if not missing_obs and not missing_actions:
        return

    lines = [
        '当前数据集与 CHESCA 不兼容（CHESCA 面向 CityLearn Challenge 2023：冷机 + DHW + 电池）。',
    ]
    if missing_obs:
        lines.append(f'缺少观测: {", ".join(missing_obs)}')
    if missing_actions:
        lines.append(f'缺少动作: {", ".join(missing_actions)}')
    lines.extend([
        '请改用例如: citylearn_challenge_2023_phase_2_local_evaluation /',
        '  citylearn_challenge_2023_phase_2_online_evaluation_1 / phase_3_*。',
        '若要跑 citylearn_challenge_2022_phase_all（仅电池），请使用 Multi-agent.py 或 NOCONTROL，',
        '不要使用 CHESCA.py（CHESCA）。',
    ])
    raise ValueError('\n'.join(lines))


def _last_scalar(series, default=None):
    if series is None:
        return default
    try:
        if hasattr(series, '__len__') and len(series) > 0:
            return float(series[-1])
        return float(series)
    except (TypeError, ValueError, IndexError):
        return default


def _fmt_opt(value, digits=2):
    if value is None:
        return '-'
    try:
        return f'{float(value):.{digits}f}'
    except (TypeError, ValueError):
        return str(value)


def resolve_citylearn_env(env):
    """
    从 WrapperEnv / Gym 包装中取出真正的 CityLearnEnv（带 .buildings 与 .time_step）。

    Agent 侧通常是 CHESCA.WrapperEnv：虽转发 .buildings，但没有
    .time_step，不能当作真实环境直接用来读储能时序。
    """
    if env is None:
        return None
    buildings = getattr(env, 'buildings', None)
    if buildings is not None and hasattr(env, 'time_step'):
        try:
            len(buildings)
            return env
        except Exception:
            pass
    for attr in ('_env', 'unwrapped'):
        inner = getattr(env, attr, None)
        if inner is None or inner is env:
            continue
        resolved = resolve_citylearn_env(inner)
        if resolved is not None:
            return resolved
    return None


def citylearn_current_series_value(series, time_step: int) -> float:
    """
    读取 CityLearn 在「当前决策时刻」应使用的时序值。

    CityLearn 2.x 在 step t 内把运行量写入 series[t]，步进后 time_step 变为 t+1，
    而 series[t+1] 尚未写入（多为 0）。观测向量里下列量正是读的 series[time_step]，
    因此在 t>0 时会错误地变成 0：
      · electrical_storage_soc / dhw_storage_soc（及 cooling/heating_storage_soc）
      · net_electricity_consumption（及各类 *_electricity_consumption）

    决策时刻应读上一已完成步：t==0 用 series[0]，否则用 series[t-1]。

    注意：cooling_demand / dhw_demand 观测在 2.5 中会预填仿真负荷曲线到当前
    time_step，一般不受此 off-by-one 影响，无需改读。
    """
    if series is None:
        return 0.0
    arr = np.asarray(series, dtype=float)
    if arr.size == 0:
        return 0.0
    idx = 0 if int(time_step) <= 0 else min(int(time_step) - 1, arr.size - 1)
    return float(arr[idx])


def building_storage_soc(env, building_index: int, storage_attr: str, default=None):
    """
    从建筑储能设备读取真实当前 SOC（规避观测 off-by-one）。

    storage_attr 例：'electrical_storage'、'dhw_storage'、
    'cooling_storage'、'heating_storage'。
    无法解析环境时返回 default（调用方可回退到观测）。
    """
    real_env = resolve_citylearn_env(env)
    if real_env is None or building_index >= len(real_env.buildings):
        return default
    building = real_env.buildings[building_index]
    storage = getattr(building, storage_attr, None)
    if storage is None or getattr(storage, 'soc', None) is None:
        return 0.0 if default is None else default
    return citylearn_current_series_value(storage.soc, int(real_env.time_step))


def building_net_electricity_consumption(env, building_index: int, default=None):
    """从建筑读取上一已完成步的净用电（规避观测 off-by-one）。"""
    real_env = resolve_citylearn_env(env)
    if real_env is None or building_index >= len(real_env.buildings):
        return default
    building = real_env.buildings[building_index]
    series = getattr(building, 'net_electricity_consumption', None)
    if series is None:
        return 0.0 if default is None else default
    return citylearn_current_series_value(series, int(real_env.time_step))


def compute_hot_discomfort_from_values(
    indoor,
    cooling_sp,
    band=None,
    occupant=None,
    *,
    indoor_obs=None,
    indoor_source='',
    setpoint_source='',
    dynamics_note='',
    heating_sp=None,
):
    """由标量温度等计算高温不适字段（逐步判定与 episode 回填共用）。"""
    if band is None:
        band = DEFAULT_COMFORT_BAND
    if occupant is None:
        occupant = 1.0

    result = {
        'kpi_indoor_temp': None if indoor is None else float(indoor),
        'kpi_indoor_temp_obs': None if indoor_obs is None else float(indoor_obs),
        'kpi_indoor_source': indoor_source or '',
        'kpi_cooling_set_point': None if cooling_sp is None else float(cooling_sp),
        'kpi_heating_set_point': None if heating_sp is None else float(heating_sp),
        'kpi_comfort_band': float(band),
        'kpi_occupant_count': float(occupant),
        'kpi_setpoint_source': setpoint_source or '',
        'kpi_dynamics_note': dynamics_note or '',
        'kpi_cooling_delta': None,
        'kpi_hot_threshold': None,
        'kpi_is_occupied': bool(float(occupant) > 0.0),
        'kpi_is_hot_discomfort': False,
        'kpi_hot_discomfort_skip_reason': '',
    }
    if indoor is None or cooling_sp is None:
        result['kpi_hot_discomfort_skip_reason'] = '缺少室内温度或制冷设定点，无法按 KPI 判定'
        return result

    cooling_delta = float(indoor) - float(cooling_sp)
    hot_threshold = float(cooling_sp) + float(band)
    occupied = float(occupant) > 0.0
    is_hot = occupied and (cooling_delta > float(band))
    result['kpi_cooling_delta'] = float(cooling_delta)
    result['kpi_hot_threshold'] = float(hot_threshold)
    result['kpi_is_occupied'] = occupied
    result['kpi_is_hot_discomfort'] = bool(is_hot)
    if not occupied:
        result['kpi_hot_discomfort_skip_reason'] = '无人占用，本步不计入高温不适比例'
    return result


def compute_step_hot_discomfort(observations, observation_names_b, b, env=None):
    """
    决策时刻的高温不适估计。

    Agent.env 多为 WrapperEnv，必须 resolve_citylearn_env 才能读 buildings。
    Episode 结束时还会 backfill，与 evaluate() 使用同一温度序列。
    """
    indoor_obs = observation_value_optional(
        observations, observation_names_b, f'indoor_dry_bulb_temperature_{b}'
    )
    cooling_sp = observation_value_optional(
        observations, observation_names_b, f'indoor_dry_bulb_temperature_cooling_set_point_{b}'
    )
    heating_sp = observation_value_optional(
        observations, observation_names_b, f'indoor_dry_bulb_temperature_heating_set_point_{b}'
    )
    generic_sp = observation_value_optional(
        observations, observation_names_b, f'indoor_dry_bulb_temperature_set_point_{b}'
    )
    band = observation_value_optional(
        observations, observation_names_b, f'comfort_band_{b}'
    )
    occupant = observation_value_optional(
        observations, observation_names_b, f'occupant_count_{b}'
    )
    setpoint_source = 'obs.cooling_set_point' if cooling_sp is not None else None
    indoor = indoor_obs
    indoor_source = 'obs.indoor'
    dynamics_note = ''

    real_env = resolve_citylearn_env(env)
    building = None
    if real_env is not None and b < len(real_env.buildings):
        building = real_env.buildings[b]

    if building is not None:
        indoor_dyn = _last_scalar(getattr(building, 'indoor_dry_bulb_temperature', None))
        cool_dyn = _last_scalar(getattr(building, 'indoor_dry_bulb_temperature_cooling_set_point', None))
        if indoor_dyn is not None:
            indoor = indoor_dyn
            indoor_source = 'building.indoor[-1]'
            if indoor_obs is not None and abs(float(indoor_dyn) - float(indoor_obs)) > 0.05:
                dynamics_note = (
                    f'观测室内={_fmt_opt(indoor_obs)}°C；'
                    f'动力学室内={_fmt_opt(indoor_dyn)}°C（判定用动力学）'
                )
            else:
                dynamics_note = f'动力学室内={_fmt_opt(indoor_dyn)}°C'
        if cool_dyn is not None:
            cooling_sp = cool_dyn
            setpoint_source = 'building.cooling_set_point[-1]'
        if heating_sp is None:
            heating_sp = _last_scalar(getattr(building, 'indoor_dry_bulb_temperature_heating_set_point', None))
        if band is None:
            band = _last_scalar(getattr(building, 'comfort_band', None))
        if occupant is None:
            occupant = _last_scalar(getattr(building, 'occupant_count', None), default=1.0)

    if cooling_sp is None and generic_sp is not None:
        cooling_sp = generic_sp
        setpoint_source = 'obs.set_point(fallback)'
    if cooling_sp is None:
        cooling_sp = generic_sp

    return compute_hot_discomfort_from_values(
        indoor,
        cooling_sp,
        band=band,
        occupant=occupant,
        indoor_obs=indoor_obs,
        indoor_source=indoor_source,
        setpoint_source=setpoint_source or '',
        dynamics_note=dynamics_note,
        heating_sp=heating_sp,
    )


def get_observation_names_with_building(observation_names):
    """
    Returns the observation names for a specific building
    """
    observation_names_by_building = observation_names.copy()
    for i, name in enumerate(observation_names_by_building):
        ocu = 0
        for j in range(i + 1, len(observation_names_by_building)):
            if name == observation_names_by_building[j]:
                ocu += 1
                observation_names_by_building[j] = f'{name}_{ocu}'
                observation_names_by_building[i] = f'{name}_{0}'

    return observation_names_by_building
