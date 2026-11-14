# 新手阅读路线：parse_args -> 创建环境/reset -> BaselineAgent -> step循环 -> evaluate/清单。
# 不需要训练；它是独立运行的固定参考，不是“费用为零”或“建筑不再用电”。
# BaselineAgent会禁用主动控制，设备仍按环境的基线需求运行；不要自行换成全零三维动作。
# 输出KPI、曲线及真实转移，供候选算法比较；默认OL1数据不等于一整年。
# 导入必要的库和模块
import argparse
import os
import sys
import warnings
import logging
import json
from citylearn.agents.base import BaselineAgent as Agent  # 导入基线智能体
from citylearn.citylearn import CityLearnEnv  # 导入CityLearn环境
import pandas as pd  # 导入pandas用于数据处理
from pathlib import Path

# Java 会把本文件复制到 output/outkpis/{taskId}/ 再执行，需能 import citylearnpy 下模块
CITYLEARNPY_DIR = Path(os.environ.get('CITYLEARN_PYTHON_PATH', Path(__file__).resolve().parent))
_CITYLEARNPY = str(CITYLEARNPY_DIR.resolve())
if _CITYLEARNPY not in sys.path:
    sys.path.insert(0, _CITYLEARNPY)

from utils.report import collect_citylearn_step_rows, write_step_trace_csv
from assessment_trace import AssessmentTrace
from evaluation_contract import capture_context, finalize_evaluation, file_sha256, protocol_id

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
    parser.add_argument('--schema', '--eval-schema', dest='schema',
                        default='citylearn_challenge_2023_phase_2_online_evaluation_1',
                        help='CityLearn 数据集名称或 schema.json 路径')
    parser.add_argument('--simulation-start-time-step', type=int)
    parser.add_argument('--simulation-end-time-step', type=int)
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        default=None,
        help=f'CityLearn 导出根目录（默认: {DEFAULT_OUTPUT_DIR}）',
    )
    parser.add_argument(
        '--no-step-trace',
        action='store_true',
        help='不写出 step_trace.csv（默认写出，便于与 Multi-agent 逐步对比）',
    )
    args = parser.parse_args()
    start, end = args.simulation_start_time_step, args.simulation_end_time_step
    if (start is not None and start < 0) or (end is not None and end < 0):
        parser.error('时间步必须非负')
    if start is not None and end is not None and end <= start:
        parser.error('结束时间步必须大于开始时间步，至少包含一次状态转移')
    return args


from community_assessment_task import run_if_requested
run_if_requested('NOCONTROL')
args = parse_args()
OUTPUT_DIR = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR

# 设置pandas显示选项，确保所有列都能显示
pd.set_option('display.max_columns', None)  # 显示所有列
pd.set_option('display.width', None)  # 不限制显示宽度

# 初始化阶段
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# 默认使用完整数据窗口；自定义数据不再被截为 OL1 的 2208 个状态位置。
env_config = args.schema
logger.info(f"初始化环境，配置: {env_config}，导出目录: {OUTPUT_DIR}")
env = CityLearnEnv(env_config, central_agent=True,
    simulation_start_time_step=args.simulation_start_time_step,
    simulation_end_time_step=args.simulation_end_time_step,
    random_seed=args.seed,
    render_mode='end',
    render_directory=OUTPUT_DIR,
    render_session_name="kpis")

log_console("环境创建完成，初始化 BaselineAgent...")
observations, _ = env.reset()
# Capture the physical protocol before BaselineAgent intentionally disables
# active controls. Otherwise the baseline would look like a different
# building/equipment protocol even though it uses the same dataset.
evaluation_context = capture_context(env, information_access='no_control_no_policy_observations')
logger.info("初始化BaselineAgent")
model = Agent(env)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
resolved_config = {
    'algorithm': 'NoControl', 'policy': 'citylearn.agents.base.BaselineAgent',
    'schema': str(env_config), 'random_seed': env.random_seed,
    'simulation_window': [env.episode_tracker.episode_start_time_step,
                          env.episode_tracker.episode_end_time_step],
    'seconds_per_time_step': env.seconds_per_time_step,
    'buildings': [b.name for b in env.buildings],
    'active_actions': env.action_names, 'step_trace_enabled': not args.no_step_trace,
}
(OUTPUT_DIR / 'agent_config.json').write_text(
    json.dumps(resolved_config, ensure_ascii=False, indent=2), encoding='utf-8')
dashboard_trace = AssessmentTrace(env, {'simulation_start_time_step': env.episode_tracker.episode_start_time_step,
                                      'seconds_per_time_step': env.seconds_per_time_step},
                                {'label': 'NoControl'}) if not args.no_step_trace else None
total_steps = env.time_steps - 1
progress_every = max(1, total_steps // 20)
log_console(f"开始仿真，共 {total_steps} 步...")

step_count = 0
step_trace_rows = []
enable_step_trace = not args.no_step_trace
while not env.terminated:
    # observation是当前可见状态；predict给出基线动作，step才推进物理环境。
    # reward是当前奖励函数反馈，不是最终KPI；info允许为空，不能据此补造设备数据。
    before = dashboard_trace.before() if dashboard_trace else None
    actions = model.predict(observations)
    transition = env.step(actions)
    observations, reward, terminated, truncated, info = transition
    if dashboard_trace:
        dashboard_trace.record(before, actions, transition, 'no_control')
    step_count += 1
    if enable_step_trace:
        # central_agent：actions 多为 list[array]；按楼栋下标对齐最稳
        action_list = None
        reward_list = None
        if isinstance(actions, (list, tuple)):
            action_list = list(actions)
        if isinstance(reward, (list, tuple)):
            reward_list = [float(r) for r in reward]
            # 若只返回 1 个社区奖励，广播到各楼便于对齐分析
            if len(reward_list) == 1 and len(env.buildings) > 1:
                reward_list = reward_list * len(env.buildings)
        elif reward is not None:
            try:
                reward_list = [float(reward)] * len(env.buildings)
            except (TypeError, ValueError):
                reward_list = None
        step_trace_rows.extend(
            collect_citylearn_step_rows(
                env,
                step_count=step_count,
                action_list=action_list,
                reward_list=reward_list,
            )
        )
    if step_count == 1 or step_count % progress_every == 0 or env.terminated:
        log_console(f"[进度] {step_count}/{total_steps} 步 ({100 * step_count / total_steps:.1f}%)")

if enable_step_trace:
    trace_dir = Path(env.new_folder_path) if env.new_folder_path else OUTPUT_DIR
    dashboard_trace.save(trace_dir)
    trace_path = write_step_trace_csv(trace_dir / 'step_trace.csv', step_trace_rows)
    log_console(f"逐步诊断已写入: {trace_path.resolve()} （共 {len(step_trace_rows)} 行）")

log_console("仿真完成，正在计算 KPI...")
# 全窗口KPI必须在reset之前计算，否则建筑累积的本轮状态会被清空。
# 日志中的每次动作转移与最终状态数相差1：最后观测之后没有再执行一次动作。
logger.info("开始评估模型性能")
kpis = model.env.evaluate()

# 处理KPI数据
kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
kpis = kpis.dropna(how='all')

# 记录结果
logger.info("评估结果:")
logger.info("kpi_results: %s", kpis.to_dict())
logger.info("kpi_table:\n%s", kpis)

if env.new_folder_path:
    log_console(f"输出目录: {Path(env.new_folder_path).resolve()}")
else:
    log_console('未生成导出目录（请确认 render_mode 已启用）')

print_kpis_for_java(kpis)
finalize_evaluation(
    env, evaluation_context, OUTPUT_DIR, 'NoControl', resolved_parameters=resolved_config,
    policy_id=protocol_id({'policy': resolved_config['policy'], 'entry_sha256': file_sha256(__file__)}),
    registry_root=os.environ.get('CITYLEARN_ANCHOR_REGISTRY'))
sys.stdout.flush()
