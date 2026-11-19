#!/usr/bin/env python3
"""
02_prepare_cold_state.py

Prepare a CENTURY-compatible lumped SUMMA coldState.nc.

Default policy:
  - Copy reference coldState.nc structure and numerical values.
  - Replace hru and hruId with the source basin's lumped HRU ID.
  - Validate source attributes/cold-state HRU consistency.
  - Validate soil layering against TOML configuration.
  - Preserve original source and reference files.
  - Record per-variable provenance in a JSON report.

Designed for standalone testing and reuse by 03_convert_basins.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import tomllib
from pathlib import Path
from shutil import copy2
from uuid import uuid4

import numpy as np
from netCDF4 import Dataset


def same(a, b):
    return (
        np.shape(a) == np.shape(b)
        and bool(np.ma.allequal(np.ma.asarray(a), np.ma.asarray(b)))
    )


def prepare_cold_state(
    camels_file: Path,
    attributes_file: Path,
    reference_file: Path,
    output_file: Path,
    policy: dict,
    overwrite: bool = False,
) -> dict:

    if policy["mode"] != "century_exact":
        raise ValueError("Only century_exact is implemented")

    if policy["cold_state"] != "copy_reference_except_hru_ids":
        raise ValueError("Unsupported cold_state policy")

    for path in (camels_file, attributes_file, reference_file):
        if not path.is_file():
            raise FileNotFoundError(path)

    if output_file.exists() and not overwrite:
        raise FileExistsError(output_file)

    expected_layers = int(policy["soil_layers"])
    expected_depths = np.asarray(
        policy["soil_layer_depths_m"], dtype=np.float64
    )

    if len(expected_depths) != expected_layers:
        raise ValueError("TOML soil layer count/depth mismatch")

    with (
        Dataset(attributes_file) as attrs,
        Dataset(camels_file) as original,
        Dataset(reference_file) as ref,
    ):
        ids = np.asarray(
            attrs.variables["hruId"][:], dtype=np.int64
        ).reshape(-1)

        if len(ids) != 1 or ids[0] <= 0:
            raise ValueError("Expected one positive lumped HRU ID")

        if len(ref.dimensions["hru"]) != 1:
            raise ValueError("Reference is not a one-HRU cold state")

        original_ids = np.asarray(
            original.variables["hruId"][:], dtype=np.int64
        ).reshape(-1)

        if not np.array_equal(ids, original_ids):
            raise ValueError(
                "Source coldState and attributes HRU IDs disagree"
            )

        if not {"hru", "hruId", "nSoil", "mLayerDepth"}.issubset(
            ref.variables
        ):
            raise ValueError("Reference coldState lacks required variables")

        n_soil = int(
            np.asarray(ref.variables["nSoil"][:]).reshape(-1)[0]
        )

        depths = np.asarray(
            ref.variables["mLayerDepth"][:], dtype=np.float64
        ).reshape(-1)

        if n_soil != expected_layers:
            raise ValueError(
                f"Reference nSoil={n_soil}, expected {expected_layers}"
            )

        if not np.allclose(
            depths, expected_depths, rtol=0, atol=1e-8
        ):
            raise ValueError(
                f"Reference depths {depths.tolist()} "
                f"do not match TOML {expected_depths.tolist()}"
            )

    output_file.parent.mkdir(parents=True, exist_ok=True)

    temporary = output_file.with_name(
        f".{output_file.name}.{uuid4().hex}.tmp"
    )

    provenance = {}

    try:
        copy2(reference_file, temporary)

        with (
            Dataset(camels_file) as original,
            Dataset(reference_file) as ref,
            Dataset(temporary, "r+") as output,
        ):
            for name, ref_var in ref.variables.items():

                if name in ("hru", "hruId"):
                    output.variables[name][:] = ids
                    provenance[name] = "BASIN_HRU_ID"
                    continue

                if name not in original.variables:
                    provenance[name] = "CENTURY_MISSING_IN_SOURCE"
                    continue

                source_values = original.variables[name][:]
                reference_values = ref_var[:]

                if same(source_values, reference_values):
                    provenance[name] = "SOURCE_MATCHES_CENTURY"
                else:
                    provenance[name] = "CENTURY_REFERENCE_VALUE"

                # Output already contains the reference values.
                # Deliberately do not replace them with source values.

        # Verify output against the reference.
        with (
            Dataset(reference_file) as ref,
            Dataset(temporary) as output,
        ):
            if set(ref.dimensions) != set(output.dimensions):
                raise ValueError("Cold-state dimension mismatch")

            if set(ref.variables) != set(output.variables):
                raise ValueError("Cold-state variable mismatch")

            for name, ref_var in ref.variables.items():
                out_var = output.variables[name]

                if (
                    ref_var.dtype != out_var.dtype
                    or ref_var.dimensions != out_var.dimensions
                ):
                    raise ValueError(f"Schema mismatch: {name}")

                if name in ("hru", "hruId"):
                    actual = np.asarray(
                        out_var[:], dtype=np.int64
                    ).reshape(-1)

                    if not np.array_equal(actual, ids):
                        raise ValueError(f"HRU ID mismatch: {name}")

                elif not same(ref_var[:], out_var[:]):
                    raise ValueError(
                        f"Reference value mismatch: {name}"
                    )

        if output_file.exists() and not overwrite:
            raise FileExistsError(output_file)

        os.replace(temporary, output_file)

    finally:
        if temporary.exists():
            temporary.unlink()

    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent
        / "config/camels_spat_arc.toml",
    )

    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path(__file__).resolve().parent
        / "reports/camels_spat_lumped_inventory.csv",
    )

    parser.add_argument("--basin", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()

    with args.config.open("rb") as f:
        config = tomllib.load(f)

    with args.inventory.open(newline="") as f:
        rows = list(csv.DictReader(f))

    selected = [
        row for row in rows
        if row["basin"] == args.basin
    ]

    if len(selected) != 1:
        raise ValueError(
            f"Expected one inventory entry for {args.basin}; "
            f"found {len(selected)}"
        )

    row = selected[0]

    if row["status"] != "READY":
        raise ValueError(
            f"Basin is not READY: {row['problems']}"
        )

    source = Path(row["source"])
    reference = Path(config["paths"]["reference_basin"])

    camels_file = (
        source / "lumped/settings/SUMMA/coldState.nc"
    )

    attributes_file = (
        source / "lumped/settings/SUMMA/attributes.nc"
    )

    reference_file = (
        reference / "summa_state/coldState.nc"
    )

    provenance = prepare_cold_state(
        camels_file=camels_file,
        attributes_file=attributes_file,
        reference_file=reference_file,
        output_file=args.output,
        policy=config["reference_policy"],
        overwrite=args.overwrite,
    )

    report = {
        "basin": args.basin,
        "group": row["group"],
        "source_cold_state": str(camels_file),
        "reference_cold_state": str(reference_file),
        "output_cold_state": str(args.output.resolve()),
        "policy": config["reference_policy"]["mode"],
        "provenance": provenance,
        "validation": "PASS",
    }

    report_file = args.output.with_suffix(".provenance.json")

    with report_file.open("w") as f:
        json.dump(report, f, indent=2)

    print("==========================================")
    print("COLD-STATE CONVERSION: PASS")
    print("==========================================")
    print("Basin:", args.basin)
    print("Group:", row["group"])
    print("Output:", args.output)
    print("Provenance:", report_file)
    print("Variables:", len(provenance))
    print("Source files: UNCHANGED")


if __name__ == "__main__":
    main()
