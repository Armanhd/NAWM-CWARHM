#!/usr/bin/env python3
"""
Step 05: Read-only distributed CAMELS-SPAT conversion inventory.

Checks source availability, one-to-one HRU/GRU/routing correspondence,
existing forcing inventory, and eligibility for direct ID alignment.

Does not modify source NetCDF files.
"""
import argparse
import csv
import tomllib
from collections import Counter
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def ids(ds, name):
    if name not in ds.variables:
        raise ValueError(f"Missing variable: {name}")
    values = np.ma.asarray(ds.variables[name][:])
    if np.ma.getmaskarray(values).any():
        raise ValueError(f"Missing values in {name}")
    values = np.asarray(values).ravel()
    if not np.issubdtype(values.dtype, np.integer):
        raise ValueError(f"Non-integer ID datatype: {name}")
    return values.astype(np.int64)


def inventory_basin(row, audit):
    source = Path(row["source"])
    basin = row["basin"]
    problems = []

    result = {
        "index": row["index"],
        "group": row["group"],
        "basin": basin,
        "source": str(source),
        "summa_hrus": "",
        "summa_grus": "",
        "routing_hrus": "",
        "forcing_files": 0,
        "old_hru_ids": "",
        "new_id_source": "attributes.gruId",
        "id_policy": "hruId=gruId=hru2gruId=topology.hruId",
        "one_to_one": False,
        "same_order": False,
        "forcing_matches_original": False,
        "status": "REVIEW",
        "issues": "",
    }

    if not source.is_dir():
        result["issues"] = "Source directory missing"
        return result

    paths = {
        "attributes": source / "settings/SUMMA/attributes.nc",
        "cold_state": source / "settings/SUMMA/coldState.nc",
        "trial_params": source / "settings/SUMMA/trialParams.nc",
        "topology": source / "settings/mizuRoute/topology.nc",
        "forcing_list": source / "settings/SUMMA/forcingFileList_LST.txt",
    }

    for name, path in paths.items():
        if not path.is_file():
            problems.append(f"Missing {name}: {path}")

    if problems:
        result["issues"] = "; ".join(problems)
        return result

    try:
        with Dataset(paths["attributes"]) as a, \
             Dataset(paths["topology"]) as t, \
             Dataset(paths["cold_state"]) as c, \
             Dataset(paths["trial_params"]) as p:

            old_hru = ids(a, "hruId")
            gru = ids(a, "gruId")
            mapping = ids(a, "hru2gruId")
            routing = ids(t, "hruId")
            cold = ids(c, "hruId")
            trial = ids(p, "hruId")

            result["summa_hrus"] = len(old_hru)
            result["summa_grus"] = len(gru)
            result["routing_hrus"] = len(routing)

            unique = all(
                len(np.unique(x)) == len(x)
                for x in (old_hru, gru, routing)
            )

            one_to_one = (
                unique
                and len(old_hru) == len(gru)
                == len(mapping) == len(routing)
                and np.array_equal(gru, mapping)
                and set(gru.tolist()) == set(routing.tolist())
            )

            same_order = np.array_equal(gru, routing)

            result["one_to_one"] = bool(one_to_one)
            result["same_order"] = bool(same_order)
            result["old_hru_ids"] = (
                "sequential_1_to_N"
                if np.array_equal(
                    old_hru, np.arange(1, len(old_hru) + 1)
                )
                else "other"
            )

            if not one_to_one:
                problems.append("HRU/GRU/routing one-to-one check failed")
            if not same_order:
                problems.append("GRU/routing ID order differs")
            if not np.array_equal(old_hru, cold):
                problems.append("Cold-state IDs differ from SUMMA attributes")
            if not np.array_equal(old_hru, trial):
                problems.append("Trial-parameter IDs differ from attributes")
            if np.any(gru <= 0):
                problems.append("Nonpositive target HRU identifier")
            if np.any(gru > np.iinfo(np.int32).max):
                problems.append("Target ID exceeds int32 range")

            for name, ds in (("cold_state", c), ("trial_params", p)):
                if "hru" not in ds.dimensions:
                    problems.append(f"{name} missing hru dimension")
                elif len(ds.dimensions["hru"]) != len(old_hru):
                    problems.append(f"{name} HRU dimension mismatch")

        names = [
            line.strip()
            for line in paths["forcing_list"].read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        result["forcing_files"] = len(names)
        forcing_dir = source / "forcing/6_SUMMA_input_LST"

        if not names:
            problems.append("Empty forcing file list")
        if len(names) != len(set(names)):
            problems.append("Duplicate forcing filenames")

        for name in names:
            path = forcing_dir / name
            if not path.is_file():
                problems.append(f"Missing forcing: {name}")
            elif path.stat().st_size == 0:
                problems.append(f"Empty forcing: {name}")

        if audit is None:
            problems.append("Missing previous HRU audit entry")
        else:
            forcing_ok = audit.get("forcing_matches_summa") == "True"
            result["forcing_matches_original"] = forcing_ok

            if audit.get("status") != "READY_DIRECT":
                problems.append(
                    f"Previous audit status: {audit.get('status')}"
                )

            if not forcing_ok:
                problems.append("Forcing HRU IDs do not match attributes")

            if str(len(old_hru)) != audit.get("summa_hrus"):
                problems.append("HRU count differs from previous audit")

        result["status"] = "READY" if not problems else "REVIEW"

    except Exception as exc:
        problems.append(f"{type(exc).__name__}: {exc}")

    result["issues"] = "; ".join(problems)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--hru-audit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.config, "rb") as f:
        config = tomllib.load(f)

    if config["selection"]["model_type"] != "distributed":
        raise SystemExit("Expected distributed model_type")

    inventory = read_csv(Path(args.inventory))
    audit_rows = read_csv(Path(args.hru_audit))
    audit = {r["basin"]: r for r in audit_rows}

    if len(inventory) != 1426 or len(audit) != 1426:
        raise SystemExit(
            "Expected 1426 inventory and 1426 HRU audit entries; "
            "check input files before continuing"
        )

    results = [
        inventory_basin(row, audit.get(row["basin"]))
        for row in inventory
    ]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print("========== STEP 05 DISTRIBUTED INVENTORY ==========")
    print("Basins:", len(results))
    print("Distributed HRUs:", sum(
        int(r["summa_hrus"]) for r in results
        if r["summa_hrus"] != ""
    ))

    for group in ("headwater", "meso_scale", "macro_scale"):
        subset = [r for r in results if r["group"] == group]
        print(f"{group}: {len(subset)}")

    for status, count in sorted(
        Counter(r["status"] for r in results).items()
    ):
        print(f"{status}: {count}")

    print("Output:", output)

    review = [r for r in results if r["status"] != "READY"]

    for row in review[:15]:
        print("REVIEW:", row["basin"], row["issues"])

    if review:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
