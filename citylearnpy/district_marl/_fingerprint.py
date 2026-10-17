# -*- coding: utf-8 -*-
"""训练/评估产物的「指纹」采集 —— 环境版本 + 机器信息 + 源码哈希。

为什么需要
----------
`PYTHONHASHSEED` 固定之后，同一台机器上「同 config + 同 seed」已经能逐位复现；
但**跨机器、跨时间**仍会漂移，原因是三类无法从 KPI 里看出来的变量：

  1. **依赖版本**：ray / numpy / torch / citylearn 细节行为随版本变化
     （例如 SAC 的 target 更新顺序、numpy 的归约顺序），会让同一 seed 走出不同轨迹；
  2. **机器**：CPU 型号 / 核心数 / 内存 / BLAS 后端不同，浮点累加顺序不同 ⇒
     结果差异可能被误读成「算法改动的效果」；
  3. **源码**：同一个 `district_train.py` 文件名下，本地可能已被改过 N 次。
     git 未提交的改动（dirty）尤其致命 —— 报告里写「v4」，代码却不是 v4。

本模块只做**只读采集**，不改变任何训练/评估行为，全部取值都有兜底：
任何一项取不到就是 `None`，绝不抛异常。

用法
----
    from district_marl._fingerprint import fingerprint_block
    block = fingerprint_block()          # {'code': {...}, 'runtime': {...}}
    log_console(fingerprint_line(block)) # 一行人类可读摘要
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

__version__ = '1.0.0'

#: 判定「代码版本」时纳入哈希的源码（相对 citylearnpy 目录）。
#: 只挑真正影响训练轨迹的：算法入口、环境、奖励、常量、验收口径、哈希引导。
SOURCE_FILES: tuple = (
    'district_marl/district_train.py',
    'district_marl/district_env.py',
    'district_marl/district_reward.py',
    'district_marl/district_config.py',
    'district_marl/district_acceptance.py',
    'district_marl/_hashseed.py',
    'district_marl/_fingerprint.py',
)

#: 需要记录版本的第三方包（importlib.metadata 的分布名）。
#: 全部用 metadata 查询，不 import 模块 ⇒ 不会拖慢启动，也不会引入额外副作用。
PACKAGES: tuple = (
    ('ray', 'ray'),
    ('numpy', 'numpy'),
    ('torch', 'torch'),
    ('gymnasium', 'gymnasium'),
    ('gym', 'gym'),
    ('citylearn', 'citylearn'),
    ('pandas', 'pandas'),
    ('scipy', 'scipy'),
)


# =============================================================================
# 小工具：所有取值都必须"取不到就 None"，绝不抛
# =============================================================================

def _try(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _all_versions(names: Iterable[str]) -> Dict[str, Optional[str]]:
    """一次遍历 site-packages 取全部版本（不 import 模块，无副作用）。

    逐个调 `importlib.metadata.version()` 每次都会重扫目录，8 个包约 1 s；
    这里改成扫一次建表，整体降到毫秒级。
    """
    wanted = {str(n).lower().replace('-', '_') for n in names}
    found: Dict[str, Optional[str]] = {}
    try:
        from importlib.metadata import distributions
        for dist in distributions():
            try:
                name = str(dist.metadata['Name'] or '').lower().replace('-', '_')
            except Exception:
                continue
            if name in wanted and name not in found:
                found[name] = str(dist.version)
    except Exception:
        pass
    return {str(n): found.get(str(n).lower().replace('-', '_')) for n in names}


def _git(args: Iterable[str], cwd: Path) -> Optional[str]:
    def _inner():
        proc = subprocess.run(
            ['git', *args], cwd=str(cwd), capture_output=True, text=True,
            timeout=8, encoding='utf-8', errors='replace')
        if proc.returncode == 0:
            return proc.stdout.strip()
        return None
    return _try(_inner)


def _sha256_file(path: Path, limit: int = 0) -> Optional[str]:
    """文件 sha256 前 16 位。`limit>0` 时只读前 N 字节（大文件用）。"""
    if not path.is_file():
        return None

    def _inner():
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            remaining = limit
            while True:
                chunk = f.read(1 << 20 if remaining <= 0 else min(1 << 20, remaining))
                if not chunk:
                    break
                h.update(chunk)
                if remaining > 0:
                    remaining -= len(chunk)
                    if remaining <= 0:
                        break
        return h.hexdigest()[:16]
    return _try(_inner)


def _cpu_model() -> Optional[str]:
    """CPU 型号。Windows 走注册表（`platform.processor()` 常常返回空串）。"""
    def _inner():
        if sys.platform.startswith('win'):
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'HARDWARE\DESCRIPTION\System\CentralProcessor\0')
            try:
                val, _ = winreg.QueryValueEx(key, 'ProcessorNameString')
            finally:
                winreg.CloseKey(key)
            val = ' '.join(str(val).split())
            if val:
                return val
        # 非 Windows 或注册表读不到：退回 platform / /proc
        val = platform.processor() or ''
        if not val and Path('/proc/cpuinfo').is_file():
            for line in Path('/proc/cpuinfo').read_text(
                    encoding='utf-8', errors='replace').splitlines():
                if line.lower().startswith('model name'):
                    return line.split(':', 1)[1].strip()
        return val or None
    return _try(_inner)


def _ram_gb() -> Optional[float]:
    """物理内存总量（GB）。优先 psutil，其次各平台兜底。"""
    def _inner():
        try:
            import psutil
            return round(psutil.virtual_memory().total / (1024 ** 3), 1)
        except Exception:
            pass
        if sys.platform.startswith('win'):
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong),
                            ('dwMemoryLoad', ctypes.c_ulong),
                            ('ullTotalPhys', ctypes.c_ulonglong),
                            ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong),
                            ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong),
                            ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]

            st = _MemStatus()
            st.dwLength = ctypes.sizeof(_MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return round(st.ullTotalPhys / (1024 ** 3), 1)
            return None
        return round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
                     / (1024 ** 3), 1)
    return _try(_inner)


def _cpu_count() -> Optional[int]:
    return _try(lambda: int(os.cpu_count() or 0) or None)


# =============================================================================
# 对外接口
# =============================================================================

def code_env_fingerprint(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """代码与依赖版本指纹。

    包含：
      · python / platform 版本
      · `PACKAGES` 的版本
      · git commit（短）+ 是否 dirty + 分支名（非 git 仓库时为 None）
      · `SOURCE_FILES` 的 sha256 前 16 位（**不依赖 git**，本地改动也能看出来）

    为什么同时给 git 和源码哈希：git 只能反映"已提交"的状态；平台上是整包拷贝的
    目录，可能根本不是 git 仓库。源码哈希在任何情况下都成立，是最终依据。
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]

    code: Dict[str, Any] = {
        'python_version': sys.version.split()[0],
        'python_impl': platform.python_implementation(),
        'platform': platform.platform(),
        'packages': _all_versions([d for d, _ in PACKAGES]),
        'source_sha256_16': {},
    }

    # ---- 源码哈希（最终依据）----
    for rel in SOURCE_FILES:
        code['source_sha256_16'][rel] = _sha256_file(root / rel)
    # 目录级的「组合哈希」：任何一个文件变了它都会变 ⇒ 一句话比对两条运行
    joined = '|'.join(f'{k}={v}' for k, v in sorted(code['source_sha256_16'].items()))
    code['source_digest_16'] = _try(
        lambda: hashlib.sha256(joined.encode('utf-8')).hexdigest()[:16])

    # ---- git（可缺失）----
    code['git_commit'] = _git(['rev-parse', '--short=12', 'HEAD'], root)
    code['git_branch'] = _git(['rev-parse', '--abbrev-ref', 'HEAD'], root)
    # `--porcelain` 有输出 ⇒ 有未提交改动；此时上报的数字无法用 commit 号定位
    _dirty = _git(['status', '--porcelain', '--', *SOURCE_FILES], root)
    code['git_dirty'] = (bool(_dirty) if _dirty is not None else None)
    code['git_dirty_files'] = (
        sorted({ln[3:].strip() for ln in _dirty.splitlines() if ln.strip()})
        if _dirty else [])

    # ---- 入口脚本（解释器与 wrapper 名）----
    code['executable'] = _try(lambda: Path(sys.executable).name)
    code['argv0'] = _try(lambda: Path(sys.argv[0]).name)
    return code


def runtime_fingerprint() -> Dict[str, Any]:
    """机器与运行环境指纹。

    `cpu_model` / `cpu_count` / `ram_gb` 三项决定浮点归约与线程数；
    `cuda_visible_devices` 与 `nvidia_smi` 决定有没有 GPU 参与。
    """
    rt: Dict[str, Any] = {
        'hostname': _try(lambda: platform.node() or None),
        'machine': _try(lambda: platform.machine() or None),
        'os': _try(lambda: f'{platform.system()} {platform.release()}'),
        'cpu_model': _cpu_model(),
        'cpu_count': _cpu_count(),
        'ram_gb': _ram_gb(),
        'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
        'nvidia_smi': _try(lambda: shutil.which('nvidia-smi')),
    }
    # 线程池环境变量：BLAS 线程数不同会改变浮点累加顺序 ⇒ 必须留痕
    for env_key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS',
                    'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS',
                    'TORCH_NUM_THREADS'):
        rt[env_key.lower()] = os.environ.get(env_key)
    rt['torch_threads'] = _torch_threads()
    return rt


def _torch_threads() -> Optional[int]:
    """`utils.base` 在导入时把 torch 压到单线程（默认 TORCH_NUM_THREADS=1）。

    这个值是「浮点累加顺序」的直接决定因素之一 ⇒ 必须记录。
    优先从已加载的 `utils.base` 模块取（那就是真正生效的值），退回环境变量。
    """
    mod = sys.modules.get('utils.base')
    val = getattr(mod, 'TORCH_THREADS', None) if mod is not None else None
    if val is not None:
        return _try(lambda: int(val))
    return _try(lambda: int(os.environ.get('TORCH_NUM_THREADS', '1')))


def fingerprint_block(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """一次性取全（训练/评估产物里写入的就是这个结构）。"""
    return {
        'code': code_env_fingerprint(repo_root),
        'runtime': runtime_fingerprint(),
    }


def fingerprint_line(block: Optional[Dict[str, Any]] = None) -> str:
    """把指纹压成一行，写进 output.log（人眼可读、便于 grep）。"""
    b = block or {}
    code = b.get('code') or {}
    rt = b.get('runtime') or {}
    pkgs = code.get('packages') or {}
    bits = [
        f"py={code.get('python_version')}",
        f"ray={pkgs.get('ray')}",
        f"numpy={pkgs.get('numpy')}",
        f"torch={pkgs.get('torch')}",
        f"cl={pkgs.get('citylearn')}",
        f"src={code.get('source_digest_16')}",
        f"git={code.get('git_commit')}"
        + ('(dirty)' if code.get('git_dirty') else ''),
        f"cpu={rt.get('cpu_model')}×{rt.get('cpu_count')}",
        f"ram={rt.get('ram_gb')}G",
    ]
    return '  指纹       : ' + ' | '.join(str(x) for x in bits)
