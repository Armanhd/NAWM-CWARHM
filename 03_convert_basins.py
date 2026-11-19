#!/usr/bin/env python3
"""03: Convert one CAMELS-SPAT lumped basin to CENTURY-style SUMMA/mizuRoute.

The default century_exact configuration follows old_scripts/09_prepare_century_basins.py.
Copying inputs is intentional; never modify or replace source files.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tomllib
from pathlib import Path
from uuid import uuid4

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent


def load_cold_state():
    path = HERE / "02_prepare_cold_state.py"
    spec = importlib.util.spec_from_file_location("prepare_cold_state_02", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare_cold_state


def require_file(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def array(ds, name):
    return np.asarray(ds.variables[name][:], dtype=np.int64).reshape(-1)


def read_forcing_names(path: Path) -> list[str]:
    names = [line.strip() for line in require_file(path).read_text().splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if not names or len(names) != len(set(names)):
        raise ValueError(f"Empty or duplicate forcing names in {path}")
    for name in names:
        if name in (".", "..") or Path(name).name != name or "\\" in name:
            raise ValueError(f"Unsafe forcing filename: {name!r}")
    return names


def check_source(source: Path, names: list[str], source_attributes: Path) -> np.ndarray:
    forcing_dir = source / "lumped/forcing/6_SUMMA_input_LST"
    with Dataset(require_file(source_attributes)) as attr:
        ids = array(attr, "hruId")
    if ids.size != 1 or ids[0] <= 0:
        raise ValueError(f"Expected one positive lumped HRU: {ids.tolist()}")
    with Dataset(require_file(source / "lumped/settings/SUMMA/trialParams.nc")) as trial:
        if not np.array_equal(array(trial, "hruId"), ids):
            raise ValueError("Source trialParams HRU mismatch")
        unexpected = set(trial.variables) - {"hru", "hruId", "maxstep"}
        if unexpected:
            raise ValueError(f"Unexpected source trial parameter overrides: {sorted(unexpected)}")
    for name in names:
        with Dataset(require_file(forcing_dir / name)) as forcing:
            if not np.array_equal(array(forcing, "hruId"), ids):
                raise ValueError(f"Forcing HRU mismatch: {name}")
    return ids


def make_prior(template: Path, ids: np.ndarray, target: Path):
    with Dataset(require_file(template)) as check:
        source_format = check.file_format
    with Dataset(template) as src, Dataset(target, "w", format=source_format) as dst:
        if set(src.variables) != {"hru", "hruId"} or len(src.dimensions["hru"]) != len(ids):
            raise ValueError("Unexpected reference prior parameter structure")
        for name, dim in src.dimensions.items():
            dst.createDimension(name, None if dim.isunlimited() else len(dim))
        for name in src.ncattrs():
            dst.setncattr(name, src.getncattr(name))
        for name, var in src.variables.items():
            opts = {"fill_value": var.getncattr("_FillValue")} if "_FillValue" in var.ncattrs() else {}
            out = dst.createVariable(name, var.dtype, var.dimensions, **opts)
            for key in var.ncattrs():
                if key != "_FillValue":
                    out.setncattr(key, var.getncattr(key))
            out[:] = ids


def make_mapping(topology: Path, ids: np.ndarray, target: Path):
    with Dataset(require_file(topology)) as topo:
        routing = array(topo, "hruId")
        segments = array(topo, "segId")
        downstream = array(topo, "downSegId")
        hru_segments = array(topo, "hruToSegId")
    segment_set = set(segments.tolist())
    if not routing.size or len(set(routing.tolist())) != routing.size:
        raise ValueError("Routing HRU IDs empty or duplicated")
    if len(segment_set) != len(segments) or not set(downstream.tolist()) <= (segment_set | {0}):
        raise ValueError("Invalid downstream routing segments")
    if not set(hru_segments.tolist()) <= segment_set:
        raise ValueError("Routing HRUs reference missing segments")
    limits = np.iinfo(np.int32)
    if np.any(routing < limits.min) or np.any(routing > limits.max) or not limits.min <= ids[0] <= limits.max:
        raise ValueError("HRU IDs exceed int32 mapping format")
    with Dataset(target, "w", format="NETCDF4") as out:
        out.createDimension("polyid", len(routing))
        out.createDimension("data", len(routing))
        out.createVariable("nOverlaps", "i4", ("polyid",))[:] = 1
        out.createVariable("polyid", "i4", ("polyid",))[:] = routing
        out.createVariable("qhru_id", "i4", ("data",))[:] = int(ids[0])
        out.createVariable("weight", "f8", ("data",))[:] = 1.0


def equal_masked(a, b) -> bool:
    return bool(np.ma.allequal(np.ma.asarray(a), np.ma.asarray(b)))


def validate_stage(stage: Path, names: list[str], source_attributes: Path,
                   reference: Path, ids: np.ndarray, config: dict):
    inputs = stage / "summa_inputs"
    with Dataset(inputs / "attributes.nc") as out, Dataset(source_attributes) as src, \
         Dataset(reference / "summa_inputs/attributes.nc") as ref:
        if not np.array_equal(array(out, "hruId"), ids):
            raise ValueError("Output attributes HRU mismatch")
        if not equal_masked(out.variables["contourLength"][:], ref.variables["contourLength"][:]):
            raise ValueError("Output contourLength differs from reference")
        if set(out.variables) != set(src.variables):
            raise ValueError("Attributes variables changed")
        for name in src.variables:
            if name != "contourLength" and not equal_masked(out.variables[name][:], src.variables[name][:]):
                raise ValueError(f"Unexpected attributes change: {name}")
    for name in ("trialParams.nc", "trialParams.priori.nc"):
        with Dataset(inputs / name) as trial:
            if set(trial.variables) != {"hru", "hruId"} or not np.array_equal(array(trial, "hruId"), ids):
                raise ValueError(f"Invalid {name}")
    with Dataset(stage / "summa_state/coldState.nc") as cold, \
         Dataset(reference / "summa_state/coldState.nc") as ref:
        if not np.array_equal(array(cold, "hruId"), ids):
            raise ValueError("Cold-state HRU mismatch")
        if set(cold.variables) != set(ref.variables):
            raise ValueError("Cold-state schema mismatch")
        for name in ref.variables:
            if name not in ("hru", "hruId") and not equal_masked(cold.variables[name][:], ref.variables[name][:]):
                raise ValueError(f"Cold-state value mismatch: {name}")
    with Dataset(stage / "mizuroute_inputs/topology.nc") as topo, \
         Dataset(stage / "mizuroute_inputs/lumped_to_hru.nc") as mapping:
        if set(array(topo, "hruId")) != set(array(mapping, "polyid")):
            raise ValueError("Routing mapping polyid mismatch")
        if not np.all(array(mapping, "qhru_id") == ids[0]):
            raise ValueError("Routing mapping qhru_id mismatch")
        if not np.allclose(mapping.variables["weight"][:], 1.0):
            raise ValueError("Routing mapping weights differ from one")
    if read_forcing_names(inputs / "forcingFileList.txt") != names:
        raise ValueError("Output forcing list changed")
    for name in names:
        if not (stage / "summa_forcing" / name).is_file():
            raise ValueError(f"Missing copied forcing: {name}")


def collect_observations(source: Path, output_root: Path, copy_enabled: bool):
    observations = []
    if copy_enabled:
        for subset in ("obs-daily", "obs-hourly"):
            for src in sorted((source / "observations" / subset).glob("*.nc")):
                observations.append((src, output_root / "observations" / subset / src.name))
    return observations


def publish_observations(observations) -> list[str]:
    """Never overwrite: atomic publish; accept already identical observations."""
    published = []
    for src, target in observations:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if src.stat().st_size != target.stat().st_size or file_hash(src) != file_hash(target):
                raise FileExistsError(f"Observation name collision with different content: {target}")
            published.append(str(target))
            continue
        tmp = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            shutil.copy2(src, tmp)
            if file_hash(src) != file_hash(tmp):
                raise IOError(f"Observation copy checksum mismatch: {src}")
            try:
                os.link(tmp, target)  # Atomic exclusive creation on one filesystem.
            except FileExistsError:
                if src.stat().st_size != target.stat().st_size or file_hash(src) != file_hash(target):
                    raise FileExistsError(f"Observation name collision: {target}")
            published.append(str(target))
        finally:
            tmp.unlink(missing_ok=True)
    return published


def process(row: dict, config: dict, dest: Path) -> str:
    if row["status"] != "READY":
        raise ValueError(f"Basin is not READY: {row['basin']} {row['problems']}")
    if config["selection"]["model_type"] != "lumped":
        raise ValueError("Only lumped model is supported")
    policy = config["reference_policy"]
    if (policy["mode"], policy["contour_length"], policy["cold_state"],
        policy["mizuroute_parameters"], policy["trial_parameters"]) != (
        "century_exact", "copy_reference", "copy_reference_except_hru_ids",
        "copy_reference", "reference_structure_with_basin_hru_ids"):
        raise ValueError("Unsupported TOML reference policy")
    if not config["processing"].get("copy_forcing", True):
        raise ValueError("This CENTURY-style converter requires copy_forcing=true")
    if config["processing"].get("overwrite_existing", False):
        raise ValueError("Overwriting completed basin directories is intentionally unsupported")
    if not config["processing"].get("validate_before_finalize", True):
        raise ValueError("Validation before finalization must remain enabled")

    basin = row["basin"]
    source = Path(row["source"]).resolve()
    source_root = Path(config["paths"]["source_root"]).resolve()
    if source != (source_root / row["group"] / f"domain_{basin}"):
        raise ValueError("Inventory source path disagrees with configuration")
    reference = Path(config["paths"]["reference_basin"]).resolve()
    if not reference.is_dir():
        raise FileNotFoundError(reference)
    if dest.resolve() == source_root or dest.resolve() == source:
        raise ValueError("Output location must be separate from source")
    domain_root = dest / "domain"
    final = domain_root / basin
    if final.exists():
        if (final / ".conversion_complete.json").is_file():
            print("SKIPPED_COMPLETED:", final)
            return "SKIPPED_COMPLETED"
        raise FileExistsError(f"Output exists without completion marker: {final}")

    forcing_dir = source / "lumped/forcing/6_SUMMA_input_LST"
    forcing_list = source / "lumped/settings/SUMMA/forcingFileList_LST.txt"
    names = read_forcing_names(forcing_list)
    source_attributes = require_file(source / "lumped/settings/SUMMA/attributes.nc")
    ids = check_source(source, names, source_attributes)
    observations = collect_observations(source, dest, config["processing"].get("copy_observations", True))
    for src, target in observations:
        if target.exists() and (src.stat().st_size != target.stat().st_size or file_hash(src) != file_hash(target)):
            raise FileExistsError(f"Observation name collision: {target}")

    domain_root.mkdir(parents=True, exist_ok=True)
    stage = domain_root / f".staging_{basin}_{uuid4().hex}"
    stage.mkdir()
    try:
        for folder in ("mizuroute_inputs/work", "summa_forcing", "summa_inputs", "summa_state", "work"):
            (stage / folder).mkdir(parents=True, exist_ok=True)
        route = stage / "mizuroute_inputs"
        shutil.copy2(require_file(source / "settings/mizuRoute/topology.nc"), route / "topology.nc")
        shutil.copy2(require_file(reference / "mizuroute_inputs/mizuroute.param"), route / "mizuroute.param")
        make_mapping(route / "topology.nc", ids, route / "lumped_to_hru.nc")
        for name in names:
            shutil.copy2(forcing_dir / name, stage / "summa_forcing" / name)
        shutil.copy2(forcing_list, stage / "summa_inputs/forcingFileList.txt")
        attrs_out = stage / "summa_inputs/attributes.nc"
        shutil.copy2(source_attributes, attrs_out)
        with Dataset(reference / "summa_inputs/attributes.nc") as ref:
            contour = ref.variables["contourLength"][:]
        with Dataset(attrs_out, "r+") as attrs:
            if attrs.variables["contourLength"].shape != contour.shape:
                raise ValueError("contourLength shape mismatch")
            attrs.variables["contourLength"][:] = contour
        for filename in ("trialParams.nc", "trialParams.priori.nc"):
            make_prior(reference / "summa_inputs/trialParams.priori.nc", ids,
                       stage / "summa_inputs" / filename)
        provenance = load_cold_state()(
            camels_file=source / "lumped/settings/SUMMA/coldState.nc",
            attributes_file=source_attributes,
            reference_file=reference / "summa_state/coldState.nc",
            output_file=stage / "summa_state/coldState.nc",
            policy=policy,
        )
        validate_stage(stage, names, source_attributes, reference, ids, config)
        # Shared observations are published before the domain becomes visible.
        observation_paths = publish_observations(observations)
        marker = {
            "basin": basin, "group": row["group"], "source": str(source),
            "reference": str(reference), "reference_policy": policy["mode"],
            "hru_id": int(ids[0]), "forcing_files": len(names),
            "observations": observation_paths, "cold_state_provenance": provenance,
            "validation": "PASS", "note": "Reference matches ARC copy; not authenticated against FIR original",
        }
        (stage / ".conversion_complete.json").write_text(json.dumps(marker, indent=2) + "\n")
        if final.exists():
            raise FileExistsError(final)
        stage.rename(final)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(f"COMPLETE: {basin} ({row['group']}) | forcing={len(names)} | observations={len(observations)}")
    print("Output:", final)
    return "COMPLETE"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "config/camels_spat_arc.toml")
    parser.add_argument("--inventory", type=Path, default=HERE / "reports/camels_spat_lumped_inventory.csv")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--basin")
    selection.add_argument("--index", type=int)
    parser.add_argument("--destination", type=Path, help="Override output root (use for tests)")
    args = parser.parse_args()
    with args.config.open("rb") as stream:
        config = tomllib.load(stream)
    with args.inventory.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if args.basin:
        selected = [r for r in rows if r["basin"] == args.basin]
        if len(selected) != 1:
            raise ValueError(f"Expected one inventory entry for {args.basin}; found {len(selected)}")
        row = selected[0]
    else:
        if args.index < 0 or args.index >= len(rows):
            raise IndexError(f"Index must be within 0..{len(rows)-1}")
        row = rows[args.index]
    dest = args.destination or Path(config["paths"]["output_root"])
    process(row, config, dest)


if __name__ == "__main__":
    main()
