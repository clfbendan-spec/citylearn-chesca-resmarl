"""
SAC 多智能体训练/评估脚本（副本，原版 Multi-agent.py 保持不变）
================================================================

纯 Multi-Agent SAC 端到端控制（非 CHESCA-ResMARL）。
CHESCA + Multi-Agent 残差请使用 local_evaluation_copy.py（marl_mode=multi_agent）。

用法：
  python Multi-agent_copy.py --output-dir D:\\citylearn-demo\\output\\outkpis\\任务ID
"""

import argparse
import os
import sys
import warnings
from pathlib import Path

import pandas as pd
from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper, RLlibMultiAgentEnv
from ray.rllib.algorithms.sac import SACConfig as Config
from ray.rllib.policy.policy import PolicySpec

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning, module='gymnasium')

pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

DEFAULT_OUTPUT_DIR = Path(r'D:\citylearn-demo\outkpis')


def log_console(message):
    print(message, flush=True)


def print_kpis_for_java(kpis_df):
    log_console('outputkpi')
    for idx in kpis_df.index:
        vals = []
        for col in kpis_df.columns:
            v = kpis_df.loc[idx, col]
            vals.append('NaN' if pd.isna(v) else f'{float(v):.6g}')
        print(f'{idx} {" ".join(vals)}', flush=True)


def parse_args():
    parser = argparse.ArgumentParser(description='SAC Multi-Agent 评估副本（参考 Multi-agent.py）')
    parser.add_argument('--output-dir', '-o', type=str, default=None)
    parser.add_argument('--train-epochs', type=int, default=20, help='SAC 训练轮数（默认 20）')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    train_epochs = max(1, int(args.train_epochs))

    env_config = {
        'env_kwargs': {
            'schema': 'citylearn_challenge_2023_phase_2_local_evaluation',
            'episode_time_steps': 720,
            'render_mode': 'end',
            'render_directory': output_dir,
            'render_session_name': '.',
        },
        'wrappers': [NormalizedObservationWrapper, ClippedObservationWrapper],
    }

    log_console(f'初始化 SAC 多智能体，导出目录: {output_dir.resolve()}')
    config = (
        Config()
        .environment(RLlibMultiAgentEnv, env_config=env_config)
        .multi_agent(
            policies={a: PolicySpec() for a in RLlibMultiAgentEnv(env_config)._agent_ids},
            policy_mapping_fn=lambda agent_id, episode, worker, **kwargs: agent_id,
        )
    )
    model = config.build()

    log_console(f'开始训练 SAC 模型，共 {train_epochs} 轮...')
    for i in range(train_epochs):
        log_console(f'[训练] 第 {i + 1}/{train_epochs} 轮...')
        _ = model.train()
    log_console('训练完成，开始测试仿真...')

    env = RLlibMultiAgentEnv(env_config)
    citylearn_env = env.env.unwrapped
    observations, _ = env.reset()
    total_steps = env_config['env_kwargs'].get('episode_time_steps', 720)
    log_console(f'开始仿真，共 {total_steps} 步...')

    step_count = 0
    while not env.terminated:
        actions = {
            p: model.compute_single_action(o, policy_id=p, explore=False)
            for p, o in observations.items()
        }
        observations, _, _, _, _ = env.step(actions)
        step_count += 1
        if step_count == 1 or step_count % 36 == 0 or env.terminated:
            log_console(f'[进度] {step_count}/{total_steps} 步 ({100 * step_count / total_steps:.1f}%)')

    log_console('仿真完成，正在计算 KPI...')
    kpis = citylearn_env.evaluate()
    kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
    kpis = kpis.dropna(how='all')

    if not getattr(citylearn_env, '_final_kpis_exported', False):
        citylearn_env.export_final_kpis(filepath='exported_kpis.csv')

    if citylearn_env.new_folder_path:
        kpi_path = Path(citylearn_env.new_folder_path) / 'exported_kpis.csv'
        log_console(f'输出目录: {Path(citylearn_env.new_folder_path).resolve()}')
        log_console(f'KPI 文件: {kpi_path.resolve()}')

    print_kpis_for_java(kpis)
    sys.stdout.flush()
