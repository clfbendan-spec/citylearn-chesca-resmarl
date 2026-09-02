# 导入必要的库和模块
import argparse
from citylearn.agents.base import BaselineAgent as Agent  # 导入基线智能体
from citylearn.citylearn import CityLearnEnv  # 导入CityLearn环境
import pandas as pd  # 导入pandas用于数据处理
from RLA.easy_log import logger  # 导入RLAssistant日志工具
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path(r'D:\citylearn-demo\outkpis')


def parse_args():
    parser = argparse.ArgumentParser(description='无控制基线仿真并导出 KPI')
    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        default=None,
        help=f'指标导出根目录（默认: {DEFAULT_OUTPUT_DIR}）',
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
env = CityLearnEnv(env_config, central_agent=True,episode_time_steps=720,
    render_mode='during',
    render_directory=OUTPUT_DIR,
    render_session_name='my_first_run4')

# 创建基线智能体实例
logger.info("初始化BaselineAgent")
model = Agent(env)

# 环境交互阶段
# 重置环境，获取初始观测
observations, _ = env.reset()

# 主循环：当环境未终止时持续执行
while not env.terminated:
    # 智能体根据当前观测预测动作
    actions = model.predict(observations)
    # 执行动作，获取新的观测、奖励等信息
    observations, reward, info, terminated, truncated = env.step(actions)

# 测试评估阶段
# 评估模型性能，获取KPI指标
logger.info("开始评估模型性能")
kpis = model.env.evaluate()

# 处理KPI数据
kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
kpis = kpis.dropna(how='all')

# 记录结果
logger.info("评估结果:")
logger.logkv("kpi_results", kpis.to_dict())
logger.logkv("kpi_table", kpis)

# 打印输出
print("outputkpi")
print(kpis)


if env.new_folder_path:
    print('输出目录:', Path(env.new_folder_path).resolve())
else:
    print('未生成导出目录（请确认 render_mode 已启用）')

logger.dump_tabular()

