import warnings
from pathlib import Path

from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper, RLlibSingleAgentWrapper
from ray.rllib.algorithms.sac import SACConfig as Config

warnings.filterwarnings('ignore', category=DeprecationWarning)

RENDER_DIR = Path('outputs/ui_exports')
RENDER_SESSION = 'single_agent_sac_run'

# initialize
env_config = {
    'env_kwargs': {
        'schema': 'citylearn_challenge_2023_phase_2_local_evaluation',
        'episode_time_steps': 720,
        'render_mode': 'during',
        'render_directory': RENDER_DIR,
        'render_session_name': RENDER_SESSION,
    },
    'wrappers': [
        NormalizedObservationWrapper,
        ClippedObservationWrapper
    ]
}
config = (
    Config()
    .environment(RLlibSingleAgentWrapper, env_config=env_config)
)
model = config.build()

# train
for i in range(2):
    _ = model.train()

# test
env = RLlibSingleAgentWrapper(env_config)
citylearn_env = env.unwrapped
observations, _ = env.reset()

while not env.unwrapped.terminated:
    actions = model.compute_single_action(observations, explore=False)
    observations, _, _, _, _ = env.step(actions)

# evaluate & export KPIs (same layout as UI exported_kpis.csv)
kpis = citylearn_env.evaluate()
kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
kpis = kpis.dropna(how='all')
print('outputkpi')
print(kpis)

if not getattr(citylearn_env, '_final_kpis_exported', False):
    citylearn_env.export_final_kpis(filepath='exported_kpis.csv')

if citylearn_env.new_folder_path:
    kpi_path = Path(citylearn_env.new_folder_path) / 'exported_kpis.csv'
    print('输出目录:', Path(citylearn_env.new_folder_path).resolve())
    print('KPI 文件:', kpi_path.resolve())
else:
    print('未生成导出目录（请确认 render_mode 已启用）')
