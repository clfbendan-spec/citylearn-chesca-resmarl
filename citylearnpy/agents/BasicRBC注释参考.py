"""
BasicRBC 中文注释参考（对照 citylearn.agents.rbc）

源码位置（conda cl2 环境）：
  site-packages/citylearn/agents/rbc.py

继承关系：
  Agent → RBC → HourRBC → BasicRBC

CentralizedRBC.py 使用的即 BasicRBC：
  from citylearn.agents.rbc import BasicRBC as Agent

本文件仅作阅读说明，不参与 import；运行仍使用库内原版类。
"""

from typing import Any, List, Mapping, Union

from citylearn.agents.base import Agent
from citylearn.building import Building
from citylearn.citylearn import CityLearnEnv


# ---------------------------------------------------------------------------
# RBC：规则控制器基类，无额外逻辑，仅继承 Agent 的观测/动作解析
# ---------------------------------------------------------------------------
class RBC(Agent):
    def __init__(self, env: CityLearnEnv, **kwargs: Any):
        super().__init__(env, **kwargs)


# ---------------------------------------------------------------------------
# HourRBC：按「小时」查表的规则控制器
# ---------------------------------------------------------------------------
class HourRBC(RBC):
    """
    核心思想：预先为每个 controllable 设备、每个小时 (1–24) 设定固定动作值；
    predict 时读取观测中的 hour，查 action_map 返回动作。

    action_map 结构（central_agent 多建筑时）：
      List[ Dict[ action_name, Dict[ hour, value ] ] ]
      外层 list 长度 = 1（central）；内层 key 如 electrical_storage / cooling_device
    """

    def __init__(self, env: CityLearnEnv, action_map=None, **kwargs: Any):
        super().__init__(env, **kwargs)
        self.action_map = action_map  # 触发 setter，BasicRBC 会在此生成默认表

    def predict(self, observations: List[List[float]], deterministic: bool = None) -> List[List[float]]:
        """
        根据当前观测中的 hour 字段，从 action_map 查表得到动作。

        参数 observations：与 env 一致，central 时为 [[...]]。
        返回 actions：与 action_names 顺序一致的动作列表。
        """
        actions = []

        if self.action_map is None:
            # 未配置 map 时退化为 Agent 基类随机动作
            actions = super().predict(observations, deterministic=deterministic)
        else:
            # 遍历每个 agent（central 仅 1 个）、其动作名、观测名、观测向量
            for m, a, n, o in zip(self.action_map, self.action_names, self.observation_names, observations):
                # 从观测向量中取出 hour（归一化或整数编码均可）
                hour_observation = o[n.index('hour')]
                hour = int(round(hour_observation))

                # 兼容 0–23 与 1–24 两种 hour 编码
                hour_candidates = []
                for candidate in (hour, hour % 24, ((hour - 1) % 24) + 1):
                    if candidate not in hour_candidates:
                        hour_candidates.append(candidate)

                actions_ = []
                for a_ in a:
                    # 对每个动作名，按候选 hour 查表
                    for candidate in hour_candidates:
                        hour_map = m[a_]
                        if candidate in hour_map:
                            actions_.append(hour_map[candidate])
                            break
                    else:
                        raise KeyError(f'Hour {hour_observation} not defined in action map for action {a_}.')

                actions.append(actions_)

            self.actions = actions
            self.next_time_step()

        return actions


# ---------------------------------------------------------------------------
# BasicRBC：CityLearn 默认基线 RBC（CentralizedRBC.py 使用）
# ---------------------------------------------------------------------------
class BasicRBC(HourRBC):
    """
    针对热泵 + 储热 / 电池系统的分时（hour-of-use）规则控制器。

    设计思路（COP 较高时段充电）：
      - 储热/电池 (storage)：夜间 22:00–08:00 充电 +9.1%，白天 09:00–21:00 放电 -8.0%
      - 冷机 (cooling_device)：白天 80% 名义功率，夜间 40%
      - 暖机 (heating_device)：白天 40%，夜间 80%（与冷机相反，适应 COP）

    动作值含义：
      - storage：正=充电比例 [0,1]，负=放电比例
      - cooling/heating_device：可用名义功率比例 [0,1]
    """

    def __init__(self, env: CityLearnEnv, **kwargs: Any):
        # 初始化时不传 action_map → setter 收到 None → 自动生成默认 24h 表
        super().__init__(env, **kwargs)

    @HourRBC.action_map.setter
    def action_map(self, action_map):
        """
        若未传入自定义 action_map，则按设备类型生成 BasicRBC 默认分时策略。

        2023 phase 2 常见动作名：
          dhw_storage / electrical_storage / cooling_device 等（名称含 storage 走储热/电池分支）
        """
        if action_map is None:
            action_map = {}
            # 展平所有 agent 的动作名并去重
            action_names = [a_ for a in self.action_names for a_ in a]
            action_names = list(set(action_names))

            for n in action_names:
                action_map[n] = {}

                # ----- 储热罐 / 电池（动作名含 storage）-----
                if 'storage' in n:
                    for hour in Building.get_periodic_observation_metadata()['hour']:
                        if 9 <= hour <= 21:
                            # 白天（9–21 点）：放电 8% 容量
                            value = -0.08
                        elif (1 <= hour <= 8) or (22 <= hour <= 24):
                            # 夜间（22–24, 1–8 点）：充电 9.1% 容量
                            value = 0.091
                        else:
                            value = 0.0
                        action_map[n][hour] = value

                # ----- 冷机 -----
                elif n == 'cooling_device':
                    for hour in Building.get_periodic_observation_metadata()['hour']:
                        if 9 <= hour <= 21:
                            value = 0.8   # 白天高负荷供冷
                        elif (1 <= hour <= 8) or (22 <= hour <= 24):
                            value = 0.4   # 夜间低负荷
                        else:
                            value = 0.0
                        action_map[n][hour] = value

                # ----- 暖机 -----
                elif n == 'heating_device':
                    for hour in Building.get_periodic_observation_metadata()['hour']:
                        if 9 <= hour <= 21:
                            value = 0.4
                        elif (1 <= hour <= 8) or (22 <= hour <= 24):
                            value = 0.8   # 夜间 COP 相对高，多供热
                        else:
                            value = 0.0
                        action_map[n][hour] = value

                # ----- 冷热一体机（部分 schema）-----
                elif n == 'cooling_or_heating_device':
                    for hour in Building.get_periodic_observation_metadata()['hour']:
                        if hour < 7:
                            value = 0.4
                        elif hour < 21:
                            value = -0.4  # 负值表示制热模式
                        else:
                            value = 0.8
                        action_map[n][hour] = value

                else:
                    raise ValueError(f'Unknown action name: {n}')

        # 调用 HourRBC 的 setter，规范化 action_map 结构（按建筑/agent 拆分）
        HourRBC.action_map.fset(self, action_map)


# ---------------------------------------------------------------------------
# 与 CentralizedRBC.py 的配合方式（示意）
# ---------------------------------------------------------------------------
# env = CityLearnEnv(..., central_agent=True)
# model = BasicRBC(env)
# observations, _ = env.reset()
# while not env.terminated:
#     actions = model.predict(observations)   # 内部仅查 hour → action_map，无 ML
#     observations, reward, terminated, truncated, info = env.step(actions)
