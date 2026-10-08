"""
从 citylearn_challenge_2023_phase_2_online_evaluation_1 编纂
citylearn_challenge_2026_jul_sep（2026-07-01 .. 2026-09-30，2208h）。

构造规则：
  · 行序 = 源 July + August + June（June 作为 September 的 30 天代理剖面）
  · month / hour / day_type 按 2026 公历重写（Mon=1 .. Sun=7）
  · 负荷、天气、电价、碳强度等物理序列保持源数据重排后的值
"""
from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SRC = Path(
    r'C:\Users\clfbe\AppData\Local\intelligent-environments-lab\citylearn'
    r'\Cache\v2.5.0\datasets\citylearn_challenge_2023_phase_2_online_evaluation_1'
)
NAME = 'citylearn_challenge_2026_jul_sep'
OUTS = [
    Path(r'D:\citylearn-demo\citylearnpy\datasets') / NAME,
    Path(
        r'C:\Users\clfbe\AppData\Local\intelligent-environments-lab\citylearn'
        r'\Cache\v2.5.0\datasets'
    ) / NAME,
    Path(r'D:\citylearn-demo\citylearnpy\CHESCA-copy\data\schemas') / NAME,
]


def build_calendar() -> pd.DataFrame:
    start, end = date(2026, 7, 1), date(2026, 9, 30)
    assert (end - start).days + 1 == 92
    months, hours, day_types = [], [], []
    d = start
    while d <= end:
        for h in range(1, 25):
            months.append(d.month)
            hours.append(h)
            day_types.append(d.weekday() + 1)
        d += timedelta(days=1)
    return pd.DataFrame({'month': months, 'hour': hours, 'day_type': day_types})


def row_order(building1: pd.DataFrame) -> list[int]:
    idx_jul = building1.index[building1['month'] == 7].tolist()
    idx_aug = building1.index[building1['month'] == 8].tolist()
    idx_jun = building1.index[building1['month'] == 6].tolist()
    assert len(idx_jul) == 744 and len(idx_aug) == 744 and len(idx_jun) == 720
    return idx_jul + idx_aug + idx_jun


def write_dataset(out_dir: Path, order: list[int], cal: pd.DataFrame) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    for fname in ('weather.csv', 'pricing.csv', 'carbon_intensity.csv'):
        pd.read_csv(SRC / fname).iloc[order].reset_index(drop=True).to_csv(
            out_dir / fname, index=False
        )

    for fname in ('Building_1.csv', 'Building_2.csv', 'Building_3.csv'):
        df = pd.read_csv(SRC / fname).iloc[order].reset_index(drop=True)
        df['month'] = cal['month'].values
        df['hour'] = cal['hour'].values
        df['day_type'] = cal['day_type'].values
        if 'daylight_savings_status' in df.columns:
            df['daylight_savings_status'] = 0
        df.to_csv(out_dir / fname, index=False)

    # LSTM 室温动力学权重与建筑绑定，日历重标后仍复用源模型
    for fname in ('Building_1.pth', 'Building_2.pth', 'Building_3.pth'):
        shutil.copy2(SRC / fname, out_dir / fname)

    schema = json.loads((SRC / 'schema.json').read_text(encoding='utf-8'))
    schema['random_seed'] = 2026
    schema['root_directory'] = None
    schema['simulation_start_time_step'] = 0
    schema['simulation_end_time_step'] = 2207
    (out_dir / 'schema.json').write_text(json.dumps(schema, indent=2), encoding='utf-8')

    meta = {
        'name': NAME,
        'based_on': 'citylearn_challenge_2023_phase_2_online_evaluation_1',
        'calendar': '2026-07-01 .. 2026-09-30 (92 days, 2208 hours)',
        'construction': {
            'row_order': 'source month7 + month8 + month6',
            'month_mapping': {
                'July 2026 (31d)': 'source July profiles',
                'August 2026 (31d)': 'source August profiles',
                'September 2026 (30d)': 'source June profiles (late-summer proxy)',
            },
            'day_type': 'ISO weekday Mon=1 .. Sun=7 aligned to 2026 calendar',
            'note': 'Physical series adapted from 2023 online_1; not measured 2026 weather.',
        },
    }
    (out_dir / 'DATASET_README.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print('wrote', out_dir)


def register_dataset_name() -> None:
    names_path = Path(
        r'C:\Users\clfbe\AppData\Local\intelligent-environments-lab\citylearn'
        r'\Cache\v2.5.0\dataset_names.json'
    )
    names = json.loads(names_path.read_text(encoding='utf-8')) if names_path.exists() else []
    if NAME not in names:
        names.append(NAME)
        names_path.write_text(json.dumps(sorted(set(names)), indent=2), encoding='utf-8')
        print('registered', NAME, 'in', names_path)


def main() -> None:
    if not SRC.is_dir():
        raise FileNotFoundError(f'source dataset missing: {SRC}')
    cal = build_calendar()
    order = row_order(pd.read_csv(SRC / 'Building_1.csv'))
    for out in OUTS:
        write_dataset(out, order, cal)
    register_dataset_name()
    print('DONE', NAME)


if __name__ == '__main__':
    main()
