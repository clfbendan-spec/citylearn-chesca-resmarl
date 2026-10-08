"""
ForecastAgent — CHESCA 阶段1：时序预测模块
==========================================

【作用】
  在每个时间步，根据当前观测和历史数据，预测未来 tau 步（默认 1 小时）的：
    · outdoor_temp        — 室外温度（全社区共用）
    · solar_generation    — 各楼光伏发电
    · non_shiftable_load  — 各楼不可调负荷（基础用电）
    · dhw_demand          — 各楼生活热水需求

【预测方法：三模型集成 (TimeSeriesEnsemble)】
  1. 预训练 XGBoost — 竞赛前离线训练好的模型（pretrained/*.json）
  2. 在线 XGBoost   — 仿真过程中用历史数据持续微调
  3. 历史均值       — 同小时历史观测的滑动平均（冷启动兜底）

  三个模型的权重会根据「上一步预测误差」动态调整（update_weights）。

【输出给谁用？】
  · initial_actions()      — 决定 DHW 加热、停电时光伏/负荷平衡
  · get_consumption_forecast() — 构造电池树搜索的状态向量
"""
import numpy as np
from checa.forecast_agent.ts_forecast_ensemble import TimeSeriesEnsemble
from checa.forecast_agent.utils import fast_closest_hour
from checa.utils import (
    building_net_electricity_consumption,
    observation_value,
    observation_value_optional,
)


class ForecastAgent:
    def __init__(self, env, tau, observation_names_b):
        """
        初始化预测模块。

        参数 tau：向前预测多少步（与 Checa.params['tau'] 一致，local_evaluation 里为 1）
        参数 observation_names_b：带建筑后缀的观测名列表，如 solar_generation_0
        """
        self.tau = tau
        self.env = env
        self.total_steps = 0
        self.n_buildings = len(self.env.buildings_metadata)
        self.observation_names_b = observation_names_b
        self.predicted_variables = ["solar_generation", "outdoor_temp", "dhw_demand", "non_shiftable_load", "occupancy", "cooling_demand", "dhw_usage_bool"]
        self.seen_steps = 0
        self.fitting_frequency = 1  # days
        self.days_until_fit = np.zeros(self.n_buildings)

        # Initialize lists to hold the expected values per hour
        self.hourly_expected_values = {
            'outdoor_temp': [[] for _ in range(24)],
            'solar_generation': [[[] for _ in range(24)] for _ in range(self.n_buildings)],
            'dhw_demand': [[[] for _ in range(24)] for _ in range(self.n_buildings)],
            'non_shiftable_load': [[[] for _ in range(24)] for _ in range(self.n_buildings)],
            'occupancy': [[[] for _ in range(24)] for _ in range(self.n_buildings)],
            'cooling_demand': [[[] for _ in range(24)] for _ in range(self.n_buildings)],
            'dhw_usage_bool': [[[] for _ in range(24)] for _ in range(self.n_buildings)],
            'net_electricity_consumption': [[[] for _ in range(24)] for _ in range(self.n_buildings)],
        }
        self.avg_expected_values = None

        # Initialize Specific datasets for XGBoost
        columns_non_shiftable_load = ['non_shiftable_load', 'cyc_hour1', 'cyc_hour2', 'cyc_day_type1', 'cyc_day_type2', 'exp_load', 'occupancy', 'annual_estimate']
        columns_solar_gen = ['solar_generation', 'cyc_hour1', 'cyc_hour2',  'exp_solar', 'direct_solar', 'diffuse_solar', 'direct_solar_6h', 'diffuse_solar_6h',
                             'direct_solar_12h', 'diffuse_solar_12h', 'direct_solar_24h', 'diffuse_solar_24h']
        columns_dhw_demand = ['dhw_demand', 'cyc_hour1', 'cyc_hour2', 'cyc_day_type1', 'cyc_day_type2', 'exp_dhw_demand', 'occupancy', 'annual_estimate']
        columns_outdoor_temp = ['outdoor_temp', 'cyc_hour1', 'cyc_hour2', 'cyc_day_type1', 'cyc_day_type2', 'direct_solar', 'diffuse_solar', 'exp_outdoor_temp']
        columns_occupancy = ['occupancy', 'cyc_hour1', 'cyc_hour2', 'cyc_day_type1', 'cyc_day_type2', 'exp_occupancy']
        columns_cooling_demand = ['cooling_demand', 'cyc_hour1', 'cyc_hour2', 'exp_cooling_demand', 'temp_out', 'temp_in', 'occupancy']
        columns_dhw_usage_bool = ['dhw_usage_bool', 'cyc_hour1', 'cyc_hour2', 'cyc_day_type1', 'cyc_day_type2', 'exp_dhw_usage_bool', 'occupancy']
        columns_net_electricity_consumption = ['net_electricity_consumption', 'cyc_hour1', 'cyc_hour2', 'cyc_day_type1', 'cyc_day_type2', 'occupancy', 'temp_out', 'temp_in', 'diff_temp_out', 'exp_net_electricity_consumption',
                                               'solar_generation', 'dhw_demand', 'non_shiftable_load', 'cooling_demand']
        self.variable_columns = {
            'non_shiftable_load': columns_non_shiftable_load,
            'solar_generation': columns_solar_gen,
            'dhw_demand': columns_dhw_demand,
            'outdoor_temp': columns_outdoor_temp,
            'occupancy': columns_occupancy,
            'cooling_demand': columns_cooling_demand,
            'dhw_usage_bool': columns_dhw_usage_bool,
            'net_electricity_consumption': columns_net_electricity_consumption
        }

        self.hist_data = {
            'outdoor_temp': [],
            'solar_generation': [[] for _ in range(self.n_buildings)],
            'non_shiftable_load': [[] for _ in range(self.n_buildings)],
            'dhw_demand': [[] for _ in range(self.n_buildings)],
            'occupancy': [[] for _ in range(self.n_buildings)],
            'cooling_demand': [[] for _ in range(self.n_buildings)],
            'dhw_usage_bool': [[] for _ in range(self.n_buildings)],
            'net_electricity_consumption': [[] for _ in range(self.n_buildings)]
        }

        # Initialize prediction models
        self.ensemble_models = {}
        outdoor_temp_args = {
            'steps_ahead': self.tau,
            'variable_name': 'outdoor_temp',
            'use_pretrained': True,
            'use_xgboost': True,
            'use_historical': True,
            'initial_weights': [1.0, 0.0, 0.0],  # pretrained xgboost, online xgboost, historical
            'weight_rate': 0.05,
            'error_exponent': 3.0
        }
        solar_generation_args = {
            'steps_ahead': self.tau,
            'variable_name': 'solar_generation',
            'use_pretrained': False,
            'use_xgboost': True,
            'use_historical': True,
            'initial_weights': [0.0, 0.1, 0.4],
            'weight_rate': 0.05,
            'error_exponent': 3.0
        }
        dhw_demand_args = {
            'steps_ahead': self.tau,
            'variable_name': 'dhw_demand',
            'use_pretrained': True,
            'use_xgboost': True,
            'use_historical': True,
            'initial_weights': [1.0, 0.0, 0.0],
            'weight_rate': 0.05,
            'error_exponent': 3.0
        }
        non_shiftable_load_args = {
            'steps_ahead': self.tau,
            'variable_name': 'non_shiftable_load',
            'use_pretrained': True,
            'use_xgboost': True,
            'use_historical': True,
            'initial_weights': [1.0, 0.0, 0.0],
            'weight_rate': 0.05,
            'error_exponent': 3.0
        }
        self.ensemble_models['outdoor_temp'] = TimeSeriesEnsemble(**outdoor_temp_args)
        self.ensemble_models['solar_generation'] = [TimeSeriesEnsemble(**solar_generation_args) for _ in range(self.n_buildings)]
        #self.ensemble_models['occupancy'] = [TimeSeriesEnsemble(**occupancy_args) for _ in range(self.n_buildings)]
        self.ensemble_models['dhw_demand'] = [TimeSeriesEnsemble(**dhw_demand_args) for _ in range(self.n_buildings)]
        self.ensemble_models['non_shiftable_load'] = [TimeSeriesEnsemble(**non_shiftable_load_args) for _ in range(self.n_buildings)]
        #self.ensemble_models['cooling_demand'] = [TimeSeriesEnsemble() for _ in range(self.n_buildings)]
        #self.ensemble_models['dhw_usage_bool'] = [TimeSeriesEnsemble() for _ in range(self.n_buildings)]

    def compute_forecast(self, observations):
        """
        阶段1 主入口：预测未来 tau 步的关键变量。

        每步流程：
          1. save_data_and_get_cur_states — 把当前观测写入历史，构造 XGBoost 特征向量
          2. update_weights — 用「上一步真实值 vs 预测值」调整三模型权重
          3. 对每栋楼调用 ensemble_models[变量].predict() 得到未来 tau 步预测
          4. 每天结束（hour==24）可选触发在线 XGBoost 重训练 fit_data

        返回 predictions_dict，结构示例：
          {
            'outdoor_temp': [t+1预测, ...],
            0: {'solar_generation': [...], 'dhw_demand': [...], 'non_shiftable_load': [...]},
            1: {...},
            2: {...},
          }
        """
        predictions_dict = {b: {} for b in range(self.n_buildings)}

        hour = int(observation_value(observations, self.observation_names_b, 'hour'))

        # 保存观测到 hist_data / hourly_expected_values，并构造 XGBoost 输入特征
        cur_states = self.save_data_and_get_cur_states(observations)

        # 从第 2 步起：根据上一步预测误差，动态调整预训练/在线/历史 三模型权重
        if self.seen_steps > 0:
            self.update_weights(observations)

        for b in range(self.n_buildings):
            # 每天最后一个小时（hour==24）：用当天积累的历史重训在线 XGBoost（每 fitting_frequency 天一次）
            if hour == 24 and self.seen_steps > 0:
                #print(self.days_until_fit[b])
                if self.days_until_fit[b] == 0:
                    self.days_until_fit[b] = self.fitting_frequency - 1
                    self.ensemble_models['solar_generation'][b].fit_data(hour, np.stack(self.hist_data['solar_generation'][b]), self.seen_steps)
                    #self.ensemble_models['occupancy'][b].fit_data(hour, np.stack(self.hist_data['occupancy'][b]), self.seen_steps)
                    self.ensemble_models['dhw_demand'][b].fit_data(hour, np.stack(self.hist_data['dhw_demand'][b]), self.seen_steps)
                    self.ensemble_models['non_shiftable_load'][b].fit_data(hour, np.stack(self.hist_data['non_shiftable_load'][b]), self.seen_steps)

                    if b == 0: # Only compute it once
                        self.ensemble_models['outdoor_temp'].fit_data(hour, np.stack(self.hist_data['outdoor_temp']), self.seen_steps)
                else:
                    self.days_until_fit[b] -= 1

            # 对建筑 b 调用集成模型预测未来 tau 步
            predictions_dict[b]['solar_generation'] = self.ensemble_models['solar_generation'][b].predict(hour, cur_states['solar_generation'][b], self.hourly_expected_values['solar_generation'][b])
            predictions_dict[b]['dhw_demand'] = self.ensemble_models['dhw_demand'][b].predict(hour, cur_states['dhw_demand'][b], self.hourly_expected_values['dhw_demand'][b])
            predictions_dict[b]['non_shiftable_load'] = self.ensemble_models['non_shiftable_load'][b].predict(hour, cur_states['non_shiftable_load'][b], self.hourly_expected_values['non_shiftable_load'][b])
            # 室外温度全社区共用，只在 b==0 时预测一次
            if b == 0:
                predictions_dict['outdoor_temp'] = self.ensemble_models['outdoor_temp'].predict(hour, cur_states['outdoor_temp'], self.hourly_expected_values['outdoor_temp'])

        self.step()  # ForecastAgent 内部步计数 +1
        return predictions_dict

    def step(self):
        self.seen_steps += 1

    def update_weights(self, observations):
        new_outdoor_temp = observations[self.observation_names_b.index('outdoor_dry_bulb_temperature')]
        self.ensemble_models['outdoor_temp'].update_weights(new_outdoor_temp)

        for b in range(self.n_buildings):
            new_solar_generation = observations[self.observation_names_b.index('solar_generation_' + str(b))]
            #new_occupancy = observations[self.observation_names_b.index('occupant_count_' + str(b))]
            new_dhw_demand = observations[self.observation_names_b.index('dhw_demand_' + str(b))]
            new_non_shiftable_load = observations[self.observation_names_b.index('non_shiftable_load_' + str(b))]

            self.ensemble_models['solar_generation'][b].update_weights(new_solar_generation)
            #self.ensemble_models['occupancy'][b].update_weights(new_occupancy)
            self.ensemble_models['dhw_demand'][b].update_weights(new_dhw_demand)
            self.ensemble_models['non_shiftable_load'][b].update_weights(new_non_shiftable_load)

    def get_expected_values(self, hour):
        if hour == 24:
            used_hour = 0
        else:
            used_hour = hour  # It's hour+1 but -1 for indexing

        expected_values = {
            'outdoor_temp': 0,
            'solar_generation': [0 for _ in range(self.n_buildings)],
            'occupancy': [0 for _ in range(self.n_buildings)],
            'dhw_demand': [0 for _ in range(self.n_buildings)],
            'non_shiftable_load': [0 for _ in range(self.n_buildings)],
            'cooling_demand': [0 for _ in range(self.n_buildings)],
            'dhw_usage_bool': [0 for _ in range(self.n_buildings)],
            'net_electricity_consumption': [0 for _ in range(self.n_buildings)],
        }
        for var in self.predicted_variables:
            if var == 'outdoor_temp':
                if len(self.hourly_expected_values[var][used_hour]) >= 1:
                    expected_values[var] = np.mean(self.hourly_expected_values[var][used_hour])
                else:
                    hours_with_data = [i for i in range(24) if len(self.hourly_expected_values[var][i]) >= 1]
                    closest_hour_with_data = fast_closest_hour(hour, hours_with_data)
                    expected_values[var] = np.mean(self.hourly_expected_values[var][closest_hour_with_data])
            else:
                for b in range(self.n_buildings):
                    if len(self.hourly_expected_values[var][b][used_hour]) >= 1:
                        expected_values[var][b] = np.mean(self.hourly_expected_values[var][b][used_hour])
                    else:
                        hours_with_data = [i for i in range(24) if len(self.hourly_expected_values[var][b][i]) >= 1]
                        closest_hour_with_data = fast_closest_hour(hour, hours_with_data)
                        expected_values[var][b] = np.mean(self.hourly_expected_values[var][b][closest_hour_with_data])

        return expected_values

    def save_data_and_get_cur_states(self, observations):
        """
        Given the observations, save the data and return the current states.
        """

        names = self.observation_names_b
        hour = observation_value(observations, names, 'hour')
        temp_out = observation_value(observations, names, 'outdoor_dry_bulb_temperature')
        cyclical_hour = np.array([np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)])
        day_type = observation_value(observations, names, 'day_type')
        cyclical_day_type = np.array([np.sin(2 * np.pi * day_type / 7), np.cos(2 * np.pi * day_type / 7)])
        direct_sol = observation_value(observations, names, 'direct_solar_irradiance')
        diff_sol = observation_value(observations, names, 'diffuse_solar_irradiance')
        direct_sol_6h = observation_value(observations, names, 'direct_solar_irradiance_predicted_6h')
        diff_sol_6h = observation_value(observations, names, 'diffuse_solar_irradiance_predicted_6h')
        direct_sol_12h = observation_value(observations, names, 'direct_solar_irradiance_predicted_12h')
        diff_sol_12h = observation_value(observations, names, 'diffuse_solar_irradiance_predicted_12h')
        direct_sol_24h = observation_value(observations, names, 'direct_solar_irradiance_predicted_24h')
        diff_sol_24h = observation_value(observations, names, 'diffuse_solar_irradiance_predicted_24h')

        self.hourly_expected_values['outdoor_temp'][hour - 1].append(temp_out)

        cur_solar_generation = []
        cur_occupancy = []
        cur_dhw_demand = []
        cur_non_shiftable_load = []
        cur_cooling_demand = []
        cur_dhw_usage_bool = []
        electricity_consumption = []
        for b in range(self.n_buildings):
            cur_solar_generation.append(observations[self.observation_names_b.index("solar_generation_" + str(b))])
            # 2023 有 occupant_count；部分数据集缺失时默认 1（视为有人）
            cur_occupancy.append(float(observation_value_optional(
                observations, self.observation_names_b, "occupant_count_" + str(b), default=1.0
            )))
            cur_dhw_demand.append(float(observation_value_optional(
                observations, self.observation_names_b, "dhw_demand_" + str(b), default=0.0
            )))
            cur_non_shiftable_load.append(observations[self.observation_names_b.index("non_shiftable_load_" + str(b))])
            cur_cooling_demand.append(float(observation_value_optional(
                observations, self.observation_names_b, "cooling_demand_" + str(b), default=0.0
            )))
            cur_dhw_usage_bool.append(cur_dhw_demand[b] > 0.001)
            obs_net = observations[self.observation_names_b.index("net_electricity_consumption_" + str(b))]
            electricity_consumption.append(building_net_electricity_consumption(
                self.env, b, default=obs_net
            ))
            self.hourly_expected_values['solar_generation'][b][hour - 1].append(cur_solar_generation[b])
            self.hourly_expected_values['occupancy'][b][hour - 1].append(cur_occupancy[b])
            self.hourly_expected_values['dhw_demand'][b][hour - 1].append(cur_dhw_demand[b])
            self.hourly_expected_values['non_shiftable_load'][b][hour - 1].append(cur_non_shiftable_load[b])
            self.hourly_expected_values['cooling_demand'][b][hour - 1].append(cur_cooling_demand[b])
            self.hourly_expected_values['dhw_usage_bool'][b][hour - 1].append(cur_dhw_usage_bool[b])
            self.hourly_expected_values['net_electricity_consumption'][b][hour - 1].append(electricity_consumption[b])

        # Get expected values and save them. Then get current state for XGBoost
        expected_values = self.get_expected_values(hour)
        self.avg_expected_values = expected_values

        outdoor_temp_X = np.array([temp_out, cyclical_hour[0], cyclical_hour[1], cyclical_day_type[0], cyclical_day_type[1], direct_sol, diff_sol, expected_values['outdoor_temp']])
        self.hist_data['outdoor_temp'].append(outdoor_temp_X)
        solar_generation_X = []
        occupancy_X = []
        dhw_demand_X = []
        non_shiftable_load_X = []
        cooling_demand_X = []
        dhw_usage_bool_X = []
        net_electricity_consumption_X = []
        for b in range(self.n_buildings):
            occupancy = cur_occupancy[b]
            temp_in = float(observation_value_optional(
                observations, self.observation_names_b, "indoor_dry_bulb_temperature_" + str(b), default=temp_out
            ))
            annual_dhw_demand_estimate = self.env.buildings_metadata[b]['annual_dhw_demand_estimate']
            annual_non_shiftable_load_estimate = self.env.buildings_metadata[b]['annual_non_shiftable_load_estimate']

            # Get the current state
            solar_generation_X.append(np.array([cur_solar_generation[b], cyclical_hour[0], cyclical_hour[1], expected_values['solar_generation'][b],
                                                direct_sol, diff_sol, direct_sol_6h, diff_sol_6h, direct_sol_12h, diff_sol_12h, direct_sol_24h, diff_sol_24h]))
            occupancy_X.append(np.array([cur_occupancy[b], cyclical_hour[0], cyclical_hour[1], cyclical_day_type[0], cyclical_day_type[1], expected_values['occupancy'][b]]))
            dhw_demand_X.append(np.array([cur_dhw_demand[b], cyclical_hour[0], cyclical_hour[1], cyclical_day_type[0], cyclical_day_type[1], expected_values['dhw_demand'][b], occupancy, annual_dhw_demand_estimate]))
            non_shiftable_load_X.append(np.array([cur_non_shiftable_load[b], cyclical_hour[0], cyclical_hour[1], cyclical_day_type[0], cyclical_day_type[1], expected_values['non_shiftable_load'][b], occupancy, annual_non_shiftable_load_estimate]))
            cooling_demand_X.append(np.array([cur_cooling_demand[b], cyclical_hour[0], cyclical_hour[1], expected_values['cooling_demand'][b], temp_out, temp_in, occupancy]))
            dhw_usage_bool_X.append(np.array([cur_dhw_usage_bool[b], cyclical_hour[0], cyclical_hour[1], cyclical_day_type[0], cyclical_day_type[1], expected_values['dhw_usage_bool'][b], occupancy]))
            net_electricity_consumption_X.append(np.array([electricity_consumption[b], cyclical_hour[0], cyclical_hour[1], cyclical_day_type[0], cyclical_day_type[1], occupancy, temp_out, temp_in, expected_values['outdoor_temp'] - temp_out,
                                                           expected_values['net_electricity_consumption'][b], cur_solar_generation[b], cur_dhw_demand[b], cur_non_shiftable_load[b], cur_cooling_demand[b]]))

            #
            # Add it to the historical data
            self.hist_data['solar_generation'][b].append(solar_generation_X[b])
            self.hist_data['occupancy'][b].append(occupancy_X[b])
            self.hist_data['dhw_demand'][b].append(dhw_demand_X[b])
            self.hist_data['non_shiftable_load'][b].append(non_shiftable_load_X[b])
            self.hist_data['cooling_demand'][b].append(cooling_demand_X[b])
            self.hist_data['dhw_usage_bool'][b].append(dhw_usage_bool_X[b])
            self.hist_data['net_electricity_consumption'][b].append(net_electricity_consumption_X[b])

        cur_states = {
            'outdoor_temp': outdoor_temp_X,
            'solar_generation': solar_generation_X,
            'occupancy': occupancy_X,
            'dhw_demand': dhw_demand_X,
            'non_shiftable_load': non_shiftable_load_X,
            'cooling_demand': cooling_demand_X,
            'dhw_usage_bool': dhw_usage_bool_X,
            'net_electricity_consumption': net_electricity_consumption_X,
        }
        return cur_states



