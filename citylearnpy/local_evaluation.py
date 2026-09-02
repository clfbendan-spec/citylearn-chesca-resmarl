"""
CHESCA 算法本地评估脚本
========================

【给初学者的整体说明】
本脚本属于「强化学习 / 智能控制」中的 **评估（evaluation）** 流程，不是训练。

可以把它想象成：
  - **环境 (Environment)**：模拟一个社区里多栋建筑的用电、储能、空调等（CityLearn）
  - **智能体 (Agent)**：你的控制算法 CHESCA，根据当前状态决定下一步怎么控制设备
  - **观测 (Observation)**：Agent 能「看到」的信息，如室外温度、电池电量、负荷等
  - **动作 (Action)**：Agent 能「做」的事，如给电池充电/放电、调节冷机等
  - **一步 (Step)**：Agent 给出动作 → 环境仿真前进 1 小时 → 返回新的观测
  - **回合 (Episode)**：从第 0 步跑到第 720 步（约 30 天 × 24 小时）算一整局
  - **KPI**：回合结束后的评价指标，如电费、碳排放、舒适度等（越小/越接近 1 通常越好）

流程概览：
  1. 创建 CityLearn 环境（并开启 render，导出时序 CSV 供前端图表使用）
  2. 加载 SubmissionAgent（CHESCA 控制策略）
  3. 循环：观测 → 预测动作 → env.step → 直到 episode 结束
  4. 计算并导出 KPI（必须在 reset 之前，否则指标会被清空）

运行目录：citylearnpy/（CHESCA 代码固定从 D:\\citylearn-demo\\citylearnpy\\CHESCA-main 加载；Java 复制脚本后仍可运行）
"""

# ---------------------------------------------------------------------------
# 第一部分：导入 Python 标准库
# ---------------------------------------------------------------------------
import argparse   # 解析命令行参数，例如 --output-dir
import os         # 操作系统相关，如判断文件是否存在
import sys        # 系统相关，如修改模块搜索路径 sys.path
import time       # 计时，统计 Agent 推理花了多少秒
import warnings   # 控制 Python 警告信息的显示
from pathlib import Path       # 更现代的路径处理（比字符串拼接路径更安全）
from typing import Optional    # 类型提示：表示函数可能返回 Path 或 None

# ---------------------------------------------------------------------------
# 第二部分：控制台编码（Windows 专用）
# ---------------------------------------------------------------------------
# Java 后端通过管道读取 Python 的 print 输出；Windows 默认编码可能导致中文乱码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# 忽略 gymnasium（CityLearn 底层用的 RL 环境库）的一些无关警告，让控制台更干净
warnings.filterwarnings('ignore', category=UserWarning, module='gymnasium')

# ---------------------------------------------------------------------------
# 第三部分：导入第三方库与 CityLearn
# ---------------------------------------------------------------------------
import pandas as pd                          # 表格数据处理，用于整理 KPI
from citylearn.citylearn import CityLearnEnv # CityLearn 仿真环境（核心）

# ---------------------------------------------------------------------------
# 第四部分：路径配置 —— CHESCA 算法目录（固定绝对路径）
# ---------------------------------------------------------------------------
# Java 执行前会把 .py 复制到 output/outkpis/{taskId}/，此时 __file__ 旁没有 CHESCA-main。
# 因此使用与 application.yml「python-file-path」一致的绝对路径。
CITYLEARNPY_DIR = Path(r'D:\citylearn-demo\citylearnpy')
CHESCA_ROOT = (CITYLEARNPY_DIR / 'CHESCA-main').resolve()

if not CHESCA_ROOT.is_dir():
    raise FileNotFoundError(f'CHESCA 目录不存在: {CHESCA_ROOT}')

if str(CHESCA_ROOT) not in sys.path:
    sys.path.insert(0, str(CHESCA_ROOT))

# SubmissionAgent：参赛用的控制算法（默认是 CHESCA）
# SubmissionReward：环境用的奖励函数（评估 KPI 时也会用到，但本脚本主要关心 evaluate()）
from agents.user_agent import SubmissionAgent
from rewards.user_reward import SubmissionReward

# 与 NOCONTROL.py 一致：使用 CityLearn 安装包/cache 中的内置数据集名，
# 不读取 CHESCA-main/data/schemas 下的本地 schema 文件
DEFAULT_SCHEMA = 'citylearn_challenge_2023_phase_2_local_evaluation'
# 默认 KPI / 时序 CSV 导出根目录（可被 --output-dir 覆盖）
DEFAULT_OUTPUT_DIR = Path(r'D:\citylearn-demo\outkpis')
# 每次运行会在 RENDER_DIR 下创建以此命名的子文件夹，避免覆盖旧结果
DEFAULT_RENDER_SESSION = 'chesca_local_eval'


# ---------------------------------------------------------------------------
# 工具函数：日志与 KPI 输出
# ---------------------------------------------------------------------------
def log_console(message):
    """
    向控制台打印一行日志。

    flush=True 表示立刻刷新缓冲区，Java 端轮询控制台时才能「实时」看到输出，
    而不是等缓冲区满了才一次性输出。
    """
    print(message, flush=True)


def print_kpis_for_java(kpis_df):
    """
    按 Java 后端 parseAndSaveKpis 约定的格式打印 KPI。

    为什么不能直接 print(kpis_df)？
    pandas 打印宽表时会用 ... 省略列，Java 解析会失败。
    因此逐行输出：指标名 + 各建筑数值，中间用空格分隔。

    参数 kpis_df：行=指标名（如 ramping），列=Building_1/2/3/District
    """
    log_console('outputkpi')  # 固定标记行，Java 靠它识别 KPI 块开始
    for idx in kpis_df.index:           # 遍历每一行（每个 KPI 指标）
        vals = []
        for col in kpis_df.columns:     # 遍历每一列（每栋建筑 + 区域汇总）
            v = kpis_df.loc[idx, col]
            # 缺失值写成 NaN；否则格式化为 6 位有效数字的字符串
            vals.append('NaN' if pd.isna(v) else f'{float(v):.6g}')
        print(f'{idx} {" ".join(vals)}', flush=True)


def parse_args():
    """
    解析命令行参数。

    示例：
      python local_evaluation.py
      python local_evaluation.py --output-dir D:\\citylearn-demo\\output\\outkpis\\任务ID
    """
    parser = argparse.ArgumentParser(description='CHESCA 本地评估并导出 KPI')
    parser.add_argument(
        '--output-dir', '-o',
        type=str,
        default=None,
        help=f'KPI/仿真数据导出目录（默认: {DEFAULT_OUTPUT_DIR}）',
    )
    parser.add_argument(
        '--render-session',
        type=str,
        default=DEFAULT_RENDER_SESSION,
        help='render 导出子目录名',
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# WrapperEnv：给 Agent 用的「简化版环境接口」
# ---------------------------------------------------------------------------
class WrapperEnv:
    """
    包装真实的 CityLearnEnv，只暴露 Agent 需要的属性。

    【为什么需要包装？】
    CHESCA 继承 citylearn.agents.base.Agent，基类会读取：
      - observation_names / action_names：知道观测向量每一维代表什么
      - buildings_metadata：每栋楼的设备参数
      - unwrapped：访问更底层的环境对象

    竞赛/本地评估习惯用 Wrapper，避免 Agent 直接调用不该用的 env 方法。
    """

    def __init__(self, env: CityLearnEnv):
        # 保存真实环境引用（前面加 _ 表示「内部使用」）
        self._env = env

        # --- 观测与动作空间（Agent 用来解析向量下标）---
        self.observation_names = env.observation_names   # 如 ['hour', 'day_type', ...]
        self.action_names = env.unwrapped.action_names   # 如 ['dhw_storage', 'electrical_storage', ...]
        self.observation_space = env.observation_space   # 观测取值范围
        self.action_space = env.action_space             # 动作取值范围（通常 -1~1）

        # --- 仿真元数据 ---
        self.time_steps = env.time_steps                           # 数据集总时间步数
        self.seconds_per_time_step = env.unwrapped.seconds_per_time_step  # 每步多少秒（通常 3600=1小时）
        self.random_seed = env.unwrapped.random_seed               # 随机种子，保证可复现
        self.buildings_metadata = env.get_metadata()['buildings']  # 各建筑配置
        self.episode_tracker = env.unwrapped.episode_tracker       # 当前 episode 进度跟踪

    @property
    def unwrapped(self):
        """Agent 基类有时会访问 env.unwrapped，这里转发到底层 CityLearnEnv。"""
        return self._env.unwrapped

    def get_metadata(self):
        """返回建筑元数据字典，供 Agent 初始化时使用。"""
        return {'buildings': self.buildings_metadata}


def create_citylearn_env(config, reward_function):
    """
    根据配置创建 CityLearn 仿真环境。

    数据集与 NOCONTROL.py 相同：传入 CityLearn 内置数据集名字符串，
    由 CityLearn 从本地 cache 加载 schema（如 .../citylearn/Cache/.../schema.json）。

    参数 config：包含 SCHEMA、episode_time_steps、RENDER_DIR 等
    参数 reward_function：奖励函数类

    返回：
      env         — 真实环境，负责 step / reset / evaluate
      wrapper_env — 给 Agent 用的包装环境
    """
    schema = getattr(config, 'SCHEMA', DEFAULT_SCHEMA)
    if not schema or not isinstance(schema, str):
        raise ValueError(
            f'无效的 SCHEMA: {schema!r}，请使用 CityLearn 内置数据集名，'
            f'例如 {DEFAULT_SCHEMA!r}'
        )

    # 创建 CityLearn 环境（schema 为内置数据集名，非 CHESCA 仓库内 data/schemas 路径）
    env = CityLearnEnv(
        schema,
        reward_function=reward_function,   # 奖励函数
        central_agent=True,                # True=一个 Agent 统一控制所有建筑（CHESCA 要求）
        episode_time_steps=getattr(config, 'episode_time_steps', 720),  # 每 episode 720 步
        render_mode='during',              # 仿真过程中逐步写入 exported_data_*.csv
        render_directory=getattr(config, 'RENDER_DIR', DEFAULT_OUTPUT_DIR),
        render_session_name=getattr(config, 'RENDER_SESSION', DEFAULT_RENDER_SESSION),
    )

    wrapper_env = WrapperEnv(env)
    return env, wrapper_env


def update_power_outage_random_seed(env: CityLearnEnv, random_seed: int) -> CityLearnEnv:
    """
    更新「随机停电」模型的种子。

    CityLearn 里部分建筑会随机停电；换 seed 可以让下一个 episode 的停电场景不同。
    必须在 env.reset() 之前调用，reset 之后停电序列就固定了。
    """
    for b in env.buildings:
        b.stochastic_power_outage_model.random_seed = random_seed
    return env


def print_episode_metrics(env: CityLearnEnv) -> dict:
    """
    计算并打印 **区域级 (District)** KPI 摘要。

    env.evaluate() 返回所有建筑 + 区域的指标；
    这里只筛选 name=='District' 的行，方便在控制台快速查看整体表现。

    指标 value 含义：相对「无智能控制基线」的比值
      - < 1.0 表示比基线更好
      - > 1.0 表示比基线更差
      - = 1.0 表示与基线相当
    """
    metrics = env.evaluate()
    district = metrics[metrics['name'] == 'District']
    summary = {}
    for _, row in district.iterrows():
        key = row['cost_function']   # 指标名，如 'ramping', '1-load_factor' 等
        value = float(row['value'])
        summary[key] = {'value': value}
        log_console(f'{key}: {value:.3f}')
    return summary


def save_episode_kpis(env: CityLearnEnv) -> Optional[Path]:
    """
    把本 episode 的完整 KPI 表写入 exported_kpis.csv，并打印给 Java 解析。

    【重要】必须在 env.reset() 之前调用！
    reset 会清空仿真状态；若之后再 evaluate()，得到的是「无控制基线」指标（多为 1.0）。
    """
    # 1. 评估：得到长表（每行 = 一个建筑/区域 × 一个指标）
    kpis = env.evaluate()

    # 2. 转为宽表：行=指标名，列=Building_1 / Building_2 / Building_3 / District
    kpis_table = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
    kpis_table = kpis_table.dropna(how='all')  # 去掉全空行

    # 3. 确保 render 输出目录存在（CityLearn 内部方法）
    env._ensure_render_output_dir()
    file_path = Path(env.new_folder_path) / 'exported_kpis.csv'

    # 4. 整理成 CSV 格式：第一列列名 KPI，后面各列为各建筑数值
    kpis_out = kpis_table.fillna('').reset_index().rename(columns={'cost_function': 'KPI'})
    kpis_out.to_csv(file_path, index=False, encoding='utf-8')
    env._final_kpis_exported = True  # 标记已导出，避免重复写入

    if env.new_folder_path:
        log_console(f'输出目录: {Path(env.new_folder_path).resolve()}')
        log_console(f'KPI 文件: {file_path.resolve()}')
    else:
        log_console('未生成导出目录（请确认 render_mode 已启用）')

    print_kpis_for_java(kpis_table)
    return file_path


def evaluate(config):
    """
    主评估流程 —— 整个脚本的核心。

    标准 RL 评估循环：
      reset → (predict → step → predict → step → ...) → 直到 done → 统计 KPI

    ========================================================================
    【CHESCA 算法详细执行步骤】（每个 env.step 之前的一次 agent.predict）
    ========================================================================

    调用链：
      local_evaluation.evaluate()
        → SubmissionAgent.register_reset / predict()     [agents/user_agent.py]
          → Checa.predict()                              [checa/agent.py 主入口]
            → 阶段1: ForecastAgent.compute_forecast()    [时序预测]
            → 阶段2: Checa.initial_actions()             [各建筑独立初稿]
            → 阶段3: get_future_cooling/dhw_demands()    [滚动预测设备用电]
            → 阶段4: refine_actions_with_battery...()  [社区级电池树搜索，第2步起]
            → 阶段5: compute_elec_consumption_values()   [更新净负荷历史]
            → 返回动作向量给 env.step()

    每栋建筑 3 个动作（共 3×n 维，本数据集 n=3）：
      [DHW_storage, electrical_storage, cooling_device]
       生活热水储热   电池充放电          冷机出力

    阶段1 — 时序预测 (ForecastAgent)
      · 把当前观测写入历史缓存
      · 用 XGBoost 预训练模型 + 在线 XGBoost + 历史均值 三模型集成
      · 预测未来 tau 步（默认 1 步）的：室外温度、光伏、不可调负荷、热水需求

    阶段2 — 初稿动作 (initial_actions)，按建筑循环：
      正常工况：
        · 冷机：PID 控制器根据室内外温差算 TMP_action（保舒适）
        · DHW：需求低于日均且储热 SOC 低 → 加热；否则从储热罐放电
        · 电池：初值 ELE_action = 0（留给阶段4优化）
      停电工况：
        · 冷机：在「电池可用电量 + 光伏」约束下尽量保冷
        · DHW：优先用储热，不够再耗电
        · 电池：光伏有余充电，负荷过大则限放电

    阶段3 — 未来设备用电估计
      · get_future_cooling_demands：用辅助 PID 滚动预测未来冷机电耗
      · get_future_dhw_demands：按 24h 加热计划表估算未来 DHW 需求

    阶段4 — 社区负荷平衡 (refine_actions_with_battery_controller)
      · 仅 seen_steps >= 1 时执行（首步无历史负荷，跳过）
      · 对每栋「未停电」建筑：
        - 构造状态向量 = [历史净负荷均值, 当前电池SOC, 当前及未来净负荷预测...]
        - BatteryController.search() 树搜索最优电池动作，使净负荷接近历史均值
        - 若净负荷过高：减 DHW 加热 / 略降冷机
        - 若净负荷过低：增加 DHW 加热吸收多余电力
      · 目标：降低 ramping（负荷剧烈波动）指标

    阶段5 — 更新预测历史
      · 净用电 = 不可调负荷 + 冷机 + DHW + 电池 − 光伏
      · 写入 elec_consumption_prediction_history，供下一步 refine 使用
    ========================================================================
    """
    log_console('Starting local evaluation (CHESCA)')

    output_dir = getattr(config, 'RENDER_DIR', DEFAULT_OUTPUT_DIR)
    log_console(f"初始化环境，配置: {config.SCHEMA}，导出目录: {Path(output_dir).resolve()}")

    # ---------- 1. 创建环境 ----------
    env, wrapper_env = create_citylearn_env(config, SubmissionReward)
    log_console('环境创建完成，初始化 CHESCA Agent...')

    # ---------- 2. 创建 Agent（控制策略）----------
    # SubmissionAgent = my_agent = Checa 的子类
    # 初始化时会创建以下子模块（见 checa/agent.py __init__）：
    #   · ForecastAgent      — XGBoost 时序预测
    #   · CoolingDeviceController × 3 — 每栋楼一个冷机 PID
    #   · BatteryController × 3       — 每栋楼一个电池树搜索
    # params={'tau': 1}：向前预测/优化 1 个时间步（1 小时）
    agent = SubmissionAgent(wrapper_env, params={'tau': 1})
    log_console('CHESCA Agent 创建完成')

    # ---------- 3. 重置环境，开始第一个 episode ----------
    # observations：当前观测；central_agent 模式下形状为 [[o1, o2, ...]]，外层长度 1
    # 第二个返回值 info 本脚本不用，用 _ 丢弃
    observations, _ = env.reset()

    # ---------- 4. 统计 Agent 纯推理耗时（不含 env.step 的物理仿真时间）----------
    agent_time_elapsed = 0
    total_steps = getattr(config, 'episode_time_steps', 720)

    # reset 后必须先算「第 0 步」要执行的动作（竞赛约定接口 register_reset）
    # 内部流程：my_agent.reset() 清空历史 → Checa.predict() 走完整 5 阶段决策
    # 注意：首步 seen_steps=0，阶段4（电池树搜索 refine）会跳过
    step_start = time.perf_counter()
    actions = agent.register_reset(observations)
    agent_time_elapsed += time.perf_counter() - step_start
    log_console(f'开始仿真，共 {total_steps} 步...')

    # ---------- 5. 循环控制变量 ----------
    episodes_completed = 0   # 已完成的 episode 数
    num_steps = 0            # 当前 episode 已执行的 step 数
    interrupted = False      # 是否被 Ctrl+C 中断
    episode_metrics = []     # 保存每个 episode 的区域 KPI 摘要

    try:
        # ---------- 6. 主仿真循环 ----------
        while True:
            # 把上一步的 actions 施加到环境，仿真前进 1 个时间步（1 小时）
            # 返回值：
            #   observations — 下一步观测
            #   _            — reward（本脚本不做 RL 训练，忽略）
            #   terminated   — 是否自然到达 episode 末尾
            #   truncated    — 是否被截断（如超过最大步数）
            observations, _, terminated, truncated, _ = env.step(actions)

            # 任一为 True 即表示本 episode 结束
            done = terminated or truncated

            if not done:
                # ===== episode 未结束：根据新观测预测下一步动作 =====
                # 此处进入 CHESCA 完整决策链（详见本函数 docstring 顶部说明）：
                #   predict → 预测 → 初稿 → 未来用电估计 → 电池 refine → 返回 9 维动作
                step_start = time.perf_counter()
                actions = agent.predict(observations)
                agent_time_elapsed += time.perf_counter() - step_start

                # 每 36 步（约 1.5 天）打印一次进度，避免控制台刷屏
                if num_steps == 0 or (num_steps + 1) % 36 == 0:
                    log_console(
                        f'[进度] {num_steps + 1}/{total_steps} 步 '
                        f'({100 * (num_steps + 1) / total_steps:.1f}%)'
                    )
            else:
                # ===== episode 已结束：汇总 KPI 并导出 =====
                episodes_completed += 1
                log_console(f'Episode complete: {episodes_completed}')
                log_console('仿真完成，正在计算 KPI...')

                metrics_dict = print_episode_metrics(env)
                episode_metrics.append(metrics_dict)
                save_episode_kpis(env)  # 必须在 reset 之前！

                # 若已达到配置的 episode 总数，退出循环
                if episodes_completed >= config.num_episodes:
                    break

                # ===== 多 episode 评测：准备下一轮 =====
                env = update_power_outage_random_seed(env, 90000)
                observations, _ = env.reset()
                step_start = time.perf_counter()
                # 第二个 episode 起没有 register_reset，直接用 predict
                actions = agent.predict(observations)
                agent_time_elapsed += time.perf_counter() - step_start

            num_steps += 1
            if num_steps % 1000 == 0:
                log_console(f'Num Steps: {num_steps}, Num episodes: {episodes_completed}')

    except KeyboardInterrupt:
        # 用户按 Ctrl+C 中断
        log_console('========================= Stopping Evaluation =========================')
        interrupted = True

    if not interrupted:
        log_console('=========================Completed=========================')

    log_console(f'Total time taken by agent: {agent_time_elapsed}s')
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# 程序入口：直接运行此文件时执行
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    args = parse_args()

    # 确定导出目录：命令行指定 > 默认目录（与 NOCONTROL.py / Single-agent.py 一致）
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Java 传入 --output-dir 任务目录时，直接写入该目录（render_session_name='.'）
    # 本地手动运行时仍可用 --render-session 创建子文件夹，避免覆盖旧结果
    render_session = '.' if args.output_dir else args.render_session

    class Config:
        SCHEMA = DEFAULT_SCHEMA              # CityLearn 内置数据集（同 NOCONTROL.py）
        num_episodes = 1
        episode_time_steps = 720
        RENDER_DIR = output_dir
        RENDER_SESSION = render_session

    evaluate(Config())
    sys.stdout.flush()
