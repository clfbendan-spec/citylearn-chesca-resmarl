"""Build a 2023-workflow-shaped, synthetic research dataset from 2022 data."""

from __future__ import annotations

import copy
import csv
import json
import math
import shutil
from pathlib import Path

from fill_2022_research_indoor_rh import fill_dataset as fill_indoor_humidity


HERE = Path(__file__).resolve().parent
RAW_2022 = HERE / "citylearn_challenge_2022_phase_all"
BASE_2022 = HERE / "citylearn_challenge_2022_phase_all_2023_compatible"
THERMAL_2022 = HERE / "citylearn_challenge_2022_thermal_proxy_medium_response"
DONOR_2023 = HERE / "citylearn_challenge_2023_phase_2_local_evaluation"
OUTPUT = HERE / "citylearn_challenge_2022_2023flow_research"
HORIZONS = ("6h", "12h", "24h")

BUILDING_HEADERS = {
    "month": "Month",
    "hour": "Hour",
    "day_type": "Day Type",
    "daylight_savings_status": "Daylight Savings Status",
    "indoor_dry_bulb_temperature": "Indoor Temperature (C)",
    "average_unmet_cooling_setpoint_difference": "Average Unmet Cooling Setpoint Difference (C)",
    "indoor_relative_humidity": "Indoor Relative Humidity (%)",
    "non_shiftable_load": "Equipment Electric Power (kWh)",
    "dhw_demand": "DHW Heating (kWh)",
    "cooling_demand": "Cooling Load (kWh)",
    "heating_demand": "Heating Load (kWh)",
    "solar_generation": "Solar Generation (W/kW)",
    "occupant_count": "Occupant Count (people)",
    "indoor_dry_bulb_temperature_set_point": "Temperature Set Point (C)",
    "hvac_mode": "HVAC Mode (Off/Cooling/Heating)",
}

WEATHER_HEADERS = {
    "outdoor_dry_bulb_temperature": "Outdoor Drybulb Temperature (C)",
    "outdoor_relative_humidity": "Outdoor Relative Humidity (%)",
    "diffuse_solar_irradiance": "Diffuse Solar Radiation (W/m2)",
    "direct_solar_irradiance": "Direct Solar Radiation (W/m2)",
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    return default if value in (None, "") else float(value)


def series_profiles(weather: list[dict[str, str]]) -> tuple[dict, dict, dict, float, float, float]:
    """Get donor occupant/setpoint/DHW profiles and weather-conditioned load slopes."""
    profile_values: dict[str, dict[tuple[int, int], list[float]]] = {
        name: {} for name in ("Occupant Count (people)", "Temperature Set Point (C)", "DHW Heating (kWh)")
    }
    cooling_total = cooling_degree = dhw_total = occupied_total = 0.0
    for i in range(1, 4):
        _, buildings = read_csv(DONOR_2023 / f"Building_{i}.csv")
        for b, w in zip(buildings, weather):
            day_hour = (int(float(b["Day Type"])), int(float(b["Hour"])))
            for field in profile_values:
                profile_values[field].setdefault(day_hour, []).append(float(b[field]))
            degree = max(0.0, number(w, "Outdoor Drybulb Temperature (C)") - float(b["Temperature Set Point (C)"]))
            cooling_degree += degree
            cooling_total += float(b["Cooling Load (kWh)"])
            dhw_total += float(b["DHW Heating (kWh)"])
            occupied_total += float(b["Occupant Count (people)"])

    profiles = {
        field: {key: sum(values) / len(values) for key, values in values_by_time.items()}
        for field, values_by_time in profile_values.items()
    }
    cooling_slope = cooling_total / max(cooling_degree, 1.0)
    # The 2023 local set has no heating season; this is an explicit proxy coefficient.
    heating_slope = 0.75 * cooling_slope
    average_dhw_per_occupant = dhw_total / max(occupied_total, 1.0)
    return profiles["Occupant Count (people)"], profiles["Temperature Set Point (C)"], profiles["DHW Heating (kWh)"], cooling_slope, heating_slope, average_dhw_per_occupant


def main() -> None:
    if OUTPUT.exists():
        marker = OUTPUT / "DATASET_README.json"
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")).get("name") != OUTPUT.name:
            raise SystemExit(f"Refusing to overwrite a dataset not created by this script: {OUTPUT}")

    _, base_weather = read_csv(BASE_2022 / "weather.csv")
    _, donor_weather = read_csv(DONOR_2023 / "weather.csv")
    profiles = series_profiles(donor_weather)
    occupancy_profile, setpoint_profile, dhw_profile, cooling_slope, heating_slope, dhw_per_occupant = profiles

    donor_schema = json.loads((DONOR_2023 / "schema.json").read_text(encoding="utf-8"))
    source_schema = json.loads((RAW_2022 / "schema.json").read_text(encoding="utf-8"))
    shutil.copytree(DONOR_2023, OUTPUT, dirs_exist_ok=True)

    # Convert the 2022 weather and tariff series to the physical 2023 CSV headers.
    weather_headers = list(WEATHER_HEADERS.values()) + [
        f"{h} {label}" for label in [
            "Outdoor Drybulb Temperature (C)", "Outdoor Relative Humidity (%)",
            "Diffuse Solar Radiation (W/m2)", "Direct Solar Radiation (W/m2)",
        ] for h in HORIZONS
    ]
    weather_rows: list[dict[str, object]] = []
    for t, row in enumerate(base_weather):
        out: dict[str, object] = {WEATHER_HEADERS[k]: row[k] for k in WEATHER_HEADERS}
        for key, label in WEATHER_HEADERS.items():
            actual = number(row, key)
            # Persistence is a causal baseline; the 2022 source forecast columns expose future values.
            for horizon in HORIZONS:
                out[f"{horizon} {label}"] = actual
        weather_rows.append(out)
    write_csv(OUTPUT / "weather.csv", weather_headers, weather_rows)

    _, source_prices = read_csv(RAW_2022 / "pricing.csv")
    pricing_names = [
        "Electricity Pricing [$/kWh]",
        "6h Prediction Electricity Pricing [$/kWh]",
        "12h Prediction Electricity Pricing [$/kWh]",
        "24h Prediction Electricity Pricing [$/kWh]",
    ]
    write_csv(OUTPUT / "pricing.csv", pricing_names, [
        {pricing_names[0]: number(r, "electricity_pricing"), pricing_names[1]: number(r, "electricity_pricing"),
         pricing_names[2]: number(r, "electricity_pricing"), pricing_names[3]: number(r, "electricity_pricing")}
        for r in source_prices
    ])
    _, carbon = read_csv(RAW_2022 / "carbon_intensity.csv")
    write_csv(OUTPUT / "carbon_intensity.csv", ["kg_CO2/kWh"], [{"kg_CO2/kWh": number(r, "carbon_intensity")} for r in carbon])

    # Fit simple day-type/hour profiles from the 2023 local sample and use 2022 weather for annual load shape.
    for building_id in range(1, 18):
        _, base_rows = read_csv(BASE_2022 / f"Building_{building_id}.csv")
        _, thermal_rows = read_csv(THERMAL_2022 / f"Building_{building_id}.csv")
        _, source_rows = read_csv(RAW_2022 / f"Building_{building_id}.csv")
        donor_id = (building_id - 1) % 3 + 1
        _, donor_rows = read_csv(DONOR_2023 / f"Building_{donor_id}.csv")
        donor_equipment_mean = sum(float(r["Equipment Electric Power (kWh)"]) for r in donor_rows) / len(donor_rows)
        source_load_mean = sum(number(r, "non_shiftable_load") for r in source_rows) / len(source_rows)
        size_scale = min(1.8, max(0.7, math.sqrt(source_load_mean / max(donor_equipment_mean, 0.1))))
        rows: list[dict[str, object]] = []

        for base, thermal, w in zip(base_rows, thermal_rows, base_weather):
            day_hour = (int(float(base["day_type"])), int(float(base["hour"])))
            occupants = occupancy_profile.get(day_hour, 0.0)
            schedule_sp = setpoint_profile.get(day_hour, 24.0)
            tin = number(thermal, "indoor_dry_bulb_temperature", 22.0)
            heat_sp = 20.0
            mode = int(float(thermal["HVAC Mode (Off/Cooling/Heating)"]))
            setpoint = heat_sp if mode == 2 else schedule_sp
            outdoor = number(w, "outdoor_dry_bulb_temperature")
            cooling_load = min(14.0, max(0.0, cooling_slope * max(0.0, outdoor - schedule_sp) * size_scale))
            heating_load = min(10.0, max(0.0, heating_slope * max(0.0, heat_sp - outdoor) * size_scale))
            dhw_load = max(0.0, dhw_profile.get(day_hour, 0.0) * size_scale)
            row: dict[str, object] = {}
            for old, new in BUILDING_HEADERS.items():
                if old == "month": value = base["month"]
                elif old == "hour": value = base["hour"]
                elif old == "day_type": value = base["day_type"]
                elif old == "daylight_savings_status": value = base["daylight_savings_status"]
                elif old == "indoor_dry_bulb_temperature": value = f"{tin:.6f}"
                elif old == "average_unmet_cooling_setpoint_difference": value = f"{max(0.0, tin - schedule_sp):.6f}"
                elif old == "indoor_relative_humidity": value = ""
                elif old == "non_shiftable_load": value = base["non_shiftable_load"]
                elif old == "dhw_demand": value = f"{dhw_load:.6f}"
                elif old == "cooling_demand": value = f"{cooling_load:.6f}"
                elif old == "heating_demand": value = f"{heating_load:.6f}"
                elif old == "solar_generation": value = base["solar_generation"]
                elif old == "occupant_count": value = f"{occupants:.6f}"
                elif old == "indoor_dry_bulb_temperature_set_point": value = f"{setpoint:.6f}"
                else: value = mode
                row[new] = value
            rows.append(row)
        write_csv(OUTPUT / f"Building_{building_id}.csv", list(BUILDING_HEADERS.values()), rows)
        shutil.copy2(DONOR_2023 / f"Building_{donor_id}.pth", OUTPUT / f"Building_{building_id}.pth")

    # Expand the 2023 building template to all 17 source buildings, preserving 2022 battery/PV sizing.
    schema = copy.deepcopy(donor_schema)
    schema["simulation_end_time_step"] = 8759
    schema["random_seed"] = 2022
    schema["observations"]["heating_demand"]["active"] = True
    schema["actions"]["heating_device"]["active"] = True
    buildings = {}
    for i in range(1, 18):
        donor_id = (i - 1) % 3 + 1
        building = copy.deepcopy(donor_schema["buildings"][f"Building_{donor_id}"])
        building["energy_simulation"] = f"Building_{i}.csv"
        building["type"] = "citylearn.building.LSTMDynamicsBuilding"
        building["electrical_storage"] = copy.deepcopy(source_schema["buildings"][f"Building_{(i - 1) % 17 + 1}"]["electrical_storage"])
        building["pv"] = copy.deepcopy(source_schema["buildings"][f"Building_{(i - 1) % 17 + 1}"]["pv"])
        building["dynamics"]["cooling"]["attributes"]["filename"] = f"Building_{i}.pth"
        building["dynamics"]["heating"]["attributes"]["filename"] = f"Building_{i}.pth"
        building["power_outage"]["stochastic_power_outage_model"]["attributes"]["random_seed"] = 73055 + i
        # The 2023 HeatPump template is used for both modes; parameters are donor assumptions.
        building["heating_device"] = copy.deepcopy(building["cooling_device"])
        buildings[f"Building_{i}"] = building
    schema["buildings"] = buildings
    (OUTPUT / "schema.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

    provenance = {
        "name": OUTPUT.name,
        "builder": Path(__file__).name,
        "purpose": "2023 workflow-shaped research dataset derived from CityLearn 2022 full-year data",
        "source_2022": RAW_2022.name,
        "2023_template": DONOR_2023.name,
        "buildings": 17,
        "time_steps": 8760,
        "synthetic_or_transferred_components": {
            "occupancy_and_setpoints": "mean day_type x hour profiles from 2023 local buildings 1-3",
            "indoor_temperature_and_hvac_mode": "medium thermal proxy scenario; uncalibrated 1R1C-style model",
            "cooling_demand": "2023 donor aggregate cooling kWh per outdoor-temperature degree above donor setpoint, scaled by source non-shiftable load",
            "heating_demand": "0.75 times cooling degree-load slope below assumed 20 C heating setpoint; proxy because 2023 local sample has no heating season",
            "dhw_demand": "2023 day_type x hour mean profile scaled by source load size",
            "dynamic_models": "2023 LSTM weights cyclically assigned to 17 buildings; transferred weights are not building-calibrated",
            "hvac_and_dhw_devices": "2023 local equipment templates copied cyclically; 2022 battery and PV sizing retained",
            "power_outage": "2023 SAIFI/CAIDI template with new deterministic per-building seeds; not location-validated",
            "weather_and_tariff_forecasts": "causal persistence baseline; source 2022 forecast columns were excluded because they equal future realized values",
        },
        "validation": "CSV lengths, schema references, model-file references, and value ranges checked. CityLearn runtime loading not performed because CityLearn is not installed in the current Python environment.",
        "limitations": [
            "This is a synthetic research dataset, not a reconstruction of measured 2022 thermal behavior.",
            "2023 LSTM weights and device parameters are transferred from only three June-period donor buildings; behavior may be out of distribution.",
            "Heating and DHW demand are assumed proxies; source 2022 columns are zero.",
            "Comfort and outage results must be interpreted as sensitivity experiments, not validated benchmark results.",
        ],
    }
    (OUTPUT / "DATASET_README.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    fill_indoor_humidity(OUTPUT)
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
