#!/usr/bin/env python3
"""Step 08: Independent validation of distributed calibration inputs."""
import argparse
import csv
import hashlib
import tomllib
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def check(condition, message):
    if not condition:
        raise ValueError(message)


def same(a, b):
    return np.ma.allequal(np.ma.asarray(a), np.ma.asarray(b))


def ids(ds):
    a = np.ma.asarray(ds.variables["hruId"][:])
    check(not np.ma.getmaskarray(a).any(), "Masked HRU IDs")
    return np.asarray(a).ravel().astype(np.int64)


def checksum(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def compare_forcing(original, converted, old_ids, new_ids):
    with Dataset(original) as src, Dataset(converted) as dst:
        check(
            set(src.dimensions) == set(dst.dimensions),
            "Forcing dimensions differ"
        )
        for name in src.dimensions:
            check(
                len(src.dimensions[name]) == len(dst.dimensions[name]),
                f"Forcing dimension mismatch: {name}"
            )

        check(
            set(src.variables) == set(dst.variables),
            "Forcing variables differ"
        )

        check(
            same(ids(src), old_ids), "Original forcing IDs incorrect"
        )
        check(
            same(ids(dst), new_ids), "Converted forcing IDs incorrect"
        )

        for name in src.variables:
            if name == "hruId":
                continue

            a = src.variables[name]
            b = dst.variables[name]

            check(a.dimensions == b.dimensions,
                  f"Variable dimensions differ: {name}")
            check(a.dtype == b.dtype,
                  f"Variable datatype differs: {name}")

            check(set(a.ncattrs()) == set(b.ncattrs()),
                  f"Variable metadata differs: {name}")

            for attr in a.ncattrs():
                x = np.asarray(a.getncattr(attr))
                y = np.asarray(b.getncattr(attr))

                if (
                    np.issubdtype(x.dtype, np.number)
                    and np.issubdtype(y.dtype, np.number)
                ):
                    equal = np.array_equal(x, y, equal_nan=True)
                else:
                    equal = np.array_equal(x, y)

                check(
                    equal,
                    f"Variable attribute differs: {name}/{attr}"
                )

            if a.ndim == 0:
                check(same(a[...], b[...]), f"Value changed: {name}")
            else:
                for start in range(0, a.shape[0], 2048):
                    stop = min(start + 2048, a.shape[0])
                    selection = (slice(start, stop),) + (
                        slice(None),
                    ) * (a.ndim - 1)

                    check(
                        same(a[selection], b[selection]),
                        f"Forcing values changed: {name}, "
                        f"index {start}:{stop}"
                    )


def compare_expanded(reference, generated, new_ids):
    """Check reference values replicated along the HRU dimension."""
    with Dataset(reference) as ref, Dataset(generated) as out:
        check(
            set(ref.variables) == set(out.variables),
            f"Reference variables differ: {generated}"
        )
        check(
            set(ref.dimensions) == set(out.dimensions),
            f"Reference dimensions differ: {generated}"
        )
        check(len(ref.dimensions["hru"]) == 1,
              "Reference does not have one HRU")
        check(len(out.dimensions["hru"]) == len(new_ids),
              "Generated HRU dimension incorrect")
        check(same(ids(out), new_ids),
              "Generated reference IDs incorrect")

        for name, rv in ref.variables.items():
            ov = out.variables[name]
            check(rv.dimensions == ov.dimensions,
                  f"Reference variable shape definition: {name}")

            if name == "hruId":
                continue

            values = rv[:]
            if "hru" in rv.dimensions:
                axis = rv.dimensions.index("hru")
                expected = np.ma.repeat(
                    values, len(new_ids), axis=axis
                )
            else:
                expected = values

            check(
                same(expected, ov[:]),
                f"Reference values differ: {generated.name}/{name}"
            )


def validate(row, config, destination):
    basin = row["basin"]
    source = Path(row["source"])
    target = destination / "domain" / basin
    reference = Path(config["paths"]["reference_basin"])

    check(target.is_dir(), f"Missing converted basin: {target}")

    original_attr = source / "settings/SUMMA/attributes.nc"
    generated_attr = target / "summa_inputs/attributes.nc"
    original_topo = source / "settings/mizuRoute/topology.nc"
    generated_topo = target / "mizuroute_inputs/topology.nc"

    with Dataset(original_attr) as src, \
         Dataset(generated_attr) as out, \
         Dataset(original_topo) as topo:

        old_ids = ids(src)
        new_ids = ids(topo)
        n = len(new_ids)

        check(same(ids(out), new_ids), "Attributes HRU IDs differ")
        check(
            same(out.variables["gruId"][:], new_ids),
            "GRU IDs differ"
        )
        check(
            same(out.variables["hru2gruId"][:], new_ids),
            "HRU-to-GRU IDs differ"
        )

        check(
            set(src.variables) == set(out.variables),
            "Spatial attribute variables differ"
        )

        for name in src.variables:
            if name in ("hruId", "contourLength"):
                continue
            check(
                same(src.variables[name][:], out.variables[name][:]),
                f"Spatial attribute changed: {name}"
            )

    check(
        checksum(original_topo) == checksum(generated_topo),
        "Routing topology changed"
    )

    check(
        checksum(reference / "mizuroute_inputs/mizuroute.param")
        == checksum(target / "mizuroute_inputs/mizuroute.param"),
        "Reference mizuRoute parameters changed"
    )

    compare_expanded(
        reference / "summa_state/coldState.nc",
        target / "summa_state/coldState.nc",
        new_ids
    )

    ref_trial = reference / "summa_inputs/trialParams.priori.nc"

    for name in ("trialParams.nc", "trialParams.priori.nc"):
        compare_expanded(
            ref_trial,
            target / "summa_inputs" / name,
            new_ids
        )

    list_path = source / "settings/SUMMA/forcingFileList_LST.txt"
    names = [
        x.strip() for x in list_path.read_text().splitlines()
        if x.strip() and not x.lstrip().startswith("#")
    ]
    check(bool(names), "No forcing filenames")

    for name in names:
        compare_forcing(
            source / "forcing/6_SUMMA_input_LST" / name,
            target / "summa_forcing" / name,
            old_ids, new_ids
        )

    check(
        not list(target.rglob("lumped_to_hru.nc")),
        "Unexpected lumped remapping file"
    )

    observations = 0
    for kind in ("obs-daily", "obs-hourly"):
        matches = [
            p for p in (source / "observations").rglob("*")
            if p.is_file()
            and basin.lower() in p.name.lower()
            and ("hourly" if kind == "obs-hourly"
                 else "daily") in
                 str(p.relative_to(source / "observations")).lower()
        ]

        check(bool(matches), f"No source {kind} observations")

        for src in matches:
            dst = destination / "observations" / kind / src.name
            check(dst.is_file(), f"Missing observation: {dst}")
            check(
                checksum(src) == checksum(dst),
                f"Observation changed: {src.name}"
            )
            observations += 1

    decisions = (
        target / "summa_inputs/modelDecisions.txt"
    ).read_text()

    check(
        "readPerStep" in decisions
        and "writePerStep" in decisions,
        "Expected distributed read/write buffering not found"
    )

    # File managers are inspected separately because Step 07 copies
    # originals and does not yet rewrite their paths.
    return {
        "basin": basin,
        "hrus": n,
        "forcing_files": len(names),
        "observations": observations,
        "status": "PASS",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--basin", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.config, "rb") as f:
        config = tomllib.load(f)

    with open(args.inventory, newline="") as f:
        rows = {r["basin"]: r for r in csv.DictReader(f)}

    destination = Path(args.destination)
    results = []

    for basin in args.basin:
        try:
            result = validate(rows[basin], config, destination)
            result["issue"] = ""
        except Exception as exc:
            result = {
                "basin": basin,
                "hrus": "",
                "forcing_files": "",
                "observations": "",
                "status": "FAIL",
                "issue": str(exc),
            }

        results.append(result)
        print(
            f"{basin}: {result['status']}"
            + (f" | {result['issue']}" if result["issue"] else ""),
            flush=True
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "basin", "hrus", "forcing_files",
            "observations", "status", "issue"
        ])
        writer.writeheader()
        writer.writerows(results)

    print("\n========== STEP 08 VALIDATION ==========")
    print("PASS:", sum(r["status"] == "PASS" for r in results))
    print("FAIL:", sum(r["status"] == "FAIL" for r in results))
    print("Report:", output)

    if any(r["status"] != "PASS" for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
