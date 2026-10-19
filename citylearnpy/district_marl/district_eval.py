# -*- coding: utf-8 -*-
"""区域级 MARL 评估入口 —— 加载 checkpoint、跑整段、导出并对比区域 KPI。

职责
----
  1) 用**与训练同一套**区域环境/奖励配置加载 checkpoint（口径必须一致，
     否则观测维度或奖励语义对不上）；
  2) 贪心跑整段，导出 exported_kpis.csv（口径与原流水线逐位一致）；
  3) 打印区域级 KPI 摘要，并可选与若干历史 run 的 outkpis 目录做对比表
     （用来回答"区域级 MARL 相比 CHESCA/原 MARL 在削峰上到底有没有赢"）。

与"零改动"的关系
----------------
  只读原模块（utils.train / utils.env / utils.config），不修改任何原文件。

用法
----
  python district_marl/district_eval.py --train-task-id <训练任务id> --output-dir <dir>
  python district_marl/district_eval.py --checkpoint <ckpt_dir> --output-dir <dir>
  python district_marl/district_eval.py --checkpoint <ckpt_dir> --compare <run1> <run2> ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# ---- 路径引导：本脚本位于 district_marl/ 子目录，需先让 citylearnpy 根目录可见 ----
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---- 确定性引导：必须写在任何重依赖 import 之前 ------------------------------
#   评估虽不学习，但同一 checkpoint 的复评也要求逐位可比（RAM/缓冲区的哈希序同样影响
#   文本键 dict 的遍历次序）⇒ 与训练入口用同一套协议。
#   仅当以脚本方式运行（__main__）时触发；作为库被 import 时是 no-op。
if __name__ == '__main__':
    from district_marl._hashseed import ensure_hashseed
    ensure_hashseed()

from utils.base import log_console, prepare_ray_env

prepare_ray_env()

from district_marl import district_config as dc
from district_marl import _fingerprint as _fp
from district_marl.district_env import DistrictContextRLlibEnv
from district_marl.district_train import (
    build_district_env_config,
    rollout_district,
    trace_steps,
)

# 区域级对比表的默认 KPI 列（区域削峰/整形关注面）
DEFAULT_COMPARE_KEYS: Sequence[str] = (
    'all_time_peak_average',
    'daily_peak_average',
    'monthly_one_minus_load_factor_average',
    'daily_one_minus_load_factor_average',
    'ramping_average',
    'cost_total',
    'carbon_emissions_total',
    'zero_net_energy',
    'discomfort_proportion',
    'power_outage_normalized_unserved_energy_total',
    'one_minus_thermal_resilience_proportion',
)


def _policy_ids(algo) -> List[str]:
    """取当前算法里可用的 policy id 列表（兼容不同 RLlib 版本）。"""
    try:
        ids = list(algo.get_policy_ids())
        if ids:
            return ids
    except Exception:
        pass
    try:
        return list(algo.workers.local_worker().policy_map.keys())
    except Exception:
        pass
    return []


def build_policy_id_fn(algo, agent_ids: Sequence[str]):
    """按 checkpoint 里实际存在的 policy id 决定"agent → policy"映射。

    优先"每 agent 一个独立策略"，其次"共用一个 shared 策略"，
    最后退回第一个 policy（保证不会因为名字对不上而静默用错策略）。
    """
    ids = _policy_ids(algo)
    if all(a in ids for a in agent_ids):
        return (lambda aid: aid), ids
    if 'shared' in ids:
        return (lambda _aid: 'shared'), ids
    if ids:
        only = ids[0]
        return (lambda _aid: only), ids
    # 兜底：policy id 与 agent id 同名
    return (lambda aid: aid), ids


def compare_with_runs(run_dirs: Sequence[str], keys: Sequence[str] = DEFAULT_COMPARE_KEYS,
                      outkpis_root: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    """读取若干 outkpis/<run>/exported_kpis.csv 的 District 列，做对齐对比。"""
    table: Dict[str, Dict[str, float]] = {}
    for run in run_dirs:
        path = Path(run)
        if path.is_dir():
            path = path / 'exported_kpis.csv'
        elif outkpis_root is not None:
            path = Path(outkpis_root) / str(run) / 'exported_kpis.csv'
        if not path.is_file():
            log_console(f'[district-marl] 跳过（找不到 KPI 文件）: {path}')
            continue
        row: Dict[str, float] = {}
        try:
            with path.open(encoding='utf-8') as fh:
                header = fh.readline().strip().split(',')
                if 'District' not in header:
                    continue
                di = header.index('District')
                for line in fh:
                    parts = line.rstrip('\n').rstrip('\r').split(',')
                    if len(parts) <= di:
                        continue
                    val = parts[di].strip()
                    if not val:
                        continue
                    try:
                        row[parts[0].strip()] = float(val)
                    except ValueError:
                        continue
        except Exception as exc:
            log_console(f'[district-marl] 读取失败（跳过）{path}: {exc}')
            continue
        table[str(run)] = row
    return table


def print_compare_table(table: Dict[str, Dict[str, float]],
                        keys: Sequence[str] = DEFAULT_COMPARE_KEYS) -> None:
    """把对比表打成对齐的文本（区域 KPI 越小越好）。"""
    if not table:
        return
    present = [k for k in keys if any(k in row for row in table.values())]
    width = max(28, max((len(r) for r in table), default=10) + 2)
    log_console('')
    log_console('[district-marl] 区域 KPI 对比（District 列，越小越好）')
    log_console('  ' + 'run'.ljust(width) + '  '.join(p[:16].rjust(16) for p in present))
    for run, row in table.items():
        cells = []
        for k in present:
            v = row.get(k)
            cells.append(('-' if v is None else f'{v:.4f}').rjust(16))
        log_console('  ' + run[:width - 1].ljust(width) + '  '.join(cells))


def _is_checkpoint_dir(path) -> bool:
    """目录本身是 RLlib checkpoint（含 rllib_checkpoint.json），或含这样的子目录。

    判据与 utils/ches_residual.py 的 is_checkpoint_dir 同款；这里内联一份，
    避免为一次目录判定把 CHESCA 配置层拉进 import 链。
    """
    p = Path(path)
    if not p.is_dir():
        return False
    if (p / 'rllib_checkpoint.json').is_file():
        return True
    try:
        return any(sub.is_dir() and (sub / 'rllib_checkpoint.json').is_file()
                   for sub in p.iterdir())
    except OSError:
        return False


def _task_id_candidates(task_id: str, output_dir: Path) -> List[Path]:
    """由「训练任务 id」推出的候选模型目录（按优先级），供定位与报错时列出。

    与 CHESCA_ResMARL.py 的 resolve_checkpoint 同一套约定：
      · <输出根>/<id>-train/<DISTRICT_CKPT_REL_DIR>（本任务先训练后评估）
      · <输出根>/<id>/<DISTRICT_CKPT_REL_DIR>（复用历史训练任务；id 可能已带 -train 后缀）
      · 同名 best 快照目录，以及任务目录本身（平台也可能直接给目录）
    """
    task = str(task_id or '').strip().strip('/\\')
    if not task:
        return []
    out_root = Path(output_dir).resolve().parent
    names = [task] if task.endswith('-train') else [task + '-train', task]
    cands: List[Path] = [Path(task)]
    for name in names:
        for rel in (dc.DISTRICT_CKPT_REL_DIR, dc.DISTRICT_CKPT_BEST_REL_DIR):
            cands.append(out_root / name / rel)
        cands.append(out_root / name)
    return cands


def _resolve_from_task_id(task_id: str, output_dir: Path) -> Optional[str]:
    """按任务 id 到各候选目录里找模型；命中返回目录，找不到返回 None。"""
    for cand in _task_id_candidates(task_id, output_dir):
        if _is_checkpoint_dir(cand):
            return str(cand)
    return None


def resolve_checkpoint(cli_checkpoint, train_task_id, output_dir) -> "tuple[Optional[str], Optional[str], str]":
    """决定加载哪个模型目录，返回 (目录, 训练任务id, 来源说明)。

    优先级（与平台任务编排对齐）：
      1) `--train-task-id`：编排任务固定注入 ⇒ 按任务 id 定位训练子任务落盘的模型
         （这就是"按理讲 traintaskid 就能找到 checkpoint"的正解）。
         任务目录里找不到时，再按**旧版全局兜底目录**取一次（策略与 Java 侧
         BaseDataService#resolveSubTaskEvalCheckpoint 的"全局兜底目录"一致）——
         2026-10-10 之前的脚本把模型写在 district_config.DISTRICT_CHECKPOINT_DIR，
         不兜底的话那些历史训练任务一律无法复用。仍找不到才算失败。
      2) `--checkpoint`：显式指定目录（独立运行 / 手动覆盖）。
      3) 旧版全局兜底目录 district_config.DISTRICT_CHECKPOINT_DIR。
    """
    task = str(train_task_id or '').strip()
    if task:
        found = _resolve_from_task_id(task, output_dir)
        if found:
            return found, task, f'--train-task-id={task}'
        # 任务目录无断点：多为「改之前」的训练任务（模型写进了全局目录）⇒ 兜底取它
        legacy = Path(dc.DISTRICT_CHECKPOINT_DIR)
        if _is_checkpoint_dir(legacy):
            log_console(f'[district-marl] 任务 {task} 目录下没有断点'
                        f'（该任务可能由旧版脚本训练，模型写在全局目录）；'
                        f'回退到 {legacy}')
            return str(legacy), task, f'--train-task-id={task}（任务目录无断点，回退全局兜底目录）'
        return None, task, f'--train-task-id={task}（未找到模型目录）'

    given = str(cli_checkpoint or '').strip()
    if given:
        return given, None, '--checkpoint'

    return str(dc.DISTRICT_CHECKPOINT_DIR), None, 'district_config.DISTRICT_CHECKPOINT_DIR（全局兜底）'


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description='区域级 MARL 评估（District-aware MARL eval）')
    p.add_argument('--checkpoint', type=str, default=None,
                   help='RLlib checkpoint 目录；与 --train-task-id 同时给出时后者优先')
    # 平台任务编排给评估子任务固定注入的「训练模型」参数（下划线/中划线两种写法都认）
    p.add_argument('--train-task-id', '--train_task_id', dest='train_task_id', type=str,
                   default=None,
                   help='前置训练任务 id：到 <输出根>/<id>[-train]/checkpoints/ 下找模型'
                        '（或平台任务编排固定注入；优先于 --checkpoint）')
    p.add_argument('--output-dir', type=str, default=None)
    # --eval-schema / --eval-steps：平台「配置」弹窗里这两个参数的 param_name，
    # 作为别名接收 ⇒ 界面配完能直接传进本脚本，不必另起一套命名。
    p.add_argument('--schema', '--eval-schema', dest='schema', type=str,
                   default=dc.DISTRICT_EVAL_SCHEMA)
    p.add_argument('--steps', '--eval-steps', dest='steps', type=int, default=0,
                   help='评估段长；0/不填 = 用数据集自带长度（整段），填值 = 只跑这么多步')
    p.add_argument('--seed', type=int, default=dc.DISTRICT_SEED)
    # 确定性协议：值取 random/none/off 表示不干预；在解释器重启时生效（预扫描 argv）
    p.add_argument('--hashseed', type=str,
                   default=os.environ.get('DISTRICT_HASHSEED', '0'),
                   help='固定 PYTHONHASHSEED 以保证复评逐位可比（默认 0；random = 不干预）。')
    p.add_argument('--no-district-obs', action='store_true',
                   help='若 checkpoint 是"无区域观测"训练出来的，评估也要关掉')
    p.add_argument('--peak-weight', type=float, default=dc.DISTRICT_PEAK_WEIGHT)
    p.add_argument('--team-share', type=float, default=dc.DISTRICT_TEAM_SHARE)
    p.add_argument('--stagger-weight', type=float, default=dc.DISTRICT_STAGGER_WEIGHT)
    p.add_argument('--attribution', type=float, default=dc.DISTRICT_ATTRIBUTION,
                   help='【方案 1】按贡献分摊区域惩罚的强度（0=均摊, 1=严格按份额）')
    p.add_argument('--peak-anchored', type=float, default=dc.DISTRICT_PEAK_ANCHORED,
                   help='【方案 2】峰值-锚定：接近/超过本局峰值的步放大惩罚（0=关, 1=开）')
    # 【方案 3】结构化动作空间（评估须与训练一致）
    p.add_argument('--peak-action-dim', type=int, default=dc.DISTRICT_PEAK_ACTION_DIM,
                   help='【方案 3】结构化削峰动作维数（0=关，动作 3 维；1=动作 4 维）')
    p.add_argument('--peak-resp-cool-frac', type=float,
                   default=dc.DISTRICT_PEAK_RESP_COOL_FRAC,
                   help='【方案 3】a_peak_resp=1 时的制冷开度倍率')
    p.add_argument('--peak-resp-batt-discharge', type=float,
                   default=dc.DISTRICT_PEAK_RESP_BATT_DISCHARGE,
                   help='【方案 3】a_peak_resp=1 时电池维目标值')
    p.add_argument('--peak-action-gated', type=int,
                   default=dc.DISTRICT_PEAK_ACTION_GATED,
                   help='【方案 3】是否只在峰值步允许削峰动作（0=纯学习 3a；1=门控 3b）')
    p.add_argument('--compare', nargs='*', default=[],
                   help='要对比的历史 run 目录（含 exported_kpis.csv）')
    p.add_argument('--outkpis-root', type=str,
                   default=r'D:/citylearn-demo/output/outkpis',
                   help='对比表的根目录（--compare 给的是 run 名时的查找位置）')
    # ---- 诊断埋点（2026-10-17；与 district_train.py 的「四·五」节同源）----
    p.add_argument('--no-diag', action='store_true',
                   help='关闭诊断埋点（奖励分解 / 逐栋不适比例 / 逐时步轨迹）⇒ '
                        '只写 district_eval_metrics.json + exported_kpis.csv 的旧行为')
    p.add_argument('--trace-label', type=str, default='eval',
                   help='轨迹文件名标签：district_trace_<标签>.npz（默认 eval）')
    # ---- 决策推演日志（模型优选界面展示用；2026-10-19）----
    #   与 --no-diag 相互独立：diag 是给脚本分析用的矩阵/奖励分解，
    #   decision_trace.json 是给界面逐步回放用的剧本，关一个不影响另一个。
    p.add_argument('--no-decision-log', action='store_true',
                   help='关闭决策推演日志（decision_trace.json）⇒ 模型优选界面看不到逐步推演。'
                        '默认**开启且全量记录**（每步一条、动作记全 DHW/电池/冷却三维），'
                        '只有显式传本参数才不记录')
    p.add_argument('--decision-log-stride', type=int, default=1,
                   help='决策推演每 N 步记一条（默认 1 = 逐步全记）；'
                        '传 0 = 按条数上限自动抽稀覆盖整段')
    p.add_argument('--decision-log-max-steps', type=int, default=0,
                   help='决策推演条数上限（默认 0 = 不限制，整段全记）')
    # parse_known_args：白名单取消后，界面配置里可能有本脚本不认的参数（例如给训练脚本
    # 配的 peak-weight 抄到了评估脚本上）⇒ 忽略并提示，不用 exit 2 打断整个任务。
    args, unknown = p.parse_known_args(argv)
    if unknown:
        log_console(f'[district-marl] 忽略未识别的命令行参数: {unknown}')
    args.unknown_args = list(unknown)
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    from utils.train import (
        ensure_ray_initialized,
        install_action_hook,
        load_multi_agent_checkpoint,
    )

    # 导出目录先算出来：--train-task-id 要靠它推「输出根目录」（= 任务目录的上一级）
    output_dir = Path(args.output_dir) if args.output_dir else (
        Path(__file__).resolve().parent / 'runs'
        / f'eval_{time.strftime("%Y%m%d_%H%M%S")}')
    output_dir.mkdir(parents=True, exist_ok=True)

    # 断点定位：--train-task-id（平台注入）→ --checkpoint → 全局兜底目录
    ckpt_dir, train_task, ckpt_source = resolve_checkpoint(
        args.checkpoint, args.train_task_id, output_dir)
    if ckpt_dir is None:
        log_console(f'[district-marl] 找不到 checkpoint：{ckpt_source}')
        log_console(f'  训练任务的模型在 <输出根>/<训练任务id>[-train]/'
                    f'{dc.DISTRICT_CKPT_REL_DIR.as_posix()}；')
        for cand in _task_id_candidates(train_task, output_dir)[:6]:
            log_console(f'    查找过：{cand}')
        log_console('  请确认该训练任务已跑完，或用 --checkpoint 直接指定模型目录。')
        return 2
    checkpoint = Path(ckpt_dir)
    if not checkpoint.exists():
        log_console(f'[district-marl] 找不到 checkpoint: {checkpoint}（来源：{ckpt_source}）')
        log_console('  请先跑一次训练（District_MARL_train.py），或用 --checkpoint 指定目录。')
        return 2

    log_console('=' * 72)
    log_console('[district-marl] 区域级 MARL 评估')
    log_console('=' * 72)
    log_console(f'  checkpoint : {checkpoint}')
    log_console(f'  来源       : {ckpt_source}')
    log_console(f'  schema     : {args.schema}    区域观测: {not args.no_district_obs}')
    try:
        from district_marl import _hashseed as _hs
        log_console(f'  可复现性   : {_hs.describe()}')
    except Exception:
        pass
    if train_task and str(args.checkpoint or '').strip():
        log_console(f'  提示       : 已按 --train-task-id 定位模型，'
                    f'忽略配置的 checkpoint={str(args.checkpoint).strip()}')
    if '回退' in ckpt_source:
        log_console('  警告       : 加载的是**全局兜底目录**里的模型 —— 旧版脚本把所有区域级训练'
                    '都写进同一个目录（后训练会覆盖前一次），因此它未必是任务 '
                    f'{train_task} 当时训练的那一份。要精确复用，请用当前版本重训一次'
                    '（模型会按任务目录落盘）。')

    ensure_ray_initialized(log_console=log_console)
    # 先装动作注入钩子：否则 action_hook_status() 未定义（原名 `_STATUS`），
    # 且奖励的"动作相关项"（制冷电费 / 电池择时）会静默为 0。
    log_console(f'  奖励动作注入 : {install_action_hook()}')
    algo = load_multi_agent_checkpoint(str(checkpoint), log_console=log_console,
                                       eval_mode=True)

    # 回合长度：不填 ⇒ 不传 episode_time_steps ⇒ 用**数据集自带长度**
    #   （与 Multi-agent-eval.py / Multi-agent-train.py 同一约定；原先查硬编码表，
    #    未登记的 schema 会被静默按 720 跑 ⇒ 截断回合）。
    eval_steps = int(args.steps) if args.steps else None

    # 评估阶段也允许 CLI 覆盖奖励参数（与训练时一致；默认等于训练用的）
    dc.DISTRICT_PEAK_WEIGHT = float(args.peak_weight)
    dc.DISTRICT_TEAM_SHARE = float(args.team_share)
    dc.DISTRICT_STAGGER_WEIGHT = float(args.stagger_weight)
    dc.DISTRICT_ATTRIBUTION = float(args.attribution)
    dc.DISTRICT_PEAK_ANCHORED = float(args.peak_anchored)
    # 【方案 3】结构化动作维（评估时必须与训练时一致，否则动作空间不匹配）
    dc.DISTRICT_PEAK_ACTION_DIM = int(args.peak_action_dim)
    dc.DISTRICT_PEAK_RESP_COOL_FRAC = float(args.peak_resp_cool_frac)
    dc.DISTRICT_PEAK_RESP_BATT_DISCHARGE = float(args.peak_resp_batt_discharge)
    dc.DISTRICT_PEAK_ACTION_GATED = int(args.peak_action_gated)

    env_config = build_district_env_config(
        args.schema, eval_steps, enable_render=False, output_dir=output_dir,
        record_details=True, district_obs=not args.no_district_obs)
    log_console(f'  回合步数   : {"auto(数据集自带)" if eval_steps is None else eval_steps}')

    # 探针只用于拿 agent 列表
    probe = DistrictContextRLlibEnv(env_config)
    agent_ids = list(probe._agent_ids)
    # 顺手读数据集总步数（energy_simulation 是预分配整段 ⇒ len() 可用且安全；
    # 注意不能去读 net_electricity_consumption[-1]，那是未滚动的假 0）。
    # 用途：决策推演日志按「总步数 / 条数上限」自动抽稀，保证整段覆盖。
    _expected_steps = None
    try:
        _cle_probe = getattr(getattr(probe, 'env', None), 'unwrapped', None)
        _b0_probe = list(getattr(_cle_probe, 'buildings', []) or [])[0]
        _expected_steps = int(len(_b0_probe.energy_simulation.hour))
    except Exception:
        _expected_steps = None
    del probe

    # 决策推演日志：拿到 agent 数之后再建（楼栋数决定条目数；读不到就自动跳过）
    _decision_log = None
    if not bool(getattr(args, 'no_decision_log', False)):
        try:
            from district_marl.district_decision_log import build_decision_log

            _max_rec = int(getattr(args, 'decision_log_max_steps', 0) or 0)
            if _max_rec <= 0:
                _max_rec = 10 ** 9   # 0 = 不限制（截断标记自然恒为 False）
            # 默认 stride=1 全量记录；只有显式传 0 才按条数上限自动抽稀。
            # 想看整季又不想要几十 MB，就 --decision-log-stride 12 / --decision-log-max-steps 720。
            _stride_cli = int(getattr(args, 'decision_log_stride', 1))
            if _stride_cli < 0:
                _stride_cli = 0
            _eff_steps = int(eval_steps) if eval_steps else int(_expected_steps or 0)
            if _stride_cli > 0:
                _stride = _stride_cli
            elif _eff_steps > 0 and _max_rec < 10 ** 8:
                _stride = max(1, -(-_eff_steps // _max_rec))   # ceil 除法
            else:
                _stride = 1
            _decision_log = build_decision_log(
                True, len(agent_ids),
                reward_label='DistrictPeakReward',
                stride=_stride,
                max_records=_max_rec,
                log_console=log_console,
            )
            if _eff_steps > 0:
                _n_expect = min(_max_rec, -(-_eff_steps // max(1, _stride)))
                log_console(f'  覆盖范围   : 全段约 {_eff_steps} 步，计划记 {_n_expect} 条'
                            f'（stride={_stride}）')
        except Exception as exc:
            log_console(f'[district-marl] 决策推演日志初始化失败（跳过）: {exc}')

    policy_id_fn, ids = build_policy_id_fn(algo, agent_ids)
    log_console(f'  agent: {", ".join(agent_ids)}  |  checkpoint policies: {ids}')

    # max_steps=0 ⇒ 不设上限，跑到环境自己结束（= 数据集自带长度）
    #   [埋点] 评估是一次性 rollout，轨迹/奖励分解的采集成本可忽略 ⇒ 默认全开；
    #   --no-diag 可退回只写 metrics + KPI 的旧行为。
    _no_diag = bool(getattr(args, 'no_diag', False))
    _diag_out: Dict[str, object] = {}
    _trace_out: Dict[str, object] = {}
    _t_eval = time.perf_counter()
    metrics = rollout_district(algo, DistrictContextRLlibEnv, env_config,
                               policy_id_fn, deterministic=True,
                               max_steps=int(args.steps or 0), export_dir=output_dir,
                               trace_out=(None if _no_diag else _trace_out),
                               diag_out=(None if _no_diag else _diag_out),
                               decision_log=_decision_log)
    _eval_s = round(time.perf_counter() - _t_eval, 1)

    (output_dir / 'district_eval_metrics.json').write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True),
        encoding='utf-8')

    # ---- 决策推演日志（模型优选界面读的就是这个文件名）----
    #   必须整段跑完再标记峰步：跑到第 10 步时还不知道全段峰值，
    #   逐步判断会把前期局部高点误标成峰步。
    if _decision_log is not None:
        try:
            _decision_log.mark_peak_steps(float(metrics.get('district_peak_raw') or 0.0))
            _dp = output_dir / 'decision_trace.json'
            _decision_log.save(_dp, extra_meta={
                'checkpoint': str(checkpoint),
                'schema': str(args.schema),
                'deterministic': True,
                'eval_steps_actual': int(metrics.get('eval_steps') or 0),
            })
            _mb = _dp.stat().st_size / 1048576 if _dp.is_file() else 0.0
            _trunc = _decision_log.truncated
            log_console(
                f'  决策推演 : {_dp}'
                f'（{_decision_log.recorded_steps} 条 / 走过 {_decision_log.seen_steps} 步，'
                f'{_mb:.1f} MB，动作维 dhw/ele/tmp'
                f'{("，已截断（--decision-log-max-steps 可调）" if _trunc else "")}）')
            if _decision_log.failures:
                log_console(f'    ⚠ 采集异常 {_decision_log.failures} 次'
                            f'（最后一条：{_decision_log._last_error}）')
            if _decision_log.recorded_steps == 0:
                log_console('    ⚠ 一条都没记下：多半是读不到 CityLearnEnv 或楼栋数'
                            '（见 --no-district-obs / checkpoint 是否匹配）')
        except Exception as exc:
            log_console(f'[district-marl] 决策推演落盘失败（忽略）: {exc}')

    if not _no_diag:
        # ---- 逐时步轨迹（原先 `_info` 被丢弃、`record_details=True` 形同虚设）----
        if _trace_out:
            try:
                import numpy as np
                _tp = output_dir / f'district_trace_{args.trace_label}.npz'
                np.savez_compressed(_tp, **_trace_out)
                log_console(f'  逐时步轨迹 : {_tp}'
                            f'（{trace_steps(_trace_out)} 步，'
                            f'键={sorted(k for k in _trace_out)}）')
            except Exception as exc:
                log_console(f'[district-marl] 轨迹落盘失败（忽略）: {exc}')
        # ---- 奖励分解 + 逐栋不适比例 ----
        try:
            _payload = {
                'reward': dict(_diag_out.get('reward') or {}),
                'reward_summary': str(_diag_out.get('reward_summary') or ''),
                'reward_stats': {str(k): float(v) for k, v in
                                 (_diag_out.get('reward_stats') or {}).items()
                                 if isinstance(v, (int, float))},
                'discomfort': dict(_diag_out.get('discomfort') or {}),
            }
            (output_dir / 'district_eval_diagnostics.json').write_text(
                json.dumps(_payload, ensure_ascii=False, indent=2, default=str),
                encoding='utf-8')
            _dis = _payload['discomfort'] or {}
            _hot = [float(v) for v in (_dis.get('hot') or [])]
            _cold = [float(v) for v in (_dis.get('cold') or [])]
            if _hot or _cold:
                _n = max(len(_hot), len(_cold))
                log_console('  ' + '[不适曲线] 高温/低温 '
                            + ' '.join(
                                f'B{i + 1}:'
                                f'{(_hot[i] if i < len(_hot) else float("nan")):5.1%}/'
                                f'{(_cold[i] if i < len(_cold) else float("nan")):5.1%}'
                                for i in range(_n)))
            if _payload['reward_summary']:
                log_console('  ' + _payload['reward_summary'])
        except Exception as exc:
            log_console(f'[district-marl] 评估诊断落盘失败（忽略）: {exc}')

        # ---- 指纹（回答"这次评估和上次跑的是同一套代码/机器吗"）----
        #   与训练侧同一个结构；额外带上本次评估自身的信息（checkpoint / schema /
        #   步数 / 耗时），这样单看一份 json 就能定位「哪个模型在什么环境下评的」。
        try:
            _fpayload = {
                'fingerprint': _fp.fingerprint_block(),
                'eval': {
                    'checkpoint': str(checkpoint),
                    'checkpoint_source': str(ckpt_source),
                    'train_task': train_task,
                    'schema': str(args.schema),
                    'steps': (None if eval_steps is None else int(eval_steps)),
                    'eval_steps_actual': int(metrics.get('eval_steps') or 0),
                    'deterministic': True,
                    'elapsed_s': _eval_s,
                    'pythonhashseed': (os.environ.get('PYTHONHASHSEED') or ''),
                },
            }
            (output_dir / 'district_eval_fingerprint.json').write_text(
                json.dumps(_fpayload, ensure_ascii=False, indent=2),
                encoding='utf-8')
            log_console(_fp.fingerprint_line(_fpayload['fingerprint']))
        except Exception as exc:
            log_console(f'[district-marl] 指纹落盘失败（忽略）: {exc}')

    log_console('')
    log_console('[district-marl] 区域 KPI（District，越小越好）')
    for k in DEFAULT_COMPARE_KEYS:
        if k in metrics:
            log_console(f'  {k:<46} {metrics[k]:.4f}')
    log_console(f'  {"district_peak_raw（原始社区峰值）":<46} '
                f'{metrics.get("district_peak_raw", float("nan")):.4f}')

    if args.compare:
        table = compare_with_runs(args.compare, outkpis_root=Path(args.outkpis_root))
        table[f'[new] {output_dir.name}'] = metrics
        print_compare_table(table)

    log_console('')
    log_console(f'  导出目录 : {output_dir}')
    log_console(f'  官方 KPI : {output_dir / "exported_kpis.csv"}')

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


if __name__ == '__main__':
    sys.exit(main())
