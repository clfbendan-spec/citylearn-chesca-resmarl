# ⚠️ 本文件是**精简注释版**（由 `_gen_marl_split.py` 生成 ✓）：全部「详注块」已整段删除 ✓，
#    代码与同目录的 `X.detailed.py` **逐字相同** ✓（AST 一致 ⇒ 行为一致 ✓）。
#    **改注释请改 `.detailed.py` 那份** ✗（本文件每次生成都会被覆盖 ✗），改完重跑 `_gen_marl_split.py` ✓。
from __future__ import annotations

# -*- coding: utf-8 -*-
# config = 三个入口共用的"设置总表"：训练规模 / 早停判据 / 奖励怎么算 / 断点里存什么 ✓

# ============================================================================
# ==== 段：train_config（原 utils/config.py ✓）====
# ============================================================================
# 原模块文档串（原样保留 ✓）：



# =============================================================================
# 训练规模（轮数 / batch / 采样量）
TRAIN_EPOCHS = 320    # 每轮 = 1 次 model.train()（P8-2：60→360；后定型 320）
TRAIN_BATCH_SIZE = 512  # learner 每轮训练批大小（P15-1 的 256 已废，回滚 1024）
# 回放缓冲区必须先攒够 ≥ train_batch_size 条，否则 RLlib 采样会报错。
MIN_SAMPLE_BEFORE_LEARN = 512  # 学习开始前先攒多少步（≥ train_batch_size 即可）
# 每轮采样量 = fragment × worker 数。**保持 "auto"**：本版 RLlib 把 auto 解析为 100 env-step/轮，
# 而 100 这一档正是唯一产出可用模型的采样量（见上方对照表）；显式改大会让学习量塌到 1 批/轮。
ROLLOUT_FRAGMENT_LENGTH = "auto"   # 从显式 500 恢复成 auto（=100 env-step/轮）

# =============================================================================
# 「每轮训练量」的机制与显式化（C′-2 / C′-3）
MIN_SAMPLE_TIMESTEPS_PER_ITERATION = 100    # ← 定型：100（数据×10 已在 C′-3 实测证伪）
_SAMPLE_TARGET_BASE = 100     # SAC 原默认值 = 旧基线每轮采样量（反推训练强度用）
TRAIN_INTENSITY = TRAIN_BATCH_SIZE * (_SAMPLE_TARGET_BASE / float(MIN_SAMPLE_TIMESTEPS_PER_ITERATION))
# 进度行告警线：每轮训练批数低于此值即判「训练量塌陷」（两次翻车的共同形态）✓ 见 §12.6
TRAIN_BATCHES_PER_ROUND_MIN = 20

# =============================================================================
# 【已移除】评估期早停（2026-10-01）：原先的 EARLY_STOP_* 常量与三个 CLI 参数已整块删除 ✓
# =============================================================================

# 默认随机种子：固定为 1，保证同参数多次运行结果可复现（论文方差可跑 --seed 0/1/2）
DEFAULT_SEED = 3

# 决策推演日志 —— 先说明「trace」是什么 ✗：它不是屏幕上的 print 日志 ✗，
DECISION_TRACE_EVERY = 144

# =============================================================================
# 训练中「中期评估」+ 早停：判断"当前模型够不够好"，够好/没救就提前收工
MINI_EVAL_EVERY = 10      # 每多少轮做一次中期评估（240 轮 → 24 次 ≈ 21 分钟）
MINI_EVAL_STEPS = 288  # 【'full' 模式下忽略】只有跑头/尾两段时才用
MID_EVAL_WINDOWS = ('full',)   # P-A/P-B（2026-09-28）：只跑整段，与正式评估同源（见上方 2)）
MID_TARGET_HOT = 0.10     # 达标线：逐栋高温比例
MID_TARGET_COLD = 0.10    # 达标线：逐栋低温比例
MID_VOTE_RATIO = 0.6      # 优于上次的楼数占比 ≥ 该值 = 仍在进步（3 栋 → 2 栋）
MID_VOTE_PATIENCE = 5     # 连续多少次"未过投票线"才判停滞（1 = 一次定生死，噪声下不推荐）
MID_PATIENCE = 3          # （仅 ②' 用）连续多少次「最差和」无实质进步
MID_MIN_GAIN = 0.01       # （仅 ②' 用）「最差和」改善 ≥1 个百分点才算实质进步
MID_STOP_BY_VOTE = True       # 判据②：投票制停滞止损（推荐）
MID_STOP_BY_SCORE = False     # 判据②'：旧的「最差和」停滞止损（默认关）
MID_STOP_ON_WORSEN = True     # 判据③：单栋恶化保护（P8-2）
MID_WORSEN_MARGIN = 0.10      # ③ 某栋合计高于「自身历史最优」多少（比例）算恶化
# 中期评估会同时用两种方式算 KPI（奖励侧 / 旧楼栋读数）；差多少算"差太多"就报警：
#   [自检-警告]。判据一律采用奖励侧。0.02 = 2 个百分点。
MID_KPI_SRC_TOL = 0.02
MID_WORSEN_PATIENCE = 3       # ③ 连续多少次才算"该栋在恶化"
MID_STOP_WHEN_GOOD = True     # 判据①：达标即停（P1-B 起**遵守 min_train_epochs**；
                              #   原先刻意不受限 → b033d51b 在第 20 轮就停，而那次
                              #   "达标"是假阳性：正式评估里 B1 高温 86%）
MID_STOP_WHEN_CONVERGED = True   # 判据④：全楼都稳定收敛才停（P9-4）
MID_CONVERGE_SUM = 0.07  # ④ 该栋"高温+低温"合计低于此值，就算这一段收敛了
MID_CONVERGE_PATIENCE = 3        # ④ 连续多少次低于阈值才算"该栋已收敛"
# -----------------------------------------------------------------------------
# 判据⑤ 崩坏止损（P17-1）：早期识别「策略饱和在单一极端」的跑，省下 80+ 轮（12~20 分钟）
MID_STOP_ON_CRASH = True       # 判据⑤：崩坏止损（默认开；只体检一次，不受最小轮数限制）
CRASH_GUARD_EPOCH = 100        # 第几轮体检（太早会误杀：第 50 轮连可用模型都在 1.3）
CRASH_GUARD_MAX_HOT = 0.90     # 单侧饱和线：某栋高温 > 90%（策略几乎不制冷）
CRASH_GUARD_MAX_COLD = 0.80    # 单侧饱和线：某栋低温 > 80%（策略一直制冷）

# -----------------------------------------------------------------------------
# 训练轮数区间（最小 / 最大）
MIN_TRAIN_EPOCHS = 160        # 4d447f3b 已用 180 验证；策略突破在 80~120 轮
# （2026-10-07 起本常量**不再被入口使用** ✗）原为 --max-train-epochs 的默认值；该参数已撤下 ✓
MAX_TRAIN_EPOCHS = 320

# -----------------------------------------------------------------------------
# checkpoint 保存 / 续训（P14-1）：每 CKPT_EVERY 轮（及训练结束/早停）把 RLlib SAC 完整状态
CKPT_ENABLE = True
CKPT_DIR = 'checkpoints/multi_agent_resume'   # 相对本文件所在目录
CKPT_EVERY = 20              # 每多少轮保存一次（0 = 只在训练结束时保存）
CKPT_PROGRESS = 'train_progress.json'   # 记录已训练轮数 / 中期评估历史最优
# -----------------------------------------------------------------------------
# best 断点（训练期表现最好那一版的存档）：给最终评估用"历史最好的那一版"
BEST_CKPT_ENABLE = True  # False = 关掉"最好一轮"存档（评估就只用最后一轮权重）
BEST_CKPT_DIR_NAME = 'multi_agent_resume_best'  # 与 CKPT_DIR 同级
BEST_CKPT_META = 'best_meta.json'             # 记录 best 轮号 / 选择指标 / 逐栋合计
# -----------------------------------------------------------------------------
# "最好的一轮"按哪个指标选：舒适超标面积（越小越好；P5-A 判据）
BEST_CKPT_TARGET_SUM = 0.15                   # 每栋「高温+低温」合计的目标线（业务：≤15%）
# -----------------------------------------------------------------------------
# 次项与接受门槛（P1，2026-09-28）：修「全部达标后指标失去分辨力」
BEST_CKPT_TIEBREAK = 0.05  # 次要项权重：0.05 × 各栋超标之和（主要项够大，次要项只用来打破平局）
                               #   0.05×1.0 ⇒ 主序不变；全部达标时首项为 0 ⇒ 按总不适排序。
# -----------------------------------------------------------------------------
# 成本怎么影响"选最好一轮"：只在成本率超过目标线时才开始计分（P-12 判据）
P4_COST_WEIGHT = 0.0  # 成本项权重（0 = 关闭：选最好一轮只看舒适）
P4_COST_HINGE = {'w': 0.3, 'target': 0.90}   # w=0 关闭；扫参 0.15 / 0.3 / 0.6
BEST_CKPT_MIN_GAIN = 0.0       # best-ckpt 接受门槛。取 0 的依据：测评是"贪心 + 固定 seed +
                               #   整段"的确定性过程，指标差 = 策略的真实差异，不是采样噪声；
                               #   代价仅是存档保存次数变多（≤ 每 MINI_EVAL_EVERY 轮 1 次）。
BEST_CKPT_METRIC_VER = 3  # 指标算法的版本号：续训时若断点里的版本与它不同 ⇒ 不继承旧记录（算法不同，数值不可比）
                               #   （两种算法的数值量级不同（约 1e-7 vs 1e-2），混着比会出错 ⇒ 版本不同就不继承 ✓）
                               #   会让新存档永远刷不进去 —— 静默失效 ✗）
                               #   v2 加入 tiebreak、v3（P-4）加入成本项 ⇒ 与前一版数值都不可比

# -----------------------------------------------------------------------------
# replay buffer 随 checkpoint 保存（续训继承经验池）
CKPT_STORE_REPLAY_BUFFER = True    # True = 经验池随 checkpoint 保存/恢复（续训继承）
REPLAY_BUFFER_CAPACITY = 50000     # 经验池容量（env-step）；0 = 用 RLlib 默认（1e6，不推荐）

# ============================================================================
# ==== 段：reward_config（原 utils/config.py ✓）====
# ============================================================================
# 原模块文档串（原样保留 ✓）：




# -----------------------------------------------------------------------------
# 自定义奖励函数开关与参数
# -----------------------------------------------------------------------------
# USE_CUSTOM_REWARD=True  → 用**外部模块** custom_comfort_reward.py 里的
#                          CustomComfortReward 替换数据集自带的
#                          citylearn.reward_function.ComfortReward（训练+评估都生效）
#                          （类体只在那个模块里定义；本文件仅 import 它 ✓）
# USE_CUSTOM_REWARD=False → 保持旧行为，用 schema.json 里定义的默认奖励
USE_CUSTOM_REWARD = True

# 说明：
CUSTOM_REWARD_KWARGS = {
    # ---- ① 温度项（= 原版 ComfortReward）----
    'band': 1.0,  # 舒适带半宽（°C）：室温离设定点不超过它，就算"在舒适带内"
    'lower_exponent': 2.0,  # 太热时的罚分指数：偏离量取平方 ⇒ −(偏离量)²
    'higher_exponent': 3.0,  # 太冷时的罚分指数：偏离量取立方 ⇒ −(偏离量)³

    # ---- ② 太热了却不肯制冷 ⇒ 罚（给制冷"保底"：至少吹到某个开度）----
    'hot_act_floor': 0.15,  # 至少该吹到的开度（老的 const 算法用它；0.15 = 实测"什么都不做"时的开度）
    'hot_a_per_c': 0.026,  # 室温每超出舒适带 1°C，要求多吹这么多开度（= 实测灵敏度）
    'hot_a_cap': 1.0,  # 要求开度的上限（1.0 = 不限；实测最高到 0.9）
    'hot_act_weight': 110.0,  # 罚多重：室温高出舒适区多少，就按这个倍数罚（1 个"缺口单位" = 110 分）
    'hot_act_penalty_cap': 130.0,  # 单步最多扣 130 分（必须大于最坏情况的缺口罚，否则再热也罚不动）
    # 多热才算"该罚"：室温要超过 设定点 + 舒适带半宽 + 这个余量，才要求制冷（余量 = 提前刹车的缓冲）
    #   实测两头都试过：余量 0.5 ⇒ B1 高温 49.3%（刹车太晚）；0.0 ⇒ B1 低温 59.7%（刹车太早）
    #   ⇒ 取中点 0.25；三轮判决过程（P2-A / P3 / P4）
    'hot_act_min_over_c': 0.25,
    # ---- ②′ "这栋楼此刻刚够用的开度"怎么算：'load' = 按物理量逐步算（现在用这个）/ 'const' = 老的一刀切常数 ----
    'hot_a_need_mode': 'load',
    # ---- ②″ 吹过头也要罚：实际开度超过"刚够用的量"的那部分，按超出多少扣分（多吹白耗电、还容易把楼吹冷）----
    'hot_over_weight': 15.0,  # 每超 1 个"超标单位"扣多少分（历史上从 30 调到 15）
    'hot_over_tol': 0.005,  # 免罚宽限（绝对值）：超出量先减掉 0.005 再罚
    'hot_over_tol_frac': 0.15,  # 再免掉"刚够用量"的 15%（负荷低时自动变严、负荷高时允许提前预冷）
    'hot_over_penalty_cap': 60.0,  # 单步最多扣 60 分（防止这一项把整步奖励吃光）
    # ---- ②‴ 温度跑出舒适带后的罚分上限：≤0 = 不限（就用原版的平方 / 立方罚）----
    'hot_temp_cap': 0.0,
    'cold_temp_cap': 0.0,

    # ---- ③ 已经太冷了还继续吹冷风 ⇒ 罚（"关冷"）----
    'cold_cool_weight': 75.0,  # [带外] 基础罚分
    'cold_w_out_frac': 0.3,  # [带外] 轻罚区折算：基础罚分 × 0.3
    'cold_gap_gain': 1.0,  # [带外] 每低于下限 1°C，把罚分再放大这个倍数
    'cold_stop_margin_c': 0.50,  # [带外] 比舒适带下沿再低多少度，算"彻底过冷（死区）"
    'cold_maintain_act': 0.05,  # [带内/带外] 允许保留的"维持开度"（这部分不算过冷）
    'cold_penalty_cap': 120.0,  # [带外] 这一项最多扣多少
    # 边界处让罚分平滑过渡（否则梯度会跳）：cold_lower ± trans_zone 内渐变，
    'trans_zone_c': 0.10,  # 边界过渡区的半宽（°C，0 = 关闭）
    # [带内] "关冷"的罚分权重（只在舒适带下沿附近一小段生效：起算点 = 设定点 − 舒适带半宽×cold_near_free_frac）
    'cold_near_weight': 45.0,
    # [带内] 免罚范围有多宽（按舒适带半宽的比例算）：
    'cold_near_free_frac': 0.5,

    # ---- ④ 其它 ----
    'act_hot_only_when_occupied': False,  # True = 只在有人时才要求"太热必须制冷"
    # ---- ⑤ 电费项：按"全屋净用电"扣分（含电池 ⇒ 会打击电池"低价存、高价放"的赚钱行为）----
    'cost_weight': 0.0,
    # ---- ⑤′ 制冷电费：只按"制冷用了多少电"扣分（怎么算与电池无关）----
    'cool_cost_weight': 2.0,
    # ---- ⑥ 电池"低价存、高价放"的力度（唯一旋钮；0 = 关闭）----
    'bat_weight': 50.0,
    # ---- ⑥′ 电池净循环量定价（给"买了却没用于负载的电"计价）----
    'bat_loss_weight': 0.0,
    # 是否记录"决策推演"的各项明细（室温奖励项 / 需要的开度 / 计算过程…）。训练阶段在
    # build_env_config 里改传 False：省掉每步 3 栋 × 5 条 f-string 格式化与列表分配，
    # 纯开销、不影响奖励值与学习；评估阶段保持 True，否则决策推演记录里就没有各项明细。
    'record_details': True,
}





# CityLearn 用 importlib 按「模块名.类名」字符串实例化奖励函数（实例化发生在**环境
_CUSTOM_REWARD_MODULE = 'custom_comfort_reward'


# -----------------------------------------------------------------------------
# 奖励配置的"说明 / 随断点存档 / 从断点读回"（2026-10-05 从入口脚本搬进本模块 ✓）
import json                     # noqa: E402
import sys                      # noqa: E402
import time                     # noqa: E402
from pathlib import Path        # noqa: E402

from utils.base import CITYLEARNPY_DIR, log_console   # noqa: E402

# 奖励配置的"随断点存档"文件名：训练时把"本次真正生效的奖励配置"写进每个断点目录，
REWARD_CONFIG_SIDECAR = 'reward_config.json'


# 把当前生效的奖励函数及其数值参数整理成一个 dict（给界面悬停展示）✓
def describe_reward_function(citylearn_env) -> dict:
    rf = getattr(citylearn_env, 'reward_function', None)
    info: dict = {'reward_function': type(rf).__name__ if rf is not None else 'unknown'}
    if rf is not None:
        for key, val in sorted(vars(rf).items()):
            if key.startswith('_'):
                continue
            if isinstance(val, (bool, int, float, str)):
                info[key] = val
    info['note'] = (
        '自定义 CustomComfortReward（逻辑与数据集默认 ComfortReward 逐位一致；'
        '类定义在外部模块 custom_comfort_reward.py，可修改区在该模块内）'
        if USE_CUSTOM_REWARD else '数据集 schema 默认奖励（USE_CUSTOM_REWARD=False）'
    )
    return info






# -----------------------------------------------------------------------------
# 入口脚本的「默认路径 / 默认数据集」（2026-10-06 下沉到本模块 ✓）
# -----------------------------------------------------------------------------
DEFAULT_OUTPUT_DIR = Path(r'D:\citylearn-demo\outkpis')

# 训练 / 评估各用哪一个数据集（Java 平台可用 --train-schema / --eval-schema 覆盖 ✓）
DEFAULT_TRAIN_SCHEMA = 'citylearn_challenge_2023_phase_2_local_evaluation'
DEFAULT_EVAL_SCHEMA = 'citylearn_challenge_2023_phase_2_online_evaluation_1'

# 断点（checkpoint）存在哪个目录 / 从哪读（训练脚本写、评估脚本读 ✓）
DEFAULT_CHECKPOINT_DIR = (
    Path(CITYLEARNPY_DIR) / CKPT_DIR
    if CITYLEARNPY_DIR
    else Path(r'D:\citylearn-demo\citylearnpy') / CKPT_DIR
)

