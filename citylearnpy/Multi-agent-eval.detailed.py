# =============================================================================
# 【评估专用入口 eval】由 _gen_marl_split.py 从 Multi-agent.py 生成
# -----------------------------------------------------------------------------
# 与 Multi-agent.py 的区别只有两处：
#   1) **不训练**：直接从 Multi-agent-train.py 产出的 RLlib checkpoint 恢复模型
#      （Algorithm.from_checkpoint），随即跑评估仿真并输出 decision_trace.json 与 KPI；
#   2) 参数表裁掉了纯训练参数（--train-schema / --train-epochs /
#      --max-train-epochs / --min-train-epochs / --seed），
#      使 --help 只列真正生效的参数。
#   新增参数：--checkpoint（默认 <citylearnpy>\checkpoints\multi_agent_resume）
#   另注：评估期早停已于 2026-10-01 移除（因此本脚本没有 --no-early-stop 等参数）
#
# 关于文件里"用不到"的名字（训练侧专用，本脚本不调用）：**有意保留** —— 它们属于与
#   Multi-agent.py 共享的工具层，未调用的定义在 import 时不产生开销；保留才能保证
#   「改 Multi-agent.py → 重跑生成器」一次成功。
# =============================================================================
# 注：本文件是**详注版**（保留每一处「详注块」= 由 详注-BEGIN / 详注-END 包起来的整段说明 ✓），
#    平台与端到端冒烟实际运行的是 **Multi-agent-eval.py**（精简注释版 ✓），
#    它由本文件自动删掉「详注块」得到 ✓（**代码**逐字相同 ✓；差异只有注释 + 头部文档串 ✓）。
#    两份都由 `python _gen_marl_split.py` 一次生成 ⇒ **不要手改任何一份** ✗
"""
SAC 多智能体评估脚本（eval 专用入口）
====================================

【一句话】把训练好的模型（checkpoint）加载进来，在指定数据集上跑一遍完整仿真，
           再用 CityLearn 官方口径统计出 KPI；同时把每一步的细节写成
           decision_trace.json 供界面/论文查看。本脚本**只评估、不训练**。

【零基础读法（建议顺序）】
  1) 先读下面的「执行流程」——它写清了 9 个编号步（0~8）、每步「做什么」，以及**经过了哪些方法**；
  2) 再读「代码阅读地图」——每一步在文件里对应哪一段（按出现顺序排列）；
  3) 然后回正文跟着 `# ==== 步骤 N ====` 的分段注释读；
  4) 遇到陌生词（checkpoint / episode / KPI / 决策推演 / SAC）查「新手名词表」。

【执行流程：从敲命令到出 KPI（含"这一步经过了哪些方法"）】
  读法：每步先写"做什么"，再写「经过：」= **实际会被调用到的函数/方法**，
        括号里是它所在的文件（本文件 = Multi-agent.py；utils/xxx.py = 抽出去的工具层）。

  [导入时] 已经做了一件事（新手最容易忽略 ✗）
            · 把本目录加进 sys.path / PYTHONPATH（让 Ray worker 进程也能 import 奖励模块 ✓）

  步骤 0   流程开始：① 安装「动作注入」钩子（幂等 ✓）② 解析命令行
           经过：install_action_hook()（utils/env.py）
                → 包装 RLlibMultiAgentEnv.step：真 step 之前把动作喂给奖励（奖励才看得见 act ✓）
                parse_args()（本文件）→ argparse.ArgumentParser.parse_args()
           ⚠️ 钩子必须在**流程第一行**装：晚于任何环境构造 ⇒ 动作项会"静默为 0"✗
           ⚠️ 只 import 本文件而不运行的脚本，需自行调用 install_action_hook() ✓
              （Ray worker 不在覆盖范围 —— 想覆盖它要改由 env 类/奖励模块在导入期装 ✓）
  （本入口**不提供** --check-reward：奖励公式自检是**训练侧**开关，评估的 KPI 与奖励无关 ✗；
    需要自检时跑 `python Multi-agent.py --check-reward` ✓）
  步骤 1   评估准备段·一：① 从 checkpoint 读回**训练时保存的**奖励配置并写进
           CUSTOM_REWARD_KWARGS（reward_config.json ✓；找不到则用当前默认 + warning ✗）
           —— 评估不学习 ✗，但决策推演日志要记奖励分项 ⇒ 必须与训练**同一套**才有解释力 ✓
           ② 确定数据集与步数
          ⚠️ 读回必须排在建环境**之前**，否则会静默失效 ✗
  步骤 2   建「评估环境」
           经过：build_env_config()（utils/env.py）→ 内部装配 CityLearnEnv 的
                schema / 奖励函数 / 渲染开关
           enable_render=True  ⇒ 回合结束导出 exported_data_*.csv（界面"数据视图"）
           record_details=True ⇒ 奖励保留每步分项，决策推演里才有明细
           ⚠️ 2026-10-05 挪位：本步之后**紧接着执行"步骤 4"**（建环境 + reset ✗）——
              即源码里的步骤 4 在 eval 里被**提前**到这里 ✓（建环境只依赖配置、不依赖模型 ✓）
              ⇒ 读代码时"配置 → 建环境"是连着的，随后才轮到步骤 3（加载模型）✓
  步骤 3   评估准备段·二：加载模型（只加载，绝不训练）
           经过：load_multi_agent_checkpoint()（utils/train.py）
                → resolve_multi_agent_checkpoint_path()（找最新 checkpoint）
                → Algorithm.from_checkpoint()（RLlib：恢复策略网络；评估不用优化器/经验池）
  步骤 4   建 CityLearnEnv 并 reset 到第 0 步（⚠️ 在 eval 里被**提前**到步骤 2 之后执行 ✗）
           经过：_AGENT_ENV_CLS()（= ContextRLlibEnv（utils/env.py）或 RLlibMultiAgentEnv）
                → env.env.unwrapped（剥掉 RLlib + 归一化两层壳，拿到 CityLearn 原生 Environment）
                → env.reset()（各楼时序清零、指针拨回 t=0）
  步骤 5   取回合长度：完全由数据集决定（本 schema = 2208 步 ≈ 一整年逐小时）
           经过：读 citylearn_env.episode_time_steps 属性 → log_console()
  步骤 6   主循环（每步 5 个小动作）
           (a) 取动作：ordered_keys ← env._agent_ids
               经过：model.compute_single_action(obs, explore=False)（RLlib，贪心无噪声）
                    → unwrap_action()（utils/env.py：统一只取动作本体）
           (b) 环境步进
               经过：env.step(actions)（RLlibMultiAgentEnv.step）
                    → pass_actions_to_reward()（本文件；动作钩子：先把动作喂给奖励）
                    → CustomComfortReward.calculate()（custom_comfort_reward.py）
                    → CityLearn 动力学推进（更新各楼时序 ⇒ 返回下一步观测 + 奖励）
           (c) 记推演（先建记录器，再逐步追加）
               经过：build_decision_recorder()（utils/report.py ✓）→ describe_reward_function()（utils/config.py ✓）
                    → record_step_trace()（utils/report.py）
                    → collect_citylearn_step_rows()（utils/report.py）
                    → MarlDecisionTraceRecorder.record_step()（utils/report.py）
           (d) 落盘（每 DECISION_TRACE_EVERY 步一次 + 回合末一次）
               经过：decision_trace_path()（utils/report.py）
                    → MarlDecisionTraceRecorder.save()
           (e) 进度：log_console()（第 1 步 / 每 36 步 / 回合末）
  步骤 7   收尾
           7a 官方 KPI：citylearn_env.evaluate()（CityLearn）
                        → DataFrame.pivot().round(3).dropna()（pandas：长表→宽表）
                        → citylearn_env.export_final_kpis()（写 exported_kpis.csv）
           7b 奖励侧自检：CustomComfortReward.stats_summary() / kpi_summary()
                        （custom_comfort_reward.py，可与 7a 的 KPI 直接对照 ✓）
           7c 平台协议：print_kpis_for_java()（utils/report.py）→ sys.stdout.flush()
  步骤 8   结束（exit 0）

【代码阅读地图（按执行顺序，用名字定位最稳）】
  步骤 0  →  def parse_args()          （文件后段；只定义参数，不执行）
  步骤 1  →  `# ==== 步骤 1/8：把评估要用的东西解析成确定值`   （生成器注入的段落）
  步骤 1  →  内联段：从 checkpoint 的 sidecar 读回训练时的奖励口径（2026-10-08 内联 ✓，原名 _read_reward_config_from_checkpoint —— 该函数**已删除** ✓）
  步骤 2  →  同段里的 build_env_config(eval_schema, ..., enable_render=True, ...)
  步骤 4  →  紧随其后（eval 里**提前** ✗）：`# ==== 步骤 4/8：建环境实例 + reset` + `# ---- 【评估准备段·一·续】`
  步骤 3  →  `# ==== 步骤 3/8：加载 checkpoint 恢复策略网络` + load_multi_agent_checkpoint(ckpt_in)
  步骤 5  →  `# ==== 步骤 5/8：确定这个回合有多长`（紧跟 `# ---- 回合长度：完全由数据集决定`）
  步骤 6  →  `# ---- 主循环：直到回合自然结束（env.terminated）`
  步骤 7  →  `# ==== 步骤 7/8：收尾 —— 用 CityLearn 官方 evaluate 算 KPI 并导出` 与
             `# ==== 步骤 7b/8：把 KPI 按平台协议打到 stdout`
  辅助    →  describe_reward_function() / build_decision_recorder() / find_metric()
  辅助    →  pass_actions_to_reward() / install_action_hook()
             （把"RLlib 动作字典"喂给奖励函数，供奖励统计与决策推演使用）

【新手名词表（本文件只用这几个词）】
  · checkpoint（模型快照）：RLlib 把"学到的策略网络 + 优化器状态 + 计数器"存成的一组文件；
      评估只用到策略网络 ⇒ 加载后即可直接决策。
  · episode（回合）：一次从头跑到尾的完整仿真；这里 = 数据集的一整年逐小时序列。
  · step（步）：回合里的一小时：给一次动作、得一次奖励、进入下一小时。
  · agent（智能体）：这里一栋楼 = 一个 agent；多智能体 = 多栋楼各自出动作、互相影响
      （共享电网、共享电价、共享电池套利机会）。
  · 观测 observation：环境交给策略的输入向量（室温、电价、太阳辐照、电池 SOC 等）。
  · 动作 action：策略输出的控制量（制冷开度 / 制热开度 / 电池充放电），归一化到 0~1 或 -1~1。
  · 奖励 reward：训练时的引导分数（本项目自定义：舒适为主，另含电费/电池项）。
      注意：**奖励值不能当评价指标**（它含人为权重），评价一律看 KPI。
  · KPI：业务口径的最终指标（高温步占比 / 低温步占比 / 电费 / 碳排 …），
      一律取 CityLearn 官方 evaluate 的结果，保证与基线、历史运行可比。
  · 决策推演 decision_trace.json：逐步记录"看到了什么、做了什么、结果如何"，
      供模型优选界面与论文案例展示、排错使用。
  · schema（数据集）：CityLearn 的数据目录名，例如
      citylearn_challenge_2023_phase_2_online_evaluation_1。
  · SAC：一种强化学习算法（Soft Actor-Critic），本项目的学习器。

【本文件里"用不到的"名字（有意保留，不是漏删）】
  文件里还有一批**训练侧**常量与函数（TRAIN_* / MID_* / BEST_CKPT_* / run_mini_eval …），
  本脚本一次都不会调用它们。它们与 Multi-agent.py / -train.py **共享同一份源码**，
  保留它们才能让「改源文件 → 重跑生成器」永远一次成功（详见文件头横幅）✓

【可配置参数（只列评估相关；训练参数已裁剪）】
  --eval-schema    评估数据集
  --checkpoint     Multi-Agent SAC checkpoint 路径（Multi-agent-train.py 训练产出）
  （--trace-every 已移除（2026-10-05）：落盘间隔**固定**为 DECISION_TRACE_EVERY = 144 ✓）
  --no-trace       不采集 decision_trace.json（只影响日志，KPI 与仿真完全不变）
  （--check-reward 已裁剪：它服务训练侧，评估的 KPI 与奖励无关 ✗）
  （--bat-weight / --bat-loss / --cost-weight 也已裁剪：奖励口径一律从 checkpoint 的
    reward_config.json 读回训练时那份 ✓ ⇒ 评估现场改不了 ✗）
（另保留 --output-dir 供 Java 平台写 KPI）

【用法】
  python Multi-agent-eval.py -o D:/citylearn-demo/output/outkpis/任务ID
      --eval-schema citylearn_challenge_2023_phase_2_online_evaluation_1
      --checkpoint D:/citylearn-demo/citylearnpy/checkpoints/multi_agent_resume
      （要评估训练期选出的"最优快照"，把末段换成 .../multi_agent_resume_best）
"""

    # [详注-BEGIN]（生成简版时整段删除）
    # 注释约定：代码注释只写"当前口径"；历史 / 实测 / 回退统一放 DECISIONS.md ✓（详注原文见 MAINTENANCE.md 附录 A ✓）
# [详注-END]

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

# 日志工具,torch设置单线程
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

from utils.train import (
    find_metric,
    read_building_series,
    run_mid_eval,
    run_mini_eval,
    run_nocontrol_cost_ref,
    load_multi_agent_checkpoint,
    save_multi_agent_checkpoint,
    install_action_hook,
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
from custom_comfort_reward import CustomComfortReward, _cap_txt
    # [详注-BEGIN]（生成简版时整段删除）
    # 奖励自检实现已抽到 custom_comfort_reward（本文件只 import 实现 + 透传当前生效参数 ✓）；过期的 _clamp_temp_penalty 导入已删 ✗
    # [详注-END]
    # [详注-BEGIN]（生成简版时整段删除）
# 注（2026-10-03）：奖励公式自检（--check-reward / check_reward_equivalence）是**训练侧**开关 ——
#   它保证"训练目标"（自定义奖励）与"验收口径"（官方 KPI）不脱钩；而评估的 KPI **与奖励无关**
#   （CityLearn evaluate 独立计算）⇒ 评估入口已把它整组裁掉。需要自检时跑：
#       `python Multi-agent.py --check-reward`   （期望「温度项总体最大绝对差 = 0.000e+00」✓）
    # [详注-END]




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
    parser = argparse.ArgumentParser(description='SAC Multi-Agent 评估（从 checkpoint 恢复模型，只跑仿真出 KPI）')
    parser.add_argument('--output-dir', '-o', type=str, default=None,
                        help='把 KPI 与仿真数据导出到这个目录（Java 平台会传入任务目录）')
    parser.add_argument('--eval-schema', type=str, default=DEFAULT_EVAL_SCHEMA,
                        help=f'评估用数据集：CityLearn 数据目录名（默认 {DEFAULT_EVAL_SCHEMA}）')
    # [详注-BEGIN]（生成简版时整段删除）
    # `--trace-every` 已移除 ⇒ 落盘间隔固定为 DECISION_TRACE_EVERY=144 ✓；`--no-trace` 保留（"要不要采集"与"多久落一次"是两件事 ✓）
    # [详注-END]
    parser.add_argument('--checkpoint', type=str, default=None,
                        help=(f'要评估的模型：Multi-agent-train.py 训练产出的 RLlib checkpoint 路径，'f'默认 {DEFAULT_CHECKPOINT_DIR}'))
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


    # 确定输出目录
    # [详注-BEGIN]（生成简版时整段删除）
    # ③ 输出目录：-o 优先、否则 DEFAULT_OUTPUT_DIR；必须先建出来（它同时是 render_directory ⇒ 不建会在渲染阶段才报错 ✗）
    # [详注-END]
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # 确定输出目录
    # [详注-BEGIN]（生成简版时整段删除）
    # 本段替换掉源文件的「训练准备段」（那里会解析 train_schema、训练轮数区间、
    #   随机种子、奖励权重覆盖，并建 **训练** 环境 —— 评估脚本一律不需要）。
    # 确定数据集
    # [详注-END]
    # [详注-BEGIN]（生成简版时整段删除）
    # ④ 数据集：优先级 = 命令行（Java 平台注入）> 文件顶部默认值 DEFAULT_EVAL_SCHEMA
    #      一个写法挡一个坑：
    #        · `or ''`    ：参数没传时是 None ⇒ 先变 ''，否则下一句 None.strip() 直接报错 ✗
    #        · `.strip()` ：平台/配置里可能带**看不见**的首尾空格或换行 ⇒ 数据集名会"找不到" ✗
    #        · `or 默认值`：传了纯空白 ⇒ strip 后是空串 ⇒ 同样落回默认值 ✓（等价于没传 ✓）
    #      评估入口只解析 eval_schema ✓（train_schema 是训练侧的事，本入口的参数表里已裁掉 ✗）
    # [详注-END]
    eval_schema = (args.eval_schema or '').strip() or DEFAULT_EVAL_SCHEMA
    # 定义步数变量
    # [详注-BEGIN]（生成简版时整段删除）
    # ⑤ 步数：**一律不传**（= None）⇒ CityLearn 用数据集自带的长度
    #      （例如 local_evaluation 实测 2208 步 ≈ 一整年逐小时 ✓）。
    #      None 在这里是"自动"的**约定值**，不是"没有值" ✗ —— 别改成 0：
    #      0 步 = 空回合，什么都不跑，KPI 直接异常 ✗
    #      历史：曾经有一张"schema → 步数"表按名字硬编步数 ✗ ⇒ 换数据集就得改代码、
    #      写错还会静默截断回合 ⇒ 已彻底删除，改为"数据集自己说了算" ✓
    # [详注-END]
    eval_steps = None

    # 读回训练时的奖励配置
    # [详注-BEGIN]（生成简版时整段删除）
    # ⑥ 奖励口径来源：**训练时保存、评估时读回** ——
    #      · 为什么评估要读它：评估**不学习**（策略固定 ✓，KPI 也与奖励无关 ✗），但
    #        **决策推演日志要记奖励分项**（每步 reward、择时/损耗/电费各多少）⇒
    #        只有用"训练时那一套"奖励配置，这些数字才代表"策略当初被训练的目标" ✓；
    #        随便换一套来记，日志里的 reward 就只能当噪声 ✗（无法解释"它在优化什么"）
    #      · 推演里那些分项分别来自哪个权重（评估入口**不提供**这三个开关 ✗，
    #        但读日志/推演时必须知道它们是什么、干什么 —— 默认值以
    #        utils/config.py 的 CUSTOM_REWARD_KWARGS 为准 ✓）：
    #        · `bat_weight`（默认 **50**，唯一在用）= 电池「择时/套利」项
    #            r_arb = −w × max(0, price − p_ref) × (充电 − 有效放电)，p_ref = 电价滑动均值
    #            ⇒ 平价充电中性、高峰放电得奖励 ⇒ 利诱"便宜时充、贵时放" ✓（§6）
    #        · `bat_loss_weight`（默认 **0 = 关闭**）= 电池「损耗/账单」项
    #            r_loss = −w × price × 充电 ⇒ 本意压制过度充放，实测"罚充电 = 掐掉套利"✗ ⇒ 关着 ✓（§7）
    #        · `cost_weight`（默认 **0 = 关闭**）= 电费项（直接罚"从电网买电"）
    #            r_cost = −w × price × max(0, net)（**含电池**）⇒ 已证伪：成本↓但 B2 不适↑ ✗（§4）
    #        （另有第四个 `cool_cost_weight` = 2.0，本项目固定启用、**无命令行开关** ✓）
    #      · 训练侧每保存一次 checkpoint（定期 / best 快照 / 收尾）就在该目录写一份
    #        reward_config.json = **本次实际生效**的 CUSTOM_REWARD_KWARGS
    #        （含训练时的命令行覆盖 ✓，不是文件默认值 ✗）
    #      · 评估侧在这里读回来，**必须排在 build_env_config 之前** ✗ ——
    #        CUSTOM_REWARD_KWARGS 是在 build_env_config 里被拷贝进
    #        env_kwargs['reward_function_kwargs'] 的 ⇒ 建完环境再改这个 dict 对本次运行无效，
    #        只会表现为"日志说改了、结果一点没变"这种极难排查的静默失效 ✗
    #      · 为什么不让评估现场传参：奖励在训练时是"学习目标"，在评估时只是"打分记录项"
    #        （评估不学习、策略固定 ⇒ 改它**不影响 KPI** ✓，只改推演里的奖励分项 ✗）
    #        ⇒ 若允许现场改，推演里的 reward 就不再是"策略被训练时用的那个目标" ✗
    #        ⇒ 唯一正确的做法就是读回训练口径 ✓；想看别的口径请改训练侧开关并重训 ✓
    #      · 查找顺序：<checkpoint>/reward_config.json → <checkpoint>/*/reward_config.json
    #        （后者兼容"给的是父目录"的调用方式 ✓）
    #      · 找不到（历史断点 ✗）⇒ 返回 {} + 一行 warning ⇒ 用当前代码默认 ✗
    #      · 读取实现**已内联在下面**（2026-10-08 ✓：原先是 utils/config.py 里的一个函数，
    #        只此一处调用 ⇒ 内联，那个名字从全仓消失 ✓）⇒ main 里一眼可见全过程 ✓
    # [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    # ② 建评估环境——注意这里建的只是**配置**（env_kwargs，一个 dict ✓），
    #      真正 new 出环境在下面「步骤 4/8」✗ 别混。
    #      只建评估环境、不建训练环境：省掉一个 CityLearnEnv 的构建开销 ✓。
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

    # 构建评估环境
    # [详注-BEGIN]（生成简版时整段删除）
    # 2026-10-05 挪位（应"挪到 eval_env_config 构建之后"）：这 3 行原来在共享【评估段】的
    #   **开头**（= 源文件的「步骤 4/8」）⇒ 现在提前到**评估配置构建之后** ✓：
    #     读代码时"配置 → 建环境"是连着的 ✓，不必等加载完模型才建环境 ✓
    #     （建环境只依赖配置，不依赖 model ✓ —— model 直到步骤 6/8 主循环才被用到 ✓）。
    #   ⚠️ 两条约定（挪位的代价 ✗，改动本段时必须一起看）：
    #     · 共享【评估段】起点因此**下移**到「步骤 5/8」的第一行
    #       （`total_steps = ...` ✓，生成器用 MARK_EVAL_SIM_START 定位 ✓）。
    #       源文件里这 3 行**仍在原位**（一体化脚本是"训练完再建评估环境"：
    #       提前建会在 3h 训练期间白占一个 CityLearnEnv ✗ 无收益 ✗）
    #       ⇒ 源文件代码一行没动 ✓，只是本生成器不再把它们带进 eval ✓。
    #     · 编号会**跳过 4/8** ✗：共享段横幅（5/8、6/8、7/8、7b/8）保持与源文件
    #       **逐字一致** ✓ ⇒ 门禁 ⑥、文档、论文引用都不会因"eval 少了 4/8"而漂移 ✓
    #         （横幅是注释 ⇒ 门禁本就不比注释 ✓，这里只是刻意不制造差异 ✓）
    # [详注-END]
    env = _AGENT_ENV_CLS(eval_env_config)

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

    # 读取checkpoint，恢复模型
    # [详注-BEGIN]（生成简版时整段删除）
    # 本段替换掉源文件的「训练流程段」：建 SACConfig → build() → train() 循环
    #   → 训练期统计 → best 快照替换 model。评估脚本一律不需要这些。
    #
    # checkpoint 从哪来（优先级）：
    #   ① --checkpoint <路径>（Java 平台读配置页的 multi_agent_checkpoint 注入绝对路径）；
    #   ② 缺省 = DEFAULT_CHECKPOINT_DIR（citylearnpy/checkpoints/multi_agent_resume）。
    #   ⚠️ 训练脚本实际会产出两个目录：multi_agent_resume（最新一版）与
    #      multi_agent_resume_best（中期评估创新低时的最优快照）。想评估"最好的那一版"，
    #      必须显式传 --checkpoint .../multi_agent_resume_best
    #      —— 本脚本**不做** best 选择（那是训练脚本的职责）✓
    # ckpt_in 已在「步骤 1/8 准备段」解析过（那里还顺手读回了奖励口径 sidecar ✓）
    # [详注-END]
    log_console(f'评估模式：加载 Multi-Agent SAC checkpoint = {ckpt_in}')
    # 注（2026-10-02 整理）：load_multi_agent_checkpoint 已统一到**文件顶部依赖区** import
    # [详注-BEGIN]（生成简版时整段删除）
    #   （原先写在这里是"延迟 import"✗；该模块顶层依赖是本文件已有依赖的子集 ⇒ 提前无风险 ✓）。
    #   它内部会调 resolve_multi_agent_checkpoint_path() 找最新 checkpoint，与训练脚本共用同一套实现 ✓
    # [详注-END]

    # Algorithm.from_checkpoint：恢复策略网络（连带优化器/计数器等，评估只用权重）。
    # [详注-BEGIN]（生成简版时整段删除）
    #   它**不会**也不需要恢复训练环境 —— 评估环境已在**上面（准备段）**建好并 reset ✓
    #   （2026-10-05 挪位后：env / citylearn_env / observations 就在上方几步之内 ✓）
    # ⚠️ 那两行"评估专用说明"（本脚本不训练 / 奖励动作注入=…）已于 2026-10-06
    #   **移入** `load_multi_agent_checkpoint(..., eval_mode=True)` ✓
    #   （见 utils/train.py ✓）。为什么在函数里加开关、而不是无条件打印 ✗：
    #   那个函数还有另一个调用方 `multi_agent_runner_copy.py`（CHESCA-ResMARL ✓），
    #   这两句评估措辞**对它不成立** ✗✗ ⇒ 只有本入口显式传 True ✓
    # [详注-END]
    model = load_multi_agent_checkpoint(ckpt_in, log_console=log_console, eval_mode=True)

    # 确定step
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

    # 决策推演日志
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

    trace_on = not getattr(args, 'no_trace', False)

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
        # 固定各楼栋顺序
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
        # 给每栋楼取一次动作
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
        # 拿到新观测与奖励
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

        # 采集
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

        # 写入决策推演日志
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

        # 打印进度日志
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

    # 评估耗时
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

    # 打印奖励
    # [详注-BEGIN]（生成简版时整段删除）
    # 评估阶段统计：与「训练阶段」的同类统计对照，看动作类惩罚项在评估中的
    #   触发率/罚分是否明显不同（不同 ⇒ 说明评估时的状态分布或行为与训练期不一致，
    #   是排查"训练好但评估差"的第一手线索）。
    # [详注-END]
    rf_eval = getattr(citylearn_env, 'reward_function', None)
    if rf_eval is not None and hasattr(rf_eval, 'stats_summary'):
        log_console('[评估阶段] ' + rf_eval.stats_summary())
    if rf_eval is not None and hasattr(rf_eval, 'kpi_summary'):

        # [详注-BEGIN]（生成简版时整段删除）
        # 正式评估也打一份「奖励侧自算的 KPI 口径」，可与紧随其后导出的
        #   discomfort_hot/cold_proportion 直接对照 —— 这是判据口径可信度的最终验收。
        #   参照值：623a9e8d → B1 11.6%/1.2%、B2 0.6%/19.3%、B3 0.5%/0.2%
        #           b30240d4 → B1 19.7%/4.3%、B2 0.6%/20.9%、B3 0.4%/5.4%
        # [详注-END]
        log_console('[评估阶段] ' + rf_eval.kpi_summary())

    # 收尾，结果
    # [详注-BEGIN]（生成简版时整段删除）
    # evaluate()：CityLearn 官方 KPI 计算。它读的是各楼**当前已积累**的时序数组 ——
    #   现在没有早停了，执行到这里时各楼数组必然是完整的 2208 步 ⇒ KPI 恒为全程口径 ✓
    #   （原先"被早停在第 N 步"时这里是前 N 步的滚动 KPI，其中 cost/carbon/electricity
    #    等归一化项的分母仍是"全年基线"、与全程值不可比 ✗ —— 这个坑随早停一起消除）
    #   也正因为不再有"半途结束"，下面**不需要**任何"部分评估补落盘"的特殊处理 ✓
    # [详注-END]
    log_console('仿真完成，正在计算 KPI...')
    kpis = citylearn_env.evaluate()
    # 长表转宽表
    # [详注-BEGIN]（生成简版时整段删除）
    # 长表 → 宽表：行=cost_function（cost_total / discomfort_hot_proportion …），
    #   列=name（Building_1 / Building_2 / Building_3 / District），再四舍五入到 3 位。
    # [详注-END]
    kpis = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
    kpis = kpis.dropna(how='all')      # 全为空的行（该指标在本场景不适用）丢掉

    # 导出kpis
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

    # 参数给到java控制台
    # [详注-BEGIN]（生成简版时整段删除）
    # 格式：首行固定是字面量 'outputkpi'，其后每行 = 指标名 + 各列值（空格分隔，
    #   NaN 打成字符串 NaN）。Java 侧（BaseDataService.parseAndSaveKpis）就是靠
    #   'outputkpi' 这个标记从控制台输出里截出 KPI 片段入库的 ⇒ **这一行不能改** ✗
    # [详注-END]
    print_kpis_for_java(kpis)
    # 强制刷缓冲
    sys.stdout.flush()
