# -*- coding: utf-8 -*-
# ⚠️ 本文件是**精简注释版**（由 `_gen_marl_split.py` 生成 ✓）：全部「详注块」已整段删除 ✓，
#    代码与同目录的 `X.detailed.py` **逐字相同** ✓（AST 一致 ⇒ 行为一致 ✓）。
#    **改注释请改 `.detailed.py` 那份** ✗（本文件每次生成都会被覆盖 ✗），改完重跑 `_gen_marl_split.py` ✓。
# CHESCA 专用环境构建：WrapperEnv（给 Agent 的瘦包装）+ 建 CityLearnEnv（2026-10-08 从 CHESCA.py 抽出 ✓）

from pathlib import Path

from citylearn.citylearn import CityLearnEnv

# 默认数据集（CityLearn 内置 ✓）
DEFAULT_SCHEMA = 'citylearn_challenge_2023_phase_2_local_evaluation'

# 默认导出根目录（Java 传了 -o 就用它自己的 ✓）
DEFAULT_OUTPUT_DIR = Path(r'D:\citylearn-demo\outkpis')

# 每次运行的渲染会话名（RENDER_DIR 下会再建同名子目录，避免覆盖旧结果 ✓）
DEFAULT_RENDER_SESSION = 'chesca_copy_eval'


class WrapperEnv:
    # 包装真实的 CityLearnEnv，只暴露 Agent 需要的属性。
    # 【为什么需要包装？】
    # 初始化：把真环境里 Agent 要用的字段抄一份缓存起来

    def __init__(self, env: CityLearnEnv):
        # 从真实 CityLearnEnv 抽取 Agent 所需字段并缓存。
        # 参数 env：已创建的 CityLearn 环境实例。
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
    # 转发 env.unwrapped（Agent 基类有时会访问它）
    def unwrapped(self):
        # Agent 基类有时会访问 env.unwrapped，这里转发到底层 CityLearnEnv。
        return self._env.unwrapped

    # 返回建筑元数据（Agent 初始化时要用）
    def get_metadata(self):
        # 返回建筑元数据字典，供 Agent 初始化时使用。
        return {'buildings': self.buildings_metadata}

    @property
    # 转发底层环境的建筑列表（读室温算 KPI 用）
    def buildings(self):
        # 转发到底层 CityLearnEnv.buildings，供高温不适等 KPI 口径读取动力学室温。
        return self.unwrapped.buildings

def create_citylearn_env(config, reward_function, schema=None, episode_time_steps=None):
    # 根据配置创建 CityLearn 仿真环境。
    # 参数 schema：可选，覆盖 config.SCHEMA（训测分离时传入 eval_schema）。
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

    env_kwargs = {
        'reward_function': reward_function,
        'central_agent': True,
    }
    # steps 为 None ⇒ **不传** episode_time_steps ⇒ 交给 CityLearn 用数据集自带长度 ✓
    if steps is not None:
        env_kwargs['episode_time_steps'] = int(steps)
    if enable_render:
        env_kwargs['render_mode'] = 'during'
        env_kwargs['render_directory'] = getattr(config, 'RENDER_DIR', DEFAULT_OUTPUT_DIR)
        env_kwargs['render_session_name'] = getattr(config, 'RENDER_SESSION', DEFAULT_RENDER_SESSION)

    env = CityLearnEnv(schema, **env_kwargs)
    wrapper_env = WrapperEnv(env)
    return env, wrapper_env
