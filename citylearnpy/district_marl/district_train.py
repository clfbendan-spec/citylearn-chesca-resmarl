# -*- coding: utf-8 -*-
"""区域级 MARL 训练入口 —— 让"区域 KPI"同时出现在观测、奖励与选点里。

与既有 Multi-agent.py 的差异（只列与区域级指标有关的）
------------------------------------------------------
  1) 环境：DistrictContextRLlibEnv（每个 agent 多 9 维区域观测）
  2) 奖励：DistrictPeakReward（显式社区尖峰惩罚 + 团队奖励混合 + 可选错峰引导）
  3) 结构：默认**参数共享**（所有 agent 共用一个 SAC 策略，输入含楼栋身份与区域特征）
  4) 选点：best-checkpoint 按**区域级 KPI**（默认 all_time_peak_average）选择，
           而既有流水线是"纯舒适"（P4_COST_WEIGHT=0）
  5) 记录：每 DISTRICT_EVAL_EVERY 轮跑一次贪心评估，落 district_metrics.csv

诊断埋点（2026-10-17 新增，全部为**只读观测**，不改变训练轨迹）
---------------------------------------------------------------
  起因：只靠 district_metrics.csv 无法判断"某轮 KPI 突然变好"是真收敛还是
  单次 rollout 的离群点（实测 320 轮 all_time_peak 从 0.968~0.976 平台突降到 0.9305，
  同轮 ramping 破 1.0、power_outage_nue 由 0.67 掉到 0.41 —— 与长趋势矛盾）。
  为此补四类埋点（详见「四·五、诊断埋点」节与
  `District-MARL-诊断埋点与不适曲线早停.md`）：
    · district_rl_diag.csv           —— `algo.train()` 返回的 RL 内部指标（原实现整个丢弃）
                                        实测路径 `info.learner.<policy>.learner_stats.*`
    · district_reward_breakdown.csv  —— `district_stats()` 区域七项 + 【方案 5/6/7】预留审计
                                        + 基类 `stats_snapshot()` 的 30+ 项触发/收支
                                        （这些方法此前**全仓库零调用**）
    · district_discomfort_curve.*    —— 「不适曲线」：逐栋 hot/cold 比例 + 五条早停判据运行态
                                        （移植自 utils/train.py 的中期评估机制）
    · district_trace_ep*.npz         —— 逐时步轨迹（社区净用电 / 逐 agent 奖励、动作、SOC），
                                        `district_trace_final.npz` 始终落盘，事后复盘离群点用
  开关：--no-diag（关全部埋点，产物回到改造前）· --discomfort-stop（启用 ①~⑤ 早停，
  默认只记录不干预）· --min-train-epochs（默认 160）· --trace-every N（默认 0）

与"零改动"的关系
----------------
  本文件**只读**原模块（utils.env / utils.train / utils.config），不修改任何原文件。

用法
----
  python district_marl/district_train.py --train-epochs 320 --output-dir <dir>
  python district_marl/district_train.py --quick            # 冒烟：3 轮 + 每 1 轮评估
  python district_marl/district_train.py --no-shared-policy # 独立策略对照
  python district_marl/district_train.py --no-diag          # 关掉全部诊断埋点
  python district_marl/district_train.py --discomfort-stop  # 开①~⑤早停判据
  python district_marl/district_train.py --trace-every 20   # 每 20 轮多落一份轨迹
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ---- 路径引导：本脚本位于 district_marl/ 子目录，需先让 citylearnpy 根目录可见 ----
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---- 确定性引导：必须写在任何重依赖 import 之前 ------------------------------
#   PYTHONHASHSEED 只在**解释器启动时**读取一次；进程内赋值无效（老坑）。
#   未设置时这里把自己重启一次把种子钉住，换取"同 config+同 seed 逐位可复现"。
#   仅当以脚本方式运行（__main__）时触发；作为库被 import 时是 no-op。
#   关闭方式：--hashseed random 或环境变量 DISTRICT_HASHSEED=random。
if __name__ == '__main__':
    from district_marl._hashseed import ensure_hashseed
    ensure_hashseed()

# ---- Ray 启动前的环境准备：必须写在 import ray 之前 --------------------------
from utils.base import log_console, prepare_ray_env

prepare_ray_env()

import numpy as np

from district_marl import district_config as dc
from district_marl import district_acceptance as dacc
from district_marl import _fingerprint as _fp
from district_marl.district_env import (
    DISTRICT_ENV_CONFIG_KEY,
    DistrictContextRLlibEnv,
)

#: 验收统计量可选值（供 argparse choices 使用）
_ACCEPT_STATS = dacc.ACCEPT_STATS


# =============================================================================
# 一、环境配置
# =============================================================================

def build_district_env_config(
    schema: str,
    episode_time_steps: Optional[int] = None,
    enable_render: bool = False,
    output_dir: Optional[Path] = None,
    render_session: str = 'district_marl',
    record_details: bool = False,
    district_obs: bool = True,
) -> Dict[str, Any]:
    """构造 RLlibMultiAgentEnv 的 env_config（区域观测 + 区域奖励）。

    与 multi_agent_runner_copy.build_multi_agent_env_config 同构，差异只有两处：
      · env 类由调用方选择为 DistrictContextRLlibEnv；
      · 奖励换成 DistrictPeakReward，并在 kwargs 里叠加区域奖励参数。
    """
    from utils.config import CUSTOM_REWARD_KWARGS
    from utils.env import (
        OBS_EXTRA_ACTIVE,
        TEMP_DELTA,
        patch_schema_observations,
    )
    from citylearn.wrappers import (
        ClippedObservationWrapper,
        NormalizedObservationWrapper,
    )

    schema_obj, schema_root = patch_schema_observations(schema, OBS_EXTRA_ACTIVE, TEMP_DELTA)

    # 奖励参数 = 原奖励参数（不覆盖）+ 区域奖励参数
    reward_kwargs = dict(CUSTOM_REWARD_KWARGS)
    reward_kwargs['record_details'] = bool(record_details)
    reward_kwargs.update(dc.district_reward_kwargs())

    env_kwargs: Dict[str, Any] = {
        'schema': schema_obj,
        'reward_function': 'district_marl.district_reward.DistrictPeakReward',
        'reward_function_kwargs': reward_kwargs,
    }
    # episode_time_steps：给了就用给定值；给 None 就**不传** ⇒ 交给 CityLearn 用数据集
    #   自带长度（dataset 的 simulation_end_time_step + 1）。与 utils/env.build_env_config
    #   同一约定，也就是 Multi-agent-train / Multi-agent-eval 的做法。
    #   ⚠️ 原先这里总是查硬编码表 _SCHEMA_DEFAULT_EPISODE_STEPS ⇒ 未登记的 schema 会被
    #   静默按 720 跑（截断回合）；那张表已按项目约定弃用（见 utils/env.py 与 CHESCA.py）。
    if episode_time_steps is not None:
        env_kwargs['episode_time_steps'] = int(episode_time_steps)
    if schema_root is not None:
        env_kwargs['root_directory'] = str(schema_root)
    if enable_render and output_dir is not None:
        env_kwargs.update({
            'render_mode': 'end',
            'render_directory': Path(output_dir),
            'render_session_name': render_session,
        })

    dm_cfg = dict(dc.district_env_config())
    dm_cfg['enabled'] = bool(district_obs)

    return {
        'env_kwargs': env_kwargs,
        'wrappers': [NormalizedObservationWrapper, ClippedObservationWrapper],
        DISTRICT_ENV_CONFIG_KEY: dm_cfg,
    }


# =============================================================================
# 二、区域 KPI 计算与评估 rollout
# =============================================================================

def district_net_now(env) -> float:
    """当前步的社区净用电（与奖励侧同源，保证"选点用的量"就是"奖励看的量"）。

    首选 `CityLearnEnv.net_electricity_consumption` 的末位 —— 实测它等于
    奖励函数这一步收到的"社区净用电"（即刚走完那一步的真实值）。
    读不到时才退回"逐楼按当前步下标求和"。
    """
    try:
        arr = np.asarray(env.env.unwrapped.net_electricity_consumption, dtype=float)
        arr = arr.reshape(-1)
        if arr.size:
            return float(arr[-1])
    except Exception:
        pass
    try:
        buildings = list(getattr(env, '_ctx_buildings', None) or [])
        total = 0.0
        for b in buildings:
            ts = int(getattr(b, 'time_step', 0) or 0)
            a = np.atleast_1d(np.asarray(b.net_electricity_consumption, dtype=float))
            if a.size:
                total += float(a[min(max(ts - 1, 0), int(a.size) - 1)])
        return total
    except Exception:
        return 0.0


def _unwrap_citylearn_env(env):
    """剥到裸 CityLearnEnv（优先用原流水线的工具函数，失败再退回固定层级）。"""
    try:
        from utils.env import unwrap_citylearn_env
        got = unwrap_citylearn_env(env)
        if got is not None:
            return got
    except Exception:
        pass
    try:
        return env.env.unwrapped
    except Exception:
        return None


def official_district_kpis(citylearn_env) -> Dict[str, float]:
    """取 CityLearn 官方 District 级归一 KPI（越小越好）。"""
    out: Dict[str, float] = {}
    if citylearn_env is None:
        return out
    try:
        kpis = citylearn_env.evaluate()
        district = kpis[kpis['name'] == 'District']
        for _, row in district.iterrows():
            try:
                out[str(row['cost_function'])] = float(row['value'])
            except (TypeError, ValueError):
                continue
    except Exception as exc:
        log_console(f'[district-marl] 官方 KPI 读取失败（忽略）: {exc}')
    return out


def _unwrap_action(raw) -> np.ndarray:
    """兼容不同 RLlib 版本 compute_single_action 的返回形态。"""
    if isinstance(raw, tuple):
        raw = raw[0]
    return np.asarray(raw, dtype=float).reshape(-1)


def _all_done(terminated, truncated) -> bool:
    """多智能体终止判定：优先看 '__all__'，否则全部 agent 都结束。"""
    for sig in (terminated, truncated):
        if isinstance(sig, Mapping):
            if bool(sig.get('__all__', False)):
                return True
    if isinstance(terminated, Mapping) and terminated:
        return all(bool(v) for v in terminated.values())
    return False


def rollout_district(
    algo,
    env_cls,
    env_config: Mapping[str, Any],
    policy_id_fn,
    deterministic: bool = True,
    max_steps: int = 0,
    export_dir: Optional[Path] = None,
    trace_out: Optional[Dict[str, Any]] = None,
    diag_out: Optional[Dict[str, Any]] = None,
    decision_log: Any = 'auto',
    decision_stride: int = 1,
    decision_max_records: int = 0,
    decision_out: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """贪心跑一整段评估，返回区域 KPI 字典。

    同时给出：
      · district_peak_raw    —— 本段社区净用电峰值（**原始量**，用于选点与对比）
      · district_peak_norm   —— 除以 net_scale 的归一值（跨数据集可比的粗口径）
      · 官方 District 归一 KPI（all_time_peak_average / daily_peak_average / ...）

    export_dir 非空时，顺手把官方 KPI 表写成 exported_kpis.csv。
    ⚠️ 必须在**本段评估刚跑完、尚未 reset 之前**导出 —— reset 会清空仿真状态，
       之后再 evaluate() 得到的是"无控制基线"（多为 1.0）。所以导出与评估同环境。

    trace_out 非空 ⇒ 顺手记逐时步轨迹（社区净用电 / 逐 agent 奖励·动作·SOC）。
    diag_out  非空 ⇒ 顺手把奖励分解（district_stats）与逐栋不适比例（kpi_snapshot）填进去。

    decision_log —— 决策推演日志（模型优选界面用）。**默认 'auto' = 记录下来**：
        · 'auto' / True  ⇒ 现场建一个默认记录器（stride=1、不限条数、三维动作全记）
        · None / False   ⇒ 显式不记录（**只有传参才会关**，供训练循环内的评估复用）
        · DistrictDecisionLog 实例 ⇒ 用调用方配好的记录器（可自定义 stride / 上限）
      记录器采到的 payload 会写进 decision_out['payload']，由调用方决定落盘路径。
    """
    env = env_cls(env_config)
    metrics: Dict[str, float] = {}
    # 默认 'auto' = 记录；None/False = 显式关闭（只有传参才关）
    _auto_log = decision_log is True or (
        isinstance(decision_log, str) and decision_log.strip().lower() == 'auto')
    _watch = trace_out is not None
    _tr_net: List[float] = []
    _tr_rew: List[List[float]] = []
    _tr_act: List[List[float]] = []
    _tr_soc: List[List[float]] = []
    # ---- [埋点 D] SOC 读数：仅当 diag_out 非空时逐时步采（零侵入：默认 None 不采）----
    _soc_steps: List[List[float]] = []
    _need_soc = bool(_watch or (diag_out is not None))
    _hours: Optional[np.ndarray] = None
    if diag_out is not None or decision_log is not None:
        # hour 挂在**每栋建筑的** energy_simulation 上（CityLearnEnv 本身没有该属性，
        # district_building_microgrid 上也没有）⇒ 取第 1 栋的整段 hour 作为时间轴。
        try:
            _b0 = list(getattr(_unwrap_citylearn_env(env), 'buildings', []) or [])[0]
            _hours = np.asarray(_b0.energy_simulation.hour, dtype=float).reshape(-1)
        except Exception:
            _hours = None
    try:
        obs, _info = env.reset()
        keys = list(getattr(env, '_agent_ids', None) or obs.keys())
        if _auto_log:
            # 默认记录：拿到 agent 列表后现场建（楼栋数 = agent 数）
            try:
                from district_marl.district_decision_log import build_decision_log

                decision_log = build_decision_log(
                    True, len(keys),
                    stride=decision_stride,
                    max_records=decision_max_records)
            except Exception:
                decision_log = None
            _auto_log = False
        series: List[float] = []
        steps = 0
        done = False
        while not done:
            actions: Dict[str, Any] = {}
            for k in keys:
                if k not in obs:
                    continue
                raw = algo.compute_single_action(
                    obs[k], policy_id=policy_id_fn(k), explore=not deterministic)
                actions[k] = _unwrap_action(raw)
            obs, _rew, terminated, truncated, _info = env.step(actions)
            _net_now = district_net_now(env)
            series.append(_net_now)
            if _watch:
                # 逐时步轨迹：与 metrics 同源，只是**不丢弃**中间过程（原先算完 max/mean 即扔）
                _tr_net.append(float(_net_now))
                _tr_rew.append([float(_rew.get(k, float('nan')))
                                if isinstance(_rew, Mapping) else float('nan') for k in keys])
                _tr_act.append([float(np.asarray(actions.get(k, [float('nan')]),
                                                 dtype=float).reshape(-1)[0])
                                for k in keys])
            if _need_soc:
                # 一次读取同时喂两条出口：轨迹（_watch）与 SOC 诊断（diag_out）
                _soc_now = _soc_by_agent(env, keys)
                if _watch:
                    _tr_soc.append(_soc_now)
                if diag_out is not None:
                    _soc_steps.append(_soc_now)
            if decision_log is not None:
                # 决策推演日志（模型优选界面用）。纯读取：不改动作、不改奖励、不改 KPI；
                # 动作优先取奖励侧的 _pending_acts（= district 改写后真正执行的值），
                # 这样方案 3 的 a_peak_resp 改写也能在剧本里如实体现。
                try:
                    _dl_hour = None
                    if _hours is not None and getattr(_hours, 'size', 0):
                        _dl_hour = float(_hours[min(steps, int(_hours.size) - 1)])
                    decision_log.record_step(
                        _unwrap_citylearn_env(env),
                        step_count=steps + 1,
                        ordered_keys=keys,
                        actions=actions,
                        rewards=_rew,
                        community_net=_net_now,
                        hour=_dl_hour,
                    )
                except Exception:
                    # record_step 内部已计数并吞掉自身异常；这里兜住 hour/解包等边缘错误，
                    # 绝不让"看日志"这件事影响评估本身。
                    pass
            steps += 1
            done = _all_done(terminated, truncated)
            if max_steps and steps >= max_steps:
                break

        arr = np.asarray(series, dtype=float) if series else np.zeros(1, dtype=float)
        metrics['district_peak_raw'] = float(np.max(arr))
        metrics['district_peak_norm'] = float(np.max(arr)) / max(dc.DISTRICT_NET_SCALE, 1e-9)
        metrics['district_net_mean'] = float(np.mean(arr))
        metrics['eval_steps'] = float(steps)
        if len(arr) >= 24:
            daily = arr[: (len(arr) // 24) * 24].reshape(-1, 24).max(axis=1)
            metrics['district_daily_peak_raw'] = float(np.mean(daily))
        else:
            metrics['district_daily_peak_raw'] = float(np.max(arr))

        cle = _unwrap_citylearn_env(env)
        metrics.update(official_district_kpis(cle))
        if export_dir is not None:
            export_kpis_csv(cle, Path(export_dir))
        # ---- 诊断出口（必须在 reset 之前读：reset 会清空累计状态）----
        if _watch:
            trace_out['agent_ids'] = np.asarray(keys, dtype=str)
            trace_out['step'] = np.arange(1, len(_tr_net) + 1, dtype=np.int32)
            trace_out['district_net'] = np.asarray(_tr_net, dtype=float)
            trace_out['reward'] = _rows_to_matrix(_tr_rew, len(keys))
            trace_out['action_cool'] = _rows_to_matrix(_tr_act, len(keys))
            trace_out['soc'] = _rows_to_matrix(_tr_soc, len(keys))
        if diag_out is not None:
            diag_out.update(env_diagnostics(env, keys))
            # [埋点 D] 电池 SOC 读数（"有没有被学成峰值储备"）；无电池时返回空 ⇒ 不加键
            _soc_stats = _soc_summary(
                _rows_to_matrix(_soc_steps, len(keys)), series, _hours)
            if _soc_stats:
                diag_out['soc'] = _soc_stats
        # 决策推演日志：整段跑完再补峰步标记（跑到第 10 步时还不知道全段峰值）
        if decision_log is not None and hasattr(decision_log, 'to_payload'):
            try:
                decision_log.mark_peak_steps(float(metrics.get('district_peak_raw') or 0.0))
                if decision_out is not None:
                    decision_out['log'] = decision_log
                    decision_out['payload'] = decision_log.to_payload()
            except Exception:
                pass
    finally:
        try:
            env.close()
        except Exception:
            pass
    return metrics


def _soc_by_agent(env, keys: Sequence[str]) -> List[float]:
    """逐楼电池 SOC（读不到给 nan）。顺序与 `keys` 一致。"""
    cle = _unwrap_citylearn_env(env)
    out: List[float] = []
    for k in keys:
        v = float('nan')
        try:
            idx = int(str(k).rsplit('_', 1)[-1])
            b = cle.buildings[idx]
            st = getattr(b, 'electrical_storage', None)
            if st is not None:
                arr = np.asarray(st.soc, dtype=float).reshape(-1)
                if arr.size:
                    v = float(arr[-1])
        except Exception:
            pass
        out.append(v)
    return out


def _rows_to_matrix(rows: Sequence[Sequence[float]], width: int) -> np.ndarray:
    """把逐时步的 list-of-list 转成 (T, width) 的 float 数组（缺项 = nan）。"""
    if not rows:
        return np.zeros((0, max(int(width), 0)), dtype=float)
    out = np.full((len(rows), int(width)), np.nan, dtype=float)
    for t, r in enumerate(rows):
        for i in range(min(len(r), int(width))):
            try:
                out[t, i] = float(r[i])
            except (TypeError, ValueError):
                continue
    return out


def _safe_nanmean_rows(mat: np.ndarray) -> np.ndarray:
    """逐行忽略 nan 求均值；整行全 nan 时该行为 nan（不产生任何 warning）。"""
    if mat is None or getattr(mat, 'size', 0) == 0:
        return np.zeros(0, dtype=float)
    m = np.asarray(mat, dtype=float)
    ok = np.isfinite(m)
    cnt = ok.sum(axis=1)
    out = np.full(m.shape[0], np.nan, dtype=float)
    nz = cnt > 0
    if nz.any():
        out[nz] = np.where(ok, m, 0.0)[nz].sum(axis=1) / cnt[nz]
    return out


def _soc_summary(soc: np.ndarray, net: Sequence[float],
                 hours: Optional[np.ndarray] = None) -> Dict[str, float]:
    """把逐时步 SOC 压成"电池有没有被学成峰值储备"的读数量（仅诊断，不参与任何选点）。

    【为什么要它】此前的 history / district_metrics.csv 里**没有任何 SOC 列**
    （`soc_avg` 只在 `district_rl_diag.csv` 的 RL 内部统计里，且是策略侧的采样均值），
    于是"进 #669 峰步时电池 SOC 只剩 0.20"这类结论只能靠事后拆 npz 轨迹，
    无法在训练过程中逐轮观察。这里补 6 个区域级读数：

      soc_avg          —— 全程平均 SOC
      soc_min          —— 全程最低（区域平均口径）
      soc_at_peak      —— 社区净负荷最大那一步的 SOC（"进峰时还剩多少电"）
      soc_pre_peak_2h  —— 峰步前 24 步（2 h）的平均 SOC（"峰前有没有提前存电"）
      soc_evening_min  —— hour∈[17,22] 窗口内最低 SOC（傍晚水位，方案 5 的目标量）
      soc_evening_avg  —— 同上窗口均值

    口径说明：**先跨 agent 取均值、再跨步取极值**（区域级），与
    `District-MARL平台跑通验证与指标诊断.md` 里"进 #669 时 0.199/0.200/0.362"
    那种逐栋读法不同 —— 两者不可互相替代，逐栋明细仍看 `district_trace_*.npz`。
    无电池 / 读不到时返回空字典（history 行不会多出全 nan 列）。
    """
    out: Dict[str, float] = {}
    if soc is None or getattr(soc, 'size', 0) == 0 or soc.shape[1] == 0:
        return out
    region = _safe_nanmean_rows(soc)
    finite = region[np.isfinite(region)]
    if finite.size == 0:
        return out
    out['soc_avg'] = float(finite.mean())
    out['soc_min'] = float(finite.min())

    net_arr = np.asarray(list(net), dtype=float).reshape(-1) if len(net) else np.zeros(0)
    n = int(min(region.size, net_arr.size))
    if n > 0 and np.isfinite(net_arr[:n]).any():
        idx = int(np.nanargmax(net_arr[:n]))
        if np.isfinite(region[idx]):
            out['soc_at_peak'] = float(region[idx])
        seg = region[max(0, idx - 24):idx + 1]
        seg = seg[np.isfinite(seg)]
        if seg.size:
            out['soc_pre_peak_2h'] = float(seg.mean())

    if hours is not None and getattr(hours, 'size', 0) >= region.size:
        h = np.asarray(hours, dtype=float).reshape(-1)[:region.size]
        with np.errstate(invalid='ignore'):
            mask = (h >= 17.0) & (h <= 22.0)
        seg = region[mask]
        seg = seg[np.isfinite(seg)]
        if seg.size:
            out['soc_evening_min'] = float(seg.min())
            out['soc_evening_avg'] = float(seg.mean())
    return out


def env_diagnostics(env, keys: Sequence[str]) -> Dict[str, Any]:
    """评估收尾前从 env 抽取诊断量（纯读取，不改变仿真状态）。

    返回：
      · `reward`          —— DistrictPeakReward.district_stats()：奖励各项分解 + 全部审计计数器
      · `reward_summary`  —— district_summary() 的一行式可读摘要（挂日志用）
      · `reward_stats`    —— 基类 stats_snapshot()：过热保底/过吹/过冷关冷/电费/电池流等触发统计
      · `discomfort`      —— KPI 口径逐栋 hot/cold **比例**（与 utils/train.py 的中期评估同源）
    """
    out: Dict[str, Any] = {}
    cle = _unwrap_citylearn_env(env)
    rf = getattr(cle, 'reward_function', None) if cle is not None else None

    # ① 区域奖励分解（district_stats 此前全仓库零调用 ⇒ 七项分解与审计计数器白算）
    try:
        if rf is not None and hasattr(rf, 'district_stats'):
            out['reward'] = {str(k): float(v) for k, v in rf.district_stats().items()}
    except Exception as exc:
        log_console(f'[district-marl] district_stats 读取失败（忽略）: {exc}')
    try:
        if rf is not None and hasattr(rf, 'district_summary'):
            out['reward_summary'] = str(rf.district_summary())
    except Exception:
        pass

    # ② 基类奖励统计（触发次数 / 电量 / 成本原值 / 电池流）
    try:
        if rf is not None and hasattr(rf, 'stats_snapshot'):
            out['reward_stats'] = {
                str(k): (float(v) if isinstance(v, (int, float)) else v)
                for k, v in rf.stats_snapshot().items()}
    except Exception:
        pass

    # ③ 不适曲线：奖励侧 KPI 累计（主动读数）⇒ 逐栋 hot/cold 比例
    try:
        if rf is not None and hasattr(rf, 'kpi_snapshot'):
            snap = rf.kpi_snapshot()
            hot = [float(v) for v in (snap.get('hot') or [])]
            cold = [float(v) for v in (snap.get('cold') or [])]
            occ = [float(v) for v in (snap.get('occ') or [])]
            n = max(len(hot), len(cold), len(occ), len(keys))
            r_hot: List[float] = []
            r_cold: List[float] = []
            for i in range(n):
                d = occ[i] if i < len(occ) else 0.0
                r_hot.append((hot[i] / d) if (i < len(hot) and d > 0) else float('nan'))
                r_cold.append((cold[i] / d) if (i < len(cold) and d > 0) else float('nan'))
            out['discomfort'] = {
                'hot': r_hot,
                'cold': r_cold,
                'occ': occ,
                'steps_run': int(snap.get('t_cnt') or 0),
                'mean_T': (float(snap.get('t_sum') or 0.0) / float(snap.get('t_cnt') or 1))
                          if int(snap.get('t_cnt') or 0) else float('nan'),
            }
    except Exception as exc:
        log_console(f'[district-marl] kpi_snapshot 读取失败（忽略）: {exc}')
    return out


# =============================================================================
# 三、选点与落盘
# =============================================================================

def _metric_value(metrics: Mapping[str, float], name: str) -> Optional[float]:
    """取选点指标；缺失 ⇒ None（调用方跳过本次比较，不误判创新低）。"""
    if not name:
        return None
    v = metrics.get(name)
    if v is None:
        # 退路：官方 KPI 缺失时用原始峰值量（仍满足"越小越好"的方向）
        if name in ('all_time_peak_average', 'district_peak_raw'):
            return metrics.get('district_peak_norm')
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _score(metrics: Mapping[str, float]) -> Optional[Tuple[float, float]]:
    """选点分数 = (主指标, 次指标)，都越小越好。"""
    primary = _metric_value(metrics, dc.DISTRICT_BEST_METRIC)
    if primary is None:
        return None
    tie = _metric_value(metrics, dc.DISTRICT_BEST_TIEBREAK)
    return (primary, 0.0 if tie is None else tie)


def _write_metrics_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    """把每轮区域 KPI 写成 CSV（列 = 所有出现过的键，便于后续画曲线）。"""
    if not rows:
        return
    cols: List[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as fh:
        fh.write(','.join(cols) + '\n')
        for r in rows:
            fh.write(','.join(
                ('%g' % float(r[k])) if k in r and r[k] is not None else ''
                for k in cols) + '\n')


def export_kpis_csv(citylearn_env, out_dir: Path) -> Optional[Path]:
    """把官方 KPI 表写成 exported_kpis.csv（口径与原流水线逐位一致）。"""
    if citylearn_env is None:
        return None
    try:
        kpis = citylearn_env.evaluate()
        table = kpis.pivot(index='cost_function', columns='name', values='value').round(3)
        table = table.dropna(how='all')
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / 'exported_kpis.csv'
        (table.fillna('').reset_index().rename(columns={'cost_function': 'KPI'})
         ).to_csv(path, index=False, encoding='utf-8')
    except Exception as exc:
        log_console(f'[district-marl] exported_kpis.csv 写入失败（忽略）: {exc}')
        return None
    # 平台协议：stdout 打印 'outputkpi' 段，Java 靠这一行截取 KPI 并入 kpis 表。
    # 必须与已有脚本**同一份实现**（utils.report.print_kpis_for_java），逐字同款。
    try:
        from utils.report import print_kpis_for_java
        print_kpis_for_java(table)
    except Exception as exc:
        log_console(f'[district-marl] outputkpi 打印失败（忽略，不影响 CSV）: {exc}')
    return path


def write_train_progress(
    ckpt_dir: Path,
    epochs_done: int,
    train_epochs_target: int,
    best_score: Optional[float] = None,
    best_epoch: Optional[int] = None,
    accept: Optional[Mapping[str, Any]] = None,
) -> None:
    """把训练进度写进断点目录的 train_progress.json（失败只提示，不打断训练）。

    平台（Java 侧 BaseDataService.isUsableCheckpointDir / getTrainModelTaskList）靠这个文件
    判断「该任务的模型可用」并展示进度；字段名与 utils/train.py 的 CkptManager.write_progress
    保持一致，前端可复用同一套解析（epochs_done / train_epochs_target / best_score / updated）。

    `accept`（可选）：验收口径摘要（见 district_acceptance.summarize）。**新增字段**，
    旧前端会忽略未知键 ⇒ 零破坏；`best_score` 语义与位置保持不变。
    """
    try:
        ckpt_dir = Path(ckpt_dir)
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            'epochs_done': int(epochs_done),
            'train_epochs_target': int(train_epochs_target),
            'best_score': (None if best_score is None else float(best_score)),
            'best_epoch': (None if best_epoch is None else int(best_epoch)),
            'best_metric': str(dc.DISTRICT_BEST_METRIC),
            'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        if accept:
            payload['accept_stat'] = str(accept.get('stat') or '')
            payload['accept_metric'] = str(accept.get('metric') or '')
            _av = accept.get('value')
            payload['accept_score'] = (None if _av is None else float(_av))
            payload['accept_n_used'] = int(accept.get('n_used') or 0)
        (ckpt_dir / dc.DISTRICT_CKPT_PROGRESS_FILE).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as exc:
        log_console(f'[district-marl] train_progress.json 写入失败（忽略）: {exc}')


# =============================================================================
# 四·五、诊断埋点（RL 内部指标 / 奖励分解 / 不适曲线 / 轨迹）
# =============================================================================
#
# 为什么要有这一节
# ----------------
#   只靠 district_metrics.csv 只能看到"KPI 是什么"，看不到"为什么"：
#   · `algo.train()` 的返回值原实现**整个丢弃** ⇒ loss / entropy / grad_norm / td_error /
#     lr / alpha 一条没留 ⇒ 无法区分"某轮 KPI 突变"是真收敛、还是发散/崩坏后的偶然解。
#   · `DistrictPeakReward.district_stats()/district_summary()` 事先写好了整套奖励分解与
#     审计计数器，但**全仓库零调用** ⇒ 每次都白算。
#   · `rollout_district` 把逐时步序列压成 max/mean 就扔 ⇒ 无法事后复盘某个离群点。
#   · 没有「不适曲线」（Multi-agent-train 的 utils/train.py 有）⇒ 看不到逐栋舒适度的
#     训练轨迹，也没有基于它的早停判据。
#
# 「不适曲线」的含义
# ------------------
#   移植自 utils/train.py 的中期评估机制（`mid_eval_history`）：每轮评估记一次**逐栋**
#   高温/低温比例，串成曲线。用途与那边一致：判断缺口是"随训练下降（训练量不够）"
#   还是"平着不动（收敛到错的点）"。默认**只记录不干预** —— 早停判据要显式开
#   `--discomfort-stop` 才生效（零侵入：关时训练轨迹与改前逐位一致）。

# ---- 「不适曲线」早停判据阈值（与 utils/config.py 同源同值）------------------
_DIS_TARGET_HOT = 0.10          # ① 达标线：逐栋高温比例
_DIS_TARGET_COLD = 0.10         # ① 达标线：逐栋低温比例
_DIS_VOTE_RATIO = 0.6           # ② 优于上次的楼数占比 ≥ 该值 = 仍在进步（3 栋 → 2 栋）
_DIS_VOTE_PATIENCE = 5          # ② 连续多少次"未过投票线"才判停滞
_DIS_WORSEN_MARGIN = 0.10       # ③ 某栋合计高于「自身历史最优」多少算恶化
_DIS_WORSEN_PATIENCE = 3        # ③ 连续多少次才算"该栋在恶化"
_DIS_CONVERGE_SUM = 0.07        # ④ 该栋"高温+低温"合计低于此值算这一段收敛
_DIS_CONVERGE_PATIENCE = 3      # ④ 连续多少次低于阈值才算"该栋已收敛"
_DIS_SAT_MAX_HOT = 0.90         # ⑤ 崩坏：单侧饱和线（高温，策略几乎不制冷）
_DIS_SAT_MAX_COLD = 0.80        # ⑤ 崩坏：单侧饱和线（低温，策略一直制冷）
_DIS_SAT_EPOCH = 100            # ⑤ 只在该轮体检一次（太早会误杀：第 50 轮连可用模型都高）

# ---- RLlib 结果的实测结构（2026-10-17 在 cl2 环境 dump 过，见 _probe_rl_result.py）----
# 跑法：加载一个 checkpoint，连续 train() 到 `num_env_steps_trained > 0`
#   （MIN_SAMPLE_BEFORE_LEARN=512，每轮采样 100 ⇒ **第 5 轮**才开始真正学习）。
# 实测路径（RLlib 2.4x + RLModule）：
#   info.learner.<policy_id>.learner_stats.<name>   ← 损失 / alpha / 梯度 / Q 值
#   info.learner.<policy_id>.<name>                 ← td_error / 训练步数
#   info.<name>                                     ← SAC target-net 更新计数
#   顶层 <name>                                      ← 回报 / 采样步数 / 计时
#
#: 逐策略 learner_stats 标量（**取 mean 汇总**；见 _RL_MAX_OF_KEYS 另取 max）
_RL_LEARNER_STATS_KEYS: Tuple[str, ...] = (
    'actor_loss', 'critic_loss', 'alpha_loss', 'alpha_value', 'log_alpha_value',
    'grad_gnorm', 'target_entropy', 'policy_t', 'mean_q', 'max_q', 'min_q',
)
#: `info.learner.<policy_id>.<name>`（比 learner_stats 高一层）
_RL_POLICY_LEVEL_KEYS: Tuple[str, ...] = (
    'mean_td_error', 'num_agent_steps_trained', 'num_grad_updates_lifetime',
)
#: 顶层与策略无关的训练进度 / 回报
_RL_TOP_LEVEL_KEYS: Tuple[str, ...] = (
    'episode_reward_mean', 'episode_reward_min', 'episode_reward_max',
    'episode_len_mean', 'episodes_total', 'timesteps_total',
    'num_env_steps_sampled', 'num_env_steps_trained',
    'num_agent_steps_sampled', 'num_agent_steps_trained',
    'num_env_steps_trained_this_iter', 'time_this_iter_s',
)
#: `info.<name>` 下的标量（SAC target-net 软更新计数 —— 判"到底有没有在学"的旁证）
_RL_INFO_KEYS: Tuple[str, ...] = ('num_target_updates', 'last_target_update_ts')
#: 在 mean 之外再记一份「跨策略 max」的指标（探测"某个 agent 独自发散"）
_RL_MAX_OF_KEYS: Tuple[str, ...] = ('actor_loss', 'critic_loss', 'grad_gnorm',
                                    'mean_td_error')
#: 兜底递归查找时**必须跳过**的子树。
#: 实测 `config.*` 里挂着 `initial_alpha` / `lr` / `entropy_learning_rate` 这类
#: **配置值**，不加过滤会被 `find_metric` 当成运行时指标收走 —— 历史 bug：
#: `district_rl_diag.csv` 里 `rl_alpha` 恒等于 1，命中的正是 `config.initial_alpha`。
_RL_SKIP_SUBTREES: Tuple[str, ...] = ('config', 'env_config')
#: 全部尝试提取的指标名（兜底递归用）
_RL_METRIC_KEYS: Tuple[str, ...] = (
    _RL_LEARNER_STATS_KEYS + _RL_POLICY_LEVEL_KEYS + _RL_TOP_LEVEL_KEYS + _RL_INFO_KEYS
)

#: 不适曲线文件名（CSV = 曲线本体；JSON = 供续训继承与前端画图）
_DIS_CURVE_CSV = 'district_discomfort_curve.csv'
_DIS_CURVE_JSON = 'district_discomfort_curve.json'


def _f(v: Any) -> float:
    """尽力转 float；转不了或非有限 ⇒ nan（CSV/JSON 里一律写成空）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float('nan')
    return f if np.isfinite(f) else float('nan')


def _csv_cell(v: Any) -> str:
    """把任意值转成一个 CSV 单元格（NaN/None → 空；含逗号/引号 → 加引号）。"""
    if v is None:
        return ''
    if isinstance(v, str):
        s = v.replace('\n', ' ').replace('\r', ' ')
        return ('"' + s.replace('"', "'") + '"') if (',' in s or '"' in s) else s
    f = _f(v)
    return '' if not np.isfinite(f) else ('%g' % f)


def _numeric_only(d: Mapping[str, Any]) -> Dict[str, float]:
    """只保留可转 float 的键 —— 诊断 CSV 里不落字符串，避免重建表头时被逗号切坏。"""
    out: Dict[str, float] = {}
    for k, v in d.items():
        if isinstance(v, (bool, str)) or v is None:
            continue
        if isinstance(v, (int, float)):
            out[str(k)] = float(v)
    return out


def trace_steps(trace: Mapping[str, Any]) -> int:
    """轨迹步数。

    ⚠️ 不能写成 `len(trace.get('step') or [])` —— `step` 是 ndarray，
    `arr or []` 会走 Python 真值判断 ⇒ numpy 抛
    「truth value of an array with more than one element is ambiguous」。
    """
    try:
        return int(len(trace.get('step')))
    except Exception:
        return 0


def append_csv_row(path: Path, row: Mapping[str, Any]) -> None:
    """把一行诊断指标**追加**进 CSV；列在首次写入时固定，之后新出现的列会补进表头。

    与 `_write_metrics_csv` 的区别：那个是训练收尾一次性覆盖写（列 = 所有行键的并集），
    本函数是**流式追加** ⇒ 训练中途被 kill 也不会丢掉已经跑出来的诊断曲线。
    """
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        header: List[str] = []
        body: List[str] = []
        if path.is_file():
            lines = path.read_text(encoding='utf-8').splitlines()
            if lines:
                header = lines[0].split(',')
                body = lines[1:]
        missing = [str(k) for k in row if str(k) not in header]
        if missing:
            old_header = list(header)
            header = header + missing
            rebuilt: List[str] = []
            for ln in body:
                cells = ln.split(',')
                old = dict(zip(old_header, cells))
                rebuilt.append(','.join(old.get(str(c), '') for c in header))
            body = rebuilt
            path.write_text(','.join(header) + '\n' + ''.join(x + '\n' for x in body),
                            encoding='utf-8')
        with path.open('a', encoding='utf-8', newline='') as fh:
            fh.write(','.join(_csv_cell(row.get(c)) for c in header) + '\n')
    except Exception as exc:
        log_console(f'[district-marl] 诊断 CSV 写入失败（忽略）: {exc}')


# -----------------------------------------------------------------------------
# RL 内部指标：`algo.train()` 的返回值（原实现整个丢弃）
# -----------------------------------------------------------------------------
def _strip_config(obj: Any) -> Any:
    """递归剔除 `config` / `env_config` 子树（兜底递归查找前先过一遍）。"""
    if isinstance(obj, Mapping):
        return {k: _strip_config(v) for k, v in obj.items()
                if str(k) not in _RL_SKIP_SUBTREES}
    if isinstance(obj, (list, tuple)):
        return [_strip_config(v) for v in obj]
    return obj


def _rl_num(v: Any) -> Optional[float]:
    """数值 → float（非有限/非数值 ⇒ None）。

    ⚠️ 必须显式接受 `np.floating` / `np.integer`：RLlib 的 learner_stats 多为
    `np.float32`，而 `isinstance(np.float32(1), float)` 是 **False** ⇒ 只写
    `(int, float)` 会把真正的 loss 全部漏掉（旧版就是这么漏的）。
    """
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        return f if np.isfinite(f) else None
    return None


def rl_stats_from_result(result: Any) -> Dict[str, float]:
    """从 RLlib `algo.train()` 的返回里抽出 RL 内部指标（**只读观测**）。

    取数顺序：**精确路径优先**（实测版式，见 `_RL_LEARNER_STATS_KEYS` 上方注释），
    再对没取到的名字做一次「剔除 config 子树后的递归兜底」（抗 RLlib 版本漂移）。
    取不到就不写该列 —— 不会伪造 0。

    ⚠️ 两点实测坑：
      · `info.learner.<policy_id>.td_error` 是**数组**（逐样本），不是标量 ⇒ 不取，
        只取同层的 `mean_td_error`。
      · 前 `MIN_SAMPLE_BEFORE_LEARN`(=512) 步之前 learner 子树**本来就是空的**
        （还没开始学）⇒ 那几轮只有顶层指标，属正常现象，不是埋点故障。
    """
    out: Dict[str, float] = {}
    if not isinstance(result, Mapping):
        return out

    # ---- 1) 逐策略 learner 指标（跨策略取 mean；损失/梯度类再加一份 max）----
    info = result.get('info')
    info = info if isinstance(info, Mapping) else {}
    learner = info.get('learner')
    learner = learner if isinstance(learner, Mapping) else {}

    buckets: Dict[str, List[float]] = {}
    n_pol = 0
    for _pid, pdata in learner.items():
        if not isinstance(pdata, Mapping):
            continue
        n_pol += 1
        stats = pdata.get('learner_stats')
        stats = stats if isinstance(stats, Mapping) else {}
        for name in _RL_LEARNER_STATS_KEYS:
            v = _rl_num(stats.get(name))
            if v is not None:
                buckets.setdefault(name, []).append(v)
        for name in _RL_POLICY_LEVEL_KEYS:
            v = _rl_num(pdata.get(name))
            if v is not None:
                buckets.setdefault(name, []).append(v)
    for name, vals in buckets.items():
        out['rl_' + name] = float(np.mean(vals))
        if name in _RL_MAX_OF_KEYS and len(vals) > 1:
            out['rl_' + name + '_max'] = float(np.max(vals))
    if n_pol:
        out['rl_n_policies'] = float(n_pol)

    # ---- 2) info 层标量 ----
    for name in _RL_INFO_KEYS:
        v = _rl_num(info.get(name))
        if v is not None:
            out['rl_' + name] = v

    # ---- 3) 顶层标量 ----
    for name in _RL_TOP_LEVEL_KEYS:
        v = _rl_num(result.get(name))
        if v is not None:
            out['rl_' + name] = v

    # ---- 4) 兜底递归（仅在精确路径没取全时执行，避免每轮白白深拷贝整份 result）----
    missing = [n for n in _RL_METRIC_KEYS if ('rl_' + n) not in out]
    if missing:
        try:
            from utils.train import find_metric
            clean = _strip_config(result)
            for name in missing:
                v = _rl_num(find_metric(clean, name))
                if v is not None:
                    out['rl_' + name] = v
        except Exception:
            pass
    return out


# -----------------------------------------------------------------------------
# 不适曲线：逐栋 hot/cold 比例的拍平 / 打印 / 持久化 / 早停判据
# -----------------------------------------------------------------------------
def flatten_discomfort(epoch: int, diag: Mapping[str, Any]) -> Dict[str, Any]:
    """把一次评估的逐栋不适比例拍平成一行（`hot_b1..N` / `cold_b1..N` / `sum_b1..N` / `max_*`）。"""
    d = diag.get('discomfort') or {}
    hot = [_f(v) for v in (d.get('hot') or [])]
    cold = [_f(v) for v in (d.get('cold') or [])]
    n = max(len(hot), len(cold))
    row: Dict[str, Any] = {'epoch': int(epoch)}
    sums: List[float] = []
    for i in range(n):
        h = hot[i] if i < len(hot) else float('nan')
        c = cold[i] if i < len(cold) else float('nan')
        row[f'hot_b{i + 1}'] = h
        row[f'cold_b{i + 1}'] = c
        s = h + c
        row[f'sum_b{i + 1}'] = s
        if np.isfinite(s):
            sums.append(s)
    fin_h = [v for v in hot if np.isfinite(v)]
    fin_c = [v for v in cold if np.isfinite(v)]
    row['max_hot'] = max(fin_h) if fin_h else float('nan')
    row['max_cold'] = max(fin_c) if fin_c else float('nan')
    row['sum_all'] = float(np.sum(sums)) if sums else float('nan')
    row['mean_T'] = _f(d.get('mean_T'))
    row['steps_run'] = int(d.get('steps_run') or 0)
    return row


def _pct(v: Any) -> str:
    """比例 → '12.3%'；无效 → ' na '（与 utils/train.py 的 _pct 同款）。"""
    f = _f(v)
    return ' na ' if not np.isfinite(f) else f'{f:5.1%}'


def format_discomfort_line(epoch: int, row: Mapping[str, Any], tag: str = '') -> str:
    """一行式不适曲线打印（`B1:高温/低温 … 逐栋合计`），格式对齐中期评估行。"""
    parts: List[str] = []
    sums: List[str] = []
    i = 1
    while f'hot_b{i}' in row:
        parts.append(f'B{i}:{_pct(row[f"hot_b{i}"])}/{_pct(row.get(f"cold_b{i}"))}')
        sums.append(f'B{i} {_pct(row.get(f"sum_b{i}"))}')
        i += 1
    return (f'[不适曲线] 第 {epoch} 轮 | 高温/低温 ' + ' '.join(parts)
            + ' | 逐栋合计 ' + ' / '.join(sums)
            + f' | max 高温={_pct(row.get("max_hot"))} 低温={_pct(row.get("max_cold"))}'
            + (f' | {tag}' if tag else ''))


def format_curve_overview(
    curve: Sequence[Mapping[str, Any]], head: int = 8, tail: int = 8,
) -> List[str]:
    """把不适曲线打成多行「训练曲线」摘要（首尾各 N 点，中间省略）。"""
    if not curve:
        return []
    lines = ['[不适曲线] 训练曲线（逐栋 高温/低温，KPI 口径；完整数据见 CSV/JSON）']
    idx = list(range(len(curve)))
    show = idx if len(curve) <= head + tail else (idx[:head] + [-1] + idx[-tail:])
    for i in show:
        if i == -1:
            lines.append(f'  … 省略 {len(curve) - head - tail} 个评估点 …')
            continue
        row = curve[i]
        lines.append('  ' + format_discomfort_line(int(row.get('epoch') or 0), row))
    return lines


def save_discomfort_curve(
    paths: Sequence[Path],
    curve: Sequence[Mapping[str, Any]],
    state: Optional[Mapping[str, Any]] = None,
) -> None:
    """把不适曲线（+ 早停判据运行态）写盘，供续训继承与前端画图。

    写成 `{"curve": [...], "stop_state": {...}}` 而不是裸 list —— 早停判据的
    `prev_sums / best_sums / worsen / conv / vote_stale` 也要跨续训继承，
    否则续训后判据会从零开始（与 utils/train.py 修复过的 P19-1 是同一类坑）。
    """
    try:
        payload = json.dumps(
            {'curve': list(curve),
             'stop_state': (dict(state) if isinstance(state, Mapping) else {})},
            ensure_ascii=False, indent=2, default=str)
    except Exception:
        return
    for p in paths:
        try:
            p = Path(p)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(payload, encoding='utf-8')
        except Exception as exc:
            log_console(f'[district-marl] 不适曲线写盘失败（忽略）: {exc}')


def load_discomfort_curve(
    paths: Sequence[Path],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """读回 `(曲线, 早停判据运行态)`（旧格式裸 list 也兼容）。

    与 utils/train.py 的 P19-1 同一个坑：续训时**绝不能**用空数组覆盖已有曲线 ——
    这里只在"读到非空曲线"时才返回，调用方也只在该返回值非空时才覆盖运行态。
    """
    for p in paths:
        try:
            p = Path(p)
            if not p.is_file():
                continue
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                curve = [d for d in (data.get('curve') or []) if isinstance(d, dict)]
                state = data.get('stop_state')
                state = state if isinstance(state, dict) else {}
            elif isinstance(data, list):          # 兼容旧格式（裸 list）
                curve, state = [d for d in data if isinstance(d, dict)], {}
            else:
                continue
            if curve:
                log_console(f'[district-marl] 不适曲线：从 {p} 继承 {len(curve)} 个历史点'
                            f'（早停判据运行态 {len(state)} 项）')
                return curve, state
        except Exception as exc:
            log_console(f'[district-marl] 不适曲线读取失败（忽略）: {exc}')
    return [], {}


def discomfort_stop_check(
    log,
    epoch: int,
    row: Mapping[str, Any],
    state: Dict[str, Any],
    min_train_epochs: int,
    enabled: bool,
) -> Optional[str]:
    """「不适曲线」早停判据（移植自 utils/train.py 中期评估的 ①~⑤）。

    ① 达标     —— 全部楼 高温 ≤10% 且 低温 ≤10%
    ② 投票停滞 —— 连续 5 次"优于上次"的楼数 < 60%
    ③ 单栋恶化 —— 某栋连续 3 次高于「自身历史最优 +10%」
    ④ 全楼收敛 —— 逐栋「高温+低温」连续 3 次 < 7%
    ⑤ 崩坏止损 —— 只在第 100 轮体检一次：某栋高温 >90% 或 低温 >80%

    返回非 None = 应停训（值为原因）；`enabled=False` 时只更新 `state`、永不返回原因
    ⇒ 训练轨迹与改前逐位一致（判据只在显式开启时生效）。
    """
    hot = [_f(row.get(f'hot_b{i + 1}')) for i in range(64)]
    cold = [_f(row.get(f'cold_b{i + 1}')) for i in range(64)]
    sums = [_f(row.get(f'sum_b{i + 1}')) for i in range(64)]
    # 截到实际存在的栋数（后面全是 nan）
    n_b = 0
    for i in range(64):
        if f'sum_b{i + 1}' not in row:
            break
        n_b = i + 1
    hot, cold, sums = hot[:n_b], cold[:n_b], sums[:n_b]

    if n_b == 0 or not all(np.isfinite(v) for v in sums):
        state['usable'] = False
        log_console(f'[不适曲线][警告] 第 {epoch} 轮探针数据不可用（n={n_b}，比例=na）→ '
                    f'该行不能用于判断模型好坏（检查占用人数读取 / kpi_snapshot 是否为空）')
        return None
    state['usable'] = True

    # ---- ② 投票：本次「高温+低温」合计是否优于上次 ----
    prev = state.get('prev_sums')
    need = max(1, int(np.ceil(_DIS_VOTE_RATIO * n_b)))
    if prev is not None and len(prev) == n_b:
        better = [k for k in range(n_b) if sums[k] < prev[k]]
        state['vote_stale'] = (0 if len(better) >= need
                               else int(state.get('vote_stale') or 0) + 1)
        state['vote_txt'] = (f'优于上次 {len(better)}/{n_b} 栋（需≥{need}）'
                             f' 未过线计数 {state["vote_stale"]}/{_DIS_VOTE_PATIENCE}')
    else:
        state['vote_txt'] = '首次评估（无对比基线）'
    state['prev_sums'] = list(sums)

    # ---- ③ 单栋恶化：逐栋跟踪自身历史最优 ----
    best = state.get('best_sums')
    if best is None or len(best) != n_b:
        best = list(sums)
        worsen = [0] * n_b
    else:
        worsen = list(state.get('worsen') or [0] * n_b)
        for k in range(n_b):
            if sums[k] < best[k]:
                best[k] = float(sums[k])
                worsen[k] = 0
            elif sums[k] > best[k] + _DIS_WORSEN_MARGIN:
                worsen[k] += 1
            else:
                worsen[k] = 0
    state['best_sums'] = list(best)
    state['worsen'] = worsen
    state['worsen_txt'] = ('单栋最优 ' + ' / '.join(f'B{k + 1} {best[k]:.1%}' for k in range(n_b))
                           + ' | 恶化计数 ' + ' / '.join(
                               f'B{k + 1} {worsen[k]}/{_DIS_WORSEN_PATIENCE}' for k in range(n_b)))

    # ---- ④ 逐栋收敛标记 ----
    conv = list(state.get('conv') or [0] * n_b)
    if len(conv) != n_b:
        conv = [0] * n_b
    for k in range(n_b):
        conv[k] = (conv[k] + 1) if sums[k] < _DIS_CONVERGE_SUM else 0
    state['conv'] = conv
    state['conv_txt'] = (' / '.join(
        f'B{k + 1} {"已收敛" if conv[k] >= _DIS_CONVERGE_PATIENCE else "未收敛"}'
        f'({sums[k]:.1%},连续 {conv[k]}/{_DIS_CONVERGE_PATIENCE})' for k in range(n_b))
        + f'（阈值 合计<{_DIS_CONVERGE_SUM:.0%}）')

    if not enabled:
        return None

    # ---- ⑤ 崩坏止损（只体检一次，不受最小轮数限制）----
    if epoch == _DIS_SAT_EPOCH:
        sat: List[str] = []
        for k in range(n_b):
            if np.isfinite(hot[k]) and hot[k] > _DIS_SAT_MAX_HOT:
                sat.append(f'B{k + 1} 高温 {hot[k]:.1%} > {_DIS_SAT_MAX_HOT:.0%}')
            if np.isfinite(cold[k]) and cold[k] > _DIS_SAT_MAX_COLD:
                sat.append(f'B{k + 1} 低温 {cold[k]:.1%} > {_DIS_SAT_MAX_COLD:.0%}')
        if sat:
            return f'崩坏止损（第 {epoch} 轮体检）：策略已饱和在单一极端 —— ' + '；'.join(sat)

    if epoch < int(min_train_epochs):
        return None

    # ---- ① 达标即停 ----
    if (all(np.isfinite(v) for v in hot + cold)
            and max(hot) <= _DIS_TARGET_HOT and max(cold) <= _DIS_TARGET_COLD):
        return (f'达标：全部楼 高温≤{_DIS_TARGET_HOT:.0%} 且 低温≤{_DIS_TARGET_COLD:.0%}'
                f'（最差 高温 {max(hot):.1%} / 低温 {max(cold):.1%}）')
    # ---- ④ 全楼稳定收敛 ----
    if all(c >= _DIS_CONVERGE_PATIENCE for c in conv):
        return (f'全楼稳定收敛：逐栋「高温+低温」合计连续 {_DIS_CONVERGE_PATIENCE} 次低于 '
                f'{_DIS_CONVERGE_SUM:.0%}（当前 '
                + ' / '.join(f'B{k + 1} {sums[k]:.1%}' for k in range(n_b)) + '）')
    # ---- ② 投票停滞 ----
    if int(state.get('vote_stale') or 0) >= _DIS_VOTE_PATIENCE:
        return (f'停滞（投票制）：连续 {state["vote_stale"]} 次评估里"优于上一次"的楼数'
                f'都没到 {need}/{n_b} 栋')
    # ---- ③ 单栋恶化 ----
    bad = [k for k in range(n_b) if worsen[k] >= _DIS_WORSEN_PATIENCE]
    if bad:
        return ('单栋恶化：' + '、'.join(f'B{k + 1}' for k in bad)
                + f' 连续 {_DIS_WORSEN_PATIENCE} 次高于「自身历史最优 +{_DIS_WORSEN_MARGIN:.0%}」'
                + '（避免用更差的模型去跑正式评估）')
    return None


# =============================================================================
# 四、命令行
# =============================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='区域级 MARL 训练（District-aware Multi-Agent SAC）')
    p.add_argument('--train-epochs', type=int, default=dc.DISTRICT_TRAIN_EPOCHS)
    p.add_argument('--output-dir', type=str, default=None)
    p.add_argument('--checkpoint-dir', type=str, default=None,
                   help='断点写入目录；不传 = <output-dir>/checkpoints/multi_agent_resume'
                        '（平台按任务目录落盘，评估端用 --train-task-id 定位）')
    p.add_argument('--seed', type=int, default=dc.DISTRICT_SEED)
    # --train-schema 是平台 Multi-agent 系列的约定别名，一并接受便于后续接入白名单
    p.add_argument('--schema', '--train-schema', dest='schema', type=str,
                   default=dc.DISTRICT_TRAIN_SCHEMA)
    p.add_argument('--eval-schema', type=str, default=dc.DISTRICT_EVAL_SCHEMA)
    p.add_argument('--eval-every', type=int, default=dc.DISTRICT_EVAL_EVERY)
    p.add_argument('--eval-steps', type=int, default=0,
                   help='评估段长（0 = 用数据集默认整段）')
    p.add_argument('--no-shared-policy', action='store_true',
                   help='关闭参数共享（每 agent 独立策略）')
    p.add_argument('--no-district-obs', action='store_true',
                   help='关闭区域观测（退化为原 ContextRLlibEnv）')
    p.add_argument('--peak-weight', type=float, default=dc.DISTRICT_PEAK_WEIGHT)
    p.add_argument('--team-share', type=float, default=dc.DISTRICT_TEAM_SHARE)
    p.add_argument('--stagger-weight', type=float, default=dc.DISTRICT_STAGGER_WEIGHT)
    p.add_argument('--attribution', type=float, default=dc.DISTRICT_ATTRIBUTION,
                   help='【方案 1】按贡献分摊区域惩罚的强度（0=均摊, 1=严格按份额）')
    p.add_argument('--peak-anchored', type=float, default=dc.DISTRICT_PEAK_ANCHORED,
                   help='【方案 2】峰值-锚定：接近/超过本局峰值的步放大惩罚（0=关, 1=开）')
    # 【方案 5】峰前储能预留（默认 0 = 关 ⇒ 与升级前逐位一致）
    p.add_argument('--soc-reserve-weight', type=float,
                   default=dc.DISTRICT_SOC_RESERVE_WEIGHT,
                   help='【方案 5】傍晚窗内低 SOC 惩罚权重（0=关，默认）。'
                        '单步最大缺口=目标−0.2=0.4，A/B 档位建议 60 / 150。')
    p.add_argument('--soc-reserve-hours', type=str,
                   default=','.join(f'{float(v):g}' for v in dc.DISTRICT_SOC_RESERVE_HOURS),
                   help='【方案 5】预留窗口的 hour 闭区间，如 "17,22"（hour 取值 1..24）')
    p.add_argument('--soc-reserve-target', type=float,
                   default=dc.DISTRICT_SOC_RESERVE_TARGET,
                   help='【方案 5】窗口内的 SOC 水位目标（低于它才罚；默认 0.60）')
    # 【方案 6】尖峰步豁免（默认 0 = 关 ⇒ 与方案 5 原样逐位一致）
    p.add_argument('--soc-reserve-ns-gate', type=float,
                   default=dc.DISTRICT_SOC_RESERVE_NS_GATE,
                   help='【方案 6】尖峰步豁免阈值（kW）：社区不可移负荷超过它时本步豁免预留罚。'
                        '0=关（默认）。建议 6.0 —— 实测命中 #669(15.39) 与 #643(9.10)。')
    # 【方案 7】尖峰步充放计价（默认 0 = 关 ⇒ 与方案 6 原样逐位一致）
    p.add_argument('--soc-reserve-spike-weight', type=float,
                   default=dc.DISTRICT_SOC_RESERVE_SPIKE_WEIGHT,
                   help='【方案 7】尖峰(豁免)步的电池流计价权重：豁免步 '
                        'r_i -= w × electrical_storage_electricity_consumption_i '
                        '（充为正⇒罚 / 放为负⇒奖），堵住"尖峰步反充自己抬新峰"。'
                        '0=关（默认）。flow 上限≈3.32 kWh ⇒ 建议 60 / 150。')
    # 【方案 3】结构化动作空间
    p.add_argument('--peak-action-dim', type=int, default=dc.DISTRICT_PEAK_ACTION_DIM,
                   help='【方案 3】结构化削峰动作维数（0=关，动作空间保持 3 维；'
                        '1=每 agent 动作扩为 4 维，新增 a_peak_resp∈[0,1]）')
    p.add_argument('--peak-resp-cool-frac', type=float,
                   default=dc.DISTRICT_PEAK_RESP_COOL_FRAC,
                   help='【方案 3】a_peak_resp=1 时的制冷开度倍率（<1 = 降额）')
    p.add_argument('--peak-resp-batt-discharge', type=float,
                   default=dc.DISTRICT_PEAK_RESP_BATT_DISCHARGE,
                   help='【方案 3】a_peak_resp=1 时电池维目标值（-1 = 最大放电）')
    p.add_argument('--peak-action-gated', type=int,
                   default=dc.DISTRICT_PEAK_ACTION_GATED,
                   help='【方案 3】是否只在峰值步允许削峰动作（0=不门控=纯学习 3a；'
                        '1=峰值步门控=残差式 3b）')
    # 【方案 4】SAC 旋钮（不换算法）
    # 默认值 = district_config 的 v4 常量（可复现最优：buffer 20 万 + τ 2e-3 + n_step 1）。
    # 显式传 CLI 时行为与改前逐位一致 —— 三个常量只是"默认值来源"，不参与逻辑判断。
    p.add_argument('--replay-buffer-cap', type=int,
                   default=dc.DISTRICT_REPLAY_BUFFER_CAP,
                   help='【方案 4】replay buffer 容量（env-step）。'
                        '默认 200000（= v4 可复现最优；旧项目默认 50000）。'
                        '0 = 用 RLlib 默认（不推荐）。')
    p.add_argument('--sac-tau', type=float, default=dc.DISTRICT_SAC_TAU,
                   help='【方案 4】SAC target 网络软更新系数（τ）。'
                        '默认 2e-3（= v4 可复现最优；RLlib 默认 5e-3）。降 = 更软 / 升 = 更硬。')
    p.add_argument('--sac-n-step', type=int, default=dc.DISTRICT_SAC_N_STEP,
                   help='【方案 4】n-step return。1=单步 TD（默认，= v4）。'
                        '>1 = 多步回报（3 = v4n）。注：>1 需 rollout_fragment_length >= n_step。')
    p.add_argument('--best-metric', type=str, default=dc.DISTRICT_BEST_METRIC)
    # ---- 验收口径（不影响训练与断点，只影响"报告哪个数"）----
    p.add_argument('--accept-stat', type=str, default=dc.DISTRICT_ACCEPT_STAT,
                   choices=list(_ACCEPT_STATS),
                   help='主验收统计量（默认 mean_last3）。best = 旧的 min-over-epochs 口径。')
    p.add_argument('--accept-tail', type=int, default=int(dc.DISTRICT_ACCEPT_TAIL),
                   help='mean_last3 的窗口（默认 3）；仅 mean_last3/mean_last 用得到。')
    # 确定性协议：值取 random/none/off 表示不干预；在解释器重启时生效（预扫描 argv）
    p.add_argument('--hashseed', type=str,
                   default=os.environ.get('DISTRICT_HASHSEED', '0'),
                   help='固定 PYTHONHASHSEED 以保证同 config+同 seed 逐位可复现'
                        '（默认 0；random = 不干预）。')
    # nargs='?'：Java 侧对某些脚本会追加**裸** `--resume`（不带值），这里要能兼容
    p.add_argument('--resume', nargs='?', const='', default=None,
                   help='从 checkpoint 目录续训；不带值 = 用本次默认断点目录')
    p.add_argument('--quick', action='store_true',
                   help='冒烟模式：3 轮 + 每轮评估 + 短评估段')
    # ---- 诊断埋点（2026-10-17；见文首「诊断埋点」与「四·五」节）------------
    #   默认**全开**：它们只写额外文件，不改 `algo.train()` / 评估 / 选点 / 断点任何一步。
    p.add_argument('--no-diag', action='store_true',
                   help='关闭全部诊断埋点（RL 内部指标 / 奖励分解 / 不适曲线 / 轨迹 / SOC 读数）'
                        '⇒ 产物回到旧行为：只写 district_metrics.csv / district_summary.json'
                        '/ exported_kpis.csv。⚠️ summary.json 仍会多 `early_stop` 块与 '
                        '`config.peak_stop_patience` 两个键；要连这两个也回到旧字节，'
                        '再加 `--peak-stop-patience 0`。训练轨迹始终逐位一致')
    p.add_argument('--discomfort-stop', action='store_true',
                   help='开启「不适曲线」早停判据（①达标 ②投票停滞 ③单栋恶化 ④收敛 ⑤崩坏）。'
                        '默认**关** ⇒ 只记录曲线、不干预训练（零侵入）；'
                        '开启后训练会提前结束，但收尾的正式评估照常跑')
    p.add_argument('--min-train-epochs', type=int, default=160,
                   help='早停判据 ①②③④ 的生效率前最小轮数（默认 160）。'
                        '⑤崩坏止损只体检一次、受 _DIS_SAT_EPOCH=100 控制，不受此限制')
    p.add_argument('--peak-stop-patience', type=int,
                   default=int(getattr(dc, 'DISTRICT_PEAK_STOP_PATIENCE', 0) or 0),
                   help='【峰值早停】连续 N 轮未刷新 best（epoch − best_epoch ≥ N）即提前收工'
                        '（默认 40；0 = 关）。best-checkpoint 在停之前已保存 ⇒ 收尾评估'
                        '用的仍是最优权重、产物格式不变。'
                        'v4 的 best_epoch=60/100/100，在 100 轮任务下不会触发；'
                        '320 轮任务通常能省掉后 40%~50% 的时间，并避免末窗落到更差的评估点。')
    p.add_argument('--peak-stop-min-epochs', type=int,
                   default=int(getattr(dc, 'DISTRICT_PEAK_STOP_MIN_EPOCHS', 0) or 0),
                   help='【峰值早停】最早轮数下限（默认 100；0 = 自动取 min(轮数,100)）。'
                        '与 patience 是「且」关系。默认值保证 100 轮任务**永远跑满** ⇒ '
                        'v4 口径分毫不动；320 轮任务仍能省掉后半段。')
    p.add_argument('--trace-every', type=int, default=0,
                   help='每 N 次评估额外落一份逐时步轨迹 district_trace_ep<轮>.npz'
                        '（0 = 不额外落；**最终评估始终**落 district_trace_final.npz）')
    # ---- 决策推演日志（模型优选界面用；默认开，传参才关）----
    p.add_argument('--no-decision-log', action='store_true',
                   help='关闭最终评估的决策推演日志（decision_trace.json）。'
                        '默认**开启**并全量记录：每步一条、动作记全 DHW/电池/冷却三维；'
                        '训练循环内的中间评估始终不记（避免每轮都攒一份大文件）。')
    p.add_argument('--decision-log-stride', type=int, default=1,
                   help='最终评估的决策推演每 N 步记一条（默认 1 = 逐步全记）')
    p.add_argument('--decision-log-max-steps', type=int, default=0,
                   help='最终评估的决策推演条数上限（默认 0 = 不限制）')
    # parse_known_args：平台可能追加本脚本不认识的 flag（例如 Multi-agent 系列专用参数），
    # 认识不了就忽略并提示，避免因一个无关参数直接 argparse 退出（exit 2）。
    args, unknown = p.parse_known_args(argv)
    if unknown:
        log_console(f'[district-marl] 忽略未识别的命令行参数: {unknown}')
    args.unknown_args = list(unknown)
    return args


# =============================================================================
# 五、主流程
# =============================================================================

def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.quick:
        args.train_epochs = min(int(args.train_epochs), 3)
        args.eval_every = 1
        if not args.eval_steps:
            args.eval_steps = 168

    here = Path(__file__).resolve().parent
    run_tag = time.strftime('%Y%m%d_%H%M%S')
    output_dir = Path(args.output_dir) if args.output_dir else (
        here / 'runs' / f'district_{run_tag}')
    # 断点默认写进「本次任务/运行目录」下的固定相对路径（与平台约定一致）：
    #   平台传 --output-dir=<任务目录> ⇒ 断点落在 <任务目录>/checkpoints/multi_agent_resume，
    #   评估用 --train-task-id 按任务 id 就能定位到（不再共用一个全局目录互相覆盖）。
    #   仍可用 --checkpoint-dir 显式覆盖（自定义目录 / 兼容旧用法）。
    if args.checkpoint_dir:
        ckpt_dir = Path(args.checkpoint_dir)
    else:
        ckpt_dir = output_dir / dc.DISTRICT_CKPT_REL_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    log_console('=' * 72)
    log_console('[district-marl] 区域级 MARL 训练（District-aware Multi-Agent SAC）')
    log_console('=' * 72)
    log_console(f'  训练 schema   : {args.schema}')
    log_console(f'  评估 schema   : {args.eval_schema}')
    log_console(f'  轮数          : {args.train_epochs}（每 {args.eval_every} 轮评估）')
    log_console(f'  参数共享      : {not args.no_shared_policy}')
    log_console(f'  区域观测      : {not args.no_district_obs}')
    log_console(f'  区域奖励      : 尖峰权重={args.peak_weight:g} '
                f'团队混合={args.team_share:g} 错峰={args.stagger_weight:g} '
                f'分摊={args.attribution:g} 峰锚={args.peak_anchored:g}')
    _res_w = float(args.soc_reserve_weight)
    if _res_w > 0.0:
        _gate = float(getattr(args, 'soc_reserve_ns_gate', 0.0) or 0.0)
        log_console(f'  峰前储能预留  : 权重={_res_w:g} '
                    f'窗口=[{args.soc_reserve_hours}]h 水位目标={args.soc_reserve_target:g}'
                    f'（窗内 r -= w × max(0, 目标 − SOC)）')
        log_console(f'  尖峰步豁免    : ' + (
            f'开（社区不可移负荷 > {_gate:g} kW 时本步豁免上面那项）'
            if _gate > 0.0 else '关闭（ns_gate=0）'))
        _spike_w = float(getattr(args, 'soc_reserve_spike_weight', 0.0) or 0.0)
        log_console(f'  尖峰充放计价  : ' + (
            f'开（豁免步 r -= {_spike_w:g} × 本栋电池流；充⇒罚、放⇒奖）'
            if (_gate > 0.0 and _spike_w > 0.0) else
            ('关闭（权重 0）' if _gate > 0.0 else '未启用（需先开 ns_gate）')))
    else:
        log_console('  峰前储能预留  : 关闭（权重 0）')
    if int(args.peak_action_dim) > 0:
        log_console(f'  结构化动作    : 动作 3→{3 + int(args.peak_action_dim)} 维 '
                    f'(a_peak_resp∈[0,1]) 制冷降额×{args.peak_resp_cool_frac:g} '
                    f'电池放电→{args.peak_resp_batt_discharge:g} '
                    f'门控={"峰值步" if int(args.peak_action_gated) else "无(3a纯学习)"}')
    else:
        log_console('  结构化动作    : 关闭（动作空间 3 维）')
    log_console(f'  best 选点指标 : {args.best_metric}（次选 {dc.DISTRICT_BEST_TIEBREAK}）')
    log_console(f'  验收口径      : {args.accept_stat}'
                f'（主指标 {args.best_metric}，尾窗 {int(args.accept_tail)}；'
                f'best 保留作参考）')
    try:
        from district_marl import _hashseed as _hs
        log_console(f'  可复现性      : {_hs.describe()}')
    except Exception:
        pass
    log_console(f'  输出目录      : {output_dir}')
    log_console(f'  断点目录      : {ckpt_dir}（供评估按任务 id 定位）')
    diag_on = not bool(getattr(args, 'no_diag', False))
    _stop_on = bool(getattr(args, 'discomfort_stop', False))
    log_console('  诊断埋点      : ' + (
        '关闭（--no-diag）⇒ 只写 district_metrics.csv'
        if not diag_on else
        '开（district_rl_diag.csv / district_reward_breakdown.csv / '
        'district_discomfort_curve.* / district_trace_ep*.npz）'))
    log_console('  不适曲线早停  : ' + (
        f'开（最小轮数 {int(getattr(args, "min_train_epochs", 160) or 160)}；'
        f'①达标②投票停滞③单栋恶化④收敛⑤崩坏）'
        if (_stop_on and diag_on) else
        ('关（仅记录曲线，不干预训练）' if diag_on else '不可用（诊断埋点已关）')))
    _peak_patience_log = int(getattr(args, 'peak_stop_patience', 0) or 0)
    _peak_min_log = int(getattr(args, 'peak_stop_min_epochs', 0) or 0) or min(
        int(args.train_epochs), 100)
    log_console('  峰值早停      : ' + (
        f'开（≥{_peak_min_log} 轮且连续 {_peak_patience_log} 轮未刷新 best 即停；'
        f'停前 best-checkpoint 已保存）'
        if _peak_patience_log > 0 else '关（跑满设定轮数）'))

    # ---- einsum-free 覆盖：把命令行值写回 district_config 的模块级开关 ----
    dc.DISTRICT_SHARED_POLICY = not args.no_shared_policy
    dc.DISTRICT_BEST_METRIC = str(args.best_metric)
    # 【验收口径】只影响"报告/比较哪个数"，不影响训练与 best-checkpoint 挑选
    dc.DISTRICT_ACCEPT_STAT = str(args.accept_stat)
    dc.DISTRICT_ACCEPT_TAIL = int(args.accept_tail)
    # 奖励参数（CLI → 模块常量 → district_reward_kwargs() 才会用到）
    dc.DISTRICT_PEAK_WEIGHT = float(args.peak_weight)
    dc.DISTRICT_TEAM_SHARE = float(args.team_share)
    dc.DISTRICT_STAGGER_WEIGHT = float(args.stagger_weight)
    dc.DISTRICT_ATTRIBUTION = float(args.attribution)
    dc.DISTRICT_PEAK_ANCHORED = float(args.peak_anchored)
    # 【方案 5】峰前储能预留（0 = 关 ⇒ 奖励侧整段不执行，与升级前逐位一致）
    dc.DISTRICT_SOC_RESERVE_WEIGHT = float(args.soc_reserve_weight)
    dc.DISTRICT_SOC_RESERVE_TARGET = float(args.soc_reserve_target)
    # 【方案 6】尖峰步豁免阈值（0 = 关 ⇒ 与方案 5 原样逐位一致）
    dc.DISTRICT_SOC_RESERVE_NS_GATE = float(getattr(args, 'soc_reserve_ns_gate', 0.0) or 0.0)
    # 【方案 7】尖峰步充放计价（0 = 关 ⇒ 与方案 6 原样逐位一致）
    dc.DISTRICT_SOC_RESERVE_SPIKE_WEIGHT = float(
        getattr(args, 'soc_reserve_spike_weight', 0.0) or 0.0)
    _res_hours = [float(x) for x in str(args.soc_reserve_hours).replace('，', ',').split(',')
                  if str(x).strip() != '']
    dc.DISTRICT_SOC_RESERVE_HOURS = (tuple(_res_hours[:2]) if len(_res_hours) >= 2
                                     else tuple(dc.DISTRICT_SOC_RESERVE_HOURS))
    # 【方案 3】结构化动作维（0 = 关；>0 = 动作空间扩维）
    dc.DISTRICT_PEAK_ACTION_DIM = int(args.peak_action_dim)
    dc.DISTRICT_PEAK_RESP_COOL_FRAC = float(args.peak_resp_cool_frac)
    dc.DISTRICT_PEAK_RESP_BATT_DISCHARGE = float(args.peak_resp_batt_discharge)
    dc.DISTRICT_PEAK_ACTION_GATED = int(args.peak_action_gated)

    # ---- Ray 侧就地 import ----
    from ray.rllib.algorithms.sac import SACConfig as Config
    from ray.rllib.policy.policy import PolicySpec
    from utils.config import (
        CKPT_STORE_REPLAY_BUFFER,
        MIN_SAMPLE_BEFORE_LEARN,
        MIN_SAMPLE_TIMESTEPS_PER_ITERATION,
        REPLAY_BUFFER_CAPACITY,
        ROLLOUT_FRAGMENT_LENGTH,
        TRAIN_BATCH_SIZE,
        TRAIN_INTENSITY,
    )
    from utils.train import (
        ensure_ray_initialized,
        install_action_hook,
        save_multi_agent_checkpoint,
    )

    ensure_ray_initialized(log_console=log_console)
    # 与 Multi-agent.py 同一口径：把动作喂给奖励，制冷电费/电池择时等"动作相关项"才会生效。
    # 本类的 step 覆写过，但 MRO 会走到被包装的 RLlibMultiAgentEnv.step ⇒ 注入依然有效。
    log_console(f'  奖励动作注入 : {install_action_hook()}')

    # ---- 环境配置 ----
    # 回合长度与 Multi-agent-train.py 同一约定：不显式指定就不传 episode_time_steps，
    #   交给 CityLearn 用**数据集自带长度**（dataset 的 simulation_end_time_step + 1）。
    #   --eval-steps 只用于「显式缩短」（例如冒烟测试）。
    #   ⚠️ 原先查硬编码表 _SCHEMA_DEFAULT_EPISODE_STEPS ⇒ 未登记的 schema 会被静默按 720
    #   跑（截断回合）；那张表已按项目约定弃用（见 utils/env.py 与 CHESCA.py 的说明）。
    train_steps = None
    eval_steps = int(args.eval_steps) if args.eval_steps else None

    train_env_config = build_district_env_config(
        args.schema, train_steps, enable_render=False,
        record_details=False, district_obs=not args.no_district_obs)
    eval_env_config = build_district_env_config(
        args.eval_schema, eval_steps, enable_render=False,
        output_dir=output_dir, record_details=True,
        district_obs=not args.no_district_obs)
    log_console(f'  回合步数      : 训练='
                f'{"auto(数据集自带)" if train_steps is None else train_steps}'
                f' / 评估={"auto(数据集自带)" if eval_steps is None else eval_steps}')

    # ---- 策略映射（共享 / 独立）----
    probe = DistrictContextRLlibEnv(train_env_config)
    agent_ids = list(probe._agent_ids)
    obs_dim = int(np.asarray(probe.observation_space[agent_ids[0]].shape).prod())
    del probe
    log_console(f'  agent 数       : {len(agent_ids)}（{", ".join(agent_ids)}）')
    log_console(f'  观测维度/agent : {obs_dim}'
                f'（区域维 {len(_district_feature_names()) if not args.no_district_obs else 0}）')

    shared = bool(dc.DISTRICT_SHARED_POLICY)
    if shared:
        policies = {'shared': PolicySpec()}
        policy_id_fn = lambda _aid: 'shared'          # noqa: E731
        policy_mapping_fn = lambda aid, episode, worker, **kw: 'shared'  # noqa: E731
    else:
        policies = {a: PolicySpec() for a in agent_ids}
        policy_id_fn = lambda aid: aid                # noqa: E731
        policy_mapping_fn = lambda aid, episode, worker, **kw: aid       # noqa: E731

    # ---- 算法配置（超参与原流水线同源，保证可比）----
    # 【方案 4】SAC 旋钮：buffer / τ / n_step。
    #   默认值已经是 v4 可复现最优（buffer 20 万 / τ 2e-3 / n_step 1）；
    #   显式传 CLI 可覆盖（对照实验用）。
    rb_capacity = int(args.replay_buffer_cap)
    rb_kwargs = ({'replay_buffer_config': {'capacity': int(rb_capacity)}}
                 if rb_capacity else {})
    # RLlib 的 tau 默认 5e-3：等于它就不下发（少一行日志噪音，语义不变）
    sac_kwargs = {}
    if float(args.sac_tau) != 5e-3:
        sac_kwargs['tau'] = float(args.sac_tau)
    if int(args.sac_n_step) > 1:
        sac_kwargs['n_step'] = int(args.sac_n_step)
    _is_v4 = (rb_capacity == int(dc.DISTRICT_REPLAY_BUFFER_CAP)
              and float(args.sac_tau) == float(dc.DISTRICT_SAC_TAU)
              and int(args.sac_n_step) == int(dc.DISTRICT_SAC_N_STEP))
    log_console(f'  SAC 旋钮       : buffer={rb_capacity}  τ={float(args.sac_tau):g}  '
                f'n_step={int(args.sac_n_step)}'
                f'{"（= v4 可复现最优）" if _is_v4 else "（非 v4 默认值，已偏离）"}'
                f'  [下发={sorted(list(sac_kwargs) + list(rb_kwargs)) or "无"}]')
    config = (
        Config()
        .environment(DistrictContextRLlibEnv, env_config=train_env_config)
        .multi_agent(policies=policies, policy_mapping_fn=policy_mapping_fn)
        .training(
            train_batch_size=TRAIN_BATCH_SIZE,
            training_intensity=TRAIN_INTENSITY,
            num_steps_sampled_before_learning_starts=MIN_SAMPLE_BEFORE_LEARN,
            store_buffer_in_checkpoints=CKPT_STORE_REPLAY_BUFFER,
            **sac_kwargs,
            **rb_kwargs,
        )
        .rollouts(num_rollout_workers=0, rollout_fragment_length=ROLLOUT_FRAGMENT_LENGTH)
        .reporting(min_sample_timesteps_per_iteration=MIN_SAMPLE_TIMESTEPS_PER_ITERATION)
        .debugging(seed=int(args.seed))
    )

    resume_path = args.resume
    if resume_path == '':                      # 裸 --resume ⇒ 用本次默认断点目录
        resume_path = str(ckpt_dir)
    if resume_path and not Path(resume_path).exists():
        # 首次训练时平台可能已经打开了「续训」开关 ⇒ 不该直接崩，改为从头训
        log_console(f'  续训          : {resume_path} 不存在，改为从零训练')
        resume_path = None
    if resume_path:
        from ray.rllib.algorithms.algorithm import Algorithm
        algo = Algorithm.from_checkpoint(str(resume_path))
        log_console(f'  续训          : 已从 {resume_path} 恢复')
    else:
        algo = config.build()

    # ---- 训练主循环 ----
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    best_score: Optional[Tuple[float, float]] = None
    best_epoch: Optional[int] = None
    epochs_done = 0
    t0 = time.perf_counter()

    # ---- 诊断埋点的运行态（diag_on=False ⇒ 下面全为空，行为与改前逐位一致）----
    _curve_paths = [output_dir / _DIS_CURVE_JSON, ckpt_dir / _DIS_CURVE_JSON]
    _rl_csv = output_dir / 'district_rl_diag.csv'
    _reward_csv = output_dir / 'district_reward_breakdown.csv'
    _curve_csv = output_dir / _DIS_CURVE_CSV
    _trace_final_npz = output_dir / 'district_trace_final.npz'
    _curve: List[Dict[str, Any]] = []
    _stop_state: Dict[str, Any] = {}
    _stop_min_epochs = int(getattr(args, 'min_train_epochs', 160) or 160)
    _stop_on = bool(diag_on and getattr(args, 'discomfort_stop', False))
    # 【峰值早停】与"不适曲线早停"是两个独立机制：前者按**区域峰值 best 停滞**判定，
    # 不依赖诊断埋点（--no-diag 也能用）；0 = 关。
    _peak_patience = int(getattr(args, 'peak_stop_patience', 0) or 0)
    # 最早轮数下限：0/未给 ⇒ min(总轮数, 100) ⇒ 100 轮任务永远跑满（旧口径不动）
    _peak_min_epochs = int(getattr(args, 'peak_stop_min_epochs', 0) or 0)
    if _peak_min_epochs <= 0:
        _peak_min_epochs = min(int(args.train_epochs), 100)
    _stopped_reason: Optional[str] = None
    _pending_stop: Optional[str] = None      # 本轮判出的停训原因（延迟到选点之后再停）
    _n_rl_rows = 0
    _n_reward_rows = 0
    _n_trace_files = 0
    # ---- [埋点 E] 耗时分解 + 训练健康自检（2026-10-17）------------------------
    #   为什么需要：`elapsed_s` 只有一个总数。训练突然变慢时，无法判断是「采样慢
    #   （env）」「学得慢（算力）」还是「评估慢（rollout 720/2208 步）」——
    #   没有这个分解，任何性能优化都是盲改。
    #   ⚠️ 与其它埋点同一个门控：`--no-diag` 时一行不写、一个键不加。
    _perf_csv = output_dir / 'district_perf.csv'
    _perf_tot: Dict[str, float] = {'train_s': 0.0, 'eval_s': 0.0,
                                   'save_s': 0.0, 'other_s': 0.0}
    _n_perf_rows = 0
    _learn_active_epoch: Optional[int] = None      # 第一次真正发生梯度更新的轮次
    _grad_updates_total: Optional[float] = None    # 末轮累计梯度更新次数
    _env_steps_total: Optional[float] = None       # 末轮累计采样环境步数
    _nan_kpi_epochs: List[int] = []                # 出现 NaN 主指标的评估点

    def _record_perf(epoch: int, t_epoch: float, train_s: float,
                     eval_s: float = 0.0, save_s: float = 0.0,
                     eval_steps: int = 0) -> None:
        """记录本轮耗时分解。`other_s` = 本轮总时长 − 上述三段（曲线/日志/落盘）。"""
        nonlocal _n_perf_rows
        if not diag_on:
            return
        total = max(0.0, time.perf_counter() - t_epoch)
        other = max(0.0, total - train_s - eval_s - save_s)
        _perf_tot['train_s'] += train_s
        _perf_tot['eval_s'] += eval_s
        _perf_tot['save_s'] += save_s
        _perf_tot['other_s'] += other
        append_csv_row(_perf_csv, {
            'epoch': int(epoch),
            'train_s': round(train_s, 3),
            'eval_s': round(eval_s, 3),
            'save_s': round(save_s, 3),
            'other_s': round(other, 3),
            'epoch_total_s': round(total, 3),
            'wall_s': round(time.perf_counter() - t0, 1),
            'eval_steps': int(eval_steps),
            'env_steps_sampled_total': (None if _env_steps_total is None
                                        else int(_env_steps_total)),
        })
        _n_perf_rows += 1

    if diag_on:
        # 续训：继承已有曲线与早停判据基线（utils/train.py 的 P19-1 同一个坑：
        #   绝不能拿空数组覆盖已有曲线 ⇒ load 只在读到非空时才返回）
        _curve, _stop_state = load_discomfort_curve(_curve_paths)

    for epoch in range(1, int(args.train_epochs) + 1):
        _t_epoch = time.perf_counter()
        _t_train = _t_epoch
        try:
            _result = algo.train()
        except Exception as exc:
            log_console(f'[district-marl] 第 {epoch} 轮训练异常，提前收工: {exc}')
            break
        _train_s = time.perf_counter() - _t_train
        epochs_done = epoch

        # ---- [埋点 P0-①] RL 内部指标：**每轮**都记（不受 --eval-every 影响）----
        #   粒度必须逐轮 —— loss / entropy / grad_norm 曲线要能看出"KPI 突变"之前
        #   有没有发散前兆；原实现把 `algo.train()` 返回值整个丢弃，等于零观测。
        if diag_on:
            _rl_row: Dict[str, Any] = {
                'epoch': epoch,
                'elapsed_s': round(time.perf_counter() - t0, 1),
            }
            _rl_row.update(rl_stats_from_result(_result))
            if len(_rl_row) > 2:
                append_csv_row(_rl_csv, _rl_row)
                _n_rl_rows += 1
            # ---- 训练健康体征：这三项只在 diag_on 下取，且都"取不到就留空" ----
            #   learn_active_epoch: 第一次 `num_grad_updates_lifetime > 0` 的轮次。
            #     在此之前策略仍是随机初始化 ⇒ 该点的 KPI **不是**"学到的表现"，
            #     和其它评估点摆在一张表里比较会得出错误结论。
            _gu = _rl_row.get('rl_num_grad_updates_lifetime')
            if _gu is not None and np.isfinite(_f(_gu)):
                _grad_updates_total = _f(_gu)
                if _learn_active_epoch is None and _grad_updates_total > 0:
                    _learn_active_epoch = int(epoch)
            _es = _rl_row.get('rl_num_env_steps_sampled')
            if _es is not None and np.isfinite(_f(_es)):
                _env_steps_total = _f(_es)

        if epoch % max(1, int(args.eval_every)) != 0 and epoch != int(args.train_epochs):
            # 本轮不评估 ⇒ 仍要落一行耗时分解，否则「训练阶段占比」会被低估
            _record_perf(epoch, _t_epoch, _train_s, 0.0, 0.0, 0)
            continue

        # ---- [埋点 P0-②/③] 评估顺带取奖励分解与不适曲线；轨迹按 --trace-every ----
        _diag_out: Dict[str, Any] = {}
        _trace: Dict[str, Any] = {}
        _every = int(getattr(args, 'trace_every', 0) or 0)
        _want_trace = bool(diag_on and _every and (epoch % _every == 0))
        _t_eval = time.perf_counter()
        metrics = rollout_district(
            algo, DistrictContextRLlibEnv, eval_env_config, policy_id_fn,
            deterministic=True, max_steps=int(args.eval_steps or 0),
            trace_out=(_trace if _want_trace else None),
            diag_out=(_diag_out if diag_on else None),
            # 训练循环内的评估**显式关闭**决策推演日志（这是"传参才不记录"的那一处）：
            # 每轮都记一遍只会把内存撑爆，真正要看的推演由评估任务（district_eval）产出。
            decision_log=None)
        _eval_s = time.perf_counter() - _t_eval
        _eval_steps = int(metrics.get('eval_steps') or 0)
        row: Dict[str, Any] = {'epoch': epoch, 'elapsed_s': round(time.perf_counter() - t0, 1)}
        row.update(metrics)
        # [埋点 D] SOC 读数并入本轮行 ⇒ 同时进 district_summary.history 与
        # district_metrics.csv；--no-diag 时 _diag_out 为空 ⇒ 不多键（旧产物逐字节一致）
        if diag_on and _diag_out.get('soc'):
            row.update(_diag_out['soc'])
        rows.append(row)
        if diag_on and not np.isfinite(_f(metrics.get(args.best_metric))):
            _nan_kpi_epochs.append(int(epoch))

        if diag_on:
            # ---- 奖励分解落盘（district_stats/district_summary 此前全仓库零调用）----
            if _diag_out.get('reward'):
                # tag 区分两种评估：loop = 循环内（每 --eval-every 轮）/ final = 收尾正式评估。
                # 末轮两者会各写一行（同一批权重、数值应当基本一致）—— 加 tag 后
                # 一眼能看出"这是同一次评估的重复记录"，而不是两次结果打架。
                _rw_row: Dict[str, Any] = {'epoch': epoch, 'tag': 'loop'}
                _rw_row.update(_numeric_only(_diag_out['reward']))
                _rw_row.update({('stats_' + k): v for k, v in
                                _numeric_only(_diag_out.get('reward_stats') or {}).items()})
                append_csv_row(_reward_csv, _rw_row)
                _n_reward_rows += 1
                if _diag_out.get('reward_summary'):
                    log_console('  ' + str(_diag_out['reward_summary']))

            # ---- 不适曲线（移植自 Multi-agent-train 的中期评估机制）----
            _dis_row = flatten_discomfort(epoch, _diag_out)
            _curve.append(_dis_row)
            append_csv_row(_curve_csv, _dis_row)
            _stop_reason = discomfort_stop_check(
                log_console, epoch, _dis_row, _stop_state,
                min_train_epochs=_stop_min_epochs, enabled=_stop_on)
            _tag = str(_stop_state.get('vote_txt') or '')
            if _stop_on:
                _tag = ' | '.join(x for x in (_tag, _stop_state.get('worsen_txt'),
                                              _stop_state.get('conv_txt')) if x)
                if _tag:
                    log_console('  [不适曲线] ' + _tag)
            log_console(format_discomfort_line(epoch, _dis_row, tag='' if _stop_on else _tag))
            save_discomfort_curve(_curve_paths, _curve, _stop_state)

            if _want_trace and _trace:
                _tp = output_dir / f'district_trace_ep{epoch}.npz'
                try:
                    np.savez_compressed(_tp, **_trace)
                    _n_trace_files += 1
                    log_console(f'  轨迹     : {_tp.name}（{trace_steps(_trace)} 步）')
                except Exception as exc:
                    log_console(f'[district-marl] 轨迹落盘失败（忽略）: {exc}')

            # ⚠️ 这里**只记原因、不 break** —— 必须让下面「best-checkpoint 保存」
            #   先跑完再停（utils/train.py 的 P1-B 同一个修复：早停判据若抢在选点之前，
            #   最后一轮的更优权重就不会被存下来，收尾评估反而用不到它）。
            _pending_stop = _stop_reason

        # 验收口径（主口径 = 末 K 个评估点均值；best 一并保留作参考）。
        # 只用于"报告/比较"，不影响上面的 best-checkpoint 挑选与落盘。
        accept = dacc.summarize(
            rows, args.best_metric, tail=int(args.accept_tail),
            tiebreak=dc.DISTRICT_BEST_TIEBREAK, stat=str(args.accept_stat))

        score = _score(metrics)
        tag = ''
        _save_s = 0.0
        if score is not None:
            improved = (best_score is None
                        or score[0] < best_score[0] - float(dc.DISTRICT_BEST_MIN_GAIN)
                        or (abs(score[0] - best_score[0]) <= float(dc.DISTRICT_BEST_MIN_GAIN)
                            and score[1] < best_score[1]))
            if improved:
                _t_save = time.perf_counter()
                saved = save_multi_agent_checkpoint(algo, ckpt_dir, log_console=log_console)
                best_score, best_epoch = score, epoch
                # 每次刷新 best 都同步进度文件 ⇒ 任务管理页随时能看到「模型可用」
                write_train_progress(ckpt_dir, epochs_done, int(args.train_epochs),
                                     score[0], epoch, accept=accept)
                _save_s = time.perf_counter() - _t_save
                tag = f'  ← best（已存 {Path(saved).name}）'

        # ---- 峰值早停（B）：best 之后连续 patience 轮无改善即收工 ----
        #   ① 放在 best 保存**之后** ⇒ 停之前最优权重一定已落盘，收尾评估用得到它；
        #   ② 与"不适曲线早停"共用同一个 _pending_stop 通道，break 统一在日志之后执行；
        #   ③ 只在"已有 best"时生效：前 patience 轮本来就该让它先找到第一个 best。
        if (_peak_patience > 0 and best_epoch is not None and score is not None
                and _pending_stop is None):
            _stale = epoch - int(best_epoch)
            if _stale >= _peak_patience and epoch >= _peak_min_epochs:
                _pending_stop = (
                    f'峰值早停：best={best_score[0]:.6f}@{best_epoch}，'
                    f'连续 {_stale} 轮未刷新（patience={_peak_patience}，'
                    f'最早轮数={_peak_min_epochs}）')

        _acc_v = accept.get('value')
        _best_v = accept.get('best')
        log_console(
            f'[district-marl] 第 {epoch:>4}/{args.train_epochs} 轮 | '
            f'社区峰值(原始)={metrics.get("district_peak_raw", float("nan")):.3f} '
            f'all_time_peak={metrics.get("all_time_peak_average", float("nan")):.4f} '
            f'daily_peak={metrics.get("daily_peak_average", float("nan")):.4f} '
            f'cost={metrics.get("cost_total", float("nan")):.4f} | '
            f'{args.accept_stat}={("nan" if _acc_v is None else format(_acc_v, ".4f"))} '
            f'best={("nan" if _best_v is None else format(_best_v, ".4f"))}{tag}')

        # 本轮耗时分解（在 break 之前落，早停那一轮的耗时也算进去）
        _record_perf(epoch, _t_epoch, _train_s, _eval_s, _save_s, _eval_steps)

        # ---- 早停：上面 best-checkpoint 的保存/比较已跑完 ⇒ 现在才真正停训 ----
        if _pending_stop:
            _stopped_reason = str(_pending_stop)
            _pending_stop = None
            log_console(f'[早停] 第 {epoch} 轮 {_stopped_reason} '
                        f'→ 提前结束训练（收尾的正式评估照常跑，用的是已保存的最优权重）')
            break

    # ---- 收尾：导出 ----
    _write_metrics_csv(output_dir / 'district_metrics.csv', rows)
    # 最终验收口径（主口径 = 末 K 个评估点均值；best/final/mean_all 一并留档）
    acceptance = dacc.summarize(
        rows, args.best_metric, tail=int(args.accept_tail),
        tiebreak=dc.DISTRICT_BEST_TIEBREAK, stat=str(args.accept_stat))
    # 训练结束补一次进度文件：覆盖「全程没有刷新过 best」的情形（此时断点目录里
    # 还没有任何 checkpoint 子目录，下面会把末次权重直接存进去，评估才能解析到它）。
    write_train_progress(ckpt_dir, epochs_done, int(args.train_epochs),
                         best_score[0] if best_score else None, best_epoch,
                         accept=acceptance)
    # 末次权重：有 best 时存到兄弟子目录 final（避免盖掉评估要用的 best），
    # 从未刷新过 best 时直接存进断点目录根（否则根目录里一个 checkpoint 都没有，
    # 评估端 resolve 会找不到可加载的断点）。
    final_dest = ckpt_dir if best_score is None else ckpt_dir / 'final'
    _t_final_save = time.perf_counter()
    try:
        save_multi_agent_checkpoint(algo, final_dest, log_console=log_console)
    except Exception as exc:
        log_console(f'[district-marl] 末次权重保存失败（忽略）: {exc}')
    _final_save_s = time.perf_counter() - _t_final_save

    # 最终区域评估 + 官方 KPI 导出（同一次 rollout 内完成，避免 reset 后读数失真）
    #   [埋点 P0-③] 这一段**始终**落逐时步轨迹 —— 事后想复盘"某轮 KPI 突变"
    #   一定是从最终评估这条轨迹开始看的（--trace-every 只是额外多落几份）。
    _final_diag: Dict[str, Any] = {}
    _final_trace: Dict[str, Any] = {}
    _final_decision: Dict[str, Any] = {}
    _t_final_eval = time.perf_counter()
    final = rollout_district(algo, DistrictContextRLlibEnv, eval_env_config,
                             policy_id_fn, deterministic=True,
                             max_steps=int(args.eval_steps or 0),
                             export_dir=output_dir,
                             trace_out=(_final_trace if diag_on else None),
                             diag_out=(_final_diag if diag_on else None),
                             # 默认记录；只有 --no-decision-log 才关
                             decision_log=(None if bool(getattr(
                                 args, 'no_decision_log', False)) else 'auto'),
                             decision_stride=int(getattr(args, 'decision_log_stride', 1) or 1),
                             decision_max_records=int(getattr(
                                 args, 'decision_log_max_steps', 0) or 0),
                             decision_out=_final_decision)
    _final_eval_s = time.perf_counter() - _t_final_eval
    if _final_decision.get('log') is not None:
        try:
            _dl = _final_decision['log']
            _dl_path = _dl.save(output_dir / 'decision_trace.json', extra_meta={
                'source': 'train_final_eval',
                'epochs_done': int(epochs_done),
                'schema': str(args.schema),
            })
            _dl_mb = _dl_path.stat().st_size / 1048576 if _dl_path.exists() else 0.0
            log_console(f'  决策推演 : {_dl_path.name}'
                        f'（{_dl.recorded_steps} 条 / 走过 {_dl.seen_steps} 步，'
                        f'{_dl_mb:.1f} MB，'
                        f'动作维 {"/".join(_dl._dim_names())}'
                        f'（每栋 {_dl.action_dim or "?"} 维 × {_dl.n_buildings} 栋）')
            if _dl.failures:
                log_console(f'    ⚠ 采集异常 {_dl.failures} 次（最后一条：{_dl._last_error}）')
        except Exception as exc:
            log_console(f'[district-marl] 决策推演落盘失败（忽略）: {exc}')
    if diag_on and _final_trace:
        try:
            np.savez_compressed(_trace_final_npz, **_final_trace)
            _n_trace_files += 1
            log_console(f'  最终轨迹 : {_trace_final_npz.name}'
                        f'（{trace_steps(_final_trace)} 步，'
                        f'键={sorted(k for k in _final_trace)})')
        except Exception as exc:
            log_console(f'[district-marl] 最终轨迹落盘失败（忽略）: {exc}')
    if diag_on and _final_diag.get('reward'):
        _rw_row = {'epoch': int(epochs_done), 'tag': 'final'}
        _rw_row.update(_numeric_only(_final_diag['reward']))
        _rw_row.update({('stats_' + k): v for k, v in
                        _numeric_only(_final_diag.get('reward_stats') or {}).items()})
        append_csv_row(_reward_csv, _rw_row)
        _n_reward_rows += 1
        if _final_diag.get('reward_summary'):
            log_console('  ' + str(_final_diag['reward_summary']))
    kpi_path = output_dir / 'exported_kpis.csv'
    if not kpi_path.is_file():
        kpi_path = None

    # ---- 指纹采集（只读，约 1.4 s）----
    #   ⚠️ 必须放在 `_wall_s` 之后：采集本身耗时不该算进训练耗时。
    #   `--no-diag` 时为 None ⇒ 不写键、不打日志，产物与改造前逐字节一致。
    _finger = _fp.fingerprint_block() if diag_on else None
    _wall_s = round(time.perf_counter() - t0, 1)
    try:
        _buffer_cap: Optional[int] = int(getattr(args, 'replay_buffer_cap', 0) or 0) or None
    except (TypeError, ValueError):
        _buffer_cap = None

    summary = {
        'config': {
            'train_epochs': int(args.train_epochs),
            'eval_every': int(args.eval_every),
            'shared_policy': shared,
            'district_obs': not args.no_district_obs,
            'peak_weight': float(args.peak_weight),
            'team_share': float(args.team_share),
            'stagger_weight': float(args.stagger_weight),
            'attribution': float(args.attribution),
            'peak_anchored': float(args.peak_anchored),
            'best_metric': str(args.best_metric),
            'seed': int(args.seed),
            'train_schema': str(args.schema),
            'eval_schema': str(args.eval_schema),
            # 验收口径（只影响报告，不影响训练）
            'accept_stat': str(args.accept_stat),
            'accept_tail': int(args.accept_tail),
            'pythonhashseed': (os.environ.get('PYTHONHASHSEED') or ''),
        },
        'best_epoch': best_epoch,
        'best_score': list(best_score) if best_score else None,
        # ★验收口径块：主口径 `acceptance.value`（默认 mean_last3），`best` 保留作参考。
        #   旧脚本读 `best_score` 仍然有效；新脚本优先读 `acceptance.value`
        #   （兼容读法见 district_acceptance.accept_value）。
        'acceptance': acceptance,
        'history': rows,
        'final_metrics': {k: float(v) for k, v in final.items()
                          if isinstance(v, (int, float))},
        'elapsed_s': _wall_s,
    }
    # ---- 峰值早停块（2026-10-17）----
    #   ⚠️ **只在 patience>0 时才加这两个键** ⇒ `--peak-stop-patience 0` 下
    #   district_summary.json 与改造前**逐字节一致**（配合 --no-diag 可完全回到旧产物）。
    #   `epochs_done < train_epochs` 表示没跑满；`reason` 与诊断埋点的 `stopped_reason` 同源
    #   （可能是"峰值早停"或"不适曲线早停"）。
    if int(_peak_patience) > 0:
        summary['config']['peak_stop_patience'] = int(_peak_patience)
        summary['config']['peak_stop_min_epochs'] = int(_peak_min_epochs)
        summary['early_stop'] = {
            'enabled': True,
            'patience': int(_peak_patience),
            'min_epochs': int(_peak_min_epochs),
            'reason': _stopped_reason,
            'epochs_done': int(epochs_done),
            'epochs_target': int(args.train_epochs),
            'best_epoch': best_epoch,
        }
    # ---- 诊断埋点块（2026-10-17）----
    #   ⚠️ 只在 diag_on 时才**追加**这三个键：`--no-diag` 下 district_summary.json
    #   与改造前**逐字节一致**（旧读法/旧哈希校验照旧通过）。
    #   曲线正文另存 district_discomfort_curve.json/csv，这里留一份便于单文件归档。
    if diag_on:
        summary['discomfort_curve'] = _curve
        summary['stopped_reason'] = _stopped_reason
        summary['diagnostics'] = {
            'enabled': True,
            'rl_diag_csv': str(_rl_csv),
            'reward_breakdown_csv': str(_reward_csv),
            'discomfort_curve_csv': str(_curve_csv),
            'discomfort_curve_json': str(_curve_paths[0]),
            'trace_final_npz': (str(_trace_final_npz) if _final_trace else None),
            'discomfort_stop_enabled': bool(_stop_on),
            'min_train_epochs': int(_stop_min_epochs),
            'n_rl_rows': int(_n_rl_rows),
            'n_reward_rows': int(_n_reward_rows),
            'n_trace_files': int(_n_trace_files),
            'perf_csv': str(_perf_csv),
            'n_perf_rows': int(_n_perf_rows),
        }

    # ---- 指纹块（2026-10-17）----
    #   回答「这台机器 + 这套依赖 + 这份源码」是不是和上次那次一样。
    #   `code.source_digest_16` 是判断"代码改没改"的最终依据（不依赖 git）；
    #   `code.git_dirty=true` 时**不能用 commit 号定位这次结果**。
    if diag_on and _finger:
        summary['fingerprint'] = _finger
        # ---- 训练健康自检块 ----
        #   · learn_active_epoch: 该轮之前策略仍是随机初始化 ⇒ 那些评估点的 KPI
        #     不能当"模型能力"来读（v4 的 ep20 就是典型：buffer 还没攒够）。
        #   · replay_buffer_fill_ratio: 200K 的 buffer 在 100 轮 local 下只填到
        #     约 0.36 ⇒ **buffer 容量根本不是瓶颈**，把它当调参旋钮是无效投入。
        #   · nan_kpi_epochs: 主指标出现 NaN 的评估点（会被 acceptance 静默跳过）。
        summary['train_health'] = {
            'learn_active_epoch': _learn_active_epoch,
            'grad_updates_total': _grad_updates_total,
            'env_steps_sampled_total': _env_steps_total,
            'replay_buffer_cap': _buffer_cap,
            'replay_buffer_fill_ratio': (
                round(float(_env_steps_total) / float(_buffer_cap), 4)
                if (_env_steps_total and _buffer_cap) else None),
            'nan_kpi_epochs': sorted(set(_nan_kpi_epochs)),
            'eval_deterministic': True,
        }
        # ---- 耗时分解总账 ----
        summary['perf'] = {
            'per_epoch_csv': str(_perf_csv),
            'totals': {k: round(v, 1) for k, v in _perf_tot.items()},
            'final_eval_s': round(_final_eval_s, 1),
            'final_save_s': round(_final_save_s, 1),
            'wall_s': float(_wall_s),
            'counted_s': round(sum(_perf_tot.values())
                               + _final_eval_s + _final_save_s, 1),
        }
    (output_dir / 'district_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    log_console('=' * 72)
    log_console(f'[district-marl] 训练结束：{summary["elapsed_s"]}s，'
                f'best 轮={best_epoch}，best 分数={best_score}')
    _acc_v = acceptance.get('value')
    _acc_n = int(acceptance.get('n_used') or 0)
    log_console(f'  验收（主口径）: {acceptance.get("stat")}'
                f'（{acceptance.get("metric")}，用 {_acc_n} 个评估点'
                f'{acceptance.get("epochs")}）= '
                f'{("nan" if _acc_v is None else format(_acc_v, ".6f"))}') 
    log_console(f'  参考          : best={acceptance.get("best")}'
                f'@{acceptance.get("best_epoch")} / '
                f'final={acceptance.get("final")}@{acceptance.get("final_epoch")} / '
                f'mean_all={acceptance.get("mean_all")}')
    log_console(f'  区域曲线 : {output_dir / "district_metrics.csv"}')
    log_console(f'  汇总     : {output_dir / "district_summary.json"}')
    if kpi_path:
        log_console(f'  官方 KPI : {kpi_path}')
    log_console(f'  最终区域 KPI: all_time_peak={final.get("all_time_peak_average")} '
                f'daily_peak={final.get("daily_peak_average")} '
                f'cost={final.get("cost_total")}')
    # ---- 诊断产物汇总（--no-diag 时一行都不打印 ⇒ 旧输出逐字节一致）----
    if _stopped_reason:
        log_console(f'  早停原因 : {_stopped_reason}')
    if diag_on:
        log_console(f'  RL 内部指标 : {_rl_csv}（{_n_rl_rows} 行，逐轮）')
        log_console(f'  奖励分解    : {_reward_csv}（{_n_reward_rows} 行）')
        log_console(f'  不适曲线    : {_curve_csv.name} / {_curve_paths[0].name}'
                    f'（{len(_curve)} 个评估点）')
        if _n_trace_files:
            log_console(f'  逐时步轨迹  : district_trace_*.npz（{_n_trace_files} 份）')
        if _n_perf_rows:
            log_console(f'  耗时分解    : {_perf_csv.name}（{_n_perf_rows} 行）'
                        f'  训练={_perf_tot["train_s"]:.0f}s '
                        f'评估={_perf_tot["eval_s"]:.0f}s '
                        f'存盘={_perf_tot["save_s"]:.0f}s '
                        f'其它={_perf_tot["other_s"]:.0f}s')
        if _finger:
            log_console(_fp.fingerprint_line(_finger))
        if _learn_active_epoch is not None:
            log_console(f'  学习启动轮  : 第 {_learn_active_epoch} 轮'
                        f'（此前的评估点仍是随机初始化策略）')
        if _buffer_cap and _env_steps_total:
            log_console(f'  回放池占用  : {_env_steps_total:.0f}/{_buffer_cap}'
                        f'（{_env_steps_total / _buffer_cap:.1%}）')
        for _ln in format_curve_overview(_curve):
            log_console(_ln)
    log_console('=' * 72)

    try:
        algo.stop()
    except Exception:
        pass
    try:
        import ray
        ray.shutdown()
    except Exception:
        pass
    return 0


def _district_feature_names() -> List[str]:
    from district_marl.district_features import FEATURE_NAMES
    return list(FEATURE_NAMES)


if __name__ == '__main__':
    sys.exit(main())
