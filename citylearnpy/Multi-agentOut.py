import warnings
from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper, RLlibMultiAgentEnv
from ray.rllib.algorithms.sac import SACConfig as Config
from ray.rllib.policy.policy import PolicySpec
from pathlib import Path
import pandas as pd

# 设置显示所有列
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

#忽略警告信息
warnings.filterwarnings('ignore', category=DeprecationWarning)


RENDER_DIR = Path('outputs/ui_exports')
RENDER_SESSION = 'multi_agent_run2'

# 初始化环境
env_config = {
    #指定数据集
    'env_kwargs': {
        'schema': 'citylearn_challenge_2023_phase_2_local_evaluation',
        'episode_time_steps': 720,
        'render_mode': 'during',
        'render_directory': RENDER_DIR,
        'render_session_name': RENDER_SESSION,
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

# 测试模型
env = RLlibMultiAgentEnv(env_config)
citylearn_env = env.env.unwrapped
observations, _ = env.reset()

while not env.terminated:
    actions = {p: model.compute_single_action(o, policy_id=p, explore=False) for p, o in observations.items()}
    observations, _, _, _, _ = env.step(actions)

# 评估并导出 KPI（与 UI 所需 exported_kpis.csv 格式一致）
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