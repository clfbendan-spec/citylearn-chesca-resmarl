import argparse
import os
import sys
import warnings
from pathlib import Path

import pandas as pd
from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper, RLlibMultiAgentEnv
from ray.rllib.algorithms.sac import SACConfig as Config
from ray.rllib.policy.policy import PolicySpec

# Windows 下管道输出强制 UTF-8，避免 Java 端控制台中文乱码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning, module='gymnasium')

pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)


def log_console(message):
    """输出到 stdout 供 Java 端实时拉取控制台（须 flush）。"""
    print(message, flush=True)


def print_kpis_for_java(kpis_df):
    """按 Java parseAndSaveKpis 约定格式输出 KPI（避免 pandas 打印 ... 省略列）。"""
    log_console("outputkpi")
    for idx in kpis_df.index:
        vals = []
        for col in kpis_df.columns:
            v = kpis_df.loc[idx, col]
            vals.append('NaN' if pd.isna(v) else f'{float(v):.6g}')
        print(f"{idx} {' '.join(vals)}", flush=True)


DEFAULT_OUTPUT_DIR = Path(r'D:\citylearn-demo\outkpis')


def parse_args():
    parser = argparse.ArgumentParser(description='SAC 多智能体训练/仿真并导出 KPI')
    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        default=None,
        help=f'KPI/仿真数据导出目录（默认: {DEFAULT_OUTPUT_DIR}）',
    )
    return parser.parse_args()


args = parse_args()
OUTPUT_DIR = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

env_config = {
    'env_kwargs': {
        'schema': 'citylearn_challenge_2023_phase_2_local_evaluation',
        'episode_time_steps': 720,
        'render_mode': 'end',
        'render_directory': OUTPUT_DIR,
        'render_session_name': '.',
    },
    'wrappers': [
        NormalizedObservationWrapper,
        ClippedObservationWrapper
    ],
}

log_console(f"初始化 SAC 多智能体，导出目录: {OUTPUT_DIR.resolve()}")
config = (
    Config()
    .environment(RLlibMultiAgentEnv, env_config=env_config)
    .multi_agent(
        policies={a: PolicySpec() for a in RLlibMultiAgentEnv(env_config)._agent_ids},
        policy_mapping_fn=lambda agent_id, episode, worker, **kwargs: agent_id,
    )
)
log_console("构建 RLlib 模型...")
model = config.build()

train_epochs = 20
log_console(f"开始训练 SAC 模型，共 {train_epochs} 轮...")
for i in range(train_epochs):
    log_console(f"[训练] 第 {i + 1}/{train_epochs} 轮...")
    _ = model.train()
log_console("训练完成，开始测试仿真...")

env = RLlibMultiAgentEnv(env_config)
citylearn_env = env.env.unwrapped
observations, _ = env.reset()
total_steps = env_config['env_kwargs'].get('episode_time_steps', 720)
log_console(f"开始仿真，共 {total_steps} 步...")

step_count = 0
while not env.terminated:
    actions = {
        p: model.compute_single_action(o, policy_id=p, explore=False)
        for p, o in observations.items()
    }
    observations, _, _, _, _ = env.step(actions)
    step_count += 1
    if step_count == 1 or step_count % 36 == 0 or env.terminated:
        log_console(f"[进度] {step_count}/{total_steps} 步 ({100 * step_count / total_steps:.1f}%)")

log_console("仿真完成，正在计算 KPI...")
kpis = citylearn_env.evaluate()
kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
kpis = kpis.dropna(how='all')

if not getattr(citylearn_env, '_final_kpis_exported', False):
    citylearn_env.export_final_kpis(filepath='exported_kpis.csv')

if citylearn_env.new_folder_path:
    kpi_path = Path(citylearn_env.new_folder_path) / 'exported_kpis.csv'
    log_console(f"输出目录: {Path(citylearn_env.new_folder_path).resolve()}")
    log_console(f"KPI 文件: {kpi_path.resolve()}")
else:
    log_console('未生成导出目录（请确认 render_mode 已启用）')

print_kpis_for_java(kpis)
sys.stdout.flush()
