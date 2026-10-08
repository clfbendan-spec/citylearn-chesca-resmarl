"""
参赛 Agent 入口文件 —— CHESCA 算法对外的「大门」
====================================================

CHESCA.py 通过本模块加载控制算法（CHESCA-copy 副本，原版见 CHESCA-main/）：
  from agents.user_agent import SubmissionAgent

【调用关系图】
  CHESCA.evaluate()
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
        环境 reset 后、第一个 env.step 之前调用。

        reset() 清空 CHESCA 内部历史 → predict() 走完整阶段 1～5，得到第 0 小时 a_final。
        ResMARL 时 a_final 已含 SAC 残差，不是单独的「纯 CHESCA 动作」。
        """
        self.reset()
        return self.predict(observations)

    def predict(self, observations, deterministic=True):
        """
        透传到 Checa.predict()，见 checa/agent.py 中阶段 1～5 说明。
        """
        return super().predict(observations, deterministic=deterministic)


###################################################################
# CHESCA.py 导入此名称；修改下方赋值即可切换 Agent 实现
SubmissionAgent = my_agent
###################################################################
