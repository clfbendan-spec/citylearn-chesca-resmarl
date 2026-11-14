"""Create a CityLearn 2.x field-name copy of the 2022 research dataset for CHESCA."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "citylearn_challenge_2022_2023flow_research"
OUTPUT = HERE / "citylearn_challenge_2022_2023flow_research_chesca_eval_v6"

BUILDING_COLUMNS = {
    "Month": "month",
    "Hour": "hour",
    "Day Type": "day_type",
    "Daylight Savings Status": "daylight_savings_status",
    "Indoor Temperature (C)": "indoor_dry_bulb_temperature",
    "Average Unmet Cooling Setpoint Difference (C)": "average_unmet_cooling_setpoint_difference",
    "Indoor Relative Humidity (%)": "indoor_relative_humidity",
    "Equipment Electric Power (kWh)": "non_shiftable_load",
    "DHW Heating (kWh)": "dhw_demand",
    "Cooling Load (kWh)": "cooling_demand",
    "Heating Load (kWh)": "heating_demand",
    "Solar Generation (W/kW)": "solar_generation",
    "Occupant Count (people)": "occupant_count",
    "HVAC Mode (Off/Cooling/Heating)": "hvac_mode",
}
WEATHER_COLUMNS = {
    "Outdoor Drybulb Temperature (C)": "outdoor_dry_bulb_temperature",
    "Outdoor Relative Humidity (%)": "outdoor_relative_humidity",
    "Diffuse Solar Radiation (W/m2)": "diffuse_solar_irradiance",
    "Direct Solar Radiation (W/m2)": "direct_solar_irradiance",
}
PRICING_COLUMNS = {
    "Electricity Pricing [$/kWh]": "electricity_pricing",
    "6h Prediction Electricity Pricing [$/kWh]": "electricity_pricing_predicted_1",
    "12h Prediction Electricity Pricing [$/kWh]": "electricity_pricing_predicted_2",
    "24h Prediction Electricity Pricing [$/kWh]": "electricity_pricing_predicted_3",
}


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def convert_columns(path: Path, mapping: dict[str, str]) -> None:
    headers, rows = read_rows(path)
    missing = set(mapping) - set(headers)
    if missing:
        raise ValueError(f"{path.name} is missing source columns: {sorted(missing)}")
    output_headers = [mapping.get(column, column) for column in headers]
    write_rows(path, output_headers, [{mapping.get(k, k): v for k, v in row.items()} for row in rows])


def main() -> None:
    if not SOURCE.is_dir():
        raise SystemExit(f"Missing source research dataset: {SOURCE}")
    if OUTPUT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {OUTPUT}")
    shutil.copytree(SOURCE, OUTPUT)

    for i in range(1, 18):
        path = OUTPUT / f"Building_{i}.csv"
        headers, rows = read_rows(path)
        missing = set(BUILDING_COLUMNS) - set(headers)
        if missing:
            raise ValueError(f"{path.name} is missing source columns: {sorted(missing)}")
        output_headers: list[str] = []
        output_rows: list[dict[str, object]] = []
        for column in headers:
            if column == "Temperature Set Point (C)":
                output_headers.extend([
                    "indoor_dry_bulb_temperature_cooling_set_point",
                    "indoor_dry_bulb_temperature_heating_set_point",
                ])
            else:
                output_headers.append(BUILDING_COLUMNS.get(column, column))
        for row in rows:
            converted = {BUILDING_COLUMNS.get(k, k): v for k, v in row.items()
                         if k != "Temperature Set Point (C)"}
            setpoint = row["Temperature Set Point (C)"]
            mode = int(float(row["HVAC Mode (Off/Cooling/Heating)"]))
            converted["indoor_dry_bulb_temperature_cooling_set_point"] = setpoint if mode != 2 else "24.0"
            converted["indoor_dry_bulb_temperature_heating_set_point"] = setpoint if mode == 2 else "20.0"
            output_rows.append(converted)
        write_rows(path, output_headers, output_rows)

    headers, rows = read_rows(OUTPUT / "weather.csv")
    weather_map: dict[str, str] = dict(WEATHER_COLUMNS)
    for old, base in WEATHER_COLUMNS.items():
        for index, horizon in enumerate(("6h", "12h", "24h"), start=1):
            old_forecast = f"{horizon} {old}"
            if old_forecast in headers:
                weather_map[old_forecast] = f"{base}_predicted_{index}"
    convert_columns(OUTPUT / "weather.csv", weather_map)
    convert_columns(OUTPUT / "pricing.csv", PRICING_COLUMNS)
    convert_columns(OUTPUT / "carbon_intensity.csv", {"kg_CO2/kWh": "carbon_intensity"})

    schema_path = OUTPUT / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["observations"]["heating_demand"]["active"] = False
    schema["actions"]["heating_device"]["active"] = False
    observation_aliases = {
        "predicted_6h": "predicted_1",
        "predicted_12h": "predicted_2",
        "predicted_24h": "predicted_3",
        "indoor_dry_bulb_temperature_set_point": "indoor_dry_bulb_temperature_cooling_set_point",
        "indoor_dry_bulb_temperature_delta": "indoor_dry_bulb_temperature_cooling_delta",
        "cooling_device_cop": "cooling_device_efficiency",
        "heating_device_cop": "heating_device_efficiency",
        "dhw_device_cop": "dhw_device_efficiency",
    }
    observations = {}
    for name, config in schema["observations"].items():
        converted_name = name
        for old, new in observation_aliases.items():
            converted_name = converted_name.replace(old, new)
        observations[converted_name] = config
    schema["observations"] = observations
    schema["root_directory"] = str(OUTPUT)
    for building in schema["buildings"].values():
        heating_device = building.get("heating_device")
        if heating_device and heating_device.get("attributes", {}).get("nominal_power") is not None:
            # Heating is not a CHESCA action in the 2023 interface, but CityLearn still serves
            # the annual synthetic winter load; leave headroom to avoid demand-limit failures.
            heating_device["attributes"]["nominal_power"] *= 2.0
        dynamics = building.get("dynamics")
        if isinstance(dynamics, dict) and "cooling" in dynamics:
            # CityLearn 2.3 uses one dynamics model per building; 2.5 schemas split heating/cooling.
            building["dynamics"] = dynamics["cooling"]
        attributes = building.get("dynamics", {}).get("attributes", {})
        attributes["input_observation_names"] = [
            name.replace(
                "indoor_dry_bulb_temperature_set_point",
                "indoor_dry_bulb_temperature_cooling_set_point",
            )
            for name in attributes.get("input_observation_names", [])
        ]
    if "indoor_dry_bulb_temperature_set_point" in schema["observations"]:
        schema["observations"]["indoor_dry_bulb_temperature_cooling_set_point"] = schema["observations"].pop(
            "indoor_dry_bulb_temperature_set_point"
        )
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

    readme_path = OUTPUT / "DATASET_README.json"
    readme = json.loads(readme_path.read_text(encoding="utf-8"))
    readme["name"] = OUTPUT.name
    readme["chesca_runtime_compatibility"] = {
        "purpose": "CityLearn 2.x / CHESCA runtime-compatible field names for a full-year 2022 research evaluation",
        "source_dataset": SOURCE.name,
        "field_mapping": "2023 display labels are converted to CityLearn EnergySimulation, Weather, Pricing, and CarbonIntensity constructor names; 6h/12h/24h forecast columns map to predicted_1/2/3 slots.",
        "heating": "Heating observation and action are disabled to match the CHESCA 2023 three-action interface; synthetic heating demand remains in the energy series and is not directly controllable by CHESCA.",
        "indoor_humidity": "Retained as a synthetic ResStock-transfer proxy and remains inactive in the observation schema.",
        "limitations": "This is an annual research-domain evaluation, not an official 2023 competition score. The transferred behavior, synthetic loads, outage profile, and persistence forecasts are not validated 2022 measurements.",
    }
    readme_path.write_text(json.dumps(readme, indent=2) + "\n", encoding="utf-8")
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
