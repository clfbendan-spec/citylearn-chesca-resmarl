# CHESCA-ResMARL 算法

# 导入库
import argparse
import json
import sys
from pathlib import Path

# 导入 CHESCA 的评估内核：仿真的主流程、KPI 导出、trace 全在那边
from CHESCA import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SCHEMA,
    evaluate,
    log_console,
)

# 配置层：默认值与校验组装（与 CHESCA.py 同一个模块、同一套校验）
# 残差三项的内置默认值里，α 的缺省（DEFAULT_RESIDUAL_ALPHA）也从这里取 ——
# 与下面 argparse 的 default 同源；掩码的默认值全库只有一处字面量（在 utils/ches_config.py）。
from utils.ches_config import (  # noqa: E402
    DEFAULT_RESIDUAL_ALPHA,
    DEFAULTS,
    _cli_overrides_from_args,
    apply_resmarl_cli_overrides,
    build_agent_config,
)

# 残差层：开关 / 加载 SAC / 换残差器 / 每步同步观测（实现在 utils/ches_residual.py）
from utils.ches_residual import (  # noqa: E402
    MARL_CKPT_BEST_REL_DIR,
    MARL_CKPT_REL_DIR,
    build_residual_layer,
    is_checkpoint_dir,
)


# 解析命令行参数
def parse_args():
    parser = argparse.ArgumentParser(
        description='CHESCA-ResMARL：CHESCA 规则控制 + Multi-Agent SAC 残差修正，并导出 KPI'
    )
    # ------------------------------------------------------------------
    # 框架参数（与 CHESCA.py 同名同义）
    # ------------------------------------------------------------------
    parser.add_argument('--output-dir', '-o', type=str, default=None,
                        help=f'KPI/仿真数据导出目录（默认: {DEFAULT_OUTPUT_DIR}）')
    parser.add_argument('--render-session', type=str, default='chesca_resmarl_eval',
                        help='render 导出子目录名')
    parser.add_argument('--min-soc-config', type=str, default=None,
                        help='【已弃用】旧的配置 JSON 路径；现在被忽略（配置直接用命令行参数传入）')
    parser.add_argument('--episode-time-steps', type=int, default=None,
                        help='覆盖每 episode 时间步数（不给则用数据集自带长度）')
    parser.add_argument('--no-render', action='store_true',
                        help='关闭 render 导出（加速消融评估）')
    # ------------------------------------------------------------------
    # CHESCA 的算法参数（与 CHESCA.py 的参数表逐项对应，名称与平台参数目录一致）
    #   校验（取值范围 / 合法性）统一交给 load_agent_config 里的 _parse_*
    #   ⇒ 口径只有一份，本文件不重复实现。
    # ------------------------------------------------------------------
    parser.add_argument('--min_soc_per_hour', type=str, default=None,
                        help='JSON：24 小时电量下限表（键 "0"~"23" 对应值 0~1；缺项会报错）')
    parser.add_argument('--max_soc_normal', type=float, default=DEFAULTS.get('max_soc_normal'),
                        help='平时允许的最高电量比例（0~1，默认 0.99）')
    parser.add_argument('--max_soc_outage', type=float, default=DEFAULTS.get('max_soc_outage'),
                        help='停电期间允许的最高电量比例（0~1，默认 0.87）')
    parser.add_argument('--max_soc_reduction_in_outage', type=float, default=DEFAULTS.get('max_soc_reduction_in_outage'),
                        help='停电期间的降额上限（0~1，默认 0.70）')
    parser.add_argument('--B_low', type=float, default=DEFAULTS.get('B_low'),
                        help='增负荷阈值系数：净负荷低于「均值 − B_low×标准差」就充电（默认 1.18）')
    parser.add_argument('--b_low', type=float, default=DEFAULTS.get('b_low'),
                        help='同上（历史小写写法，两种都认）')
    parser.add_argument('--B_high', type=float, default=DEFAULTS.get('B_high'),
                        help='减负荷阈值系数：净负荷高于「均值 + B_high×标准差」就放电（默认 1.0）')
    parser.add_argument('--b_high', type=float, default=DEFAULTS.get('b_high'),
                        help='同上（历史小写写法，两种都认）')
    parser.add_argument('--TMP_max_reduction_percent', type=float, default=DEFAULTS.get('TMP_max_reduction_percent'),
                        help='温度控制的最大降额比例（默认 0.0）')
    parser.add_argument('--tmp_max_reduction_percent', type=float, default=DEFAULTS.get('tmp_max_reduction_percent'),
                        help='同上（历史小写写法，两种都认）')
    parser.add_argument('--min_cool_per_c_overheat', type=float, default=DEFAULTS.get('min_cool_per_c_overheat'),
                        help='每超设定点 1°C 至少开多少制冷（冷机开环保底）')
    parser.add_argument('--min_cool_per_c_outdoor_gap', type=float, default=DEFAULTS.get('min_cool_per_c_outdoor_gap'),
                        help='室外温度高于设定点时每 1°C 至少开多少制冷')
    parser.add_argument('--outdoor_gap_deadband_c', type=float, default=DEFAULTS.get('outdoor_gap_deadband_c'),
                        help='上面那条的死区宽度（°C）')
    parser.add_argument('--outdoor_floor_max_overheat_c', type=float, default=DEFAULTS.get('outdoor_floor_max_overheat_c'),
                        help='室内超设定点达到该值后，保底开度不再随室外温度变')
    parser.add_argument('--cooling_demand_feedforward_frac', type=float, default=DEFAULTS.get('cooling_demand_feedforward_frac'),
                        help='按制冷需求预测提前加多少开度（前馈）')
    parser.add_argument('--demand_feedforward_only_when_overheat', type=str, default=DEFAULTS.get('demand_feedforward_only_when_overheat'),
                        help='true/false：前馈是否只在过热时生效')
    parser.add_argument('--outdoor_floor_allow_when_under_setpoint', type=str, default=DEFAULTS.get('outdoor_floor_allow_when_under_setpoint'),
                        help='true/false：室内已低于设定点时，还允许室外触发的保底吗')
    parser.add_argument('--clear_open_loop_floor_when_under_setpoint', type=str, default=DEFAULTS.get('clear_open_loop_floor_when_under_setpoint'),
                        help='true/false：低于设定点时是否清掉开环保底')
    parser.add_argument('--use_lagged_dynamics_indoor', type=str, default=DEFAULTS.get('use_lagged_dynamics_indoor'),
                        help='true/false：室内温度是否用带滞后的动力学来估')
    parser.add_argument('--lagged_indoor_only_when_hotter', type=str, default=DEFAULTS.get('lagged_indoor_only_when_hotter'),
                        help='true/false：滞后动力学是否只在更热时用')
    parser.add_argument('--lagged_indoor_hotter_margin_c', type=float, default=DEFAULTS.get('lagged_indoor_hotter_margin_c'),
                        help='上面那条的余量（°C）')
    parser.add_argument('--post_outage_soft_charge_enabled', type=str, default=DEFAULTS.get('post_outage_soft_charge_enabled'),
                        help='true/false：停电恢复后允许缓充')
    parser.add_argument('--post_outage_relax_steps', type=int, default=DEFAULTS.get('post_outage_relax_steps'),
                        help='缓充持续多少步')
    parser.add_argument('--post_outage_waive_min_soc', type=str, default=DEFAULTS.get('post_outage_waive_min_soc'),
                        help='true/false：缓充期间豁免电量下限')
    parser.add_argument('--post_outage_max_ele_charge', type=float, default=DEFAULTS.get('post_outage_max_ele_charge'),
                        help='缓充期间电池最多充到多少（0~1）')
    parser.add_argument('--post_outage_forbid_charge_when_overheat', type=str, default=DEFAULTS.get('post_outage_forbid_charge_when_overheat'),
                        help='true/false：过热时禁止充电')
    parser.add_argument('--post_outage_overheat_c', type=float, default=DEFAULTS.get('post_outage_overheat_c'),
                        help='判定过热的偏离量（°C）')
    parser.add_argument('--post_outage_tmp_cap_enabled', type=str, default=DEFAULTS.get('post_outage_tmp_cap_enabled'),
                        help='true/false：电力恢复后限制温度控制功率')
    parser.add_argument('--post_outage_tmp_cap_steps', type=int, default=DEFAULTS.get('post_outage_tmp_cap_steps'),
                        help='限功率持续多少步')
    parser.add_argument('--post_outage_tmp_max_start', type=float, default=DEFAULTS.get('post_outage_tmp_max_start'),
                        help='限功率的起始上限（0~1）')
    parser.add_argument('--post_outage_tmp_ramp', type=str, default=DEFAULTS.get('post_outage_tmp_ramp'),
                        help='true/false：限制是否逐步放开')
    parser.add_argument('--post_outage_tmp_stagger', type=str, default=DEFAULTS.get('post_outage_tmp_stagger'),
                        help='true/false：各楼栋错峰放开')
    parser.add_argument('--price_aware_battery_enabled', type=str, default=DEFAULTS.get('price_aware_battery_enabled'),
                        help='true/false：启用看电价决定充放电')
    parser.add_argument('--price_high_quantile', type=float, default=DEFAULTS.get('price_high_quantile'),
                        help='高价分位点（0~1，默认 0.75）')
    parser.add_argument('--price_low_quantile', type=float, default=DEFAULTS.get('price_low_quantile'),
                        help='低价分位点（0~1，默认 0.25）')
    parser.add_argument('--price_history_min_steps', type=int, default=DEFAULTS.get('price_history_min_steps'),
                        help='算分位点至少需要多少步历史（默认 48）')
    parser.add_argument('--price_high_soc_threshold', type=float, default=DEFAULTS.get('price_high_soc_threshold'),
                        help='高价时的电量阈值（默认 0.70）')
    parser.add_argument('--price_high_forbid_charge', type=str, default=DEFAULTS.get('price_high_forbid_charge'),
                        help='true/false：高价时禁止充电')
    parser.add_argument('--price_high_force_discharge', type=str, default=DEFAULTS.get('price_high_force_discharge'),
                        help='true/false：高价时强制放电')
    parser.add_argument('--price_high_discharge_ele', type=float, default=DEFAULTS.get('price_high_discharge_ele'),
                        help='高价时的放电量（默认 0.15）')
    parser.add_argument('--price_min_reserve_soc', type=float, default=DEFAULTS.get('price_min_reserve_soc'),
                        help='为高价时段预留的最低电量（默认 0.55）')
    parser.add_argument('--price_global_reserve_enabled', type=str, default=DEFAULTS.get('price_global_reserve_enabled'),
                        help='true/false：启用全楼预留电量')
    parser.add_argument('--price_low_target_soc', type=float, default=DEFAULTS.get('price_low_target_soc'),
                        help='低价时充到多少（默认 0.80）')
    parser.add_argument('--price_low_charge_ele', type=float, default=DEFAULTS.get('price_low_charge_ele'),
                        help='低价时的充电量（默认 0.25）')
    parser.add_argument('--price_low_search_boost', type=str, default=DEFAULTS.get('price_low_search_boost'),
                        help='true/false：低价时加强树搜索')
    parser.add_argument('--tau', type=int, default=DEFAULTS.get('tau'),
                        help='树搜索向前看几步（只允许 1/2/3，默认 1）')
    parser.add_argument('--balance_type', type=str, default=DEFAULTS.get('balance_type'),
                        help='树搜索适应度类型：A 跟踪历史均值 / B 抑制波动 / C 跟踪均值与预测中点（默认 C）')
    parser.add_argument('--eval_schema', '--eval-schema', dest='eval_schema', type=str,
                        default=DEFAULTS.get('eval_schema'),
                        help='本脚本仿真/KPI 用的数据集（下划线/中划线两种写法都认）')
    # ------------------------------------------------------------------
    # CHESCA-ResMARL 专属参数
    # ------------------------------------------------------------------
    parser.add_argument('--marl_mode', '--marl-mode', dest='marl_mode', type=str,
                        default='multi_agent',
                        help='运行模式：multi_agent = CHESCA + SAC 残差（本入口的常态）；'
                             'none = 退化成纯 CHESCA（便于对照）')
    parser.add_argument('--train_task_id', '--train-task-id', dest='train_task_id', type=str,
                        default=None,
                        help='前置训练任务 id：据它到 <输出根>/<id>-train/checkpoints/ 下找模型')
    parser.add_argument('--multi_agent_checkpoint', '--multi-agent-checkpoint',
                        dest='multi_agent_checkpoint', type=str, default=None,
                        help='直接指定 Multi-Agent SAC 模型目录（优先于 --train-task-id）')
    parser.add_argument('--residual_alpha', '--residual-alpha', dest='residual_alpha', type=float,
                        default=DEFAULT_RESIDUAL_ALPHA,
                        help='残差强度 α：a_final = (1-α)·a_base + α·a_rl（0~1；0 等于纯 CHESCA）')
    parser.add_argument('--residual_action_mask', '--residual-action-mask',
                        dest='residual_action_mask', type=str, default=None,
                        help='逐维掩码，如 {"dhw":false,"ele":true,"tmp":false}；'
                             '为 false 的维度保持 CHESCA 原值')
    parser.add_argument('--resmarl_after_safety', '--resmarl-after-safety',
                        dest='resmarl_after_safety', type=str, default='true',
                        help='true/false：是否在安全审查（动作边界裁剪）之后才叠加残差')
    # 与 CHESCA.py 同一策略：容忍未识别参数并提示，而不是 exit 2 崩掉
    args, unknown = parser.parse_known_args()
    if unknown:
        log_console(f'提示：忽略未识别参数 {unknown}')
    return args


# 由「前置训练任务 id」推出模型目录
def resolve_checkpoint(cli_checkpoint, train_task_id, output_dir):
    """返回 (模型目录, 来源说明)；找不到时返回 (None, 原因)。"""
    given = str(cli_checkpoint or '').strip()
    if given:
        path = Path(given)
        if is_checkpoint_dir(path):
            return str(path), '--multi-agent-checkpoint'
        # 不在这里报错：路径可能指向"父目录/文件"，交给模型的加载器去判断并给出准确报错
        return given, '--multi-agent-checkpoint（未在磁盘上确认，按原值传入）'

    task = str(train_task_id or '').strip().strip('/\\')
    if not task:
        return None, '既没有 --train-task-id，也没有 --multi-agent-checkpoint'

    if is_checkpoint_dir(Path(task)):
        return str(Path(task)), '--train-task-id（直接给了模型目录）'

    out_root = Path(output_dir).resolve().parent
    dir_names = [task] if task.endswith('-train') else [task + '-train', task]
    searched = []
    for name in dir_names:
        for rel in (MARL_CKPT_REL_DIR, MARL_CKPT_BEST_REL_DIR):
            cand = out_root / name / rel
            searched.append(cand)
            if is_checkpoint_dir(cand):
                return str(cand), f'--train-task-id={task}'
        # 也可以直接给「训练子任务目录」本身（平台把它当 outputs 根用）
        cand = out_root / name
        searched.append(cand)
        if is_checkpoint_dir(cand):
            return str(cand), f'--train-task-id={task}'

    detail = '\n  '.join(str(p) for p in searched[:6])
    return None, (f'没找到训练任务 {task} 的模型目录。已查找：\n  {detail}\n'
                  f'（请确认该训练任务已跑完，或用 --multi-agent-checkpoint 直接指定模型目录）')


# 评估主流程
def main():
    args = parse_args()

    # 确定导出目录
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    render_session = '.' if args.output_dir else args.render_session

    # 配置只有一个来源：命令行（缺省值来自 DEFAULTS 与上面的 DEFAULT_RESIDUAL_*）
    agent_config = build_agent_config(_cli_overrides_from_args(args)) or {}

    # 残差开关与三项参数（marl_mode != multi_agent 时它会把残差整体关掉）
    agent_config = apply_resmarl_cli_overrides(agent_config, args)
    marl_mode = str(agent_config.get('marl_mode') or 'multi_agent')

    # 模型：先 --multi-agent-checkpoint，再 --train-task-id
    ckpt, source = resolve_checkpoint(args.multi_agent_checkpoint, args.train_task_id, output_dir)
    if marl_mode == 'multi_agent':
        if not ckpt:
            raise FileNotFoundError(f'CHESCA-ResMARL 需要 Multi-Agent SAC 模型：{source}')
        agent_config['multi_agent_checkpoint'] = ckpt
        agent_config['resmarl_enabled'] = True
    log_console('========== CHESCA-ResMARL 评估入口 ==========')
    log_console(f'marl_mode={marl_mode}')
    log_console(f'residual_alpha={agent_config.get("residual_alpha")}')
    log_console(
        'residual_action_mask='
        + json.dumps(agent_config.get('residual_action_mask'), ensure_ascii=False)
    )
    log_console(f'resmarl_after_safety={agent_config.get("resmarl_after_safety")}')
    if marl_mode == 'multi_agent':
        log_console(f'multi_agent_checkpoint={ckpt}（来源：{source}）')

    class Config:
        SCHEMA = DEFAULT_SCHEMA
        EVAL_SCHEMA = args.eval_schema
        num_episodes = 1
        episode_time_steps = args.episode_time_steps if args.episode_time_steps else None
        RENDER_DIR = output_dir
        RENDER_SESSION = render_session
        AGENT_CONFIG = agent_config
        ENABLE_RENDER = not args.no_render

    # 残差层由本入口建好再交给 CHESCA 的评估内核（加载 SAC、换残差器、建旁路环境都在层里）
    layer = build_residual_layer(agent_config, marl_mode)
    evaluate(Config(), residual=layer)
    sys.stdout.flush()


if __name__ == '__main__':
    main()
