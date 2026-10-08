# 【训练专用入口 train · 详注版】由 _gen_marl_split.py 生成（勿手改 ✗）——只训练、结尾打印 CHECKPOINT=<绝对路径>；KPI 见 Multi-agent-eval.py ✓
"""
SAC 多智能体训练脚本（train 专用入口）
====================================

纯 Multi-Agent SAC 端到端控制（非 CHESCA-ResMARL），**只训练**。
奖励默认使用**外部模块** custom_comfort_reward.py 里的 CustomComfortReward
（本文件只在顶部 import 它，类体不在本文件内；逻辑与数据集默认 ComfortReward
完全一致，便于在该模块上继续修改；把 USE_CUSTOM_REWARD 置 False 可回退到
schema 默认奖励）。奖励类 / schema patch / 中期评估探针 / 早停判据等工具层与
Multi-agent.py 逐字一致。

训练结束会保存 RLlib checkpoint（供 Multi-agent-eval.py 加载），并打印一行
`CHECKPOINT=<绝对路径>`；本脚本不跑评估仿真、不出 KPI。

可配置参数（只列训练相关；评估参数已裁剪）：
  --train-schema      训练数据集
  --eval-schema       训练中「中期评估探针」用的数据集（不是正式评估）
  --train-epochs      训练轮数（硬上限；Java 平台注入走这个）
  --min-train-epochs  最小训练轮数（在此之前不停训；早停护栏 ✓）
  --checkpoint-dir    checkpoint 落盘目录（默认 citylearnpy/checkpoints/multi_agent_resume）
  --seed              随机种子，默认 3（可复现；论文方差跑 3 次：--seed 0/1/2）
  --check-reward      仅自检新奖励与原版是否逐位一致后退出
（另保留 --output-dir 供中期评估探针与 Java 平台使用）

训练规模：**以文件顶部常量为准**——
  训练结束会打印一行「奖励统计」，其中「读到act」为 0 说明动作注入未生效。

用法：
  python Multi-agent-train.py -o D:/citylearn-demo/output/outkpis/任务ID
      --train-schema citylearn_challenge_2023_phase_2_local_evaluation
      --eval-schema citylearn_challenge_2023_phase_2_online_evaluation_1
      --checkpoint-dir D:/citylearn-demo/citylearnpy/checkpoints/multi_agent_resume
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

# 中期评估,checkpoint,动作注入钩子
from utils.train import (
    find_metric,
    read_building_series,
    run_mid_eval,
    run_mini_eval,
    run_nocontrol_cost_ref,
    load_multi_agent_checkpoint,
    save_multi_agent_checkpoint,
    install_action_hook,
    log_reward_banner,
)

# 自定义奖励函数相关配置，用于记录决策推演日志
from utils.config import (
    CUSTOM_REWARD_KWARGS,
    USE_CUSTOM_REWARD,
    _CUSTOM_REWARD_MODULE,
    describe_reward_function,
    DECISION_TRACE_EVERY,
    DEFAULT_CHECKPOINT_DIR,
    DEFAULT_EVAL_SCHEMA,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TRAIN_SCHEMA,
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
    # 这里不再做"模块缺失就降级"的兜底：实测是死代码（前面已 import 更多 utils/第三方 ⇒ 走不到）⇒ 已删 ✓
# [详注-END]
from utils.report import decision_trace_path, print_kpis_for_java, MarlDecisionTraceRecorder, build_decision_recorder, record_step_trace

from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper, RLlibMultiAgentEnv
from gymnasium import spaces   # 扩展 observation_space 用
# [详注-BEGIN]（生成简版时整段删除）
    # 原先这行 `from ray.rllib.algorithms.sac import SAC`（续训用）已随 --resume 撤下而删 ✗（模型构建在 utils/train_phase ✓）
# [详注-END]


    # [详注-BEGIN]（生成简版时整段删除）
    # 这两行 checkpoint 存取工具来自 utils/train.py（顶层依赖很轻 ⇒ 提前到顶部不新增风险 ✓；一体化入口用不到，由生成器注入 ✓）
    # [详注-END]

    # [详注-BEGIN]（生成简版时整段删除）
    # 奖励配置的唯一真源在 utils/config.py：sidecar 的读/写也在那儿 ✓（训练侧写、评估侧读，且必须先于 build_env_config ✗）
    # [详注-END]
    # [详注-BEGIN]（生成简版时整段删除）
    # 训练侧常量已抽到 utils/config.py（原先内联于此 ⇒ eval 里躺着约 240 行从不被调用的常量 ✗）；别再在入口重复定义同名常量（会静默遮蔽 ✗）
    # [详注-END]

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
# 奖励函数自检
from custom_comfort_reward import check_reward_equivalence as _reward_equiv_check




# [详注-BEGIN]（生成简版时整段删除）
    # 动作注入补丁：CityLearn 的 reward.calculate 只给观测不给动作 ⇒ 包 RLlibMultiAgentEnv.step，在真正 step 前把动作喂给奖励（只读不改 ⇒ 动力学/KPI 不变 ✓；train 提供梯度、eval 出诊断账本 ✓）
# [详注-END]
# [详注-BEGIN]（生成简版时整段删除）
    # 本文件只 import（真正调用在 `__main__` 第一行 ✓）；只 import 不运行的脚本请自行调用 install_action_hook()；状态用 action_hook_status() **函数**读 ✗
# [详注-END]

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
    parser = argparse.ArgumentParser(description='SAC Multi-Agent 训练（只训练并保存 checkpoint；KPI 由 Multi-agent-eval.py 产出）')
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
    # [详注-BEGIN]（生成简版时整段删除）
    # `--no-early-stop` / `--early-stop-pct` / `--early-stop-after` 已随"评估期早停"一并移除（2026-10-01 ✓）
    # [详注-END]
    return parser.parse_args()


# [详注-BEGIN]（生成简版时整段删除）
    # 三入口切分边界（生成器靠这些标记定位 ✗）：共享区（本段）→ 训练准备段（train_schema… ⇒ eval 换成"评估准备段"）→ 训练流程段（probe… ⇒ eval 换成"加载 checkpoint"）→ 评估段（与 eval 逐字一致 ✓）
# [详注-END]
if __name__ == '__main__':
    # 流程：① 装钩子 → ② 解析参数 → ③ 奖励自检(可选) → ④ 定目录/数据集/轮数 → ⑤ 覆盖权重(可选) → ⑥ 建环境 → ⑦ 跑训练 → ⑧ 取回产出 → ⑨ 收尾汇总 → ⑩ 存 checkpoint

    # 让环境每一步都把动作记下来
    # [详注-BEGIN]（生成简版时整段删除）
    # 装动作注入钩子：幂等；必须排在**任何环境构造之前** ✗✗（晚一步奖励读不到动作 ⇒ 动作项静默为 0）✓
    # [详注-END]
    install_action_hook()

    # 解析命令行参数
    # [详注-BEGIN]（生成简版时整段删除）
    # 解析命令行参数（--output-dir 由 Java 平台注入；两入口的参数表各由生成器裁成真正生效的子集 ✓）
    # [详注-END]
    args = parse_args()

    # 奖励自检开关
    # [详注-BEGIN]（生成简版时整段删除）
    # ② --check-reward：奖励公式回归自检（与数据集原版逐位比对；最大绝对差 == 0 ⇒ 退出码 0 ✓，可当 CI 用）
    # [详注-END]
    if args.check_reward:
        # 奖励自检
        _worst = _reward_equiv_check(CUSTOM_REWARD_KWARGS, verbose=True)
        sys.exit(0 if _worst == 0.0 else 1)

    # 确定输出目录
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
    # 训练轮数
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
    # 随机种子
    seed = int(getattr(args, 'seed', None) if getattr(args, 'seed', None) is not None else DEFAULT_SEED)
    # 根据入参覆盖奖励中的部分参数
    # [详注-BEGIN]（生成简版时整段删除）
    # ⑥ 覆盖奖励权重：给了就改 CUSTOM_REWARD_KWARGS；必须排在 build_env_config **之前** ✗（否则静默无效）
    # [详注-END]
    for _oname, _obox, _okey, _oshown, _owhy in (
        ('bat-weight', CUSTOM_REWARD_KWARGS, 'bat_weight', 'bat_weight', '电池择时项'),
        ('bat-loss', CUSTOM_REWARD_KWARGS, 'bat_loss_weight', 'bat_loss_weight', '电池损耗项'),
        ('cost-weight', CUSTOM_REWARD_KWARGS, 'cost_weight', 'cost_weight',
         '电费项 price×max(0,net)，含电池'),
        ('p4-hinge-w', P4_COST_HINGE, 'w', 'P4_COST_HINGE["w"]', None), 
        ('p4-hinge-target', P4_COST_HINGE, 'target', '目标线',
         'B2 ≈ 1.07~1.09 × 目标线 ⇒ 0.90 对应 B2 ≈ 0.96~0.98'),
    ):
        _oval = getattr(args, _oname.replace('-', '_'), None)
        if _oval is None:
            continue
        _obox[_okey] = float(_oval)
        _otag = '[P-13]' if _oname.startswith('p4-hinge') else '[奖励]'
        _oextra = _owhy or f'目标线 {P4_COST_HINGE.get("target"):g}'
        log_console(f'{_otag} --{_oname} 覆盖：{_oshown}={float(_oval):g}（{_oextra}）')

    # 建训练环境
    train_env_config = build_env_config(
        train_schema, train_steps, output_dir, enable_render=False, record_details=False
    )

    log_console(f'初始化 SAC 多智能体，导出目录: {output_dir.resolve()}')
    log_reward_banner(log_console)   # 奖励口径 + 动作重标定总览（实现在 utils/train.py ✓）
    log_console(f'训练 schema={train_schema} steps={train_steps or "auto(数据集自带)"}')
    log_console(f'训练中中期评估/探针 schema={eval_schema} steps={eval_steps or "auto(数据集自带)"}')
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

    # 经验池容量
    _rb_kwargs = {}
    if REPLAY_BUFFER_CAPACITY:
        _rb_kwargs['replay_buffer_config'] = {'capacity': int(REPLAY_BUFFER_CAPACITY)}

    probe = _AGENT_ENV_CLS(train_env_config)
    # 训练主循环
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

    # 取回参数
    _last_epoch = _o._last_epoch          
    _mid_best = _o._mid_best              
    _mid_eval_hist = _o._mid_eval_hist    
    ckpt = _o.ckpt                        
    ckpt_dir = _o.ckpt_dir               
    model = _o.model                      
    _train_secs = time.perf_counter() - _o._t_train0
    # 训练结束
    ckpt.save('训练结束', _last_epoch, _mid_best, _mid_eval_hist)
    # 打印收尾
    log_training_summary(
        log=log_console, model=model, stopped_reason=_o._stopped_reason,
        last_epoch=_last_epoch, start_epoch=_o._start_epoch, train_epochs=train_epochs,
        train_secs=_train_secs, sampled=_o._sampled_prev,
        mid_best=_mid_best, mid_prev_sums=_o._mid_prev_sums, mid_vote_stale=_o._mid_vote_stale,
        mid_best_sums=_o._mid_best_sums, mid_worsen=_o._mid_worsen, mid_conv=_o._mid_conv,
    )
    # 用训练期最优快照替换 model
    _best_model = restore_best_model(ckpt, last_epoch=_last_epoch, log=log_console)
    if _best_model is not None:
        model = _best_model
    # [详注-BEGIN]（生成简版时整段删除）
    # 本段替换掉源文件「训练完成 → 跑评估仿真」的收尾：训练脚本到此结束，评估全交给 Multi-agent-eval.py ✓
    # save_multi_agent_checkpoint 现在**顺带**把奖励口径 sidecar 写进 checkpoint 目录 ✓
    #   （2026-10-08 合并 ✓：原先那两行是另一个函数 `_write_reward_sidecar(_ckpt_saved)` ✓ —— 该函数**已删除** ✓）
    # [详注-END]

    # 保存checkpoint
    _ckpt_saved = save_multi_agent_checkpoint(model, ckpt_dir, log_console=log_console)
    log_console('')
    log_console(f'CHECKPOINT={_ckpt_saved}')
    log_console(
        f'训练完成（本脚本只训练，不出 KPI）。要看 KPI 请运行：'
        f'python Multi-agent-eval.py --checkpoint "{_ckpt_saved}" '
        f'--eval-schema {eval_schema} --output-dir {output_dir}'
    )
    log_console(
        '提示：Java 平台可把配置页的「multi_agent_checkpoint」设为上面的绝对路径，'
        '之后评估任务即会跳过训练直接复用该模型。'
    )
    sys.stdout.flush()
    sys.exit(0)
