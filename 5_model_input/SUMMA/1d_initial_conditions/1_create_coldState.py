# Create coldState.nc for the active NWAM-SUMMA domain.
#
# HRU ordering is read from the first forcing file listed in
# forcingFileList.txt so that coldState.nc exactly follows the
# forcing HRU order used by SUMMA.
#
# Model assumptions retained from the CWARHM setup:
#   - 8 soil layers
#   - 0 initial snow layers
#   - prescribed initial canopy, snow, aquifer, temperature,
#     liquid-water, ice and matric-head states
#
# These are initialization/model assumptions rather than
# domain-specific paths.

from pathlib import Path
from datetime import datetime
from shutil import copy2

import numpy as np
import xarray as xr
import netCDF4 as nc4


# ============================================================
# PROJECT / CONTROL FILE
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

# Script:
# CWARHM/5_model_input/SUMMA/1d_initial_conditions/
# 1_create_coldState.py
CWARHM_ROOT = SCRIPT_DIR.parents[2]

CONTROL_FILE = (
    CWARHM_ROOT
    / "0_control_files"
    / "control_active.txt"
)

if not CONTROL_FILE.exists():
    raise FileNotFoundError(
        f"Control file not found:\n{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(file, setting):

    with open(file) as contents:

        for line in contents:

            stripped = line.strip()

            if (
                stripped
                and not stripped.startswith("#")
                and "|" in stripped
            ):

                left, right = stripped.split("|", 1)

                if left.strip() != setting:
                    continue

                return (
                    right
                    .split("#", 1)[0]
                    .strip()
                )

    raise ValueError(
        f"Setting not found in control file: {setting}"
    )


def make_default_path(suffix):

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

    value = read_from_control(
        CONTROL_FILE,
        setting
    )

    if value == "default":
        return make_default_path(
            default_suffix
        )

    return Path(value)


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
# VALIDATE FORCING FILE LIST
# ============================================================

if not forcing_path.exists():

    raise FileNotFoundError(
        f"SUMMA forcing directory not found:\n"
        f"{forcing_path}"
    )


if not forcing_list_file.exists():

    raise FileNotFoundError(
        f"Forcing file list not found:\n"
        f"{forcing_list_file}\n"
        "Run Step 18 first."
    )


with open(
    forcing_list_file
) as file:

    forcing_names = [
        line.strip()
        for line in file
        if line.strip()
    ]


if not forcing_names:

    raise RuntimeError(
        f"Forcing file list is empty:\n"
        f"{forcing_list_file}"
    )


forcing_file = (
    forcing_path
    / forcing_names[0]
)


if not forcing_file.exists():

    raise FileNotFoundError(
        f"First forcing file listed in "
        f"forcingFileList.txt does not exist:\n"
        f"{forcing_file}"
    )


# ============================================================
# READ HRU ORDER FROM FORCING
# ============================================================

with xr.open_dataset(
    forcing_file
) as forcing:

    if "hruId" not in forcing:

        raise RuntimeError(
            f"hruId not found in forcing file:\n"
            f"{forcing_file}"
        )

    forcing_hru_ids = np.asarray(
        forcing["hruId"].values
    )


forcing_hru_ids = (
    forcing_hru_ids
    .squeeze()
)


if forcing_hru_ids.ndim != 1:

    raise RuntimeError(
        "Forcing hruId must be one-dimensional. "
        f"Shape found: {forcing_hru_ids.shape}"
    )


if len(forcing_hru_ids) == 0:

    raise RuntimeError(
        "No HRU IDs found in forcing file."
    )


if not np.all(
    np.isfinite(forcing_hru_ids)
):

    raise RuntimeError(
        "Non-finite HRU IDs found in forcing."
    )


forcing_hru_ids = (
    forcing_hru_ids
    .astype(np.int64)
)


if len(np.unique(forcing_hru_ids)) != len(
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

dt_init = float(
    read_from_control(
        CONTROL_FILE,
        "forcing_time_step_size"
    )
)


if dt_init <= 0:

    raise ValueError(
        "forcing_time_step_size must be positive."
    )


# ============================================================
# COLD-STATE MODEL ASSUMPTIONS
# ============================================================

nSoil = 8
nSnow = 0

midSoil = 8
midToto = 8
ifcToto = midToto + 1
scalarv = 1


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


if len(mLayerDepth) != midToto:

    raise RuntimeError(
        "mLayerDepth length does not match midToto."
    )


if len(iLayerHeight) != ifcToto:

    raise RuntimeError(
        "iLayerHeight length does not match ifcToto."
    )


# Initial states

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
# NETCDF HELPER
# ============================================================

def create_and_fill_nc_var(
    nc,
    variable_name,
    variable_value,
    dim1,
    dim2,
    variable_dimension,
    variable_type
):

    if variable_name in [
        "iLayerHeight",
        "mLayerDepth"
    ]:

        values = np.full(
            (dim1, dim2),
            variable_value
        ).transpose()

    else:

        values = np.full(
            (dim1, dim2),
            variable_value
        )


    nc_variable = nc.createVariable(
        variable_name,
        variable_type,
        (
            variable_dimension,
            "hru"
        )
    )

    nc_variable[:] = values


# ============================================================
# REPORT
# ============================================================

print()
print("============================================================")
print("CREATE SUMMA COLD STATE")
print("============================================================")
print(f"Domain           : {domain_name}")
print(f"Forcing template : {forcing_file}")
print(f"HRUs             : {num_hru}")
print(f"First HRU ID     : {forcing_hru_ids[0]}")
print(f"Last HRU ID      : {forcing_hru_ids[-1]}")
print(f"Initial timestep : {dt_init} s")
print(f"Soil layers      : {nSoil}")
print(f"Output           : {coldstate_file}")


# ============================================================
# CREATE coldState.nc
# ============================================================

with nc4.Dataset(
    coldstate_file,
    "w",
    format="NETCDF4"
) as cs:

    now = datetime.now()

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
        "HRU_order_source",
        forcing_file.name
    )


    # Dimensions

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


    # HRU IDs

    variable = cs.createVariable(
        "hruId",
        "i8",
        ("hru",)
    )

    variable.setncattr(
        "units",
        "-"
    )

    variable.setncattr(
        "long_name",
        "Index of hydrological response unit (HRU)"
    )

    variable[:] = (
        forcing_hru_ids
    )


    # Initial timestep

    create_and_fill_nc_var(
        cs,
        "dt_init",
        dt_init,
        1,
        num_hru,
        "scalarv",
        "f8"
    )


    # Number of layers

    create_and_fill_nc_var(
        cs,
        "nSoil",
        nSoil,
        1,
        num_hru,
        "scalarv",
        "i4"
    )

    create_and_fill_nc_var(
        cs,
        "nSnow",
        nSnow,
        1,
        num_hru,
        "scalarv",
        "i4"
    )


    # Scalar states

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

        create_and_fill_nc_var(
            cs,
            name,
            value,
            1,
            num_hru,
            "scalarv",
            "f8"
        )


    # Layer states

    create_and_fill_nc_var(
        cs,
        "mLayerTemp",
        mLayerTemp,
        midToto,
        num_hru,
        "midToto",
        "f8"
    )

    create_and_fill_nc_var(
        cs,
        "mLayerVolFracIce",
        mLayerVolFracIce,
        midToto,
        num_hru,
        "midToto",
        "f8"
    )

    create_and_fill_nc_var(
        cs,
        "mLayerVolFracLiq",
        mLayerVolFracLiq,
        midToto,
        num_hru,
        "midToto",
        "f8"
    )

    create_and_fill_nc_var(
        cs,
        "mLayerMatricHead",
        mLayerMatricHead,
        midSoil,
        num_hru,
        "midSoil",
        "f8"
    )


    # Layer geometry

    create_and_fill_nc_var(
        cs,
        "iLayerHeight",
        iLayerHeight,
        num_hru,
        ifcToto,
        "ifcToto",
        "f8"
    )

    create_and_fill_nc_var(
        cs,
        "mLayerDepth",
        mLayerDepth,
        num_hru,
        midToto,
        "midToto",
        "f8"
    )


# ============================================================
# VERIFY OUTPUT
# ============================================================

with xr.open_dataset(
    coldstate_file
) as ds:

    output_hru_ids = (
        ds["hruId"]
        .values
        .astype(np.int64)
    )


if not np.array_equal(
    forcing_hru_ids,
    output_hru_ids
):

    raise RuntimeError(
        "coldState.nc HRU order does not match forcing."
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


this_file = Path(__file__).name

copy2(
    Path(__file__).resolve(),
    log_folder / this_file
)


now = datetime.now()

log_file = (
    log_folder
    / f"{now:%Y%m%d}_make_initial_conditions_file.txt"
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
        f"Forcing template: "
        f"{forcing_file.name}\n"
    )

    file.write(
        f"HRUs: {num_hru}\n"
    )

    file.write(
        f"Soil layers: {nSoil}\n"
    )

    file.write(
        f"Cold-state file: "
        f"{coldstate_file}\n"
    )


print()
print("coldState.nc created successfully.")
print(f"HRUs: {num_hru}")
print(f"Output: {coldstate_file}")