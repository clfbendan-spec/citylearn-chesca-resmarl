"""Build a clearly labeled 2022-derived, 2023-shaped CityLearn dataset."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "citylearn_challenge_2022_phase_all"
DONOR = HERE / "citylearn_challenge_2023_phase_2_local_evaluation"
OUTPUT = HERE / "citylearn_challenge_2022_phase_all_2023_compatible"

FORECAST_HORIZONS = {"1": "6h", "2": "12h", "3": "24h"}
BUILDING_FIELDS = [
    ("occupant_count", "Occupant Count (people)"),
    ("indoor_dry_bulb_temperature_cooling_set_point", "Cooling Set Point (C)"),
    ("indoor_dry_bulb_temperature_heating_set_point", "Heating Set Point (C)"),
    ("hvac_mode", "HVAC Mode (Off/Cooling/Heating)"),
]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def rename_forecasts(headers: list[str], rows: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
    mapping = {}
    for name in headers:
        for suffix, horizon in FORECAST_HORIZONS.items():
            ending = f"_predicted_{suffix}"
            if name.endswith(ending):
                mapping[name] = name[: -len(ending)] + f"_predicted_{horizon}"
    return [mapping.get(h, h) for h in headers], [
        {mapping.get(k, k): v for k, v in row.items()} for row in rows
    ]


def profile_for(field: str) -> dict[tuple[int, int], float]:
    """Average the three 2023 local buildings by day type and hour."""
    sums: dict[tuple[int, int], float] = {}
    counts: dict[tuple[int, int], int] = {}
    for building in range(1, 4):
        _, rows = read_csv(DONOR / f"Building_{building}.csv")
        for row in rows:
            key = (int(float(row["Day Type"])), int(float(row["Hour"])))
            value = float(row[field])
            sums[key] = sums.get(key, 0.0) + value
            counts[key] = counts.get(key, 0) + 1
    return {key: value / counts[key] for key, value in sums.items()}


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit(f"Refusing to overwrite existing dataset: {OUTPUT}")
    occupancy = profile_for("Occupant Count (people)")
    cooling = profile_for("Temperature Set Point (C)")
    shutil.copytree(SOURCE, OUTPUT)

    for filename in ("weather.csv", "pricing.csv"):
        headers, rows = read_csv(OUTPUT / filename)
        headers, rows = rename_forecasts(headers, rows)
        if filename == "weather.csv":
            headers = [h.replace("outdoor_dry_bulb_temperature", "outdoor_dry_bulb_temperature") for h in headers]
        write_csv(OUTPUT / filename, headers, rows)

    for path in sorted(OUTPUT.glob("Building_*.csv")):
        headers, rows = read_csv(path)
        extra = [label for _, label in BUILDING_FIELDS]
        for row in rows:
            day_type, hour = int(float(row["day_type"])), int(float(row["hour"]))
            row["Occupant Count (people)"] = f"{occupancy.get((day_type, hour), 0.0):.6f}"
            # Cooling schedule from the 2023 local evaluation profiles; heating is a fixed proxy.
            row["Cooling Set Point (C)"] = f"{cooling.get((day_type, hour), 24.0):.6f}"
            row["Heating Set Point (C)"] = "20.000000"
            row["HVAC Mode (Off/Cooling/Heating)"] = "0"
        write_csv(path, headers + extra, rows)

    schema_path = OUTPUT / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    renamed = {}
    for key, value in schema["observations"].items():
        for old, new in FORECAST_HORIZONS.items():
            if key.endswith(f"_predicted_{old}"):
                key = key[: -len(f"_predicted_{old}")] + f"_predicted_{new}"
                break
        renamed[key] = value
    schema["observations"] = renamed
    schema["observations"].update({
        "occupant_count": {"active": False, "shared_in_central_agent": False},
        "indoor_dry_bulb_temperature_cooling_set_point": {"active": False, "shared_in_central_agent": False},
        "indoor_dry_bulb_temperature_heating_set_point": {"active": False, "shared_in_central_agent": False},
        "hvac_mode": {"active": False, "shared_in_central_agent": False},
    })
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

    provenance = {
        "name": OUTPUT.name,
        "source": SOURCE.name,
        "format_reference": DONOR.name,
        "time_steps": 8760,
        "buildings": 17,
        "forecast_mapping": {"_predicted_1": "_predicted_6h", "_predicted_2": "_predicted_12h", "_predicted_3": "_predicted_24h"},
        "synthetic_fields": {
            "occupant_count": "mean day_type x hour profile from 2023 local evaluation Buildings 1-3; proxy only",
            "cooling_set_point": "2023 local evaluation Temperature Set Point mean profile; proxy only",
            "heating_set_point": "constant 20 C research assumption; proxy only",
            "hvac_mode": "constant off (0); not a modeled response",
        },
        "limitations": [
            "2022 indoor temperature and humidity remain missing; no indoor temperature was fabricated.",
            "All synthetic occupant and set-point fields are inactive in schema and must not be treated as 2022 observations.",
            "HVAC actions and thermal dynamics remain disabled; this is not functionally equivalent to the 2023 HVAC challenge.",
            "2022 predicted_1/2/3 forecast columns were renamed to 6h/12h/24h; inspection showed they exactly match future realized values and therefore leak future information.",
        ],
    }
    (OUTPUT / "DATASET_README.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()
