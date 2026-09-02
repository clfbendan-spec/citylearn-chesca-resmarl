"""
CHESCA 算法本地评估脚本（可修改副本）
========================================

【说明】
  本文件是 local_evaluation.py 的副本，配套目录 CHESCA-copy/。

【MARL 两种模式】（chesca_agent_config.json / --marl-mode）
  none         — 纯 CHESCA
  multi_agent  — CHESCA-ResMARL

================================================================================
【CHESCA-ResMARL 完整流程（marl_mode=multi_agent）— 易读版】
================================================================================

  记忆口诀：先练后用；每步先规则、后残差、α 加权，再进环境。

  ┌─ 阶段 0：准备工作（仿真尚未开始）──────────────────────────────┐
  │ ① 读配置（resmarl_enabled、α、mask、multi_agent_train_epochs、训测 schema）│
  │ ② 创建主环境 env（eval_schema，central_agent=True，KPI 只看它）            │
  │ ③ 创建 CHESCA Agent（SubmissionAgent）                                   │
  │ ④ 在 train_schema 上训练 Multi-Agent SAC（model.train × N 轮）           │
  │ ⑤ 挂载 MultiAgentResidualCorrector 到 agent.residual_corrector           │
  │ ⑥ 创建旁路 multi_env（eval_schema，与主 env 同步观测）                   │
  └──────────────────────────────────────────────────────────────────┘

  ┌─ 阶段 1：开局（第 0 小时）──────────────────────────────────────┐
  │ env.reset() + multi_env.reset()                                   │
  │ register_reset → Checa.predict() 一次完成：                       │
  │   阶段1 预测 → 阶段2 初稿 → 阶段3 未来用电 → 阶段4 refine → a_base│
  │   阶段5 SAC 各 agent 输出 Δa → a_final = clip(a_base+α·mask·Δa)  │
  └──────────────────────────────────────────────────────────────────┘

  ┌─ 阶段 2：主循环（第 1～719 小时，每小时重复）────────────────────┐
  │  env.step(a_final)          ← 主环境执行最终动作，推进 1 小时      │
  │  multi_env.step(a_final)    ← 旁路同步，使三 agent 观测对齐        │
  │  _bind_multi_obs()          ← 把观测交给残差器                     │
  │  agent.predict()            ← 再算下一小时的 a_final（同上 1～5）  │
  └──────────────────────────────────────────────────────────────────┘

  ┌─ 阶段 3：结束 ────────────────────────────────────────────────────┐
  │  env.evaluate() → exported_kpis.csv + chesca_trace / decision_trace│
  └──────────────────────────────────────────────────────────────────┘

  【常见误解】
  ✗ 不是「先跑一遍 MARL 仿真，再跑一遍纯 CHESCA，最后合并」
  ✗ 不是「MARL 先出动作，CHESCA 后出动作」
  ✓ 是「每一步：CHESCA 先算 a_base → SAC 算 Δa → α 合成 a_final → 执行」
  ✓ SAC 在 train_schema 上训练；CHESCA 在 eval_schema 上仿真（方案 A，默认开启）

  【训测 schema 默认值 — multi_agent 且 schema_split_enabled=true】
    train_schema = phase_2_local_evaluation（720h）
    eval_schema  = phase_2_online_evaluation_1（2208h，不同天气）
  纯 CHESCA 或 --no-schema-split：train/eval 同一 schema（默认 local_evaluation）

  【数值示例】某栋楼 ELE：a_base=0.20，Δa=0.50，α=0.2，mask 含 ELE
      a_final = 0.20 + 0.2 × 0.50 = 0.30
  α=0 时 a_final=a_base，与纯 CHESCA 数值一致。

运行目录：citylearnpy/（CHESCA 与 multi_agent_runner_copy 均从 CITYLEARNPY_DIR 加载）
"""

# 导入
import argparse 
import json       
import os         
import sys        
import time       
import warnings   
from pathlib import Path
from typing import Optional


# 统一输出编码，要不java会读取到乱码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# 忽略警告
warnings.filterwarnings('ignore', category=UserWarning, module='gymnasium')

# 导入 CityLearn 相关库
import pandas as pd                          # 表格数据处理，用于整理 KPI
from citylearn.citylearn import CityLearnEnv # CityLearn 仿真环境

# Java 执行前会把 .py 复制到 output/outkpis/{taskId}/，此时 __file__ 旁没有 CHESCA-copy /
# multi_agent_runner_copy.py。因此使用与 application.yml「python-file-path」一致的绝对路径。
CITYLEARNPY_DIR = Path(r'D:\citylearn-demo\citylearnpy')
CHESCA_ROOT = (CITYLEARNPY_DIR / 'CHESCA-copy').resolve()

if not CHESCA_ROOT.is_dir():
    raise FileNotFoundError(f'CHESCA 目录不存在: {CHESCA_ROOT}')

# citylearnpy：multi_agent_runner_copy.py；CHESCA-copy：agents / checa
for _p in (str(CITYLEARNPY_DIR.resolve()), str(CHESCA_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agents.user_agent import SubmissionAgent
from rewards.user_reward import SubmissionReward
from checa.trace_exporter import ChescaTraceRecorder, save_chesca_trace, save_decision_trace_json
from multi_agent_runner_copy import (
    setup_chesca_multi_agent_residual,
    sync_multi_env_step,
)

# 使用 CityLearn 内置数据集
DEFAULT_TRAIN_SCHEMA = 'citylearn_challenge_2023_phase_2_local_evaluation'
DEFAULT_EVAL_SCHEMA = 'citylearn_challenge_2023_phase_2_online_evaluation_1'
DEFAULT_SCHEMA = DEFAULT_TRAIN_SCHEMA  # 纯 CHESCA / 关闭训测分离时的默认 schema

# 各 schema 默认 episode 步数（simulation_end_time_step + 1）
SCHEMA_DEFAULT_EPISODE_STEPS = {
    'warm_up': 720,
    'citylearn_challenge_2023_phase_1': 720,
    'citylearn_challenge_2023_phase_2_local_evaluation': 720,
    'citylearn_challenge_2023_phase_2_online_evaluation_1': 2208,
    'citylearn_challenge_2023_phase_2_online_evaluation_2': 2208,
    'citylearn_challenge_2023_phase_2_online_evaluation_3': 2208,
    'citylearn_challenge_2023_phase_3_1': 2208,
    'citylearn_challenge_2023_phase_3_2': 2208,
    'citylearn_challenge_2023_phase_3_3': 2208,
}
# 设置导出目录
DEFAULT_OUTPUT_DIR = Path(r'D:\citylearn-demo\outkpis')
# 每次运行会在 RENDER_DIR 下创建以此命名的子文件夹，避免覆盖旧结果
DEFAULT_RENDER_SESSION = 'chesca_copy_eval'


#打印日志 flush=True表示立刻刷新缓冲区 让Java能实时获得控制台输出
def log_console(message):
    print(message, flush=True)

#按特定格式打印指标
#指标名 + 各建筑数值 
def print_kpis_for_java(kpisPrint):
    log_console('outputkpi')  # 标记 供java判断
    for idx in kpisPrint.index:           
        vals = []
        for col in kpisPrint.columns:
            v = kpisPrint.loc[idx, col]
            vals.append('NaN' if pd.isna(v) else f'{float(v):.6g}')
        print(f'{idx} {" ".join(vals)}', flush=True)

#解析命令行参数
def parse_args():
    parser = argparse.ArgumentParser(description='CHESCA 本地评估副本（可修改）并导出 KPI')
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
    parser.add_argument(
        '--min-soc-config',
        type=str,
        default=None,
        help='CHESCA Agent 配置 JSON 路径（含 SOC 与 B_low/B_high 等参数）',
    )
    parser.add_argument(
        '--episode-time-steps',
        type=int,
        default=None,
        help='覆盖每 episode 时间步数（默认 720；消融冒烟可用 24）',
    )
    parser.add_argument(
        '--no-render',
        action='store_true',
        help='关闭 render 导出（加速消融评估）',
    )
    parser.add_argument(
        '--marl-mode',
        type=str,
        default=None,
        choices=['none', 'multi_agent'],
        help='MARL 模式：multi_agent=CHESCA+Multi-Agent SAC 残差；none=纯 CHESCA',
    )
    parser.add_argument(
        '--train-schema',
        type=str,
        default=None,
        help=f'Multi-Agent SAC 训练用 schema（默认: {DEFAULT_TRAIN_SCHEMA}）',
    )
    parser.add_argument(
        '--eval-schema',
        type=str,
        default=None,
        help=f'CHESCA 仿真/KPI 用 schema（默认: {DEFAULT_EVAL_SCHEMA}；关闭分离时用 DEFAULT_SCHEMA）',
    )
    parser.add_argument(
        '--schema-split',
        action='store_true',
        default=None,
        help='启用训测 schema 分离（multi_agent 默认开启）',
    )
    parser.add_argument(
        '--no-schema-split',
        action='store_true',
        help='关闭训测分离，训练与评估使用同一 schema（等同旧行为）',
    )
    return parser.parse_args()

#数据规范化 用于24 小时电池 SOC 下限表（min_soc_per_hour） key为0~23 value为0~1
def _parse_min_soc_map(raw):
    result = {}
    for hour in range(24):
        key = str(hour)
        if key not in raw:
            raise ValueError(f'缺少对应的时间段 {hour}')
        value = float(raw[key])
        if value < 0 or value > 1:
            raise ValueError(f'{hour}的SOC对应值应在 0~1 之间，当前: {value}')
        result[key] = value
    return result

#数据规范化 用于SOC中部分百分比参数
def _parse_soc_limit(value, name):
    soc = float(value)
    if soc < 0 or soc > 1:
        raise ValueError(f'{name} 须在 0~1 之间，当前: {soc}')
    return soc

#数据规范化 用于负荷平衡阈值（如 B_low / B_high）
#用于判断净负荷相对历史均值的偏离倍数；合法范围 (0, 20]
def _parse_threshold(value, name):
    threshold = float(value)
    if threshold <= 0 or threshold > 20:
        raise ValueError(f'{name} 须在0~20之间，当前: {threshold}')
    return threshold

#数据规范化  解析预测/优化前瞻步数 tau
#CHESCA只允许1,2,3；用于决定 ForecastAgent 与电池树搜索看多远
def _parse_tau(value):
    tau = int(value)
    if tau not in (1, 2, 3):
        raise ValueError(f'tau 须为 1、2、3，当前: {tau}')
    return tau

#数据规范化  电池树搜索适应度类型balance_type：A / B / C   对应 BatteryController 3种目标函数
def _parse_balance_type(value):
    balance_type = str(value).strip().upper()
    if balance_type not in ('A', 'B', 'C'):
        raise ValueError(f'balance_type 须为 A、B、C，当前: {balance_type}')
    return balance_type

#数据规范化 返回规范bool值
def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ('1', 'true', 'yes', 'on'):
        return True
    if s in ('0', 'false', 'no', 'off', ''):
        return False
    return default

#数据规范化 ResMARL 残差强度 residual_alpha（α） 用于判断MARL的影响程度  0~1
#a_final = clip(a_base + α · mask · Δa) 
def _parse_residual_alpha(value):
    alpha = float(value)
    if alpha < 0 or alpha > 1:
        raise ValueError(f'residual_alpha 须在 [0, 1] 之间，当前: {alpha}')
    return alpha

#数据规范化 ResMARL 动作掩码 residual_action_mask
#控制残差可作用的动作维：dhw / ele / tmp。
#默认仅 ele=True（只修正电池充放电）
def _parse_residual_mask(value):
    mask = {'dhw': False, 'ele': True, 'tmp': False}
    if not isinstance(value, dict):
        return mask
    for key in ('dhw', 'ele', 'tmp'):
        if key in value:
            mask[key] = _parse_bool(value[key], mask[key])
    return mask


def _default_episode_steps_for_schema(schema: str) -> int:
    return int(SCHEMA_DEFAULT_EPISODE_STEPS.get(schema, 720))


def resolve_schema_plan(config, agent_config, marl_mode: str) -> dict:
    """
    解析训测 schema 方案（方案 A）。

    multi_agent 且 schema_split_enabled 时（默认开启）：
      · SAC 训练 → train_schema（默认 phase_2_local_evaluation，720h）
      · CHESCA 仿真/KPI → eval_schema（默认 phase_2_online_evaluation_1，2208h）

    关闭分离或 marl_mode=none 时：train/eval 使用同一 schema。
    """
    agent_config = agent_config or {}

    train_schema = (
        getattr(config, 'TRAIN_SCHEMA', None)
        or agent_config.get('train_schema')
    )
    eval_schema = (
        getattr(config, 'EVAL_SCHEMA', None)
        or agent_config.get('eval_schema')
        or getattr(config, 'SCHEMA', None)
        or agent_config.get('schema')
    )

    cli_split = getattr(config, 'SCHEMA_SPLIT_ENABLED', None)
    if agent_config.get('schema_split_enabled') is not None:
        split_enabled = _parse_bool(agent_config.get('schema_split_enabled'))
    elif cli_split is not None:
        split_enabled = bool(cli_split)
    else:
        split_enabled = marl_mode == 'multi_agent'

    if not split_enabled:
        single = eval_schema or DEFAULT_SCHEMA
        steps = getattr(config, 'episode_time_steps', None)
        if steps is None:
            steps = _default_episode_steps_for_schema(single)
        return {
            'schema_split_enabled': False,
            'train_schema': single,
            'eval_schema': single,
            'train_episode_steps': int(steps),
            'eval_episode_steps': int(steps),
        }

    train_schema = train_schema or DEFAULT_TRAIN_SCHEMA
    eval_schema = eval_schema or DEFAULT_EVAL_SCHEMA

    train_steps = getattr(config, 'TRAIN_EPISODE_TIME_STEPS', None)
    if train_steps is None:
        train_steps = agent_config.get('train_episode_time_steps')
    if train_steps is None:
        train_steps = _default_episode_steps_for_schema(train_schema)

    eval_steps = getattr(config, 'EVAL_EPISODE_TIME_STEPS', None)
    if eval_steps is None:
        eval_steps = agent_config.get('eval_episode_time_steps')
    if eval_steps is None:
        explicit = getattr(config, 'episode_time_steps', None)
        eval_steps = explicit if explicit is not None else _default_episode_steps_for_schema(eval_schema)

    return {
        'schema_split_enabled': True,
        'train_schema': train_schema,
        'eval_schema': eval_schema,
        'train_episode_steps': int(train_steps),
        'eval_episode_steps': int(eval_steps),
    }


def _parse_marl_mode(value):
    """
    解析 MARL 运行模式。

    none         — 纯 CHESCA，不用 RL 残差
    multi_agent  — CHESCA-ResMARL（CHESCA 基准 + Multi-Agent SAC 残差修正）
    """
    mode = str(value).strip().lower()
    if mode == 'central_residual':
        return 'multi_agent'
    if mode not in ('none', 'multi_agent'):
        raise ValueError(f'marl_mode 须为 none / multi_agent，当前: {value}')
    return mode


def _resolve_marl_mode(agent_config, cli_mode=None):
    """
    决定本次评估走哪条控制链路（优先级从高到低）：
      1. 命令行 --marl-mode
      2. JSON 字段 marl_mode
      3. resmarl_enabled=true → multi_agent（CHESCA-ResMARL）
      4. 否则 none（纯 CHESCA）
    """
    if cli_mode:
        return _parse_marl_mode(cli_mode)
    if not agent_config:
        return 'none'
    if agent_config.get('marl_mode') is not None:
        return _parse_marl_mode(agent_config['marl_mode'])
    if _parse_bool(agent_config.get('resmarl_enabled'), False):
        return 'multi_agent'
    return 'none'


#读取启动java时获得的json中的参数(chesca_agent_config.json) 或命令行 --min-soc-config 指定的路径
def load_agent_config(config_path):
    """
      {
        "min_soc_per_hour": {"0": 0.6, ...},
        "max_soc_normal": 0.99,
        "max_soc_outage": 0.87,
        "B_low": 1.18,
        "B_high": 1.0,
        "resmarl_enabled": false,
        "marl_mode": "none",
        "residual_alpha": 0.0,
        "residual_action_mask": {"dhw": false, "ele": true, "tmp": false},
        "multi_agent_train_epochs": 20,
        "multi_agent_explore": false,
        "resmarl_after_safety": true,
        "schema_split_enabled": true,
        "train_schema": "citylearn_challenge_2023_phase_2_local_evaluation",
        "eval_schema": "citylearn_challenge_2023_phase_2_online_evaluation_1"
      }
    """
    if not config_path:
        return None
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f'电池 SOC 配置文件不存在: {path}')
    with path.open(encoding='utf-8') as f:
        raw = json.load(f)

    if isinstance(raw, dict) and 'min_soc_per_hour' in raw:
        min_soc = _parse_min_soc_map(raw['min_soc_per_hour'])
        max_normal = _parse_soc_limit(raw.get('max_soc_normal', 0.99), 'max_soc_normal')
        max_outage = _parse_soc_limit(raw.get('max_soc_outage', 0.87), 'max_soc_outage')
        max_soc_reduction = _parse_soc_limit(
            raw.get('max_soc_reduction_in_outage', 0.70),
            'max_soc_reduction_in_outage',
        )
        b_low = _parse_threshold(raw.get('B_low', raw.get('b_low', 1.18)), 'B_low')
        b_high = _parse_threshold(raw.get('B_high', raw.get('b_high', 1.0)), 'B_high')
        tmp_max_reduction = _parse_soc_limit(
            raw.get('TMP_max_reduction_percent', raw.get('tmp_max_reduction_percent', 0.0)),
            'TMP_max_reduction_percent',
        )
        tau = _parse_tau(raw.get('tau', 1))
        balance_type = _parse_balance_type(raw.get('balance_type', 'C'))
        resmarl_enabled = _parse_bool(raw.get('resmarl_enabled', raw.get('residual_enabled', False)))
        residual_alpha = _parse_residual_alpha(raw.get('residual_alpha', raw.get('resmarl_alpha', 0.0)))
        residual_action_mask = _parse_residual_mask(raw.get('residual_action_mask'))
        resmarl_after_safety = _parse_bool(raw.get('resmarl_after_safety', True), default=True)
        marl_mode = raw.get('marl_mode')
        if marl_mode is not None:
            marl_mode = _parse_marl_mode(marl_mode)
        multi_agent_train_epochs = int(raw.get('multi_agent_train_epochs', 20))
        multi_agent_explore = _parse_bool(raw.get('multi_agent_explore', False))
        schema_split_enabled = raw.get('schema_split_enabled')
        if schema_split_enabled is not None:
            schema_split_enabled = _parse_bool(schema_split_enabled)
        train_schema = raw.get('train_schema')
        eval_schema = raw.get('eval_schema')
        train_episode_time_steps = raw.get('train_episode_time_steps')
        eval_episode_time_steps = raw.get('eval_episode_time_steps')
        if train_episode_time_steps is not None:
            train_episode_time_steps = int(train_episode_time_steps)
        if eval_episode_time_steps is not None:
            eval_episode_time_steps = int(eval_episode_time_steps)
    else:
        min_soc = _parse_min_soc_map(raw)
        max_normal = 0.99
        max_outage = 0.87
        max_soc_reduction = 0.70
        b_low = 1.18
        b_high = 1.0
        tmp_max_reduction = 0.0
        tau = 1
        balance_type = 'C'
        resmarl_enabled = False
        residual_alpha = 0.0
        residual_action_mask = {'dhw': False, 'ele': True, 'tmp': False}
        resmarl_after_safety = True
        marl_mode = None
        multi_agent_train_epochs = 20
        multi_agent_explore = False
        schema_split_enabled = None
        train_schema = None
        eval_schema = None
        train_episode_time_steps = None
        eval_episode_time_steps = None

    resolved_marl_mode = _resolve_marl_mode({
        'marl_mode': marl_mode,
        'resmarl_enabled': resmarl_enabled,
    })

    result = {
        'min_soc_per_hour': min_soc,
        'max_soc_normal': max_normal,
        'max_soc_outage': max_outage,
        'max_soc_reduction_in_outage': max_soc_reduction,
        'B_low': b_low,
        'B_high': b_high,
        'TMP_max_reduction_percent': tmp_max_reduction,
        'tau': tau,
        'balance_type': balance_type,
        'resmarl_enabled': resmarl_enabled,
        'residual_alpha': residual_alpha,
        'residual_action_mask': residual_action_mask,
        'resmarl_after_safety': resmarl_after_safety,
        'marl_mode': resolved_marl_mode,
        'multi_agent_train_epochs': multi_agent_train_epochs,
        'multi_agent_explore': multi_agent_explore,
    }
    if schema_split_enabled is not None:
        result['schema_split_enabled'] = schema_split_enabled
    if train_schema:
        result['train_schema'] = str(train_schema).strip()
    if eval_schema:
        result['eval_schema'] = str(eval_schema).strip()
    if train_episode_time_steps is not None:
        result['train_episode_time_steps'] = train_episode_time_steps
    if eval_episode_time_steps is not None:
        result['eval_episode_time_steps'] = eval_episode_time_steps
    return result


#用于包装CityLearnEnv
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
        """
        从真实 CityLearnEnv 抽取 Agent 所需字段并缓存。

        参数 env：已创建的 CityLearn 环境实例。
        """
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


def create_citylearn_env(config, reward_function, schema=None, episode_time_steps=None):
    """
    根据配置创建 CityLearn 仿真环境。

    参数 schema：可选，覆盖 config.SCHEMA（训测分离时传入 eval_schema）。
    参数 episode_time_steps：可选，覆盖 config.episode_time_steps。
    """
    schema = schema or getattr(config, 'SCHEMA', DEFAULT_SCHEMA)
    if not schema or not isinstance(schema, str):
        raise ValueError(
            f'无效的 SCHEMA: {schema!r}，请使用 CityLearn 内置数据集名，'
            f'例如 {DEFAULT_SCHEMA!r}'
        )

    enable_render = bool(getattr(config, 'ENABLE_RENDER', True))
    steps = episode_time_steps
    if steps is None:
        steps = getattr(config, 'episode_time_steps', None)
    if steps is None:
        steps = _default_episode_steps_for_schema(schema)

    env_kwargs = {
        'reward_function': reward_function,
        'central_agent': True,
        'episode_time_steps': int(steps),
    }
    if enable_render:
        env_kwargs['render_mode'] = 'during'
        env_kwargs['render_directory'] = getattr(config, 'RENDER_DIR', DEFAULT_OUTPUT_DIR)
        env_kwargs['render_session_name'] = getattr(config, 'RENDER_SESSION', DEFAULT_RENDER_SESSION)

    env = CityLearnEnv(schema, **env_kwargs)
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


def save_episode_kpis(env: CityLearnEnv, fallback_dir: Optional[Path] = None) -> Optional[Path]:
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

    # 3. 确定导出目录：消融/评估任务目录优先，其次 CityLearn render 目录
    file_path = None
    if fallback_dir is not None:
        out = Path(fallback_dir)
        out.mkdir(parents=True, exist_ok=True)
        file_path = out / 'exported_kpis.csv'
    else:
        try:
            env._ensure_render_output_dir()
            if getattr(env, 'new_folder_path', None):
                file_path = Path(env.new_folder_path) / 'exported_kpis.csv'
        except Exception:
            file_path = None
        if file_path is None:
            file_path = Path('.') / 'exported_kpis.csv'

    # 4. 整理成 CSV 格式：第一列列名 KPI，后面各列为各建筑数值
    kpis_out = kpis_table.fillna('').reset_index().rename(columns={'cost_function': 'KPI'})
    kpis_out.to_csv(file_path, index=False, encoding='utf-8')
    env._final_kpis_exported = True  # 标记已导出，避免重复写入

    log_console(f'输出目录: {file_path.parent.resolve()}')
    log_console(f'KPI 文件: {file_path.resolve()}')

    print_kpis_for_java(kpis_table)
    return file_path


def save_chesca_trace_csv(recorder: ChescaTraceRecorder, output_dir: Path) -> Optional[Path]:
    """
    将 CHESCA / ResMARL 决策 trace 写入任务目录。

    输出：
      - chesca_trace.csv      — 逐步表格（含残差埋点列）
      - decision_trace.json   — 供前端「决策推演」阅读的结构化日志

    参数 recorder：评估循环中挂在 Agent 上的 ChescaTraceRecorder。
    参数 output_dir：与 KPI 相同的导出目录。
    无数据时打印提示并返回 None；成功则返回 csv 路径。
    """
    if recorder is None or not recorder.rows:
        log_console('未收集到 CHESCA trace 数据，跳过 Decision Trace 导出')
        return None

    out = Path(output_dir)
    csv_path = out / 'chesca_trace.csv'
    json_path = out / 'decision_trace.json'
    save_chesca_trace(recorder, csv_path)
    save_decision_trace_json(recorder, json_path)
    log_console(f'CHESCA trace 文件: {csv_path.resolve()}')
    log_console(f'决策推演日志: {json_path.resolve()}')
    return csv_path


def evaluate(config):
    """
    评估总入口。

    流程：解析 marl_mode → 写配置快照 → 进入 evaluate_chesca()。
    无论 none 还是 multi_agent，仿真主链都在 evaluate_chesca 中完成。
    """
    output_dir = getattr(config, 'RENDER_DIR', DEFAULT_OUTPUT_DIR)
    agent_config = getattr(config, 'AGENT_CONFIG', None) or {}

    cli_marl_mode = getattr(config, 'MARL_MODE_CLI', None)
    marl_mode = _resolve_marl_mode(agent_config, cli_mode=cli_marl_mode)
    if isinstance(agent_config, dict):
        agent_config = dict(agent_config)
        agent_config['marl_mode'] = marl_mode
        config.AGENT_CONFIG = agent_config

    log_console(f'控制模式 marl_mode={marl_mode}')

    marl_mode_resolved = marl_mode
    schema_plan = resolve_schema_plan(config, agent_config, marl_mode_resolved)
    if isinstance(agent_config, dict):
        agent_config = dict(agent_config)
        agent_config['marl_mode'] = marl_mode_resolved
        agent_config['schema_split_enabled'] = schema_plan['schema_split_enabled']
        agent_config['train_schema'] = schema_plan['train_schema']
        agent_config['eval_schema'] = schema_plan['eval_schema']
        agent_config['train_episode_time_steps'] = schema_plan['train_episode_steps']
        agent_config['eval_episode_time_steps'] = schema_plan['eval_episode_steps']
        config.AGENT_CONFIG = agent_config

    try:
        cfg_path = Path(output_dir) / 'chesca_agent_config.json'
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = dict(agent_config) if isinstance(agent_config, dict) else {}
        cfg_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
        log_console(f'已写入配置快照: {cfg_path.resolve()}')
    except Exception as exc:
        log_console(f'写入 chesca_agent_config.json 失败: {exc}')

    evaluate_chesca(config, marl_mode=marl_mode)


def evaluate_chesca(config, marl_mode='none'):
    """
    CHESCA 主评估流程（可选 CHESCA-ResMARL）。

    ========================================================================
    【marl_mode=multi_agent 时 — 按时间顺序】
    ========================================================================
    阶段 0（本函数前半段，仿真未开始）：
      创建 env + Agent → 训练 SAC → 挂载残差器 → 创建旁路 multi_env

    阶段 1（reset 后 register_reset）：
      第 0 小时动作 = predict() 一次走完阶段 1～5

    阶段 2（while 主循环，每小时）：
      env.step(a_final) → multi_env 同步 → predict() 得下一小时 a_final

    阶段 3（done 时）：
      KPI + trace 导出

    【每一步 predict() 内部 — Checa.predict，见 checa/agent.py】
      阶段1 预测 → 阶段2 初稿 → 阶段3 未来用电 → 阶段4 refine → a_base
      阶段5 SAC 输出 Δa → a_final = clip(a_base + α·mask·Δa)

    【marl_mode=none】
      resmarl_enabled=False，阶段 5 恒等，a_final = a_base（纯 CHESCA）
    """
    log_console('Starting local evaluation (CHESCA)')
    output_dir = getattr(config, 'RENDER_DIR', DEFAULT_OUTPUT_DIR)
    agent_config = getattr(config, 'AGENT_CONFIG', None) or {}
    schema_plan = resolve_schema_plan(config, agent_config, marl_mode)
    log_console(
        f"数据集方案: split={schema_plan['schema_split_enabled']}, "
        f"train={schema_plan['train_schema']}({schema_plan['train_episode_steps']}步), "
        f"eval={schema_plan['eval_schema']}({schema_plan['eval_episode_steps']}步)"
    )
    log_console(f"导出目录: {Path(output_dir).resolve()}")
    log_console(f'CHESCA 子模式: marl_mode={marl_mode}')

    # True = CHESCA-ResMARL；False = 纯 CHESCA
    use_marl_residual = marl_mode == 'multi_agent'

    # ==================================================================
    # 阶段 0-①：创建主环境（eval_schema，central_agent=True，KPI / render 只看它）
    # ==================================================================
    env, wrapper_env = create_citylearn_env(
        config,
        SubmissionReward,
        schema=schema_plan['eval_schema'],
        episode_time_steps=schema_plan['eval_episode_steps'],
    )
    log_console('环境创建完成，初始化 CHESCA Agent...')

    # ==================================================================
    # 阶段 0-②：组装 Agent 参数（SOC、B_low/B_high、残差 α·mask 等）
    # ==================================================================
    agent_params = {}
    agent_config = getattr(config, 'AGENT_CONFIG', None)
    if agent_config:
        agent_params['tau'] = agent_config.get('tau', 1)
        log_console(f"已加载 tau={agent_params['tau']}")

        min_soc = agent_config.get('min_soc_per_hour')
        if min_soc:
            agent_params['min_soc_per_hour'] = min_soc
            log_console(f'已加载自定义电池 SOC 下限配置（{len(min_soc)} 个小时）')

        if agent_config.get('max_soc_normal') is not None:
            agent_params['max_soc_normal'] = agent_config['max_soc_normal']
            log_console(f"已加载 max_soc_normal={agent_config['max_soc_normal']}")
        if agent_config.get('max_soc_outage') is not None:
            agent_params['max_soc_outage'] = agent_config['max_soc_outage']
            log_console(f"已加载 max_soc_outage={agent_config['max_soc_outage']}")
        if agent_config.get('max_soc_reduction_in_outage') is not None:
            agent_params['max_soc_reduction_in_outage'] = agent_config['max_soc_reduction_in_outage']
            log_console(f"已加载 max_soc_reduction_in_outage={agent_config['max_soc_reduction_in_outage']}")

        if agent_config.get('B_low') is not None:
            agent_params['B_low'] = agent_config['B_low']
            log_console(f"已加载 B_low={agent_config['B_low']}")
        if agent_config.get('B_high') is not None:
            agent_params['B_high'] = agent_config['B_high']
            log_console(f"已加载 B_high={agent_config['B_high']}")

        if agent_config.get('TMP_max_reduction_percent') is not None:
            agent_params['TMP_max_reduction_percent'] = agent_config['TMP_max_reduction_percent']
            log_console(f"已加载 TMP_max_reduction_percent={agent_config['TMP_max_reduction_percent']}")

        if agent_config.get('balance_type') is not None:
            agent_params['balance_type'] = agent_config['balance_type']
            log_console(f"已加载 balance_type={agent_config['balance_type']}")

        if use_marl_residual:
            # 打开残差开关；Δa 由 setup_chesca_multi_agent_residual 挂载的 SAC 提供
            agent_params['resmarl_enabled'] = True
            agent_params['residual_alpha'] = agent_config.get('residual_alpha', 0.15)
            log_console(f"已加载 CHESCA-ResMARL residual_alpha={agent_params['residual_alpha']}")
            if agent_config.get('residual_action_mask') is not None:
                agent_params['residual_action_mask'] = agent_config['residual_action_mask']
            if agent_config.get('resmarl_after_safety') is not None:
                agent_params['resmarl_after_safety'] = agent_config['resmarl_after_safety']
        else:
            agent_params['resmarl_enabled'] = False
            agent_params['residual_alpha'] = 0.0
    else:
        agent_params['tau'] = 1
        agent_params['balance_type'] = 'C'
        agent_params['resmarl_enabled'] = False
        agent_params['residual_alpha'] = 0.0

    agent = SubmissionAgent(wrapper_env, params=agent_params)

    # ==================================================================
    # 阶段 0-③～⑤：CHESCA-ResMARL
    #   ③ 训练 Multi-Agent SAC（model.train × N 轮，尚未开始 720 步仿真）
    #   ④ 用 MultiAgentResidualCorrector 替换 agent.residual_corrector
    #   ⑤ 创建旁路 multi_env（无 render，仅同步三 agent 观测，不算 KPI）
    # ==================================================================
    multi_env = None
    multi_agent_ids = []
    if use_marl_residual:
        multi_env, multi_agent_ids, _ = setup_chesca_multi_agent_residual(
            agent,
            agent_config or {},
            config,
            log_console,
            schema_plan=schema_plan,
        )

    # Decision Trace：记录每步初稿 / refine / 残差，供前端决策推演
    trace_recorder = ChescaTraceRecorder(agent.n_buildings)
    agent.trace_recorder = trace_recorder
    trace_recorder.begin_episode()
    log_console('CHESCA Agent 创建完成（trace 已启用）')

    # ==================================================================
    # 阶段 1：开局 — 双环境 reset，算第 0 小时动作
    # ==================================================================
    observations, _ = env.reset()
    multi_observations = {}
    if multi_env is not None:
        multi_observations, _ = multi_env.reset()

    def _bind_multi_obs():
        """
        把旁路 multi_env 的三 agent 观测交给残差器。
        predict 阶段 5 里 SAC 用这些观测推理 Δa（不是用 central 的 9 维动作当最终动作）。
        """
        if use_marl_residual and hasattr(agent, 'residual_corrector'):
            agent.residual_corrector.set_multi_observations(multi_observations)

    agent_time_elapsed = 0
    total_steps = schema_plan['eval_episode_steps']

    _bind_multi_obs()
    step_start = time.perf_counter()
    # register_reset = reset() + predict()：
    #   CHESCA 阶段1～4 → a_base；阶段5 → a_final（ResMARL 时含 SAC 残差）
    actions = agent.register_reset(observations)
    agent_time_elapsed += time.perf_counter() - step_start
    log_console(f'开始仿真，共 {total_steps} 步...')

    episodes_completed = 0
    num_steps = 0
    interrupted = False
    episode_metrics = []

    try:
        # ==============================================================
        # 阶段 2：主循环 — 每小时重复（只有一条仿真链，不是 MARL 与 CHESCA 各跑一遍）
        #
        #   小时 t 已有 actions (= a_final)
        #     → env.step(actions)           主环境前进，得到 t+1 观测
        #     → multi_env.step(同一 actions) 旁路对齐，供下一步 SAC 看观测
        #     → predict()                   算 t+1 的 a_final
        #   重复直到 720 步或 episode 结束
        # ==============================================================
        while True:
            # --- 2.1 主环境执行 a_final（KPI 来自这一路）---
            observations, _, terminated, truncated, _ = env.step(actions)
            done = terminated or truncated

            # --- 2.2 旁路环境同步（ResMARL 时；不参与 KPI）---
            if multi_env is not None:
                multi_observations = sync_multi_env_step(multi_env, actions, multi_agent_ids)

            if not done:
                # --- 2.3 算下一小时动作：先 CHESCA(a_base)，再 SAC(Δa)，再 α 合成 ---
                _bind_multi_obs()
                step_start = time.perf_counter()
                actions = agent.predict(observations)
                agent_time_elapsed += time.perf_counter() - step_start

                if num_steps == 0 or (num_steps + 1) % 36 == 0:
                    log_console(
                        f'[进度] {num_steps + 1}/{total_steps} 步 '
                        f'({100 * (num_steps + 1) / total_steps:.1f}%)'
                    )
            else:
                # ======================================================
                # 阶段 3：episode 结束 — 导出 KPI 与决策 trace
                # ======================================================
                episodes_completed += 1
                log_console(f'Episode complete: {episodes_completed}')
                log_console('仿真完成，正在计算 KPI...')

                metrics_dict = print_episode_metrics(env)
                episode_metrics.append(metrics_dict)

                save_episode_kpis(env, fallback_dir=Path(output_dir))
                save_chesca_trace_csv(trace_recorder, Path(output_dir))

                if episodes_completed >= config.num_episodes:
                    break

                # 6.5 多局：双环境一起 reset，再 predict 开局动作
                env = update_power_outage_random_seed(env, 90000)
                observations, _ = env.reset()
                if multi_env is not None:
                    multi_observations, _ = multi_env.reset()

                trace_recorder.begin_episode()
                _bind_multi_obs()
                step_start = time.perf_counter()
                actions = agent.predict(observations)
                agent_time_elapsed += time.perf_counter() - step_start

            num_steps += 1
            if num_steps % 1000 == 0:
                log_console(f'Num Steps: {num_steps}, Num episodes: {episodes_completed}')

    except KeyboardInterrupt:
        log_console('========================= Stopping Evaluation =========================')
        interrupted = True

    if not interrupted:
        log_console('=========================Completed=========================')

    log_console(f'Total time taken by agent: {agent_time_elapsed}s')
    sys.stdout.flush()



# 程序入口
if __name__ == '__main__':
    args = parse_args()

    # 确定导出目录
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    render_session = '.' if args.output_dir else args.render_session
    agent_config = load_agent_config(args.min_soc_config)
    if agent_config and args.marl_mode:
        agent_config['marl_mode'] = args.marl_mode

    if args.no_schema_split:
        schema_split_enabled = False
    elif args.schema_split:
        schema_split_enabled = True
    else:
        schema_split_enabled = None

    class Config:
        SCHEMA = DEFAULT_SCHEMA
        TRAIN_SCHEMA = args.train_schema
        EVAL_SCHEMA = args.eval_schema
        SCHEMA_SPLIT_ENABLED = schema_split_enabled
        num_episodes = 1
        episode_time_steps = args.episode_time_steps if args.episode_time_steps else None
        RENDER_DIR = output_dir
        RENDER_SESSION = render_session
        AGENT_CONFIG = agent_config
        ENABLE_RENDER = not args.no_render
        MARL_MODE_CLI = args.marl_mode

    evaluate(Config())
    sys.stdout.flush()
