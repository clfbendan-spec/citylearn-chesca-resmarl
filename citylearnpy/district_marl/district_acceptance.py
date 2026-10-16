# -*- coding: utf-8 -*-
"""验收口径（acceptance statistic）—— 把"训练曲线上取哪个数"从选点里独立出来。

【为什么要单独成模块】
--------------------------------------------------------------
现行 `best_score[0]` = 评估点上的 **min**，即 `best-over-epochs`。实测（见
`District-MARL-方案5/6/7-*.md` §6.4/§6.5）：
  · **单次训练内部**逐 epoch 摆动 std 0.02~0.053、range 达 0.132；
  · 跨次复跑同量级 ⇒ `min` 恰好是**把方差最大化的统计量**（min-of-noisy）。
后果：方案 5/6/7 的 27 组 A/B 效应量全部 < 该口径的分辨率 ⇒ "全不显著"里有相当
一部分来自**统计量选择**，而不是效应不存在。仅把口径换成"末 K 个评估点均值"（零新增
训练），`w150 vs w0` 的 p 就从 0.318 掉到 0.047，而两个**零效应对照仍停在 p≈0.84/0.92**
（不被污染）⇒ 换口径是有依据的、且不自欺的。

【与"选点/断点"的关系（重要）】
--------------------------------------------------------------
本模块**只影响"报告/比较"用哪个数**，**不影响**：
  · 训练本身（不碰梯度、奖励、环境）；
  · best-checkpoint 的挑选与落盘（仍按 `best_score`/`DISTRICT_BEST_METRIC` 的 min 口径，
    因为平台协议 `train_progress.json::best_score` 与 `multi_agent_resume/algorithm_state.pkl`
    都依赖它，改口径会破坏既有对齐）。
即：`best` 仍是"模型"，`mean_last3` 是"成绩"。

【默认口径】
--------------------------------------------------------------
`DISTRICT_ACCEPT_STAT = 'mean_last3'`（末 3 个评估点均值），`best` 作为参考一并落盘。

纯函数、无第三方依赖 ⇒ 可被分析脚本直接 import 复用。
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

# 支持的验收统计量
ACCEPT_STATS = ('mean_last3', 'mean_last', 'mean_all', 'best', 'final')

# 默认验收统计量与尾部窗口
DEFAULT_ACCEPT_STAT = 'mean_last3'
DEFAULT_ACCEPT_TAIL = 3


def _finite(v: Any) -> Optional[float]:
    """把任意值转成有限 float；转不了 / NaN / inf 一律返回 None。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # 不用 numpy 也可判断 NaN/Inf
    if f != f or f in (float('inf'), float('-inf')):
        return None
    return f


def _series(rows: Sequence[Mapping[str, Any]],
            metric: str) -> List[tuple]:
    """从 history 行里抽出 (epoch, metric) 序列，跳过缺值/非有限的点。"""
    out: List[tuple] = []
    for r in rows:
        if not isinstance(r, Mapping):
            continue
        val = _finite(r.get(metric))
        if val is None:
            continue
        ep = r.get('epoch')
        try:
            ep = int(ep)
        except (TypeError, ValueError):
            ep = len(out) + 1
        out.append((ep, val))
    return out


def _tail_mean(pairs: Sequence[tuple], k: int) -> Optional[Dict[str, Any]]:
    if not pairs:
        return None
    k = max(1, int(k))
    used = list(pairs[-k:]) if k < len(pairs) else list(pairs)
    vals = [v for _, v in used]
    return {
        'value': float(sum(vals) / len(vals)),
        'n': len(used),
        'epochs': [ep for ep, _ in used],
        'values': [float(v) for _, v in used],
    }


def summarize(rows: Sequence[Mapping[str, Any]],
              metric: str,
              tail: int = DEFAULT_ACCEPT_TAIL,
              tiebreak: Optional[str] = None,
              stat: str = DEFAULT_ACCEPT_STAT) -> Dict[str, Any]:
    """把一段 `history`（每轮一行）压成一份验收报告。

    参数
    ----
    rows     : district_train 落盘的 ``history``（list[dict]，每项含 'epoch' 与各 KPI）
    metric   : 主指标名（默认 `all_time_peak_average`），**越小越好**
    tail     : `mean_last3` 的窗口长度（默认 3）
    tiebreak : 次选指标名（仅作记录；本函数不参与排序）
    stat     : 哪个统计量作为 ``value`` 主口径，见 ``ACCEPT_STATS``

    返回
    ----
    dict，键：metric / stat / tail / value / n_used / epochs / mean_last3 /
    mean_all / best / best_epoch / final / final_epoch / usable。
    ``usable=False`` 表示序列为空（例如全程未跑过评估）。
    """
    pairs = _series(rows, metric)
    if not pairs:
        return {
            'metric': str(metric), 'stat': str(stat), 'tail': int(max(1, tail)),
            'value': None, 'n_used': 0, 'epochs': [], 'usable': False,
            'mean_last3': None, 'mean_all': None,
            'best': None, 'best_epoch': None, 'final': None, 'final_epoch': None,
            'tiebreak': (None if tiebreak is None else str(tiebreak)),
        }

    m_all = _tail_mean(pairs, len(pairs))
    m_last3 = _tail_mean(pairs, 3)
    m_last = _tail_mean(pairs, tail)
    best_ep, best_v = min(pairs, key=lambda t: t[1])
    final_ep, final_v = pairs[-1]

    # `mean_last` 是"按 tail 参数"的版本，别名到 mean_last{tail}
    named = {
        'mean_all': m_all,
        'mean_last3': m_last3,
        'mean_last': m_last,
        'best': {'value': float(best_v), 'n': 1, 'epochs': [int(best_ep)],
                 'values': [float(best_v)]},
        'final': {'value': float(final_v), 'n': 1, 'epochs': [int(final_ep)],
                  'values': [float(final_v)]},
    }
    stat = str(stat) if str(stat) in ACCEPT_STATS else DEFAULT_ACCEPT_STAT
    picked = named.get(stat) or named['mean_last3']

    out: Dict[str, Any] = {
        'metric': str(metric),
        'stat': stat,
        'tail': int(max(1, tail)),
        'value': (None if picked is None else float(picked['value'])),
        'n_used': (0 if picked is None else int(picked['n'])),
        'epochs': ([] if picked is None else list(picked['epochs'])),
        'usable': True,
        'mean_last3': (None if m_last3 is None else float(m_last3['value'])),
        'mean_last3_epochs': ([] if m_last3 is None else list(m_last3['epochs'])),
        'mean_all': (None if m_all is None else float(m_all['value'])),
        'best': float(best_v),
        'best_epoch': int(best_ep),
        'final': float(final_v),
        'final_epoch': int(final_ep),
        'n_evals': len(pairs),
        'tiebreak': (None if tiebreak is None else str(tiebreak)),
    }
    if tiebreak is not None:
        tb = _series(rows, tiebreak)
        if tb:
            out['tiebreak_final'] = float(tb[-1][1])
    return out


def accept_value(summary: Mapping[str, Any],
                 fallback_to_best: bool = True) -> Optional[float]:
    """从 ``district_summary.json`` 里读**主验收值**（供 A/B 汇总脚本使用）。

    新格式：优先 `acceptance.value`
    旧格式（本改动之前落盘的 summary）：**回退**到 `best_score[0]`
      —— 保证历史产物仍可被同一套脚本读取，不制造"新旧不可比"。
    """
    if not isinstance(summary, Mapping):
        return None
    acc = summary.get('acceptance')
    if isinstance(acc, Mapping):
        v = _finite(acc.get('value'))
        if v is not None:
            return v
    if not fallback_to_best:
        return None
    bs = summary.get('best_score')
    if isinstance(bs, (list, tuple)) and bs:
        return _finite(bs[0])
    v = _finite(bs)
    return v


def accept_metric_name(summary: Mapping[str, Any]) -> str:
    """返回主验收统计量名（用于报告表头）；缺省按 'best' 处理（旧格式）。"""
    if isinstance(summary, Mapping):
        acc = summary.get('acceptance')
        if isinstance(acc, Mapping) and acc.get('stat'):
            return str(acc['stat'])
    return 'best'
