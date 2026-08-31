#!/usr/bin/env python3
# coding: utf-8

# Create the SUMMA fileManager.txt for a selected CWARHM domain.
#
# Purpose
# -------
# This script:
#   - reads a domain-specific control file supplied on the command line
#   - resolves all default paths from root_path/domain_name
#   - uses experiment_time_start/end when explicitly provided
#   - otherwise derives simulation dates from forcing_raw_time
#   - validates required SUMMA directories and base-setting files
#   - writes fileManager.txt
#   - stores workflow provenance
#
# IMPORTANT
# ---------
# This script does NOT read or modify control_active.txt.
#
# Usage
# -----
# python 1_create_file_manager.py \
# /path/to/control_DOMAIN.txt

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_create_file_manager.py "
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
# PROJECT PATHS
# ============================================================

SCRIPT_DIR = Path(
    __file__
).resolve().parent


# Script location:
#
# CWARHM_multibasin/
#   5_model_input/
#     SUMMA/
#       1b_file_manager/
#         1_create_file_manager.py

CWARHM_ROOT = (
    SCRIPT_DIR.parents[2]
)


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(
    file,
    setting
):
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


def make_default_path(
    suffix
):
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


def resolve_path(
    setting,
    default_suffix
):
    """
    Resolve a control-file path setting.
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
# DOMAIN / EXPERIMENT SETTINGS
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
# SIMULATION PERIOD
# ============================================================

sim_start = read_from_control(
    CONTROL_FILE,
    "experiment_time_start"
)


sim_end = read_from_control(
    CONTROL_FILE,
    "experiment_time_end"
)


forcing_raw_time = read_from_control(
    CONTROL_FILE,
    "forcing_raw_time"
)


try:

    year_parts = [
        item.strip()
        for item in forcing_raw_time.split(",")
    ]


    if len(year_parts) != 2:

        raise ValueError


    start_year = int(
        year_parts[0]
    )

    end_year = int(
        year_parts[1]
    )


except Exception as exc:

    raise ValueError(
        "forcing_raw_time must have format:\n"
        "START_YEAR,END_YEAR\n\n"
        "Example:\n"
        "1950,2019"
    ) from exc


if start_year > end_year:

    raise ValueError(
        "Invalid forcing_raw_time:\n"
        f"{start_year},{end_year}"
    )


if sim_start == "default":

    sim_start = (
        f"{start_year}-01-01 00:00"
    )


if sim_end == "default":

    sim_end = (
        f"{end_year}-12-31 23:00"
    )


# ============================================================
# PATHS
# ============================================================

settings_path = resolve_path(
    "settings_summa_path",
    "settings/SUMMA"
)


forcing_path = resolve_path(
    "forcing_summa_path",
    "forcing/4_SUMMA_input"
)


output_path_setting = read_from_control(
    CONTROL_FILE,
    "experiment_output_summa"
)


if output_path_setting == "default":

    output_path = make_default_path(
        f"simulations/{experiment_id}/SUMMA"
    )

else:

    output_path = Path(
        output_path_setting
    )


settings_path.mkdir(
    parents=True,
    exist_ok=True
)


output_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FILENAMES
# ============================================================

filemanager_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_filemanager"
)


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


forcing_list_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_forcing_list"
)


filemanager_file = (
    settings_path
    / filemanager_name
)


# ============================================================
# VALIDATE REQUIRED DIRECTORIES
# ============================================================

if not forcing_path.exists():

    raise FileNotFoundError(
        "SUMMA forcing directory not found:\n"
        f"{forcing_path}"
    )


# ============================================================
# VALIDATE BASE SETTINGS
# ============================================================

required_base_files = [
    "modelDecisions.txt",
    "outputControl.txt",
    "localParamInfo.txt",
    "basinParamInfo.txt",
    "TBL_VEGPARM.TBL",
    "TBL_SOILPARM.TBL",
    "TBL_GENPARM.TBL",
    "TBL_MPTABLE.TBL",
]


missing_base_files = [
    name
    for name in required_base_files
    if not (
        settings_path
        / name
    ).exists()
]


if missing_base_files:

    missing_text = "\n".join(
        f"  {name}"
        for name in missing_base_files
    )

    raise FileNotFoundError(
        "Required SUMMA base-setting files "
        "are missing:\n"
        f"{missing_text}\n\n"
        "Run 1a_copy_base_settings.py first."
    )


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("CREATE SUMMA FILE MANAGER")
print("=" * 70)

print(
    f"Domain          : {domain_name}"
)

print(
    f"Control file    : {CONTROL_FILE}"
)

print(
    f"Experiment      : {experiment_id}"
)

print(
    f"Simulation start: {sim_start}"
)

print(
    f"Simulation end  : {sim_end}"
)

print(
    f"Settings path   : {settings_path}"
)

print(
    f"Forcing path    : {forcing_path}"
)

print(
    f"Output path     : {output_path}"
)

print(
    f"File manager    : {filemanager_file}"
)


# ============================================================
# WRITE FILE MANAGER
# ============================================================

with open(
    filemanager_file,
    "w"
) as fm:

    fm.write(
        "controlVersion       "
        "'SUMMA_FILE_MANAGER_V3.0.0' "
        "! file manager version\n"
    )

    fm.write(
        f"simStartTime         "
        f"'{sim_start}' !\n"
    )

    fm.write(
        f"simEndTime           "
        f"'{sim_end}' !\n"
    )

    fm.write(
        "tmZoneInfo           "
        "'utcTime' !\n"
    )

    fm.write(
        f"outFilePrefix        "
        f"'{experiment_id}' !\n"
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
        f"forcingListFile      "
        f"'{forcing_list_name}' "
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
# VERIFY OUTPUT
# ============================================================

if not filemanager_file.exists():

    raise RuntimeError(
        "fileManager.txt was not created:\n"
        f"{filemanager_file}"
    )


filemanager_text = (
    filemanager_file
    .read_text()
)


required_entries = [
    "simStartTime",
    "simEndTime",
    "settingsPath",
    "forcingPath",
    "outputPath",
    "initConditionFile",
    "attributeFile",
    "trialParamFile",
    "forcingListFile",
]


missing_entries = [
    entry
    for entry in required_entries
    if entry not in filemanager_text
]


if missing_entries:

    raise RuntimeError(
        "Created fileManager.txt is missing "
        "required entries:\n"
        + "\n".join(
            f"  {entry}"
            for entry in missing_entries
        )
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


this_file = Path(
    __file__
).name


copy2(
    Path(__file__).resolve(),
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
        "create_summa_file_manager.txt"
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
        f"Experiment: {experiment_id}\n"
    )

    file.write(
        f"Simulation start: {sim_start}\n"
    )

    file.write(
        f"Simulation end: {sim_end}\n"
    )

    file.write(
        f"Settings path: {settings_path}\n"
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

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("SUMMA FILE MANAGER CREATION COMPLETED")
print("=" * 70)

print(
    f"Domain          : {domain_name}"
)

print(
    f"Experiment      : {experiment_id}"
)

print(
    f"Simulation start: {sim_start}"
)

print(
    f"Simulation end  : {sim_end}"
)

print(
    f"Output          : {filemanager_file}"
)

print(
    f"Workflow log    : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)