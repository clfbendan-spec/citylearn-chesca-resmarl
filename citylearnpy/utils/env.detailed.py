# 注：本模块原名 utils/env.py（2026-10-07 utils 整理：按功能改名，内容未改 ✓）
from __future__ import annotations

# -*- coding: utf-8 -*-
# [详注-BEGIN]（生成简版时整段删除）
# 环境层：动作/环境解包 / 上下文环境 / schema 改造 / 建环境 / 探针 / 动作注入
#
# 本文件由 utils/ 下多个模块合并而来（2026-10-06 ✓，合并映射见每段横幅 ✓）：
#   · envs.py
#   · envs.py
#   · envs.py
#   · envs.py
#   · envs.py
#   · train_eval.py
#

# ============================================================================
# ==== 段：env_utils（原 utils/env_utils.py ✓）====
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# 环境 / 动作解包助手（三个入口脚本 + 诊断脚本共用）。
# =====================================================
#
# 把「RLlib 包装层 ↔ CityLearn 本体」之间的两处形态差异收在一处：
#
# · `unwrap_action`        —— RLlib 部分版本 `compute_single_action` 返回
#                             `(action, state, info)` 三元组，这里只取动作本体 ✓
# · `unwrap_citylearn_env` —— `RLlibMultiAgentEnv` →（逐层 `.env`）→ `CityLearnEnv`，
#                             判据是"该对象带 `buildings` / `reward_function`" ✓
#
# 原先这两段内联在 `Multi-agent.py` 里，被 20+ 处调用（mid-eval、评估循环、训练准备段、
# 各诊断脚本）。抽出后三个入口共用一份实现；诊断脚本仍可照旧用
# `ma.unwrap_action` / `ma.unwrap_citylearn_env` 调用（源文件里保留了同名 ✓）
#
# 本模块**不含任何配置常量**：与 `COOL_*` 动作映射、奖励参数完全解耦 ✓
# [详注-END]



from typing import Any, Optional


# RLlib 部分版本 compute_single_action 返回 (action, state, info)，只取动作本体 ✓
def unwrap_action(action: Any) -> Any:
    # [详注-BEGIN]（生成简版时整段删除）
    # RLlib 部分版本 compute_single_action 返回 (action, state, info)，只取动作本体。
    # [详注-END]
    if isinstance(action, tuple) and len(action) > 0:
        return action[0]
    return action


# 从 RLlibMultiAgentEnv 逐层 .env 找到带 buildings/reward_function 的 CityLearnEnv ✓
def unwrap_citylearn_env(rllib_env: Any) -> Optional[Any]:
    # [详注-BEGIN]（生成简版时整段删除）
    # 从 RLlibMultiAgentEnv 逐层 .env 找到带 buildings/reward_function 的 CityLearnEnv。
    # [详注-END]
    env = getattr(rllib_env, 'env', None)
    for _ in range(6):
        if env is None:
            return None
        if hasattr(env, 'reward_function') and hasattr(env, 'buildings'):
            return env
        env = getattr(env, 'env', None)
    return None

# ============================================================================
# ==== 段：context_env（原 utils/context_env.py ✓）====
# [详注-BEGIN]（生成简版时整段删除）
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# 楼栋上下文环境 + 冷却动作重标定（Multi-agent 三个入口共用一份）。
# =====================================================================================
#
# `ContextRLlibEnv` 在 CityLearn 的 `RLlibMultiAgentEnv` 之上做两件**环境契约层**的事：
#
# ① **观测扩展**（开关 `OBS_CONTEXT_*`）：给每个 agent 的观测追加
#    「制冷能力比值 / 楼栋 identity one-hot / 本步理想负荷所需开度 a_ref」，
#    并**同步扩大 `observation_space`**（RLlib 用它建策略网络输入层）。
#    拼接发生在**归一化之后** —— 常量特征过 NormalizedObservationWrapper 会被压成 0 ✗。
#    ⚠️ 改任一 `OBS_CONTEXT_*` 开关 = 改输入层 ⇒ **旧 checkpoint 不可复用，必须重训** ✗
#
# ② **冷却动作重标定**（`_cool_action_apply`，开关 `COOL_*`）：在 `super().step()` **之前**
#    改写冷却维动作。三种模式：P-1 负荷跟随（默认）/ P2 缩放 / C′-4 下界。
#    顺序是硬约束：奖励的动作注入 tap 包装的是基类 step ⇒ 它读到的必然是"已施加"的
#    动作，与建筑实际执行一致 ✓（这正是 decision_trace 的 act 列可信的机制来源 ✓）
#
# 本模块同时持有 `COOL_FLOOR_SCALE`（运行时衰减系数）与 `update_cool_floor_scale()`，
# 以及 `get/set_cool_floor_scale()` —— 原先是"写在一个文件、读在另一个文件"的**跨模块
# 共享可变全局** ✗；现在读写都在本模块内，对外只暴露一对显式访问器 ✓
#
# 配置口径（每个开关/常量的动机、实测判决与回退方法）**随代码一起搬来**，逐字未改 ✓
# （这些注释的归档整理另做，与本次"只搬家"分开 ✓）
# [详注-END]



import numpy as np
from citylearn.wrappers import RLlibMultiAgentEnv
from gymnasium import spaces



# （2026-10-07 更新 ✓）原先 Multi-agent.py 里有一层老名字 `_unwrap_citylearn_env` 指向本函数 ✓；
#   这个老名字已删 ✗ ⇒ 那 20+ 处调用点与诊断脚本统一改用**新名字** `ma.unwrap_citylearn_env` ✓（同一个东西 ✓）。


# 本步热容量 [kWh/步] = 额定电功率 × 当前 COP，读不到返回 0.0 ✓
def _cool_thermal_capacity(building, nominal_power, idx) -> float:
    # [详注-BEGIN]（生成简版时整段删除）
    # 本步热容量 [kWh/步] = 额定电功率 × 当前 COP，读不到返回 0.0。
    #
    # ⚠️ 不能用 `cooling_device.efficiency`：实测它是卡诺效率因子（0.25 左右），
    #    `nominal×efficiency` 只有 ~1 kWh/步，物理上不成立。
    #    COP 随室外温度在 3.1~10.2 之间变化（实测），因此必须逐时算。
    #
    # [详注-END]
    try:
        npw = float(nominal_power or 0.0)
        if npw <= 0.0:
            return 0.0
        tout = np.asarray(getattr(getattr(building, 'weather', None),
                                  'outdoor_dry_bulb_temperature', []), dtype=float).ravel()
        t = min(max(int(idx), 0), tout.size - 1) if tout.size else 0
        to = float(tout[t]) if tout.size else 25.0
        cop = float(np.asarray(building.cooling_device.get_cop(to, heating=False)).reshape(-1)[0])
        return max(0.0, npw * cop)
    except Exception:
        return 0.0


# "刚够用"的开度 a_ref = 理想负荷 ÷ 本步热容量，范围 0~1；读不到就返回 0.0 ✓
def _ideal_a_ref(building, nominal_power, idx) -> float:
    # [详注-BEGIN]（生成简版时整段删除）
    # "刚够用"的开度 a_ref = 理想负荷 ÷ 本步热容量，范围 0~1；读不到就返回 0.0 ✓
    #
    # · 理想负荷 = 数据集预计算的 `energy_simulation.cooling_demand_without_control`
    #   （跨 run 恒定）。NOCONTROL（BaselineAgent）交付的正是这条曲线：实测
    #   「实际开度 ≡ a_ref」比值 0.993、相关 0.995、平均偏差 0.0014
    #   ⇒ 这就是它"成本低 + 不过冷"的原因（开度逐时精确等于维持设定点所需的量）。
    # · ⚠️ 不要用观测里的 `cooling_demand`：实测它 = 设备**实际交付**的热量
    #   （a_act ≡ cool_dem/(nominal·COP)），拿它当"需求"会变成自证（缺口恒为 0）。
    # · 物理含义：把室温拉回设定点所需的最小开度。逐时、逐栋由物理量算出，
    #   不含任何手写的按楼常数 ⇒ 与"学习不应有针对单栋的规则"一致。
    #
    # [详注-END]
    try:
        ideal = np.asarray(getattr(getattr(building, 'energy_simulation', None),
                                   'cooling_demand_without_control', []), dtype=float).ravel()
        cap = _cool_thermal_capacity(building, nominal_power, idx)
        if not ideal.size or cap <= 1e-9:
            return 0.0
        t = min(max(int(idx), 0), ideal.size - 1)
        return float(min(max(ideal[t] / cap, 0.0), 1.0))
    except Exception:
        return 0.0




# =============================================================================
# 给每个 agent 的观测追加"这栋是谁"的信息 —— 制冷能力比值 + 楼栋身份（one-hot）
# [详注-BEGIN]（生成简版时整段删除）
# =============================================================================
# 要解决的问题（分析见对话记录）：B1 与 B2 的不适长期互斥（跷跷板）。
#   机理：观测里唯一表达"该不该开冷"的信号是 `T − SP`；但同一 `T − SP`
#         对 B1（需求 0.911 kW、会继续升温）要求 act↑，对 B2（需求 0.335 kW、
#         升温很慢）要求 act↓ → 同一输入给出相反梯度 → 网络被拉锯成折中值。
#   旁证：P9-1′ 把 maximum_temperature_delta 20→3.0（放大温度观测 3.5~6.7 倍）后，
#         B2 午后动作 0.42~0.51→0.49~0.62、温度被压到 23.3、低温飙到 45.3%
#         —— 证明策略开度确实由"温度这一路"驱动，且该增益是全局的（已证伪）。
# 做法：不改奖励、不改策略网络，只补上缺失的那一维"能力信息"：
#   ① 制冷能力比值 = nominal_power(本栋) / max(nominal_power) ∈ (0, 1]
#      B1 = 1.00 / B2 = 0.65 / B3 = 0.32
#      为什么不用更直觉的「负载率 demand/nominal」：实测（_verify_load_ratio.py）
#      负载率的均值 B1 0.112 / B2 0.063 / **B3 0.141**、夏季时刻 B2(0.687) > B1(0.529)、
#      B3 常达 1.000 —— 它把"能力"和"负荷"混在一起，反而显示"问题最小的 B3 最忙"
#      （B3 能力最小 2.602，比值天然容易饱和）。而决定"会不会过热"的是
#      **绝对热负荷 vs 绝对制冷能力**，所以这里给"能力"这一维（绝对值比值），
#      负荷那一维由原观测里已有的 cooling_demand 提供，二者在策略内部相乘即可。
#   ② 楼栋身份 one-hot（n_b 维）—— 提供"我是谁"这个事实，兜底保证可分。
#      说明：①② 都只是「条件信息」，不含任何"该多开还是少开"的先验；
#            "怎么用"仍完全由学习决定（奖励与网络结构均未改动）。
# 为什么加在 RLlibMultiAgentEnv 这一层（而不是 CityLearn 的 wrappers）：
#   CityLearn 层是 central_agent=True 的「所有楼拼接」向量，RLlibMultiAgentEnv
#   才按 agent 拆分（3 个 agent × 35 维）。在 CityLearn 层追加无法被正确拆分。
# 为什么常量特征不归一化也有效：它扮演 meta-RL 里的"任务上下文"，策略可以拿它做条件。
#   若走 NormalizedObservationWrapper，常量会被压成 0（min=max）而失效，
#   所以本层在**归一化之后**拼接、自己控制量级。
# 红线（吸取 P9-1′ 教训）：新增维度落在 [0,1] 且**不放大温度类信息**。
# [详注-END]
OBS_CONTEXT_ENABLE = True
OBS_CONTEXT_CAPACITY = True       # ① 制冷能力比值维度
OBS_CONTEXT_IDENTITY = True       # ② 楼栋 one-hot 维度
# ③ Step2B（2026-09-29）：算出这一步"刚够用"的开度 a_ref（每步现算，由物理量推出）
# [详注-BEGIN]（生成简版时整段删除）
#   为什么必须给：此前观测里唯一的负荷信号 `cooling_demand` 实测是"设备刚交付了多少"（自证），
#   只能靠 T−SP 反推 ⇒ 必然滞后+过冲（实测 B2 多吹 37%、65% 的步过量）；而 NOCONTROL 的动作
#   就是 a_ref 本身（比值 0.993、相关 0.995）⇒ 给这一维，策略只需学一个近似恒等映射 ✓
# [详注-END]
OBS_CONTEXT_A_REF = True

# =============================================================================
# C′-4「制冷动作下界（floor）」：实测证明不行、已改回；这里只留结论与判据
# [详注-BEGIN]（生成简版时整段删除）
# -----------------------------------------------------------------------------
# ❌ 2026-09-28 结论：**已证伪，已回退**（当时置 COOL_FLOOR_ENABLE=False）。两条独立证据：
#   【证据 1｜零和】下界把 B1 实际开度的**下沿**从 0.039 抬到 0.148（= 关不掉冷）
#     ⇒ 冷 +17pp / 热 −18pp，**合计几乎不动** —— 只是把"热超标"平移成"冷超标"，
#     没增加任何控制精度，同时把该维控制权冻死（eff cv 55% → 9.4%）✗
#   【证据 2｜策略远胜任何常数】全季"固定开度"离线探针（7 档 × 2207 步，绕开下界）给出
#     "不学习"的上限：三栋最优常数 0.15 / 0.15 / 0.20 ⇒ 30.4% / 30.3% / 19.7%，
#     而策略实际 21.6% / 22.6% / 2.4% ⇒ **策略全胜（胜 8.8 / 7.7 / 17.3pp）**
#     （同探针：全季中立开度 B1≈0.150 / B2≈0.167 / B3≈0.182，且凉季↔热季漂移 1.2~2.1°C
#      ⇒ **单一常数必然在全季某段是错的**）
#   ⇒ 三条教训：① 别拿"欠训练快照"当"结构性自锁"（立论依据只跑 60 轮；320 轮时 B1 自己就
#     把开度爬到了 0.12）；② 映射侧硬干预会冻结控制权，而日志只报"已设置"、
#     **不会报警"策略已放弃该维"**；③ trace 的动作列必须落"建筑实际执行"值，否则诊断走偏
# 现状（为什么仍保留一个很小的 floor）：唯一作用是防止策略漂到 a→0 的 tanh 饱和区自锁
#   （实测：floor=0 + 纯缩放会让 B1 在 R10 就锁死 98% 高温）；而"随轮数衰减的课程式下界"
#   也已实测证伪 —— 撤除就打回死锁（e722911a：floor 0.127/0.096/0.049/0.002/0
#   ⇒ B1 热 30.9%/52.7%/86.9%/97.9%/97.9%），故 COOL_FLOOR_UNTIL 保持 0（不衰减）✓
# =============================================================================
# [详注-END]
COOL_FLOOR_ENABLE = True                   # floor 托举总开关（**必须开**：floor=0 + 纯缩放会早期自锁）
# Step 1（2026-09-29）：**三栋统一**，不再按楼栋查表 —— 见下方"三栋共用同一条映射"的说明块。
COOL_REMAP_FLOOR = 0.05                    # 所有楼栋共用同一动作下界；**必须明显低于中立开度 0.15**
COOL_FLOOR_UNTIL = 0                       # 0 = 不衰减（全程保持 floor；衰减会在撤除后立刻打回死锁）
COOL_FLOOR_SCALE = 1.0                     # 运行时衰减系数 0~1；训练循环每轮更新，评估前按 best_meta 恢复

# -----------------------------------------------------------------------------
# 动作映射（SPAN）：为什么用"乘一个倍率"而不是"砍一个下界"
# [详注-BEGIN]（生成简版时整段删除）
# -----------------------------------------------------------------------------
# 根因（两个数字钉死）：C′-4 的映射把**中立开度 0.15 放在 a=0**，而 a=0 处 tanh 深度饱和
#   （∂a/∂z ≈ 0.005）⇒ 热侧 ∂R/∂act=+110 传到 actor 只剩 ~0.5 —— **策略"想动也动不了"**
# 为什么放弃下界（e722911a 决定性证据）：B1 高温与 floor **完全同步**
#   （floor 0.127/0.096/0.049/0.002/0 ⇒ 热 30.9%/52.7%/86.9%/97.9%/97.9%，撤除即打回死锁）
#   ⇒ 下界是**外部托举**：绕过"策略自己走不动"，所以必须一直开着；而一直开着又让"减小 a 的
#     边际收益"变小 ⇒ 策略懒得调 ⇒ 冻结（cv 55%→9.4%）⇒ **「托举 ↔ 冻结」二选一（死结）** ✗
# 做法：线性缩放 applied = SPAN × a —— 把中立开度 0.15 挪到 **a = 0.5（tanh 梯度最大处）**
#   · 有效梯度 0.86×0.005 = 0.004 → 0.40×0.5 = 0.20（**放大约 50 倍**）；
#   · 策略初始化 a≈0.5 ⇒ applied = 0.20 ⇒ **一开始就站在舒适点**；
#   · 跑到 a=0 ⇒ applied=0 ⇒ 立即过热 ⇒ 热罚梯度 +110×0.40 = +44 能把它拉回
#     （而旧 floor 方案下贴 a=0 时 applied 仍是 0.14、不会过热 ⇒ **没有纠偏力**）
# 取值约束（改 SPAN 必读）：必须让"奖励要求"落在策略可达范围内 —— 热侧要求
#   a_need ∈ [0.15, 0.30] ⇒ 取 SPAN=0.40 ⇒ 工作区 a∈[0.375, 0.75]，既可达、又避开 tanh 饱和；
#   ⚠️ 改 SPAN 时必须逐 over 档验算 a_need/SPAN ≤ 1（旧值 SPAN=0.30 配旧 a_need 时最低一档
#     也要 a=1.09 ⇒ **全程不可达**，这正是"恒欠吹"的典型成因）
# 回退：COOL_SPAN_ENABLE=False（回到 applied=a）
# [详注-END]
COOL_SPAN_ENABLE = True                    # 动作缩放总开关
COOL_REMAP_SPAN = 0.40                     # 所有楼栋共用同一缩放系数（1.0 = 不缩放）

# =============================================================================
# P-1（2026-09-29）：把映射的「中立点」由**固定开度**改为**逐时负荷跟随**
# [详注-BEGIN]（生成简版时整段删除）
# =============================================================================
#   动机（e6cf8272 逐栋取证 + 同场景 NOCONTROL 对照，脚本 _diag_b2_cost.py）：
#     三栋的负荷需求几乎相同（a_ref p50≈0.16、p90≈0.44），但「相对负荷开度」的偏离完全不同：
#       B1 −18.6%（成本 0.874 ✓）、B2 **+32.4%**（成本 1.163、不适 7.4% ✗ 被无控制支配）、
#       B3 −8.8%（成本 0.936 ✓）。根因：旧映射中立点**固定**（a=0.5 ⇒ 开度 0.24）比负荷
#       所需的 0.19 高 25%，且 **B2 的输出均值停在初始化值 0.499** ⇒ 系统性超吹：
#       63.5% 的步超吹、多花 780 kWh（= B2 总电量的 63.6%），把室温压到 KPI 冷线外。
#     ⚠️ B2 的奖励罚分本就三栋最高（冷罚 −3.72/步 ≫ 超吹罚 −1.64/步）⇒ **不是"奖励没罚"，
#        而是策略没走到那个点** ⇒ 加权重治不了 ⇒ 必须改映射结构 ✓
#   做法：把中立点钉在**本步的负荷所需开度 a_ref** 上，用**乘法**（相对负荷的倍率）：
#       applied = a_ref × ( MIN_FRAC + (MAX_FRAC − MIN_FRAC) × a )
#     · a = 0.5（策略初始化点）⇒ 倍率恰为 1.00 ⇒ applied = a_ref = 无控制基线的「恒等跟随」
#       （实测比值 0.993）⇒ 三栋都从「不浪费」出发；B2 的初始化即（近）最优 ⇒ 病根被结构性消除 ✓
#     · a > 0.5 ⇒ 相对负荷多吹（前馈预冷/顶热，上限 MAX_FRAC）；a < 0.5 ⇒ 少吹
#       （下限 MIN_FRAC = 0.75 ⇒ **最多少吹 25%，不可能塌到 0**）
#     · 天花板/地板都变成「负荷相对」⇒ 不再有「高负荷步顶格吹不动」或「低负荷步白吹一大截」
#     · 工作点在 a≈0.5 = tanh 梯度最大处（∂a/∂z=0.5）⇒ 不必再靠 floor 托举
#     · a_ref 取不到（异常/越界）⇒ 才回退旧映射（注：合法为 0 不算"取不到"，见 P-6′(i)）
#     · ⚠️ 必须是**乘法**：加法式（a_ref + span×(a−0.5)，第一版已证伪）在 a<0.5 时会**塌到 0**，
#       而超吹罚是**单边**的 ⇒ 策略滑进 tanh 低斜率区就爬不回来：冒烟 _p1_load_smoke 实测
#       B1 的 a_raw p50=0.072（30.4% 的步贴 0）、applied 均值 0.045 vs 需求 0.185、
#       dT=+5.21 ⇒ **高温 93% 的关冷自锁** ✗。改乘法后 a=0 仍有 0.75×a_ref ⇒ 后果有界 ✓
#   为什么这仍是「标定」而非「按楼规则」：a_ref 是**物理量**（理想负荷 ÷ 本步热容量），
#     逐时逐栋由环境算出，不含任何 {楼号: 值} 的人为先验 ⇒ 与 Step 1 的原则一致 ✓
#   回退方法：COOL_LOAD_CENTERED_ENABLE = False（立刻回到 COOL_REMAP_FLOOR/SPAN 的旧映射）
# [详注-END]
COOL_LOAD_CENTERED_ENABLE = True  # P-1 总开关（True = 真实施加的开度以"本步刚够用"为中心）
# 倍率区间取 ±25%（[0.75, 1.25]）：实测三栋实际用到的倍率是 0.77 / 1.05 / 1.00
# [详注-BEGIN]（生成简版时整段删除）
#   （逐步对齐统计 _check_p1_aligned.py），±25% 正好覆盖；
#   ⚠️ 第一版取 ±50% 时 B1 漂到 mult=0.667（欠吹 33%）⇒ **相对形式的缺口随负荷成比例放大**，
#     高负荷步被伤得最重 ⇒ B1 高温 11%（冒烟 _p1_load_smoke40）✗ ⇒ 收紧到 ±25%
# [详注-END]
COOL_LOAD_MIN_FRAC = 0.75  # a=0 ⇒ 0.75×a_ref（比"刚够用"最多少吹 25%）
# P-2（2026-09-29）：上沿 1.25 → 1.10 —— ⚠️ **已实测证明不行，2026-09-30 改回 1.25**
# [详注-BEGIN]（生成简版时整段删除）
#   判决（1a21ef2c，160 轮）：B2 冷 3.5%→3.5%（毫无改善）、热 1.9%→**4.0%（翻倍）**、
#     不适 5.4%→**7.6%** ⇒ 净负面。教训：压上沿会让策略失去"负荷尖峰时补吹"的能力
#     （热侧立刻付代价），而冷侧并不来自 mult 的上侧摆动 —— 上侧收紧没治到病 ✗
# [详注-END]
COOL_LOAD_MAX_FRAC = 1.25  # a=1 ⇒ 1.25×a_ref（比"刚够用"最多多吹 25%，用来提前预冷）
# ---- P-6′(i)（2026-09-30）：把"a_ref 正好是 0"与"a_ref 读不到"分开处理 ----
#   事故（7c7ae2b2 trace 逐组分解，脚本 _q_b2cold.py + _q_fallback.py）：B2 低温步 99 步里
# [详注-BEGIN]（生成简版时整段删除）
#     **91 步（91.9%）**的实际动作 = **0.05 + 0.38×a**（回退映射的公式，逐位吻合）——
#     因为 `_use_load = _aref > 0.0` 把"本步理想负荷恰好为 0（**合法**：不需要制冷）"与
#     "取不到（异常/越界）"混为一谈 ⇒ 前者也走了回退 ⇒ **无负荷步上白吹 0.226 开度**、
#     室温被压到 KPI 冷线之外 ⇒ B2 低温 6.2% / 成本 1.045 的共同来源
#   做法：a_ref 合法（含 0）⇒ 一律走 P-1 倍率式；a_ref=0 时给一个极小的自由量
#     （NOLOAD_MAX×a，a=0.5 ⇒ 0.04）：既消除"无负荷白吹"，又保留"必要时补救"的能力
#     （不给 0 是防止在 a_ref=0 的步上彻底失去制冷手段）；取不到 ⇒ 才回退旧映射
#     全楼同一常量、同一公式，无按楼参数 ✓
# [详注-END]
COOL_LOAD_NOLOAD_MAX = 0.08  # a_ref 正好为 0 时：真实施加 = 0.08×a（a=0.5 时约 0.04）


# -----------------------------------------------------------------------------
# Step 1（2026-09-29）：动作换算不再**按楼栋各用一套**，三栋共用同一条映射
# [详注-BEGIN]（生成简版时整段删除）
# -----------------------------------------------------------------------------
# 原则（用户提出）：**学习本身不应该有针对单栋建筑的规则。** 手写的 {楼号: 值} 表等于把
#   "哪栋该吹多少"的人类先验硬编码进环境 —— 策略无从学到它、也无法迁移到别的楼；而且一旦
#   某栋表现不好，只会诱使我们去改表（C′-4 {1:0.14}、floor {1:0.05}、span {1:0.40} 三次
#   干预都是这么来的，其中前两次已被实测证伪 ✗）
# 做法：两张按楼查表 ⇒ 两个**全局标量**，三栋一视同仁：
#       applied = COOL_REMAP_FLOOR + (1 − COOL_REMAP_FLOOR) × COOL_REMAP_SPAN × a
#   当前 floor=0.05、span=0.40 ⇒ applied = 0.05 + 0.38·a ∈ [0.05, 0.43]（B1/B2/B3 完全相同）
# 为什么这仍属"标定"而非"规则"：
#   · 动作的物理含义是"额定功率的百分比"，而三栋的有用开度区间都落在 [0, ~0.45]
#     （实测：B1 中立 0.15、B2 理想负荷等效 0.12~0.19、B3≈0.20；探针：eff=0.30 已 dT=−4.46°C）
#     ⇒ "把有用区间铺满 a∈[0,1]"是**对动作语义的一次性归一化**，与楼栋无关 ✓
#   · 附带把 tanh 分辨率统一提升约 2.5 倍（B2/B3 原先 applied=a，在 [0,1] 上有 3 倍冗余）
#   · floor 的唯一作用是防止策略漂到 a→0 的 tanh 饱和区自锁（历史实测：floor=0 + 纯缩放
#     会让 B1 在 R10 就锁死 98% 高温），它对三栋同样生效、不区分楼栋 ✓
# 楼栋差异从哪来：**从观测学**。P6-A 已把「负载率 cooling_demand/nominal_power」
#   「能力比值 nominal_power/max(nominal)」「楼栋 identity one-hot」放进观测 ——
#   策略有足够信息区分三栋，不需要（也不应该）由我们喂表 ✓
# 判据（与 f4328081 单变量对照）：B1 热 ≤6% / 冷 ≤8%（它失去了原先的"专属 span/floor"）；
#   B2 的 applied 均值应下移（现在 0.27，理想负荷等效 ≈0.19）；三栋行为应"像同一个控制器"。
# 回退：把两个标量改回按楼字典；或 COOL_SPAN_ENABLE=False + COOL_FLOOR_ENABLE=False。
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# P2 最终形态：applied = floor + (1−floor) × (span × a)
#   B1: floor=0.05, span=0.40 ⇒ applied ∈ [0.05, 0.43]
# -----------------------------------------------------------------------------
# 三次 10 轮冒烟给出的完整因果链（同一协议，只改这几项）：
#   配置                               floor  热罚强度   B1@R10(热/冷)
#   C′-4 全程下界(0.14+0.86a)           0.14     强      30.9 /  7.5
#   纯缩放 SPAN=0.30 + 旧强 a_need       0.00     强       2.2 / 32.9   ← a 顶格 → 过冷
#   纯缩放 SPAN=0.45 + 新弱 a_need       0.00     弱      98.0 /  0.0   ← 死锁
#   floor=0.08 + span=0.40              0.08     弱      b972fb6c 全程：B1 14.2%（热 1.6/冷 12.6）
#   ⇒ 一：floor=0 必死锁（两种 SPAN/a_need 组合都锁死）⇒ 必须"托举"；
#   ⇒ 二：floor ≈ 中立开度会**冻结** —— C′-4 的 0.14 ≈ 实测中立 0.15，贴到 floor 即最优，
#      于是策略的 a 贴在 0（cv 55%→9.4%）。所以 floor 必须**明显低于**中立值：
#      贴 0.05 时 applied=0.05 仍偏热 ⇒ 热罚继续把 a 往上推 ⇒ 策略不会停在 a=0；
#   ⇒ 三：热罚不能一味调弱（历史 P1/P5-2/P8-1 三次"降 a_need"都导致更不开冷）。
# 结果：策略的达标工作区 applied ∈ [0.15, 0.30] ⇒ a ∈ [0.26, 0.66]（tanh 梯度良好区）；
#   有效梯度 = (1−0.05)×0.40 × ∂a/∂z(a≈0.26) ≈ 0.38×0.40 ≈ 0.15，
#   对比 C′-4 的 0.86×0.0048 = 0.004，约 **37 倍**。
# -----------------------------------------------------------------------------
# P2A（2026-09-28）floor 0.08 → 0.05：依据 b972fb6c 的残余病灶
# -----------------------------------------------------------------------------
#   · 该运行（140 轮早停达标）B1 热侧已降到 1.6% —— 距 ±10% 达标线还有 8pp 余量，
#     而冷侧 12.6% 是唯一残余 ⇒ 有充分的"以热换冷"空间；
#   · 用 cooling_electricity_consumption/nominal_power 反推实际开度：eff p10=0.090 /
#     p50=0.170 / p90=0.260（cv 37%，控制权已恢复 ⇒ 机制本身工作正常）；
#   · 按 eff 分档看，B1 在 eff∈[0,0.127) 的 567 步（25.7%）里 dT 均值 −1.09、
#     冷<−2 占 22.0% —— 这些是"建筑本身已偏冷"的低负荷时段，策略想把冷关到 0
#     却被 floor 托住 ⇒ **floor 就是这些步的过冷源**；
#   · 物理上：floor 只抬高映射的下沿（a→0 时 applied 0.08→0.05），达标工作区
#     （applied≈0.15对应的 a 由 0.19 抬到 0.26）仍在梯度良好区 ⇒ 不引入死锁风险。
#   · 判据：B1 冷应下降、热应略升（仍 <10%）；若 B1 热 >10% 或冷未降 → 回 0.06，
#     或直接 COOL_FLOOR_ENABLE=False。
# 回退方法：COOL_FLOOR_ENABLE=False + COOL_SPAN_ENABLE=False（回到 applied = a）。
# -----------------------------------------------------------------------------
# [详注-END]


class ContextRLlibEnv(RLlibMultiAgentEnv):
    """P6-A：在 RLlibMultiAgentEnv 之上，为每个 agent 的观测追加 [负载率, 身份one-hot]。

    · 观测空间同步扩展（RLlib 会用 self.observation_space 建模型输入层）；
    · 负载率取「本楼」的实时 cooling_demand / nominal_power，按步刷新；
    · 身份 one-hot 固定不变，仅用于让策略知道"这是第几栋楼"。
    """

    # 初始化环境包装：记住每栋的 id 与额定制冷能力（换算成 0~1 的比值），并准备好"额外观测"开关 ✓
    def __init__(self, env_config):
        super().__init__(env_config)
        self._ctx_ids = list(getattr(self, '_agent_ids', None) or [])
        self._ctx_n_b = len(self._ctx_ids)
        # 每栋的额定制冷能力（nominal_power）→ 换算成 0~1 的比值（①，常量 ✓）
        _caps = []
        ce = self.env.unwrapped                      # 最内层 CityLearnEnv
        for b in getattr(ce, 'buildings', []) or []:
            _c = 0.0
            try:
                _c = float(getattr(getattr(b, 'cooling_device', None), 'nominal_power', 0.0) or 0.0)
            except (TypeError, ValueError):
                _c = 0.0
            _caps.append(_c)
        _mx = max(_caps) if _caps and max(_caps) > 1e-9 else 1.0
        self._ctx_cap_ratio = [min(max(c / _mx, 0.0), 1.0) for c in _caps]
        self._ctx_nominal = list(_caps)                        # 每栋额定电功率（Step2 用）
        self._ctx_buildings = list(getattr(ce, 'buildings', []) or [])
        # 新增维度数 = 能力比值(0/1 维) + 身份(n_b 维)
        n_extra = (1 if OBS_CONTEXT_CAPACITY else 0) + \
                  (self._ctx_n_b if OBS_CONTEXT_IDENTITY else 0) + \
                  (1 if OBS_CONTEXT_A_REF else 0)
        self._ctx_n_extra = n_extra
        if n_extra > 0:
            try:
                base_sp = dict(self.observation_space)
            except Exception:
                base_sp = {}
            if base_sp:
                self.observation_space = spaces.Dict({
                    k: spaces.Box(
                        low=np.concatenate([np.asarray(v.low, dtype=np.float32),
                                            np.zeros(n_extra, dtype=np.float32)]),
                        high=np.concatenate([np.asarray(v.high, dtype=np.float32),
                                             np.ones(n_extra, dtype=np.float32)]),
                        dtype=np.float32,
                    )
                    for k, v in base_sp.items()
                })
        # ---- C′-4：制冷动作下界（Step 1 起是**全局一个数**，见文件顶部 COOL_REMAP_FLOOR 处）----
        #   self._cool_dim[i]   = 第 i 个 agent 的动作向量里 'cooling_device' 的下标
        #   self._cool_floor[i] = 该楼制冷动作的下界（0 = 不做换算，原样使用）
        self._cool_dim = []
        self._cool_floor = []
        self._cool_span = []
        # ---- P-1（2026-09-29）：跟着负荷走的映射（"中间值"= 本步刚够用的 a_ref；见文件顶部说明）----
        self._cool_centered = bool(COOL_LOAD_CENTERED_ENABLE)
        self._cool_load_min_frac = float(COOL_LOAD_MIN_FRAC)
        self._cool_load_max_frac = float(COOL_LOAD_MAX_FRAC)
        self._cool_load_noload_max = float(COOL_LOAD_NOLOAD_MAX)
        try:
            _blist = list(getattr(ce, 'buildings', []) or [])
            for _i in range(self._ctx_n_b):
                _names = list(getattr(_blist[_i], 'active_actions', None) or []) \
                    if _i < len(_blist) else []
                self._cool_dim.append(_names.index('cooling_device')
                                      if 'cooling_device' in _names else None)
                # Step 1：全局一个数（不再按楼栋查表）⇒ 三栋拿到同一条映射
                _fl = float(COOL_REMAP_FLOOR) if COOL_FLOOR_ENABLE else 0.0
                self._cool_floor.append(min(max(_fl, 0.0), 0.99))
                # 动作缩放系数（1.0 = 不缩放）。用线性缩放把"中立开度"放到 a=0.5，
                #   也就是 tanh 梯度最大的地方（学得最快）—— 动机与实测见文件顶部 COOL_REMAP_SPAN 处。
                _sp = 1.0
                if COOL_SPAN_ENABLE:
                    try:
                        _sp = float(COOL_REMAP_SPAN)
                    except (TypeError, ValueError):
                        _sp = 1.0
                self._cool_span.append(min(max(_sp, 0.0), 1.0))
        except Exception:
            self._cool_dim = []
            self._cool_floor = []
            self._cool_span = []

    # ---- 拼接逻辑 ----------------------------------------------------------
    # 按开关把该栋的附加特征（制冷能力比 / 身份 one-hot / 刚够用开度 a_ref ✓）拼成一个数组 ✓
    def _ctx_extra(self, agent_id: str) -> np.ndarray:
        if self._ctx_n_extra <= 0:
            return np.zeros(0, dtype=np.float32)
        try:
            i = self._ctx_ids.index(agent_id)
        except ValueError:
            i = 0
        parts = []
        if OBS_CONTEXT_CAPACITY:
            cap = self._ctx_cap_ratio[i] if i < len(self._ctx_cap_ratio) else 1.0
            parts.append(np.array([cap], dtype=np.float32))
        if OBS_CONTEXT_IDENTITY:
            onehot = np.zeros(self._ctx_n_b, dtype=np.float32)
            if 0 <= i < self._ctx_n_b:
                onehot[i] = 1.0
            parts.append(onehot)
        if OBS_CONTEXT_A_REF:
            # Step2B：把「本步理想负荷所需开度」喂给策略（见文件顶部 OBS_CONTEXT_A_REF 注释）。
# [详注-BEGIN]（生成简版时整段删除）
            #   索引：本函数在 step **之后**调用 ⇒ 用 b.time_step（当前步）；
            #   奖励侧 tap 在 step **之前**调用、用 time_step+1 ⇒ 两者指向同一步，语义一致。
# [详注-END]
            _ref = 0.0
            try:
                _b = self._ctx_buildings[i] if i < len(self._ctx_buildings) else None
                if _b is not None:
                    _npw = self._ctx_nominal[i] if i < len(self._ctx_nominal) else 0.0
                    _ref = _ideal_a_ref(_b, _npw, int(getattr(_b, 'time_step', 0) or 0))
            except Exception:
                _ref = 0.0
            parts.append(np.array([_ref], dtype=np.float32))
        return np.concatenate(parts).astype(np.float32) if parts else np.zeros(0, np.float32)

    # 把额外信息拼进每栋的观测里（旧的 obs dict → 新的 obs dict ✓）✓
    def _ctx_augment(self, observations):
        if self._ctx_n_extra <= 0 or not isinstance(observations, dict):
            return observations
        out = {}
        for k, o in observations.items():
            try:
                base = np.asarray(o, dtype=np.float32)
                out[k] = np.concatenate([base, self._ctx_extra(k)]).astype(np.float32)
            except Exception:
                out[k] = o
        return out

    # 重置环境；返回前把额外信息拼进观测 ✓
    def reset(self, *, seed=None, options=None):
        obs, info = super().reset(seed=seed, options=options)
        return self._ctx_augment(obs), info

    # 这一步第 i 栋"刚好够用"的制冷开度 a_ref（与奖励用的是同一个函数 _ideal_a_ref ✓）
    def _cool_a_ref_now(self, i: int):
        # [详注-BEGIN]（生成简版时整段删除）
        # 这一步第 i 栋"刚好够用"的制冷开度 a_ref（与奖励用的是同一个函数 _ideal_a_ref ✓）
        #
        # P-1 用它当映射的中立点。**返回值语义（P-6′ 修）**：
        #   · float（含 0.0）= 有效值 —— **0 表示"本步理想负荷为 0，不需要制冷"**，
        #     这是合法结果，调用方必须按"负荷跟随"处理（给极小自由量），
        #     **不得**当成"取不到"而改进回退映射；
        #   · None = 取不到（索引越界/异常）—— 只有这种情况才退回旧的 floor+span 映射。
        # 旧版把两者都返回 0.0，导致无负荷步上白吹 0.05+0.38a（实测 0.226）⇒ B2 深过冷。
        # idx = time_step + 1（step 尚未推进），与 pass_actions_to_reward 喂奖励的算法一致。
        #
        # [详注-END]
        try:
            _bl = getattr(self, '_ctx_buildings', None) or []
            if not (0 <= i < len(_bl)):
                return None
            _b = _bl[i]
            _npw = float(getattr(getattr(_b, 'cooling_device', None),
                                 'nominal_power', 0.0) or 0.0)
            _idx = int(getattr(_b, 'time_step', 0) or 0) + 1
            return float(_ideal_a_ref(_b, _npw, _idx))
        except Exception:
            return None

    # 把制冷动作换算成真实施加的开度；按开关三选一（见文件顶部对应常量的注释）： ✓
    def _cool_action_apply(self, action):
        # [详注-BEGIN]（生成简版时整段删除）
        # 把制冷动作换算成真实施加的开度；按开关三选一（见文件顶部对应常量的注释）： ✓
        #
        #   · P-1 负荷跟随（默认开，COOL_LOAD_CENTERED_ENABLE）：
        #       applied = a_ref × ( MIN_FRAC + (MAX_FRAC − MIN_FRAC) × a )
        #       —— 中立点 = **本步负荷所需开度**；a=0.5 ⇒ 倍率 1.0 ⇒ 恒等跟随（= 无控制）。
        #          上下界都是「负荷相对」（a=0 仍有 MIN_FRAC×a_ref）⇒ 不会关冷自锁。
        #   · P2 缩放（P-1 关闭时生效）：applied = span × a
        #       —— 中立点固定，实测比负荷贵 25%（B2 因此被无控制支配），由 P-1 取代。
        #   · C′-4 下界（默认关）：applied = floor + (1−floor)×a
        #       —— 抬下界防"关冷自锁"，但把中立点落在 a=0（饱和区）⇒ 策略调不动。
        #
        # 必须在 super().step() **之前**执行 —— 奖励的动作注入（install_action_hook
        # 包装的是基类 step）在 super().step() 内部读动作，所以它读到的将是"已施加"
        # 的动作，与建筑实际执行的一致。
        #
        # [详注-END]
        _fl_list = getattr(self, '_cool_floor', None) or []
        _sp_list = getattr(self, '_cool_span', None) or []
        _centered = bool(getattr(self, '_cool_centered', False))
        _has_floor = bool(COOL_FLOOR_ENABLE and any(_fl_list))
        _has_span = bool(COOL_SPAN_ENABLE
                         and any(abs(float(v) - 1.0) > 1e-9 for v in _sp_list))
        if ((not _centered and not _has_floor and not _has_span)
                or not isinstance(action, dict)):
            return action
        # 课程式衰减系数（仅 C′-4 下界用）—— 现读模块级变量，不做缓存
        _scale = float(min(max(float(COOL_FLOOR_SCALE), 0.0), 1.0))
        _dim_list = getattr(self, '_cool_dim', None) or []
        out = {}
        for _aid, _vec in action.items():
            try:
                _i = self._ctx_ids.index(_aid)
            except ValueError:
                _i = -1
            _dim = _dim_list[_i] if 0 <= _i < len(_dim_list) else None
            _fl = (float(_fl_list[_i]) * _scale
                   if (_has_floor and 0 <= _i < len(_fl_list)) else 0.0)
            _sp = (float(_sp_list[_i])
                   if (_has_span and 0 <= _i < len(_sp_list)) else 1.0)
            # P-1 / P-6′(i)：这一步的 a_ref —— **None = 读不到**（改走旧的兜底映射：按固定倍率算）；
            #   合法数值（含 0）⇒ 走负荷跟随式，不再把"合法的 0"误当成"取不到"
            _aref = self._cool_a_ref_now(_i) if (_centered and _i >= 0) else None
            _has_ref = bool(_centered and _aref is not None and np.isfinite(_aref))
            _use_load = bool(_has_ref and _aref > 0.0)
            if _dim is None or (not _has_ref and _fl <= 0.0 and abs(_sp - 1.0) <= 1e-9):
                out[_aid] = _vec
                continue
            try:
                _arr = np.array(_vec, dtype=np.float32, copy=True).reshape(-1)
                if _dim < _arr.size:
                    _a = min(max(float(_arr[_dim]), 0.0), 1.0)   # 冷却维原始范围就是 [0,1]
                    if _use_load:
                        # 真实施加的开度 = a_ref × 倍率；倍率随策略输出 a 在 [MIN_FRAC, MAX_FRAC] 之间线性变化
# [详注-BEGIN]（生成简版时整段删除）
                        #   a=0.5 ⇒ 倍率 1.00 ⇒ applied = a_ref（恒等跟随 = 无控制基线）
                        #   用**乘法**（而非 a_ref+span×(a−0.5)）是关键：后者在 a<0.5 时会把
                        #   applied 压到 0，配合"单边超吹罚"会滑进关冷自锁（已实测，见文件顶部）。
# [详注-END]
                        _lo = float(self._cool_load_min_frac)
                        _hi = float(self._cool_load_max_frac)
                        _a = _aref * (_lo + (_hi - _lo) * _a)
                    elif _has_ref:
                        # P-6′(i)：a_ref 可以**正好是 0**（这一步刚够用就是不用制冷 ✓）
# [详注-BEGIN]（生成简版时整段删除）
                        #   旧版走回退映射 ⇒ 白吹 0.05+0.38a（实测 0.226）⇒ 深过冷。
                        #   现在只给一个极小的自由量（a=0.5 ⇒ 0.04），保留补救能力但不浪费。
# [详注-END]
                        _a = float(self._cool_load_noload_max) * _a
                    else:
                        if _sp < 1.0:
                            _a = _sp * _a                        # 缩放 → 工作点 a≈0.5
                        if _fl > 0.0:
                            _a = _fl + (1.0 - _fl) * _a          # C′-4：抬下界（默认关）
                    _arr[_dim] = min(max(_a, 0.0), 1.0)
                out[_aid] = _arr
            except Exception:
                out[_aid] = _vec
        return out

    # 走一步：先把策略给的制冷动作换算成"真实施加的开度"，再让环境推进一步，最后把额外信息拼进新观测 ✓
    def step(self, action):
        action = self._cool_action_apply(action)
        obs, reward, terminated, truncated, info = super().step(action)
        return self._ctx_augment(obs), reward, terminated, truncated, info




# P1：按已完成轮数更新冷却下界的衰减系数（模块级，供 ContextRLlibEnv 读取） ✓
def update_cool_floor_scale(epochs_done: int) -> float:
    # [详注-BEGIN]（生成简版时整段删除）
    # P1：按已完成轮数更新冷却下界的衰减系数（模块级，供 ContextRLlibEnv 读取）。
    #
    #     scale = max(0, 1 − epochs_done / COOL_FLOOR_UNTIL)
    #
    # 前 COOL_FLOOR_UNTIL 轮线性引导（治 B1 的 tanh 死锁），之后归零 ⇒ applied = a。
    # 动机与实测证据见 COOL_FLOOR_ENABLE 处注释。
    # 因为 env_runners=0（环境跑在本进程），改模块级变量即可让所有环境即时读到新值。
    #
    # [详注-END]
    global COOL_FLOOR_SCALE
    try:
        until = float(COOL_FLOOR_UNTIL)
        s = 1.0 if until <= 0 else max(0.0, 1.0 - float(epochs_done) / until)
    except Exception:
        s = 1.0
    COOL_FLOOR_SCALE = float(min(max(s, 0.0), 1.0))
    return COOL_FLOOR_SCALE


# 当前冷却下界衰减系数（∈[0,1]）。C′-4 下界按它缩放；`COOL_FLOOR_UNTIL=0` 时恒为 1.0 ✓
def get_cool_floor_scale() -> float:
    # [详注-BEGIN]（生成简版时整段删除）
    # 当前冷却下界衰减系数（∈[0,1]）。C′-4 下界按它缩放；`COOL_FLOOR_UNTIL=0` 时恒为 1.0 ✓
    # [详注-END]
    return float(min(max(float(COOL_FLOOR_SCALE), 0.0), 1.0))


# 写入冷却下界衰减系数（训练循环每轮 / 评估前按 best_meta 恢复时调用）✓
def set_cool_floor_scale(value) -> float:
    # [详注-BEGIN]（生成简版时整段删除）
    # 写入冷却下界衰减系数（训练循环每轮 / 评估前按 best_meta 恢复时调用）✓
    # [详注-END]
    global COOL_FLOOR_SCALE
    COOL_FLOOR_SCALE = float(min(max(float(value), 0.0), 1.0))
    return COOL_FLOOR_SCALE






# 训练/评估/中期评估三处统一使用的环境类（RLlib 的 .environment() 也接受类对象）
_AGENT_ENV_CLS = ContextRLlibEnv if OBS_CONTEXT_ENABLE else RLlibMultiAgentEnv


# ---- _make_agent_env / _AGENT_ENV_CLS（2026-10-02 自入口脚本搬来）----


# 按开关选择环境类：P6-A 开启时用含楼栋上下文的子类 ✓
def _make_agent_env(env_config):
    # [详注-BEGIN]（生成简版时整段删除）
    # 按开关选择环境类：P6-A 开启时用含楼栋上下文的子类。
    # [详注-END]
    cls = ContextRLlibEnv if OBS_CONTEXT_ENABLE else RLlibMultiAgentEnv
    return cls(env_config)


# 训练/评估/中期评估三处统一使用的环境类（RLlib 的 .environment() 也接受类对象）
_AGENT_ENV_CLS = ContextRLlibEnv if OBS_CONTEXT_ENABLE else RLlibMultiAgentEnv

# ============================================================================
# ==== 段：schema_patch（原 utils/schema_patch.py ✓）====
# [详注-BEGIN]（生成简版时整段删除）
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# schema.json 的**定位**与**观测口径改造**（2026-10-02 从 Multi-agent.py 抽出）。
#
# 训练 / 评估 / 中评探针三处的环境构建都经 `patch_schema_observations` ⇒ 观测口径天然一致 ✓。
#
# 设计约定：本模块**不读全局配置** ✗ —— 配置值（要打开哪些观测、`maximum_temperature_delta`
# 取多少）由调用方（`Multi-agent.py`）显式传入 ✓：
#
#     # 模块导入时装一次 monkeypatch（因为写在 schema 里会被 CityLearn 丢弃，见下）
#     _TEMP_DELTA_STATUS = install_temp_delta_override(TEMP_DELTA)
#
#     # 每次建环境前
#     schema_obj, schema_root = patch_schema_observations(schema, OBS_EXTRA_ACTIVE, TEMP_DELTA)
# [详注-END]


import json
from pathlib import Path


# 按数据集名定位 schema.json（CityLearn 缓存目录 / 包内 datasets）。找不到返回 None ✓
def resolve_schema_path(schema: str):
    # [详注-BEGIN]（生成简版时整段删除）
    # 按数据集名定位 schema.json（CityLearn 缓存目录 / 包内 datasets）。找不到返回 None。
    # [详注-END]
    roots = [
        Path.home() / 'AppData' / 'Local' / 'intelligent-environments-lab' / 'citylearn',
        Path.home() / '.citylearn',
    ]
    for root in roots:
        try:
            if Path(root).is_dir():
                hits = sorted(Path(root).glob(f'**/{schema}/schema.json'))
                if hits:
                    return hits[-1]
        except Exception:
            pass
    try:
        import citylearn
        cand = Path(citylearn.__file__).resolve().parent / 'datasets' / schema / 'schema.json'
        if cand.is_file():
            return cand
    except Exception:
        pass
    return None


# 按 P7-1 修改 schema；返回 (schema 对象, root_directory 或 None) ✓
def patch_schema_observations(schema, extra_active, temp_delta):
    # [详注-BEGIN]（生成简版时整段删除）
    # 按 P7-1 修改 schema；返回 (schema 对象, root_directory 或 None)。
    #
    # · 传进来的本身是 dict（如 build_probe_env 的中期评估窗口）→ 原地改，root 返回 None；
    # · 传的是数据集名 → 用 resolve_schema_path 定位 schema.json，改完返回其父目录作 root。
    # 定位不到 schema 时原样返回（退回旧行为，不报错）。
    #
    # 参数
    # ----
    # extra_active : 要强制 `active: True` 的观测名（数据集把它们显式关掉了 ✗，而 CityLearn 默认是开的）
    # temp_delta   : 每栋 `maximum_temperature_delta`（None/<=0 = 不改）；它只影响温度类观测的
    #                归一化上下限（不参与奖励/KPI ✓），详见 utils/schema_patch 说明与 DECISIONS.md §14
    #
    # [详注-END]
    if isinstance(schema, dict):
        data, root = schema, None
    else:
        path = resolve_schema_path(schema)
        if path is None:
            return schema, None
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
        except Exception:
            return schema, None
        root = path.parent
    try:
        obs = data.setdefault('observations', {})
        for key in (extra_active or ()):
            item = obs.get(key)
            if not isinstance(item, dict):
                item = {}
            item['active'] = True
            item.setdefault('shared_in_central_agent', False)
            obs[key] = item
        if temp_delta and float(temp_delta) > 0.0:
            bl = data.get('buildings')
            items = bl.values() if isinstance(bl, dict) else (bl or [])
            for b in items:
                if isinstance(b, dict):
                    b['maximum_temperature_delta'] = float(temp_delta)
    except Exception:
        pass
    return data, root


# 把 Building.maximum_temperature_delta 强制成 `temp_delta`（P7-1）。返回状态字符串 ✓
def install_temp_delta_override(temp_delta):
    # [详注-BEGIN]（生成简版时整段删除）
    # 把 Building.maximum_temperature_delta 强制成 `temp_delta`（P7-1）。返回状态字符串。
    #
    # 为什么必须 monkeypatch：CityLearn 的 Environment._load_building() 只把 schema 里
    # **白名单字段**透传给 Building（见 citylearn/citylearn.py:2347-2364 的构造调用），
    # 写在 building 字典里的 maximum_temperature_delta 会被静默丢弃 ——
    # 实测（_smoke_test_p7.py 首轮）写 3.0 后建出来的楼仍是 20.0，观测维度虽然 +3
    # 但偏差观测的归一化范围仍是 ±20（分辨率 0.025/°C，等于 P7-1 只生效了一半）。
    #
    # 该属性在 CityLearn 里只被 estimate_observation_space() 用来定
    # 「室温 / 制冷偏差 / 制热偏差」三类观测的归一化上下限，因此在这里统一改掉即可。
    # 幂等：重复调用不会叠加。
    #
    # [详注-END]
    if not (temp_delta and float(temp_delta) > 0.0):
        return 'skipped(temp_delta off)'
    try:
        import citylearn.building as _clb
    except Exception as exc:
        return f'import failed: {exc}'
    prop = _clb.Building.maximum_temperature_delta
    if getattr(_clb.Building, '_temp_delta_patched', False):
        return 'already'
    fget_orig, fset_orig = prop.fget, prop.fset

    # 读 Building.maximum_temperature_delta；若已强制指定 temp_delta 就直接返回它 ✓
    def _get(self):
        val = temp_delta
        if val and float(val) > 0.0:
            return float(val)
        return fget_orig(self)

    # 写 Building.maximum_temperature_delta；若已强制指定 temp_delta 则写 temp_delta ✓
    def _set(self, value):
        fset_orig(self, temp_delta if (temp_delta and float(temp_delta) > 0.0) else value)

    _clb.Building.maximum_temperature_delta = property(
        _get, _set, prop.fdel, prop.__doc__
    )
    _clb.Building._temp_delta_patched = True
    return 'installed'

# ============================================================================
# ==== 段：env_config（原 utils/env_config.py ✓）====
# [详注-BEGIN]（生成简版时整段删除）
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# 环境配置构建（schema → CityLearn env_kwargs），Multi-agent 三个入口共用一份。
# =====================================================================================
#
# `build_env_config()` 做四件事：① 调 `patch_schema_observations` 打观测补丁（带本模块的
# `OBS_EXTRA_ACTIVE` / `TEMP_DELTA` 两个配置）；② 组装 `env_kwargs`（schema / 回合长度 /
# root_directory）；③ 按 `USE_CUSTOM_REWARD` 挂自定义奖励（配置见 `utils.reward_config`）；
# ④ 按需打开 render，并固定两个 wrapper（归一化 + 裁剪）。
#
# ⚠️ `episode_time_steps=None` 是**有语义的**：不传 ⇒ 交给 CityLearn 用数据集自带长度
#    （源码 citylearn.py:910）⇒ 未登记的 schema 不会被静默按硬编码值跑 ✗
#
# `_TEMP_DELTA_STATUS` 是**导入即执行**的 monkeypatch（写在 schema 里的
# `maximum_temperature_delta` 会被 CityLearn 静默丢弃 ✗ ⇒ 只能改 Building 属性 ✓）
# ⇒ 本模块一旦被 import，该补丁就生效（与原先在源文件顶部执行等价 ✓）
# [详注-END]


from citylearn.wrappers import ClippedObservationWrapper, NormalizedObservationWrapper

from utils.config import (
    CUSTOM_REWARD_KWARGS,
    _CUSTOM_REWARD_MODULE,
    USE_CUSTOM_REWARD,
)



# 注：原来这里的 `_KPI_READ_ERR_LOGGED` + `_log_kpi_read_err`（"只提示一次"的
# [详注-BEGIN]（生成简版时整段删除）
#   KPI 读取失败告警）已于 2026-10-02 抽到 runtime.py 的 `log_kpi_read_err()`。
#   抽出的实际收益：那份"只报一次"的状态原本**三个入口脚本各存一份**（文件被复制
#   成三份），现在是 Python 模块级状态 ⇒ 全进程唯一一份 ✓
#   行为与 `[中期评估] … 失败（后续不再重复）: 异常类型: 消息` 的日志格式**不变**，
#   历史排查经验继续适用 ✓ 调用方约定也不变：只有"读取过程抛异常"才调用 ✗


# mid-eval 三件套（read_building_series / run_mini_eval）的实现已抽到
#   utils/train.py（2026-10-02）⇒ 评估脚本里不再内联训练侧探针代码 ✓


# run_nocontrol_cost_ref 的实现已抽到 utils/train.py（训练期 best-ckpt 成本项用）✓


# run_mid_eval（多窗口合并）同样在 utils/train.py ✓


# =============================================================================
# 观测改造（P7-1）：让策略"看得见"离设定点多远
# -----------------------------------------------------------------------------
# 问题（2685a524 / da6627c7 两次记录共同的病根）：
#   1) 数据集 schema.json 把最能用的观测显式关掉了（CityLearn 默认是开的，
#      见 citylearn/misc/settings.yaml 183-192 行）：
#        indoor_dry_bulb_temperature_cooling_delta = T − 制冷设定点 → active: false
#        indoor_dry_bulb_temperature_heating_delta、comfort_band   → active: false
#   2) 温度类观测被 maximum_temperature_delta=20 的缓冲撑开：偏差观测归一化范围
#      是 [−20,+20]，室温是 [min−20, max+20]；而本数据集室温跨度极小
#      （实测全季：B1 7.2°C、B2 3.8°C、B3 仅 1.6°C），于是
#      1°C 只值 0.021~0.025 的输入变化（B3 整季变化只占输入的 4%）。
#      而"该开 0.10 还是 0.25 开度"要靠亚度级判断 → 策略学不出状态依赖：
#      动作与需求弱相关甚至反相关（B1 corr(act,T−SP) = −0.21，逐小时内 −0.35）、
#      带内白吹关不掉（B2 有 41.8% 步处于 T<SP、act 均值 0.305，每步白丢约 −13.7 分）。
# 改法：打开偏差观测 + 把 maximum_temperature_delta 收到 3
#      （偏差分辨率 0.025 → 0.167/°C，6.7 倍；室温分辨率 0.024 → 0.13）。
# 影响面：奖励不受影响（奖励读的是未归一化的原始观测，归一化只在 wrapper 层）。
#        但观测空间变了 → **旧模型不可复用，必须重训**。
# 退回旧行为：OBS_EXTRA_ACTIVE = ()、TEMP_DELTA = None。
# =============================================================================
# [详注-END]
OBS_EXTRA_ACTIVE = (
    'indoor_dry_bulb_temperature_cooling_delta',   # T − 制冷设定点（策略最缺的信号）
    'indoor_dry_bulb_temperature_heating_delta',  # T − 制热设定点（算法与制冷侧一样，只是换成制热设定点）
    'comfort_band',                                # 舒适带（本数据集恒为 2.0）
)
TEMP_DELTA = 20.0    # 每栋 maximum_temperature_delta（CityLearn 默认值）；None/<=0 = 不改
# P9-1′（归因步骤）：3.0 → 20.0（退回默认）。依据两次运行对照：
# [详注-BEGIN]（生成简版时整段删除）
#   f4693695（delta 观测开启、MTD 未生效=20）→ B1 2.7%/24.6%、B2 0.8%/10.5%、B3 0.4%/0.5%
#   75a95510（delta 观测开启、MTD=3.0）      → B1 14.2%/1.1%、B2 0.8%/45.3%、B3 1.3%/0.3%
# 两处同时改了（MTD + P8-1 需求），但机理上 MTD 更可疑：它把温度/偏差观测的输入幅度放大
# 3.5~6.7 倍，网络对"温度高"的响应被同步放大 —— 实测 B2 午后动作从 0.42~0.51 升到 0.49~0.62、
# 温度从 24.1 被压到 23.3，正是"放大 T 响应 → 午后过度制冷"的形态；
# 而 B2 几乎不过热（高温 0.7%），热侧需求并不驱动它的动作，需求下调不该让动作升高。
# 因此本次只回退 MTD（保留 delta 观测这个明确有效的部分），用一次运行做归因。


# 温度观测幅度：**激活 monkeypatch**（实现在 utils/env.py，2026-10-02 抽出 ✓）
#   ⚠️ 为什么必须 monkeypatch：写在 schema 里的 maximum_temperature_delta 会被 CityLearn
#      静默丢弃 ✗（只透传白名单字段）⇒ 只能改 Building 的属性 ✓
#   该属性只影响「室温 / 制冷偏差 / 制热偏差」三类观测的归一化上下限（不参与奖励/KPI ✓）
# [详注-END]
_TEMP_DELTA_STATUS = install_temp_delta_override(TEMP_DELTA)




# 注：给观测加特征 / 改特征这件事，已抽成 utils/schema_patch.patch_schema_observations() ✓
# [详注-BEGIN]（生成简版时整段删除）
#   （2026-10-02）—— 本文件只在建环境时调用它，并显式传入下面两个配置项 ✓
#   配置见：OBS_EXTRA_ACTIVE / TEMP_DELTA（本文件顶部）
# [详注-END]


# 组装 CityLearn 环境配置（数据集 / 步数 / 输出目录 / 渲染 / 用哪个奖励 ✓）—— 训练与评估都走它 ✓
def build_env_config(
    schema: str,
    episode_time_steps,          # int 或 None（None ⇒ 用数据集自带长度，见下）
    output_dir: Path,
    enable_render: bool,
    record_details: bool = True,
) -> dict:
    # 打开"偏差类"观测 + 把温度缩放的宽度改窄（细节见上方说明）
    schema_obj, schema_root = patch_schema_observations(schema, OBS_EXTRA_ACTIVE, TEMP_DELTA)
    env_kwargs = {
        'schema': schema_obj,
    }
    # episode_time_steps：**给了就用给定值；给 None 就不传**，交给 CityLearn 用数据集自带长度
# [详注-BEGIN]（生成简版时整段删除）
    #   （源码 citylearn.py:910：`… = 数据集长度 if episode_time_steps is None else <传入值>`）
    #   ⇒ 未登记的 schema 不会被静默按某个硬编码值跑 ✗（那会截断回合、或越界读数据）
# [详注-END]
    if episode_time_steps is not None:
        env_kwargs['episode_time_steps'] = int(episode_time_steps)
    if schema_root is not None:
        env_kwargs['root_directory'] = str(schema_root)
    if USE_CUSTOM_REWARD:
        # 用本文件的 CustomComfortReward 覆盖 schema.json 里的默认奖励（训练/评估同时生效）。
        # 注意：CityLearn 按「模块.类名」字符串 + reward_function_kwargs 实例化。
        env_kwargs['reward_function'] = f'{_CUSTOM_REWARD_MODULE}.CustomComfortReward'
        env_kwargs['reward_function_kwargs'] = dict(CUSTOM_REWARD_KWARGS, record_details=bool(record_details))
    if enable_render:
        env_kwargs.update({
            'render_mode': 'end',
            'render_directory': output_dir,
            'render_session_name': '.',
        })
    return {
        'env_kwargs': env_kwargs,
        'wrappers': [NormalizedObservationWrapper, ClippedObservationWrapper],
    }

# ============================================================================
# ==== 段：probe_env（原 utils/probe_env.py ✓）====
# [详注-BEGIN]（生成简版时整段删除）
# ============================================================================
# 原模块文档串（原样保留 ✓）：
# 中期评估「探针环境」工厂（Multi-agent 训练侧共用一份）。
# =====================================================================================
#
# `build_probe_env(schema, output_dir, steps, where)` 另建一个独立 CityLearn 环境当探针：
# 把 schema.json 读成 dict、改 `simulation_start/end_time_step`、补 `root_directory`
# （否则 CityLearn 找不到 CSV），再交给 `build_env_config` ✓
#
# 窗口：`head` = 数据集前 steps 步（最凉段）/ `tail` = 末 steps 步（最热段）/
# `full` = 整段 episode（start=0）。返回 `(env, 实际步数, 窗口说明)` ✓
# 注意底层数组长度 = `episode_time_steps`，步进会多读一格 ⇒ 实际只跑 `n-1` 步 ✓
#
# ⚠️ 只有 start=0 的窗口（`head`/`full`）与**正式评估的初始条件一致**；`start≠0` 时
# CityLearn 用 CSV 静态室温 + 全新 LSTM 隐状态起步 ⇒ 与"全 episode 跑到该步的真实状态"
# 不同 ⇒ **tail 读数不可信**，不要再依赖它做定量判断 ✗（这就是 `MID_EVAL_WINDOWS`
# 只留 `('full',)` 的原因 ✓）
#
# ⚠️ 本模块**只被训练侧使用**：`Multi-agent-eval.py` 里没有调用点（只保留定义 ✓）。
# [详注-END]

from utils.base import log_console






# 构建中期评估用的"试跑"环境。返回 (env, 跑多少步, 这段怎么取) ✓
def build_probe_env(schema: str, output_dir: Path, steps: int, where: str):
    # [详注-BEGIN]（生成简版时整段删除）
    # 构建中期评估用的"试跑"环境。返回 (env, 跑多少步, 这段怎么取) ✓
    #
    # where='head' → 数据集前 steps 步（季节最凉段）；'tail' → 末 steps 步（最热段）；
    #       'full' → 整段 episode（start=0, end=full_end），用于 P0 的全口径 KPI 评估。
    # 实现方式：把 schema.json 读成 dict，改 simulation_start/end_time_step 并补
    # root_directory（否则 CityLearn 找不到 CSV）。定位不到 schema 时回退成前 steps 步。
    # 注意：底层数组长度 = episode_time_steps，步进会多读一格，所以实际只跑 n-1 步。
    #
    # ⚠️ 只有 start=0 的窗口（'head'/'full'）与正式评估的初始条件是**一致**的：
    #   start≠0 时 CityLearn 会用 CSV 里的静态室温 + 全新 LSTM 隐状态起步，
    #   与"全 episode 跑到该步时的真实状态"不同 —— 这正是 tail 窗口读数不可信的原因
    #   （那套独立整段探针已于 2026-10-08 删除 ✓）。不要再依赖 'tail' 做定量判断。
    #
    # [详注-END]
    steps = max(4, int(steps))
    path = resolve_schema_path(schema)
    if path is not None:
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            full_end = int(data.get('simulation_end_time_step') or (steps - 1))
            if where == 'tail':
                end = full_end
                start = max(0, end - steps + 1)
            elif where == 'full':
                start = 0
                end = full_end
            else:
                start = 0
                end = min(full_end, steps - 1)
            data['simulation_start_time_step'] = int(start)
            data['simulation_end_time_step'] = int(end)
            data['root_directory'] = str(Path(path).parent)
            n = int(end) - int(start) + 1
            cfg = build_env_config(data, n, output_dir, enable_render=False, record_details=False)
            return (
                _AGENT_ENV_CLS(cfg),
                max(1, n - 1),
                f'{where}[{start}-{end}] {n - 1}步',
            )
        except Exception as exc:
            log_console(f'[中期评估] {where} 窗口构建失败，回退到前 {steps} 步: {exc}')
    # 定位不到 schema.json（罕见）：不猜步数 ✓
# [详注-BEGIN]（生成简版时整段删除）
    #   · 'full'  ⇒ 传 None，让 CityLearn 用数据集自带长度，再把实际值读回来 ✓
    #   · 其它窗口 ⇒ 就按请求的 steps 跑（截断，日志里标"(回退)" ✓）
# [详注-END]
    if where == 'full':
        cfg = build_env_config(schema, None, output_dir, enable_render=False, record_details=False)
        penv = _AGENT_ENV_CLS(cfg)
        n_steps = int(getattr(penv.env.unwrapped, 'episode_time_steps', 0) or 0) or steps
        return penv, max(1, n_steps - 1), f'{where}(回退·数据集自带) {max(1, n_steps - 1)}步'
    cfg = build_env_config(schema, int(steps), output_dir, enable_render=False, record_details=False)
    return _AGENT_ENV_CLS(cfg), max(1, int(steps) - 1), f'{where}(回退) {int(steps) - 1}步'

# ============================================================================
# 原模块文档串（原样保留 ✓）：
# [详注-BEGIN]（生成简版时整段删除）
# 动作注入补丁：让奖励函数「看得见动作」（三个入口共用一份）。
# =============================================================
#
# 问题
# ----
# CityLearn 的 `reward.calculate(observations)` **只给观测、不给动作** ⇒ 自定义奖励里所有
# 依赖 act 的项（过热保底 / 过吹罚 / 过冷关冷 / 制冷电耗 / 电池项）都读不到 ⇒
# `∂R/∂act_cool = 0` ⇒ 策略"加大制冷也拿一样的分"（= DECISIONS §2「高温不制冷」的病根 ✗）
#
# 做法
# ----
# 包装 `RLlibMultiAgentEnv.step`：在「真正 step（内部会调 reward.calculate）」**之前**，把本步
# 各楼动作按**楼栋顺序**交给奖励函数（`note_pending_actions`），并顺带把制冷热容量、理想开度、
# 额定电功率与电池规格一起注入（奖励侧的 `a_need` 与电池项要用 ✓）。
#
#   · 只**读**动作、不改动作、不改返回值 ⇒ 仿真动力学与 KPI 完全不变 ✓
#   · 挂在**基类**上：子类 `ContextRLlibEnv` 的 `super().step()` 也会走到 ✓，
#     且 `OBS_CONTEXT_ENABLE=False`（环境直接用库里那个类）时同样生效 ✓
#   · 训练时 `env.step` 由 RLlib 内部调用 ⇒ 这里是**唯一**的公共拦截点 ✓（详见源文件的补丁注释块）
#
# 安装位置（2026-10-03 起 ✓）
# ---------------------------
# 由入口脚本在 `if __name__ == '__main__':` 的**第一行**调用 ⇒ 等价于"流程最开始"✓，
# 且早于任何环境构造 ✓（晚一步就会出现"奖励读不到动作 ⇒ 动作项静默为 0"✗✗）。
#
#   · 只 **import** 本模块（或入口脚本）而**不运行**的脚本 ⇒ 需自行调用一次 `install_action_hook()` ✓
#   · **Ray worker**（`--env-runners > 0`）不会 import 入口脚本 ⇒ **不在覆盖范围** ✗；
#     要覆盖它，应改由 **env 类模块**或**奖励模块**在导入期调用本函数 ✓
#     （当前 `NUM_ENV_RUNNERS = 0` 单进程采样 ⇒ 不受影响 ✓）
#
# 作用域（两个入口不同，都是**有意**的 ✓）
# ----------------------------------------
#   · 训练：动作项 = 奖励的**梯度来源**（主战场 ✓）
#   · 评估：不参与任何决策 ✗，只把奖励变成**可读的诊断账本** —— 决策推演的分项与实际执行值
#     （decision_trace.json ✓）、`[评估阶段]` 统计与"训练↔评估"对照（output.log ✓）
#
# ⚠️ 状态读取请用 `action_hook_status()` 函数 ✓ —— 不要 `from utils.action_hook import _STATUS`：
#    import 变量会把**当时的值**拷贝过来，装钩子之后再读仍是 'not_installed' ✗
# [详注-END]



from typing import Any


_STATUS = 'not_installed'
