"""
参赛 Agent 入口文件 —— CHESCA 算法对外的「大门」
====================================================

local_evaluation.py 通过本模块加载控制算法：
  from agents.user_agent import SubmissionAgent

【调用关系图】
  local_evaluation.evaluate()
    └── SubmissionAgent (= my_agent)
          ├── register_reset(obs)   # episode 开始时
          │     ├── self.reset()    # 清空 Checa 内部历史/计数器
          │     └── Checa.predict() # 完整 5 阶段决策
          └── predict(obs)          # 每个 step 之后
                └── Checa.predict() # 同上

【my_agent 做了什么？】
  几乎不做额外逻辑，只是继承 Checa 并满足竞赛接口约定。
  真正的算法在 checa/agent.py 的 Checa 类里。

如需替换为自定义策略：
  1. 继承 citylearn.agents.base.Agent 或 Checa
  2. 实现 predict / register_reset
  3. 将 SubmissionAgent 指向你的类
"""

from checa.agent import Checa

###################################################################
#####                Specify your agent here                  #####
###################################################################


class my_agent(Checa):
    """
    本地评估使用的 Agent 类。

    继承 Checa = 完整的 CHESCA 分层协调控制算法，包含：
      · ForecastAgent（XGBoost 时序预测）
      · CoolingDeviceController（冷机 PID 控制）
      · BatteryController（电池树搜索，平滑社区负荷）
    """

    def __init__(self, env, **kwargs):
        """
        初始化 Agent，触发 Checa.__init__ 创建所有子模块。

        参数 env：WrapperEnv，提供观测/动作空间及建筑元数据。
        参数 **kwargs：可选超参（如 params={'tau': 1}），会传给 Checa。
        """
        super().__init__(env, **kwargs)

    def register_reset(self, observations):
        """
        环境 reset 后、第一个 env.step 之前调用（竞赛/本地评估约定）。

        【为什么需要这个方法？】
        CityLearn 约定：reset 返回初始观测后，Agent 必须立刻给出 t=0 的动作，
        然后主循环才 env.step(actions)。

        【内部两步】
        1. self.reset()  — 继承自 citylearn Agent 基类，清空 episode 状态
        2. self.predict() — 走 CHESCA 完整决策链，返回首步动作

        返回：[[DHW_0, ELE_0, TMP_0, DHW_1, ELE_1, TMP_1, DHW_2, ELE_2, TMP_2]]
              共 3 栋楼 × 3 维动作 = 9 个数
        """
        self.reset()
        return self.predict(observations)

    def predict(self, observations, deterministic=True):
        """
        根据当前观测预测本时间步要施加的动作。

        参数 observations：[[o1, o2, ...]]，central_agent 模式外层长度必须为 1。
        参数 deterministic：CHESCA 是规则控制算法，此参数仅为接口兼容，实际未使用。

        【实际执行】透传到 Checa.predict()，依次经过：
          阶段1 时序预测 → 阶段2 初稿动作 → 阶段3 未来用电估计
          → 阶段4 电池树搜索 refine → 阶段5 更新净负荷历史

        可在 super().predict() 前后加入自定义逻辑（如日志、动作裁剪等）。
        """
        return super().predict(observations, deterministic=deterministic)


###################################################################
# local_evaluation.py 导入此名称；修改下方赋值即可切换 Agent 实现
SubmissionAgent = my_agent
###################################################################
