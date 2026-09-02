import warnings
from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper, RLlibMultiAgentEnv
from ray.rllib.algorithms.sac import SACConfig as Config
from ray.rllib.policy.policy import PolicySpec

import pandas as pd

# 设置显示所有列
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

#忽略警告信息
warnings.filterwarnings('ignore', category=DeprecationWarning)

# 初始化环境
env_config = {
    #指定数据集
    'env_kwargs': {
        'schema': 'citylearn_challenge_2023_phase_2_local_evaluation',
    },
    #应用包装器
    'wrappers': [
        NormalizedObservationWrapper,
        ClippedObservationWrapper
    ]
}

# 配置SAC算法
config = (
    Config()
    .environment(RLlibMultiAgentEnv, env_config=env_config)
    .multi_agent(
        policies={a: PolicySpec() for a in RLlibMultiAgentEnv(env_config)._agent_ids},
        policy_mapping_fn=lambda agent_id, episode, worker, **kwargs: agent_id,
    )
)

# 构建模型
model = config.build()

# 训练模型
for i in range(20):
    _ = model.train()
111
# 测试模型
env = RLlibMultiAgentEnv(env_config)
observations, _ = env.reset()
# 测试模型
while not env.terminated:
    actions = {p: model.compute_single_action(o, policy_id=p, explore=False) for p, o in observations.items()}
    observations, _, _, _, _ = env.step(actions)

# 评估模型
kpis = env.unwrapped.evaluate()
kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
kpis = kpis.dropna(how='all')
print("outputkpi")
print(kpis)