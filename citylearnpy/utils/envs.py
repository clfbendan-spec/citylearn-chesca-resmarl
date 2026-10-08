# -*- coding: utf-8 -*-
"""兼容别名模块：`utils.envs`（旧名）→ `utils.env`（现名）。

# 为什么需要它
#   2026-10-07 把 `utils/envs.py` 改名成了 `utils/env.py`（同一次还做了别的模块合并）。
#   而 RLlib 的 checkpoint 里**记着**组件（环境 / 策略）的**模块路径**，它是按字符串
#   反查并 import 的 ⇒ 改名之前用 `Multi-agent-train.py` 训出来的断点，
#   加载时会直接：
#       ModuleNotFoundError: No module named 'utils.envs'
#   （2026-10-08 使用者复现：复用历史训练子任务 `5cbad9e0…-train` 的模型时炸在这里）
#
# 做什么
#   把 `utils.env` / `utils.ches_env` 里的**同名符号原样再导出一遍**，让旧断点里的
#   `utils.envs.XXX` 能 import 到同一个类 ⇒ 旧模型可以直接加载、复用。
#   纯别名，不含任何逻辑；等手上这些旧断点都不需要了，整个文件可以直接删。
#
# 注意：本文件是**手写的兼容层**，不参与 `_gen_marl_split.py` 的「详注版 / 精简版」生成，
#   也不需要 `.detailed.py` 孪生文件。
"""
from utils.ches_env import *          # noqa: F401,F403
from utils.env import *               # noqa: F401,F403

import utils.ches_env as _ches_env    # noqa: E402
import utils.env as _env              # noqa: E402


def __getattr__(name):
    """兜底：`import *` 带不过来的名字（下划线开头 / 未列进 __all__ 的）也照样能取到。"""
    for module in (_env, _ches_env):
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
