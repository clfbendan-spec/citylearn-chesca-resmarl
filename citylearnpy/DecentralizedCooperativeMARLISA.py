from citylearn.agents.marlisa import MARLISA as Agent
from citylearn.citylearn import CityLearnEnv
from pathlib import Path

# initialize
env = CityLearnEnv('citylearn_challenge_2023_phase_2_local_evaluation', central_agent=False,episode_time_steps=720,
    render_mode='during',
    render_directory=Path('outputs/ui_exports'),  # optional custom base folder
    render_session_name='my_first_run10')
model = Agent(env)

# train
model.learn(episodes=2, deterministic_finish=True)

# test
kpis = model.env.evaluate()
kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
kpis = kpis.dropna(how='all')
print(kpis)
