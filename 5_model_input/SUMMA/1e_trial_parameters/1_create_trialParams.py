# Create trialParams.nc for the active NWAM-SUMMA domain.
#
# HRU ordering is taken from the first forcing file listed in
# forcingFileList.txt so that trialParams.nc follows exactly
# the same HRU order as SUMMA forcing.
#
# Trial parameters are defined in control_active.txt:
#
#   settings_summa_trialParam_n
#   settings_summa_trialParam_1
#   settings_summa_trialParam_2
#   ...
#
# A parameter can contain:
#   parameter,value
#
# which assigns the same value to every HRU, or:
#
#   parameter,value1,value2,...,valueN
#
# where N must equal the number of HRUs.

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
# CWARHM/5_model_input/SUMMA/1e_trial_parameters/
# 1_create_trialParams.py
CWARHM_ROOT = SCRIPT_DIR.parents[2]

CONTROL_FILE = (
    CWARHM_ROOT
    / "0_control_files"
    / "control_active.txt"
)

if not CONTROL_FILE.exists():

    raise FileNotFoundError(
        f"Control file not found:\n"
        f"{CONTROL_FILE}"
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

                left, right = stripped.split(
                    "|",
                    1
                )

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

    return Path(
        value
    )


# ============================================================
# DOMAIN / PATHS
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


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


trialparams_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_trialParams"
)

forcing_list_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_forcing_list"
)


trialparams_file = (
    settings_path
    / trialparams_name
)

forcing_list_file = (
    settings_path
    / forcing_list_name
)


# ============================================================
# FIND FORCING TEMPLATE
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
        "forcingFileList.txt is empty."
    )


forcing_file = (
    forcing_path
    / forcing_names[0]
)


if not forcing_file.exists():

    raise FileNotFoundError(
        f"Forcing template not found:\n"
        f"{forcing_file}"
    )


# ============================================================
# READ HRU ORDER
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
        f"hruId must be one-dimensional. "
        f"Found shape: {forcing_hru_ids.shape}"
    )


if len(forcing_hru_ids) == 0:

    raise RuntimeError(
        "No HRU IDs found in forcing."
    )


if not np.all(
    np.isfinite(forcing_hru_ids)
):

    raise RuntimeError(
        "Non-finite hruId values found."
    )


forcing_hru_ids = (
    forcing_hru_ids
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
# READ TRIAL PARAMETERS
# ============================================================

num_trial_parameters = int(
    read_from_control(
        CONTROL_FILE,
        "settings_summa_trialParam_n"
    )
)


if num_trial_parameters < 0:

    raise ValueError(
        "settings_summa_trialParam_n "
        "cannot be negative."
    )


trial_parameters = {}


for index in range(
    1,
    num_trial_parameters + 1
):

    setting_name = (
        f"settings_summa_trialParam_{index}"
    )

    parameter_setting = (
        read_from_control(
            CONTROL_FILE,
            setting_name
        )
    )


    pieces = [
        item.strip()
        for item in parameter_setting.split(",")
        if item.strip()
    ]


    if len(pieces) < 2:

        raise ValueError(
            f"{setting_name} must contain "
            f"'parameter,value'."
        )


    parameter_name = pieces[0]


    if parameter_name in trial_parameters:

        raise ValueError(
            f"Duplicate trial parameter: "
            f"{parameter_name}"
        )


    try:

        values = np.asarray(
            [
                float(value)
                for value in pieces[1:]
            ],
            dtype=np.float64
        )

    except ValueError as exc:

        raise ValueError(
            f"Non-numeric value found in "
            f"{setting_name}: "
            f"{parameter_setting}"
        ) from exc


    # One value means apply it to all HRUs.

    if len(values) == 1:

        values = np.full(
            num_hru,
            values[0],
            dtype=np.float64
        )


    # Multiple values must provide one value per HRU.

    elif len(values) != num_hru:

        raise ValueError(
            f"{parameter_name} specifies "
            f"{len(values)} values, but the "
            f"domain has {num_hru} HRUs. "
            "Use either one value or exactly "
            "one value per HRU."
        )


    trial_parameters[
        parameter_name
    ] = values


# ============================================================
# REPORT
# ============================================================

print()
print("============================================================")
print("CREATE SUMMA TRIAL PARAMETERS")
print("============================================================")
print(f"Domain           : {domain_name}")
print(f"Forcing template : {forcing_file}")
print(f"HRUs             : {num_hru}")
print(f"Trial parameters : {num_trial_parameters}")

if trial_parameters:

    for name, values in trial_parameters.items():

        if np.all(
            values == values[0]
        ):

            print(
                f"  {name} = "
                f"{values[0]} "
                f"(all HRUs)"
            )

        else:

            print(
                f"  {name} = "
                f"HRU-specific values"
            )

else:

    print(
        "  None specified."
    )


print(f"Output           : {trialparams_file}")


# ============================================================
# CREATE trialParams.nc
# ============================================================

with nc4.Dataset(
    trialparams_file,
    "w",
    format="NETCDF4"
) as tp:

    now = datetime.now()

    tp.setncattr(
        "Author",
        "NWAM-SUMMA workflow"
    )

    tp.setncattr(
        "History",
        "Created "
        + now.strftime(
            "%Y/%m/%d %H:%M:%S"
        )
    )

    tp.setncattr(
        "Purpose",
        "SUMMA trial parameter values"
    )

    tp.setncattr(
        "HRU_order_source",
        forcing_file.name
    )


    # Dimension

    tp.createDimension(
        "hru",
        num_hru
    )


    # HRU IDs

    variable = tp.createVariable(
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


    # Trial parameters

    for (
        parameter_name,
        values
    ) in trial_parameters.items():

        variable = tp.createVariable(
            parameter_name,
            "f8",
            ("hru",)
        )

        variable[:] = (
            values
        )


# ============================================================
# VERIFY OUTPUT
# ============================================================

with xr.open_dataset(
    trialparams_file
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
        "trialParams.nc HRU order "
        "does not match forcing."
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
    / f"{now:%Y%m%d}_make_trial_parameter_file.txt"
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
        f"Trial parameters: "
        f"{num_trial_parameters}\n"
    )

    for name in trial_parameters:

        file.write(
            f"Parameter: {name}\n"
        )


print()
print("trialParams.nc created successfully.")
print(f"HRUs: {num_hru}")
print(
    f"Trial parameters: "
    f"{num_trial_parameters}"
)
print(f"Output: {trialparams_file}")