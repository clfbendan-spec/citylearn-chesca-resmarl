from citylearn.agents.sac import SAC as Agent
from citylearn.citylearn import CityLearnEnv

import pandas as pd

# 设置显示所有列
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

# initialize
env = CityLearnEnv('citylearn_challenge_2023_phase_2_local_evaluation', central_agent=False)
model = Agent(env)

# train
model.learn(episodes=2, deterministic_finish=True)

# test
kpis = model.env.evaluate()
kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
kpis = kpis.dropna(how='all')
print("outputkpi")
print(kpis)