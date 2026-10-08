# ⚠️ 本文件是**精简注释版**（由 `_gen_marl_split.py` 生成 ✓）：全部「详注块」已整段删除 ✓，
#    代码与同目录的 `X.detailed.py` **逐字相同** ✓（AST 一致 ⇒ 行为一致 ✓）。
#    **改注释请改 `.detailed.py` 那份** ✗（本文件每次生成都会被覆盖 ✗），改完重跑 `_gen_marl_split.py` ✓。
# base = 三个入口共用的「启动靴」：日志工具 + 子进程/Ray 环境准备 + torch 单线程 + 编码与警告 ✓
# 用法：`from utils.base import …`，必须写在任何重库（numpy/pandas/torch/citylearn/ray）之前 ⇒ 导入即生效 ✓
from __future__ import annotations

from typing import Any, Dict

__all__ = ['log_console', 'log_once', 'log_kpi_read_err']

_ONCE_KEYS: Dict[str, bool] = {}

# 统一的日志出口
def log_console(message: Any) -> None:
    print(message, flush=True)

# 同一个小标签只打印一次
def log_once(key: str, message: Any) -> None:
    if not _ONCE_KEYS.get(key):
        _ONCE_KEYS[key] = True
        log_console(message)


# 读取楼栋数据失败时的告警
def log_kpi_read_err(name: str, exc: BaseException) -> None:
    log_once(
        'kpi_read_err',
        f'[中期评估] 读取楼栋量 {name} 失败: '
        f'{type(exc).__name__}: {exc}',
    )

import os
import sys
from pathlib import Path
from typing import Optional

__all__ = [
    'CITYLEARNPY_DIR',
    'patch_windows_resource_limits',
    'ensure_on_pythonpath',
    'prepare_ray_env',
    'ray_runtime_env',
]

# 本模块所在目录
_MODULE_DIR = Path(__file__).resolve().parent          # …/citylearnpy/utils
_PKG_ROOT = _MODULE_DIR.parent                         # …/citylearnpy
_HERE = _PKG_ROOT
_SHIM_DIRNAME = '_ray_win_shim'


# 找出 `_ray_win_shim` 目录
def _resolve_shim_dir() -> Optional[Path]:
    candidate = _HERE / _SHIM_DIRNAME
    if candidate.is_dir():
        return candidate
    env = os.environ.get('CITYLEARNPY_DIR')
    if env:
        fallback = Path(env) / _SHIM_DIRNAME
        if fallback.is_dir():
            return fallback
    return None


# 把一个目录同时写进 PYTHONPATH（子进程）与 sys.path（本进程）
def ensure_on_pythonpath(directory) -> None:
    d = str(Path(directory).resolve())
    pp = os.environ.get('PYTHONPATH', '')
    if d not in [p for p in pp.split(os.pathsep) if p]:
        os.environ['PYTHONPATH'] = d + (os.pathsep + pp if pp else '')
    if d not in sys.path:
        sys.path.insert(0, d)


# 根目录
CITYLEARNPY_DIR = _PKG_ROOT
ensure_on_pythonpath(_PKG_ROOT)


# 在 Windows 上补齐 Python 缺失的 resource 功能
def patch_windows_resource_limits() -> None:
    if sys.platform != 'win32':
        return

    # 让 Ray 子进程也能 import 到 shim
    shim_dir = _resolve_shim_dir()
    if shim_dir is not None:
        ensure_on_pythonpath(shim_dir)

    if 'resource' in sys.modules and not hasattr(sys.modules['resource'], 'getpagesize'):
        del sys.modules['resource']
    try:
        import resource as _resource
    except ImportError:
        return
    if not hasattr(_resource, 'RLIMIT_NOFILE'):
        _resource.RLIMIT_NOFILE = 7
    if not hasattr(_resource, 'getrlimit'):
        _resource.getrlimit = lambda _which: (8192, 8192)
    if not hasattr(_resource, 'setrlimit'):
        _resource.setrlimit = lambda _which, _limits: None
    if not hasattr(_resource, 'getpagesize'):
        _resource.getpagesize = lambda: 4096


# 启动 Ray 之前先做准备：打补丁 + 设置模块搜索路径 + 日志去重
def prepare_ray_env() -> None:
    patch_windows_resource_limits()
    ensure_on_pythonpath(_HERE)
    os.environ.setdefault('RAY_DEDUP_LOGS', '0')
    os.environ.setdefault('RAY_DISABLE_DASHBOARD', '1')


# 把父进程的 PYTHONPATH 等环境变量打包好，显式交给子进程用
def ray_runtime_env() -> dict:
    return {
        'env_vars': {
            'PYTHONPATH': os.environ.get('PYTHONPATH', ''),
            'RAY_DISABLE_DASHBOARD': os.environ.get('RAY_DISABLE_DASHBOARD', '1'),
        }
    }


# Ray 环境准备
patch_windows_resource_limits()

import warnings

import pandas as pd

pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

# torch 单线程
try:
    import torch as _torch
    TORCH_THREADS = max(1, int(os.environ.get('TORCH_NUM_THREADS', '1') or '1'))
    _torch.set_num_threads(TORCH_THREADS)
except Exception:
    TORCH_THREADS = None

# 防止乱码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# 忽略部分警告
warnings.filterwarnings('ignore', category=DeprecationWarning)
warnings.filterwarnings('ignore', category=UserWarning, module='gymnasium')
