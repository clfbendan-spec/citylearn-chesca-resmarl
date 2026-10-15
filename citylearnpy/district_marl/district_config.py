# -*- coding: utf-8 -*-
"""区域级 MARL 的全部可调参数（集中一处，便于消融实验）。

【为什么单独成文件】
  与 utils/config.py 的分工：那里是**原流水线**的参数，本文件是**本包新增**的参数。
  集中放一处的好处：做消融（关掉区域观测 / 关掉尖峰惩罚 / 换共享策略……）时
  只改这一个文件或只覆盖对应键，不必翻代码。

【取值口径与依据】
  · DISTRICT_*_NET 的阈值量级取自原流水线 ComfortOutagePenaltyReward 的同名默认
    （building_peak_net=3.0 / district_peak_net=6.0 / valley_district_net=4.0），
    保证"社区尖峰/谷底"两个口径与原奖励判据**同一数量级**，便于横向比较。
  · DISTRICT_NET_SCALE 取 9.0 ≈ 3 栋 × 单栋 3.0（本数据集 3 栋楼）。
    它不是"物理常数"，只是把量级压到 ~1 的归一尺度；换数据集应重设。
"""

from pathlib import Path

# =============================================================================
# 一、区域观测特征（district_features / district_env）
# =============================================================================

# 归一尺度：典型的社区净用电量级（≈ 楼栋数 × 单栋峰值）
DISTRICT_NET_SCALE = 9.0

# 判定"社区尖峰 / 社区谷底"的净用电阈值（与原奖励同名默认同量级）
DISTRICT_PEAK_NET = 6.0
DISTRICT_VALLEY_NET = 4.0

# 特征统一裁剪范围（对称）⇒ 观测空间恒为 Box(-1, 1)，与数据漂移无关
DISTRICT_FEATURE_CLIP = 1.0

# 是否给每个 agent 追加区域观测（消融开关：False = 退化成原 ContextRLlibEnv）
DISTRICT_OBS_ENABLE = True

# =============================================================================
# 二、区域奖励（district_reward）
# =============================================================================
# 注意：下面四个权重**默认全为 0** ⇒ DistrictPeakReward 单独使用时与原
# CustomComfortReward 逐位一致；本包的训练入口会显式传入"DISTRICT_*_ACTIVE"的值，
# 于是"区域强调"是**显式打开**的，而不是藏在类的默认值里（可审计、可消融）。

# 显式社区尖峰惩罚：r -= w × max(0, 社区净用电 − 目标线)
# 【2026-10-15 调参】原 3.0/6.0 经实测失效：单栋项 hot_act_weight=110 / bat_weight=50
#   量级大两个数量级 ⇒ 区域项被淹没（探针实测单步奖励 -0.015~-0.4，区域项占比 <3%），
#   320 轮社区峰值全程横盘 17.2。改为压过 bat_weight 的量级，并下调目标线提高触发率。
DISTRICT_PEAK_WEIGHT = 60.0
DISTRICT_PEAK_TARGET = 4.0          # 目标线：社区净用电超过它才罚（均值≈2.91，取 1.4×均值）

# 团队奖励混合：r_i ← (1−s)·r_i + s·mean(r)
#   s>0 时三栋楼的**相对**差异被压缩，公共目标被放大 ⇒ 治"搭便车 / 各扫门前雪"。
#   代价：过度混合会让 agent 失去"我该多做一点"的动机（信用分配变糊）。
# 【2026-10-15 调参】原 0.25 在 shared policy 之上叠加，加剧同质化 ⇒ 先归零隔离变量。
DISTRICT_TEAM_SHARE = 0.0

# 【方案 1：按贡献分摊】把"集体惩罚"按 own_net_i / dist_net 分摊
#   0.0 = 退回旧的均摊（向后兼容原版）
#   1.0 = 严格按"自己贡献的那部分"承担（a2 烧 50% 拿 50% 惩罚）
#   中间值 = attribution 部分按份额 + 其余均摊
# 【2026-10-15 二轮调参】开 1.0：解决"a0 独削、a2 旁观"的信用分配问题。
DISTRICT_ATTRIBUTION = 1.0

# 【方案 2：峰值-锚定】把"接近/超过本局峰值的步"放大惩罚
#   0.0 = 关闭（按 over 量固定罚）
#   1.0 = 接近/超过本局峰值的步罚更狠（最大约 2×）
#   ⇒ 让"造成新峰的那步"获得更大梯度，n-step return 可向其反向传播
# 【2026-10-15 二轮调参】开 1.0：解决"舒适度主导、削峰梯度被压平"问题。
DISTRICT_PEAK_ANCHORED = 1.0

# 错峰引导：社区处于谷底时，SOC 越低的楼奖励越大（"让最空的先充"）
#   0 = 关闭。开启后需要观测里有 own_soc_rank 才学得动（本包默认提供）。
DISTRICT_STAGGER_WEIGHT = 0.0
DISTRICT_STAGGER_SOC_TARGET = 0.85

# =============================================================================
# 二·B、【方案 3：结构化动作空间】把"削峰"变成一个显式的动作维度
# =============================================================================
# 【动机】方案 1+2 证明：靠"奖励里加区域项"去教 agent 削峰，梯度会被单栋项淹没、
#   且 100→200 轮只表现为高方差震荡（见报告 §0.6/§0.7）。根因是**信用分配**：
#   "该削峰"这件事必须先在奖励里被辨识出来，再反传到动作。
#   方案 3 换范式：**不做信用分配**，直接把"削峰响应"做成一个显式动作维 a_peak_resp,
#   让策略输出它 —— 学不学得会变成"策略敢不敢在峰值步开这一维"，不再是"能不能从
#   奖励里把信号挑出来"。
#
# 【动作语义】每 agent 动作空间由 3 维扩到 4 维：
#     [a_dhw, a_elec, a_cool, a_peak_resp]   （前 3 维与现状完全一致）
#   a_peak_resp ∈ [0,1] 的含义（由 _dm_peak_action_apply 落实）：
#     0.0 ⇒ **完全不干预**（逐位 == 原 3 维行为，零侵入）
#     1.0 ⇒ 最强削峰响应：制冷维按 PEAK_RESP_COOL_FRAC 降额 + 电池维按
#           PEAK_RESP_BATT_DISCHARGE 深度放电
#   中间值线性插值 ⇒ 策略可以"轻削/重削"，而非只能在开/关之间跳。
#
# 【为什么这样能治"学不动"】SAC 在连续动作上做的是"最大化 Q"。当削峰维的收益
#   被**直接**体现在 a_peak_resp 这一个维度上（而非摊散到 3 栋的舒适项里），
#   策略梯度只需判断"这一维该往哪走"，不必再解耦三类设备的混合效应。
#
# ⚠️ 默认 0 = 关闭 ⇒ 动作空间仍 3 维，与原版逐位一致（零侵入铁律）。
#    开启时（=1）动作空间变 4 维，**旧 checkpoint 不兼容**（输入层维度变了）。
DISTRICT_PEAK_ACTION_DIM = 0

# 削峰响应强度映射：a_peak_resp=1 时，制冷开度乘以此倍率（<1 = 降额省电）
DISTRICT_PEAK_RESP_COOL_FRAC = 0.55
# a_peak_resp=1 时电池维的目标值（-1 = 最大放电，与 CHESCA 峰值满放同向）
DISTRICT_PEAK_RESP_BATT_DISCHARGE = -1.0
# 是否只在"社区峰值步"允许该维生效（1 = 门控，仅峰值步生效；0 = 全程可自由使用）
#   ⚠️ 3a（纯学习）取 0：不预设"什么时候该削"，让策略自己学。
#   取 1 会引入"峰值判据"这一规则先验 ⇒ 那是 3b（残差式）的形态，不是 3a。
DISTRICT_PEAK_ACTION_GATED = 0


# =============================================================================
# 二·C、可复现最优（v4）：SAC 旋钮
# =============================================================================
# 【这是什么】纯 MARL（不叠加 CHESCA 规则）全谱系 8 组配置里，v4 是唯一一组
#   3-seed 平均归一峰值（all_time_peak_average）稳定低于 0.90 的可复现变体：
#
#     配置                      3-seed mean      散度
#     v2-100 (方案1+2)          0.9192          ±0.0081
#     v2-200 (方案1+2)          0.8558          ±0.0460  ← 噪声主导，不可复现
#     v3a    (4 维动作,无门控)  0.9304          ±0.0007
#     v3b    (4 维动作,门控)    0.9241          ±0.0059
#   ★ v4     (方案1+2 + 本组旋钮) 0.8903         ±0.0213  ← 本文件默认值
#     v4n    (v4 + n_step=3)    0.8872          ±0.0172
#     CHESCA soft(5,6)          0.638           ——（规则派，范式不同）
#
# 【怎么来的】奖励配比与 v2 逐位一致（方案 1 分摊 1.0 + 方案 2 峰锚 1.0），
#   只拧两个 SAC 超参 ⇒ 0.9192 → 0.8903 全部归因于超参，唯一自变量干净：
#     · 回放池 5 万 → 20 万：让 SAC 采样到更老的跨回合经验（跨回合削峰信号更完整）；
#     · τ 5e-3 → 2e-3：target 网络更新更软 ⇒ 价值估计更稳、策略震荡收窄。
#   实测副作用：训练耗时约 +40%（buffer 变大后采样稍慢），可接受。
#
# 【提醒】v4 仍是"范式差距"的注脚 —— 0.8903 vs CHESCA 0.638 差 39%。
#   本组默认值只是把"纯 MARL 这一侧的最好成绩"变成开箱可跑。
#
# ⚠️ 零侵入：这三个常量是**本包新增**的默认值来源，district_train.py 的 argparse
#    默认值引用它们；显式传 CLI 时行为与改前完全一致（逐位可复现）。
#    注意 RLlib 侧的"是否下发"由 district_train.py 判断（τ == 5e-3 且 n_step == 1
#    且 buffer == 旧默认时不下发 kwargs），所以改这里会真的改变"不传参数"时的行为。
DISTRICT_REPLAY_BUFFER_CAP = 200000      # env-step（旧默认 50000）
DISTRICT_SAC_TAU = 2e-3                  # 旧默认（RLlib）5e-3
DISTRICT_SAC_N_STEP = 1                  # 1 = 单步 TD（= v4）；3 = v4n


# =============================================================================
# 三、学习结构（district_train）
# =============================================================================

# 参数共享：所有 agent 共用一个 SAC 策略（输入含"本楼身份"与区域特征）。
#   True  = 参数级协同（本包默认；RLlib 侧只建一个 PolicySpec，最稳）
#   False = 每 agent 独立策略（与 Multi-agent.py 一致的对照基线）
DISTRICT_SHARED_POLICY = True

# 共享策略下"本楼身份"如何编码：'onehot' = 用楼栋 one-hot（来自 ContextRLlibEnv）
DISTRICT_IDENTITY_MODE = 'onehot'

# =============================================================================
# 四、评估与选点（district_train / district_eval）
# =============================================================================

# 每多少轮做一次区域评估（贪心、跑整段）
DISTRICT_EVAL_EVERY = 20

# best-checkpoint 的选择指标（取**区域级、越小越好**的归一 KPI）
#   可选：all_time_peak_average / daily_peak_average /
#         daily_one_minus_load_factor_average / ramping_average /
#         cost_total / carbon_emissions_total ...
DISTRICT_BEST_METRIC = 'all_time_peak_average'

# 次选指标（主指标打平时用；None = 不启用）
DISTRICT_BEST_TIEBREAK = 'daily_peak_average'

# 接受门槛：主指标改善至少这么多才算"创新低"（防浮点噪声反复刷盘）
DISTRICT_BEST_MIN_GAIN = 1e-4

# =============================================================================
# 五、训练规模（沿用原流水线的量级；独立成键便于本包单独调）
# =============================================================================
# 【2026-10-15】320 → 100：全谱系复检显示 100→200→320 轮只会进入高方差震荡期
#   （200ep 3-seed 散度 ±0.046）⇒ "加轮数改善"是伪结论。v4 的 0.8903 就是 100 轮
#   的成绩，默认取 100 与"可复现最优"对齐，训练耗时也压到约 1/3。
DISTRICT_TRAIN_EPOCHS = 100
DISTRICT_SEED = 3

# 默认数据集
#   ⚠️ 训练与评估同域（local → local）才能对上 v4 的 0.8903。
#      评估若换成 online_* 属于跨域，数值不可直接与 0.8903 比较。
DISTRICT_TRAIN_SCHEMA = 'citylearn_challenge_2023_phase_2_local_evaluation'
DISTRICT_EVAL_SCHEMA = 'citylearn_challenge_2023_phase_2_local_evaluation'


# =============================================================================
# 六、断点目录（训练写 / 评估读）
# =============================================================================
# 【2026-10-10 改：按任务目录落盘，取代原先的全局固定目录】
#   原先训练写死一个全局"最新模型"目录、评估默认读它 ⇒ 所有任务共用同一份、
#   互相覆盖，且**无法按训练任务 id 定位模型**（任务管理页的「复用历史训练任务」
#   对区域级评估形同虚设）。
#   现在：训练默认写进**本次任务目录**（= 平台传的 --output-dir）下的
#   DISTRICT_CKPT_REL_DIR；评估用平台注入的 --train-task-id 到
#   <输出根>/<训练任务id>[-train]/DISTRICT_CKPT_REL_DIR 取模型。
#   这套约定与 CHESCA_ResMARL.py 的模型定位、以及 Java 侧 MARL_CKPT_REL_DIR 完全一致。
DISTRICT_CKPT_REL_DIR = Path('checkpoints') / 'multi_agent_resume'

# best 快照的兄弟目录名（与 utils/config.py 的 BEST_CKPT_DIR_NAME 一致）
DISTRICT_CKPT_BEST_REL_DIR = DISTRICT_CKPT_REL_DIR.parent / 'multi_agent_resume_best'

# 训练断点进度文件：写进断点目录，平台（Java）据此判断「该任务的模型可用」
# 并在任务管理页展示训练进度 ⇒ 少了它，区域级训练任务在「复用」下拉里会被
# 显示成「（模型已丢失）」并禁选。
DISTRICT_CKPT_PROGRESS_FILE = 'train_progress.json'

# 旧版全局固定断点目录：仅作**兜底**保留。
#   评估脚本在既没有 --train-task-id、也没有 --checkpoint 时才读它
#   （兼容独立运行习惯与历史磁盘上的模型；平台编排路径不会走到这里）。
DISTRICT_CHECKPOINT_DIR = Path(r'D:\citylearn-demo\output\district_marl_checkpoints')


def district_reward_kwargs():
    """把本文件里的区域奖励参数打包成"可直接喂给 CityLearn"的 kwargs。

    返回值会与 utils.config.CUSTOM_REWARD_KWARGS 合并后再传给
    CityLearnEnv(reward_function_kwargs=...)，因此**不会覆盖**原奖励参数。
    """
    return {
        'district_net_scale': float(DISTRICT_NET_SCALE),
        'district_peak_target': float(DISTRICT_PEAK_TARGET),
        'district_valley_target': float(DISTRICT_VALLEY_NET),
        'district_peak_weight': float(DISTRICT_PEAK_WEIGHT),
        'district_team_share': float(DISTRICT_TEAM_SHARE),
        'district_stagger_weight': float(DISTRICT_STAGGER_WEIGHT),
        'district_stagger_soc_target': float(DISTRICT_STAGGER_SOC_TARGET),
        'district_attribution': float(DISTRICT_ATTRIBUTION),
        'district_peak_anchored': float(DISTRICT_PEAK_ANCHORED),
    }


def district_env_config():
    """区域观测层的配置（会挂在 env_config['district_marl'] 上）。"""
    return {
        'enabled': bool(DISTRICT_OBS_ENABLE),
        'net_scale': float(DISTRICT_NET_SCALE),
        'peak_net': float(DISTRICT_PEAK_NET),
        'valley_net': float(DISTRICT_VALLEY_NET),
        'clip': float(DISTRICT_FEATURE_CLIP),
        # 【方案 3】结构化动作维度：0 = 关闭（动作空间 3 维，与原版逐位一致）
        'peak_action_dim': int(DISTRICT_PEAK_ACTION_DIM),
        'peak_resp_cool_frac': float(DISTRICT_PEAK_RESP_COOL_FRAC),
        'peak_resp_batt_discharge': float(DISTRICT_PEAK_RESP_BATT_DISCHARGE),
        'peak_action_gated': int(DISTRICT_PEAK_ACTION_GATED),
    }
