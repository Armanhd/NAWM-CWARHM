#!/usr/bin/env python3
# coding: utf-8

"""
Create fileManager_LST.txt for one distributed CWARHM domain.

The simulation start/end times are read directly from the concatenated
LST forcing NetCDF.

The existing fileManager.txt for UTC forcing is NOT modified.

IMPORTANT
---------
The forcing timestamps have already been converted from UTC to local
standard time before this script runs.

Therefore:

    tmZoneInfo 'localTime'

is used so SUMMA does not apply another longitude-derived UTC offset.
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
        "python 1_create_file_manager_LST.py "
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


def resolve_path(
    setting,
    default_suffix
):

    value = read_from_control(
        CONTROL_FILE,
        setting
    )

    if value == "default":

        return make_default_path(
            default_suffix
        )

    return Path(value)


def format_summa_time(value):

    return (
        f"{int(value.year):04d}-"
        f"{int(value.month):02d}-"
        f"{int(value.day):02d} "
        f"{int(value.hour):02d}:"
        f"{int(value.minute):02d}"
    )


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


experiment_id = read_from_control(
    CONTROL_FILE,
    "experiment_id"
)


# ============================================================
# PATHS
# ============================================================

settings_path = resolve_path(
    "settings_summa_path",
    "settings/SUMMA"
)


forcing_path = make_default_path(
    "forcing/6_SUMMA_input_LST"
)


if not settings_path.is_dir():

    raise FileNotFoundError(
        "SUMMA settings directory not found:\n"
        f"{settings_path}"
    )


if not forcing_path.is_dir():

    raise FileNotFoundError(
        "LST forcing directory not found:\n"
        f"{forcing_path}"
    )


# Separate model output from UTC run.

output_path = make_default_path(
    f"simulations/{experiment_id}_LST/SUMMA"
)


output_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FIND LST FORCING
# ============================================================

forcing_files = sorted(
    forcing_path.glob(
        "NWAM_SUMMA_forcing_*_*_LST.nc"
    )
)


if len(forcing_files) != 1:

    raise RuntimeError(
        "Expected exactly one concatenated LST forcing file "
        f"for {domain_name}, found {len(forcing_files)}.\n"
        f"Directory:\n{forcing_path}"
    )


forcing_file = forcing_files[0]


# ============================================================
# READ ACTUAL LST PERIOD
# ============================================================

with Dataset(
    forcing_file,
    "r"
) as ds:

    if "time" not in ds.variables:

        raise RuntimeError(
            f"time variable missing:\n{forcing_file}"
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
            "LST forcing contains no timestamps."
        )

    sim_start = format_summa_time(
        dates[0]
    )

    sim_end = format_summa_time(
        dates[-1]
    )

    timezone = getattr(
        ds,
        "time_zone",
        "not recorded"
    )

    utc_offset = getattr(
        ds,
        "utc_to_lst_offset_hours",
        "not recorded"
    )


# ============================================================
# INPUT FILE NAMES
# ============================================================

coldstate_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_coldstate"
)


attributes_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_attributes"
)


trialparams_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_trialParams"
)


forcing_list_name = (
    "forcingFileList_LST.txt"
)


filemanager_file = (
    settings_path
    / "fileManager_LST.txt"
)


# ============================================================
# VERIFY OTHER SUMMA SETTINGS
# ============================================================

required_files = [
    coldstate_name,
    attributes_name,
    trialparams_name,
    forcing_list_name,
    "modelDecisions.txt",
    "outputControl.txt",
    "localParamInfo.txt",
    "basinParamInfo.txt",
    "TBL_VEGPARM.TBL",
    "TBL_SOILPARM.TBL",
    "TBL_GENPARM.TBL",
    "TBL_MPTABLE.TBL",
]


missing_files = [
    name
    for name in required_files
    if not (
        settings_path
        / name
    ).is_file()
]


if missing_files:

    raise FileNotFoundError(
        "Required SUMMA input files are missing:\n"
        + "\n".join(
            f"  {name}"
            for name in missing_files
        )
    )


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 72)
print("CREATE SUMMA LST FILE MANAGER")
print("=" * 72)

print(f"Domain          : {domain_name}")
print(f"Control file    : {CONTROL_FILE}")
print(f"Timezone        : {timezone}")
print(f"UTC offset      : {utc_offset}")
print(f"Simulation start: {sim_start}")
print(f"Simulation end  : {sim_end}")
print(f"tmZoneInfo      : localTime")
print(f"Forcing path    : {forcing_path}")
print(f"Forcing file    : {forcing_file.name}")
print(f"Settings path   : {settings_path}")
print(f"Output path     : {output_path}")
print(f"File manager    : {filemanager_file}")


# ============================================================
# WRITE FILE MANAGER
# ============================================================

with filemanager_file.open("w") as fm:

    fm.write(
        "controlVersion       "
        "'SUMMA_FILE_MANAGER_V3.0.0' "
        "! file manager version\n"
    )

    fm.write(
        f"simStartTime         "
        f"'{sim_start}' ! LST forcing start\n"
    )

    fm.write(
        f"simEndTime           "
        f"'{sim_end}' ! LST forcing end\n"
    )

    fm.write(
        "tmZoneInfo           "
        "'localTime' "
        "! forcing timestamps already converted to LST\n"
    )

    fm.write(
        f"outFilePrefix        "
        f"'{experiment_id}_LST' !\n"
    )

    fm.write(
        f"settingsPath         "
        f"'{settings_path}/' !\n"
    )

    fm.write(
        f"forcingPath          "
        f"'{forcing_path}/' !\n"
    )

    fm.write(
        f"outputPath           "
        f"'{output_path}/' !\n"
    )

    fm.write(
        f"initConditionFile    "
        f"'{coldstate_name}' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        f"attributeFile        "
        f"'{attributes_name}' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        f"trialParamFile       "
        f"'{trialparams_name}' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "forcingListFile      "
        "'forcingFileList_LST.txt' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "decisionsFile        "
        "'modelDecisions.txt' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "outputControlFile    "
        "'outputControl.txt' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "globalHruParamFile   "
        "'localParamInfo.txt' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "globalGruParamFile   "
        "'basinParamInfo.txt' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "vegTableFile         "
        "'TBL_VEGPARM.TBL' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "soilTableFile        "
        "'TBL_SOILPARM.TBL' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "generalTableFile     "
        "'TBL_GENPARM.TBL' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "noahmpTableFile      "
        "'TBL_MPTABLE.TBL' "
        "! Relative to settingsPath\n"
    )


# ============================================================
# VERIFY
# ============================================================

text = filemanager_file.read_text()


required_entries = [
    "simStartTime",
    "simEndTime",
    "'localTime'",
    str(forcing_path),
    "forcingFileList_LST.txt",
    str(output_path),
]


missing_entries = [
    item
    for item in required_entries
    if item not in text
]


if missing_entries:

    raise RuntimeError(
        "LST file manager verification failed:\n"
        + "\n".join(
            f"  {item}"
            for item in missing_entries
        )
    )


# ============================================================
# LOG
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
        "create_summa_file_manager_LST.txt"
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
        f"Timezone: {timezone}\n"
    )

    file.write(
        f"UTC-to-LST offset hours: {utc_offset}\n"
    )

    file.write(
        f"Simulation start: {sim_start}\n"
    )

    file.write(
        f"Simulation end: {sim_end}\n"
    )

    file.write(
        "tmZoneInfo: localTime\n"
    )

    file.write(
        f"Forcing path: {forcing_path}\n"
    )

    file.write(
        f"Output path: {output_path}\n"
    )

    file.write(
        f"File manager: {filemanager_file}\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 72)
print("SUMMA LST FILE MANAGER CREATION COMPLETED")
print("=" * 72)

print(f"Domain          : {domain_name}")
print(f"Timezone        : {timezone}")
print(f"Simulation start: {sim_start}")
print(f"Simulation end  : {sim_end}")
print("tmZoneInfo      : localTime")
print(f"Forcing list    : {forcing_list_name}")
print(f"Output          : {filemanager_file}")
print(f"Workflow log    : {log_file}")

print()
print("Existing UTC fileManager.txt was not modified.")