"""
CHESCA-ResMARL 阶段 3/5：消融批量评估 + α 扫描入库。

对比三组（默认）：
  1. chesca_baseline  — 纯 CHESCA（enabled=false）
  2. resmarl_alpha0   — 启用残差层但 α=0（恒等对照）
  3. resmarl_full     — 完整 ResMARL（enabled + α>0 + policy）

α 扫描（阶段 5）：
  python ablation_resmarl.py --alpha-sweep 0,0.05,0.1,0.15,0.2 --policy checkpoints/resmarl_policy.pt
  结果写入 ablation_results/alpha_sweep_<id>/ 并登记到 registry/index.json，供看板曲线读取。

用法：
  cd citylearnpy
  python ablation_resmarl.py --smoke
  python ablation_resmarl.py --policy checkpoints/resmarl_policy.pt --steps 720
  python ablation_resmarl.py --register-existing ablation_results  # 把已有 summary 入库
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
import warnings
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
warnings.filterwarnings('ignore', category=UserWarning, module='gymnasium')

ROOT = Path(__file__).resolve().parent
CHESCA = ROOT / 'CHESCA-copy'
sys.path.insert(0, str(CHESCA))
sys.path.insert(0, str(ROOT))

# 注意：evaluate / load_agent_config 依赖 citylearn，仅在实际跑仿真时惰性导入

BASELINE_PATH = ROOT / 'configs' / 'chesca_baseline_v1.json'
ABLATION_DIR = ROOT / 'configs' / 'ablation'
DEFAULT_OUT = ROOT / 'ablation_results'
REGISTRY_DIR = DEFAULT_OUT / 'registry'
REGISTRY_INDEX = REGISTRY_DIR / 'index.json'

# 看板默认关注的 KPI（可在前端再选）
DEFAULT_CHART_KPIS = [
    'cost_total',
    'ramping_average',
    'electricity_consumption_total',
    'carbon_emissions_total',
    'discomfort_proportion',
    'power_outage_normalized_unserved_energy_total',
]


def _import_eval():
    from local_evaluation_copy import DEFAULT_SCHEMA, evaluate, load_agent_config

    return DEFAULT_SCHEMA, evaluate, load_agent_config


def _load_baseline() -> Dict[str, Any]:
    raw = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
    return raw


def build_variants(policy_path: Optional[str], alpha: float) -> List[Dict[str, Any]]:
    base = _load_baseline()
    policy = str(policy_path).strip() if policy_path else None
    if policy and not Path(policy).is_file():
        print(f'[warn] 策略文件不存在: {policy}，resmarl_full 将退化为 Δa≡0', flush=True)

    variants = [
        {
            'name': 'chesca_baseline',
            'label': '纯 CHESCA',
            'config': {
                **base,
                'resmarl_enabled': False,
                'residual_alpha': 0.0,
                'resmarl_policy_path': None,
            },
        },
        {
            'name': 'resmarl_alpha0',
            'label': 'ResMARL α=0',
            'config': {
                **base,
                'resmarl_enabled': True,
                'residual_alpha': 0.0,
                'resmarl_policy_path': policy,
            },
        },
        {
            'name': 'resmarl_full',
            'label': f'ResMARL α={alpha}',
            'config': {
                **base,
                'resmarl_enabled': True,
                'residual_alpha': float(alpha),
                'resmarl_policy_path': policy,
            },
        },
    ]
    return variants


def write_ablation_configs(variants: List[Dict[str, Any]]) -> None:
    ABLATION_DIR.mkdir(parents=True, exist_ok=True)
    for v in variants:
        path = ABLATION_DIR / f"{v['name']}.json"
        payload = deepcopy(v['config'])
        payload['_ablation_name'] = v['name']
        payload['_ablation_label'] = v['label']
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[config] {path}', flush=True)


def _alpha_slug(alpha: float) -> str:
    s = f'{alpha:g}'.replace('.', 'p').replace('-', 'm')
    return s


def build_alpha_sweep_variants(
    policy_path: Optional[str],
    alphas: List[float],
) -> List[Dict[str, Any]]:
    """基线 + 每个 α 一组 ResMARL（enabled=True）。"""
    base = _load_baseline()
    policy = str(policy_path).strip() if policy_path else None
    if policy and not Path(policy).is_file():
        print(f'[warn] 策略文件不存在: {policy}，残差将退化为 Δa≡0', flush=True)

    variants: List[Dict[str, Any]] = [
        {
            'name': 'chesca_baseline',
            'label': '纯 CHESCA',
            'kind': 'baseline',
            'config': {
                **base,
                'resmarl_enabled': False,
                'residual_alpha': 0.0,
                'resmarl_policy_path': None,
            },
        }
    ]
    seen = set()
    for a in alphas:
        a = float(a)
        if a in seen:
            continue
        seen.add(a)
        slug = _alpha_slug(a)
        variants.append(
            {
                'name': f'resmarl_a{slug}',
                'label': f'ResMARL α={a:g}',
                'kind': 'resmarl',
                'config': {
                    **base,
                    'resmarl_enabled': True,
                    'residual_alpha': a,
                    'resmarl_policy_path': policy,
                },
            }
        )
    return variants


def parse_alpha_list(text: str) -> List[float]:
    parts = [p.strip() for p in str(text).replace(';', ',').split(',') if p.strip()]
    if not parts:
        raise ValueError('α 列表为空')
    return [float(p) for p in parts]


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _run_id() -> str:
    from datetime import datetime

    return datetime.now().strftime('%Y%m%d_%H%M%S')


def build_alpha_sweep_payload(
    summaries: List[Dict[str, Any]],
    *,
    run_id: str,
    policy_path: Optional[str],
    steps: int,
    alphas: List[float],
    output_dir: str,
) -> Dict[str, Any]:
    baseline = next((s for s in summaries if s.get('name') == 'chesca_baseline'), None)
    points = []
    for s in summaries:
        points.append(
            {
                'name': s['name'],
                'label': s['label'],
                'kind': 'baseline' if s.get('name') == 'chesca_baseline' else 'resmarl',
                'resmarl_enabled': bool(s.get('resmarl_enabled')),
                'residual_alpha': float(s.get('residual_alpha', 0.0)),
                'district_kpis': s.get('district_kpis') or {},
                'elapsed_sec': s.get('elapsed_sec'),
                'output_dir': s.get('output_dir'),
            }
        )

    kpi_names: List[str] = []
    seen = set()
    for s in summaries:
        for k in s.get('district_kpis', {}):
            if k not in seen:
                seen.add(k)
                kpi_names.append(k)

    chart_kpis = [k for k in DEFAULT_CHART_KPIS if k in seen] or kpi_names[:6]

    return {
        'version': 1,
        'run_id': run_id,
        'created_at': _utc_now_iso(),
        'policy_path': policy_path,
        'episode_time_steps': steps,
        'alphas': [float(a) for a in alphas],
        'kpi_names': kpi_names,
        'default_chart_kpis': chart_kpis,
        'baseline': baseline,
        'points': points,
        'output_dir': output_dir,
    }


def _load_registry_index() -> List[Dict[str, Any]]:
    if not REGISTRY_INDEX.is_file():
        return []
    try:
        data = json.loads(REGISTRY_INDEX.read_text(encoding='utf-8'))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get('runs'), list):
            return data['runs']
    except Exception as exc:
        print(f'[warn] 读取 registry 失败: {exc}', flush=True)
    return []


def register_alpha_sweep(
    payload: Dict[str, Any],
    run_dir: Path,
    *,
    update_index: bool = True,
    index_path: Optional[Path] = None,
) -> Path:
    """将 α 扫描结果写入 run 目录并登记到 registry/index.json（看板入库）。"""
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / 'alpha_sweep_summary.json'
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[registry] {summary_path.resolve()}', flush=True)

    if not update_index:
        return summary_path

    idx_path = Path(index_path) if index_path else REGISTRY_INDEX
    idx_path.parent.mkdir(parents=True, exist_ok=True)

    # 相对 citylearnpy 根的路径，便于跨机器只改根目录
    try:
        rel = str(run_dir.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        rel = str(run_dir.resolve())

    entry = {
        'run_id': payload['run_id'],
        'created_at': payload.get('created_at'),
        'label': f"α-scan [{', '.join(f'{a:g}' for a in payload.get('alphas', []))}] · {payload.get('episode_time_steps')} steps",
        'policy_path': payload.get('policy_path'),
        'episode_time_steps': payload.get('episode_time_steps'),
        'alphas': payload.get('alphas'),
        'n_points': len(payload.get('points') or []),
        'default_chart_kpis': payload.get('default_chart_kpis'),
        'rel_dir': rel.replace('\\', '/'),
        'summary_file': 'alpha_sweep_summary.json',
    }

    index = [e for e in _load_registry_index() if e.get('run_id') != entry['run_id']]
    # 若测试传入临时 index，则只读该文件
    if index_path is not None and idx_path.is_file():
        try:
            data = json.loads(idx_path.read_text(encoding='utf-8'))
            index = data.get('runs', data) if isinstance(data, dict) else data
            index = [e for e in index if e.get('run_id') != entry['run_id']]
        except Exception:
            index = []

    index.insert(0, entry)
    idx_path.write_text(
        json.dumps({'version': 1, 'runs': index}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'[registry] index → {idx_path.resolve()} ({len(index)} runs)', flush=True)
    return summary_path


def register_existing_summary(summary_dir: Path, run_id: Optional[str] = None) -> Path:
    """把已有 ablation_summary.json 转成 α 扫描格式并入库。"""
    summary_dir = Path(summary_dir)
    json_path = summary_dir / 'ablation_summary.json'
    if not json_path.is_file():
        # 也接受已是 alpha_sweep_summary.json 的目录
        sweep_path = summary_dir / 'alpha_sweep_summary.json'
        if sweep_path.is_file():
            payload = json.loads(sweep_path.read_text(encoding='utf-8'))
            if not payload.get('run_id'):
                payload['run_id'] = run_id or _run_id()
            return register_alpha_sweep(payload, summary_dir)
        raise FileNotFoundError(f'未找到 ablation_summary.json: {json_path}')

    summaries = json.loads(json_path.read_text(encoding='utf-8'))
    if not isinstance(summaries, list) or not summaries:
        raise ValueError('ablation_summary.json 为空或格式错误')

    alphas = sorted(
        {
            float(s.get('residual_alpha', 0.0))
            for s in summaries
            if s.get('resmarl_enabled') or s.get('name') != 'chesca_baseline'
        }
    )
    rid = run_id or f"import_{_run_id()}"
    policy = next((s.get('resmarl_policy_path') for s in summaries if s.get('resmarl_policy_path')), None)
    steps = int(summaries[0].get('episode_time_steps') or 720)
    payload = build_alpha_sweep_payload(
        summaries,
        run_id=rid,
        policy_path=policy,
        steps=steps,
        alphas=alphas or [0.0],
        output_dir=str(summary_dir.resolve()),
    )
    return register_alpha_sweep(payload, summary_dir)


def extract_district_kpis(output_dir: Path) -> Dict[str, float]:
    """从 exported_kpis.csv 读 District 列。"""
    candidates = list(Path(output_dir).rglob('exported_kpis.csv'))
    # 优先任务根目录下的文件
    root_csv = Path(output_dir) / 'exported_kpis.csv'
    if root_csv.is_file():
        candidates = [root_csv] + [c for c in candidates if c != root_csv]
    if not candidates:
        return {}
    path = candidates[0]
    rows: Dict[str, float] = {}
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        # 去掉 BOM
        fieldnames = [fn.lstrip('\ufeff') if fn else fn for fn in fieldnames]
        district_keys = [k for k in fieldnames if k and 'district' in k.lower()]
        kpi_key = None
        for cand in ('KPI', 'kpi', 'cost_function'):
            if cand in fieldnames:
                kpi_key = cand
                break
        if kpi_key is None and fieldnames:
            kpi_key = fieldnames[0]

        for raw in reader:
            # 兼容带 BOM 的列名
            row = {(k.lstrip('\ufeff') if k else k): v for k, v in raw.items()}
            kpi_name = row.get(kpi_key, '') if kpi_key else ''
            if not kpi_name:
                continue
            val = None
            for dk in district_keys:
                cell = row.get(dk)
                if cell in (None, '', 'NaN', 'nan'):
                    continue
                try:
                    val = float(cell)
                    break
                except ValueError:
                    continue
            if val is not None:
                rows[str(kpi_name)] = val
    return rows


def run_variant(
    variant: Dict[str, Any],
    out_root: Path,
    steps: int,
    enable_render: bool,
) -> Dict[str, Any]:
    name = variant['name']
    out_dir = out_root / name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg_path = out_dir / 'chesca_agent_config.json'
    cfg_path.write_text(json.dumps(variant['config'], ensure_ascii=False, indent=2), encoding='utf-8')

    DEFAULT_SCHEMA, evaluate, load_agent_config = _import_eval()
    agent_config = load_agent_config(str(cfg_path))
    if int(steps) < 720:
        agent_config = dict(agent_config)
        agent_config['schema_split_enabled'] = False

    class Config:
        SCHEMA = DEFAULT_SCHEMA
        num_episodes = 1
        episode_time_steps = int(steps)
        RENDER_DIR = out_dir
        RENDER_SESSION = '.'
        AGENT_CONFIG = agent_config
        ENABLE_RENDER = bool(enable_render)

    print(f'\n===== [{name}] {variant["label"]} steps={steps} =====', flush=True)
    t0 = time.perf_counter()
    evaluate(Config())
    elapsed = time.perf_counter() - t0

    kpis = extract_district_kpis(out_dir)
    summary = {
        'name': name,
        'label': variant['label'],
        'resmarl_enabled': bool(variant['config'].get('resmarl_enabled')),
        'residual_alpha': float(variant['config'].get('residual_alpha', 0.0)),
        'resmarl_policy_path': variant['config'].get('resmarl_policy_path'),
        'episode_time_steps': steps,
        'elapsed_sec': round(elapsed, 2),
        'output_dir': str(out_dir.resolve()),
        'district_kpis': kpis,
    }
    (out_dir / 'ablation_variant_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f'[{name}] done in {elapsed:.1f}s, KPIs={len(kpis)}', flush=True)
    return summary


def write_summary_table(summaries: List[Dict[str, Any]], out_root: Path) -> Path:
    # 收集所有 KPI 名
    kpi_names: List[str] = []
    seen = set()
    for s in summaries:
        for k in s.get('district_kpis', {}):
            if k not in seen:
                seen.add(k)
                kpi_names.append(k)

    csv_path = out_root / 'ablation_summary.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as f:
        fields = [
            'name', 'label', 'resmarl_enabled', 'residual_alpha',
            'resmarl_policy_path', 'episode_time_steps', 'elapsed_sec',
        ] + kpi_names
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for s in summaries:
            row = {
                'name': s['name'],
                'label': s['label'],
                'resmarl_enabled': s['resmarl_enabled'],
                'residual_alpha': s['residual_alpha'],
                'resmarl_policy_path': s.get('resmarl_policy_path') or '',
                'episode_time_steps': s['episode_time_steps'],
                'elapsed_sec': s['elapsed_sec'],
            }
            for k in kpi_names:
                row[k] = s.get('district_kpis', {}).get(k, '')
            writer.writerow(row)

    json_path = out_root / 'ablation_summary.json'
    json_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n[summary] {csv_path.resolve()}', flush=True)
    print(f'[summary] {json_path.resolve()}', flush=True)
    return csv_path


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description='CHESCA-ResMARL ablation / alpha-sweep runner')
    p.add_argument('--policy', type=str, default=str(ROOT / 'checkpoints' / 'resmarl_policy_smoke.pt'))
    p.add_argument('--alpha', type=float, default=0.15, help='单点 ResMARL α（非扫描模式）')
    p.add_argument(
        '--alpha-sweep',
        type=str,
        default='',
        help='α 扫描列表，如 0,0.05,0.1,0.15,0.2；启用后跑基线+各组并入库',
    )
    p.add_argument('--steps', type=int, default=720)
    p.add_argument('--output', type=str, default=str(DEFAULT_OUT))
    p.add_argument('--render', action='store_true', help='开启 render（更慢，可出时序 CSV）')
    p.add_argument('--smoke', action='store_true', help='冒烟：24 步')
    p.add_argument('--configs-only', action='store_true', help='只写出 configs/ablation/*.json')
    p.add_argument(
        '--register-existing',
        type=str,
        default='',
        help='将已有消融目录（含 ablation_summary.json）登记到看板 registry',
    )
    p.add_argument('--run-id', type=str, default='', help='自定义 run_id（扫描/登记时）')
    p.add_argument('--no-register', action='store_true', help='扫描完成后不写入 registry')
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    if args.register_existing:
        path = register_existing_summary(Path(args.register_existing), run_id=args.run_id or None)
        print(f'[done] registered → {path}', flush=True)
        return

    steps = 24 if args.smoke else int(args.steps)
    out_root = Path(args.output)
    sweep_alphas: Optional[List[float]] = None
    if args.alpha_sweep.strip():
        sweep_alphas = parse_alpha_list(args.alpha_sweep)
        rid = args.run_id.strip() or f'alpha_sweep_{_run_id()}'
        out_root = out_root / rid
    elif args.smoke:
        out_root = out_root / 'smoke'

    if sweep_alphas is not None:
        variants = build_alpha_sweep_variants(args.policy, sweep_alphas)
    else:
        variants = build_variants(args.policy, args.alpha)

    write_ablation_configs(variants)
    if args.configs_only:
        return

    out_root.mkdir(parents=True, exist_ok=True)
    summaries = []
    for v in variants:
        summaries.append(run_variant(v, out_root, steps, enable_render=args.render))
    write_summary_table(summaries, out_root)

    if sweep_alphas is not None and not args.no_register:
        rid = out_root.name
        payload = build_alpha_sweep_payload(
            summaries,
            run_id=rid,
            policy_path=args.policy,
            steps=steps,
            alphas=sweep_alphas,
            output_dir=str(out_root.resolve()),
        )
        register_alpha_sweep(payload, out_root)
    elif not args.no_register and not args.smoke:
        try:
            register_existing_summary(out_root, run_id=args.run_id or f'ablation_{_run_id()}')
        except Exception as exc:
            print(f'[warn] 自动入库跳过: {exc}', flush=True)


if __name__ == '__main__':
    main()
