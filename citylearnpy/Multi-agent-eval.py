# Multi-agent 的评估算法入口
import argparse
import json
import os
import sys
import time
from pathlib import Path

# 算子不大，设置单线程启动，避免多线程抢锁
_THREADS = str(max(1, int(os.environ.get('TORCH_NUM_THREADS', '1') or '1')))
os.environ.setdefault('OMP_NUM_THREADS', _THREADS)
os.environ.setdefault('MKL_NUM_THREADS', _THREADS)
os.environ.setdefault('NUMEXPR_NUM_THREADS', _THREADS)

# 执行时会把本脚本复制到 output/outkpis/{taskId}/ 再执行
sys.path[:0] = [str(Path(p).resolve()) for p in (os.environ.get('CITYLEARNPY_DIR'), r'D:\citylearn-demo\citylearnpy') if p and Path(p).is_dir()][:1]

# 日志工具,torch设置单线程
from utils.base import log_console, TORCH_THREADS

# 构建环境配置，动作解析
from utils.env import unwrap_action, _AGENT_ENV_CLS, build_env_config

# 自定义奖励函数相关配置，用于记录决策推演日志
from utils.config import CUSTOM_REWARD_KWARGS, USE_CUSTOM_REWARD, DECISION_TRACE_EVERY, DEFAULT_CHECKPOINT_DIR, DEFAULT_EVAL_SCHEMA, DEFAULT_OUTPUT_DIR

from utils.report import decision_trace_path, print_kpis_for_java, build_decision_recorder, record_step_trace

# 动作注入钩子与读取checkpoint的工具
from utils.train import load_multi_agent_checkpoint,install_action_hook

# 外部入参
def parse_args():
    parser = argparse.ArgumentParser(description='SAC Multi-Agent 评估（从 checkpoint 恢复模型，只跑仿真出 KPI）')
    parser.add_argument('--output-dir', '-o', type=str, default=None,
                        help='把 KPI 与仿真数据导出到这个目录（Java 平台会传入任务目录）')
    parser.add_argument('--eval-schema', type=str, default=DEFAULT_EVAL_SCHEMA,
                        help=f'评估用数据集：CityLearn 数据目录名（默认 {DEFAULT_EVAL_SCHEMA}）')
    parser.add_argument('--checkpoint', type=str, default=None,
                        help=(f'要评估的模型：Multi-agent-train.py 训练产出的 RLlib checkpoint 路径，'f'默认 {DEFAULT_CHECKPOINT_DIR}'))
    parser.add_argument('--no-trace', action='store_true',
                        help='不采集 decision_trace.json（只影响日志，KPI 与仿真结果完全不变）')
    return parser.parse_args()

if __name__ == '__main__':
    # 让环境每一步都把动作记下来（奖励统计与决策推演要用）
    install_action_hook()

    # 解析命令行参数
    args = parse_args()

    # 确定输出目录
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # 解析评估参数
    eval_schema = (args.eval_schema or '').strip() or DEFAULT_EVAL_SCHEMA
    # 定义步数变量
    eval_steps = None

    # 读回训练时的奖励配置
    ckpt_in = str(getattr(args, 'checkpoint', None) or '').strip() or str(DEFAULT_CHECKPOINT_DIR)
    import json                                        # noqa: E402（内联段自带依赖 ✓）
    from utils.config import REWARD_CONFIG_SIDECAR      # noqa: E402
    # 从 checkpoint 目录读回「训练时的奖励口径」（sidecar `reward_config.json` ✓）
    # ⚠️ 2026-10-08：原先是个独立函数（utils/config.py 的 `_read_..._checkpoint` ✓）——
    #   它只有这一处调用 ⇒ 已内联到这里 ✓（那个名字从全仓消失 ✓）。
    # 查找顺序：<checkpoint>/reward_config.json → <checkpoint>/*/reward_config.json
    #   （后者兼容「给的是父目录」的调用方式 ✓）；找不到（历史断点 ✗）⇒ 什么都不改 + 一行 warning ✓
    _rc_dirs = [Path(ckpt_in)]
    if Path(ckpt_in).is_dir():
        _rc_dirs += sorted((c for c in Path(ckpt_in).glob('*/') if c.is_dir()), reverse=True)
    _rc_f = next((d / REWARD_CONFIG_SIDECAR for d in _rc_dirs
                  if (d / REWARD_CONFIG_SIDECAR).is_file()), None)
    if _rc_f is None:
        log_console(f'[奖励口径] 该 checkpoint 未存 {REWARD_CONFIG_SIDECAR}（历史断点），'
                    f'先用当前代码默认；要读回训练口径请先用新版训练脚本跑一次')
    else:
        try:
            _rc_saved = json.loads(_rc_f.read_text(encoding='utf-8'))
            log_console(f'[奖励口径] 已从 checkpoint 读回训练时的奖励配置'
                        f'（{_rc_f}；保存于 {_rc_saved.get("saved_at", "?")}）')
            CUSTOM_REWARD_KWARGS.update(_rc_saved.get('reward_kwargs') or {})
        except Exception as exc:
            log_console(f'[奖励口径] 读取失败，改用当前代码默认: '
                        f'{type(exc).__name__}: {exc}')

    # 初始化配置
    eval_env_config = build_env_config(
        eval_schema, eval_steps, output_dir, enable_render=True, record_details=True
    )

    # 构建评估环境
    env = _AGENT_ENV_CLS(eval_env_config)
    citylearn_env = env.env.unwrapped
    observations, _ = env.reset()

    # 记录日志
    log_console(f'初始化评估，导出目录: {output_dir.resolve()}')
    if USE_CUSTOM_REWARD:
        log_console(
            f'奖励函数=CustomComfortReward（替换数据集默认，参数={CUSTOM_REWARD_KWARGS}）'
        )
    else:
        log_console('奖励函数=数据集 schema 默认 ComfortReward（USE_CUSTOM_REWARD=False）')
    log_console(f'评估 schema={eval_schema} steps={eval_steps or "auto(数据集自带)"}')
    log_console(
        f'计算线程: torch={TORCH_THREADS}（TORCH_NUM_THREADS='
        f'{os.environ.get("TORCH_NUM_THREADS") or "未设→1"}）'
    )
    log_console(f'评估模式：加载 Multi-Agent SAC checkpoint = {ckpt_in}')

    # 读取checkpoint，恢复模型
    model = load_multi_agent_checkpoint(ckpt_in, log_console=log_console, eval_mode=True)

    # 确定step
    total_steps = int(getattr(citylearn_env, 'episode_time_steps', 0) or 0)
    if total_steps <= 0:
        raise SystemExit(
            f'[致命] 读不到回合长度（episode_time_steps={total_steps}）'
            '—— 检查 schema / 数据集文件是否完整'
        )
    log_console(f'开始仿真，共 {total_steps} 步（数据集自带长度）...')

    # 决策推演日志
    trace_every = DECISION_TRACE_EVERY
    trace_on = not getattr(args, 'no_trace', False)
    trace_off_reason = '--no-trace' if getattr(args, 'no_trace', False) else ''
    decision_recorder = build_decision_recorder(
        citylearn_env,
        enabled=trace_on,
        every=trace_every,
        off_reason=trace_off_reason,
        log_console=log_console,
    )
    trace_path = None

    # 计数与计时器
    step_count = 0    
    t_eval_start = time.perf_counter() 
    t_env_step = 0.0 
    t_trace = 0.0 
    t_flush = 0.0 
 
    # 主循环
    while not env.terminated:
        # 固定各楼栋顺序
        ordered_keys = list(getattr(env, '_agent_ids', None) or list(observations.keys()))
        # 给每栋楼取一次动作
        actions = {
            p: unwrap_action(model.compute_single_action(observations[p], policy_id=p, explore=False))
            for p in ordered_keys
            if p in observations
        }
        # 拿到新观测与奖励
        _t_step_start = time.perf_counter()
        observations, rewards, _, _, _ = env.step(actions)
        t_env_step += time.perf_counter() - _t_step_start
        step_count += 1

        # 采集
        if trace_on:
            _t_trace_start = time.perf_counter()
            try:
                record_step_trace(
                    decision_recorder,
                    citylearn_env,
                    step_count=step_count,
                    ordered_keys=ordered_keys,
                    actions=actions,
                    rewards=rewards,
                )
            except Exception as exc:
                log_console(f'[决策推演] step {step_count} 记录失败（忽略）: {exc}')
            t_trace += time.perf_counter() - _t_trace_start

        # 写入决策推演日志
        if trace_on and (step_count % trace_every == 0 or env.terminated):
            _t_flush_start = time.perf_counter()
            try:
                trace_path = decision_recorder.save(decision_trace_path(citylearn_env, output_dir))
            except Exception as exc: 
                log_console(f'[决策推演] 落盘失败（忽略）: {exc}')
            t_flush += time.perf_counter() - _t_flush_start

        # 打印进度日志
        if step_count == 1 or step_count % 36 == 0 or env.terminated:
            log_console(
                f'[进度] {step_count}/{total_steps} 步 ({100 * step_count / total_steps:.1f}%)'
            )

    _eval_secs = time.perf_counter() - t_eval_start
    if trace_path is not None:
        log_console(
            f'决策推演日志: {trace_path.resolve()} '
            f'（{len(decision_recorder.steps)} 步，每 {trace_every} 步批量落盘）'
        )
    else:
        log_console('决策推演日志未落盘（未启用或本步记录为空）')

    # 评估耗时
    log_console(
        f'评估用时 {_eval_secs:.1f}s（{step_count} 步，{step_count / max(_eval_secs, 1e-9):.1f} step/s）= '
        f'环境步进 {t_env_step:.1f}s({t_env_step / max(_eval_secs, 1e-9):.0%}) '
        f'+ 推演采集 {t_trace:.1f}s({t_trace / max(_eval_secs, 1e-9):.0%}) '
        f'+ 推演落盘 {t_flush:.1f}s({t_flush / max(_eval_secs, 1e-9):.0%})'
    )

    # 打印奖励
    rf_eval = getattr(citylearn_env, 'reward_function', None)
    if rf_eval is not None and hasattr(rf_eval, 'stats_summary'):
        log_console('[评估阶段] ' + rf_eval.stats_summary())
    if rf_eval is not None and hasattr(rf_eval, 'kpi_summary'):
        log_console('[评估阶段] ' + rf_eval.kpi_summary())

    # 收尾，结果
    log_console('仿真完成，正在计算 KPI...')
    kpis = citylearn_env.evaluate()
    # 长表转宽表
    kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
    kpis = kpis.dropna(how='all')

    # 导出kpis
    if not getattr(citylearn_env, '_final_kpis_exported', False):
        citylearn_env.export_final_kpis(filepath='exported_kpis.csv')
    if citylearn_env.new_folder_path:
        kpi_path = Path(citylearn_env.new_folder_path) / 'exported_kpis.csv'
        log_console(f'输出目录: {Path(citylearn_env.new_folder_path).resolve()}')
        log_console(f'KPI 文件: {kpi_path.resolve()}')
    else:
        log_console('未生成导出目录（请确认 render_mode 已启用）')

    # 参数给到java控制台
    print_kpis_for_java(kpis)
    # 强制刷缓冲
    sys.stdout.flush()
