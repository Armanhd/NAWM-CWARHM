#!/usr/bin/env python3
# coding: utf-8

# Create coldState.nc for an NWAM-SUMMA domain.
#
# Purpose
# -------
# Create the SUMMA initial-condition NetCDF using the HRU ordering
# contained in the first forcing file listed in forcingFileList.txt.
#
# This guarantees that:
#
#   coldState.nc hruId
#
# exactly follows:
#
#   NWAM_SUMMA_forcing_YYYYMM.nc hruId
#
# IMPORTANT
# ---------
# This script reads the domain-specific control file supplied on the
# command line.
#
# It does NOT read or modify control_active.txt.
#
# Model assumptions retained from the CWARHM setup:
#
#   - 8 soil layers
#   - 0 initial snow layers
#   - prescribed initial canopy states
#   - prescribed initial soil temperatures
#   - prescribed liquid/ice fractions
#   - prescribed aquifer storage
#   - prescribed matric head
#
# Usage
# -----
#
# python 1_create_coldState.py \
#     /path/to/control_DOMAIN.txt

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

import netCDF4 as nc4
import numpy as np
import xarray as xr


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_create_coldState.py "
        "/path/to/control_DOMAIN.txt"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).resolve()


if not CONTROL_FILE.exists():

    raise FileNotFoundError(
        f"Control file not found:\n"
        f"{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(file, setting):
    """
    Read one setting using exact control-key matching.
    """

    with open(file) as contents:

        for line in contents:

            stripped = line.strip()

            if (
                not stripped
                or stripped.startswith("#")
                or "|" not in stripped
            ):
                continue

            left, right = stripped.split(
                "|",
                1
            )

            if left.strip() != setting:
                continue

            value = (
                right
                .split("#", 1)[0]
                .strip()
            )

            if value == "":
                raise ValueError(
                    f"Setting '{setting}' is empty in:\n"
                    f"{file}"
                )

            return value

    raise ValueError(
        f"Setting '{setting}' not found in:\n"
        f"{file}"
    )


def make_default_path(suffix):
    """
    Construct:
        <root_path>/domain_<domain_name>/<suffix>
    """

    root_path = Path(
        read_from_control(
            CONTROL_FILE,
            "root_path"
        )
    )

    domain_name = read_from_control(
        CONTROL_FILE,
        "domain_name"
    )

    return (
        root_path
        / f"domain_{domain_name}"
        / suffix
    )


def resolve_path(setting, default_suffix):
    """
    Resolve a control-file path that may be set to 'default'.
    """

    value = read_from_control(
        CONTROL_FILE,
        setting
    )

    if value == "default":

        return make_default_path(
            default_suffix
        )

    return Path(
        value
    )


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# PATHS
# ============================================================

forcing_path = resolve_path(
    "forcing_summa_path",
    "forcing/4_SUMMA_input"
)


settings_path = resolve_path(
    "settings_summa_path",
    "settings/SUMMA"
)


settings_path.mkdir(
    parents=True,
    exist_ok=True
)


coldstate_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_coldstate"
)


forcing_list_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_forcing_list"
)


coldstate_file = (
    settings_path
    / coldstate_name
)


forcing_list_file = (
    settings_path
    / forcing_list_name
)


# ============================================================
# VALIDATE FORCING INPUTS
# ============================================================

if not forcing_path.exists():

    raise FileNotFoundError(
        "SUMMA forcing directory not found:\n"
        f"{forcing_path}"
    )


if not forcing_list_file.exists():

    raise FileNotFoundError(
        "SUMMA forcing-file list not found:\n"
        f"{forcing_list_file}\n\n"
        "Run 1_create_forcing_file_list.py after the complete "
        "forcing archive has been generated."
    )


with open(
    forcing_list_file
) as file:

    forcing_names = [
        line.strip()
        for line in file
        if line.strip()
        and not line.lstrip().startswith("#")
    ]


if not forcing_names:

    raise RuntimeError(
        "SUMMA forcing-file list is empty:\n"
        f"{forcing_list_file}"
    )


# Check for duplicate names.

if len(forcing_names) != len(
    set(forcing_names)
):

    raise RuntimeError(
        "Duplicate filenames were found in:\n"
        f"{forcing_list_file}"
    )


forcing_file = (
    forcing_path
    / forcing_names[0]
)


if not forcing_file.exists():

    raise FileNotFoundError(
        "First forcing file listed in forcingFileList.txt "
        "does not exist:\n"
        f"{forcing_file}"
    )


# ============================================================
# READ HRU ORDER FROM FIRST SUMMA FORCING FILE
# ============================================================

with xr.open_dataset(
    forcing_file
) as forcing:

    if "hru" not in forcing.dims:

        raise RuntimeError(
            "Forcing file does not contain an 'hru' dimension:\n"
            f"{forcing_file}"
        )


    if "hruId" not in forcing:

        raise RuntimeError(
            "hruId not found in forcing file:\n"
            f"{forcing_file}"
        )

    forcing_hru_ids = (
        np.asarray(
            forcing["hruId"].values
        )
        .reshape(-1)
    )
# ============================================================
# VALIDATE HRU IDS
# ============================================================

if forcing_hru_ids.ndim != 1:

    raise RuntimeError(
        "Forcing hruId must be one-dimensional.\n"
        f"Shape found: {forcing_hru_ids.shape}"
    )


if forcing_hru_ids.size == 0:

    raise RuntimeError(
        "No HRU IDs found in forcing file."
    )


try:

    forcing_hru_ids_float = (
        forcing_hru_ids
        .astype(np.float64)
    )

except Exception as exc:

    raise RuntimeError(
        "Forcing hruId values could not be converted "
        "to numeric values."
    ) from exc


if not np.all(
    np.isfinite(
        forcing_hru_ids_float
    )
):

    raise RuntimeError(
        "Non-finite HRU IDs found in forcing."
    )


# Make sure the values are actually integers before casting.

if not np.allclose(
    forcing_hru_ids_float,
    np.round(
        forcing_hru_ids_float
    )
):

    raise RuntimeError(
        "Forcing hruId contains non-integer values."
    )


forcing_hru_ids = (
    np.round(
        forcing_hru_ids_float
    )
    .astype(np.int64)
)


if len(
    np.unique(
        forcing_hru_ids
    )
) != len(
    forcing_hru_ids
):

    raise RuntimeError(
        "Duplicate hruId values found in forcing."
    )


num_hru = len(
    forcing_hru_ids
)


# ============================================================
# FORCING TIME STEP
# ============================================================

try:

    dt_init = float(
        read_from_control(
            CONTROL_FILE,
            "forcing_time_step_size"
        )
    )

except Exception as exc:

    raise ValueError(
        "forcing_time_step_size could not be converted "
        "to a numeric value."
    ) from exc


if (
    not np.isfinite(dt_init)
    or dt_init <= 0
):

    raise ValueError(
        "forcing_time_step_size must be finite "
        "and greater than zero."
    )


# ============================================================
# COLD-STATE MODEL ASSUMPTIONS
# ============================================================

# Number of active soil and snow layers.

nSoil = 8
nSnow = 0


# SUMMA cold-state dimensions.

midSoil = 8
midToto = 8
ifcToto = midToto + 1
scalarv = 1


# ------------------------------------------------------------
# Layer geometry
# ------------------------------------------------------------

mLayerDepth = np.asarray(
    [
        0.025,
        0.075,
        0.15,
        0.25,
        0.5,
        0.5,
        1.0,
        1.5,
    ],
    dtype=np.float64
)


iLayerHeight = np.asarray(
    [
        0.0,
        0.025,
        0.1,
        0.25,
        0.5,
        1.0,
        1.5,
        2.5,
        4.0,
    ],
    dtype=np.float64
)


if len(
    mLayerDepth
) != midToto:

    raise RuntimeError(
        "mLayerDepth length does not match midToto."
    )


if len(
    iLayerHeight
) != ifcToto:

    raise RuntimeError(
        "iLayerHeight length does not match ifcToto."
    )


if not np.isclose(
    np.sum(
        mLayerDepth
    ),
    iLayerHeight[-1]
):

    raise RuntimeError(
        "Soil-layer depths are inconsistent with "
        "the final interface height."
    )


# ============================================================
# INITIAL STATES
# ============================================================

scalarCanopyIce = 0.0
scalarCanopyLiq = 0.0

scalarSnowDepth = 0.0
scalarSWE = 0.0

scalarSfcMeltPond = 0.0

scalarAquiferStorage = 1.0

scalarSnowAlbedo = 0.0

scalarCanairTemp = 283.16
scalarCanopyTemp = 283.16

mLayerTemp = 283.16

mLayerVolFracIce = 0.0
mLayerVolFracLiq = 0.2

mLayerMatricHead = -1.0


# ============================================================
# NETCDF HELPERS
# ============================================================

def create_scalar_hru_variable(
    dataset,
    variable_name,
    value,
    dtype="f8"
):
    """
    Create a SUMMA scalar-state variable with dimensions:
        (scalarv, hru)
    """

    variable = dataset.createVariable(
        variable_name,
        dtype,
        (
            "scalarv",
            "hru"
        )
    )

    variable[:, :] = np.full(
        (
            scalarv,
            num_hru
        ),
        value
    )

    return variable


def create_layer_hru_variable(
    dataset,
    variable_name,
    value,
    layer_dimension,
    layer_count,
    dtype="f8"
):
    """
    Create a layer-state variable with dimensions:
        (<layer_dimension>, hru)
    """

    variable = dataset.createVariable(
        variable_name,
        dtype,
        (
            layer_dimension,
            "hru"
        )
    )

    variable[:, :] = np.full(
        (
            layer_count,
            num_hru
        ),
        value
    )

    return variable


def create_layer_geometry_variable(
    dataset,
    variable_name,
    values,
    layer_dimension,
    dtype="f8"
):
    """
    Repeat one vertical layer geometry vector for every HRU.

    Output shape:
        (<layer_dimension>, hru)
    """

    values = np.asarray(
        values,
        dtype=np.float64
    )


    variable = dataset.createVariable(
        variable_name,
        dtype,
        (
            layer_dimension,
            "hru"
        )
    )


    variable[:, :] = np.repeat(
        values[:, np.newaxis],
        num_hru,
        axis=1
    )

    return variable


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("CREATE SUMMA COLD STATE")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"Forcing list     : {forcing_list_file}"
)

print(
    f"Forcing template : {forcing_file}"
)

print(
    f"HRUs             : {num_hru}"
)

print(
    f"First HRU ID     : {forcing_hru_ids[0]}"
)

print(
    f"Last HRU ID      : {forcing_hru_ids[-1]}"
)

print(
    f"Initial timestep : {dt_init:g} s"
)

print(
    f"Soil layers      : {nSoil}"
)

print(
    f"Snow layers      : {nSnow}"
)

print(
    f"Output           : {coldstate_file}"
)


# ============================================================
# CREATE coldState.nc
# ============================================================

# Existing file is intentionally replaced only after all
# input validation above has passed.

with nc4.Dataset(
    coldstate_file,
    "w",
    format="NETCDF4"
) as cs:

    now = datetime.now()


    # --------------------------------------------------------
    # Global attributes
    # --------------------------------------------------------

    cs.setncattr(
        "Author",
        "NWAM-SUMMA workflow"
    )

    cs.setncattr(
        "History",
        "Created "
        + now.strftime(
            "%Y/%m/%d %H:%M:%S"
        )
    )

    cs.setncattr(
        "Purpose",
        "Initial SUMMA cold-state conditions"
    )

    cs.setncattr(
        "Domain",
        domain_name
    )

    cs.setncattr(
        "HRU_order_source",
        forcing_file.name
    )


    # --------------------------------------------------------
    # Dimensions
    # --------------------------------------------------------

    cs.createDimension(
        "hru",
        num_hru
    )

    cs.createDimension(
        "midSoil",
        midSoil
    )

    cs.createDimension(
        "midToto",
        midToto
    )

    cs.createDimension(
        "ifcToto",
        ifcToto
    )

    cs.createDimension(
        "scalarv",
        scalarv
    )


    # --------------------------------------------------------
    # HRU IDs
    # --------------------------------------------------------

    hru_variable = cs.createVariable(
        "hruId",
        "i8",
        ("hru",)
    )

    hru_variable.setncattr(
        "units",
        "-"
    )

    hru_variable.setncattr(
        "long_name",
        "Hydrological response unit identifier"
    )

    hru_variable[:] = (
        forcing_hru_ids
    )


    # --------------------------------------------------------
    # Initial timestep
    # --------------------------------------------------------

    variable = create_scalar_hru_variable(
        cs,
        "dt_init",
        dt_init,
        "f8"
    )

    variable.setncattr(
        "long_name",
        "Initial model timestep"
    )

    variable.setncattr(
        "units",
        "s"
    )


    # --------------------------------------------------------
    # Number of layers
    # --------------------------------------------------------

    variable = create_scalar_hru_variable(
        cs,
        "nSoil",
        nSoil,
        "i4"
    )

    variable.setncattr(
        "long_name",
        "Number of soil layers"
    )


    variable = create_scalar_hru_variable(
        cs,
        "nSnow",
        nSnow,
        "i4"
    )

    variable.setncattr(
        "long_name",
        "Number of snow layers"
    )


    # --------------------------------------------------------
    # Scalar states
    # --------------------------------------------------------

    scalar_states = {
        "scalarCanopyIce": scalarCanopyIce,
        "scalarCanopyLiq": scalarCanopyLiq,
        "scalarSnowDepth": scalarSnowDepth,
        "scalarSWE": scalarSWE,
        "scalarSfcMeltPond": scalarSfcMeltPond,
        "scalarAquiferStorage": scalarAquiferStorage,
        "scalarSnowAlbedo": scalarSnowAlbedo,
        "scalarCanairTemp": scalarCanairTemp,
        "scalarCanopyTemp": scalarCanopyTemp,
    }


    for name, value in scalar_states.items():

        create_scalar_hru_variable(
            cs,
            name,
            value,
            "f8"
        )


    # --------------------------------------------------------
    # Layer states
    # --------------------------------------------------------

    create_layer_hru_variable(
        cs,
        "mLayerTemp",
        mLayerTemp,
        "midToto",
        midToto,
        "f8"
    )


    create_layer_hru_variable(
        cs,
        "mLayerVolFracIce",
        mLayerVolFracIce,
        "midToto",
        midToto,
        "f8"
    )


    create_layer_hru_variable(
        cs,
        "mLayerVolFracLiq",
        mLayerVolFracLiq,
        "midToto",
        midToto,
        "f8"
    )


    create_layer_hru_variable(
        cs,
        "mLayerMatricHead",
        mLayerMatricHead,
        "midSoil",
        midSoil,
        "f8"
    )


    # --------------------------------------------------------
    # Layer geometry
    # --------------------------------------------------------

    create_layer_geometry_variable(
        cs,
        "iLayerHeight",
        iLayerHeight,
        "ifcToto",
        "f8"
    )


    create_layer_geometry_variable(
        cs,
        "mLayerDepth",
        mLayerDepth,
        "midToto",
        "f8"
    )


# ============================================================
# VERIFY SAVED OUTPUT
# ============================================================

with xr.open_dataset(
    coldstate_file
) as saved:

    required_dimensions = {
        "hru": num_hru,
        "midSoil": midSoil,
        "midToto": midToto,
        "ifcToto": ifcToto,
        "scalarv": scalarv,
    }


    for dimension, expected_size in (
        required_dimensions.items()
    ):

        if dimension not in saved.sizes:

            raise RuntimeError(
                "coldState.nc is missing required "
                f"dimension '{dimension}'."
            )


        if saved.sizes[
            dimension
        ] != expected_size:

            raise RuntimeError(
                "Unexpected dimension size in coldState.nc.\n"
                f"Dimension : {dimension}\n"
                f"Expected  : {expected_size}\n"
                f"Found     : {saved.sizes[dimension]}"
            )


    required_variables = [
        "hruId",
        "dt_init",
        "nSoil",
        "nSnow",
        "scalarCanopyIce",
        "scalarCanopyLiq",
        "scalarSnowDepth",
        "scalarSWE",
        "scalarSfcMeltPond",
        "scalarAquiferStorage",
        "scalarSnowAlbedo",
        "scalarCanairTemp",
        "scalarCanopyTemp",
        "mLayerTemp",
        "mLayerVolFracIce",
        "mLayerVolFracLiq",
        "mLayerMatricHead",
        "iLayerHeight",
        "mLayerDepth",
    ]


    missing_variables = [
        variable
        for variable in required_variables
        if variable not in saved
    ]


    if missing_variables:

        raise RuntimeError(
            "coldState.nc is missing variable(s):\n"
            + "\n".join(
                f"  {name}"
                for name in missing_variables
            )
        )


    saved_hru_ids = (
        saved["hruId"]
        .values
        .astype(np.int64)
    )


    if not np.array_equal(
        forcing_hru_ids,
        saved_hru_ids
    ):

        raise RuntimeError(
            "coldState.nc HRU order does not match "
            "the SUMMA forcing."
        )


    # Ensure key state variables contain finite values.

    variables_to_check = [
        "dt_init",
        "scalarCanopyIce",
        "scalarCanopyLiq",
        "scalarSnowDepth",
        "scalarSWE",
        "scalarAquiferStorage",
        "scalarCanairTemp",
        "scalarCanopyTemp",
        "mLayerTemp",
        "mLayerVolFracIce",
        "mLayerVolFracLiq",
        "mLayerMatricHead",
        "iLayerHeight",
        "mLayerDepth",
    ]


    for variable in variables_to_check:

        values = np.asarray(
            saved[
                variable
            ].values,
            dtype=np.float64
        )


        if not np.all(
            np.isfinite(
                values
            )
        ):

            raise RuntimeError(
                f"{variable} contains non-finite values "
                "in saved coldState.nc."
            )


# ============================================================
# LOGGING
# ============================================================

log_folder = (
    settings_path
    / "_workflow_log"
)


log_folder.mkdir(
    parents=True,
    exist_ok=True
)


this_file = Path(
    __file__
).name


copy2(
    Path(
        __file__
    ).resolve(),
    log_folder
    / this_file
)


copy2(
    CONTROL_FILE,
    log_folder
    / CONTROL_FILE.name
)


now = datetime.now()


log_file = (
    log_folder
    / (
        f"{now:%Y%m%d_%H%M%S}_"
        "create_summa_coldstate.txt"
    )
)


with open(
    log_file,
    "w"
) as file:

    file.write(
        f"Log generated by {this_file} "
        f"on {now:%Y/%m/%d %H:%M:%S}\n"
    )

    file.write(
        f"Domain: {domain_name}\n"
    )

    file.write(
        f"Control file: {CONTROL_FILE}\n"
    )

    file.write(
        f"Forcing list: {forcing_list_file}\n"
    )

    file.write(
        f"Forcing template: {forcing_file}\n"
    )

    file.write(
        f"HRUs: {num_hru}\n"
    )

    file.write(
        f"First HRU ID: {forcing_hru_ids[0]}\n"
    )

    file.write(
        f"Last HRU ID: {forcing_hru_ids[-1]}\n"
    )

    file.write(
        f"Soil layers: {nSoil}\n"
    )

    file.write(
        f"Snow layers: {nSnow}\n"
    )

    file.write(
        f"Initial timestep: {dt_init:g} s\n"
    )

    file.write(
        f"coldState file: {coldstate_file}\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("SUMMA COLD STATE CREATION COMPLETED")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"HRUs             : {num_hru}"
)

print(
    f"First HRU ID     : {forcing_hru_ids[0]}"
)

print(
    f"Last HRU ID      : {forcing_hru_ids[-1]}"
)

print(
    f"Soil layers      : {nSoil}"
)

print(
    f"Snow layers      : {nSnow}"
)

print(
    f"Initial timestep : {dt_init:g} s"
)

print(
    "HRU order        : matches SUMMA forcing"
)

print(
    f"Output           : {coldstate_file}"
)

print(
    f"Workflow log     : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)