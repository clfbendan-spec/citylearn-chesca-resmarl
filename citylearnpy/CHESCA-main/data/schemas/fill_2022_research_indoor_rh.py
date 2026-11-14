"""Add a ResStock-calibrated but unverified indoor-RH proxy dataset variant."""

from __future__ import annotations

import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "citylearn_challenge_2022_2023flow_research"
RESSTOCK = HERE.parents[3] / "AAC_MADRL" / "data" / "TX_10_dynamics"
OUTPUT = HERE / "citylearn_challenge_2022_2023flow_research_with_rh_proxy"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def humidity_ratio(temperature_c: float, relative_humidity: float) -> float:
    saturation_pressure = 0.61078 * math.exp(17.2694 * temperature_c / (temperature_c + 237.3))
    vapor_pressure = min(0.999 * saturation_pressure, max(0.00001, relative_humidity / 100.0 * saturation_pressure))
    return 0.62198 * vapor_pressure / (101.325 - vapor_pressure)


def relative_humidity(temperature_c: float, ratio: float) -> float:
    saturation_pressure = 0.61078 * math.exp(17.2694 * temperature_c / (temperature_c + 237.3))
    vapor_pressure = 101.325 * ratio / (0.62198 + ratio)
    return 100.0 * vapor_pressure / saturation_pressure


def bin_key(row: dict[str, str]) -> tuple[int, int, int]:
    return int(float(row["month"])), int(float(row["day_type"])), int(float(row["hour"]))


def fit_profile(excluded: str | None = None) -> tuple[dict, float, float]:
    weather = read_csv(RESSTOCK / "weather.csv")
    sums: dict[tuple[int, int, int], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    home_rows: dict[str, list[tuple]] = {}

    for path in sorted(RESSTOCK.glob("resstock-*.csv")):
        if path.name == excluded:
            continue
        rows = read_csv(path)
        records = []
        for row, outdoor in zip(rows, weather):
            key = bin_key(row)
            indoor_w = humidity_ratio(float(row["indoor_dry_bulb_temperature"]), float(row["indoor_relative_humidity"]))
            outdoor_w = humidity_ratio(float(outdoor["outdoor_dry_bulb_temperature"]), float(outdoor["outdoor_relative_humidity"]))
            occupants = float(row["occupant_count"])
            records.append((key, indoor_w, outdoor_w, occupants, float(row["indoor_dry_bulb_temperature"]), float(row["indoor_relative_humidity"])))
            sums[key][0] += indoor_w
            sums[key][1] += outdoor_w
            sums[key][2] += occupants
            sums[key][3] += 1.0
        home_rows[path.name] = records

    means = {key: (v[0] / v[3], v[1] / v[3], v[2] / v[3]) for key, v in sums.items()}
    out_cov = out_var = occ_cov = occ_var = 0.0
    for records in home_rows.values():
        for key, indoor_w, outdoor_w, occupants, *_ in records:
            mean_indoor_w, mean_outdoor_w, mean_occ = means[key]
            do = outdoor_w - mean_outdoor_w
            dc = occupants - mean_occ
            di = indoor_w - mean_indoor_w
            out_cov += do * di
            out_var += do * do
            occ_cov += dc * di
            occ_var += dc * dc
    outdoor_slope = out_cov / out_var if out_var else 0.0
    occupancy_slope = occ_cov / occ_var if occ_var else 0.0
    return (means, outdoor_slope, occupancy_slope), sums, weather


def leave_one_home_out_rmse() -> dict[str, float]:
    weather = read_csv(RESSTOCK / "weather.csv")
    results = []
    files = sorted(RESSTOCK.glob("resstock-*.csv"))
    for heldout in files:
        (means, outdoor_slope, occupancy_slope), _, _ = fit_profile(heldout.name)
        rows = read_csv(heldout)
        errors = []
        for row, outdoor in zip(rows, weather):
            mean_indoor_w, mean_outdoor_w, mean_occ = means[bin_key(row)]
            target_outdoor_w = humidity_ratio(float(outdoor["outdoor_dry_bulb_temperature"]), float(outdoor["outdoor_relative_humidity"]))
            predicted_w = mean_indoor_w + outdoor_slope * (target_outdoor_w - mean_outdoor_w) + occupancy_slope * (float(row["occupant_count"]) - mean_occ)
            predicted_rh = relative_humidity(float(row["indoor_dry_bulb_temperature"]), max(0.00002, min(0.03, predicted_w)))
            errors.append((predicted_rh - float(row["indoor_relative_humidity"])) ** 2)
        results.append(math.sqrt(sum(errors) / len(errors)))
    return {"mean_rmse_percentage_points": sum(results) / len(results), "median_rmse_percentage_points": sorted(results)[len(results) // 2], "max_rmse_percentage_points": max(results), "homes": len(results)}


def fill_dataset(target: Path) -> None:
    (profiles, outdoor_slope, occupancy_slope), _, _ = fit_profile()
    cv = leave_one_home_out_rmse()
    target_weather = read_csv(target / "weather.csv")

    for i in range(1, 18):
        path = target / f"Building_{i}.csv"
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            rows = list(reader)
        for row, weather in zip(rows, target_weather):
            key = bin_key({"month": row["Month"], "day_type": row["Day Type"], "hour": row["Hour"]})
            if key not in profiles:
                key = (key[0], 1, key[2])
            mean_indoor_w, mean_outdoor_w, mean_occ = profiles[key]
            target_outdoor_w = humidity_ratio(float(weather["Outdoor Drybulb Temperature (C)"]), float(weather["Outdoor Relative Humidity (%)"]))
            predicted_w = mean_indoor_w + outdoor_slope * (target_outdoor_w - mean_outdoor_w) + occupancy_slope * (float(row["Occupant Count (people)"]) - mean_occ)
            rh = relative_humidity(float(row["Indoor Temperature (C)"]), max(0.00002, min(0.03, predicted_w)))
            row["Indoor Relative Humidity (%)"] = f"{min(95.0, max(5.0, rh)):.6f}"
        write_csv(path, headers, rows)

    readme_path = target / "DATASET_README.json"
    readme = json.loads(readme_path.read_text(encoding="utf-8"))
    readme["name"] = target.name
    readme["builder"] = Path(__file__).name
    readme["indoor_humidity_proxy"] = {
        "method": "transfer of monthly x day_type x hour average indoor humidity ratio from 10 Texas ResStock annual simulation series, adjusted by pooled within-bin response to outdoor humidity ratio and occupancy, then converted to RH using the target indoor temperature",
        "donor_data": "AAC_MADRL/data/TX_10_dynamics/resstock-amy2018-2021-release-1-*.csv",
        "leave_one_home_out_validation": cv,
        "scope_of_validation": "Held-out homes from the same Texas donor set and weather year only; this does not validate transfer to the 2022 buildings or their climate.",
        "coefficients": {"outdoor_humidity_ratio_slope": outdoor_slope, "occupancy_slope": occupancy_slope},
        "rh_clipping_percent": [5.0, 95.0],
        "limitations": "Synthetic proxy, not measured 2022 humidity. The source buildings are not matched to the 2022 buildings. The CityLearn observation remains inactive to match the 2023 local schema.",
    }
    readme["limitations"].append("Indoor relative humidity in this variant is transferred from unmatched Texas ResStock homes; do not interpret it as measured 2022 humidity.")
    readme_path.write_text(json.dumps(readme, indent=2) + "\n", encoding="utf-8")
    print(f"Filled {target}; donor leave-one-home-out mean RH RMSE: {cv['mean_rmse_percentage_points']:.2f} percentage points")


def main() -> None:
    if not SOURCE.is_dir():
        raise SystemExit(f"Missing research dataset: {SOURCE}")
    if not RESSTOCK.is_dir():
        raise SystemExit(f"Missing ResStock donor series: {RESSTOCK}")
    if OUTPUT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {OUTPUT}")
    shutil.copytree(SOURCE, OUTPUT)
    fill_dataset(OUTPUT)


if __name__ == "__main__":
    main()
