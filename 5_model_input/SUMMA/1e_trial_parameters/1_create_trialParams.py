#!/usr/bin/env python3
# coding: utf-8

# Create trialParams.nc for an NWAM-SUMMA domain.
#
# Purpose
# -------
# Create the SUMMA trial-parameter NetCDF using the HRU ordering
# from the first forcing file listed in forcingFileList.txt.
#
# This guarantees that:
#
#   trialParams.nc hruId
#
# exactly follows:
#
#   NWAM_SUMMA_forcing_YYYYMM.nc hruId
#
# Trial parameters are defined in the supplied control file:
#
#   settings_summa_trialParam_n
#   settings_summa_trialParam_1
#   settings_summa_trialParam_2
#   ...
#
# A parameter setting may contain:
#
#   parameter,value
#
# which assigns the same value to every HRU, or:
#
#   parameter,value1,value2,...,valueN
#
# where N must equal the number of HRUs.
#
# IMPORTANT
# ---------
# This script reads the domain-specific control file supplied on
# the command line.
#
# It does NOT read or modify control_active.txt.
#
# Usage
# -----
#
# python 1_create_trialParams.py \
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
        "python 1_create_trialParams.py "
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
# READ NUMBER OF TRIAL PARAMETERS
# ============================================================

try:

    num_trial_parameters = int(
        read_from_control(
            CONTROL_FILE,
            "settings_summa_trialParam_n"
        )
    )

except Exception as exc:

    raise ValueError(
        "settings_summa_trialParam_n must be "
        "an integer."
    ) from exc


if num_trial_parameters < 0:

    raise ValueError(
        "settings_summa_trialParam_n "
        "cannot be negative."
    )


# ============================================================
# READ TRIAL PARAMETERS
# ============================================================

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
    ]


    if len(pieces) < 2:

        raise ValueError(
            f"{setting_name} must contain at least:\n"
            "parameter,value"
        )


    parameter_name = pieces[0]


    if parameter_name == "":

        raise ValueError(
            f"{setting_name} contains an empty "
            "parameter name."
        )


    if parameter_name in trial_parameters:

        raise ValueError(
            "Duplicate trial parameter found:\n"
            f"{parameter_name}"
        )


    value_strings = pieces[1:]


    if any(
        value == ""
        for value in value_strings
    ):

        raise ValueError(
            f"{setting_name} contains an empty "
            "parameter value:\n"
            f"{parameter_setting}"
        )


    try:

        values = np.asarray(
            [
                float(value)
                for value in value_strings
            ],
            dtype=np.float64
        )

    except ValueError as exc:

        raise ValueError(
            "Non-numeric trial-parameter value found.\n"
            f"Setting : {setting_name}\n"
            f"Value   : {parameter_setting}"
        ) from exc


    if not np.all(
        np.isfinite(
            values
        )
    ):

        raise ValueError(
            f"{parameter_name} contains non-finite "
            "trial-parameter values."
        )


    # --------------------------------------------------------
    # One value -> same parameter for all HRUs
    # --------------------------------------------------------

    if len(values) == 1:

        values = np.full(
            num_hru,
            values[0],
            dtype=np.float64
        )


    # --------------------------------------------------------
    # Multiple values -> one value for every HRU
    # --------------------------------------------------------

    elif len(values) != num_hru:

        raise ValueError(
            f"Trial parameter '{parameter_name}' specifies "
            f"{len(values)} values, but the domain contains "
            f"{num_hru} HRUs.\n\n"
            "Supply either:\n"
            "  1 value for all HRUs\n"
            "or\n"
            f"  exactly {num_hru} HRU-specific values."
        )


    trial_parameters[
        parameter_name
    ] = values


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("CREATE SUMMA TRIAL PARAMETERS")
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
    f"Trial parameters : {num_trial_parameters}"
)


if trial_parameters:

    print()

    for (
        name,
        values
    ) in trial_parameters.items():

        if np.allclose(
            values,
            values[0]
        ):

            print(
                f"  {name} = "
                f"{values[0]:g} "
                "(all HRUs)"
            )

        else:

            print(
                f"  {name} = "
                "HRU-specific values"
            )

            print(
                f"    min = {values.min():g}"
            )

            print(
                f"    max = {values.max():g}"
            )

else:

    print()
    print(
        "  No trial parameters specified."
    )


print()

print(
    f"Output           : {trialparams_file}"
)


# ============================================================
# CREATE trialParams.nc
# ============================================================

# Existing output is replaced only after all input and
# control-file validation above has passed.

with nc4.Dataset(
    trialparams_file,
    "w",
    format="NETCDF4"
) as tp:

    now = datetime.now()


    # --------------------------------------------------------
    # Global attributes
    # --------------------------------------------------------

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
        "Domain",
        domain_name
    )

    tp.setncattr(
        "HRU_order_source",
        forcing_file.name
    )


    # --------------------------------------------------------
    # Dimension
    # --------------------------------------------------------

    tp.createDimension(
        "hru",
        num_hru
    )


    # --------------------------------------------------------
    # HRU IDs
    # --------------------------------------------------------

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
        "Hydrological response unit identifier"
    )

    variable[:] = (
        forcing_hru_ids
    )


    # --------------------------------------------------------
    # Trial parameters
    # --------------------------------------------------------

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
) as saved:

    # --------------------------------------------------------
    # HRU dimension
    # --------------------------------------------------------

    if "hru" not in saved.sizes:

        raise RuntimeError(
            "trialParams.nc is missing the "
            "'hru' dimension."
        )


    if saved.sizes[
        "hru"
    ] != num_hru:

        raise RuntimeError(
            "trialParams.nc has the wrong HRU count.\n"
            f"Expected : {num_hru}\n"
            f"Found    : {saved.sizes['hru']}"
        )


    # --------------------------------------------------------
    # HRU ID
    # --------------------------------------------------------

    if "hruId" not in saved:

        raise RuntimeError(
            "hruId is missing from trialParams.nc."
        )


    output_hru_ids = (
        saved[
            "hruId"
        ]
        .values
        .astype(np.int64)
    )


    if not np.array_equal(
        forcing_hru_ids,
        output_hru_ids
    ):

        raise RuntimeError(
            "trialParams.nc HRU order does not "
            "match SUMMA forcing."
        )


    # --------------------------------------------------------
    # Trial parameters
    # --------------------------------------------------------

    for (
        parameter_name,
        expected_values
    ) in trial_parameters.items():

        if parameter_name not in saved:

            raise RuntimeError(
                "Trial parameter missing from "
                f"saved NetCDF: {parameter_name}"
            )


        saved_values = np.asarray(
            saved[
                parameter_name
            ].values,
            dtype=np.float64
        )


        if saved_values.shape != (
            num_hru,
        ):

            raise RuntimeError(
                f"{parameter_name} has an unexpected "
                "shape in trialParams.nc.\n"
                f"Expected : {(num_hru,)}\n"
                f"Found    : {saved_values.shape}"
            )


        if not np.all(
            np.isfinite(
                saved_values
            )
        ):

            raise RuntimeError(
                f"{parameter_name} contains non-finite "
                "values in trialParams.nc."
            )


        if not np.allclose(
            saved_values,
            expected_values,
            rtol=0.0,
            atol=0.0
        ):

            raise RuntimeError(
                "Saved trial-parameter values do not "
                "match the values requested in the "
                f"control file for {parameter_name}."
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
        "create_summa_trial_params.txt"
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
        f"Trial parameters: "
        f"{num_trial_parameters}\n"
    )


    for (
        name,
        values
    ) in trial_parameters.items():

        if np.allclose(
            values,
            values[0]
        ):

            file.write(
                f"{name}: {values[0]:g} "
                "(all HRUs)\n"
            )

        else:

            file.write(
                f"{name}: HRU-specific; "
                f"min={values.min():g}; "
                f"max={values.max():g}\n"
            )


    file.write(
        f"trialParams file: {trialparams_file}\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("SUMMA TRIAL PARAMETERS CREATION COMPLETED")
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
    f"Trial parameters : {num_trial_parameters}"
)

print(
    "HRU order        : matches SUMMA forcing"
)

print(
    f"Output           : {trialparams_file}"
)

print(
    f"Workflow log     : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)