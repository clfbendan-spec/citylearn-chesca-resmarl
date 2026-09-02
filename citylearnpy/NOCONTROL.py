# 导入必要的库和模块
import argparse
import os
import sys
import warnings
from citylearn.agents.base import BaselineAgent as Agent  # 导入基线智能体
from citylearn.citylearn import CityLearnEnv  # 导入CityLearn环境
import pandas as pd  # 导入pandas用于数据处理
from RLA.easy_log import logger  # 导入RLAssistant日志工具
from pathlib import Path

# Windows 下管道输出强制 UTF-8，避免 Java 端控制台中文乱码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
warnings.filterwarnings('ignore', category=UserWarning, module='gymnasium')


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
    parser = argparse.ArgumentParser(description='无控制基线仿真并导出 KPI')
    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        default=None,
        help=f'CityLearn 导出根目录（默认: {DEFAULT_OUTPUT_DIR}）',
    )
    return parser.parse_args()


args = parse_args()
OUTPUT_DIR = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR

# 设置pandas显示选项，确保所有列都能显示
pd.set_option('display.max_columns', None)  # 显示所有列
pd.set_option('display.width', None)  # 不限制显示宽度

# 初始化阶段
# 初始化RLAssistant日志记录器
logger.configure("./rla_logs")

# 创建CityLearn环境实例
env_config = 'citylearn_challenge_2023_phase_2_local_evaluation'
logger.info(f"初始化环境，配置: {env_config}，导出目录: {OUTPUT_DIR}")
env = CityLearnEnv(env_config, central_agent=True, episode_time_steps=720,
    render_mode='end',
    render_directory=OUTPUT_DIR,
    render_session_name="kpis")

log_console("环境创建完成，初始化 BaselineAgent...")
logger.info("初始化BaselineAgent")
model = Agent(env)

observations, _ = env.reset()
total_steps = getattr(env, 'episode_time_steps', None) or 720
log_console(f"开始仿真，共 {total_steps} 步...")

step_count = 0
while not env.terminated:
    actions = model.predict(observations)
    observations, reward, info, terminated, truncated = env.step(actions)
    step_count += 1
    if step_count == 1 or step_count % 36 == 0 or env.terminated:
        log_console(f"[进度] {step_count}/{total_steps} 步 ({100 * step_count / total_steps:.1f}%)")

log_console("仿真完成，正在计算 KPI...")
logger.info("开始评估模型性能")
kpis = model.env.evaluate()

# 处理KPI数据
kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
kpis = kpis.dropna(how='all')

# 记录结果
logger.info("评估结果:")
logger.logkv("kpi_results", kpis.to_dict())
logger.logkv("kpi_table", kpis)

if env.new_folder_path:
    log_console(f"输出目录: {Path(env.new_folder_path).resolve()}")
else:
    log_console('未生成导出目录（请确认 render_mode 已启用）')

logger.dump_tabular()

print_kpis_for_java(kpis)
sys.stdout.flush()



