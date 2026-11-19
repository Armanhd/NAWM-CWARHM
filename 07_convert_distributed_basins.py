#!/usr/bin/env python3
"""
Step 07: Complete a distributed SUMMA calibration test basin.

Inputs:
  - Step 05 distributed inventory
  - Step 06 prepared SUMMA/routing inputs
  - Original CWARHM distributed LST forcing
  - Original basin observations
  - Reference and distributed common settings

Safety:
  - Never changes original CWARHM data
  - Never changes Step 06 output
  - Refuses existing destination basins
  - Refuses production destination
  - Preserves forcing data and HRU order
  - Does not create lumped_to_hru.nc
"""
import argparse
import csv
import shutil
import tempfile
import tomllib
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def get_ids(path, name="hruId"):
    with Dataset(path) as ds:
        if name not in ds.variables:
            raise ValueError(f"Missing {name}: {path}")
        a = np.ma.asarray(ds.variables[name][:])
        if np.ma.getmaskarray(a).any():
            raise ValueError(f"Masked IDs: {path}")
        values = np.asarray(a).ravel()
        if not np.all(np.isfinite(values)):
            raise ValueError(f"Non-finite IDs: {path}")
        if not np.all(values == np.floor(values)):
            raise ValueError(f"Non-integer IDs: {path}")
        return values.astype(np.int64)


def inventory_row(path, basin):
    with open(path, newline="") as f:
        rows = [
            x for x in csv.DictReader(f)
            if x["basin"] == basin
        ]
    if len(rows) != 1 or rows[0]["status"] != "READY":
        raise ValueError(f"Basin not uniquely READY: {basin}")
    return rows[0]


def forcing_names(source):
    path = source / "settings/SUMMA/forcingFileList_LST.txt"
    if not path.is_file():
        raise FileNotFoundError(path)

    names = [
        x.strip() for x in path.read_text().splitlines()
        if x.strip() and not x.lstrip().startswith("#")
    ]
    if not names or len(names) != len(set(names)):
        raise ValueError("Invalid forcing file list")

    for name in names:
        if Path(name).name != name:
            raise ValueError(f"Unsafe forcing filename: {name}")

    return names


def align_forcing(source, destination, old_ids, new_ids):
    """
    Copy NetCDF first, then change only its hruId variable.
    All other variables are left untouched.
    """
    shutil.copy2(source, destination)

    with Dataset(destination, "r+") as ds:
        if "hru" not in ds.dimensions:
            raise ValueError(f"No hru dimension: {source}")

        if len(ds.dimensions["hru"]) != len(new_ids):
            raise ValueError(f"Wrong HRU dimension: {source}")

        if "hruId" not in ds.variables:
            raise ValueError(f"No forcing hruId: {source}")

        variable = ds.variables["hruId"]
        raw = np.ma.asarray(variable[:])

        if np.ma.getmaskarray(raw).any():
            raise ValueError(f"Masked forcing IDs: {source}")

        existing = np.asarray(raw).ravel()
        if not np.array_equal(existing, old_ids):
            raise ValueError(f"Original forcing IDs mismatch: {source}")

        # Avoid float-precision loss in NetCDF HRU identifiers.
        if np.issubdtype(variable.dtype, np.integer):
            limits = np.iinfo(variable.dtype)
            if (new_ids.min() < limits.min or
                    new_ids.max() > limits.max):
                raise ValueError("New HRU IDs exceed integer dtype")
        elif np.issubdtype(variable.dtype, np.floating):
            if np.any(np.abs(new_ids) > 2**53):
                raise ValueError("HRU IDs cannot be represented exactly")
        else:
            raise ValueError(f"Unsupported forcing ID dtype: {variable.dtype}")

        variable[:] = new_ids.astype(variable.dtype)

    if not np.array_equal(get_ids(destination), new_ids):
        raise ValueError(f"Written forcing IDs incorrect: {destination}")


def copy_common_settings(source, reference, experiment, stage):
    dest = stage / "summa_inputs"

    # CENTURY reference takes priority for model parameter settings.
    # Preserve distributed read/write buffering from exp56.
    src_settings = source / "settings/SUMMA"
    ref_settings = reference / "summa_inputs"
    exp_settings = (
        experiment / "common_inputs"
        if experiment.is_dir() else None
    )

    names = (
        "localParamInfo.txt",
        "basinParamInfo.txt",
        "modelDecisions.txt",
        "TBL_SOILPARM.TBL",
        "TBL_VEGPARM.TBL",
        "TBL_GENPARM.TBL",
        "TBL_MPTABLE.TBL",
        "outputControl.txt",
    )

    for name in names:
        candidates = []

        if name == "modelDecisions.txt" and exp_settings:
            candidates.append(exp_settings / name)

        candidates.extend((
            ref_settings / name,
            src_settings / name,
        ))

        if exp_settings:
            candidates.append(exp_settings / name)

        choice = next(
            (p for p in candidates if p.is_file()), None
        )

        if choice is None:
            raise FileNotFoundError(
                f"Cannot locate required settings file: {name}"
            )

        shutil.copy2(choice, dest / name)

    # Preserve the original CWARHM file managers for comparison.
    # Their paths are NOT assumed ready for the new directory.
    for name in ("fileManager.txt", "fileManager_LST.txt"):
        path = src_settings / name
        if path.is_file():
            shutil.copy2(path, dest / name)


def copy_observations(source, stage, basin):
    """
    Locate original basin observations and stage them in
    shared daily/hourly folders. No observation values are altered.
    """
    root = source / "observations"
    if not root.is_dir():
        raise FileNotFoundError(f"Observations directory missing: {root}")

    selected = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue

        lower = str(path.relative_to(root)).lower()

        if "hourly" in lower:
            kind = "obs-hourly"
        elif "daily" in lower:
            kind = "obs-daily"
        else:
            continue

        # Only observation files for this basin.
        if basin.lower() not in path.name.lower():
            continue

        key = (kind, path.name)
        if key in selected:
            raise ValueError(f"Duplicate observation: {key}")

        selected[key] = path

    if not selected:
        raise ValueError(
            f"No basin-specific observations found under {root}"
        )

    for (kind, name), path in selected.items():
        dest = stage / "observations" / kind
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest / name)

    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--basin", required=True)
    parser.add_argument("--step06", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()

    with open(args.config, "rb") as f:
        config = tomllib.load(f)

    if config["selection"]["model_type"] != "distributed":
        raise ValueError("Expected distributed configuration")

    row = inventory_row(Path(args.inventory), args.basin)
    source = Path(row["source"])
    reference = Path(config["paths"]["reference_basin"])

    prepared = (
        Path(args.step06) / "domain" / args.basin
    )
    if not prepared.is_dir():
        raise FileNotFoundError(
            f"Run Step 06 first: {prepared}"
        )

    destination = Path(args.destination).resolve()
    production = Path(config["paths"]["output_root"]).resolve()
    if destination == production:
        raise ValueError("Step 07 test cannot write to production")

    if destination == Path(args.step06).resolve():
        raise ValueError("Step 07 and Step 06 destinations must differ")

    target = destination / "domain" / args.basin
    if target.exists():
        raise FileExistsError(f"Target exists: {target}")

    attr_source = source / "settings/SUMMA/attributes.nc"
    attr_prepared = prepared / "summa_inputs/attributes.nc"
    topology = prepared / "mizuroute_inputs/topology.nc"

    old_ids = get_ids(attr_source)
    new_ids = get_ids(attr_prepared)
    routing_ids = get_ids(topology)

    if not np.array_equal(new_ids, routing_ids):
        raise ValueError("Step 06 IDs do not match topology")

    if len(old_ids) != len(new_ids):
        raise ValueError("HRU count changed")

    names = forcing_names(source)
    force_dir = source / "forcing/6_SUMMA_input_LST"

    for name in names:
        path = force_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)

    # Use distributed experiment settings where applicable.
    experiment = (
        Path(args.config).resolve().parent.parent
        / "test_distributed/exp56_distributed"
    )

    destination.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".step07_",
        dir=destination
    ) as tmp:
        temporary = Path(tmp)
        stage = temporary / "domain" / args.basin
        stage.parent.mkdir(parents=True)

        shutil.copytree(prepared, stage)

        for relative in (
            "summa_inputs/attributes.nc",
            "summa_state/coldState.nc",
            "summa_inputs/trialParams.nc",
            "summa_inputs/trialParams.priori.nc",
            "mizuroute_inputs/topology.nc",
        ):
            if not (stage / relative).is_file():
                raise FileNotFoundError(stage / relative)

        # Add settings and original distributed forcing list.
        copy_common_settings(source, reference, experiment, stage)
        shutil.copy2(
            source / "settings/SUMMA/forcingFileList_LST.txt",
            stage / "summa_inputs/forcingFileList.txt"
        )

        out_force = stage / "summa_forcing"
        out_force.mkdir()

        for i, name in enumerate(names, 1):
            align_forcing(
                force_dir / name,
                out_force / name,
                old_ids,
                new_ids
            )
            print(
                f"Forcing {i}/{len(names)}: "
                f"{name} | IDs PASS",
                flush=True
            )

        observations = copy_observations(
            source, temporary, args.basin
        )

        # No lumped remapping for direct distributed routing.
        if list(stage.rglob("lumped_to_hru.nc")):
            raise ValueError("Unexpected lumped remapping file")

        for relative in (
            "summa_inputs/attributes.nc",
            "summa_state/coldState.nc",
            "summa_inputs/trialParams.nc",
            "summa_inputs/trialParams.priori.nc",
            "mizuroute_inputs/topology.nc",
        ):
            if not np.array_equal(
                get_ids(stage / relative), new_ids
            ):
                raise ValueError(
                    f"Final identifier mismatch: {relative}"
                )

        # Check for existing observation collisions BEFORE publication.
        obs_source = temporary / "observations"
        for path in obs_source.rglob("*"):
            if path.is_file():
                relative = path.relative_to(obs_source)
                final_path = destination / "observations" / relative
                if final_path.exists():
                    raise FileExistsError(
                        f"Existing observation: {final_path}"
                    )

        final_domain = destination / "domain"
        final_domain.mkdir(parents=True, exist_ok=True)

        stage.rename(target)

        for path in obs_source.rglob("*"):
            if path.is_file():
                relative = path.relative_to(obs_source)
                final_path = destination / "observations" / relative
                final_path.parent.mkdir(
                    parents=True, exist_ok=True
                )
                shutil.copy2(path, final_path)

    print("\n========== STEP 07 DISTRIBUTED CONVERSION ==========")
    print("Basin:", args.basin)
    print("Distributed HRUs:", len(new_ids))
    print("Forcing files:", len(names))
    print("Observation files:", len(observations))
    print("All model HRU IDs: MATCH")
    print("Original forcing values: COPIED UNCHANGED")
    print("Lumped remapping file: NOT USED")
    print("Output:", target)
    print("STEP 07: PASS (structural conversion)")


if __name__ == "__main__":
    main()
