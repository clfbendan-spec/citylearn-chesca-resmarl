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

与"零改动"的关系
----------------
  本文件**只读**原模块（utils.env / utils.train / utils.config），不修改任何原文件。

用法
----
  python district_marl/district_train.py --train-epochs 320 --output-dir <dir>
  python district_marl/district_train.py --quick            # 冒烟：3 轮 + 每 1 轮评估
  python district_marl/district_train.py --no-shared-policy # 独立策略对照
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
) -> Dict[str, float]:
    """贪心跑一整段评估，返回区域 KPI 字典。

    同时给出：
      · district_peak_raw    —— 本段社区净用电峰值（**原始量**，用于选点与对比）
      · district_peak_norm   —— 除以 net_scale 的归一值（跨数据集可比的粗口径）
      · 官方 District 归一 KPI（all_time_peak_average / daily_peak_average / ...）

    export_dir 非空时，顺手把官方 KPI 表写成 exported_kpis.csv。
    ⚠️ 必须在**本段评估刚跑完、尚未 reset 之前**导出 —— reset 会清空仿真状态，
       之后再 evaluate() 得到的是"无控制基线"（多为 1.0）。所以导出与评估同环境。
    """
    env = env_cls(env_config)
    metrics: Dict[str, float] = {}
    try:
        obs, _info = env.reset()
        keys = list(getattr(env, '_agent_ids', None) or obs.keys())
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
            series.append(district_net_now(env))
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
    finally:
        try:
            env.close()
        except Exception:
            pass
    return metrics


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

    for epoch in range(1, int(args.train_epochs) + 1):
        try:
            algo.train()
        except Exception as exc:
            log_console(f'[district-marl] 第 {epoch} 轮训练异常，提前收工: {exc}')
            break
        epochs_done = epoch

        if epoch % max(1, int(args.eval_every)) != 0 and epoch != int(args.train_epochs):
            continue

        metrics = rollout_district(
            algo, DistrictContextRLlibEnv, eval_env_config, policy_id_fn,
            deterministic=True, max_steps=int(args.eval_steps or 0))
        row: Dict[str, Any] = {'epoch': epoch, 'elapsed_s': round(time.perf_counter() - t0, 1)}
        row.update(metrics)
        rows.append(row)

        # 验收口径（主口径 = 末 K 个评估点均值；best 一并保留作参考）。
        # 只用于"报告/比较"，不影响上面的 best-checkpoint 挑选与落盘。
        accept = dacc.summarize(
            rows, args.best_metric, tail=int(args.accept_tail),
            tiebreak=dc.DISTRICT_BEST_TIEBREAK, stat=str(args.accept_stat))

        score = _score(metrics)
        tag = ''
        if score is not None:
            improved = (best_score is None
                        or score[0] < best_score[0] - float(dc.DISTRICT_BEST_MIN_GAIN)
                        or (abs(score[0] - best_score[0]) <= float(dc.DISTRICT_BEST_MIN_GAIN)
                            and score[1] < best_score[1]))
            if improved:
                saved = save_multi_agent_checkpoint(algo, ckpt_dir, log_console=log_console)
                best_score, best_epoch = score, epoch
                # 每次刷新 best 都同步进度文件 ⇒ 任务管理页随时能看到「模型可用」
                write_train_progress(ckpt_dir, epochs_done, int(args.train_epochs),
                                     score[0], epoch, accept=accept)
                tag = f'  ← best（已存 {Path(saved).name}）'

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
    try:
        save_multi_agent_checkpoint(algo, final_dest, log_console=log_console)
    except Exception as exc:
        log_console(f'[district-marl] 末次权重保存失败（忽略）: {exc}')

    # 最终区域评估 + 官方 KPI 导出（同一次 rollout 内完成，避免 reset 后读数失真）
    final = rollout_district(algo, DistrictContextRLlibEnv, eval_env_config,
                             policy_id_fn, deterministic=True,
                             max_steps=int(args.eval_steps or 0),
                             export_dir=output_dir)
    kpi_path = output_dir / 'exported_kpis.csv'
    if not kpi_path.is_file():
        kpi_path = None

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
        'elapsed_s': round(time.perf_counter() - t0, 1),
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
