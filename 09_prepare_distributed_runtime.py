#!/usr/bin/env python3
"""Generate distributed runtime TOML without modifying validated inputs."""

import argparse
import csv
import json
import re
import tomllib
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
from netCDF4 import Dataset, num2date


def replace_keys(text, values):
    """Replace existing TOML keys in their exact sections."""
    section = None
    used = set()
    output = []

    for line in text.splitlines(keepends=True):
        match = re.match(r"^\s*(\[\[?.*?\]\]?)\s*$", line)
        if match:
            section = match.group(1).strip("[]")
            output.append(line)
            continue

        match = re.match(
            r"^(\s*)([A-Za-z_][A-Za-z_0-9]*)\s*=",
            line
        )

        if match:
            key = (section, match.group(2))
            if key in values:
                new_value = values[key]
                output.append(
                    f"{match.group(1)}{key[1]} = "
                    f"{json.dumps(new_value)}\n"
                )
                used.add(key)
                continue

        output.append(line)

    missing = set(values) - used
    if missing:
        raise ValueError(
            f"Required template keys missing: {sorted(missing)}"
        )

    return "".join(output)


def get_dates(path):
    with Dataset(path) as ds:
        t = ds.variables["time"]
        if len(t) < 2:
            raise ValueError("Forcing time axis too short")

        values = [t[0], t[-1]]
        dates = num2date(
            values,
            t.units,
            calendar=getattr(t, "calendar", "standard")
        )

        return dates[0], dates[1], len(t)


def get_obs_dates(path):
    with Dataset(path) as ds:
        t = ds.variables["time"]

        dates = num2date(
            [t[0], t[-1]],
            t.units,
            calendar=getattr(t, "calendar", "standard")
        )

        if "q_obs" not in ds.variables:
            raise ValueError(f"Missing q_obs: {path}")

        return dates[0], dates[1]


def time_string(d):
    return (
        f"{d.year:04d}-{d.month:02d}-{d.day:02d} "
        f"{d.hour:02d}:{d.minute:02d}"
    )


def date_string(d):
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--inventory", required=True)
    p.add_argument("--converted-root", required=True)
    p.add_argument("--output-root", required=True)
    p.add_argument("--template", required=True)
    p.add_argument("--basin", action="append", required=True)
    args = p.parse_args()

    with open(args.config, "rb") as f:
        config = tomllib.load(f)

    if config["selection"]["model_type"] != "distributed":
        raise ValueError("Expected distributed configuration")

    with open(args.inventory, newline="") as f:
        inventory = {
            r["basin"]: r for r in csv.DictReader(f)
        }

    converted_root = Path(args.converted_root).resolve()
    output_root = Path(args.output_root).resolve()
    template = Path(args.template).read_text()

    if output_root == converted_root:
        raise ValueError(
            "Runtime config output must be separate from model inputs"
        )

    for basin in args.basin:
        if basin not in inventory:
            raise ValueError(f"Unknown basin: {basin}")

        if inventory[basin]["status"] != "READY":
            raise ValueError(f"Basin not READY: {basin}")

        domain = converted_root / "domain" / basin
        forcing_list = domain / "summa_inputs/forcingFileList.txt"

        names = [
            line.strip()
            for line in forcing_list.read_text().splitlines()
            if line.strip()
            and not line.lstrip().startswith("#")
        ]

        if not names:
            raise ValueError("Empty forcing file list")

        # Check every listed file and obtain overall time coverage.
        starts = []
        ends = []
        total_steps = 0

        for name in names:
            if Path(name).name != name:
                raise ValueError(f"Unsafe forcing filename: {name}")

            path = domain / "summa_forcing" / name
            if not path.is_file():
                raise FileNotFoundError(path)

            start, end, count = get_dates(path)
            starts.append(start)
            ends.append(end)
            total_steps += count

        forcing_start = min(starts)
        forcing_end = max(ends)

        if len(names) > 1:
            print(
                f"WARNING: {basin}: verify no gaps or overlaps "
                "between forcing files"
            )

        obs = (
            converted_root / "observations/obs-daily"
            / f"{basin}_daily_flow_observations.nc"
        )

        if not obs.is_file():
            raise FileNotFoundError(obs)

        obs_start, obs_end = get_obs_dates(obs)

        # Use the full available intersection.
        calibration_start = max(
            forcing_start, obs_start
        )
        calibration_end = min(
            forcing_end, obs_end
        )

        if calibration_start > calibration_end:
            raise ValueError(
                f"No observation/forcing overlap: {basin}"
            )

        # SUMMA resolves basin settings relative to settings_path.
        # Use "/" as the root and root-relative filenames.
        rel = lambda x: str(x.resolve()).lstrip("/")

        inputs = domain / "summa_inputs"

        settings_files = {
            "attributes": "attributes.nc",
            "forcing_list": "forcingFileList.txt",
            "trial_params": "trialParams.nc",
            "decisions": "modelDecisions.txt",
            "output_control": "outputControl.txt",
            "local_parameters": "localParamInfo.txt",
            "basin_parameters": "basinParamInfo.txt",
            "vegetation_table": "TBL_VEGPARM.TBL",
            "soil_table": "TBL_SOILPARM.TBL",
            "general_table": "TBL_GENPARM.TBL",
            "noahmp_table": "TBL_MPTABLE.TBL",
        }

        for name in settings_files.values():
            if not (inputs / name).is_file():
                raise FileNotFoundError(inputs / name)

        if not (domain / "summa_state/coldState.nc").is_file():
            raise FileNotFoundError("Missing coldState.nc")

        if not (domain / "mizuroute_inputs/topology.nc").is_file():
            raise FileNotFoundError("Missing topology.nc")

        if not (domain / "mizuroute_inputs/mizuroute.param").is_file():
            raise FileNotFoundError("Missing mizuroute.param")

        values = {
            ("simulation", "case_name"): basin,
            ("simulation", "basin_dir"): rel(domain),
            ("simulation", "start_time"): time_string(forcing_start),
            ("simulation", "end_time"): time_string(forcing_end),
            ("simulation", "time_zone"): "localTime",

            ("summa_files", "settings_path"): "/",
            ("summa_files", "state_path"):
                str(domain / "summa_state") + "/",
            ("summa_files", "forcing_path"):
                str(domain / "summa_forcing") + "/",
            ("summa_files", "output_path"):
                str(domain / "work") + "/",
            ("summa_files", "init_condition"): "coldState.nc",

            ("mizuRoute", "namelist_path"):
                str(domain / "mizuroute_inputs") + "/",
            ("mizuRoute", "namelist_file"): "mizuroute.param",

            ("hydrofabric", "hfabric_path"):
                str(domain / "mizuroute_inputs") + "/",
            ("hydrofabric", "hfabric_file"): "topology.nc",

            ("calibration", "start_date"):
                date_string(calibration_start),
            ("calibration", "end_date"):
                date_string(calibration_end),

            ("calibration.target", "obs_path"):
                str(obs.parent) + "/",
            ("calibration.target", "obs_file"): obs.name,
        }

        for key, filename in settings_files.items():
            values[("summa_files", key)] = rel(
                inputs / filename
            )

        generated = replace_keys(template, values)

        # Ensure the result is valid TOML and retains direct routing.
        parsed = tomllib.loads(generated)

        if "hydrofabric" not in parsed:
            raise ValueError("Missing hydrofabric section")

        if "remapping" in parsed:
            raise ValueError("Unexpected lumped remapping section")

        outdir = output_root / "domain" / basin
        outdir.mkdir(parents=True, exist_ok=True)
        output = outdir / "summa_config.toml"

        if output.exists():
            raise FileExistsError(
                f"Runtime configuration exists: {output}"
            )

        output.write_text(generated)

        print("\n" + "=" * 65)
        print("Basin:", basin)
        print("Forcing files:", len(names))
        print("Forcing timesteps:", total_steps)
        print("Simulation:", time_string(forcing_start),
              "to", time_string(forcing_end))
        print("Daily observations:", date_string(obs_start),
              "to", date_string(obs_end))
        print("Calibration:", date_string(calibration_start),
              "to", date_string(calibration_end))
        print("Direct hydrofabric routing: YES")
        print("Config:", output)
        print("STEP 09A: PASS (configuration generation)")


if __name__ == "__main__":
    main()
