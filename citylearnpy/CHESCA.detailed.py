# CHESCA 算法
# [详注-BEGIN]（生成简版时整段删除）
#
# 【说明】
#   本文件是 local_evaluation.py 的副本，配套目录 CHESCA-copy/。
#   作为 Java / 算法列表中的「纯 CHESCA」入口时：
#     - 只跑规则控制（a_final = a_base）
#     - 不读取 CHESCA-ResMARL 配置页的残差开关（resmarl_enabled / alpha / checkpoint）
#
# 【CHESCA-ResMARL】
#   请使用同目录 CHESCA_ResMARL.py：
#     读取配置页 multi_agent_checkpoint、residual_alpha 等，
#     再以参数方式调用本文件的评估内核（--marl_mode multi_agent）。
#
# 【本文件仍保留的 ResMARL 能力】
#   仅当调用方显式传入 --marl_mode multi_agent（及残差相关参数）时启用。
#   混合公式：a_final = clip((1-alpha)*a_base + alpha*a_rl)
#
#   运行目录：citylearnpy（CHESCA 与 multi_agent_runner_copy 都从这里加载）
#
# 【生成约定（维护者看）】
#   本文件是详注版；平台实际跑的 CHESCA.py = 本文件删掉全部详注块
#   改注释请改本文件，改完重跑 python _gen_marl_split.py
#   直接改 CHESCA.py 会在下次生成时被覆盖
# [详注-END]

# 导入库
import argparse 
import json
import re       
import sys        
import time       
from pathlib import Path
from typing import Optional



# 导入 CityLearn 仿真环境
from citylearn.citylearn import CityLearnEnv # CityLearn 仿真环境

# 脚本会被复制到任务目录运行，所以用绝对路径定位代码目录
CITYLEARNPY_DIR = Path(r'D:\citylearn-demo\citylearnpy')
CHESCA_ROOT = (CITYLEARNPY_DIR / 'CHESCA-copy').resolve()

if not CHESCA_ROOT.is_dir():
    raise FileNotFoundError(f'CHESCA 目录不存在: {CHESCA_ROOT}')

# 把代码目录加入模块搜索路径
for _p in (str(CITYLEARNPY_DIR.resolve()), str(CHESCA_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 日志输出函数，导入时顺带完成控制台编码设置
from utils.base import log_console  # noqa: F401

# 按平台协议打印 KPI
from utils.report import print_kpis_for_java  # noqa: F401

# 环境构建工具
from utils.ches_env import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RENDER_SESSION,
    DEFAULT_SCHEMA,
    create_citylearn_env,
)

# 配置层：默认值与校验组装
# [详注-BEGIN]（生成简版时整段删除）
#   ⚠️ 必须写在**上面那两行 sys.path.insert 之后** ✓ —— 否则 CHESCA-copy / citylearnpy
#      还没进 sys.path，`utils` 包 import 不到 ✗。
#   这里**不再**反导出 `load_agent_config`（2026-10-08 ✗）：本文件自己一次都不用它，
#   而它真正的使用者已改为直接从 `utils.ches_config` import ✓
#     （ablation_resmarl.py / tests/test_residual_phase0.py / CHESCA_ResMARL.py / 20260914153739.py）。
#   同理 `WrapperEnv` 也不再从这里反导出（train_chesca_resmarl.py 已改从 utils.ches_env 取 ✓）。
# [详注-END]
from utils.ches_config import (
    AGENT_PARAM_KEYS,
    DEFAULTS,
    _cli_overrides_from_args,
    build_agent_config,
)

from agents.user_agent import SubmissionAgent
from rewards.user_reward import SubmissionReward
# 决策过程记录工具
from utils.ches_trace import (
    ChescaTraceWriter,
    build_chesca_trace_recorder,
)
# 残差控制层
from utils.ches_residual import build_residual_layer


# 解析命令行参数
def parse_args():
    parser = argparse.ArgumentParser(description='CHESCA 本地评估副本（可修改）并导出 KPI')
    parser.add_argument('--output-dir', '-o', type=str, default=None,
                        help=f'KPI/仿真数据导出目录（默认: {DEFAULT_OUTPUT_DIR}）')
    parser.add_argument('--render-session', type=str, default=DEFAULT_RENDER_SESSION,
                        help='render 导出子目录名')
    parser.add_argument('--min-soc-config', type=str, default=None,
                        help='【已弃用】旧的配置 JSON 路径；现在被忽略（配置直接用命令行参数传入 ✓）')
    parser.add_argument('--episode-time-steps', type=int, default=None,
                        help='覆盖每 episode 时间步数（不给 ⇒ 用数据集自带长度 ✓）')
    parser.add_argument('--no-render', action='store_true',
                        help='关闭 render 导出（加速消融评估）')
    # CHESCA 的算法参数，名称与平台参数表保持一致
    parser.add_argument('--min_soc_per_hour', type=str, default=None,
                        help='JSON：24 小时电量下限表（键 "0"~"23" ⇒ 值 0~1 ✓；缺项会报错 ✓）')
    parser.add_argument('--max_soc_normal', type=float, default=DEFAULTS.get('max_soc_normal'),
                        help='平时允许的最高电量比例（0~1 ✓ 默认 0.99 ✓）')
    parser.add_argument('--max_soc_outage', type=float, default=DEFAULTS.get('max_soc_outage'),
                        help='停电期间允许的最高电量比例（0~1 ✓ 默认 0.87 ✓）')
    parser.add_argument('--max_soc_reduction_in_outage', type=float, default=DEFAULTS.get('max_soc_reduction_in_outage'),
                        help='停电期间的降额上限（0~1 ✓ 默认 0.70 ✓）')
    parser.add_argument('--B_low', type=float, default=DEFAULTS.get('B_low'),
                        help='增负荷阈值系数：净负荷低于「均值 − B_low×标准差」就充电（默认 1.18 ✓）')
    parser.add_argument('--b_low', type=float, default=DEFAULTS.get('b_low'),
                        help='同上（历史小写写法 ✓ 两种都认 ✓）')
    parser.add_argument('--B_high', type=float, default=DEFAULTS.get('B_high'),
                        help='减负荷阈值系数：净负荷高于「均值 + B_high×标准差」就放电（默认 1.0 ✓）')
    parser.add_argument('--b_high', type=float, default=DEFAULTS.get('b_high'),
                        help='同上（历史小写写法 ✓ 两种都认 ✓）')
    parser.add_argument('--TMP_max_reduction_percent', type=float, default=DEFAULTS.get('TMP_max_reduction_percent'),
                        help='温度控制的最大降额比例（默认 0.0 ✓）')
    parser.add_argument('--tmp_max_reduction_percent', type=float, default=DEFAULTS.get('tmp_max_reduction_percent'),
                        help='同上（历史小写写法 ✓ 两种都认 ✓）')
    parser.add_argument('--min_cool_per_c_overheat', type=float, default=DEFAULTS.get('min_cool_per_c_overheat'),
                        help='每超设定点 1°C 至少开多少制冷（冷机开环保底 ✓）')
    parser.add_argument('--min_cool_per_c_outdoor_gap', type=float, default=DEFAULTS.get('min_cool_per_c_outdoor_gap'),
                        help='室外温度高于设定点时每 1°C 至少开多少制冷 ✓')
    parser.add_argument('--outdoor_gap_deadband_c', type=float, default=DEFAULTS.get('outdoor_gap_deadband_c'),
                        help='上面那条的死区宽度（°C ✓）')
    parser.add_argument('--outdoor_floor_max_overheat_c', type=float, default=DEFAULTS.get('outdoor_floor_max_overheat_c'),
                        help='室内超设定点达到该值后，保底开度不再随室外温度变 ✓')
    parser.add_argument('--cooling_demand_feedforward_frac', type=float, default=DEFAULTS.get('cooling_demand_feedforward_frac'),
                        help='按制冷需求预测提前加多少开度（前馈 ✓）')
    parser.add_argument('--demand_feedforward_only_when_overheat', type=str, default=DEFAULTS.get('demand_feedforward_only_when_overheat'),
                        help='true/false：前馈是否只在过热时生效 ✓')
    parser.add_argument('--outdoor_floor_allow_when_under_setpoint', type=str, default=DEFAULTS.get('outdoor_floor_allow_when_under_setpoint'),
                        help='true/false：室内已低于设定点时，还允许室外触发的保底吗 ✓')
    parser.add_argument('--clear_open_loop_floor_when_under_setpoint', type=str, default=DEFAULTS.get('clear_open_loop_floor_when_under_setpoint'),
                        help='true/false：低于设定点时是否清掉开环保底 ✓')
    parser.add_argument('--use_lagged_dynamics_indoor', type=str, default=DEFAULTS.get('use_lagged_dynamics_indoor'),
                        help='true/false：室内温度是否用带滞后的动力学来估 ✓')
    parser.add_argument('--lagged_indoor_only_when_hotter', type=str, default=DEFAULTS.get('lagged_indoor_only_when_hotter'),
                        help='true/false：滞后动力学是否只在更热时用 ✓')
    parser.add_argument('--lagged_indoor_hotter_margin_c', type=float, default=DEFAULTS.get('lagged_indoor_hotter_margin_c'),
                        help='上面那条的余量（°C ✓）')
    parser.add_argument('--post_outage_soft_charge_enabled', type=str, default=DEFAULTS.get('post_outage_soft_charge_enabled'),
                        help='true/false：停电恢复后允许缓充 ✓')
    parser.add_argument('--post_outage_relax_steps', type=int, default=DEFAULTS.get('post_outage_relax_steps'),
                        help='缓充持续多少步 ✓')
    parser.add_argument('--post_outage_waive_min_soc', type=str, default=DEFAULTS.get('post_outage_waive_min_soc'),
                        help='true/false：缓充期间豁免电量下限 ✓')
    parser.add_argument('--post_outage_max_ele_charge', type=float, default=DEFAULTS.get('post_outage_max_ele_charge'),
                        help='缓充期间电池最多充到多少（0~1 ✓）')
    parser.add_argument('--post_outage_forbid_charge_when_overheat', type=str, default=DEFAULTS.get('post_outage_forbid_charge_when_overheat'),
                        help='true/false：过热时禁止充电 ✓')
    parser.add_argument('--post_outage_overheat_c', type=float, default=DEFAULTS.get('post_outage_overheat_c'),
                        help='判定过热的偏离量（°C ✓）')
    parser.add_argument('--post_outage_tmp_cap_enabled', type=str, default=DEFAULTS.get('post_outage_tmp_cap_enabled'),
                        help='true/false：电力恢复后限制温度控制功率 ✓')
    parser.add_argument('--post_outage_tmp_cap_steps', type=int, default=DEFAULTS.get('post_outage_tmp_cap_steps'),
                        help='限功率持续多少步 ✓')
    parser.add_argument('--post_outage_tmp_max_start', type=float, default=DEFAULTS.get('post_outage_tmp_max_start'),
                        help='限功率的起始上限（0~1 ✓）')
    parser.add_argument('--post_outage_tmp_ramp', type=str, default=DEFAULTS.get('post_outage_tmp_ramp'),
                        help='true/false：限制是否逐步放开 ✓')
    parser.add_argument('--post_outage_tmp_stagger', type=str, default=DEFAULTS.get('post_outage_tmp_stagger'),
                        help='true/false：各楼栋错峰放开 ✓')
    parser.add_argument('--price_aware_battery_enabled', type=str, default=DEFAULTS.get('price_aware_battery_enabled'),
                        help='true/false：启用看电价决定充放电 ✓')
    parser.add_argument('--price_high_quantile', type=float, default=DEFAULTS.get('price_high_quantile'),
                        help='高价分位点（0~1 ✓ 默认 0.75 ✓）')
    parser.add_argument('--price_low_quantile', type=float, default=DEFAULTS.get('price_low_quantile'),
                        help='低价分位点（0~1 ✓ 默认 0.25 ✓）')
    parser.add_argument('--price_history_min_steps', type=int, default=DEFAULTS.get('price_history_min_steps'),
                        help='算分位点至少需要多少步历史（默认 48 ✓）')
    parser.add_argument('--price_high_soc_threshold', type=float, default=DEFAULTS.get('price_high_soc_threshold'),
                        help='高价时的电量阈值（默认 0.70 ✓）')
    parser.add_argument('--price_high_forbid_charge', type=str, default=DEFAULTS.get('price_high_forbid_charge'),
                        help='true/false：高价时禁止充电 ✓')
    parser.add_argument('--price_high_force_discharge', type=str, default=DEFAULTS.get('price_high_force_discharge'),
                        help='true/false：高价时强制放电 ✓')
    parser.add_argument('--price_high_discharge_ele', type=float, default=DEFAULTS.get('price_high_discharge_ele'),
                        help='高价时的放电量（默认 0.15 ✓）')
    parser.add_argument('--price_min_reserve_soc', type=float, default=DEFAULTS.get('price_min_reserve_soc'),
                        help='为高价时段预留的最低电量（默认 0.55 ✓）')
    parser.add_argument('--price_global_reserve_enabled', type=str, default=DEFAULTS.get('price_global_reserve_enabled'),
                        help='true/false：启用全楼预留电量 ✓')
    parser.add_argument('--price_low_target_soc', type=float, default=DEFAULTS.get('price_low_target_soc'),
                        help='低价时充到多少（默认 0.80 ✓）')
    parser.add_argument('--price_low_charge_ele', type=float, default=DEFAULTS.get('price_low_charge_ele'),
                        help='低价时的充电量（默认 0.25 ✓）')
    parser.add_argument('--price_low_search_boost', type=str, default=DEFAULTS.get('price_low_search_boost'),
                        help='true/false：低价时加强树搜索 ✓')
    parser.add_argument('--tau', type=int, default=DEFAULTS.get('tau'),
                        help='树搜索向前看几步（只允许 1/2/3 ✓ 默认 1 ✓）')
    parser.add_argument('--balance_type', type=str, default=DEFAULTS.get('balance_type'),
                        help='树搜索适应度类型：A 跟踪历史均值 / B 抑制波动 / C 跟踪均值与预测中点（默认 C ✓）')
    parser.add_argument('--eval_schema', '--eval-schema', dest='eval_schema', type=str,
                        default=DEFAULTS.get('eval_schema'),
                        help='本脚本仿真/KPI 用的数据集（覆盖默认 SCHEMA ✓；下划线/中划线两种写法都认 ✓）')
    # 残差相关参数不在这里声明，只在 CHESCA_ResMARL.py 中
    # [详注-BEGIN]（生成简版时整段删除）
    #   ⚠️ Java 的纯 CHESCA 任务**仍可能**把它们一起传过来 ✗（BaseDataService 里 "chesca.py" 的参数表
    #   列着 marl_mode / resmarl_enabled / residual_alpha / multi_agent_checkpoint … ✓）
    #   ⇒ 这里用 `parse_known_args()` **容忍**未识别参数并打一行告警 ✓：不静默 ✗、也不会 exit 2 崩掉 ✗。
    # [详注-END]
    args, unknown = parser.parse_known_args()
    if unknown:
        log_console(f'提示：忽略未识别参数 {unknown}'
                    f'（纯 CHESCA 已不再接受 ResMARL 参数；它们只在 CHESCA_ResMARL.py 里生效）')
    return args


# 决定用哪个数据集、跑多少步
def resolve_schema_plan(config) -> dict:
    # 数据集由命令行参数决定，未指定时用默认数据集
    # [详注-BEGIN]（生成简版时整段删除）
    #   与 Multi-agent-eval 同一写法 ✓：`(args.eval_schema or '').strip() or DEFAULT_EVAL_SCHEMA` ✓
    #   —— 不再兜 `config.SCHEMA` / `agent_config` 里的同义键 ✗（那几条是历史多入口遗留 ✓，
    #   而且会和"把结果写回 agent_config"形成自我喂养 ✗）。
    # [详注-END]
    eval_schema = (str(getattr(config, 'EVAL_SCHEMA', None) or '')).strip() or DEFAULT_SCHEMA

    # 步数未指定时返回空值，由数据集自身长度决定
    # [详注-BEGIN]（生成简版时整段删除）
    #   老版本这里查一张硬编码表（SCHEMA_DEFAULT_EPISODE_STEPS ✓，2026-10-08 删除 ✗）：
    #   实测那张表 22/23 条就等于数据集自己的 `simulation_end_time_step + 1` ⇒ 纯冗余 ✗，
    #   而且**未登记的 schema 会被静默按 720 跑** ✗（截断回合）。现在与 eval/train 同一约定 ✓：
    #   None ⇒ 不传给 CityLearn ⇒ 由数据集自带长度决定 ✓
    #   （同一个约定见 utils/env.py 的 build_env_config ✓）。
    #   需要整数的地方（总步数 / 日志 ✓）在**建好环境之后**从环境读回真实值 ✓。
    # [详注-END]
    steps = getattr(config, 'episode_time_steps', None)

    return {
        'eval_schema': eval_schema,
        'eval_episode_steps': None if steps is None else int(steps),
    }


# 更换随机停电的种子
def update_power_outage_random_seed(env: CityLearnEnv, random_seed: int) -> CityLearnEnv:
    # 为每栋楼设置停电模型的随机种子
    # [详注-BEGIN]（生成简版时整段删除）
    #     必须在 env.reset() 之前调用，reset 之后停电序列就固定了。
    # [详注-END]
    for b in env.buildings:
        b.stochastic_power_outage_model.random_seed = random_seed
    return env


# 打印区域级 KPI 摘要，数值越小越好
def print_episode_metrics(env: CityLearnEnv) -> dict:
    # 只取区域级结果逐项打印
    # [详注-BEGIN]（生成简版时整段删除）
    #     这里只筛选 name=='District' 的行，方便在控制台快速查看整体表现。
    #
    #     指标 value 含义：相对「无智能控制基线」的比值
    #       - < 1.0 表示比基线更好
    #       - > 1.0 表示比基线更差
    #       - = 1.0 表示与基线相当
    # [详注-END]
    metrics = env.evaluate()
    district = metrics[metrics['name'] == 'District']
    summary = {}
    for _, row in district.iterrows():
        key = row['cost_function']   # 指标名称
        value = float(row['value'])
        summary[key] = {'value': value}
        log_console(f'{key}: {value:.3f}')
    return summary


# 写出 KPI 文件并打印给平台
def save_episode_kpis(env: CityLearnEnv, fallback_dir: Optional[Path] = None) -> Optional[Path]:
    # 计算 KPI，必须在重置环境之前调用，否则取到的是无控制基线值
    # [详注-BEGIN]（生成简版时整段删除）
    #     reset 会清空仿真状态；若之后再 evaluate()，得到的是「无控制基线」指标（多为 1.0）。
    #     （也就是说：这一句必须排在主流程 reset 之前 ✓）
    # [详注-END]
    kpis = env.evaluate()

    # 转成宽表，行是指标，列是建筑与区域
    kpis_table = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
    kpis_table = kpis_table.dropna(how='all')  # 去掉全空的行

    # 确定导出目录，优先用任务目录
    file_path = None
    if fallback_dir is not None:
        out = Path(fallback_dir)
        out.mkdir(parents=True, exist_ok=True)
        file_path = out / 'exported_kpis.csv'
    else:
        try:
            env._ensure_render_output_dir()
            if getattr(env, 'new_folder_path', None):
                file_path = Path(env.new_folder_path) / 'exported_kpis.csv'
        except Exception:
            file_path = None
        if file_path is None:
            file_path = Path('.') / 'exported_kpis.csv'

    # 整理成 CSV 格式
    kpis_out = kpis_table.fillna('').reset_index().rename(columns={'cost_function': 'KPI'})
    kpis_out.to_csv(file_path, index=False, encoding='utf-8')
    env._final_kpis_exported = True  # 标记已导出，避免重复写入

    log_console(f'输出目录: {file_path.parent.resolve()}')
    log_console(f'KPI 文件: {file_path.resolve()}')

    print_kpis_for_java(kpis_table)
    return file_path


# 评估总入口，用一套参数跑完仿真并导出 KPI
def evaluate(config, residual=None):
    # 写出配置快照，然后进入主流程
    # [详注-BEGIN]（生成简版时整段删除）
    #     无论 none 还是 multi_agent，仿真主链都在 evaluate_chesca 中完成。
    # [详注-END]
    output_dir = getattr(config, 'RENDER_DIR', DEFAULT_OUTPUT_DIR)
    agent_config = getattr(config, 'AGENT_CONFIG', None) or {}

    # 未传入残差层时使用空实现
    residual = residual or build_residual_layer({}, 'none')
    log_console(f'控制模式 marl_mode={residual.marl_mode}')

    # 数据集与步数只在主流程里解析一次
    try:
        cfg_path = Path(output_dir) / 'chesca_agent_config.json'
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = dict(agent_config) if isinstance(agent_config, dict) else {}
        cfg_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
        log_console(f'已写入配置快照: {cfg_path.resolve()}')
    except Exception as exc:
        log_console(f'写入 chesca_agent_config.json 失败: {exc}')

    evaluate_chesca(config, residual=residual)


# CHESCA 主流程，可选叠加强化学习修正
def evaluate_chesca(config, residual=None):
    # 主流程从这里开始
    # [详注-BEGIN]（生成简版时整段删除）
    #     【marl_mode=multi_agent 时 — 按时间顺序】
    #     ========================================================================
    #     阶段 0（本函数前半段，仿真未开始）：
    #       创建 env + Agent → 加载预存 SAC → 挂载残差器 → 创建旁路 旁路环境
    #
    #     阶段 1（reset 后 register_reset）：
    #       第 0 小时动作 = predict() 一次走完阶段 1～5
    #
    #     阶段 2（while 主循环，每小时）：
    #       env.step(a_final) → 旁路环境 同步 → predict() 得下一小时 a_final
    #
    #     阶段 3（done 时）：
    #       KPI + trace 导出
    #
    #     【每一步 predict() 内部 — Checa.predict，见 checa/agent.py】
    #       阶段1 预测 → 阶段2 初稿 → 阶段3 未来用电 → 阶段4 refine → a_base
    #       阶段5 SAC 输出 a_rl → a_final = clip((1−α)·a_base + α·a_rl)
    #
    #     【marl_mode=none】
    #       resmarl_enabled=False，阶段 5 恒等，a_final = a_base（纯 CHESCA）
    # [详注-END]
    log_console('开始 CHESCA 本地评估')
    output_dir = getattr(config, 'RENDER_DIR', DEFAULT_OUTPUT_DIR)
    agent_config = getattr(config, 'AGENT_CONFIG', None) or {}
    schema_plan = resolve_schema_plan(config)
    log_console(
        f"数据集: {schema_plan['eval_schema']}"
        f"({schema_plan['eval_episode_steps'] if schema_plan['eval_episode_steps'] is not None else '数据集自带'}步)"
    )
    log_console(f"导出目录: {Path(output_dir).resolve()}")
    log_console(f'CHESCA 子模式: marl_mode={residual.marl_mode}')

    # 未启用残差控制时它是空实现
    residual = residual or build_residual_layer({}, 'none')

    # 创建仿真环境，KPI 只统计这一个环境
    env, wrapper_env = create_citylearn_env(
        config,
        SubmissionReward,
        schema=schema_plan['eval_schema'],
        episode_time_steps=schema_plan['eval_episode_steps'],
    )
    if schema_plan['eval_episode_steps'] is None:
        # 未指定步数时从环境读回真实长度
        # [详注-BEGIN]（生成简版时整段删除）
        #   `wrapper_env.time_steps` = 数据集总时间步数 ✓（与 utils/env.py 的探针读回同一做法 ✓）。
        #   下游 total_steps / 日志都是整数 ⇒ 在这里补齐 ✓（不再靠硬编码表 ✗）。
        # [详注-END]
        schema_plan['eval_episode_steps'] = int(getattr(wrapper_env, 'time_steps', 0) or 0)
        log_console(f"（未指定步数则用数据集自带长度 {schema_plan['eval_episode_steps']} 步）")
    log_console('环境创建完成，初始化 CHESCA Agent...')
    agent_config = getattr(config, 'AGENT_CONFIG', None)
    agent_params = {}
    if agent_config:
        # 把校验过的配置搬给智能体
        for key in AGENT_PARAM_KEYS:
            value = agent_config.get(key)
            if value is None:
                continue
            agent_params[key] = value
            if key == 'min_soc_per_hour':
                log_console(f'已加载自定义电池 SOC 下限配置（{len(value)} 个小时）')
            else:
                log_console(f'已加载 {key}={value}')
        agent_params.setdefault('tau', 1)
    else:
        agent_params = {'tau': 1, 'balance_type': 'C'}

    # 组装智能体参数

    # 设置强化学习修正的开关与强度
    residual.apply_agent_params(agent_params)

    agent = SubmissionAgent(wrapper_env, params=agent_params)

    # 挂载残差控制层，纯 CHESCA 时它是空操作
    # [详注-BEGIN]
    #   ③ 加载训练好的 Multi-Agent SAC 模型（multi_agent_checkpoint，必填）
    #   ④ 换上「RL 修正器」MultiAgentResidualCorrector（替换 agent.residual_corrector）
    #   ⑤ 创建旁路环境（无 render，仅同步各楼观测，不算 KPI）
    # [详注-END]
    residual.attach(agent, config, schema_plan)

    # 记录每一步的决策过程，供界面查看
    trace_recorder = build_chesca_trace_recorder(agent.n_buildings)
    trace_writer = ChescaTraceWriter(trace_recorder, Path(output_dir))
    agent.trace_recorder = trace_recorder
    trace_recorder.begin_episode()
    log_console('CHESCA Agent 创建完成（trace 已启用）')

    # 重置环境并计算第一个动作
    observations, _ = env.reset()
    residual.reset()          # 残差环境也重置

    agent_time_elapsed = 0
    total_steps = schema_plan['eval_episode_steps']

    residual.bind()
    step_start = time.perf_counter()
    # 计算第一个动作
    actions = agent.register_reset(observations)
    agent_time_elapsed += time.perf_counter() - step_start
    log_console(f'开始仿真，共 {total_steps} 步...')

    episodes_completed = 0
    num_steps = 0
    interrupted = False
    episode_metrics = []

    try:
        # 主循环，每个时间步执行一次
        # [详注-BEGIN]
        #
        #   小时 t 已有 actions
        #     → env.step(actions)           主环境前进，得到下一步观测
        #     → residual.sync(同一 actions) 残差环境对齐
        #     → predict()                   算下一步动作
        #   重复直到回合结束
        # [详注-END]
        while True:
            # 主环境执行动作，KPI 来自这里
            observations, _, terminated, truncated, _ = env.step(actions)
            done = terminated or truncated

            # 残差环境同步，不影响 KPI
            residual.sync(actions)

            if not done:
                # 计算下一个动作
                residual.bind()
                step_start = time.perf_counter()
                actions = agent.predict(observations)
                agent_time_elapsed += time.perf_counter() - step_start

                if num_steps == 0 or (num_steps + 1) % 36 == 0:
                    log_console(
                        f'[进度] {num_steps + 1}/{total_steps} 步 '
                        f'({100 * (num_steps + 1) / total_steps:.1f}%)'
                    )
            else:
                # 回合结束，导出 KPI 与决策记录
                episodes_completed += 1
                log_console(f'第 {episodes_completed} 个回合结束')
                log_console('仿真完成，正在计算 KPI...')

                metrics_dict = print_episode_metrics(env)
                episode_metrics.append(metrics_dict)

                save_episode_kpis(env, fallback_dir=Path(output_dir))
                trace_writer.save(env=env)

                if episodes_completed >= config.num_episodes:
                    break

                # 开始下一回合
                env = update_power_outage_random_seed(env, 90000)
                observations, _ = env.reset()
                residual.reset()

                trace_recorder.begin_episode()
                residual.bind()
                step_start = time.perf_counter()
                actions = agent.predict(observations)
                agent_time_elapsed += time.perf_counter() - step_start

            num_steps += 1
            if num_steps % 1000 == 0:
                log_console(f'已走步数: {num_steps}, 已完成回合: {episodes_completed}')

    except KeyboardInterrupt:
        log_console('========================= 评估被中断 =========================')
        interrupted = True

    if not interrupted:
        log_console('========================= 评估完成 =========================')

    log_console(f'智能体总耗时: {agent_time_elapsed:.2f} 秒')
    sys.stdout.flush()



if __name__ == '__main__':
    args = parse_args()

    # 确定导出目录
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    render_session = '.' if args.output_dir else args.render_session
    agent_config = build_agent_config(_cli_overrides_from_args(args)) or {}

    class Config:
        SCHEMA = DEFAULT_SCHEMA
        EVAL_SCHEMA = args.eval_schema
        num_episodes = 1
        episode_time_steps = args.episode_time_steps if args.episode_time_steps else None
        RENDER_DIR = output_dir
        RENDER_SESSION = render_session
        AGENT_CONFIG = agent_config
        ENABLE_RENDER = not args.no_render

    evaluate(Config())
    sys.stdout.flush()
