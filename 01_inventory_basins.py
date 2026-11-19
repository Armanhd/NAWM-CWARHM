#!/usr/bin/env python3
"""
01_inventory_basins.py

Read-only inventory of CAMELS-SPAT lumped NAWM-CWARHM basins.

- Supports headwater, meso_scale, macro_scale.
- Uses a TOML configuration.
- Checks required SUMMA/mizuRoute inputs.
- Checks the LST forcing file list and file existence.
- Detects duplicate basin IDs.
- Writes one consolidated CSV for the conversion workflow.

No source datasets are modified.
"""

from __future__ import annotations

import argparse
import csv
import tomllib
from collections import Counter, defaultdict
from pathlib import Path


REQUIRED = {
    "topology": "settings/mizuRoute/topology.nc",
    "attributes": "lumped/settings/SUMMA/attributes.nc",
    "cold_state": "lumped/settings/SUMMA/coldState.nc",
    "trial_params": "lumped/settings/SUMMA/trialParams.nc",
    "forcing_list": "lumped/settings/SUMMA/forcingFileList_LST.txt",
}

FORCING_DIR = Path("lumped/forcing/6_SUMMA_input_LST")

FIELDNAMES = [
    "index",
    "group",
    "basin",
    "source",
    "forcing_files",
    "obs_daily",
    "obs_hourly",
    "missing_forcing",
    "problems",
    "status",
]


def check_forcing(source: Path):
    path = source / REQUIRED["forcing_list"]
    if not path.is_file():
        return 0, 0, ["missing forcing_list"]

    problems = []
    names = [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    if not names:
        problems.append("empty forcing list")

    if len(names) != len(set(names)):
        problems.append("duplicate forcing names")

    missing = 0

    for name in names:
        if (
            Path(name).name != name
            or name in (".", "..")
            or "/" in name
            or "\\" in name
        ):
            problems.append(f"unsafe forcing filename: {name}")
            continue

        if not (source / FORCING_DIR / name).is_file():
            missing += 1

    if missing:
        problems.append(f"{missing} missing forcing files")

    return len(names), missing, problems


def inspect_basin(group: str, source: Path):
    basin = source.name.removeprefix("domain_")
    problems = []

    for key, relative in REQUIRED.items():
        if not (source / relative).is_file():
            problems.append(f"missing {key}")

    forcing_count, missing_count, forcing_problems = check_forcing(source)

    for problem in forcing_problems:
        if problem not in problems:
            problems.append(problem)

    daily = source / "observations/obs-daily"
    hourly = source / "observations/obs-hourly"

    daily_count = sum(1 for x in daily.glob("*.nc") if x.is_file())
    hourly_count = sum(1 for x in hourly.glob("*.nc") if x.is_file())

    if not daily_count:
        problems.append("no daily observations")

    return {
        "group": group,
        "basin": basin,
        "source": str(source.resolve()),
        "forcing_files": forcing_count,
        "obs_daily": daily_count,
        "obs_hourly": hourly_count,
        "missing_forcing": missing_count,
        "_problems": problems,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent
        / "config/camels_spat_arc.toml",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )

    args = parser.parse_args()

    with args.config.open("rb") as file:
        config = tomllib.load(file)

    source_root = Path(config["paths"]["source_root"])
    groups = config["selection"]["scales"]

    if config["selection"]["model_type"] != "lumped":
        raise ValueError("This inventory supports only lumped SUMMA")

    if config["selection"]["duplicate_basin_policy"] != "error":
        raise ValueError("Only duplicate_basin_policy='error' is supported")

    output = (
        args.output
        if args.output is not None
        else Path(__file__).resolve().parent
        / "reports/camels_spat_lumped_inventory.csv"
    )

    if not source_root.is_dir():
        raise FileNotFoundError(source_root)

    rows = []

    for group in groups:
        group_root = source_root / group

        if not group_root.is_dir():
            raise FileNotFoundError(
                f"Missing source group directory: {group_root}"
            )

        basins = sorted(
            path
            for path in group_root.glob("domain_*")
            if path.is_dir()
        )

        print(f"{group}: {len(basins)} basin directories")

        for basin_path in basins:
            rows.append(inspect_basin(group, basin_path))

    counts = Counter(row["basin"] for row in rows)
    duplicates = {
        basin for basin, count in counts.items()
        if count > 1
    }

    for row in rows:
        if row["basin"] in duplicates:
            row["_problems"].append("DUPLICATE_BASIN_ID")

        row["problems"] = "; ".join(row.pop("_problems"))
        row["status"] = "REVIEW" if row["problems"] else "READY"

    rows.sort(key=lambda row: (row["basin"], row["group"]))

    for index, row in enumerate(rows):
        row["index"] = index

    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    status = Counter(row["status"] for row in rows)
    problem_counts = Counter()

    for row in rows:
        if row["problems"]:
            problem_counts.update(row["problems"].split("; "))

    print("\n========== INVENTORY SUMMARY ==========")
    print("Total entries:", len(rows))
    print("Unique basin IDs:", len(counts))
    print("READY:", status["READY"])
    print("REVIEW:", status["REVIEW"])
    print("Duplicate basin IDs:", len(duplicates))

    print("\n========== REVIEW REASONS ==========")
    for problem, count in problem_counts.most_common(15):
        print(f"{count:6d}  {problem}")

    print("\nInventory:", output)
    print("No basin files were modified.")


if __name__ == "__main__":
    main()
