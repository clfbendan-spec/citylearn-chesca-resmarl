"""
以 citylearn_challenge_2022_phase_1（公开在线训练集）为基准，
参考 citylearn_challenge_2023_phase_2_online_evaluation_1 补全缺失字段，
模拟生成 2026 全年三栋建筑数据集。

构造要点
--------
1. 特征重构法（整周搬迁）：从 2022 提取连续 Mon..Sun 整周负荷块，硬塞到 2026
   含完整周末的周；CSV 的 Day Type 按 2026 日历重算，并与源周星期一一对应。
2. 年首/年尾非整周用同月同星期单日补齐。
3. 缺失冷/热/热水等按 2023 统计 + HDD 启发式生成；schema 含热泵/电采暖/DHW 等。
"""
from __future__ import annotations

import json
import math
import shutil
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r'D:\citylearn-demo\citylearnpy')
SRC22 = ROOT / 'CHESCA-main' / 'data' / 'schemas' / 'citylearn_challenge_2022_phase_1'
SRC23 = (
    ROOT / 'CHESCA-copy' / 'data' / 'schemas'
    / 'citylearn_challenge_2023_phase_2_online_evaluation_1'
)
NAME = 'citylearn_challenge_2026_from_2022'
BUILDINGS = ('Building_1', 'Building_2', 'Building_3')
OUTS = [
    ROOT / 'datasets' / NAME,
    ROOT / 'CHESCA-copy' / 'data' / 'schemas' / NAME,
    ROOT / 'CHESCA-main' / 'data' / 'schemas' / NAME,
]
def _citylearn_cache_dataset_dirs() -> list:
    """写入本机 CityLearn 实际缓存（2.3.0 → v2.3.0）及兼容的 v2.5.0。"""
    roots = []
    try:
        from citylearn.data import DataSet
        roots.append(Path(DataSet().cache_directory) / 'datasets' / NAME)
    except Exception:
        pass
    legacy = Path(
        r'C:\Users\clfbe\AppData\Local\intelligent-environments-lab\citylearn'
        r'\Cache\v2.5.0\datasets'
    ) / NAME
    if legacy not in roots:
        roots.append(legacy)
    return roots


CACHE_DIRS = _citylearn_cache_dataset_dirs()
CACHE = CACHE_DIRS[0] if CACHE_DIRS else (
    Path(
        r'C:\Users\clfbe\AppData\Local\intelligent-environments-lab\citylearn'
        r'\Cache\v2.3.0\datasets'
    ) / NAME
)

COL23 = {
    'Month': 'month',
    'Hour': 'hour',
    'Day Type': 'day_type',
    'Daylight Savings Status': 'daylight_savings_status',
    'Indoor Temperature (C)': 'indoor_dry_bulb_temperature',
    'Average Unmet Cooling Setpoint Difference (C)': 'average_unmet_cooling_setpoint_difference',
    'Indoor Relative Humidity (%)': 'indoor_relative_humidity',
    'Equipment Electric Power (kWh)': 'non_shiftable_load',
    'DHW Heating (kWh)': 'dhw_demand',
    'Cooling Load (kWh)': 'cooling_demand',
    'Heating Load (kWh)': 'heating_demand',
    'Solar Generation (W/kW)': 'solar_generation',
    'Occupant Count (people)': 'occupant_count',
    'Temperature Set Point (C)': 'temperature_set_point',
    'HVAC Mode (Off/Cooling/Heating)': 'hvac_mode',
}

BUILDING_COLS = [
    'month', 'hour', 'day_type', 'daylight_savings_status',
    'indoor_dry_bulb_temperature', 'average_unmet_cooling_setpoint_difference',
    'indoor_relative_humidity', 'non_shiftable_load', 'dhw_demand',
    'cooling_demand', 'heating_demand', 'solar_generation', 'occupant_count',
    'indoor_dry_bulb_temperature_cooling_set_point',
    'indoor_dry_bulb_temperature_heating_set_point', 'hvac_mode',
]


def load_building23(name: str) -> pd.DataFrame:
    df = pd.read_csv(SRC23 / f'{name}.csv').rename(columns=COL23)
    if 'temperature_set_point' in df.columns:
        df['indoor_dry_bulb_temperature_cooling_set_point'] = df['temperature_set_point']
        df['indoor_dry_bulb_temperature_heating_set_point'] = df['temperature_set_point']
    return df


def build_calendar_2026() -> pd.DataFrame:
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    assert (end - start).days + 1 == 365
    rows = []
    d = start
    while d <= end:
        day_type = d.weekday() + 1  # Mon=1 .. Sun=7
        dst = 1 if 3 <= d.month <= 10 else 0
        for h in range(1, 25):
            rows.append({
                'date': d.isoformat(),
                'month': d.month,
                'hour': h,
                'day_type': day_type,
                'daylight_savings_status': dst,
            })
        d += timedelta(days=1)
    cal = pd.DataFrame(rows)
    assert len(cal) == 8760
    return cal


def iter_source_days(df: pd.DataFrame) -> list[dict]:
    """按时间顺序提取源 CSV 中每个完整日（hour 1..24）。"""
    hours = df['hour'].to_numpy()
    starts = [i for i in range(len(df)) if hours[i] == 1 and i + 24 <= len(df)]
    days = []
    for day_start in starts:
        idx = np.arange(day_start, day_start + 24, dtype=int)
        block = df.iloc[idx]
        if not np.array_equal(block['hour'].to_numpy(), np.arange(1, 25)):
            continue
        months = block['month'].unique()
        dows = block['day_type'].unique()
        if len(months) != 1 or len(dows) != 1:
            continue
        days.append({
            'idx': idx,
            'month': int(months[0]),
            'day_type': int(dows[0]),
        })
    return days


def extract_source_weeks(days: list[dict]) -> list[dict]:
    """
    提取源数据中连续的 Mon..Sun 整周（day_type 序列恰为 1..7）。
    每个整周保留 7 天原始负荷/天气耦合，供特征重构整周搬迁。
    """
    weeks = []
    i = 0
    while i + 7 <= len(days):
        chunk = days[i:i + 7]
        if [d['day_type'] for d in chunk] == list(range(1, 8)):
            weeks.append({
                'days': chunk,
                'idx': np.concatenate([d['idx'] for d in chunk]),
                'month_mode': int(pd.Series([d['month'] for d in chunk]).mode().iloc[0]),
            })
            i += 7
        else:
            i += 1
    return weeks


def extract_2026_complete_weeks() -> list[dict]:
    """2026 年内所有含完整周末的 Mon..Sun 周。"""
    weeks = []
    d = date(2026, 1, 1)
    # 找到第一个周一
    while d.weekday() != 0:
        d += timedelta(days=1)
    while True:
        sun = d + timedelta(days=6)
        if sun.year != 2026:
            break
        days = [d + timedelta(days=k) for k in range(7)]
        weeks.append({
            'start': d,
            'end': sun,
            'dates': days,
            'month_mode': int(pd.Series([x.month for x in days]).mode().iloc[0]),
        })
        d += timedelta(days=7)
    return weeks


def build_day_pools_from_days(days: list[dict]) -> dict[tuple[int, int], list[np.ndarray]]:
    pools: dict[tuple[int, int], list[np.ndarray]] = {}
    for d in days:
        key = (d['month'], d['day_type'])
        pools.setdefault(key, []).append(d['idx'])
    return pools


def feature_reconstruct_row_index(cal: pd.DataFrame, source_df: pd.DataFrame) -> tuple[np.ndarray, dict]:
    """
    特征重构法（整周搬迁）：
    1) 从 2022 源序列提取连续 Mon..Sun 整周负荷块；
    2) 按季节（众数月）匹配，依次硬塞进 2026 含完整周末的周；
    3) 年首/年尾不完整周，用同月同星期单日池补齐；
    4) 最终 CSV 的 day_type/month/hour 一律按 2026 真实日历重写，
       但物理序列来自对应星期的源周，使 XGBoost 时间特征与负荷逻辑一致。

    例：源第 1 个完整周 → 2026 第一个 Mon..Sun 完整周（2026-01-05..01-11）。
    """
    src_days = iter_source_days(source_df)
    src_weeks = extract_source_weeks(src_days)
    tgt_weeks = extract_2026_complete_weeks()
    pools = build_day_pools_from_days(src_days)
    if not src_weeks:
        raise RuntimeError('no Mon-Sun source weeks found')
    if not tgt_weeks:
        raise RuntimeError('no complete 2026 weeks found')

    # 按目标周顺序分配源周：优先同月，否则取下一可用源周（循环）
    used = [False] * len(src_weeks)
    assignment: list[int] = []
    cursor = 0
    for tw in tgt_weeks:
        chosen = None
        # 先找未使用且 month_mode 相同的源周
        for j in range(len(src_weeks)):
            k = (cursor + j) % len(src_weeks)
            if not used[k] and src_weeks[k]['month_mode'] == tw['month_mode']:
                chosen = k
                break
        if chosen is None:
            for j in range(len(src_weeks)):
                k = (cursor + j) % len(src_weeks)
                if not used[k]:
                    chosen = k
                    break
        if chosen is None:
            # 全部用过则循环复用
            chosen = cursor % len(src_weeks)
        used[chosen] = True
        assignment.append(chosen)
        cursor = chosen + 1

    # 建立 2026 date -> source day idx(24,)
    date_to_idx: dict[str, np.ndarray] = {}
    for tw, sw_i in zip(tgt_weeks, assignment):
        sw = src_weeks[sw_i]
        for d2026, sday in zip(tw['dates'], sw['days']):
            date_to_idx[d2026.isoformat()] = sday['idx']

    # 补齐年首年尾非完整周日期
    counters: dict[tuple[int, int], int] = {}
    all_dates = cal.loc[cal['hour'] == 1, ['date', 'month', 'day_type']].reset_index(drop=True)
    edge_filled = 0
    for _, row in all_dates.iterrows():
        ds = row['date']
        if ds in date_to_idx:
            continue
        key = (int(row['month']), int(row['day_type']))
        bucket = pools.get(key) or pools.get((int(row['month']), int(row['day_type'])))
        # 回退：任意同星期
        if not bucket:
            bucket = []
            for (m, dt), v in pools.items():
                if dt == int(row['day_type']):
                    bucket.extend(v)
        if not bucket:
            raise RuntimeError(f'no pool for edge day {ds} key={key}')
        k = counters.get(key, 0)
        date_to_idx[ds] = bucket[k % len(bucket)]
        counters[key] = k + 1
        edge_filled += 1

    pieces = [date_to_idx[ds] for ds in all_dates['date'].tolist()]
    idx = np.concatenate(pieces)
    assert len(idx) == len(cal)

    meta = {
        'method': 'feature_reconstruction_week_blocks',
        'source_complete_weeks': len(src_weeks),
        'target_complete_weeks': len(tgt_weeks),
        'first_target_week': f"{tgt_weeks[0]['start']} .. {tgt_weeks[0]['end']}",
        'first_source_week_month_mode': src_weeks[assignment[0]]['month_mode'],
        'edge_days_filled': edge_filled,
        'week_assignment': [
            {
                'target': f"{tw['start']}..{tw['end']}",
                'source_week_index': int(sw_i),
                'source_month_mode': int(src_weeks[sw_i]['month_mode']),
            }
            for tw, sw_i in zip(tgt_weeks[:3], assignment[:3])  # 摘要前 3 周
        ],
    }
    return idx, meta


def align_frame(df: pd.DataFrame, idx: np.ndarray) -> pd.DataFrame:
    return df.iloc[idx].reset_index(drop=True)


def fit_temp_load_model(df23: pd.DataFrame, weather23: pd.DataFrame, col: str):
    """按室外温度分箱估计平均冷/热负荷，并给出小时修正。"""
    w = weather23.copy()
    if 'Outdoor Drybulb Temperature (C)' in w.columns:
        tout = w['Outdoor Drybulb Temperature (C)'].to_numpy(dtype=float)
    else:
        tout = w['outdoor_dry_bulb_temperature'].to_numpy(dtype=float)
    y = df23[col].to_numpy(dtype=float)
    # 温度分箱均值
    edges = np.arange(math.floor(tout.min()) - 1, math.ceil(tout.max()) + 2, 1.0)
    centers = 0.5 * (edges[:-1] + edges[1:])
    idx = np.clip(np.digitize(tout, edges) - 1, 0, len(centers) - 1)
    bin_sum = np.zeros(len(centers))
    bin_cnt = np.zeros(len(centers))
    for i, v in zip(idx, y):
        bin_sum[i] += v
        bin_cnt[i] += 1
    bin_mean = np.divide(bin_sum, np.maximum(bin_cnt, 1), where=bin_cnt > 0)
    # 空箱用邻域插值
    for i in range(len(bin_mean)):
        if bin_cnt[i] == 0:
            left = next((bin_mean[j] for j in range(i - 1, -1, -1) if bin_cnt[j] > 0), 0.0)
            right = next((bin_mean[j] for j in range(i + 1, len(bin_mean)) if bin_cnt[j] > 0), left)
            bin_mean[i] = 0.5 * (left + right)
    hour_mean = df23.groupby('hour')[col].mean()
    global_mean = float(y.mean()) + 1e-9
    hour_factor = (hour_mean / global_mean).reindex(range(1, 25)).fillna(1.0)
    return centers, bin_mean, hour_factor.to_dict(), float(y.mean())


def predict_temp_load(tout, hours, centers, bin_mean, hour_factor) -> np.ndarray:
    idx = np.argmin(np.abs(centers.reshape(-1, 1) - tout.reshape(1, -1)), axis=0)
    base = bin_mean[idx]
    hf = np.array([hour_factor.get(int(h), 1.0) for h in hours], dtype=float)
    return np.maximum(0.0, base * hf)


def fit_dhw_profile(df23: pd.DataFrame) -> dict:
    g = df23.groupby(['day_type', 'hour'])['dhw_demand'].mean()
    return {(int(dt), int(h)): float(v) for (dt, h), v in g.items()}


def fit_occupant_profile(df23: pd.DataFrame) -> dict:
    g = df23.groupby(['day_type', 'hour'])['occupant_count'].mean()
    return {(int(dt), int(h)): float(v) for (dt, h), v in g.items()}


def fit_setpoint_profile(df23: pd.DataFrame) -> dict:
    cool = df23.groupby('hour')['indoor_dry_bulb_temperature_cooling_set_point'].mean()
    heat = df23.groupby('hour')['indoor_dry_bulb_temperature_heating_set_point'].mean()
    return {
        'cooling': cool.reindex(range(1, 25)).ffill().bfill().to_dict(),
        'heating': heat.reindex(range(1, 25)).ffill().bfill().to_dict(),
    }


def synthesize_building(
    df22: pd.DataFrame,
    weather22: pd.DataFrame,
    cal: pd.DataFrame,
    df23: pd.DataFrame,
    weather23: pd.DataFrame,
    rng: np.random.Generator,
    shared_cool=None,
    shared_heat=None,
    ref_nsl23: float = 1.0,
) -> pd.DataFrame:
    if shared_cool is None:
        cool_c, cool_m, cool_hf, cool_mu = fit_temp_load_model(df23, weather23, 'cooling_demand')
    else:
        cool_c, cool_m, cool_hf, cool_mu = shared_cool
    if shared_heat is None:
        heat_c, heat_m, heat_hf, heat_mu = fit_temp_load_model(df23, weather23, 'heating_demand')
    else:
        heat_c, heat_m, heat_hf, heat_mu = shared_heat

    dhw_prof = fit_dhw_profile(df23)
    occ_prof = fit_occupant_profile(df23)
    sp = fit_setpoint_profile(df23)

    tout = weather22['outdoor_dry_bulb_temperature'].to_numpy(dtype=float)
    tout_rh = weather22['outdoor_relative_humidity'].to_numpy(dtype=float) if 'outdoor_relative_humidity' in weather22.columns else None
    hours = df22['hour'].to_numpy(dtype=int)
    day_types = df22['day_type'].to_numpy(dtype=int)

    cooling = predict_temp_load(tout, hours, cool_c, cool_m, cool_hf)
    heating = predict_temp_load(tout, hours, heat_c, heat_m, heat_hf)
    month = df22['month'].to_numpy(dtype=int)

    # 2023 online_1 几乎无采暖样本；用 Fontana 气温补 HDD 制热，避免全年 heating=0
    # 平衡点约 16°C：室外越冷需求越大（kWh 热），再乘小时修正
    heat_hour = {
        1: 1.15, 2: 1.15, 3: 1.10, 4: 1.05, 5: 1.05, 6: 1.10,
        7: 1.00, 8: 0.85, 9: 0.80, 10: 0.85, 11: 0.90, 12: 1.00,
        13: 1.00, 14: 0.95, 15: 0.95, 16: 1.00, 17: 1.10, 18: 1.20,
        19: 1.25, 20: 1.25, 21: 1.20, 22: 1.15, 23: 1.15, 24: 1.15,
    }
    hdd = np.maximum(0.0, 16.0 - tout)
    heating_hdd = hdd * 0.12 * np.array([heat_hour[int(h)] for h in hours], dtype=float)
    # 夏季模型采暖很弱时，用 HDD 结果托底；夏季（冷负荷主导月）压低采暖
    heating = np.maximum(heating, heating_hdd)
    heating = np.where(np.isin(month, [6, 7, 8, 9]), heating * 0.05, heating)
    cooling = np.where(np.isin(month, [11, 12, 1, 2]), cooling * 0.20, cooling)

    # CityLearn 禁止同一时步 cooling 与 heating 同时 > 0：按负荷较大者取舍
    use_cool = cooling >= heating
    heating = np.where(use_cool, 0.0, heating)
    cooling = np.where(use_cool, cooling, 0.0)

    dhw = np.array([
        dhw_prof.get((int(dt), int(h)), dhw_prof.get((1, int(h)), 0.0))
        for dt, h in zip(day_types, hours)
    ], dtype=float)

    # 按该楼 2022 用电与 2023 参考用电比例缩放
    scale = float(df22['non_shiftable_load'].mean() / max(ref_nsl23, 1e-6))
    scale = float(np.clip(scale, 0.5, 3.0))
    cooling *= scale
    heating *= scale
    dhw *= scale

    # 夏季保底制冷
    cool_hour = df23.groupby('hour')['cooling_demand'].mean()
    floor = np.array([cool_hour.get(int(h), cool_mu) for h in hours], dtype=float) * scale
    cooling = np.where(np.isin(month, [6, 7, 8, 9]), np.maximum(cooling, 0.45 * floor), cooling)

    # 噪声
    cooling = np.maximum(0.0, cooling * rng.normal(1.0, 0.04, size=len(cooling)))
    heating = np.maximum(0.0, heating * rng.normal(1.0, 0.04, size=len(heating)))
    dhw = np.maximum(0.0, dhw * rng.normal(1.0, 0.05, size=len(dhw)))

    # 噪声 / 夏季保底后再互斥一次
    use_cool = cooling >= heating
    heating = np.where(use_cool, 0.0, heating)
    cooling = np.where(use_cool, cooling, 0.0)

    # 热负荷→估算用电并从 non_shiftable 扣除（热泵 COP≈1/0.25=4，电加热 η≈0.94）
    cool_elec = cooling * 0.28
    heat_elec = heating * 0.35
    dhw_elec = dhw / 0.94
    nsl = df22['non_shiftable_load'].to_numpy(dtype=float)
    # 最多扣减原负荷的 55%，保留插座等基线
    deduct = np.minimum(cool_elec + heat_elec + dhw_elec, 0.55 * nsl)
    nsl_new = np.maximum(0.05, nsl - deduct)

    occ = np.array([
        occ_prof.get((int(dt), int(h)), occ_prof.get((1, int(h)), 2.0))
        for dt, h in zip(day_types, hours)
    ], dtype=float)
    occ = np.clip(np.rint(occ + rng.normal(0, 0.15, size=len(occ))), 0, 3).astype(float)

    cool_sp = np.array([sp['cooling'].get(int(h), 24.44) for h in hours], dtype=float)
    heat_sp = np.array([sp['heating'].get(int(h), 21.11) for h in hours], dtype=float)
    # 冬季略降设定，夏季略升（贴近 2023 分布）
    cool_sp = np.where(np.isin(month, [6, 7, 8]), cool_sp, cool_sp - 0.5)
    heat_sp = np.where(np.isin(month, [12, 1, 2]), heat_sp - 0.3, heat_sp)

    hvac = np.zeros(len(hours), dtype=int)
    hvac = np.where(cooling > 0.02, 1, hvac)
    hvac = np.where(heating > 0.02, 2, hvac)

    indoor = df22['indoor_dry_bulb_temperature'].to_numpy(dtype=float)
    # 2022 室内温度列全为空；用设定点 + 2023 室内相对偏差启发重造
    if np.isnan(indoor).all() or np.nanstd(indoor) < 1e-9:
        # 2023：室内相对设定点的小时平均偏差
        sp23 = df23['indoor_dry_bulb_temperature_cooling_set_point'].to_numpy(dtype=float)
        in23 = df23['indoor_dry_bulb_temperature'].to_numpy(dtype=float)
        delta = pd.DataFrame({
            'hour': df23['hour'].to_numpy(dtype=int),
            'delta': in23 - sp23,
        }).groupby('hour')['delta'].mean()
        d_hour = delta.reindex(range(1, 25)).fillna(0.0).to_dict()
        base_sp = np.where(hvac == 2, heat_sp, cool_sp)
        indoor = base_sp + np.array([d_hour.get(int(h), 0.0) for h in hours], dtype=float)
        indoor = indoor + rng.normal(0.0, 0.25, size=len(indoor))
        # 无 HVAC 时更随室外漂
        indoor = np.where(hvac == 0, 0.6 * indoor + 0.4 * tout, indoor)
    else:
        target = np.where(hvac == 1, cool_sp, np.where(hvac == 2, heat_sp, indoor))
        indoor = 0.7 * indoor + 0.3 * target
    indoor = np.clip(indoor, 16.0, 32.0)

    unmet = np.maximum(0.0, indoor - cool_sp)

    # 2022 室内湿度列通常全空；用 2023 小时均值剖面 + 2026 室外湿度合成
    rh = df22['indoor_relative_humidity'].to_numpy(dtype=float)
    if np.isnan(rh).all() or np.nanstd(np.nan_to_num(rh, nan=0.0)) < 1e-9:
        rh23 = df23['indoor_relative_humidity'].to_numpy(dtype=float)
        h23 = df23['hour'].to_numpy(dtype=int)
        rh_hour = (
            pd.DataFrame({'hour': h23, 'rh': rh23})
            .groupby('hour')['rh']
            .mean()
            .reindex(range(1, 25))
            .fillna(rh23[~np.isnan(rh23)].mean() if np.any(~np.isnan(rh23)) else 50.0)
        )
        profile = np.array([float(rh_hour.get(int(h), 50.0)) for h in hours], dtype=float)
        # 室外湿度（与建筑等长）；缺测时退回剖面
        if tout_rh is not None and len(tout_rh) == len(hours):
            rh = 0.55 * tout_rh + 0.45 * profile + rng.normal(0.0, 1.5, size=len(hours))
        else:
            rh = profile + rng.normal(0.0, 2.0, size=len(hours))
        rh = np.clip(rh, 25.0, 85.0)

    out = pd.DataFrame({
        'month': cal['month'].values,
        'hour': cal['hour'].values,
        'day_type': cal['day_type'].values,
        'daylight_savings_status': cal['daylight_savings_status'].values,
        'indoor_dry_bulb_temperature': indoor,
        'average_unmet_cooling_setpoint_difference': unmet,
        'indoor_relative_humidity': rh,
        'non_shiftable_load': nsl_new,
        'dhw_demand': dhw,
        'cooling_demand': cooling,
        'heating_demand': heating,
        'solar_generation': df22['solar_generation'].values,
        'occupant_count': occ,
        'indoor_dry_bulb_temperature_cooling_set_point': cool_sp,
        'indoor_dry_bulb_temperature_heating_set_point': heat_sp,
        'hvac_mode': hvac,
    })[BUILDING_COLS]
    return out


def scale_device(attrs: dict, factor: float, keys: tuple[str, ...]) -> dict:
    out = deepcopy(attrs)
    for k in keys:
        if k in out and isinstance(out[k], (int, float)):
            out[k] = float(out[k]) * factor
    return out


def build_schema(cal_len: int = 8760) -> dict:
    """
    以可被 CityLearn 2.3.x 加载的 2026_jul_sep schema 为模板
   （单层 dynamics.type），再叠 2022 电池/PV 与缩放后的 2023 热泵/DHW。
    """
    s22 = json.loads((SRC22 / 'schema.json').read_text(encoding='utf-8'))
    s23 = json.loads((SRC23 / 'schema.json').read_text(encoding='utf-8'))
    template_path = ROOT / 'datasets' / 'citylearn_challenge_2026_jul_sep' / 'schema.json'
    if not template_path.exists():
        template_path = (
            ROOT / 'CHESCA-copy' / 'data' / 'schemas'
            / 'citylearn_challenge_2026_jul_sep' / 'schema.json'
        )
    schema = json.loads(template_path.read_text(encoding='utf-8'))
    schema['random_seed'] = 2026
    schema['root_directory'] = None
    schema['central_agent'] = True
    schema['simulation_start_time_step'] = 0
    schema['simulation_end_time_step'] = cal_len - 1
    schema['episode_time_steps'] = None

    buildings = {}
    for name in BUILDINGS:
        b22 = s22['buildings'][name]
        b23 = s23['buildings'][name]
        b = deepcopy(schema['buildings'][name])
        b['include'] = True
        b['energy_simulation'] = f'{name}.csv'
        b['weather'] = 'weather.csv'
        b['carbon_intensity'] = 'carbon_intensity.csv'
        b['pricing'] = 'pricing.csv'
        b['type'] = 'citylearn.building.LSTMDynamicsBuilding'

        # 保留 2022 电池与光伏
        b['electrical_storage'] = deepcopy(b22['electrical_storage'])
        b['pv'] = deepcopy(b22['pv'])

        # 按负荷比缩放 2023 热泵/DHW 设备
        nsl22 = float(pd.read_csv(SRC22 / f'{name}.csv')['non_shiftable_load'].mean())
        nsl23 = float(load_building23(name)['non_shiftable_load'].mean())
        fac = float(np.clip(nsl22 / max(nsl23, 1e-6), 0.6, 2.5))
        b['cooling_device'] = deepcopy(b23['cooling_device'])
        b['dhw_device'] = deepcopy(b23['dhw_device'])
        b['dhw_storage'] = deepcopy(b23['dhw_storage'])
        b['cooling_device']['attributes'] = scale_device(
            b23['cooling_device']['attributes'], fac, ('nominal_power',)
        )
        b['dhw_device']['attributes'] = scale_device(
            b23['dhw_device']['attributes'], fac, ('nominal_power',)
        )
        b['dhw_storage']['attributes'] = scale_device(
            b23['dhw_storage']['attributes'], fac, ('capacity',)
        )
        # 增加电采暖设备，使全年 heating_demand 可被满足（2023 schema 默认无此设备）
        heat_nom = float(b['cooling_device']['attributes']['nominal_power']) * 0.85
        b['heating_device'] = {
            'type': 'citylearn.energy_model.ElectricHeater',
            'autosize': False,
            'attributes': {
                'nominal_power': heat_nom,
                'efficiency': 0.95,
            },
        }

        # CityLearn 2.3：单层 dynamics（非 cooling/heating 嵌套）
        dyn_src = b23['dynamics']
        if 'cooling' in dyn_src:
            dyn_attrs = deepcopy(dyn_src['cooling']['attributes'])
        else:
            dyn_attrs = deepcopy(dyn_src.get('attributes', b['dynamics']['attributes']))
        dyn_attrs['filename'] = f'{name}.pth'
        # 2.3 常用 cooling_set_point 观测名
        names = dyn_attrs.get('input_observation_names', [])
        names = [
            'indoor_dry_bulb_temperature_cooling_set_point'
            if n == 'indoor_dry_bulb_temperature_set_point' else n
            for n in names
        ]
        dyn_attrs['input_observation_names'] = names
        b['dynamics'] = {
            'type': 'citylearn.dynamics.LSTMDynamics',
            'attributes': dyn_attrs,
        }

        # 停电模型换种子
        if 'power_outage' not in b:
            b['power_outage'] = deepcopy(b23.get('power_outage', {}))
        if 'stochastic_power_outage_model' in b.get('power_outage', {}):
            attrs = b['power_outage']['stochastic_power_outage_model'].setdefault('attributes', {})
            attrs['random_seed'] = 202600 + int(name.split('_')[1])

        b['inactive_observations'] = []
        b['inactive_actions'] = []
        buildings[name] = b

    # 只保留三栋。
    # CityLearn 2.3 不允许 cooling_device 与 heating_device 动作同时 active；
    # 保留 heating_device 设备以满足冬季需求，但动作保持 inactive（由环境按需求自动满足），
    # 这样不破坏 CHESCA 对 cooling_device 动作的依赖。
    schema['buildings'] = buildings
    if 'heating_device' in schema.get('actions', {}):
        schema['actions']['heating_device'] = {'active': False}
    if 'cooling_device' in schema.get('actions', {}):
        schema['actions']['cooling_device'] = {'active': True}
    return schema


def write_dataset(
    out_dir: Path,
    buildings: dict[str, pd.DataFrame],
    schema: dict,
    weather: pd.DataFrame,
    pricing: pd.DataFrame,
    carbon: pd.DataFrame,
    align_meta: dict | None = None,
) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    for name, df in buildings.items():
        df.to_csv(out_dir / f'{name}.csv', index=False)
        src_pth = SRC23 / f'{name}.pth'
        if src_pth.exists():
            shutil.copy2(src_pth, out_dir / f'{name}.pth')

    weather.to_csv(out_dir / 'weather.csv', index=False)
    pricing.to_csv(out_dir / 'pricing.csv', index=False)
    carbon.to_csv(out_dir / 'carbon_intensity.csv', index=False)

    (out_dir / 'schema.json').write_text(
        json.dumps(schema, indent=2, ensure_ascii=False), encoding='utf-8'
    )

    meta = {
        'name': NAME,
        'calendar': '2026-01-01 .. 2026-12-31 (365 days, 8760 hours)',
        'buildings': list(BUILDINGS),
        'baseline': 'citylearn_challenge_2022_phase_1 (Building_1..3)',
        'reference_for_missing': 'citylearn_challenge_2023_phase_2_online_evaluation_1',
        'construction': {
            'calendar_alignment': (
                'Feature reconstruction with week blocks: extract contiguous Mon-Sun '
                'weeks from 2022 source load curves and place them into 2026 weeks that '
                'contain a complete weekend; regenerate day_type/month/hour from the real '
                '2026 calendar so XGBoost time features match the transplanted weekday '
                'load logic (e.g. first source Mon-Sun week -> 2026-01-05..01-11). '
                'Leading/trailing partial weeks filled by same-month/same-weekday days.'
            ),
            'kept_from_2022_aligned': [
                'non_shiftable_load (after end-use split deduction)',
                'solar_generation',
                'indoor_relative_humidity',
                'weather.csv', 'pricing.csv', 'carbon_intensity.csv',
                'electrical_storage', 'pv',
            ],
            'synthesized_from_2023_patterns': [
                'cooling_demand (temp+hour model + summer floor)',
                'heating_demand (HDD@16C + hour profile; mutually exclusive with cooling)',
                'dhw_demand (day_type×hour profile)',
                'occupant_count (day_type×hour profile)',
                'cooling/heating set points',
                'hvac_mode (1=cool, 2=heat)',
                'cooling_device / heating_device / dhw_device / dhw_storage',
                'LSTM dynamics .pth (CityLearn 2.3 single-layer format)',
                'power_outage model (new seeds)',
            ],
            'note': (
                'Synthetic research dataset. Not measured 2026 weather. '
                'Source physical year is CityLearn 2022 challenge series '
                '(Fontana / Sierra Crest), not calendar-year 2022.'
            ),
            'feature_reconstruction_meta': align_meta or {},
        },
    }
    (out_dir / 'DATASET_README.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print('wrote', out_dir)


def register_dataset_name() -> None:
    """在所有已知 CityLearn Cache 版本的 dataset_names.json 中注册本数据集。"""
    cache_roots = set()
    try:
        from citylearn.data import DataSet
        cache_roots.add(Path(DataSet().cache_directory))
    except Exception:
        pass
    base = Path(r'C:\Users\clfbe\AppData\Local\intelligent-environments-lab\citylearn')
    for p in (base / 'Cache' / 'v2.3.0', base / 'Cache' / 'v2.5.0'):
        if p.is_dir():
            cache_roots.add(p)

    for cache_root in sorted(cache_roots):
        names_path = cache_root / 'dataset_names.json'
        if not names_path.parent.exists():
            continue
        names = json.loads(names_path.read_text(encoding='utf-8')) if names_path.exists() else []
        if NAME not in names:
            names.append(NAME)
            names_path.write_text(json.dumps(sorted(set(names)), indent=2), encoding='utf-8')
            print('registered', NAME, 'in', names_path)


def main() -> None:
    if not SRC22.is_dir():
        raise FileNotFoundError(SRC22)
    if not SRC23.is_dir():
        raise FileNotFoundError(SRC23)

    cal = build_calendar_2026()
    b1_raw = pd.read_csv(SRC22 / 'Building_1.csv')
    align_idx, align_meta = feature_reconstruct_row_index(cal, b1_raw)
    src_dt = b1_raw.iloc[align_idx]['day_type'].to_numpy()
    match = float(np.mean(src_dt == cal['day_type'].to_numpy()))
    print(f'feature_reconstruct day_type match rate: {match:.3f} (expect 1.000)')
    print('align_meta', {k: align_meta[k] for k in [
        'method', 'source_complete_weeks', 'target_complete_weeks',
        'first_target_week', 'first_source_week_month_mode', 'edge_days_filled',
    ]})
    assert match > 0.999, match

    # 整周完整性：完整周内 7 天应来自源中连续 Mon..Sun 块（源 day_type 恰为 1..7）
    tgt_weeks = extract_2026_complete_weeks()
    day_starts = list(range(0, 8760, 24))
    date_list = cal.loc[cal['hour'] == 1, 'date'].tolist()
    date_to_daypos = {ds: i for i, ds in enumerate(date_list)}
    intact = 0
    for tw in tgt_weeks:
        pos = [date_to_daypos[d.isoformat()] for d in tw['dates']]
        # 源下标：每天 24 行，检查源 day_type 序列
        src_dows = [int(b1_raw.iloc[align_idx[p * 24]]['day_type']) for p in pos]
        if src_dows == list(range(1, 8)):
            intact += 1
    print(f'intact Mon-Sun week blocks placed: {intact}/{len(tgt_weeks)}')
    assert intact == len(tgt_weeks)

    weather22 = align_frame(pd.read_csv(SRC22 / 'weather.csv'), align_idx)
    pricing22 = align_frame(pd.read_csv(SRC22 / 'pricing.csv'), align_idx)
    carbon22 = align_frame(pd.read_csv(SRC22 / 'carbon_intensity.csv'), align_idx)
    weather23 = pd.read_csv(SRC23 / 'weather.csv')
    assert len(weather22) == 8760

    pooled23 = pd.concat([load_building23(n) for n in BUILDINGS], ignore_index=True)
    weather23_pooled = pd.concat([weather23] * 3, ignore_index=True)
    shared_cool = fit_temp_load_model(pooled23, weather23_pooled, 'cooling_demand')
    shared_heat = fit_temp_load_model(pooled23, weather23_pooled, 'heating_demand')
    ref_nsl23 = float(pooled23['non_shiftable_load'].mean())

    buildings = {}
    for i, name in enumerate(BUILDINGS):
        rng = np.random.default_rng(2026 * 10 + i)
        df22 = align_frame(pd.read_csv(SRC22 / f'{name}.csv'), align_idx)
        # 对齐后用 2026 日历覆盖标签（与源 day_type 已一致；month/hour 亦对齐）
        df22 = df22.copy()
        df22['month'] = cal['month'].values
        df22['hour'] = cal['hour'].values
        df22['day_type'] = cal['day_type'].values
        df22['daylight_savings_status'] = cal['daylight_savings_status'].values
        df23 = load_building23(name)
        buildings[name] = synthesize_building(
            df22, weather22, cal, df23, weather23, rng,
            shared_cool=shared_cool, shared_heat=shared_heat, ref_nsl23=ref_nsl23,
        )
        b = buildings[name]
        print(
            name,
            'nsl', round(b['non_shiftable_load'].mean(), 3),
            'cool', round(b['cooling_demand'].mean(), 3),
            'dhw', round(b['dhw_demand'].mean(), 3),
            'heat', round(b['heating_demand'].mean(), 3),
            'heat%>0', round(float((b['heating_demand'] > 0).mean()), 3),
            'occ', round(b['occupant_count'].mean(), 2),
        )

    schema = build_schema(8760)

    for name, df in buildings.items():
        cool_nom = float(schema['buildings'][name]['cooling_device']['attributes']['nominal_power'])
        cool_eff = float(schema['buildings'][name]['cooling_device']['attributes'].get('efficiency', 0.25))
        cool_cap = cool_nom / max(cool_eff, 1e-3)
        heat_nom = float(schema['buildings'][name]['heating_device']['attributes']['nominal_power'])
        heat_eff = float(schema['buildings'][name]['heating_device']['attributes'].get('efficiency', 0.95))
        heat_cap = heat_nom * max(heat_eff, 1e-3)
        dhw_nom = float(schema['buildings'][name]['dhw_device']['attributes']['nominal_power'])
        dhw_eff = float(schema['buildings'][name]['dhw_device']['attributes'].get('efficiency', 0.94))
        dhw_cap = dhw_nom * max(dhw_eff, 1e-3)
        df['cooling_demand'] = np.minimum(df['cooling_demand'].to_numpy(dtype=float), 0.95 * cool_cap)
        df['heating_demand'] = np.minimum(df['heating_demand'].to_numpy(dtype=float), 0.95 * heat_cap)
        df['dhw_demand'] = np.minimum(df['dhw_demand'].to_numpy(dtype=float), 0.95 * dhw_cap)
        buildings[name] = df

    targets = list(OUTS)
    for cache_dir in CACHE_DIRS:
        if cache_dir.parent.exists() or True:
            cache_dir.parent.mkdir(parents=True, exist_ok=True)
            if cache_dir not in targets:
                targets.append(cache_dir)
    for out in targets:
        write_dataset(out, buildings, schema, weather22, pricing22, carbon22, align_meta)
    register_dataset_name()
    print('DONE', NAME)


if __name__ == '__main__':
    main()
