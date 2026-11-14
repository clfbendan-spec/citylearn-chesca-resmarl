# -*- coding: utf-8 -*-
r"""第三方库噪声警告抑制（District-MARL 训练 / 评估入口专用）。

【为什么必须在入口最早期调用】
  实测一次 320 轮训练（见 output/outkpis/*/output.log），日志里 90% 的警告行
  是**import 阶段**产生的：

    · protobuf   → `UserWarning: Protobuf gencode version 5.28.3 is exactly one
                    major version older than the runtime version` —— 一次运行 40+ 条
    · requests   → `RequestsDependencyWarning: Unable to find acceptable
                    character detection dependency`（缺 charset 检测依赖）
    · ray        → `DeprecationWarning: rllib/algorithms/simple_q/ has been deprecated`
                   `... multi_gpu_train_one_step has been deprecated`
    · tensorflow → `tf.logging.set_verbosity is deprecated`

  这些都发生在 `from district_marl.district_train import main` 那一行里。
  等 import 完再过滤，警告早就打出来了 ⇒ 必须放在该 import **之前**。

【两条通道，缺一不可】
  ① `warnings` 模块 ← protobuf / requests / gymnasium / h5py / matplotlib 走这条
  ② `logging` 模块  ← ray / tensorflow / absl 的 `WARNING xxx.py:12 -- ...` 走这条

  只压 ① 的话日志里仍有 `WARNING deprecation.py:50 -- ...` 这类行。
  这里用 `logging.disable(logging.WARNING)`：**WARNING 及以下全丢，ERROR 及以上保留**。
  之所以不用 `logging.getLogger('ray').setLevel(...)`：`ray.init()` 会重新配置自己
  的 logger，按 logger 设会被打回原形；`logging.disable` 改的是 manager 级全局开关，
  任何 logger 都绕不过去。

【安全性核对（改这个模块前请重跑这两条）】
    grep -rn "warnings.warn"   district_marl/   → 空
    grep -rn "logger.warning(" district_marl/   → 空
  即包内关键输出全部走 `print`，抑制上述两条通道**不会吞掉本项目自己的任何提示**。

【唯一压不掉的一行】
    `Couldn't import dot_parser, loading of dot files will not be possible.`
  它来自 pydot 的 `print(..., file=sys.stderr)`，既不是 warning 也不是 logging。
  只有一行，不影响阅读。

【打开全部输出（排查第三方库问题时）】
    python District_MARL_train.py --verbose-warnings
    DISTRICT_MARL_WARNINGS=1 python District_MARL_train.py
"""

import logging
import os
import sys
import warnings

#: 环境变量开关：取值 1/true/yes/on/enable/enabled ⇒ **不**抑制（等同 --verbose-warnings）
ENV_VERBOSE = 'DISTRICT_MARL_WARNINGS'

#: 命令行开关（本模块会把它从 argv 里摘掉，不污染下游 argparse）
FLAG_VERBOSE = '--verbose-warnings'

_TRUTHY = frozenset({'1', 'true', 'yes', 'on', 'enable', 'enabled'})

#: 「已提示过」标记 —— hashseed 引导会重启一次子进程，靠它避免同一句提示打两遍
_ANNOUNCED_ENV = '_DISTRICT_MARL_QUIET_ANNOUNCED'

#: 决定结果缓存：None=尚未决定；True=抑制中；False=用户要看全部
#: （--verbose-warnings 会被摘出 argv，不缓存的话第二次调用会误判成"该抑制"）
_quiet = None


def _take_flag(argv):
    """从 argv 里就地摘掉 FLAG_VERBOSE，返回是否出现过。"""
    hit = False
    while FLAG_VERBOSE in argv:
        argv.remove(FLAG_VERBOSE)
        hit = True
    return hit


def _env_verbose():
    return (os.environ.get(ENV_VERBOSE) or '').strip().lower() in _TRUTHY


def quiet_warnings(argv=None):
    """抑制第三方库的 WARNING；幂等。

    返回当前进程是否处于「抑制」状态（False = 用户显式要求看全部）。
    `argv` 缺省为 `sys.argv`（会被就地修改，摘掉 `--verbose-warnings`）。
    """
    global _quiet
    if _quiet is not None:
        return _quiet

    argv = sys.argv if argv is None else argv

    # --verbose-warnings 要「摘掉 + 转写成环境变量」两件事都做：
    #   摘掉 —— 免得下游 argparse 报未知参数；
    #   转写 —— `_hashseed.ensure_hashseed()` 会用 `[sys.executable, *sys.argv]`
    #           重启一次子进程，若只摘不转写，子进程看不到这个标志，反而会按抑制
    #           分支走（实测就是它把 verbose 吃掉了）。env 会被那次 subprocess 继承。
    if _take_flag(argv):
        os.environ[ENV_VERBOSE] = '1'
    if _env_verbose():
        _quiet = False
        return False

    # ---- ① warnings 通道 ----
    warnings.filterwarnings('ignore')
    # 让 hashseed 重启出的子进程、以及后续任何 subprocess 继承同一口径
    os.environ.setdefault('PYTHONWARNINGS', 'ignore')
    # tensorflow / absl 的 C++ 层日志：0=全开 1=去INFO 2=去WARNING 3=只留FATAL
    os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')

    # ---- ② logging 通道 ----
    logging.disable(logging.WARNING)

    _quiet = True
    if not os.environ.get(_ANNOUNCED_ENV):
        os.environ[_ANNOUNCED_ENV] = '1'
        print(
            '[district-marl] 已抑制第三方库警告（protobuf / requests / ray / tensorflow）；'
            '要看全部请加 --verbose-warnings',
            file=sys.stderr,
        )
    return True
