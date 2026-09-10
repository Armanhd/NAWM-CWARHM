
'''
For every:

domain_*/lumped/settings/SUMMA/

you will end with:
coldState_8layer.nc     <- original untouched 8-layer file
coldState_3layer.nc     <- newly generated 3-layer file
coldState.nc            <- copy of 3-layer file used by SUMMA


The script remaps the existing initial soil-state values into the top 1 m.
'''

#!/usr/bin/env python3

from pathlib import Path
import argparse
import shutil
import sys

import numpy as np
from netCDF4 import Dataset


# ============================================================
# STANDARD SUMMA 3-LAYER SOIL PROFILE
# ============================================================

NEW_INTERFACES = np.array([0.0, 0.2, 0.5, 1.0], dtype=float)
NEW_DEPTHS = np.diff(NEW_INTERFACES)

LAYER_VARIABLES = {
    "mLayerTemp",
    "mLayerVolFracIce",
    "mLayerVolFracLiq",
    "mLayerMatricHead",
    "mLayerDepth",
    "iLayerHeight",
}


def thickness_weighted_remap(values, old_interfaces, new_interfaces):
    """
    Remap layer-centred values using thickness-weighted overlap.

    values shape:
        (old_layers, hru) or (old_layers,)

    Only the top 1 m is retained because the new profile ends at 1 m.
    """
    values = np.asarray(values)

    if values.ndim == 1:
        values = values[:, None]
        squeeze = True
    else:
        squeeze = False

    nnew = len(new_interfaces) - 1
    nhru = values.shape[1]

    out = np.full((nnew, nhru), np.nan, dtype=float)

    for j in range(nnew):
        new_top = new_interfaces[j]
        new_bottom = new_interfaces[j + 1]

        weights = []

        for i in range(len(old_interfaces) - 1):
            old_top = old_interfaces[i]
            old_bottom = old_interfaces[i + 1]

            overlap = max(
                0.0,
                min(new_bottom, old_bottom)
                - max(new_top, old_top)
            )
            weights.append(overlap)

        weights = np.asarray(weights)

        if weights.sum() <= 0:
            raise RuntimeError(
                f"No overlap found for new layer "
                f"{new_top}-{new_bottom} m"
            )

        for h in range(nhru):
            x = values[:, h]
            good = np.isfinite(x) & (weights > 0)

            if np.any(good):
                out[j, h] = np.sum(
                    x[good] * weights[good]
                ) / np.sum(weights[good])

    if squeeze:
        return out[:, 0]

    return out


def create_3layer_file(source, output):
    with Dataset(source, "r") as src:

        if "iLayerHeight" not in src.variables:
            raise RuntimeError(
                f"{source}: iLayerHeight is missing"
            )

        if "hruId" not in src.variables:
            raise RuntimeError(
                f"{source}: hruId is missing"
            )

        old_interfaces = np.asarray(
            src.variables["iLayerHeight"][:]
        ).squeeze()

        if old_interfaces.ndim != 1:
            raise RuntimeError(
                f"{source}: unexpected iLayerHeight shape"
            )

        if old_interfaces[-1] < NEW_INTERFACES[-1]:
            raise RuntimeError(
                f"{source}: original soil depth "
                f"{old_interfaces[-1]} m is less than 1.0 m"
            )

        if output.exists():
            output.unlink()

        with Dataset(output, "w", format=src.file_format) as dst:

            # ------------------------------------------------
            # Dimensions
            # ------------------------------------------------
            for name, dim in src.dimensions.items():

                if name == "midSoil":
                    dst.createDimension("midSoil", 3)

                elif name == "midToto":
                    dst.createDimension("midToto", 3)

                elif name == "ifcToto":
                    dst.createDimension("ifcToto", 4)

                else:
                    dst.createDimension(
                        name,
                        None if dim.isunlimited() else len(dim)
                    )

            # ------------------------------------------------
            # Global attributes
            # ------------------------------------------------
            for attr in src.ncattrs():
                dst.setncattr(attr, src.getncattr(attr))

            dst.setncattr(
                "Soil_layer_configuration",
                "3 layers: 0-0.2, 0.2-0.5, 0.5-1.0 m"
            )

            # ------------------------------------------------
            # Copy ordinary variables
            # ------------------------------------------------
            for name, var in src.variables.items():

                if name in LAYER_VARIABLES or name == "nSoil":
                    continue

                # Skip any unexpected variable that explicitly
                # depends on old vertical dimensions.
                if any(
                    d in ("midSoil", "midToto", "ifcToto")
                    for d in var.dimensions
                ):
                    print(
                        f"WARNING: skipping layer-dependent "
                        f"variable {name}",
                        file=sys.stderr
                    )
                    continue

                fill = getattr(var, "_FillValue", None)

                if fill is None:
                    newvar = dst.createVariable(
                        name,
                        var.datatype,
                        var.dimensions
                    )
                else:
                    newvar = dst.createVariable(
                        name,
                        var.datatype,
                        var.dimensions,
                        fill_value=fill
                    )

                for attr in var.ncattrs():
                    if attr != "_FillValue":
                        newvar.setncattr(
                            attr,
                            var.getncattr(attr)
                        )

                newvar[:] = var[:]

            # ------------------------------------------------
            # nSoil = 3
            # ------------------------------------------------
            old_nsoil = src.variables["nSoil"]

            fill = getattr(old_nsoil, "_FillValue", None)

            if fill is None:
                nsoil = dst.createVariable(
                    "nSoil",
                    old_nsoil.datatype,
                    old_nsoil.dimensions
                )
            else:
                nsoil = dst.createVariable(
                    "nSoil",
                    old_nsoil.datatype,
                    old_nsoil.dimensions,
                    fill_value=fill
                )

            for attr in old_nsoil.ncattrs():
                if attr != "_FillValue":
                    nsoil.setncattr(
                        attr,
                        old_nsoil.getncattr(attr)
                    )

            nsoil[:] = 3

            # ------------------------------------------------
            # Layer interfaces
            # ------------------------------------------------
            old_var = src.variables["iLayerHeight"]

            ivar = dst.createVariable(
                "iLayerHeight",
                old_var.datatype,
                old_var.dimensions
            )

            for attr in old_var.ncattrs():
                if attr != "_FillValue":
                    ivar.setncattr(
                        attr,
                        old_var.getncattr(attr)
                    )

            # SUMMA convention here is (ifcToto, hru)
            if len(old_var.dimensions) == 2:
                nhru = len(src.dimensions["hru"])
                ivar[:] = np.tile(
                    NEW_INTERFACES[:, None],
                    (1, nhru)
                )
            else:
                ivar[:] = NEW_INTERFACES

            # ------------------------------------------------
            # Layer depths
            # ------------------------------------------------
            old_var = src.variables["mLayerDepth"]

            dvar = dst.createVariable(
                "mLayerDepth",
                old_var.datatype,
                old_var.dimensions
            )

            for attr in old_var.ncattrs():
                if attr != "_FillValue":
                    dvar.setncattr(
                        attr,
                        old_var.getncattr(attr)
                    )

            if len(old_var.dimensions) == 2:
                nhru = len(src.dimensions["hru"])
                dvar[:] = np.tile(
                    NEW_DEPTHS[:, None],
                    (1, nhru)
                )
            else:
                dvar[:] = NEW_DEPTHS

            # ------------------------------------------------
            # Remap layer-centred state variables
            # ------------------------------------------------
            for name in [
                "mLayerTemp",
                "mLayerVolFracIce",
                "mLayerVolFracLiq",
                "mLayerMatricHead",
            ]:

                old_var = src.variables[name]
                values = np.asarray(old_var[:])

                remapped = thickness_weighted_remap(
                    values,
                    old_interfaces,
                    NEW_INTERFACES
                )

                fill = getattr(old_var, "_FillValue", None)

                if fill is None:
                    newvar = dst.createVariable(
                        name,
                        old_var.datatype,
                        old_var.dimensions
                    )
                else:
                    newvar = dst.createVariable(
                        name,
                        old_var.datatype,
                        old_var.dimensions,
                        fill_value=fill
                    )

                for attr in old_var.ncattrs():
                    if attr != "_FillValue":
                        newvar.setncattr(
                            attr,
                            old_var.getncattr(attr)
                        )

                newvar[:] = remapped


def process_domain(domain_dir, activate=False):

    summa = domain_dir / "lumped/settings/SUMMA"
    current = summa / "coldState.nc"

    if not current.exists():
        return "MISSING"

    backup = summa / "coldState_8layer.nc"
    output = summa / "coldState_3layer.nc"

    # Preserve the ORIGINAL file only once.
    if not backup.exists():
        shutil.copy2(current, backup)

    # Always generate from preserved original.
    create_3layer_file(backup, output)

    if activate:
        shutil.copy2(output, current)

    return "OK"


def main():

    parser = argparse.ArgumentParser(
        description="Convert NWAM lumped SUMMA cold states "
                    "to the standard 3-layer soil profile."
    )

    parser.add_argument(
        "--root",
        required=True,
        help="Directory containing domain_CAN_* and domain_USA_*"
    )

    parser.add_argument(
        "--activate",
        action="store_true",
        help="Replace coldState.nc with the generated 3-layer "
             "version after preserving coldState_8layer.nc"
    )

    args = parser.parse_args()

    root = Path(args.root)

    domains = sorted(
        p for p in root.iterdir()
        if p.is_dir()
        and (
            p.name.startswith("domain_CAN_")
            or p.name.startswith("domain_USA_")
        )
    )

    ok = 0
    missing = 0
    failed = 0

    for domain in domains:

        try:
            status = process_domain(
                domain,
                activate=args.activate
            )

            if status == "OK":
                print(f"PASS  {domain.name}")
                ok += 1
            else:
                print(f"MISS  {domain.name}")
                missing += 1

        except Exception as exc:
            print(
                f"FAIL  {domain.name}: {exc}",
                file=sys.stderr
            )
            failed += 1

    print()
    print("========================================")
    print("3-LAYER COLD-STATE SUMMARY")
    print("========================================")
    print(f"Domains found : {len(domains)}")
    print(f"Converted     : {ok}")
    print(f"Missing       : {missing}")
    print(f"Failed        : {failed}")

    if args.activate:
        print("Active file   : coldState.nc = 3-layer")
    else:
        print("Active file   : unchanged")
        print("New file      : coldState_3layer.nc")


if __name__ == "__main__":
    main()