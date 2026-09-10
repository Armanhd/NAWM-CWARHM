#!/usr/bin/env python3
# coding: utf-8

"""
Create forcingFileList_LST.txt for one distributed CWARHM domain.

The input forcing is the already concatenated and UTC-to-LST converted
SUMMA forcing created by:

    3a_forcing/5_utc_to_lst/

Expected input:

    <root_path>/domain_<DOMAIN>/forcing/6_SUMMA_input_LST/
        NWAM_SUMMA_forcing_YYYYMM_YYYYMM_LST.nc

Output:

    <settings_summa_path>/forcingFileList_LST.txt

The existing UTC forcingFileList.txt is NOT modified.
"""

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

from netCDF4 import Dataset, num2date


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_create_forcing_file_list_LST.py "
        "/path/to/control_DOMAIN.txt"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).expanduser().resolve()


if not CONTROL_FILE.is_file():

    raise FileNotFoundError(
        f"Control file not found:\n{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(file, setting):

    with file.open() as contents:

        for line in contents:

            stripped = line.strip()

            if (
                not stripped
                or stripped.startswith("#")
                or "|" not in stripped
            ):
                continue

            left, right = stripped.split("|", 1)

            if left.strip() != setting:
                continue

            value = right.split("#", 1)[0].strip()

            if not value:

                raise ValueError(
                    f"Setting '{setting}' is empty in:\n{file}"
                )

            return value

    raise ValueError(
        f"Setting '{setting}' not found in:\n{file}"
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


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


root_path = Path(
    read_from_control(
        CONTROL_FILE,
        "root_path"
    )
)


# ============================================================
# SETTINGS PATH
# ============================================================

settings_path_setting = read_from_control(
    CONTROL_FILE,
    "settings_summa_path"
)


if settings_path_setting == "default":

    settings_path = make_default_path(
        "settings/SUMMA"
    )

else:

    settings_path = Path(
        settings_path_setting
    )


if not settings_path.is_dir():

    raise FileNotFoundError(
        "SUMMA settings directory not found:\n"
        f"{settings_path}"
    )


# ============================================================
# LST FORCING PATH
# ============================================================

forcing_path = make_default_path(
    "forcing/6_SUMMA_input_LST"
)


if not forcing_path.is_dir():

    raise FileNotFoundError(
        "LST forcing directory not found:\n"
        f"{forcing_path}"
    )


# ============================================================
# FIND CONCATENATED LST FORCING
# ============================================================

forcing_files = sorted(
    forcing_path.glob(
        "NWAM_SUMMA_forcing_*_*_LST.nc"
    )
)


if len(forcing_files) == 0:

    raise FileNotFoundError(
        "No concatenated LST SUMMA forcing file found in:\n"
        f"{forcing_path}"
    )


if len(forcing_files) > 1:

    raise RuntimeError(
        "Expected exactly one concatenated LST forcing file, "
        f"but found {len(forcing_files)}:\n"
        + "\n".join(
            f"  {file.name}"
            for file in forcing_files
        )
    )


forcing_file = forcing_files[0]


# ============================================================
# VALIDATE NETCDF
# ============================================================

required_variables = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "pptrate",
    "airtemp",
    "spechum",
    "windspd",
]


with Dataset(
    forcing_file,
    "r"
) as ds:

    if "time" not in ds.variables:

        raise RuntimeError(
            f"time variable missing:\n{forcing_file}"
        )

    if "hru" not in ds.dimensions:

        raise RuntimeError(
            f"hru dimension missing:\n{forcing_file}"
        )

    missing = [
        variable
        for variable in required_variables
        if variable not in ds.variables
    ]

    if missing:

        raise RuntimeError(
            "Required SUMMA variables missing:\n"
            + "\n".join(
                f"  {variable}"
                for variable in missing
            )
        )

    time_var = ds.variables["time"]

    dates = num2date(
        time_var[:],
        units=time_var.units,
        calendar=getattr(
            time_var,
            "calendar",
            "standard"
        ),
    )

    if len(dates) == 0:

        raise RuntimeError(
            "LST forcing contains no timesteps."
        )

    first_time = dates[0]
    last_time = dates[-1]

    num_time = len(dates)
    num_hru = len(
        ds.dimensions["hru"]
    )

    timezone = getattr(
        ds,
        "time_zone",
        "not recorded"
    )

    offset = getattr(
        ds,
        "utc_to_lst_offset_hours",
        "not recorded"
    )


# ============================================================
# WRITE FORCING LIST
# ============================================================

file_list_file = (
    settings_path
    / "forcingFileList_LST.txt"
)


file_list_file.write_text(
    forcing_file.name + "\n"
)


written = [
    line.strip()
    for line in file_list_file.read_text().splitlines()
    if line.strip()
]


if written != [forcing_file.name]:

    raise RuntimeError(
        "forcingFileList_LST.txt verification failed."
    )


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    settings_path
    / "_workflow_log"
)


log_folder.mkdir(
    parents=True,
    exist_ok=True
)


copy2(
    Path(__file__).resolve(),
    log_folder
    / Path(__file__).name
)


now = datetime.now()


log_file = (
    log_folder
    / (
        f"{now:%Y%m%d_%H%M%S}_"
        "create_summa_forcing_file_list_LST.txt"
    )
)


with log_file.open("w") as file:

    file.write(
        f"Domain: {domain_name}\n"
    )

    file.write(
        f"Control file: {CONTROL_FILE}\n"
    )

    file.write(
        f"Forcing path: {forcing_path}\n"
    )

    file.write(
        f"Forcing file: {forcing_file.name}\n"
    )

    file.write(
        f"Timezone: {timezone}\n"
    )

    file.write(
        f"UTC-to-LST offset hours: {offset}\n"
    )

    file.write(
        f"First timestamp: {first_time}\n"
    )

    file.write(
        f"Last timestamp: {last_time}\n"
    )

    file.write(
        f"Timesteps: {num_time}\n"
    )

    file.write(
        f"HRUs: {num_hru}\n"
    )

    file.write(
        "SUMMA tmZoneInfo required: localTime\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 72)
print("SUMMA LST FORCING FILE LIST CREATED")
print("=" * 72)

print(f"Domain       : {domain_name}")
print(f"Timezone     : {timezone}")
print(f"UTC offset   : {offset}")
print(f"Forcing path : {forcing_path}")
print(f"Forcing file : {forcing_file.name}")
print(f"Timesteps    : {num_time}")
print(f"HRUs         : {num_hru}")
print(f"First        : {first_time}")
print(f"Last         : {last_time}")
print(f"Output       : {file_list_file}")

print()
print("Existing UTC forcingFileList.txt was not modified.")