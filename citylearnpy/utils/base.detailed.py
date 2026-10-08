# base = 三个入口共用的「启动靴」：日志工具 + 子进程/Ray 环境准备 + torch 单线程 + 编码与警告 ✓
# 用法：`from utils.base import …`，必须写在任何重库（numpy/pandas/torch/citylearn/ray）之前 ⇒ 导入即生效 ✓
# [详注-BEGIN]（生成简版时整段删除）
# """入口启动靴 entry_boot：三个入口**逐字相同**的那套"环境 / 单线程 / 显示"设置（2026-10-06 抽出 ✓）。
#
# 谁在用 ✗：`Multi-agent.py` / `Multi-agent-train.py` / `Multi-agent-eval.py` 各一行
# `from utils.base import TORCH_THREADS`（**导入即生效** ✓）
# ⚠️ 这一行必须写在**任何重库之前**（numpy / pandas / torch / gymnasium / citylearn / ray ✓）：
# 本模块一被 import 就立刻执行下面四件事 ✓ —— 这一条由门禁 `_q_eval_seg_diff.py`
# 的**顺序守卫**逐文件看着 ✓（坏掉的后果是**静默变慢** ✗，不会报错 ✗）。
#
# 本模块做四件事（原先散在各入口的模块级、内容逐字相同 ⇒ 现在只此一份 ✓）：
#
# ① **Ray 的 Windows 兼容补丁**：`patch_windows_resource_limits()`（utils/base.py ✓）
# 背景 ✗：Ray 的 worker.py 只捕获 `ImportError`，而本环境的 `resource` 是"能 import
# 但缺 API"的残缺模块 ⇒ 抛 `AttributeError` 冒到上层，症状是**续训静默退化成从头训练** ✗；
# 补丁做两件事 —— 把 `_ray_win_shim/`（内含 resource.py 替身）塞进 sys.path + PYTHONPATH
# （Ray 子进程靠它 ✓），并把当前进程缺的 4 个 API 就地补齐 ✓。非 Windows 直接空操作 ✓
# ⚠️ 必须是**调用**（带 `()` ✗✗）—— 只写函数名等于"引用了一下、没执行"，
# 症状与完全没打补丁一模一样 ✗（2026-10-06 手改时踩过 ✓）；
# ⚠️ 且必须早于 `import ray`（Ray 在 import / 拉起 worker 时就会走那条路径 ✓）⇒ 故放在本模块顶部 ✓
#
# ② **torch 单线程**：`TORCH_THREADS`（入口只拿它打一行日志 ✓）
# 为什么单线程 ✗：本任务的算子都极小（SAC learner 是 batch≈256 的 256×256 小网络；
# CityLearn 的 LSTM 动力学是逐楼 batch=1 前向）⇒ 线程开满只会互相抢锁空转
# （实测：进程 CPU/墙钟 ≈ 12.5）⇒ 单线程通常更快，且**不影响结果** ✓；想对比设
# `TORCH_NUM_THREADS=4` 环境变量即可 ✓。
# ⚠️ 线程 env 三行仍然留在**入口**里 ✗：它们必须早于 numpy / pandas / torch 的 import ✓
# （那是本模块**管不到**的最前一段 ✓，由门禁的顺序守卫看着 ✓）；
# ⚠️ 这里只影响 CPU 算子并行度 —— 该 learner 是"框架开销主导"，调它**不会**解决训练慢 ✗
#
# ③ **pd 显示选项**：列宽不换行（`display.max_columns / display.width` ✓）
# （评估入口那一份原先被 ev 补丁挪到 torch 块之后 ✓ —— 现在两处统一到本模块 ✓）
#
# ④ **兼容设置**：stdout / stderr 改 UTF-8（"防止乱码" ✓）+ `PYTHONIOENCODING` + 忽略两类警告 ✓
#
# ⚠️ 保持 **import-light** ✗✗：只许 `utils.base` + 标准库 + pandas / torch
# （不要在这里 import Ray / CityLearn / gymnasium ⇒ 否则三个入口的启动成本都会变 ✗）。
# ⚠️ 依赖前提 ✗：入口必须先做完 `sys.path` 引导（那 1 行"先有鸡还是先有蛋"的引导 ✓、
# 写在 `os`/`pathlib` 之后、`utils.*` 之前 ✓）才能 import 本模块 ✓。
# """
# [详注-END]
from __future__ import annotations
# [详注-BEGIN]（生成简版时整段删除）
# 运行环境：日志出口 / Windows 资源补丁 / Ray 环境 / 子进程 import 预检
#
# 本文件由 utils/ 下多个模块合并而来（2026-10-06 ✓，合并映射见每段横幅 ✓）：
#   · log_utils（日志出口 ✓，见下方同名段）
#   · process_env（Windows resource 补丁 / PYTHONPATH / Ray 环境 ✓，见下方同名段）
#   · entry_boot（本段：pd 显示选项 + torch 单线程 + 编码与警告 ✓）
# [详注-END]
# [详注-BEGIN]（生成简版时整段删除）
# 日志打印相关方法（公共模块）
# =====================================================================
#
# 本文件**只放"打印日志"这一件事**，供三个入口脚本共同使用：
#
#     Multi-agent.py          （训练 + 评估 一体化，同时也是生成器的源文件）
#     Multi-agent-train.py    （只训练，由 _gen_marl_split.py 生成）
#     Multi-agent-eval.py     （只评估，由 _gen_marl_split.py 生成）
#
# 为什么单独成文件
# ----------------
# 1. **唯一出口**：全项目日志都走 `log_console()`（= print + flush）。集中到一处后，
#    将来要改日志形态（加时间戳 / 加前缀 / 落文件 / 降噪 / 按级别过滤），
#    只改这一个函数即可，不必去三个入口脚本里各改一遍 ✓
# 2. **任何进程都能安全 import**：本文件**只依赖标准库**（不 import torch / citylearn /
#    ray）⇒ RLlib 的 worker 进程、奖励模块、独立小脚本都可以放心用它打日志 ✓
# 3. **"只报一次"这类的状态，放在模块里才正确**：这类状态必须"模块级、进程内唯一"。
#    原先它写在主脚本里，而主脚本会被复制成三个入口 ⇒ 同一份状态在三个文件里各存一份。
#    抽到本模块后，由 Python 的**模块导入缓存**保证全进程只有一份 ✓
#
# 用法
# ----
#     from utils.log_utils import log_console, log_once, log_kpi_read_err
#
#     log_console('普通一行日志')                      # 唯一日志出口
#     log_once('某问题', '这条同 key 在进程内只出现一次')
#     log_kpi_read_err('occupant_count', exc)          # 读取楼栋量失败的告警
#
# 维护约定（重要）
# ----------------
# - **不要**在本文件里 import 项目内的其它模块 ✗ —— 那些模块反过来要 import 本文件，
#   一旦反向依赖就会形成循环导入。
# - 本文件必须位于 citylearnpy 目录下：入口脚本靠 `CITYLEARNPY_DIR` 把它注入
#   sys.path 后再 import（脚本被 Java 复制到任务目录执行时也要能找得到）✓
# [详注-END]

from typing import Any, Dict

__all__ = ['log_console', 'log_once', 'log_kpi_read_err']

_ONCE_KEYS: Dict[str, bool] = {}

# 统一的日志出口
def log_console(message: Any) -> None:
    # [详注-BEGIN]（生成简版时整段删除）
    # 统一日志出口：打印一行，并**立即 flush**。
    #
    # 参数
    # ----
    # message : 任意可打印对象（调用方通常传 f-string）。
    #
    # 为什么必须 flush
    # ----------------
    # Java 平台是**边读 stdout 边解析**的：KPI 靠 `outputkpi` 协议行、进度靠普通日志行。
    # 若把输出留在缓冲区里，平台可能读不到或延迟读到 ⇒ 一律立即刷新 ✓
    # （这也是本函数不能简单换成 `print` 的原因 —— 少写一次 flush 就会改变平台行为。）
    #
    # [详注-END]
    print(message, flush=True)

# 同一个小标签只打印一次
def log_once(key: str, message: Any) -> None:
    # [详注-BEGIN]（生成简版时整段删除）
    # 同一个 key 在**整个进程内只打印一次**，之后同 key 的调用静默返回。
    #
    # 参数
    # ----
    # key     : 去重键。同一个 key 只报一次；不同 key 各自独立计数。
    #           ⚠️ 应当用「问题类别」当 key（如 'kpi_read_err'），
    #              **不要**把楼栋号 / 步号编进去 —— 那样每次 key 都不同，去重会失效 ✗
    # message : 要打印的内容。
    #
    # 返回
    # ----
    # None（纯副作用函数）。
    #
    # 用途
    # ----
    # 某些告警会在**逐步循环**里反复触发（每一步、每一栋都可能失败）。每次都打会刷屏
    # （本仓库历史上出现过"同一个问题一次刷 2000+ 行"），而**首条信息量最大**：
    # 异常类型 + 消息已经足够定位根因，重复出现的信息量为 0 ⇒ 只留第一条 ✓
    #
    # [详注-END]
    if not _ONCE_KEYS.get(key):
        _ONCE_KEYS[key] = True
        log_console(message)


# 读取楼栋数据失败时的告警
def log_kpi_read_err(name: str, exc: BaseException) -> None:
    # [详注-BEGIN]（生成简版时整段删除）
    # 读取楼栋/环境某个量失败时的告警：**整个进程只提示一次**。
    #
    # （原为 Multi-agent.py 内的 `_log_kpi_read_err(name, exc)` 与模块级标志
    #   `_KPI_READ_ERR_LOGGED`，2026-10-02 抽到本模块。行为、日志格式与
    #   `[中期评估]` 前缀**完全不变**，历史排查经验继续适用 ✓）
    #
    # 参数
    # ----
    # name : 正在读取的属性名，例如 'indoor_dry_bulb_temperature'、
    #        'indoor_dry_bulb_temperature_cooling_set_point'、'comfort_band'、
    #        'occupant_count'。只在日志里用于指出"哪个量读失败了"。
    # exc  : 捕获到的异常对象。本函数只取 `type(exc).__name__`（异常类型名）
    #        与 `str(exc)`（异常消息）打进日志。
    #
    # 返回
    # ----
    # None（不改变任何计算结果，调用方照旧继续执行）。
    #
    # 调用方约定（很重要）
    # --------------------
    # **只有"读取过程抛异常"才调用本函数**；
    # 下面这些属于"读不到"的正常情况，**不要**调用 ✗：
    #   · 该楼根本没有这个属性（getattr 返回 None）
    #   · 读到的东西转不成数值数组、数组为空
    #   · 所有候选都试完后返回 NaN
    # 这些由上层按 NaN 处理（例如 `if not np.isfinite(T): continue`），不是错误。
    #
    # 典型日志
    # --------
    # [中期评估] 读取楼栋量 occupant_count 失败（后续不再重复）: AttributeError: ...
    #
    # [详注-END]
    log_once(
        'kpi_read_err',
        f'[中期评估] 读取楼栋量 {name} 失败: '
        f'{type(exc).__name__}: {exc}',
    )
# [详注-BEGIN]（生成简版时整段删除）
# Windows 兼容：补齐 stdlib ``resource`` 缺失的 Unix API（Ray 会用到）
# =====================================================================
#
# 要解决的问题（真实症状）
# ------------------------
# ``ray/_private/worker.py`` 的 ``_connect()`` 里写着：
#
#     try:
#         import resource
#         soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
#     except ImportError:          # 作者假设：Windows 上 import resource 会失败
#         pass
#
# 但本环境里 ``import resource`` 是**能成功的**（一个 ``__file__ = None`` 的残缺
# 命名空间模块），只是**没有** ``getrlimit`` / ``getpagesize`` ⇒ 抛的是
# **AttributeError 而不是 ImportError** ✗ ⇒ 不被那个 ``except`` 捕获、直接冒到上层。
# 症状（最难查的一类：静默降级）：
#
#     [续训] 恢复失败（AttributeError: module 'resource' has no attribute 'getrlimit'）
#            → 改为从头训练
#
# 本模块做两件事
# --------------
# **① 让 Ray 子进程也能 import 到 shim**
#     同目录下的 ``_ray_win_shim/``（内含一个 508 字节的 ``resource.py`` 桩，提供
#     ``RLIMIT_*`` 常量与 ``getrlimit/setrlimit/getpagesize``）会被同时写进
#     **PYTHONPATH**（Ray worker / dashboard 是**独立进程**，只继承环境变量与工作目录）
#     与 **sys.path**（当前进程）。
#
#     ⚠️ shim 位置用**本模块自己的** ``__file__`` 定位 —— 本模块固定在
#     ``citylearnpy/utils/`` 下 ⇒ 取 ``parent.parent`` 得**包根目录** ``citylearnpy/``
#     （shim 在 ``citylearnpy/_ray_win_shim/`` ✓，永远指向正确位置 ✓）；
#     而调用方脚本可能被 Java 复制到 ``output/outkpis/<taskId>/`` 再执行，
#     它们的 ``__file__`` 指向任务目录 ✗（那里没有 shim）。
#     若定位不到，再退回环境变量 ``CITYLEARNPY_DIR`` 兜底 ✓
#
# **② 给当前进程就地补齐缺失的 API**
#     先丢掉"残缺的 resource"（若已 import 且没有 ``getpagesize``），再重新 import
#     （这时会拿到 shim 的那一份），然后**缺什么补什么**。补的值都是无害的假值：
#     Ray 只拿它们做日志/上限检查，不会真的去改系统限制 ✓
#
# 用法（重要）
# ------------
#     from utils.process_env import patch_windows_resource_limits
#     patch_windows_resource_limits()      # ⚠️ 必须在 import ray / ray.init 之前调用
#     import ray                           # 之后才能安全 import / 初始化 Ray
#
# - **幂等**：重复调用无害（每项都先 ``hasattr`` 判断）✓
# - **非 Windows**：第一行就 ``return`` ⇒ 完全空操作 ✓（所以在 Linux 上留着没有代价 ✓）
# - **只依赖标准库** ✓ ⇒ worker 进程、任何小脚本都能安全 import ✓
# - 本模块**import 时就会自动打一次补丁**（它存在的意义就是那个副作用），
#   同时导出函数供调用方在 "import ray 之前" 再显式调一次（更直观）✓
#
# 本模块还负责"Ray 启动前的环境准备"
# ---------------------------------
# ``prepare_ray_env()``（2026-10-02 从 ``multi_agent_runner_copy.ensure_ray_initialized``
# 收拢进来）做三件事：
#
#     ① 打 resource 补丁（见上）；
#     ② 把 citylearnpy 写进 PYTHONPATH / sys.path ⇒ Ray worker 才能 import
#        ``custom_comfort_reward`` / ``process_env`` / ``log_utils`` 等本地模块；
#     ③ 设两个 Ray 环境变量：
#        · ``RAY_DISABLE_DASHBOARD=1`` —— 关掉 dashboard（Windows 上 prometheus 侧
#          容易崩，是历史踩过的坑）
#        · ``RAY_DEDUP_LOGS=0`` —— 关掉日志去重，便于排查启动问题
#        两条都走 ``setdefault`` ⇒ 用户显式设过就尊重用户 ✓
#
# ``ray_runtime_env()``：把上面那份环境**显式传给 Ray worker 子进程**（worker 是独立
# 进程，只继承环境变量、不带父进程的 sys.path ✗）。
#
# 调用方（一处实现，多处共用）
# ----------------------------
#     Multi-agent.py / Multi-agent-train.py / Multi-agent-eval.py
#         ``patch_windows_resource_limits()`` —— 模块级，紧挨在 import ray 之前
#     multi_agent_runner_copy.py
#         ``prepare_ray_env()`` —— 模块级 + ``ensure_ray_initialized()`` 内各一次
#
# （2026-10-02 从上述文件抽出：原先这几处各存一份实现、靠注释提醒"两处改动请同步" ✗，
# 抽取后项目里只剩这一份 ✓）
# [详注-END]

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
# [详注-BEGIN]（生成简版时整段删除）
# ⚠️ 刻意用**本模块的** __file__：本文件固定在 citylearnpy/utils 下、不会被复制到任务目录，
#    因此这里永远指向正确位置 ✓（调用脚本可能被复制，它们的 __file__ 不可靠 ✗）
#   ⚠️ 2026-10-02：本模块从 citylearnpy/ 移入 utils/ 后，**必须取 parent.parent** ——
#      shim（citylearnpy/_ray_win_shim）与 PYTHONPATH 注入要的都是**包根目录** ✓；
#      只注入 utils/ 的话，Ray worker 会 import 不到 custom_comfort_reward ✗
# [详注-END]
_MODULE_DIR = Path(__file__).resolve().parent          # …/citylearnpy/utils
_PKG_ROOT = _MODULE_DIR.parent                         # …/citylearnpy
_HERE = _PKG_ROOT
_SHIM_DIRNAME = '_ray_win_shim'


# 找出 `_ray_win_shim` 目录
def _resolve_shim_dir() -> Optional[Path]:
    # [详注-BEGIN]（生成简版时整段删除）
    # 定位 shim 目录：优先本模块同级目录，其次环境变量 CITYLEARNPY_DIR 兜底。
    # [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    # 把某个目录写进 PYTHONPATH（给 Ray 等**子进程**）与 sys.path（给当前进程）。
    #
    # 两者都必须做：Ray worker 是**独立进程**，不继承本进程的 sys.modules / sys.path，
    # 只继承环境变量 ⇒ 只改一处都无效 ✗
    #
    # 已存在则不动（幂等）✓ —— shim 目录与 citylearnpy 目录都用它 ✓
    #
    # [详注-END]
    d = str(Path(directory).resolve())
    pp = os.environ.get('PYTHONPATH', '')
    if d not in [p for p in pp.split(os.pathsep) if p]:
        os.environ['PYTHONPATH'] = d + (os.pathsep + pp if pp else '')
    if d not in sys.path:
        sys.path.insert(0, d)


# 根目录
# [详注-BEGIN]（生成简版时整段删除）
#   · 入口脚本**直接 import 这个名字** ✓ —— 它由**本模块的 __file__** 推出
#     （本文件固定在 citylearnpy/utils 下、不会被复制到任务目录 ✓）⇒ 比入口自己
#     "猜三个候选"更权威 ✓，三个入口也不必各写一份口径 ✗；
#   · 并在**本模块被 import 时**就把它挂到 sys.path / PYTHONPATH 上（幂等 ✓）。
#   ⇒ "找 citylearnpy 并挂上"这件事从此只此一处 ✓；入口只剩 1 行"把目录找出来"的引导 ✓
#     （那 1 行**删不掉** ✗✗：它必须先于 `from utils.base import …` 执行 ——
#      先有鸡还是先有蛋 ✓；平台复制执行时脚本目录里没有 utils/ ✗）。
# [详注-END]
CITYLEARNPY_DIR = _PKG_ROOT
ensure_on_pythonpath(_PKG_ROOT)


# 在 Windows 上补齐 Python 缺失的 resource 功能
def patch_windows_resource_limits() -> None:
    # [详注-BEGIN]（生成简版时整段删除）
    # 当前进程 + Ray 子进程：补齐 Windows 缺失的 ``resource`` API。
    #
    # ⚠️ 必须在 **import ray / ray.init 之前**调用（Ray 在 import 与拉起 worker 时就会
    #    走 ``resource.getrlimit(...)`` 那条路径）✓
    #
    # 幂等：重复调用无害；非 Windows 平台直接返回（空操作）✓
    #
    # [详注-END]
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
    # [详注-BEGIN]（生成简版时整段删除）
    # Ray 启动前的环境准备 —— ⚠️ 必须在 **import ray / ray.init 之前**调用（幂等）。
    #
    # 三件事（对应模块 docstring 顶部"本模块还负责…"一节）：
    #   ① Windows resource 补丁（patch_windows_resource_limits）
    #   ② 把**包根目录**（= citylearnpy，含 utils/ 与 shim）写进 PYTHONPATH / sys.path
    #      ⇒ Ray worker 子进程才能 import custom_comfort_reward / utils.* 等本地模块
    #   ③ 设两个 Ray 环境变量：RAY_DISABLE_DASHBOARD=1、RAY_DEDUP_LOGS=0
    #      （都走 setdefault ⇒ 用户显式设过就尊重用户 ✓）
    #   （原 ④ preflight_import_module() 已于 2026-10-07 删除 ✗ —— 它唯一的用户就是同日撤下的
    #     `--env-runners` 并行采样 ✓）
    #
    # [详注-END]
    patch_windows_resource_limits()
    ensure_on_pythonpath(_HERE)
    os.environ.setdefault('RAY_DEDUP_LOGS', '0')
    os.environ.setdefault('RAY_DISABLE_DASHBOARD', '1')


# 把父进程的 PYTHONPATH 等环境变量打包好，显式交给子进程用
def ray_runtime_env() -> dict:
    # [详注-BEGIN]（生成简版时整段删除）
    # 构造 ``ray.init(runtime_env=...)`` 的取值：把父进程环境**显式**传给 worker。
    #
    # 为什么需要：Ray worker 是独立进程，只继承环境变量、不带父进程的 sys.path ✗
    # ⇒ 在 Windows 上必须显式传 PYTHONPATH（里面含 ``_ray_win_shim`` 与 citylearnpy），
    # 否则 worker 里 ``import resource`` / ``import custom_comfort_reward`` 会失败 ✗
    #
    # 用法（仅 Windows 需要传）：``init_kwargs['runtime_env'] = ray_runtime_env()``
    #
    # [详注-END]
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
