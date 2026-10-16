# -*- coding: utf-8 -*-
"""进程级确定性引导：把 `PYTHONHASHSEED` 固定下来（默认 0）。

【为什么必须"重新起进程"】
--------------------------------------------------------------
Python 只在**解释器启动时**读一次 `PYTHONHASHSEED`。进程跑起来之后
`os.environ['PYTHONHASHSEED'] = ...`（很多脚本都这么写）**完全无效** ——
这正是一个长期潜伏的坑：看起来设了种子，实际 str 哈希仍是随机的。

而 `str` 的 `hash()` 每进程不同 ⇒ 任何**裸 `set()` / 文本键 `dict` 的迭代次序**
在进程间不同 ⇒ 观测/动作次序被置换 ⇒ 学习轨迹分岔。实测（见
`District-MARL-方案7-尖峰充放计价A-B.md` §6.9）：

  · 同一 hash seed ⇒ 训练**逐位可复现**（N=8 时 14/14；100 轮 × 3 路逐位相同）；
  · 不同 hash seed ⇒ 落到不同但**各自可复现**的轨迹；
  · 不固定 ⇒ 同 config + 同 seed 复跑 8 次的 `std=0.039 / range=0.089`
    —— 大于全部 6 个 A/B 对比的效应量（≤0.053）。

⇒ 不固定它，**同一 A/B 的每次复跑都等价于换了一个随机源**，实验会白跑。
本模块用"'未设置就把自己重启一次"的方式把种子真正钉住（零算法改动、
不影响吞吐；模型是极小 MLP，多一次进程启动约 2~5 秒）。

【开关与尊重原则】
--------------------------------------------------------------
取值优先级（高 → 低）：
  1. 命令行 `--hashseed <v>`（预扫描 argv，因此不依赖 argparse）；
  2. **已经显式设置的 `PYTHONHASHSEED` 环境变量** —— 原样尊重，**绝不覆盖**
     （上级脚本 / 用户显式指定优先；`PYTHONHASHSEED=random` 也按"不干预"处理）；
  3. 环境变量 `DISTRICT_HASHSEED`；
  4. 默认 `'0'`。
值取 `random` / `none` / `off` / `''` / `-1` / `no` / `false` ⇒ **不干预**（保留原生随机哈希）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Optional, Sequence

#: 认为"不要固定"的取值
_NOOP_VALUES = frozenset({'', 'random', 'none', 'off', '-1', 'no', 'false'})

#: 重入保护标记（防止 exec 后因环境异常无限自我重启）
_GUARD_ENV = '_DISTRICT_HASHSEED_REEXEC'

#: 默认固定的哈希种子
DEFAULT_HASHSEED = '0'


def _prescan_arg(argv: Sequence[str], name: str) -> Optional[str]:
    """在 argparse 之前从 argv 里扫出一个选项的值（支持 `--x=v` 与 `--x v`）。"""
    flag = '--' + name
    toks = list(argv)
    for i, tok in enumerate(toks):
        if tok == flag and i + 1 < len(toks):
            return toks[i + 1]
        if tok.startswith(flag + '='):
            return tok.split('=', 1)[1]
    return None


def desired_hashseed(argv: Optional[Sequence[str]] = None,
                     default: str = DEFAULT_HASHSEED) -> str:
    """按优先级算出"想固定的哈希种子"。

    顺序：``--hashseed``（CLI）> 已设置的 ``PYTHONHASHSEED``（尊重，不覆盖）
    > ``DISTRICT_HASHSEED`` > ``default``。
    """
    val = _prescan_arg(sys.argv if argv is None else argv, 'hashseed')
    if val is not None:
        return str(val).strip()
    cur = os.environ.get('PYTHONHASHSEED')
    if cur is not None and str(cur).strip() != '':
        return str(cur).strip()          # 显式指定过 ⇒ 原样尊重（含 'random'）
    val = os.environ.get('DISTRICT_HASHSEED', default)
    return '' if val is None else str(val).strip()


def hashseed_is_noop(value: str) -> bool:
    return value.strip().lower() in _NOOP_VALUES


def ensure_hashseed(argv: Optional[Sequence[str]] = None,
                    default: str = DEFAULT_HASHSEED,
                    reexec: bool = True) -> str:
    """确保当前进程的 `PYTHONHASHSEED` == 期望值；不一致则**重启进程**。

    返回最终生效的值（``''`` 表示"未固定"）。
    仅在脚本以 ``__main__`` 运行时应调用 —— 作为库被 import 时调用会重启宿主进程。
    """
    want = desired_hashseed(argv, default)
    if hashseed_is_noop(want):
        return ''

    cur = os.environ.get('PYTHONHASHSEED')
    if cur == want:
        return want                      # 已经是目标值（典型：re-exec 后的子进程）

    if os.environ.get(_GUARD_ENV) == '1':
        # 已经重启过一次却仍不是目标值 ⇒ 放弃（避免无限重启），显式提示
        print(f'[hashseed] 二次进入仍未生效（PYTHONHASHSEED={cur!r}，'
              f'期望 {want!r}）⇒ 本次不做固定，结果可能不可复现。',
              file=sys.stderr)
        return cur or ''

    if not reexec:
        return cur or ''

    env = dict(os.environ)
    env['PYTHONHASHSEED'] = want
    env[_GUARD_ENV] = '1'
    cmd: List[str] = [sys.executable, *sys.argv]
    try:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        rc = subprocess.call(cmd, env=env)
    except OSError as exc:                # 起不来也不致命：继续跑（只是失去逐位可复现）
        print(f'[hashseed] 重启进程失败（忽略，本次不固定哈希种子）: {exc}',
              file=sys.stderr)
        return cur or ''
    sys.exit(rc)


def active_hashseed() -> str:
    """当前进程实际生效的哈希种子（未设置时返回 ``''``，表示原生随机）。"""
    return os.environ.get('PYTHONHASHSEED', '') or ''


def describe() -> str:
    """给日志用的一行说明。"""
    v = active_hashseed()
    if not v:
        return 'PYTHONHASHSEED 未设置（哈希随机 ⇒ 结果不可复现）'
    if hashseed_is_noop(v):
        return f'PYTHONHASHSEED={v}（显式要求不干预 ⇒ 哈希随机，结果不可复现）'
    return f'PYTHONHASHSEED={v}（已固定 ⇒ 同 config+同 seed 逐位可复现）'
