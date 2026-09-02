"""
将已有 decision_trace.json 瘦身为 v2 格式（去掉每步嵌入的 code_snippet / narrative_entries）。

用法：
  cd citylearnpy
  python slim_decision_trace.py
  python slim_decision_trace.py D:\\citylearn-demo\\output\\outkpis\\<taskId>
  python slim_decision_trace.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def slim_payload(data: dict) -> dict:
    steps = data.get('steps') or []
    slim_steps = []
    for step in steps:
        buildings = []
        for b in step.get('buildings') or []:
            nb = {k: v for k, v in b.items() if k != 'narrative_entries'}
            # 若只有 entries 没有 lines，从 entries 抽 text
            if not nb.get('narrative_lines') and b.get('narrative_entries'):
                nb['narrative_lines'] = [
                    e.get('text', '') for e in b['narrative_entries'] if isinstance(e, dict) and e.get('text')
                ]
            buildings.append(nb)
        ns = dict(step)
        ns['buildings'] = buildings
        slim_steps.append(ns)
    return {
        'version': 2,
        'n_buildings': data.get('n_buildings'),
        'slim': True,
        'steps': slim_steps,
    }


def slim_file(path: Path, dry_run: bool = False) -> tuple[int, int, int]:
    raw = path.read_bytes()
    before = len(raw)
    data = json.loads(raw.decode('utf-8'))
    if data.get('slim') and int(data.get('version') or 0) >= 2:
        return before, before, len(data.get('steps') or [])
    slim = slim_payload(data)
    out = json.dumps(slim, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    after = len(out)
    if not dry_run:
        bak = path.with_suffix('.json.bak')
        if not bak.exists():
            bak.write_bytes(raw)
        path.write_bytes(out)
    return before, after, len(slim.get('steps') or [])


def main():
    parser = argparse.ArgumentParser(description='瘦身 decision_trace.json')
    parser.add_argument('path', nargs='?', default=None, help='任务目录或 decision_trace.json 路径')
    parser.add_argument('--all', action='store_true', help='处理 output/outkpis 下全部 decision_trace.json')
    parser.add_argument('--dry-run', action='store_true', help='只统计不写回')
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    targets: list[Path] = []
    if args.all:
        targets = sorted((root / 'output' / 'outkpis').glob('*/decision_trace.json'))
    elif args.path:
        p = Path(args.path)
        if p.is_dir():
            targets = [p / 'decision_trace.json']
        else:
            targets = [p]
    else:
        # 默认：最新任务
        out = root / 'output' / 'outkpis'
        cands = sorted(out.glob('*/decision_trace.json'), key=lambda x: x.stat().st_mtime, reverse=True)
        targets = cands[:1] if cands else []

    if not targets:
        print('未找到 decision_trace.json', flush=True)
        sys.exit(1)

    for path in targets:
        if not path.is_file():
            print(f'跳过（不存在）: {path}', flush=True)
            continue
        before, after, n = slim_file(path, dry_run=args.dry_run)
        ratio = (100.0 * after / before) if before else 0
        print(
            f'{path.parent.name}: steps={n}  '
            f'{before / 1e6:.1f}MB → {after / 1e6:.1f}MB ({ratio:.1f}%)'
            f'{" [dry-run]" if args.dry_run else ""}',
            flush=True,
        )


if __name__ == '__main__':
    main()
