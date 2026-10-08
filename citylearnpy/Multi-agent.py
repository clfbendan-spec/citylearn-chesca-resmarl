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

    # [详注-BEGIN]（生成简版时整段删除）
    # 注释约定：代码注释只写"当前口径"；历史 / 实测 / 回退统一放 DECISIONS.md ✓（详注原文见 MAINTENANCE.md 附录 A ✓）
# [详注-END]

# 【依赖总览】全部 import 都在下面这一段（正文不再出现 import ✓）
# [详注-BEGIN]（生成简版时整段删除）
    # 【依赖总览】全部 import 都在这段（正文不再出现 import）；硬约束：线程 env 三行必须在 numpy/pandas/torch 之前 ✗
# [详注-END]
import argparse
import json
import os
import sys
import time
from pathlib import Path

# 算子不大，设置单线程启动，避免多线程抢锁
    # [详注-BEGIN]（生成简版时整段删除）
    # 单线程启动：必须写在 import numpy/pandas/torch **之前**（它们 import 时就定线程池 ⇒ 之后再设不生效 ✗）
    # [详注-END]
_THREADS = str(max(1, int(os.environ.get('TORCH_NUM_THREADS', '1') or '1')))
os.environ.setdefault('OMP_NUM_THREADS', _THREADS)
os.environ.setdefault('MKL_NUM_THREADS', _THREADS)
os.environ.setdefault('NUMEXPR_NUM_THREADS', _THREADS)

# 执行时会把本脚本复制到 output/outkpis/{taskId}/ 再执行
    # [详注-BEGIN]（生成简版时整段删除）
    # Java 会把脚本复制到 output/outkpis/<taskId>/ 再跑 ⇒ 必须先把项目目录注入 sys.path（这 1 行是物理下限 ✗）
    # [详注-END]
sys.path[:0] = [str(Path(p).resolve()) for p in (os.environ.get('CITYLEARNPY_DIR'), r'D:\citylearn-demo\citylearnpy') if p and Path(p).is_dir()][:1]

# 日志工具，设置torch单线程
# [详注-BEGIN]（生成简版时整段删除）
    # 本组来自 utils/base.py：日志出口 / CITYLEARNPY_DIR / Windows 资源补丁（只依赖标准库 ⇒ worker 也能安全 import ✓）
# [详注-END]
from utils.base import CITYLEARNPY_DIR, log_console, TORCH_THREADS

import pandas as pd
# 构建环境配置，动作解析
# [详注-BEGIN]（生成简版时整段删除）
    # 这些实现原先内联在本文件 ⇒ 已下沉 utils/env.py（schema / 解包 / 上下文环境与 COOL_* 开关 / build_env_config）✓
# [详注-END]
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

# [详注-BEGIN]（生成简版时整段删除）
    # 这里不再做"模块缺失就降级"的兜底：实测是死代码（前面已 import 更多 utils/第三方 ⇒ 走不到）⇒ 已删 ✓
# [详注-END]
from utils.report import decision_trace_path, print_kpis_for_java, MarlDecisionTraceRecorder, build_decision_recorder, record_step_trace

from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper, RLlibMultiAgentEnv
from gymnasium import spaces   # 扩展 observation_space 用
# [详注-BEGIN]（生成简版时整段删除）
    # 原先这行 `from ray.rllib.algorithms.sac import SAC`（续训用）已随 --resume 撤下而删 ✗（模型构建在 utils/train_phase ✓）
# [详注-END]

from utils.config import (
    DEFAULT_CHECKPOINT_DIR,
    DEFAULT_EVAL_SCHEMA,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TRAIN_SCHEMA,
)

    # [详注-BEGIN]（生成简版时整段删除）
    # 奖励配置的唯一真源在 utils/config.py：sidecar 的读/写也在那儿 ✓（训练侧写、评估侧读，且必须先于 build_env_config ✗）
    # [详注-END]
    # [详注-BEGIN]（生成简版时整段删除）
    # 训练侧常量已抽到 utils/config.py（原先内联于此 ⇒ eval 里躺着约 240 行从不被调用的常量 ✗）；别再在入口重复定义同名常量（会静默遮蔽 ✗）
    # [详注-END]
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

    # [详注-BEGIN]（生成简版时整段删除）
    # 回合长度一律由数据集说了算（传 None ⇒ CityLearn 用自带长度 ✓）；曾经那张 schema→步数 硬编表已删 ✗
    # [详注-END]


    # [详注-BEGIN]（生成简版时整段删除）
    # log_console 已抽到 utils/base.py（全项目唯一日志出口，含 print+flush）⇒ 本文件不再自定义 ✓
    # [详注-END]


    # [详注-BEGIN]（生成简版时整段删除）
# print_kpis_for_java 的实现已抽到 utils/report.py（三个入口共用一份）✓
    # [详注-END]


    # [详注-BEGIN]（生成简版时整段删除）
# unwrap_action 的实现已抽到 utils/env.py（三个入口 + 诊断脚本共用一份）✓
    # [详注-END]

# [详注-BEGIN]（生成简版时整段删除）
    # 自定义奖励 CustomComfortReward 的类体住在 citylearnpy/custom_comfort_reward.py（C′-1：脚本名带连字符不能当模块 import ⇒ 抽成真实模块后 worker 才能 import ✓）；本文件只留 3 行 import 引用 ✓
# [详注-END]
from custom_comfort_reward import CustomComfortReward
from custom_comfort_reward import _cap_txt              # 推演叙事用
    # [详注-BEGIN]（生成简版时整段删除）
    # 奖励自检实现已抽到 custom_comfort_reward（本文件只 import 实现 + 透传当前生效参数 ✓）；过期的 _clamp_temp_penalty 导入已删 ✗
    # [详注-END]
# 奖励自检的实现：`--check-reward` 用它把自定义奖励与数据集原版逐位比对 ✓
from custom_comfort_reward import check_reward_equivalence as _reward_equiv_check




# [详注-BEGIN]（生成简版时整段删除）
    # 动作注入补丁：CityLearn 的 reward.calculate 只给观测不给动作 ⇒ 包 RLlibMultiAgentEnv.step，在真正 step 前把动作喂给奖励（只读不改 ⇒ 动力学/KPI 不变 ✓；train 提供梯度、eval 出诊断账本 ✓）
# [详注-END]
# [详注-BEGIN]（生成简版时整段删除）
    # 本文件只 import（真正调用在 `__main__` 第一行 ✓）；只 import 不运行的脚本请自行调用 install_action_hook()；状态用 action_hook_status() **函数**读 ✗
# [详注-END]
from utils.train import install_action_hook, log_reward_banner

# [详注-BEGIN]（生成简版时整段删除）
    # 原先这里有一行模块级 `install_action_hook()`；2026-10-03 移到 `__main__` 第一行 ⇒ 只 import 不运行的脚本请自行调用 ✓
# [详注-END]


    # [详注-BEGIN]（生成简版时整段删除）
    # 薄垫片 def check_reward_equivalence(...) 已于 2026-10-02 移除 ⇒ 三入口+探针统一走 custom_comfort_reward 的实现、调用点显式传参 ✓
    # [详注-END]
# [详注-BEGIN]（生成简版时整段删除）
# 原先在此的 describe_reward_function / build_decision_recorder 已搬到本职模块（utils/config.py / utils/report.py ✓）⇒ 本文件 import 回来，诊断脚本 ma.* 照旧 ✓
# [详注-END]


# [详注-BEGIN]（生成简版时整段删除）
    # 逐步采集与 decision_trace_path 的实现已抽到 utils/report.py（本文件 import 回来 ⇒ 诊断脚本的 ma.* 照旧可用 ✓）
# [详注-END]


# [详注-BEGIN]（生成简版时整段删除）
    # 随"评估期早停"一起删掉的三个私有辅助（_attr_path / _series_prev / comfort_flags）成了死代码 ⇒ 要诊断请用导出的 KPI 或 decision_trace.json ✓
# [详注-END]


# [详注-BEGIN]（生成简版时整段删除）
    # find_metric 已搬到 utils/train.py；本文件 import 回来 ⇒ 诊断脚本 `ma.find_metric` 照旧可用 ✓
# [详注-END]


# [详注-BEGIN]（生成简版时整段删除）
    # sidecar 的读/写已搬到 utils/config.py（与奖励配置同家 ✓）⇒ 训练侧三处保存点与 eval 准备段都不用改，诊断脚本 ma.* 照旧 ✓
    # [详注-END]


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
    # [详注-BEGIN]（生成简版时整段删除）
    # `--trace-every` 已移除 ⇒ 落盘间隔固定为 DECISION_TRACE_EVERY=144 ✓；`--no-trace` 保留（"要不要采集"与"多久落一次"是两件事 ✓）
    # [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    # `--no-early-stop` / `--early-stop-pct` / `--early-stop-after` 已随"评估期早停"一并移除（2026-10-01 ✓）
    # [详注-END]
    return parser.parse_args()


# [详注-BEGIN]（生成简版时整段删除）
    # 三入口切分边界（生成器靠这些标记定位 ✗）：共享区（本段）→ 训练准备段（train_schema… ⇒ eval 换成"评估准备段"）→ 训练流程段（probe… ⇒ eval 换成"加载 checkpoint"）→ 评估段（与 eval 逐字一致 ✓）
# [详注-END]
if __name__ == '__main__':
    # 流程：① 装钩子 → ② 解析参数 → ③ 奖励自检(可选) → ④ 定目录/数据集/轮数 → ⑤ 覆盖权重(可选) → ⑥ 建环境 → ⑦ 跑训练 → ⑧ 取回产出 → ⑨ 收尾汇总 → ⑩ 存 checkpoint

    # 让环境每一步都把动作记下来（奖励统计与决策推演要用）
    # [详注-BEGIN]（生成简版时整段删除）
    # 装动作注入钩子：幂等；必须排在**任何环境构造之前** ✗✗（晚一步奖励读不到动作 ⇒ 动作项静默为 0）✓
    # [详注-END]
    install_action_hook()

    # 解析命令行参数
    # [详注-BEGIN]（生成简版时整段删除）
    # 解析命令行参数（--output-dir 由 Java 平台注入；两入口的参数表各由生成器裁成真正生效的子集 ✓）
    # [详注-END]
    args = parse_args()

    # 奖励公式自检开关（--check-reward）：不训练、不仿真，几秒后退出
    # [详注-BEGIN]（生成简版时整段删除）
    # ② --check-reward：奖励公式回归自检（与数据集原版逐位比对；最大绝对差 == 0 ⇒ 退出码 0 ✓，可当 CI 用）
    # [详注-END]
    if args.check_reward:
        # 只做奖励自检（不训练）：确认新奖励与数据集原版逐位一致
        _worst = _reward_equiv_check(CUSTOM_REWARD_KWARGS, verbose=True)
        sys.exit(0 if _worst == 0.0 else 1)

    # 确定输出目录（-o/--output-dir 优先，否则用默认值）
    # [详注-BEGIN]（生成简版时整段删除）
    # ③ 输出目录：-o 优先、否则 DEFAULT_OUTPUT_DIR；必须先建出来（它同时是 render_directory ⇒ 不建会在渲染阶段才报错 ✗）
    # [详注-END]
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # 确定数据集
    # [详注-BEGIN]（生成简版时整段删除）
    # ④ 数据集：命令行（Java 注入）> 文件顶部默认值；or '' + .strip() 各挡一个坑（None 报错 / 看不见的空格 ✗）✓
    # [详注-END]
    train_schema = (args.train_schema or '').strip() or DEFAULT_TRAIN_SCHEMA
    eval_schema = (args.eval_schema or '').strip() or DEFAULT_EVAL_SCHEMA
    # 定义步数变量
    # [详注-BEGIN]（生成简版时整段删除）
    # ⑤ 步数一律不传（None = 让 CityLearn 用数据集自带长度 ✓；别改成 0 ✗：0 步 = 空回合）
    # [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    # ⑥ 覆盖奖励权重：给了就改 CUSTOM_REWARD_KWARGS；必须排在 build_env_config **之前** ✗（否则静默无效）
    # [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    # ② 建评估环境——注意这里建的只是**配置**（env_kwargs，一个 dict ✓），
    #      真正 new 出环境在下面「评估段」✗ 别混。
    #      5 个参数逐个说清：
    #        · eval_schema ：用哪个数据集（上一步定好的 ✓）
    #        · eval_steps  ：回合长度；None = 用数据集自带长度 ✓（见上一步详注 ✓）
    #        · output_dir  ：既当导出目录，也当 CityLearn 的 render_directory ⇒
    #                        回合结束时的 exported_kpis.csv / exported_data_*.csv /
    #                        decision_trace.json 都写到这里 ✓（目录已在上一步建好 ✓）
    #        · enable_render=True  ：回合结束导出 exported_data_*.csv（界面「数据视图」✓）
    #        · record_details=True ：奖励侧保留每步分项明细 ⇒ 推演日志里才有 narrative_lines
    #          （**训练侧故意关掉**：每步 3 栋 × 5 条 f-string 纯属开销 ✓）
    #      ⚠️ 顺序约束（与上一步呼应）：奖励配置必须在这个调用**之前**定好 ✗ ——
    #        CUSTOM_REWARD_KWARGS 是在这里被拷进 env_kwargs['reward_function_kwargs'] 的 ✓
    # [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    # 下面这行 `probe = …` 是**生成器的切分点**（只此一处）：它之前的准备段被 eval 整段替换、之后的训练段已下沉 ✓
    # [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    # 注：本段注释（简略行 + 详注）在两个入口里**保持逐字一致** ✓ —— 改注释请
    #     **两处一起改** ✗（源文件 Multi-agent.py + 生成器 EVAL_SETUP_BLOCK ✓）；
    #     门禁 ⑥ 只比代码、不比注释 ⇒ 它不会替你抓出"注释漂移" ✗（只有这条人工约定在管 ✓）
    # [详注-END]
    # [详注-BEGIN]（生成简版时整段删除）
    # 剥出 CityLearn 原生 Environment（读 KPI / 导出都靠它）
    #   · 三个对象不是一回事 ✗（最容易混的地方）：
    #       env           = _AGENT_ENV_CLS 实例（ContextRLlibEnv / RLlibMultiAgentEnv）——
    #                        RLlib 的多智能体环境；**仿真步进用它** ✓（见步骤 6/8）
    #       env.env        —— 内层包装链的**最外层**（RLlibMultiAgentRewardWrapper ✓）
    #       citylearn_env  —— 剥到最里层的**裸 CityLearnEnv** ✓（本行要的就是它）
    #   · 为什么必须 `.env.unwrapped` **两级** ✗（少一级都拿不到裸环境）：
    #       ① 只写 `env.unwrapped` ✗ 没用：RLlib 的 MultiAgentEnv 继承的是
    #          `gymnasium.Env`（**不是** `Wrapper` ✗）⇒ `Env.unwrapped` 的定义就是
    #          `return self` ⇒ 只会拿回它自己（实测 issubclass(MultiAgentEnv, Wrapper)=False ✓）
    #       ② 只写 `env.env` ✗ 不够：那只是最外层 wrapper ⇒ `evaluate()` /
    #          `export_final_kpis()` 这些方法**只有裸环境上**才有 ✗
    #       ③ `.unwrapped` 是 `Wrapper` 的属性（定义 = `return self.env.unwrapped` ✓）
    #          ⇒ 从 `env.env` 出发会**逐层剥掉全部包装** ✓（实测那 5 层都是 Wrapper ✓）
    #   · 实际封了 **5 层**（RLlibMultiAgentEnv.__init__ 里套的 ✓；wrappers 列表来自
    #     utils/env.py 的 build_env_config ✓），由外到内：
    #       RLlibMultiAgentRewardWrapper          ← `env.env` 指到这里
    #        └ RLlibMultiAgentObservationWrapper
    #          └ RLlibMultiAgentActionWrapper
    #            └ ClippedObservationWrapper      （配置里的 wrappers[1]）
    #              └ NormalizedObservationWrapper （配置里的 wrappers[0]）
    #                └ CityLearnEnv               ← `citylearn_env` 就是它 ✓
    #   · ⚠️ 分工红线（搞错会**静默**改变结果 ✗✗）：
    #       **仿真/步进一律用 `env`** ✓ —— 观测归一化、动作映射、按 agent 拆分全在包装层里，
    #         用裸环境步进等于绕过它们 ⇒ 与训练时口径不一致 ✗
    #       **`citylearn_env` 只用来读/导出** ✓：`evaluate()`（官方 KPI 口径 ✓）、
    #         `export_final_kpis()`（写 exported_kpis.csv ✓）、`new_folder_path`
    #         （CityLearn 本回合的导出目录，实例属性 ✓）、决策推演读时序数据 ✓
    #   · 想更稳的写法 ✓：utils/env.py 的 `unwrap_citylearn_env()` ——
    #       逐层找"带 buildings + reward_function"的对象 ✓，找不到返回 None ✗。
    #       本行是"链条固定 5 层"的直连写法 ✓（更快；但包装顺序/层数一变就会
    #       静默取错对象 ✗ ⇒ 那时换用它更保险 ✓）
    # [详注-END]
    citylearn_env = env.env.unwrapped
    # reset：清空各楼时序、仿真指针拨回 t=0（返回 observations / infos，本脚本只用前者 ✓）
    observations, _ = env.reset()
    # ==== 步骤 5/8：确定这个回合有多长（本 schema = 2208 步）====
    # [详注-BEGIN]（生成简版时整段删除）
    # ---- 回合长度：**完全由数据集决定**（我们不传 episode_time_steps）-------------
    # 读不到（<=0）说明 schema/数据异常 ⇒ 立刻失败，别让 0 流到进度分母里 ✗
    # [详注-END]
    total_steps = int(getattr(citylearn_env, 'episode_time_steps', 0) or 0)
    if total_steps <= 0:
        raise SystemExit(
            f'[致命] 读不到回合长度（episode_time_steps={total_steps}）'
            '—— 检查 schema / 数据集文件是否完整'
        )
    log_console(f'开始仿真，共 {total_steps} 步（数据集自带长度）...')

    # ---- 决策推演日志（decision_trace.json；落盘间隔固定 = DECISION_TRACE_EVERY = 144）----
    # [详注-BEGIN]（生成简版时整段删除）
    # 做什么：每步把关键参数（室温 / 设定点 / 温差 / 动作 / 制冷用电 / 电价 / SOC / 回报
    #   / 奖励分项）追加到**内存**；每 trace_every 步（默认 144）统一落盘一次，
    #   回合结束（跑满 total_steps）时再收尾一次 ⇒ 文件任何时候都是完整可解析 JSON。
    # 为什么批量：逐步写 JSON 的 IO 开销远大于仿真本身（实测推演落盘可占评估耗时的可观比例），
    #   批量落盘后这部分几乎为零。
    # 关掉它（--no-trace）只影响日志，KPI 与仿真结果**完全不变**（所以可以放心用它快速迭代）。
    # [详注-END]
    # [详注-BEGIN]（生成简版时整段删除）
    # 决策推演日志的落盘间隔（步）：固定用 DECISION_TRACE_EVERY（= 144）
    # 先弄清 trace 是什么 ✗（本行只管它的"写入频率"，不是它的内容 ✗）：
    #   · trace = **决策推演日志**：把仿真每一步的关键量按楼栋记下来，供「模型优选界面」
    #     与论文回放"策略当时看到什么、为什么这么动作" ✓
    #     （写盘位置 = 输出目录的 decision_trace.json ✓）
    #   · 每步每栋约 30 项 ✓：室温 / 冷热设定点 / 舒适带 / 温差与高低温判定 / 动作分量 /
    #     制冷用电 / 冷热负荷 / 净用电 / 光伏 / 电价 / SOC 与电池充放 / 是否有人 / 停电 /
    #     奖励及其分项 ✓（采集实现在 utils/report.py ✓；
    #     字段清单见 utils/eval_step_trace.building_step_snapshot ✓）
    #   · 三步走 ✓：① 每步只追加到**内存**（不写盘 ✓）② 每 `trace_every` 步（或回合结束 ✓）
    #     把**完整** JSON 覆盖写一次 ⇒ 文件任何时候都可解析、界面能边跑边看 ✓
    #     ③ 收尾再写一次 ✓ —— 本行决定的就是 ② 的频率 ✓
    #   · 为什么是 144 ✓：1 步 = 1 小时（逐小时数据 ✓）⇒ 144 步 = 6 天；整回合 2208 步
    #     ≈ 92 天 ⇒ 全程约 15 次落盘 ✓（进度日志是每 36 步一次 ⇒ 144 恰好 = 4×36 ✓ ——
    #     这是我按现有数字读出来的 ✓，**不是**文档里记载的设定理由 ✗）
    #   · 名字只有**两层** ✓（2026-10-05 起 ✗）：常量 `DECISION_TRACE_EVERY`（= 144，
    #     utils/config.py ✓）→ 运行时变量 `trace_every`（= 本行，**直接取常量** ✓）。
    #     概念、字段与"顺序契约"的权威说明在 utils/report.py 头部 ✓
    # ⚠️ 2026-10-05 **移除 `--trace-every` 参数** ✗（判决见 DECISIONS §17）：
    #   · 理由：它几乎从不被调（144 是经验值 ✓，扫参也不会动它 ✗），却要付两份代价 ✗：
    #     ① 出现在参数表 ⇒ 让人以为"这是个该调的旋钮" ✗；
    #     ② 为它写一整套兜底（getattr / or / int / max(1,…)）✗ —— 那套兜底的初衷是
    #        挡"train 入口没有这个参数" ✗（写得没错，但纯属负债 ✗）。
    #   · 现在：三个入口一律用常量 144 ✓，参数表里**没有**它 ✓（`--help` 更干净 ✓），
    #     本行退化成一行**直取常量** ✓（没有 getattr、没有 or、没有 int、没有 max ✓）。
    #   · 想改频率 ⇒ 改 utils/config.py 的 `DECISION_TRACE_EVERY` ✓（一处生效 ✓）；
    #     想彻底不采集 ⇒ 用 `--no-trace` ✓（该参数**保留** ✓，它只影响日志 —— 见下面 trace_on ✓）。
    #   · 历史（移除前那套兜底挡过的坑 ✗）：`0` 会让主循环 `step_count % trace_every`
    #     直接 **ZeroDivisionError 崩** ✗✗（实测 ✓）；负数不崩但"每 -5 步落盘一次"
    #     毫无意义 ✗；字符串（'7'）要靠 int() 收 ⇒ 参数没了，这三类坑**结构性消失** ✓
    #   · 同族兜底句式（本项目惯用 ✓，别处还在用）：getattr(…, 默认) → or 默认 →
    #     strip/int → 边界裁剪；例：eval_schema = (args.eval_schema or '').strip() or DEFAULT_EVAL_SCHEMA ✓
    # [详注-END]
    trace_every = DECISION_TRACE_EVERY
    # trace_on：本次是否采集推演日志（--no-trace 时 = False；关掉只跳过日志，仿真与 KPI 不变 ✓）
    trace_on = not getattr(args, 'no_trace', False)
    # 建记录器（不采集时**什么都不建** ⇒ None ✓）—— **ON / OFF 那行日志由工厂自己打** ✓
    # [详注-BEGIN]（生成简版时整段删除）
    #   · 这是什么 ✗：`build_decision_recorder` 是**工厂**（utils/report.py ✓），
    #     "按环境实际楼栋数 / 奖励函数构建决策推演记录器" ✓；2026-10-06 起它**顺手把
    #     ON / OFF 状态日志也打掉** ✓（原先那段日志写在本处 ⇒ 调用点从 6 行缩成一次调用 ✓）
    #   · 为什么传 `citylearn_env`（**裸环境** ✓）而不是 `env`（带包装 ✗）：
    #     工厂要读楼栋数（`len(citylearn_env.buildings)` ✓，决定每次记几行 ✓）和
    #     奖励函数描述（`describe_reward_function(citylearn_env)` ✓ → 得到 `reward_label` ✓，
    #     就是 ON 日志里那个"奖励函数=…" ✓）；后面写盘路径
    #     `decision_trace_path(citylearn_env, output_dir)` 同样是裸环境 ✓
    #   · `enabled=trace_on` 的含义 ✗：**不采集就什么都不建** ✓（返回 None ✓，
    #     省掉记录器对象与它的内存缓存 ⇒ 关日志时几乎零开销 ✓）
    #     代价是**后面每一处用它都必须先判 trace_on** ✗ —— 实测这几处都守住了 ✓：
    #       ① 主循环里的 `record_step_trace(decision_recorder, …)`（在 `if trace_on:` 里 ✓）
    #       ② 主循环里的 `decision_recorder.save(…)`（在 `if trace_on and (…):` 里 ✓）
    #       ③ 收尾里的 `len(decision_recorder.steps)`（在 `if trace_path is not None:` 里 ✓ ——
    #          而 trace_path 只在 ② 成功时被赋值 ✓ ⇒ trace_on=False 时必为 None ⇒ 走 else ✓）
    #     （原先 ON 日志里也读过 `decision_recorder.reward_label` ✗ ⇒ 那次读取现在移进**工厂
    #      内部** ✓，天然只有 enabled=True 才走到 ⇒ 手工判断少了一处 ✓）
    #   · `trace_off_reason` 为什么要在这一行算 ✗：工厂要打的那句 OFF 必须说清**到底是哪个
    #     原因**（`--no-trace` ✓ 还是"依赖模块不可用" ✗）—— 这两个原因**只有调用方知道** ✓；
    #     `trace_on=True` 时它用不上 ✓（工厂走 ON 分支 ✓）
    #   · 与相邻两行的关系 ✓：`trace_on` = 本次到底要不要采集（判一次、全程复用 ✓）；
    #     `trace_path = None` = 收尾按"有没有成功落盘"分别打印"已落盘 / 未落盘" ✓
    #     （所以它初值必须是 None ✗，不能省 ✓）
    # [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    # 三者之和≈总耗时的意义：出结果的瓶颈到底在仿真本身，还是在日志上（优化时看这个）
    # [详注-END]

    # 不做早停：一直跑到回合结束（KPI 才是全程口径）
    # [详注-BEGIN]（生成简版时整段删除）
    # 说明：本循环**没有早停**（2026-10-01 移除，原因见文件顶部该常量块）⇒
    #   只在 env.terminated（跑满 total_steps）时结束，KPI 恒为全程口径、可比 ✓
    # [详注-END]

    # ---- 主循环：直到回合自然结束（env.terminated）------------------------------
    # [详注-BEGIN]（生成简版时整段删除）
    # ==== 步骤 6/8：主循环 —— 每步都重复「取动作 → 环境步进 → 记推演日志」====
    # 每步固定三件事：① 按固定顺序取各 agent 动作 → ② 环境步进 → ③ 采推演日志
    #                （③ 按 trace_every 批量落盘，并按 36 步打一次进度）
    # [详注-END]
    while not env.terminated:
        # 固定各楼栋顺序（奖励注入与推演都按「第几个 = 第几栋」对应）
        # [详注-BEGIN]（生成简版时整段删除）
        # ①-1 固定 agent_0..n 的顺序。这一步不能省：observations 是 dict，顺序不保证，
        #   而下游（奖励注入、决策推演）都靠"下标 = 楼栋号"一一对应。
        #   优先用 env._agent_ids（ContextRLlibEnv 建的、与楼栋下标的真实映射），
        #   取不到才退回 observations.keys()。
        #   · 它里面到底是什么值 ✓：`['agent_0', 'agent_1', 'agent_2']` ——
        #     来自 CityLearn 的 RLlibMultiAgentEnv.__init__：
        #       `self._agent_ids = [f'agent_{i}' for i in range(len(self.buildings))]` ✓
        #     ⇒ **下标就是楼栋号**（本数据集 3 栋 ⇒ agent_0 / agent_1 / agent_2 ✓），
        #     且顺序恒等于楼栋顺序 ✓
        #   · 它就是"顺序契约"的来源 ✓：下游 `record_step_trace(..., ordered_keys=…)`
        #     会拿它把 RLlib 的 `{agent_id: …}` 字典**按这个顺序**摊成列表 ✓
        #     （utils/report.py 里就是 `[actions.get(k) for k in ordered_keys]` ✓）
        #     ⇒ 顺序错了会把某栋的动作/奖励记到别栋上 ✗（历史事故见 DECISIONS §9.6.2 / §11.5）
        # [详注-END]
        ordered_keys = list(getattr(env, '_agent_ids', None) or list(observations.keys()))
        # 给每栋楼取一次动作（不加随机探索 ⇒ 结果可复现）
        # [详注-BEGIN]（生成简版时整段删除）
        # ①-2 逐 agent 推动作：每个 agent 有自己的 policy（policy_id=p），
        #   explore=False ⇒ **贪心/确定性**动作（评估必须可复现；训练时才是随机采样）。
        #   unwrap_action：某些 RLlib 版本 compute_single_action 返回 (action, state, info)
        #   三元组，这里统一只取动作本体，否则喂给 env.step 会类型报错。
        #   · 下面这个 `{…}` 是**字典推导式** ✗（不是普通 for 循环 ⇒ 语序和直觉相反 ✗）：
        #       结果 = { 键 : 值  for 变量 in 可迭代  if 条件 }
        #     换成多行写法完全等价 ✓：
        #       actions = {}
        #       for p in ordered_keys:            # 按楼栋顺序遍历 agent_id
        #           if p in observations:         # ← 守卫，见下一条
        #               actions[p] = unwrap_action(
        #                   model.compute_single_action(observations[p], policy_id=p, explore=False)
        #               )
        #   · 注意书写顺序 ✗：`if` 写在**最后**，但它是在**赋值之前**判的 ✓
        #     （等价于"先筛后算"✓ —— 这就是一眼看过去别扭的原因 ✗）
        #   · `if p in observations` 干什么 ✗：`observations` 是
        #     `{agent_id: 该 agent 的观测}` ✓；万一某个 agent 这一步**不在**里面
        #     （例如它已经结束 ✗），`observations[p]` 会 KeyError ⇒ 这句先把它跳过 ✓。
        #     正常运行下三个 agent 都在 ✓ ⇒ 它只是防御 ✓
        #   · 得到的 `actions` 同样是 `{agent_id: 动作}` ✓，直接喂 `env.step(actions)` ✓；
        #     它**不需要**保序 ✗ —— 但推演日志要保序 ⇒ 所以 `ordered_keys` 是**另外单独**
        #     传给记录器的 ✓（见下面 record_step_trace 调用 ✓）
        # [详注-END]
        actions = {
            p: unwrap_action(model.compute_single_action(observations[p], policy_id=p, explore=False))
            for p in ordered_keys
            if p in observations
        }
        # 环境走一步：拿到新观测与奖励（以及是否结束）
        # [详注-BEGIN]（生成简版时整段删除）
        # ② 环境步进：内部顺序是「先算奖励（用本步动作，靠 install_action_hook 注入）
        #   → 再推进 CityLearn 动力学 → 返回下一步观测」。返回 5 元组，
        #   terminated/truncated/infos 这里用不到（循环条件看 env.terminated）。
        #   只有这里计入 t_env_step，用来和推演日志开销分开统计。
        # [详注-END]
        _t_step_start = time.perf_counter()
        observations, rewards, _, _, _ = env.step(actions)
        t_env_step += time.perf_counter() - _t_step_start
        step_count += 1

        # 采集本步（**只进内存**，不写盘）
        # [详注-BEGIN]（生成简版时整段删除）
        #   · `if trace_on:` 一箭双雕 ✓：关掉推演时**连采集都不做** ✓，同时避免对
        #     `decision_recorder = None` 调方法 ✗（关日志时它是 None ✓，见上面那行 ✓）
        #   · `record_step_trace(...)` 做什么 ✓（utils/report.py ✓）：
        #     ① 按 `ordered_keys` 把 RLlib 的 `{agent_id: …}` 摊成"**第 1 项 = 第 1 栋**"的列表 ✓
        #        （`[actions.get(k) for k in ordered_keys]` ✓）—— 这正是"结果已经是 dict
        #        却还要另外传 ordered_keys"的原因 ✗：dict 的顺序语义不可依赖 ✓
        #     ② 动作写**两列**（P0-B 协议 ✓）：
        #          `action_<名字>`     = 建筑**实际执行**值（取自奖励侧 `rf._pending_acts` ✓，
        #                               由 install_action_hook 在 env.step 内注入 ✓）
        #          `action_<名字>_raw` = 策略网络的**原始输出**（= 上面传进来的 `actions` ✓）
        #        ⇒ 两者不一致时（例如冷却动作被重标定 ✓）界面能直接看出差异 ✓；
        #        取不到"实际执行值"时退回只写原始列、**且不写 `_raw`** ✓（界面就不附 `(raw=…)` ✓）
        #     ③ 每栋一行（约 30 项 ✓）+ 奖励分项（`rf._last_details` ✓）；
        #        `recorder.record_step(...)` 内部只做 `self.steps.append(...)` ✓ ⇒ **全程内存** ✓
        #   · `try/except` 的理由 ✓：**日志是"旁观者"，绝不许影响仿真与 KPI** ✗✗ ——
        #     记一行失败只打印一行提示、继续跑 ✓（KPI 由仿真数据独立算，与它无关 ✓）
        #   · 计时 ✓：这一段耗时累进 `t_trace` ✓，收尾时能看出"推演采集占了多少" ✓
        #     （落盘耗时**单独**累进 `t_flush` ✓ —— 分开统计，优化时才知道该动哪一头 ✓）
        # [详注-END]
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
        # [详注-BEGIN]（生成简版时整段删除）
        #   · 条件 `step_count % trace_every == 0 or env.terminated` ✓：
        #       定期（默认每 144 步 ✓）**加上"末步必落"** ✓ ⇒ 文件**任何时候都是完整可解析
        #       JSON** ✓，界面能边跑边看 ✓
        #       （`save` 写的是 `to_payload()` 里的**全部** steps ✓，不是增量 ✗ —— 所以
        #        每次落盘都是"整份覆盖"，这也是"文件始终完整"的来源 ✓）
        #   · `decision_trace_path(citylearn_env, output_dir)` ✓（utils/report.py ✓）：
        #       优先用 CityLearn 的**渲染/导出目录** `citylearn_env.new_folder_path` ✓，
        #       拿不到才退回 `--output-dir` ✓ ⇒ 最终路径 = `<该目录>/decision_trace.json` ✓
        #       （所以这里也需要**裸环境** ✓；`save` 内部还会 `mkdir(parents=True,
        #        exist_ok=True)` ✓ ⇒ 目录不存在也不会报错 ✓）
        #   · `save` 做什么 ✓：`json.dumps(..., ensure_ascii=False, separators=(',',':'))`
        #       ⇒ **紧凑 JSON 且中文不转义** ✓（体积小、又能直接人眼读 ✓），并返回路径 ⇒
        #       赋给 `trace_path` ✓
        #   · `trace_path` 的用途 ✓：收尾时按它是否为 None 分别打印"已落盘 / 未落盘" ✓
        #     （所以它上面初值必须是 None ✓，不能省 ✗）
        #   · `try/except` ✓ 与采集同理：落盘失败（磁盘满 / 权限 ✗）**也绝不影响仿真与 KPI** ✓，
        #     只打印一行提示 ✓；耗时累进 `t_flush` ✓（与采集的 `t_trace` 分开 ✓）
        # [详注-END]
        if trace_on and (step_count % trace_every == 0 or env.terminated):
            _t_flush_start = time.perf_counter()
            try:
                trace_path = decision_recorder.save(decision_trace_path(citylearn_env, output_dir))
            except Exception as exc:  # 落盘失败不影响仿真与 KPI（忽略并继续）
                log_console(f'[决策推演] 落盘失败（忽略）: {exc}')
            t_flush += time.perf_counter() - _t_flush_start

        # 打印进度日志（第 1 步 / 每 36 步 / 回合结束时各一次）
        # [详注-BEGIN]（生成简版时整段删除）
        # 进度日志：第 1 步、每 36 步、回合结束时各打一次
        #   （36 步 ≈ 每 1.5 天，够密能看出卡住，又不会刷屏）
        #   注：原先这里还会附带"各栋累计不适比例"（早停的副产品），已随早停留一并移除；
        #   要看不适比例，看结束时的 [评估阶段] kpi_summary 与导出的 exported_kpis.csv ✓
        # [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    # 评估耗时拆解：定位瓶颈在「环境步进」还是「日志采集/落盘」
    # （经验值：环境步进 ≈ 大头；若推演落盘占比高 ⇒ 加 --no-trace，或调小
    #   utils/config.py 的 DECISION_TRACE_EVERY（2026-10-05 起它已不是命令行参数 ✗））
    # [详注-END]
    log_console(
        f'评估用时 {_eval_secs:.1f}s（{step_count} 步，{step_count / max(_eval_secs, 1e-9):.1f} step/s）= '
        f'环境步进 {t_env_step:.1f}s({t_env_step / max(_eval_secs, 1e-9):.0%}) '
        f'+ 推演采集 {t_trace:.1f}s({t_trace / max(_eval_secs, 1e-9):.0%}) '
        f'+ 推演落盘 {t_flush:.1f}s({t_flush / max(_eval_secs, 1e-9):.0%})'
    )

    # 打印本阶段奖励统计（与训练期对照，排查「训练好但评估差」）
    # [详注-BEGIN]（生成简版时整段删除）
    # 评估阶段统计：与「训练阶段」的同类统计对照，看动作类惩罚项在评估中的
    #   触发率/罚分是否明显不同（不同 ⇒ 说明评估时的状态分布或行为与训练期不一致，
    #   是排查"训练好但评估差"的第一手线索）。
    # [详注-END]
    rf_eval = getattr(citylearn_env, 'reward_function', None)
    if rf_eval is not None and hasattr(rf_eval, 'stats_summary'):
        log_console('[评估阶段] ' + rf_eval.stats_summary())
    if rf_eval is not None and hasattr(rf_eval, 'kpi_summary'):
        # 另打印「奖励侧自算的 KPI」，与紧随其后的官方 KPI 对照
        # [详注-BEGIN]（生成简版时整段删除）
        # 正式评估也打一份「奖励侧自算的 KPI 口径」，可与紧随其后导出的
        #   discomfort_hot/cold_proportion 直接对照 —— 这是判据口径可信度的最终验收。
        #   参照值：623a9e8d → B1 11.6%/1.2%、B2 0.6%/19.3%、B3 0.5%/0.2%
        #           b30240d4 → B1 19.7%/4.3%、B2 0.6%/20.9%、B3 0.4%/5.4%
        # [详注-END]
        log_console('[评估阶段] ' + rf_eval.kpi_summary())

    # ==== 步骤 7/8：收尾 —— 用 CityLearn 官方 evaluate 算 KPI 并导出 ====
    # [详注-BEGIN]（生成简版时整段删除）
    # evaluate()：CityLearn 官方 KPI 计算。它读的是各楼**当前已积累**的时序数组 ——
    #   现在没有早停了，执行到这里时各楼数组必然是完整的 2208 步 ⇒ KPI 恒为全程口径 ✓
    #   （原先"被早停在第 N 步"时这里是前 N 步的滚动 KPI，其中 cost/carbon/electricity
    #    等归一化项的分母仍是"全年基线"、与全程值不可比 ✗ —— 这个坑随早停一起消除）
    #   也正因为不再有"半途结束"，下面**不需要**任何"部分评估补落盘"的特殊处理 ✓
    # [详注-END]
    log_console('仿真完成，正在计算 KPI...')
    kpis = citylearn_env.evaluate()
    # 长表转宽表：行 = 指标，列 = 楼栋 / District
    # [详注-BEGIN]（生成简版时整段删除）
    # 长表 → 宽表：行=cost_function（cost_total / discomfort_hot_proportion …），
    #   列=name（Building_1 / Building_2 / Building_3 / District），再四舍五入到 3 位。
    # [详注-END]
    kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
    kpis = kpis.dropna(how='all')      # 全为空的行（该指标在本场景不适用）丢掉

    # 落盘 exported_kpis.csv（平台读它入库；幂等标志避免重复写）
    # [详注-BEGIN]（生成简版时整段删除）
    # 落盘 exported_kpis.csv（Java 平台读它入库；_final_kpis_exported 是幂等标志，
    #   CityLearn 在回合自然结束时可能已经写过一次，这里避免重复写）。
    # [详注-END]
    if not getattr(citylearn_env, '_final_kpis_exported', False):
        citylearn_env.export_final_kpis(filepath='exported_kpis.csv')

    if citylearn_env.new_folder_path:
        kpi_path = Path(citylearn_env.new_folder_path) / 'exported_kpis.csv'
        log_console(f'输出目录: {Path(citylearn_env.new_folder_path).resolve()}')
        log_console(f'KPI 文件: {kpi_path.resolve()}')
    else:
        log_console('未生成导出目录（请确认 render_mode 已启用）')

    # ==== 步骤 7b/8：把 KPI 按平台协议打到 stdout（Java 靠 'outputkpi' 标记截取）====
    # [详注-BEGIN]（生成简版时整段删除）
    # 格式：首行固定是字面量 'outputkpi'，其后每行 = 指标名 + 各列值（空格分隔，
    #   NaN 打成字符串 NaN）。Java 侧（BaseDataService.parseAndSaveKpis）就是靠
    #   'outputkpi' 这个标记从控制台输出里截出 KPI 片段入库的 ⇒ **这一行不能改** ✗
    # [详注-END]
    print_kpis_for_java(kpis)
    # 强制刷缓冲：Java 是边读 stdout 边解析的，不能等到进程退出才一起吐（否则可能漏读）
    sys.stdout.flush()
