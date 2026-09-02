from pathlib import Path
from citylearn.citylearn import CityLearnEnv

# Built-in dataset name (bundled with the citylearn package), not a local file path
schema = 'citylearn_challenge_2022_phase_all_plus_evs'

env = CityLearnEnv(
    schema,
    central_agent=True,
    episode_time_steps=1464,
    render_mode='during',
    render_directory=Path('outputs/ui_exports'),  # optional custom base folder
    render_session_name='my_first_run3',  # optional custom subfolder
)

observations, _ = env.reset()
while not env.terminated:
    actions = [env.action_space[0].sample()]
    observations, reward, terminated, truncated, info = env.step(actions)

if env.new_folder_path:
    print('输出目录:', Path(env.new_folder_path).resolve())
else:
    print('未生成导出目录（请确认 render_mode 已启用）')