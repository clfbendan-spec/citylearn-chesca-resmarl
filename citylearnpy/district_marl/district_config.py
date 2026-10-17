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
# 二·D、【方案 5：峰前储能预留】傍晚窗内惩罚低 SOC
# =============================================================================
# 【为什么加这一项（实测依据，2026-10-16）】
#   v4（0.8903±0.0213）与 CHESCA（0.638）的社区峰值差 7.078 kW 里，
#   **电池一项占 4.384 kW（62%）**、热设备占 2.693 kW（38%）（见 CHESCA-v4峰步通道分解.md）。
#   进入 v4 决定指标的那一步（#669 ⇒ hour=22）时三栋 SOC 只有
#   0.199/0.200/0.362，而 CHESCA 是 0.607/0.600/0.765；
#   且 v4 全天 SOC 几乎贴 0.20（电池只做时段型 h≈1–6 充、6–8 放的小循环）。
#   ⇒ 缺口不在动作空间（拆 0.75 制冷地板在 #669 只值 1.8 kW），而在**峰前没留住电**。
#
# 【机制】h ∈ [17, 22] 时：r_i -= w × max(0, 目标水位 − soc_i)
#   · 窗口对齐：CityLearn 的 hour ∈ 1..24，且 step i ⇒ hour = i%24+1（实测确认）；
#     本数据集决定指标的 #643 ⇒ h=20、#669 ⇒ h=22，均落在窗内。
#   · 策略侧观测本来就含 hour ⇒ 能分辨"现在是不是傍晚"，不构成部分可观测。
#   · 读不到 SOC 时该项退化为 0（不罚、不误伤），不会因缺键静默产生常数偏置。
#
# ⚠️ 默认 0 = 关闭 ⇒ 与升级前逐位一致（零侵入铁律）。
# ⚠️ 量级提醒：单步最大缺口 = 目标 − SOC 下限(0.2) = 0.4。
#    本项目已有教训——区域项曾因量级太小（3.0）被单栋项（hot_act_weight=110）淹没，
#    实测无效后才提到 60。所以 A/B 档位取 60/150，而**不是** 0.5/1.0。
DISTRICT_SOC_RESERVE_WEIGHT = 0.0        # 0 = 关闭（默认）；A/B 档位建议 {60, 150}
DISTRICT_SOC_RESERVE_HOURS = (17.0, 22.0)  # hour 闭区间（1..24）；覆盖 #643(20)/#669(22)
DISTRICT_SOC_RESERVE_TARGET = 0.60       # 水位目标（对齐 CHESCA 进入 #669 时的 0.60 档）

# =============================================================================
# 二·E、【方案 6：尖峰步豁免】把"傍晚门控"换成"尖峰门控"
# =============================================================================
# 【为什么加（2026-10-16 实测，报告 District-MARL-方案5-SOC预留奖励A-B.md §机制）】
#   方案 5 用"傍晚"当门控，w=150 时确实把窗内 SOC 均值从 0.199 抬到 0.621，
#   但决定指标的 #669 峰步 SOC 仍只有 0.213 —— 因为 #669 是**无预警异常日**：
#   day 27 的 h21 社区不可移负荷仅 1.736 kW，h22 一步跳到 15.388 kW（8.9 倍）。
#
#   ★ 离线判据可分性实测（_probe_nonshift_anomaly.py）：
#       当日累计 ns @h18 / h20 / h21 的全季分位 = 50.0% / 43.3% / 43.3%
#     ⇒ **任何"用已观测 ns 预测异常日"的门控都提前不了**（不可移负荷逐时独立）。
#       前一日同小时 @h20 看似满分，但那只是因为 day 26 h20 本身就是
#       CHESCA 峰值步 #643（另一个尖峰），不是前兆 —— 用它当判据属事后巧合。
#
# 【怎么办】CityLearn 的 obs **本步就带 `non_shiftable_load`**（实测确认，
#   67 键之一）⇒ 根本不需要预测。改成**门控方向反转**：
#       · ns ≤ 阈值 ⇒ 正常要求水位（罚低 SOC）——「平时储备」
#       · ns >  阈值 ⇒ **本步豁免** —— 「尖峰放行」
#   这与 CHESCA 的形态一致（规则派全天顶高水位、尖峰来了再放），但代价更小。
#
# 【为什么判据必须用 ns 而不是 net】net 含 agent 自己的动作 ⇒ 可被操纵，
#   会出现"削峰削到自己失去豁免"的自相矛盾（方案 5 的奖励门控已知的坑）。
#   non_shiftable_load 是外生的、不可操纵。
#
# 【阈值怎么取】社区 ns：mean=1.95 / 各 hour P90≈2~6 / max=15.39（= #669）。
#   取 6.0 ≈ 覆盖全季最尖的一批步：实测命中 #669(15.39) 与 #643(9.096)。
#
# ⚠️ 默认 0 = 关闭 ⇒ 与"方案 5 原样"逐位一致（零侵入铁律）。
DISTRICT_SOC_RESERVE_NS_GATE = 0.0       # 0 = 关闭；建议 6.0（kW，社区不可移负荷阈值）

# =============================================================================
# 【方案 7：尖峰步充放计价】豁免步不再"什么都不做"，而是按本栋净电池流计价
# =============================================================================
# 【动机·实测（2026-10-16）】方案 6 的豁免是**无条件**的：尖峰步只免罚，不区分本栋在
#   充电还是放电。结果 B 组在 #690(h19, ns=9.848) 反而**充了 1.74 kWh**，把峰值从
#   #669 搬到了 #690（15.00 kW）—— 典型的"打地鼠"。
# 【为什么不需要预测】实测不可移负荷逐时独立：#669 当天 h21 社区 ns 仅 1.736、
#   h22 跳到 15.388（8.9 倍）⇒ 提前预测不可能。但本步 obs 里就带
#   `electrical_storage_electricity_consumption`（正=充电 / 负=放电），
#   经《_probe_bat_flow_phase.py》实测确认它是**本步**值（H1 无滞后残差 1.7e-2，
#   vs 滞后一步的 1.18，区分度 70×），且量纲与 net_electricity_consumption 同源。
# 【形态】豁免步： r_i -= w × flow_i      （充 ⇒ 罚；放 ⇒ 奖）
# 【为什么不破坏预充】实测豁免集（gate=6，23 步）**不含 #668**（ns=1.736 < 6）
#   ⇒ 预充步仍在方案 5 的罚区，预充动机原样保留。
# 【档位】flow 上限 ≈ 电池额定功率 3.32 kWh（b2 为 1.61）⇒ w=60 时单步最大 ±199。
#   与方案 5 的"单步最大缺口罚"（w×(0.6−0.2)=24）同量级略大 ⇒ 建议 {60, 150}。
#
# ⚠️ 默认 0 = 关闭 ⇒ 与"方案 6 原样"逐位一致（零侵入铁律）。
DISTRICT_SOC_RESERVE_SPIKE_WEIGHT = 0.0  # 0 = 关闭；建议 60 / 150

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

# ---- 验收口径（acceptance statistic，与"选点/断点"解耦）----------------------
# 【2026-10-16】`best_score` = 评估点取 min，实测是**方差最大化统计量**
#   （单次训练内部逐 epoch range 达 0.132，与跨次复跑同量级）⇒ 方案 5/6/7 的 27 组
#   A/B 效应量全部低于该口径的分辨率。换成"末 K 个评估点均值"后（零新增训练），
#   `w150 vs w0` 的 p 从 0.318 掉到 0.047，而两个**零效应对照仍 p≈0.84/0.92**（不污染）。
#   ⇒ 默认主口径改为 mean_last3；`best_score`/`best_epoch` 顶层字段**保持不变**，
#     仍是 best-checkpoint 与平台 train_progress.json 的依据（"best 是模型，mean_last3 是成绩"）。
#   可选：mean_last3 / mean_last（按 DISTRICT_ACCEPT_TAIL 长）/ mean_all / best / final
DISTRICT_ACCEPT_STAT = 'mean_last3'
DISTRICT_ACCEPT_TAIL = 3

# ---- 峰值早停（peak-stop，2026-10-17）----------------------------------------
# 【为什么需要】320 轮实测（local 训练 / online_1 评估，103.6 min）：best 出现在 ep120，
#   随后 ep140~320 一直是 0.97 的高方差平台，`acceptance`（末 3 个评估点）恰好取到
#   [160,180,200] 这三个**最差点**（0.9743），比 best 差 0.05。
#   ⇒ 越过 best 之后再跑，只会让"末窗"落到更差的点上，**既费时间又让主口径变差**。
# 【口径】连续 `patience` 轮未刷新 best（`epoch - best_epoch >= patience`）即停训：
#   · 停之前 best-checkpoint 已经保存 ⇒ 收尾正式评估用的仍是最优权重，产物格式不变；
#   · 只影响"跑多少轮"，不改奖励/观测/动作/选点任一环节；
#   · v4 的三个 seed best_epoch = 60/100/100，在 100 轮任务下 patience=40 **均不会触发**
#     ⇒ "不传参数 == v4 可复现口径"仍然成立；320 轮任务则省掉后半段。
# `0` = 关闭（回到无早停的旧行为，逐位一致）。
DISTRICT_PEAK_STOP_PATIENCE = 40

# 早停的**最早轮数**下限（两道闸门都要过：`epoch >= min_epochs` 且 `epoch - best_epoch >= patience`）。
# 【为什么还要这道闸】只有 patience 时，若 best 碰巧出现在前 60 轮，100 轮任务会被截到 80 轮
#   ⇒ 与 v4「跑满 100 轮」的口径不再一致。加上 min_epochs=100 后：
#     · 100 轮任务**永远跑满**（best 在最晚第 60 轮也不影响）⇒ 旧口径分毫不动；
#     · 320 轮任务仍能省掉后半段（best@120 ⇒ ep160 停）。
# `0` = 自动取 `min(train_epochs, 100)`。
DISTRICT_PEAK_STOP_MIN_EPOCHS = 100



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
        # 【方案 5】峰前储能预留（weight=0 ⇒ 接收端整段不执行）
        'district_soc_reserve_weight': float(DISTRICT_SOC_RESERVE_WEIGHT),
        'district_soc_reserve_hours': list(DISTRICT_SOC_RESERVE_HOURS),
        'district_soc_reserve_target': float(DISTRICT_SOC_RESERVE_TARGET),
        # 【方案 6】尖峰步豁免（ns_gate=0 ⇒ 接收端不执行 ⇒ 与方案 5 原样逐位一致）
        'district_soc_reserve_ns_gate': float(DISTRICT_SOC_RESERVE_NS_GATE),
        # 【方案 7】尖峰步充放计价（spike_weight=0 ⇒ 接收端不执行 ⇒ 与方案 6 原样逐位一致）
        'district_soc_reserve_spike_weight': float(DISTRICT_SOC_RESERVE_SPIKE_WEIGHT),
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
