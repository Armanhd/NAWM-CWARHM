#!/usr/bin/env python3
"""
Step 06: Prepare distributed SUMMA inputs with aligned HRU IDs.

- Never edits original NAWM-CWARHM inputs.
- Preserves HRU order and spatial attributes.
- Uses the existing routing HRU IDs as the target identifiers.
- Replicates the CENTURY reference cold state and trial structures.
- Copies the original mizuRoute topology without alteration.
- Forcing conversion is handled separately in Step 07.
"""
import argparse
import csv
import shutil
import tempfile
import tomllib
from pathlib import Path

import numpy as np
from netCDF4 import Dataset


def read_ids(ds, name):
    if name not in ds.variables:
        raise ValueError(f"Missing {name}")

    a = np.ma.asarray(ds.variables[name][:])
    if np.ma.getmaskarray(a).any():
        raise ValueError(f"Missing values in {name}")

    result = np.asarray(a).reshape(-1)
    if not np.issubdtype(result.dtype, np.integer):
        raise ValueError(f"{name} is not integer")

    return result.astype(np.int64)


def load_row(inventory, basin):
    with open(inventory, newline="") as f:
        rows = [r for r in csv.DictReader(f)
                if r["basin"] == basin]

    if len(rows) != 1:
        raise ValueError(f"Expected one inventory row: {basin}")

    if rows[0]["status"] != "READY":
        raise ValueError(f"Basin not READY: {basin}")

    return rows[0]


def copy_reference_expanded(reference, output, hru_ids):
    """
    Copy all reference dimensions, variables, metadata and numerical
    values, expanding the one-HRU reference along its HRU axis.
    """
    with Dataset(reference) as src, Dataset(
        output, "w", format=src.file_format
    ) as dst:

        if "hru" not in src.dimensions:
            raise ValueError(f"No hru dimension in {reference}")

        if len(src.dimensions["hru"]) != 1:
            raise ValueError("Expected one-HRU reference")

        for key in src.ncattrs():
            dst.setncattr(key, src.getncattr(key))

        for name, dim in src.dimensions.items():
            dst.createDimension(
                name,
                len(hru_ids) if name == "hru" else (
                    None if dim.isunlimited() else len(dim)
                ),
            )

        for name, var in src.variables.items():
            fill = (
                var.getncattr("_FillValue")
                if "_FillValue" in var.ncattrs()
                else None
            )

            kwargs = {}
            if fill is not None:
                kwargs["fill_value"] = fill

            out = dst.createVariable(
                name, var.datatype, var.dimensions, **kwargs
            )

            for attr in var.ncattrs():
                if attr != "_FillValue":
                    out.setncattr(attr, var.getncattr(attr))

            if name == "hruId":
                if "hru" not in var.dimensions:
                    raise ValueError("Reference hruId lacks hru axis")

                if not np.issubdtype(np.dtype(var.dtype), np.integer):
                    raise ValueError("Reference hruId must be integer")

                limits = np.iinfo(var.dtype)
                if (
                    hru_ids.min() < limits.min or
                    hru_ids.max() > limits.max
                ):
                    raise ValueError(
                        "Target HRU IDs exceed reference datatype"
                    )

                shape = [
                    len(hru_ids) if d == "hru"
                    else len(src.dimensions[d])
                    for d in var.dimensions
                ]
                axis = var.dimensions.index("hru")

                data = np.asarray(hru_ids, dtype=var.dtype)
                expand_shape = [1] * len(shape)
                expand_shape[axis] = len(hru_ids)
                data = np.broadcast_to(
                    data.reshape(expand_shape), shape
                )
                out[:] = data

            elif "hru" in var.dimensions:
                axis = var.dimensions.index("hru")
                data = var[:]
                out[:] = np.ma.repeat(
                    data, len(hru_ids), axis=axis
                )

            else:
                out[:] = var[:]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--basin", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()

    with open(args.config, "rb") as f:
        config = tomllib.load(f)

    if config["selection"]["model_type"] != "distributed":
        raise ValueError("Expected distributed configuration")

    if config["reference_policy"]["cold_state"] != (
        "replicate_reference_across_hrus"
    ):
        raise ValueError("Incorrect distributed cold-state policy")

    row = load_row(args.inventory, args.basin)
    source = Path(row["source"])
    reference = Path(config["paths"]["reference_basin"])

    output_root = Path(args.destination).resolve()
    target = output_root / "domain" / args.basin

    # Step 06 is deliberately restricted to explicit test destinations.
    configured_production = Path(
        config["paths"]["output_root"]
    ).resolve()

    if output_root == configured_production:
        raise ValueError(
            "Step 06 must use a test destination, not production"
        )

    if target.exists():
        raise FileExistsError(
            f"Target exists; refusing overwrite: {target}"
        )

    src_attr = source / "settings/SUMMA/attributes.nc"
    src_cold = source / "settings/SUMMA/coldState.nc"
    src_trial = source / "settings/SUMMA/trialParams.nc"
    src_topo = source / "settings/mizuRoute/topology.nc"

    ref_attr = reference / "summa_inputs/attributes.nc"
    ref_cold = reference / "summa_state/coldState.nc"
    ref_trial = reference / "summa_inputs/trialParams.priori.nc"
    ref_routing = reference / "mizuroute_inputs/mizuroute.param"

    for path in (
        src_attr, src_cold, src_trial, src_topo,
        ref_attr, ref_cold, ref_trial, ref_routing
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    with Dataset(src_attr) as a, Dataset(src_topo) as t, \
         Dataset(src_cold) as c, Dataset(src_trial) as p:

        old_ids = read_ids(a, "hruId")
        gru_ids = read_ids(a, "gruId")
        mapping = read_ids(a, "hru2gruId")
        routing_ids = read_ids(t, "hruId")
        cold_ids = read_ids(c, "hruId")
        trial_ids = read_ids(p, "hruId")

        n = len(old_ids)

        if not (
            len(gru_ids) == len(mapping)
            == len(routing_ids) == n
        ):
            raise ValueError("HRU and GRU counts differ")

        if len(np.unique(routing_ids)) != n:
            raise ValueError("Routing IDs are not unique")

        if not np.array_equal(gru_ids, mapping):
            raise ValueError("GRU mapping mismatch")

        if not np.array_equal(gru_ids, routing_ids):
            raise ValueError("Routing and GRU ID order differs")

        if not np.array_equal(old_ids, cold_ids):
            raise ValueError("Cold-state source IDs mismatch")

        if not np.array_equal(old_ids, trial_ids):
            raise ValueError("Trial-parameter source IDs mismatch")

        if "gru" not in a.dimensions or (
            len(a.dimensions["gru"]) != n
        ):
            raise ValueError("Expected one GRU per HRU")

    with Dataset(ref_attr) as ref:
        contour = np.asarray(
            ref.variables["contourLength"][:]
        ).reshape(-1)

        if len(contour) != 1:
            raise ValueError("Invalid reference contourLength")

        contour_value = float(contour[0])

    if config["reference_policy"]["contour_length"] != (
        "copy_reference"
    ):
        raise ValueError("Unexpected contour-length policy")

    output_root.joinpath("domain").mkdir(
        parents=True, exist_ok=True
    )

    # Stage a complete Step 06 output before placing it in domain/.
    with tempfile.TemporaryDirectory(
        prefix=".distributed_step06_",
        dir=output_root / "domain"
    ) as temp:

        stage = Path(temp) / args.basin

        for folder in (
            "summa_inputs",
            "summa_state",
            "mizuroute_inputs",
        ):
            (stage / folder).mkdir(parents=True)

        attr_output = stage / "summa_inputs/attributes.nc"
        cold_output = stage / "summa_state/coldState.nc"
        trial_output = stage / "summa_inputs/trialParams.nc"
        priori_output = (
            stage / "summa_inputs/trialParams.priori.nc"
        )
        topo_output = stage / "mizuroute_inputs/topology.nc"

        # Preserve every source spatial attribute except fields
        # that are intentionally aligned to the reference policy.
        shutil.copy2(src_attr, attr_output)

        with Dataset(attr_output, "r+") as ds:
            ds.variables["hruId"][:] = routing_ids
            ds.variables["contourLength"][:] = contour_value

        copy_reference_expanded(
            ref_cold, cold_output, routing_ids
        )
        copy_reference_expanded(
            ref_trial, trial_output, routing_ids
        )
        copy_reference_expanded(
            ref_trial, priori_output, routing_ids
        )

        shutil.copy2(src_topo, topo_output)
        shutil.copy2(
            ref_routing,
            stage / "mizuroute_inputs/mizuroute.param"
        )

        # Independently reopen every generated NetCDF file.
        for path in (
            attr_output, cold_output, trial_output,
            priori_output, topo_output
        ):
            with Dataset(path) as ds:
                actual = read_ids(ds, "hruId")
                if not np.array_equal(actual, routing_ids):
                    raise ValueError(
                        f"Generated HRU ID mismatch: {path}"
                    )

        with Dataset(cold_output) as ds:
            if len(ds.dimensions["midSoil"]) != 3:
                raise ValueError("Expected 3 soil layers")

            nsoil = np.asarray(
                ds.variables["nSoil"][:]
            )
            if not np.all(nsoil == 3):
                raise ValueError("nSoil must be 3 for every HRU")

            depths = np.asarray(
                ds.variables["mLayerDepth"][:]
            )
            expected = np.asarray(
                config["reference_policy"]["soil_layer_depths_m"]
            ).reshape(3, 1)

            if depths.shape != (3, n) or not np.allclose(
                depths, expected
            ):
                raise ValueError("Soil layer depths mismatch")

        stage.rename(target)

    print("========== STEP 06 DISTRIBUTED INPUTS ==========")
    print("Basin:", args.basin)
    print("HRUs:", n)
    print("IDs match topology: PASS")
    print("Spatial attributes preserved: PASS")
    print("Reference contourLength:", contour_value)
    print("Cold-state soil layers: 3")
    print("Cold-state depths: 0.2, 0.3, 0.5 m")
    print("Reference trial parameters: PASS")
    print("Routing topology copied: PASS")
    print("Forcing: NOT YET PREPARED (Step 07)")
    print("Output:", target)
    print("STEP 06: PASS")


if __name__ == "__main__":
    main()
