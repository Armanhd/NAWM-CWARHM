#!/usr/bin/env python3
# coding: utf-8

"""
Create a lumped SUMMA coldState.nc from a reference cold state.

Purpose
-------
This utility is intended for controlled SUMMA experiments where the newly
generated lumped CWARHM/NWAM configuration must retain the vertical-state
structure and physical initial conditions of an existing reference
SUMMA experiment.

The script:

1. reads the single HRU ID from the new lumped attributes.nc;
2. validates the reference coldState.nc;
3. copies the reference coldState.nc to a new output file;
4. changes only hruId in the copied file so that it matches attributes.nc;
5. preserves all physical cold-state variables and dimensions;
6. records provenance as global NetCDF attributes;
7. verifies the resulting file.

The reference coldState.nc is never modified.

Example
-------
python update_lumped_coldstate_layers.py \\
    --reference-coldstate /path/to/reference/coldState.nc \\
    --attributes /path/to/new/lumped/attributes.nc \\
    --output /path/to/output/coldState.nc

Optional strict layer check:

python update_lumped_coldstate_layers.py \\
    --reference-coldstate /path/to/reference/coldState.nc \\
    --attributes /path/to/attributes.nc \\
    --output /path/to/coldState.nc \\
    --expected-midsoil 3 \\
    --expected-midtoto 3 \\
    --expected-ifctoto 4 \\
    --overwrite
"""

from pathlib import Path
import argparse
import shutil
import sys
from datetime import datetime

import numpy as np
from netCDF4 import Dataset


# ============================================================
# HELPERS
# ============================================================

def read_single_hru_id(path):
    """
    Read exactly one hruId from a NetCDF file.
    """

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(
            f"NetCDF file not found:\n{path}"
        )

    with Dataset(path, "r") as ds:

        if "hruId" not in ds.variables:
            raise RuntimeError(
                f"hruId variable missing from:\n{path}"
            )

        values = np.asarray(
            ds.variables["hruId"][:]
        ).reshape(-1)

        if len(values) != 1:
            raise RuntimeError(
                "Expected exactly one HRU.\n"
                f"File : {path}\n"
                f"Found: {len(values)}"
            )

        if not np.isfinite(values[0]):
            raise RuntimeError(
                f"Invalid hruId in:\n{path}"
            )

        return int(values[0])


def read_dimensions(path):
    """
    Return selected cold-state dimensions.
    """

    wanted = [
        "hru",
        "gru",
        "midSoil",
        "midToto",
        "ifcToto",
    ]

    result = {}

    with Dataset(path, "r") as ds:

        for name in wanted:

            if name in ds.dimensions:
                result[name] = len(
                    ds.dimensions[name]
                )

    return result


def validate_reference_coldstate(
    path,
    expected_midsoil=None,
    expected_midtoto=None,
    expected_ifctoto=None,
):
    """
    Validate the reference coldState.nc.
    """

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(
            "Reference coldState.nc not found:\n"
            f"{path}"
        )

    with Dataset(path, "r") as ds:

        if "hru" not in ds.dimensions:
            raise RuntimeError(
                "Reference coldState has no hru dimension:\n"
                f"{path}"
            )

        if len(ds.dimensions["hru"]) != 1:
            raise RuntimeError(
                "Reference coldState must contain exactly "
                "one HRU.\n"
                f"Found: {len(ds.dimensions['hru'])}\n"
                f"File : {path}"
            )

        if "hruId" not in ds.variables:
            raise RuntimeError(
                "Reference coldState has no hruId variable:\n"
                f"{path}"
            )

        checks = {
            "midSoil": expected_midsoil,
            "midToto": expected_midtoto,
            "ifcToto": expected_ifctoto,
        }

        for dim_name, expected in checks.items():

            if expected is None:
                continue

            if dim_name not in ds.dimensions:
                raise RuntimeError(
                    f"Expected dimension '{dim_name}' is "
                    f"missing from:\n{path}"
                )

            actual = len(
                ds.dimensions[dim_name]
            )

            if actual != expected:
                raise RuntimeError(
                    "Reference coldState layer structure "
                    "does not match expectation.\n"
                    f"Dimension: {dim_name}\n"
                    f"Expected : {expected}\n"
                    f"Found    : {actual}\n"
                    f"File     : {path}"
                )


def update_hru_id(
    coldstate_path,
    new_hru_id,
    reference_path,
    attributes_path,
):
    """
    Change only hruId in the copied coldState.nc and
    add provenance metadata.
    """

    coldstate_path = Path(coldstate_path)

    with Dataset(
        coldstate_path,
        "r+"
    ) as ds:

        if "hruId" not in ds.variables:
            raise RuntimeError(
                f"hruId missing from:\n{coldstate_path}"
            )

        old_values = np.asarray(
            ds.variables["hruId"][:]
        ).reshape(-1)

        if len(old_values) != 1:
            raise RuntimeError(
                "Copied coldState must contain exactly "
                "one hruId."
            )

        old_hru_id = int(
            old_values[0]
        )

        ds.variables["hruId"][:] = [
            new_hru_id
        ]

        ds.setncattr(
            "CWARHM_reference_coldState",
            str(
                Path(reference_path)
                .resolve()
            )
        )

        ds.setncattr(
            "CWARHM_target_attributes",
            str(
                Path(attributes_path)
                .resolve()
            )
        )

        ds.setncattr(
            "CWARHM_original_hruId",
            old_hru_id
        )

        ds.setncattr(
            "CWARHM_updated_hruId",
            new_hru_id
        )

        ds.setncattr(
            "CWARHM_coldState_update",
            (
                "Reference physical cold-state values and "
                "vertical structure preserved; only hruId "
                "updated to match lumped attributes.nc."
            )
        )

        ds.setncattr(
            "CWARHM_coldState_update_time",
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

    return old_hru_id


def verify_output(
    output,
    target_hru_id,
    reference_dimensions,
):
    """
    Verify output HRU ID and preservation of dimensions.
    """

    output = Path(output)

    if not output.is_file():
        raise RuntimeError(
            f"Output coldState was not created:\n{output}"
        )

    output_hru_id = read_single_hru_id(
        output
    )

    if output_hru_id != target_hru_id:
        raise RuntimeError(
            "Output hruId does not match target.\n"
            f"Expected: {target_hru_id}\n"
            f"Found   : {output_hru_id}"
        )

    output_dimensions = read_dimensions(
        output
    )

    for name, reference_size in (
        reference_dimensions.items()
    ):

        output_size = output_dimensions.get(
            name
        )

        if output_size != reference_size:
            raise RuntimeError(
                "Cold-state dimension changed during copy.\n"
                f"Dimension : {name}\n"
                f"Reference : {reference_size}\n"
                f"Output    : {output_size}"
            )

    return output_dimensions


# ============================================================
# MAIN OPERATION
# ============================================================

def create_updated_coldstate(
    reference_coldstate,
    attributes,
    output,
    overwrite=False,
    expected_midsoil=None,
    expected_midtoto=None,
    expected_ifctoto=None,
):
    """
    Copy reference coldState and update only its hruId.
    """

    reference_coldstate = Path(
        reference_coldstate
    ).resolve()

    attributes = Path(
        attributes
    ).resolve()

    output = Path(
        output
    ).resolve()

    # --------------------------------------------------------
    # Validate inputs
    # --------------------------------------------------------

    if not attributes.is_file():
        raise FileNotFoundError(
            "Target attributes.nc not found:\n"
            f"{attributes}"
        )

    validate_reference_coldstate(
        reference_coldstate,
        expected_midsoil=expected_midsoil,
        expected_midtoto=expected_midtoto,
        expected_ifctoto=expected_ifctoto,
    )

    target_hru_id = read_single_hru_id(
        attributes
    )

    reference_hru_id = read_single_hru_id(
        reference_coldstate
    )

    reference_dimensions = read_dimensions(
        reference_coldstate
    )

    # --------------------------------------------------------
    # Output handling
    # --------------------------------------------------------

    if output.exists():

        if not overwrite:
            raise FileExistsError(
                "Output coldState already exists.\n"
                "Use --overwrite if replacement is "
                "intentional:\n"
                f"{output}"
            )

        output.unlink()

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Copy reference file
    # --------------------------------------------------------

    shutil.copy2(
        reference_coldstate,
        output
    )

    # --------------------------------------------------------
    # Change only hruId
    # --------------------------------------------------------

    copied_original_hru_id = update_hru_id(
        coldstate_path=output,
        new_hru_id=target_hru_id,
        reference_path=reference_coldstate,
        attributes_path=attributes,
    )

    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    output_dimensions = verify_output(
        output,
        target_hru_id,
        reference_dimensions,
    )

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("LUMPED COLDSTATE REFERENCE UPDATE")
    print("=" * 70)

    print(
        f"Reference coldState : "
        f"{reference_coldstate}"
    )

    print(
        f"Target attributes   : "
        f"{attributes}"
    )

    print(
        f"Output coldState    : "
        f"{output}"
    )

    print()

    print(
        f"Reference hruId     : "
        f"{reference_hru_id}"
    )

    print(
        f"Copied original ID  : "
        f"{copied_original_hru_id}"
    )

    print(
        f"Target/output hruId : "
        f"{target_hru_id}"
    )

    print()

    for name in [
        "hru",
        "gru",
        "midSoil",
        "midToto",
        "ifcToto",
    ]:

        if name in output_dimensions:

            print(
                f"{name:<18}: "
                f"{output_dimensions[name]}"
            )

    print()
    print(
        "Reference physical cold-state values and "
        "vertical structure were preserved."
    )

    print(
        "Only the copied hruId was updated."
    )

    print()
    print("PASS: LUMPED COLDSTATE UPDATE")
    print("=" * 70)


# ============================================================
# CLI
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Copy a reference SUMMA coldState.nc and "
            "update its single hruId to match a new "
            "lumped attributes.nc."
        )
    )

    parser.add_argument(
        "--reference-coldstate",
        required=True,
        help=(
            "Reference SUMMA coldState.nc whose "
            "physical state and layer structure "
            "should be preserved."
        ),
    )

    parser.add_argument(
        "--attributes",
        required=True,
        help=(
            "New lumped attributes.nc supplying "
            "the target hruId."
        ),
    )

    parser.add_argument(
        "--output",
        required=True,
        help=(
            "Output coldState.nc path."
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Replace the output file if it "
            "already exists."
        ),
    )

    parser.add_argument(
        "--expected-midsoil",
        type=int,
        default=None,
        help=(
            "Optional expected size of midSoil."
        ),
    )

    parser.add_argument(
        "--expected-midtoto",
        type=int,
        default=None,
        help=(
            "Optional expected size of midToto."
        ),
    )

    parser.add_argument(
        "--expected-ifctoto",
        type=int,
        default=None,
        help=(
            "Optional expected size of ifcToto."
        ),
    )

    args = parser.parse_args()

    try:

        create_updated_coldstate(
            reference_coldstate=(
                args.reference_coldstate
            ),
            attributes=args.attributes,
            output=args.output,
            overwrite=args.overwrite,
            expected_midsoil=(
                args.expected_midsoil
            ),
            expected_midtoto=(
                args.expected_midtoto
            ),
            expected_ifctoto=(
                args.expected_ifctoto
            ),
        )

    except Exception as exc:

        print()
        print("=" * 70)
        print("FAIL: LUMPED COLDSTATE UPDATE")
        print("=" * 70)

        print(
            str(exc),
            file=sys.stderr
        )

        sys.exit(1)


if __name__ == "__main__":
    main()