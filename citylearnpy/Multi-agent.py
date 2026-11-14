"""
SAC 多智能体训练/评估脚本
========================

纯 Multi-Agent SAC 端到端控制（非 CHESCA-ResMARL）。
结构参考 Multi-agent_copy.py；奖励默认使用**外部模块** custom_comfort_reward.py
里的 CustomComfortReward（本文件只在顶部 import 它，类体不在本文件内；
逻辑与数据集默认 ComfortReward 完全一致，便于在该模块上继续修改；
把 USE_CUSTOM_REWARD 置 False 可回退到 schema 默认奖励）。

评估阶段会写「决策推演」decision_trace.json 供模型优选界面查看：
  每步关键参数（室温/设定点/温差/动作/制冷用电/电价/SOC/回报）先缓存内存，
  每 `DECISION_TRACE_EVERY` 步（固定 144 ✓，见 utils/config.py）批量落盘一次，避免逐步写盘的 IO 开销。

可配置参数：
  --train-schema  训练数据集
  --eval-schema   评估数据集
  --train-epochs  训练轮数，默认取文件顶部 TRAIN_EPOCHS
  --seed          随机种子，默认取 DEFAULT_SEED（可复现；论文方差跑 3 次：--seed 0/1/2）
  --check-reward  仅自检新奖励与原版是否逐位一致后退出
（另保留 --output-dir 供 Java 平台写 KPI）

训练规模：**以文件顶部常量为准**；其中一条不能改的约束是
  `ROLLOUT_FRAGMENT_LENGTH` 必须保持 "auto"（实测显式改成 500/1000 会让每轮训练量
  从 ~100 批塌到 1 批、模型崩坏 ✗）
  早停多一条「判据⑤ 崩坏止损」：第 100 轮体检一次，某栋高温>90% 或低温>80% 即停
  训练/评估结束都会打印一行「奖励统计」，其中「读到act」为 0 说明动作注入未生效。

⚠️ 注释约定见紧随本 docstring 之后的那段注释（全局只声明一次）✓

用法：
  python Multi-agent.py -o D:\\citylearn-demo\\output\\outkpis\\任务ID \\
      --train-schema citylearn_challenge_2023_phase_2_local_evaluation \\
      --eval-schema citylearn_challenge_2023_phase_2_online_evaluation_1
"""


# 【依赖总览】全部 import 都在下面这一段（正文不再出现 import ✓）
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

# 日志工具，设置torch单线程
from utils.base import CITYLEARNPY_DIR, log_console, TORCH_THREADS

import pandas as pd
# 构建环境配置，动作解析
from utils.env import (
    install_temp_delta_override,
    patch_schema_observations,
    resolve_schema_path,
    unwrap_action,
    unwrap_citylearn_env,
    _AGENT_ENV_CLS,
    COOL_FLOOR_ENABLE,
    COOL_FLOOR_UNTIL,
    COOL_LOAD_CENTERED_ENABLE,
    COOL_LOAD_MAX_FRAC,
    COOL_LOAD_MIN_FRAC,
    COOL_LOAD_NOLOAD_MAX,
    COOL_REMAP_FLOOR,
    COOL_REMAP_SPAN,
    COOL_SPAN_ENABLE,
    ContextRLlibEnv,
    OBS_CONTEXT_A_REF,
    OBS_CONTEXT_CAPACITY,
    OBS_CONTEXT_ENABLE,
    OBS_CONTEXT_IDENTITY,
    set_cool_floor_scale,
    update_cool_floor_scale,
    build_env_config,
    build_probe_env,
)

# utils/train.py：读数 / 中期评估 / checkpoint 存取 / 动作注入钩子（诊断脚本按 `ma.xxx` 取用 ✓）
from utils.train import (
    find_metric,
    read_building_series,
    run_mid_eval,
    run_mini_eval,
    run_nocontrol_cost_ref,
)

# 自定义奖励函数相关配置，用于记录决策推演日志
from utils.config import (
    CUSTOM_REWARD_KWARGS,
    USE_CUSTOM_REWARD,
    _CUSTOM_REWARD_MODULE,
    describe_reward_function,
    DECISION_TRACE_EVERY,
)

from utils.report import decision_trace_path, print_kpis_for_java, MarlDecisionTraceRecorder, build_decision_recorder, record_step_trace

from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper, RLlibMultiAgentEnv
from gymnasium import spaces   # 扩展 observation_space 用

from utils.config import (
    DEFAULT_CHECKPOINT_DIR,
    DEFAULT_EVAL_SCHEMA,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TRAIN_SCHEMA,
)

from utils.config import (
    TRAIN_EPOCHS,
    TRAIN_BATCH_SIZE,
    MIN_SAMPLE_BEFORE_LEARN,
    ROLLOUT_FRAGMENT_LENGTH,
    MIN_SAMPLE_TIMESTEPS_PER_ITERATION,
    TRAIN_INTENSITY,
    TRAIN_BATCHES_PER_ROUND_MIN,
    DEFAULT_SEED,
    MINI_EVAL_EVERY,
    MINI_EVAL_STEPS,
    MID_EVAL_WINDOWS,
    MID_TARGET_HOT,
    MID_TARGET_COLD,
    MID_VOTE_RATIO,
    MID_VOTE_PATIENCE,
    MID_MIN_GAIN,
    MID_STOP_BY_VOTE,
    MID_STOP_BY_SCORE,
    MID_STOP_ON_WORSEN,
    MID_WORSEN_MARGIN,
    MID_KPI_SRC_TOL,
    MID_WORSEN_PATIENCE,
    MID_STOP_WHEN_GOOD,
    MID_STOP_WHEN_CONVERGED,
    MID_CONVERGE_SUM,
    MID_CONVERGE_PATIENCE,
    MID_STOP_ON_CRASH,
    CRASH_GUARD_EPOCH,
    CRASH_GUARD_MAX_HOT,
    CRASH_GUARD_MAX_COLD,
    MIN_TRAIN_EPOCHS,
    CKPT_DIR,
    CKPT_EVERY,
    BEST_CKPT_ENABLE,
    BEST_CKPT_DIR_NAME,
    BEST_CKPT_META,
    BEST_CKPT_TARGET_SUM,
    BEST_CKPT_TIEBREAK,
    P4_COST_WEIGHT,
    P4_COST_HINGE,
    BEST_CKPT_MIN_GAIN,
    BEST_CKPT_METRIC_VER,
    CKPT_STORE_REPLAY_BUFFER,
    REPLAY_BUFFER_CAPACITY,
)








from custom_comfort_reward import CustomComfortReward
from custom_comfort_reward import _cap_txt              # 推演叙事用
# 奖励自检的实现：`--check-reward` 用它把自定义奖励与数据集原版逐位比对 ✓
from custom_comfort_reward import check_reward_equivalence as _reward_equiv_check




from utils.train import install_action_hook, log_reward_banner













# 外部入参
def parse_args():
    parser = argparse.ArgumentParser(description='SAC Multi-Agent 训练/评估（仅配置训测数据集）')
    parser.add_argument('--output-dir', '-o', type=str, default=None,
                        help='把 KPI 与仿真数据导出到这个目录（Java 平台会传入任务目录）')
    parser.add_argument('--train-schema', type=str, default=DEFAULT_TRAIN_SCHEMA,
                        help=f'训练数据集（默认 {DEFAULT_TRAIN_SCHEMA}）')
    parser.add_argument('--eval-schema', type=str, default=DEFAULT_EVAL_SCHEMA,
                        help=f'评估用数据集：CityLearn 数据目录名（默认 {DEFAULT_EVAL_SCHEMA}）')
    parser.add_argument('--train-epochs', type=int, default=None,
                        help=(f'训练轮数（硬上限；Java 注入走这个），默认 {TRAIN_EPOCHS}' f'（每轮采样 ≈ {MIN_SAMPLE_TIMESTEPS_PER_ITERATION} env-step；' f'训练 batch={TRAIN_BATCH_SIZE}）'))
    parser.add_argument('--min-train-epochs', type=int, default=None,
                        help=(f'最小训练轮数：在此之前一律继续训练（早停判据②不生效），' f'默认 {MIN_TRAIN_EPOCHS}'))
    parser.add_argument('--no-checkpoint', action='store_true',
                        help='关闭训练中的 checkpoint 保存（默认开启，每 CKPT_EVERY 轮一次）')
    parser.add_argument('--no-best-ckpt', action='store_true',
                        help=('P2-D：关闭「训练期最优快照用于最终评估」' f'（默认开启：中期评估创新低即存 best 快照，评估用 best 权重；' f'关闭后退回用末次权重）'))
    parser.add_argument('--checkpoint-dir', type=str, default=None,
                        help=f'checkpoint 目录，默认 {CKPT_DIR}（相对本脚本所在目录）')
    parser.add_argument('--check-reward', action='store_true',
                        help='自检开关：对比自定义奖励与数据集原版奖励是否逐位一致，打印结果后直接退出')
    parser.add_argument('--bat-weight', type=float, default=None,
                        help=('电池"择时"项（低买高卖）权重：越大利诱电池低价充电、高价放电。' '默认 = CUSTOM_REWARD_KWARGS 的 50。' '语义：r_arb = −w×max(0, price−p_ref)×(充电−有效放电) ⇒ 平价中性、' '高价(16~18时)放=大奖、高价充=重罚；只作用于电池，不影响制冷'))
    parser.add_argument('--cost-weight', type=float, default=None,
                        help=('电费项权重覆盖：是否惩罚"从电网买电"，作用于 price×max(0,net)，' '与官方 cost_total 逐位同构。' '默认 = CUSTOM_REWARD_KWARGS 的 0（关闭）。语义：r_cost=−w×price×max(0,net)。' '⚠️ 历史上 50 会压制电池套利（d0f8b032）；建议小权重扫 5 / 10 / 20'))
    parser.add_argument('--p4-hinge-w', type=float, default=None,
                        help=('P-13：best-ckpt 选择指标的**成本 hinge** 权重（默认 = P4_COST_HINGE["w"] 的 0）。' '语义：metric += w×max(0, 成本率 − P4_COST_HINGE["target"])，' '达标轮之间仍按舒适排序。建议扫 0.15 / 0.3 / 0.6'))
    parser.add_argument('--p4-hinge-target', type=float, default=None,
                        help=('P-13：hinge 目标线覆盖（默认 = P4_COST_HINGE["target"] 的 0.93）。' '注意 district 成本率与单栋的换算：实测 B2 ≈ **1.07~1.09 × district** ' '⇒ 要让 B2 落到 1.0 以下，目标线需 ≈ **0.90**（0.93 只能保证 district ≤0.93）'))
    parser.add_argument('--bat-loss', type=float, default=None,
                        help=('电池"损耗/账单"项权重：惩罚"买了电却没用于负载"的净循环量，' '抑制为抓高峰而过度充放。默认 = CUSTOM_REWARD_KWARGS 的 12。' '语义：r_loss = −w×price×(充电−有效放电)。扫 0(=P-1b旧行为) / 6 / 12 / 20'))
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                        help=f'固定 RLlib/ray 随机种子，默认 {DEFAULT_SEED}（可复现）；论文方差跑 3 次：--seed 0/1/2')
    parser.add_argument('--no-trace', action='store_true',
                        help='不采集 decision_trace.json（只影响日志，KPI 与仿真结果完全不变）')
    return parser.parse_args()


if __name__ == '__main__':
    # 流程：① 装钩子 → ② 解析参数 → ③ 奖励自检(可选) → ④ 定目录/数据集/轮数 → ⑤ 覆盖权重(可选) → ⑥ 建环境 → ⑦ 跑训练 → ⑧ 取回产出 → ⑨ 收尾汇总 → ⑩ 存 checkpoint

    # 让环境每一步都把动作记下来（奖励统计与决策推演要用）
    install_action_hook()

    # 解析命令行参数
    args = parse_args()

    # 奖励公式自检开关（--check-reward）：不训练、不仿真，几秒后退出
    if args.check_reward:
        # 只做奖励自检（不训练）：确认新奖励与数据集原版逐位一致
        _worst = _reward_equiv_check(CUSTOM_REWARD_KWARGS, verbose=True)
        sys.exit(0 if _worst == 0.0 else 1)

    # 确定输出目录（-o/--output-dir 优先，否则用默认值）
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # 确定数据集
    train_schema = (args.train_schema or '').strip() or DEFAULT_TRAIN_SCHEMA
    eval_schema = (args.eval_schema or '').strip() or DEFAULT_EVAL_SCHEMA
    # 定义步数变量
    train_steps = None
    eval_steps = None
    # ④ 训练轮数 = --train-epochs（Java 注入优先），没传就用文件顶部常量 TRAIN_EPOCHS ✓
    train_epochs = int(args.train_epochs or TRAIN_EPOCHS)
    min_train_epochs = int(
        getattr(args, 'min_train_epochs', None)
        if getattr(args, 'min_train_epochs', None) is not None else MIN_TRAIN_EPOCHS
    )
    if min_train_epochs > train_epochs:
        log_console(
            f'[轮数] 最小训练轮数 {min_train_epochs} > 最大 {train_epochs} → 自动收敛为 {min_train_epochs}'
        )
        train_epochs = min_train_epochs
    min_train_epochs = max(1, min(min_train_epochs, train_epochs))
    # 随机种子：默认 DEFAULT_SEED(=1)，显式固定以保证可复现
    seed = int(getattr(args, 'seed', None) if getattr(args, 'seed', None) is not None else DEFAULT_SEED)
    # ⑤ 按命令行覆盖奖励/选择权重（不传即用默认值；须早于建环境 ✗）—— 表列：参数名/容器/键/显示名/说明
    for _oname, _obox, _okey, _oshown, _owhy in (
        ('bat-weight', CUSTOM_REWARD_KWARGS, 'bat_weight', 'bat_weight', '电池择时项'),
        ('bat-loss', CUSTOM_REWARD_KWARGS, 'bat_loss_weight', 'bat_loss_weight', '电池损耗项'),
        ('cost-weight', CUSTOM_REWARD_KWARGS, 'cost_weight', 'cost_weight',
         '电费项 price×max(0,net)，含电池'),
        ('p4-hinge-w', P4_COST_HINGE, 'w', 'P4_COST_HINGE["w"]', None),   # 说明见下：附当前目标线 ✓
        ('p4-hinge-target', P4_COST_HINGE, 'target', '目标线',
         'B2 ≈ 1.07~1.09 × 目标线 ⇒ 0.90 对应 B2 ≈ 0.96~0.98'),
    ):
        _oval = getattr(args, _oname.replace('-', '_'), None)
        if _oval is None:
            continue
        _obox[_okey] = float(_oval)
        _otag = '[P-13]' if _oname.startswith('p4-hinge') else '[奖励]'
        # p4-hinge-w 这条要顺带报出**当前**目标线（扫参时两条必须一起看 ✓）
        _oextra = _owhy or f'目标线 {P4_COST_HINGE.get("target"):g}'
        log_console(f'{_otag} --{_oname} 覆盖：{_oshown}={float(_oval):g}（{_oextra}）')

    # 建训练环境（关闭数据导出与奖励明细 ⇒ 省掉纯日志开销）
    train_env_config = build_env_config(
        train_schema, train_steps, output_dir, enable_render=False, record_details=False
    )
    # 建评估环境（打开数据导出与奖励明细）
    eval_env_config = build_env_config(
        eval_schema, eval_steps, output_dir, enable_render=True, record_details=True
    )

    log_console(f'初始化 SAC 多智能体，导出目录: {output_dir.resolve()}')
    log_reward_banner(log_console)   # 奖励口径 + 动作重标定总览（实现在 utils/train.py ✓）
    log_console(f'训练 schema={train_schema} steps={train_steps or "auto(数据集自带)"}')
    log_console(f'评估 schema={eval_schema} steps={eval_steps or "auto(数据集自带)"}')
    log_console(
        f'训练规模: epochs={train_epochs}（最小 {min_train_epochs}：在此之前不停）'
        f' | 每轮: 采样 fragment={ROLLOUT_FRAGMENT_LENGTH}（auto≈100，单进程采样）'
        f' | 训练 batch={TRAIN_BATCH_SIZE}（agent-steps，×楼栋数才是 agent-step）'
        f' | seed={seed}'
    )
    log_console(
        f'计算线程: torch={TORCH_THREADS}（TORCH_NUM_THREADS='
        f'{os.environ.get("TORCH_NUM_THREADS") or "未设→1"}；OMP='
        f'{os.environ.get("OMP_NUM_THREADS")}）'
        f' | 该 learner 是框架开销主导，线程数不是提速手段'
    )

    # 经验池容量（为 0/None 时不动 RLlib 默认值，避免误配；开启持久化才有限制意义）
    _rb_kwargs = {}
    if REPLAY_BUFFER_CAPACITY:
        _rb_kwargs['replay_buffer_config'] = {'capacity': int(REPLAY_BUFFER_CAPACITY)}

    probe = _AGENT_ENV_CLS(train_env_config)
    # ⑦ 跑训练主循环（实现下沉在 utils/train.py 的 run_training ✓：中期评估/早停都在里面）
    from utils.train import log_training_summary, restore_best_model, run_training
    _o = run_training(
        log=log_console,
        _rb_kwargs=_rb_kwargs,
        args=args,
        eval_schema=eval_schema,
        min_train_epochs=min_train_epochs,
        output_dir=output_dir,
        seed=seed,
        train_env_config=train_env_config,
        train_epochs=train_epochs,
    )

    # ⑧ 取回训练段产出：只接出后面还要用**原名**的 6 个（其余 10 个只喂汇总 ⇒ 实参里写 _o.xxx ✓）
    _last_epoch = _o._last_epoch          # 早停 / 存盘 / 汇总都要
    _mid_best = _o._mid_best              # 存盘 + 汇总
    _mid_eval_hist = _o._mid_eval_hist    # 存盘
    ckpt = _o.ckpt                        # 存盘 + 恢复 best 权重
    ckpt_dir = _o.ckpt_dir                # 存盘目录
    model = _o.model                      # 汇总 / 换 best / 存盘
    _train_secs = time.perf_counter() - _o._t_train0
    # 训练结束（含早停）再存一次，保证"最后一轮"的权重一定落盘 ✓
    ckpt.save('训练结束', _last_epoch, _mid_best, _mid_eval_hist)
    # ⑨ 打印收尾汇总（必须在"换成 best 权重"之前 ✗：它的奖励统计要读末次 model ✓）
    log_training_summary(
        log=log_console, model=model, stopped_reason=_o._stopped_reason,
        last_epoch=_last_epoch, start_epoch=_o._start_epoch, train_epochs=train_epochs,
        train_secs=_train_secs, sampled=_o._sampled_prev,
        mid_best=_mid_best, mid_prev_sums=_o._mid_prev_sums, mid_vote_stale=_o._mid_vote_stale,
        mid_best_sums=_o._mid_best_sums, mid_worsen=_o._mid_worsen, mid_conv=_o._mid_conv,
    )
    # P2-D：用训练期最优快照替换 model（若可用 ✓；位置约束见函数 docstring ✓）
    _best_model = restore_best_model(ckpt, last_epoch=_last_epoch, log=log_console)
    if _best_model is not None:
        model = _best_model
    log_console('训练完成，开始测试仿真...')

    # ---- 建评估环境 + 复位（**仅一体化脚本在这里做** ✗）-------------------------
    # 2026-10-05 挪位：下面这 3 行**不再属于**共享【评估段】——
    #   共享段现在从「步骤 5/8」（`total_steps = ...`）开始 ✓；
    #   eval 侧那 3 行由生成器**提前到"评估配置构建之后"**执行（见 _gen_marl_split.py ✓）。
    #   本脚本留在原地的原因：一体化先训练（约 3h）再建评估环境 ✓ ——
    #   提前建会在整段训练期间白占一个 CityLearnEnv ✗，没有收益 ✗
    # 共享【评估段】里两者唯一的差异在更上面一步 ——「model 从哪来」：
    #     一体化：训练结束后（或 best 快照替换后）的 model；
    #     eval  ：Algorithm.from_checkpoint 从磁盘恢复的 model。
    # _AGENT_ENV_CLS = ContextRLlibEnv（OBS_CONTEXT_ENABLE=True 时；否则 RLlibMultiAgentEnv）。
    #   它做的事：在 RLlib 这一层给每个 agent 的观测追加「制冷能力比值 + 楼栋 one-hot
    #   + 理想负荷所需开度 a_ref」等上下文维（见 OBS_CONTEXT_* 处说明）。
    #   ⚠️ 必须在这一层追加 —— CityLearn 层是 central_agent 的「所有楼拼接」向量，
    #      在那里加维度没法按 agent 正确拆分。
    env = _AGENT_ENV_CLS(eval_env_config)
    # ==== 步骤 4/8：建环境实例 + reset 到第 0 步（并剥出原生 CityLearnEnv）====
    citylearn_env = env.env.unwrapped
    # reset：清空各楼时序、仿真指针拨回 t=0（返回 observations / infos，本脚本只用前者 ✓）
    observations, _ = env.reset()
    # ==== 步骤 5/8：确定这个回合有多长（本 schema = 2208 步）====
    total_steps = int(getattr(citylearn_env, 'episode_time_steps', 0) or 0)
    if total_steps <= 0:
        raise SystemExit(
            f'[致命] 读不到回合长度（episode_time_steps={total_steps}）'
            '—— 检查 schema / 数据集文件是否完整'
        )
    log_console(f'开始仿真，共 {total_steps} 步（数据集自带长度）...')

    # ---- 决策推演日志（decision_trace.json；落盘间隔固定 = DECISION_TRACE_EVERY = 144）----
    trace_every = DECISION_TRACE_EVERY
    # trace_on：本次是否采集推演日志（--no-trace 时 = False；关掉只跳过日志，仿真与 KPI 不变 ✓）
    trace_on = not getattr(args, 'no_trace', False)
    # 建记录器（不采集时**什么都不建** ⇒ None ✓）—— **ON / OFF 那行日志由工厂自己打** ✓
    trace_off_reason = '--no-trace' if getattr(args, 'no_trace', False) else ''
    decision_recorder = build_decision_recorder(
        citylearn_env,
        enabled=trace_on,
        every=trace_every,
        off_reason=trace_off_reason,
        log_console=log_console,
    )
    trace_path = None      # 收尾按它是否为 None 决定打印"已落盘 / 未落盘" ✓（见收尾段 ✓）

    # ---- 计时与计数器 ----
    step_count = 0                      # 已仿真步数（同时是决策推演里的步号）
    t_eval_start = time.perf_counter()  # 评估段总耗时起点（收尾时做拆解）
    t_env_step = 0.0                    # 纯环境步进（含策略推理）累计秒数
    t_trace = 0.0                       # 决策推演「采集」累计秒数
    t_flush = 0.0                       # 决策推演「落盘」累计秒数
    # 计时与计数器（收尾时用来拆解耗时）

    # 不做早停：一直跑到回合结束（KPI 才是全程口径）

    # ---- 主循环：直到回合自然结束（env.terminated）------------------------------
    while not env.terminated:
        # 固定各楼栋顺序（奖励注入与推演都按「第几个 = 第几栋」对应）
        ordered_keys = list(getattr(env, '_agent_ids', None) or list(observations.keys()))
        # 给每栋楼取一次动作（不加随机探索 ⇒ 结果可复现）
        actions = {
            p: unwrap_action(model.compute_single_action(observations[p], policy_id=p, explore=False))
            for p in ordered_keys
            if p in observations
        }
        # 环境走一步：拿到新观测与奖励（以及是否结束）
        _t_step_start = time.perf_counter()
        observations, rewards, _, _, _ = env.step(actions)
        t_env_step += time.perf_counter() - _t_step_start
        step_count += 1

        # 采集本步（**只进内存**，不写盘）
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
            except Exception as exc:  # 记日志失败不影响仿真与 KPI（忽略并继续）
                log_console(f'[决策推演] step {step_count} 记录失败（忽略）: {exc}')
            t_trace += time.perf_counter() - _t_trace_start

        # 到点落盘（每 trace_every 步，或回合结束那一步）
        if trace_on and (step_count % trace_every == 0 or env.terminated):
            _t_flush_start = time.perf_counter()
            try:
                trace_path = decision_recorder.save(decision_trace_path(citylearn_env, output_dir))
            except Exception as exc:  # 落盘失败不影响仿真与 KPI（忽略并继续）
                log_console(f'[决策推演] 落盘失败（忽略）: {exc}')
            t_flush += time.perf_counter() - _t_flush_start

        # 打印进度日志（第 1 步 / 每 36 步 / 回合结束时各一次）
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

    # 评估耗时拆解（环境步进 / 推演采集 / 推演落盘）
    log_console(
        f'评估用时 {_eval_secs:.1f}s（{step_count} 步，{step_count / max(_eval_secs, 1e-9):.1f} step/s）= '
        f'环境步进 {t_env_step:.1f}s({t_env_step / max(_eval_secs, 1e-9):.0%}) '
        f'+ 推演采集 {t_trace:.1f}s({t_trace / max(_eval_secs, 1e-9):.0%}) '
        f'+ 推演落盘 {t_flush:.1f}s({t_flush / max(_eval_secs, 1e-9):.0%})'
    )

    # 打印本阶段奖励统计（与训练期对照，排查「训练好但评估差」）
    rf_eval = getattr(citylearn_env, 'reward_function', None)
    if rf_eval is not None and hasattr(rf_eval, 'stats_summary'):
        log_console('[评估阶段] ' + rf_eval.stats_summary())
    if rf_eval is not None and hasattr(rf_eval, 'kpi_summary'):
        # 另打印「奖励侧自算的 KPI」，与紧随其后的官方 KPI 对照
        log_console('[评估阶段] ' + rf_eval.kpi_summary())

    # ==== 步骤 7/8：收尾 —— 用 CityLearn 官方 evaluate 算 KPI 并导出 ====
    log_console('仿真完成，正在计算 KPI...')
    kpis = citylearn_env.evaluate()
    # 长表转宽表：行 = 指标，列 = 楼栋 / District
    kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
    kpis = kpis.dropna(how='all')      # 全为空的行（该指标在本场景不适用）丢掉

    # 落盘 exported_kpis.csv（平台读它入库；幂等标志避免重复写）
    if not getattr(citylearn_env, '_final_kpis_exported', False):
        citylearn_env.export_final_kpis(filepath='exported_kpis.csv')

    if citylearn_env.new_folder_path:
        kpi_path = Path(citylearn_env.new_folder_path) / 'exported_kpis.csv'
        log_console(f'输出目录: {Path(citylearn_env.new_folder_path).resolve()}')
        log_console(f'KPI 文件: {kpi_path.resolve()}')
    else:
        log_console('未生成导出目录（请确认 render_mode 已启用）')

    # ==== 步骤 7b/8：把 KPI 按平台协议打到 stdout（Java 靠 'outputkpi' 标记截取）====
    print_kpis_for_java(kpis)
    # 强制刷缓冲：Java 是边读 stdout 边解析的，不能等到进程退出才一起吐（否则可能漏读）
    sys.stdout.flush()
