# -*- coding: utf-8 -*-
"""区域级 MARL 的「决策推演日志」——产出与模型优选界面同构的 decision_trace.json。

为什么要有这一层
----------------
`district_marl` 原本只落两样东西：`district_trace_*.npz`（numpy 矩阵，供脚本分析）
和 `district_eval_diagnostics.json`（奖励分解 / 逐栋不适）。而「模型优选」页面读的是
`decision_trace.json`（version 2 / slim 结构），于是 district 任务在界面上
「决策推演」一栏是空的 —— 明明跑了整段，却看不到任何一步是怎么决策的。

本模块把逐时步的观测 / 动作 / 电池 SOC / 区域奖励翻译成**同一套结构**，
让 district 与 CHESCA、Multi-agent 在界面上长得一样（同一个滑块、同一个剧本面板）。

设计取舍
--------
  1) **复用而非重写**：building 条目与剧本行直接走 `utils.report.record_step_trace`
     → 格式、字段名、行序（`[观测动作]` 首行 / `[奖励计算]` / 状态行）与既有任务
     完全一致，前端 `resolveDecisionTrace` 无需任何改动。
     `[观测动作]` 这个前缀还有个副作用：前端见到它就不再注入 CHESCA 三段动作对照，
     正好符合"district 是纯 MARL、没有 CHESCA 基线动作"的事实。
  2) **只换 phases**：`utils.report` 的 phases 写死为"SAC 策略动作 → SymmetricComfortReward"，
     那是单栋 Multi-agent 的说法；district 要讲的是「区域上下文 → 逐栋动作 → 区域奖励分摊」，
     所以每步记录生成后覆盖 phases，并附上社区净负荷 / 峰值目标等区域字段。
  3) **动作记全三维**：district 的动作是「DHW / 电池 / 冷却」三维，而 `utils.report`
     的通用出口只写后两维（DHW 写死 0.0）。这里以 `include_all_actions=True` 建记录器，
     把 `actions.final` / `actions.raw` 全量写进去；同时补每栋 `dhw_soc`，
     并在 `district.exec_actions` 里按 agent 汇总一份执行动作，方便与 `raw_actions` 对照。
  4) **默认全量记录**：stride=1、max_records=0（不限）⇒ 走过多少步就记多少步。
     只有显式传参（`--no-decision-log` / `--decision-log-stride` / `--decision-log-max-steps`）
     才会变成"不记录 / 抽稀 / 截断"。

零侵入
------
  `build_decision_log(enabled=False)` 返回 None；`rollout_district` 拿到 None 时
  一行都不执行 ⇒ 既有产物（npz / diagnostics / KPI）逐位不变。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

__all__ = ['DistrictDecisionLog', 'build_decision_log', 'DECISION_TRACE_FILENAME']

DECISION_TRACE_FILENAME = 'decision_trace.json'

# "峰步"判据：达到本段峰值的 99.5% 即视作峰步。**纯展示用**——
# 只写进日志给人看，不参与任何选点、KPI 或奖励计算（避免又造出一个"事后口径"）。
_PEAK_STEP_RATIO = 0.995


def _fmt(v: Any, d: int = 3) -> str:
    """数值格式化（None / nan 统一给 '-'，与 utils.report 的风格一致）。"""
    try:
        if v is None:
            return '-'
        f = float(v)
        if f != f:  # nan
            return '-'
        return f'{f:.{d}f}'
    except (TypeError, ValueError):
        return '-'


class DistrictDecisionLog:
    """逐时步收集 district 决策推演，结束时写成 decision_trace.json。

    参数
    ----
    n_buildings    社区楼栋数（只用于顶层字段）
    reward_label   奖励函数名（打印在 phases 与顶层 meta 里）
    reward_kwargs  奖励超参快照（可选，写进顶层便于回溯；不参与展示逻辑）
    stride         每多少步记一条（1 = 逐步，默认）
    max_records    最多记多少条（0 = 不限制，默认）；达到上限会停止采集并标 truncated
    """

    def __init__(
        self,
        n_buildings: int,
        *,
        reward_label: str = 'DistrictPeakReward',
        reward_kwargs: Optional[Mapping[str, Any]] = None,
        stride: int = 1,
        max_records: int = 0,
    ):
        # 延迟 import：district_eval 会先做 sys.path 引导与 ray 环境准备，
        # 模块级 import utils.* 在部分包装脚本下会过早拉起重依赖。
        from utils.report import MarlDecisionTraceRecorder

        self.n_buildings = int(n_buildings)
        self.reward_label = str(reward_label or 'DistrictPeakReward')
        self.reward_kwargs = dict(reward_kwargs or {})
        self.stride = max(1, int(stride))
        # 0 = 不限制（默认）：decision_trace 要能回答"每一步每次动作是什么"，
        # 预先截断会让界面上后半段凭空消失。
        self.max_records = max(0, int(max_records))

        self._rec = MarlDecisionTraceRecorder(
            self.n_buildings, self.reward_kwargs, reward_label=self.reward_label,
            include_all_actions=True)

        self.seen_steps = 0        # 走过多少步（抽稀前）
        self.recorded_steps = 0    # 实际写进 JSON 的条数
        self.failures = 0          # 采集异常次数（不打断评估）
        self.peak_net = 0.0        # 本段见过的最大社区净负荷（事后补写峰步标记）
        self._peak_marked = False  # 峰步标记只做一次（重复调用会重复追加摘要文字）
        self._last_error = ''

    @property
    def truncated(self) -> bool:
        """是否因条数上限而截断（max_records=0 视为不限 ⇒ 永远 False）。"""
        return bool(self.max_records and self.recorded_steps >= self.max_records)

    # ------------------------------------------------------------------ 采集
    def record_step(
        self,
        citylearn_env: Any,
        *,
        step_count: int,
        ordered_keys: Sequence[Any],
        actions: Mapping[Any, Sequence[float]],
        rewards: Any,
        community_net: Optional[float] = None,
        peak_target: Optional[float] = None,
        hour: Optional[float] = None,
        outage_flags: Optional[Sequence[float]] = None,
    ) -> None:
        """记录一步。`citylearn_env` 必须是**剥掉 wrapper 的 CityLearnEnv**。

        actions 传「策略原始输出」即可：`utils.report` 内部会优先用奖励侧的
        `_pending_acts`（= 经过 district 改写后**真正执行**的动作），
        这样方案 3 的 a_peak_resp 改写也能在剧本里如实体现。
        """
        if self._rec is None:
            return
        self.seen_steps += 1
        if self.max_records and self.recorded_steps >= self.max_records:
            return
        if self.stride > 1 and ((self.seen_steps - 1) % self.stride) != 0:
            return

        try:
            from utils.report import record_step_trace

            record_step_trace(
                self._rec,
                citylearn_env,
                step_count=int(step_count),
                ordered_keys=list(ordered_keys),
                actions=actions,
                rewards=rewards,
            )
        except Exception as exc:  # 采集失败绝不影响评估主流程
            self.failures += 1
            self._last_error = f'{type(exc).__name__}: {exc}'
            return

        if not self._rec.steps:
            return
        record = self._rec.steps[-1]

        net = float(community_net) if community_net is not None else None
        if net is not None and net > self.peak_net:
            self.peak_net = net

        # 补齐三维动作与 DHW 储能读数（district 专有；report 的通用出口没有这一层）
        exec_actions = self._decorate_buildings(citylearn_env, record, ordered_keys)

        # 区域字段：界面暂不渲染，但排查"这一步为什么这么动作"时最有用
        record['district'] = {
            'community_net_kw': net,
            'peak_target_kw': (None if peak_target is None else float(peak_target)),
            'peak_ratio': (None if (peak_target in (None, 0) or net is None)
                           else float(net) / float(peak_target)),
            'hour': hour,
            'outage_flags': list(outage_flags or []),
            # 动作维度顺序：DHW / 电池 / 冷却（与 building.active_actions 一致）
            'action_dims': ['dhw', 'ele', 'tmp'],
            # 策略原始输出（未经改写/投影）：与 exec_actions 对照即可看出被改了多少
            'raw_actions': {str(k): [float(x) for x in _as_list(v)]
                            for k, v in (actions or {}).items()},
            # 实际执行值：来自奖励侧 _pending_acts（方案 3 的削峰改写会体现在这里）
            'exec_actions': exec_actions,
        }
        record['phases'] = self._build_phases(record, net, peak_target, hour)
        self.recorded_steps += 1

    # ------------------------------------------------------------- 三维动作
    def _decorate_buildings(
        self,
        citylearn_env: Any,
        record: Dict[str, Any],
        ordered_keys: Sequence[Any],
    ) -> Dict[str, List[Any]]:
        """给每栋补 DHW 储能 SOC，并按 agent 汇总「执行动作」三维向量。"""
        from utils.report import getattr_path, series_value

        buildings = list(getattr(citylearn_env, 'buildings', []) or [])
        time_step = int(getattr(citylearn_env, 'time_step', 0) or 0)
        exec_map: Dict[str, List[Any]] = {}
        for i, entry in enumerate(record.get('buildings') or []):
            building = buildings[i] if i < len(buildings) else None
            if building is not None:
                soc = series_value(getattr_path(building, 'dhw_storage', 'soc'), time_step)
                try:
                    entry['dhw_soc'] = float(soc) if math.isfinite(float(soc)) else None
                except (TypeError, ValueError):
                    entry['dhw_soc'] = None
            fin = ((entry.get('actions') or {}).get('final') or {})
            key = str(ordered_keys[i]) if i < len(ordered_keys) else f'agent_{i}'
            exec_map[key] = [fin.get('dhw'), fin.get('ele'), fin.get('tmp')]
        return exec_map

    # ------------------------------------------------------------- 阶段推演
    def _build_phases(
        self,
        record: Mapping[str, Any],
        net: Optional[float],
        peak_target: Optional[float],
        hour: Optional[float],
    ) -> List[Dict[str, Any]]:
        """区域级三段推演（替换 utils.report 里单栋 Multi-agent 的两段说法）。"""
        buildings = list(record.get('buildings') or [])
        n = len(buildings) or self.n_buildings

        # ① 区域上下文
        hour_v = record.get('hour')
        if hour_v is None:
            hour_v = hour
        try:
            hour_s = f'{int(float(hour_v)):02d}:00'
        except (TypeError, ValueError):
            hour_s = '-'
        ratio = None
        if net is not None and peak_target not in (None, 0):
            try:
                ratio = float(net) / float(peak_target)
            except (TypeError, ValueError, ZeroDivisionError):
                ratio = None
        ctx = f'社区净用电 {_fmt(net, 2)} kW（{hour_s}）'
        if ratio is not None:
            ctx += f'，为峰值目标的 {ratio * 100:.1f}%'
            ctx += '，已进入峰段' if ratio >= _PEAK_STEP_RATIO else '，未到峰段'

        # ② 逐栋动作：三维全列（DHW / 电池 / 冷却），并给出储能读数区间，
        #    便于判断"尖峰时电池/DHW 到底有没有出力"。
        def _nums(key: str) -> List[float]:
            vals = [b.get(key) for b in buildings]
            return [float(v) for v in vals
                    if isinstance(v, (int, float)) and v == v]

        def _rng(vals: List[float]) -> str:
            return '-' if not vals else f'{min(vals):.2f}~{max(vals):.2f}'

        bat_socs = _nums('battery_soc')
        dhw_socs = _nums('dhw_soc')
        dhw_txt = _rng(dhw_socs)
        if dhw_socs and max(dhw_socs) == 0.0 and min(dhw_socs) == 0.0:
            # 如实标注：DHW 动作在变但 SOC 全程不动，多半是上游蓄热更新没生效
            dhw_txt += '（本段未变化）'
        act_s = (f'{n} 栋各自 Policy 输出 DHW / 电池 / 冷却三维动作'
                 f'（act_dhw / act_bat / act_cool 是改写后**实际执行**值，raw= 为策略原始输出）；'
                 f'电池 SOC {_rng(bat_socs)}、DHW SOC {dhw_txt}')

        # ③ 区域奖励
        r_sum, r_n = 0.0, 0
        for b in buildings:
            for ln in (b.get('narrative_lines') or []):
                if '[观测动作]' in ln and 'R=' in ln:
                    try:
                        r_sum += float(ln.split('R=')[1].split()[0])
                        r_n += 1
                    except (IndexError, ValueError):
                        pass
                    break
        rew_s = (f'区域奖励 {self.reward_label}：各栋回报合计 {_fmt(r_sum, 3)}'
                 f'（n={r_n}）；区域七项分解与审计计数器是**整段累计量**，'
                 f'见同目录 district_eval_diagnostics.json')

        return [
            {'phase': 1, 'name': '区域观测与峰值目标', 'summary': ctx},
            {'phase': 2, 'name': '逐栋策略动作', 'summary': act_s},
            {'phase': 3, 'name': '区域奖励与分摊', 'summary': rew_s},
        ]

    # ------------------------------------------------------------------ 落盘
    def to_payload(self, extra_meta: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """顶层结构：与 CHESCA / Multi-agent 的 decision_trace 同构（version 2 / slim）。"""
        payload: Dict[str, Any] = {
            'version': 2,
            'agent': 'district_marl',
            'n_buildings': self.n_buildings,
            'slim': True,
            'reward_label': self.reward_label,
            'district': {
                'stride': self.stride,
                'max_records': self.max_records,
                'seen_steps': int(self.seen_steps),
                'recorded_steps': int(self.recorded_steps),
                # max_records=0 表示不限 ⇒ 永不截断
                'truncated': bool(self.max_records and self.recorded_steps >= self.max_records),
                'action_dims': ['dhw', 'ele', 'tmp'],
                'peak_net_kw': float(self.peak_net) if self.peak_net else None,
                'collect_failures': int(self.failures),
            },
            'steps': list(self._rec.steps),
        }
        if self.reward_kwargs:
            payload['reward_kwargs'] = _json_safe(self.reward_kwargs)
        if extra_meta:
            payload['district'].update({str(k): _json_safe(v)
                                       for k, v in extra_meta.items()})
        return payload

    def save(self, file_path: Path, extra_meta: Optional[Mapping[str, Any]] = None) -> Path:
        """整份覆盖写（紧凑分隔符：与 slim_decision_trace 的落盘方式一致，省 40% 体积）。"""
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            json.dumps(self.to_payload(extra_meta), ensure_ascii=False,
                       separators=(',', ':'), default=_json_default),
            encoding='utf-8',
        )
        return file_path

    # ------------------------------------------------------------- 事后补标记
    def mark_peak_steps(self, peak_net: Optional[float] = None) -> None:
        """把「是否为峰步」和「占全段峰值的比例」补写进每条记录。

        必须**全部采完再标**：跑到第 10 步时还不知道整段峰值是多少，
        逐步判断会把前期的局部高点误标成峰步。

        参照量用「本段实测峰值」而不是 `DISTRICT_PEAK_TARGET`：
        后者是奖励侧的归一化目标线（4.0 × net_scale），与原始 kW 不同量纲，
        直接拿来当分母会算出恒 <100% 的假比例。
        """
        peak = float(peak_net) if peak_net else float(self.peak_net or 0.0)
        if peak <= 0 or self._peak_marked:
            return
        for step in self._rec.steps:
            d = step.get('district') or {}
            net = d.get('community_net_kw')
            if net is None:
                continue
            try:
                ratio = float(net) / peak
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            is_peak = bool(ratio >= _PEAK_STEP_RATIO)
            d['is_peak_step'] = is_peak
            d['ratio_vs_segment_peak'] = ratio
            step['district'] = d

            # 同步把结论写进第一条剧本摘要 —— 界面上不看 JSON 也能一眼看到"这是不是峰步"
            phases = step.get('phases')
            if isinstance(phases, list) and phases and isinstance(phases[0], dict):
                base = str(phases[0].get('summary') or '')
                extra = f'；占全段峰值 {peak:.2f} kW 的 {ratio * 100:.1f}%'
                if is_peak:
                    extra += '（峰步）'
                phases[0]['summary'] = base + extra
        # 只标一次：rollout 收尾与调用方可能各调一次（尤其训练/评估两条路径）
        self._peak_marked = True


# ------------------------------------------------------------------ 小工具
def _as_list(v: Any) -> List[float]:
    try:
        return [float(x) for x in list(v)]
    except (TypeError, ValueError):
        return []


def _json_default(o: Any) -> Any:
    """把 numpy 标量 / 数组转成可序列化对象（避免 np.float32 直接报错）。"""
    for attr in ('tolist', 'item'):
        fn = getattr(o, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return str(o)


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return _json_default(obj)


def build_decision_log(
    enabled: bool = True,
    n_buildings: int = 0,
    *,
    reward_label: str = 'DistrictPeakReward',
    reward_kwargs: Optional[Mapping[str, Any]] = None,
    stride: int = 1,
    max_records: int = 0,
    log_console=None,
) -> Optional[DistrictDecisionLog]:
    """工厂：默认**开启**并全量记录（stride=1、不限条数）；enabled=False 才返回 None。

    调用方拿到 None 即整段跳过 ⇒ 零侵入。想少记就显式传 stride / max_records。
    """
    if not enabled:
        if log_console is not None:
            log_console('决策推演日志=OFF（--no-decision-log；KPI 与既有产物不受影响）')
        return None
    if int(n_buildings or 0) <= 0:
        if log_console is not None:
            log_console('决策推演日志=OFF（读不到楼栋数）')
        return None
    log = DistrictDecisionLog(
        int(n_buildings),
        reward_label=reward_label,
        reward_kwargs=reward_kwargs,
        stride=stride,
        max_records=max_records,
    )
    if log_console is not None:
        _cap = '不限' if log.max_records == 0 else f'{log.max_records} 条'
        log_console(f'决策推演日志=ON（每 {log.stride} 步一条，条数上限 {_cap} '
                    f'⇒ decision_trace.json；动作维 dhw/ele/tmp 全量；'
                    f'奖励={log.reward_label}）')
    return log
