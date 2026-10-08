# -*- coding: utf-8 -*-
# ⚠️ 本文件是**精简注释版**（由 `_gen_marl_split.py` 生成 ✓）：全部「详注块」已整段删除 ✓，
#    代码与同目录的 `X.detailed.py` **逐字相同** ✓（AST 一致 ⇒ 行为一致 ✓）。
#    **改注释请改 `.detailed.py` 那份** ✗（本文件每次生成都会被覆盖 ✗），改完重跑 `_gen_marl_split.py` ✓。
"""CHESCA 的「决策推演」落盘工具（2026-10-08 从 CHESCA.py 抽出 ✓）。

与 Multi-agent 那套**同一形式** ✓（见 `utils/report.py` 的 `MarlDecisionTraceRecorder` ✓）：

| 这一套（CHESCA ✓） | 对标（Multi-agent ✓） |
|---|---|
| `build_chesca_trace_recorder(n_buildings)` | `build_decision_recorder(env, *, enabled)` |
| `ChescaTraceWriter(...).save(env=None)` | `MarlDecisionTraceRecorder.save(path)` |
| `chesca_trace_path()` / `chesca_decision_trace_path()` | `decision_trace_path(env, output_dir)` |

谁在用 ✓：`CHESCA.py`（纯 CHESCA / ResMARL 两条路都走它 ✓）。
产出两个文件 ✓（格式与以前**逐字节一致** ✓，Java 任务详情页与 `tests/` 都读它们 ✓）：
  · `chesca_trace.csv`    — 逐步决策宽表
  · `decision_trace.json` — 供前端「决策推演」阅读的结构化日志
"""

import sys
from pathlib import Path
from typing import Optional

# 让本模块**可以独立 import** ✓（不依赖调用方先设 sys.path ✓）
_HERE = Path(__file__).resolve().parent.parent          # .../citylearnpy
for _p in (_HERE, _HERE / 'CHESCA-copy'):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from checa.trace_exporter import (
    ChescaTraceRecorder,
    save_chesca_trace,
    save_decision_trace_json,
)


def _log(message: str) -> None:
    # 立刻刷新：Java 端要实时看到（与 CHESCA.py 的 log_console 行为一致 ✓）
    print(message, flush=True)


# 逐步决策表写到哪（与 utils/report.py 的 decision_trace_path 同一形式 ✓）
def chesca_trace_path(output_dir) -> Path:
    return Path(output_dir) / 'chesca_trace.csv'


# 决策推演日志写到哪（同上 ✓）
def chesca_decision_trace_path(output_dir) -> Path:
    return Path(output_dir) / 'decision_trace.json'


# 建"决策推演"记录器（与 build_decision_recorder 同一形式 ✓；它由 Agent 逐步填充 ✓）
def build_chesca_trace_recorder(n_buildings: int) -> ChescaTraceRecorder:
    return ChescaTraceRecorder(n_buildings)


# 把 recorder 落成两个文件（**函数体原样搬自 CHESCA.py** ✓，只有日志函数换了名 ✓）
def save_chesca_trace_files(recorder: ChescaTraceRecorder, output_dir: Path, env=None) -> Optional[Path]:
    # 将 CHESCA / ResMARL 决策 trace 写入任务目录。
    # 输出：
    if recorder is None or not recorder.rows:
        _log('未收集到 CHESCA trace 数据，跳过 Decision Trace 导出')
        return None

    if env is not None and hasattr(recorder, 'backfill_hot_discomfort_from_env'):
        try:
            stats = recorder.backfill_hot_discomfort_from_env(env)
            _log(
                f'高温不适判定已按 evaluate 温度回填：'
                f'{stats.get("hot", 0)}/{stats.get("total", 0)} 步为是'
                f'（比例 {100 * float(stats.get("hot_rate", 0)):.1f}%）'
            )
        except Exception as exc:
            _log(f'高温不适回填失败（仍导出原剧本）: {exc}')

    out = Path(output_dir)
    csv_path = out / 'chesca_trace.csv'
    json_path = out / 'decision_trace.json'
    save_chesca_trace(recorder, csv_path)
    save_decision_trace_json(recorder, json_path)
    _log(f'CHESCA trace 文件: {csv_path.resolve()}')
    _log(f'决策推演日志: {json_path.resolve()}')
    return csv_path

# 工具类（与 MarlDecisionTraceRecorder.save 同一形式 ✓）：一处负责"把 recorder 落盘" ✓
class ChescaTraceWriter:
    def __init__(self, recorder: ChescaTraceRecorder, output_dir):
        self.recorder = recorder
        self.output_dir = Path(output_dir)

    def save(self, env=None) -> Optional[Path]:
        return save_chesca_trace_files(self.recorder, self.output_dir, env)
