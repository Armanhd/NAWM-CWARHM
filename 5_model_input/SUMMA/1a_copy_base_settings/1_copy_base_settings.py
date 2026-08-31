#!/usr/bin/env python3
# coding: utf-8

# Copy SUMMA base settings into the selected domain settings folder.
#
# Purpose
# -------
# This script:
#   - locates CWARHM_multibasin from its own file location
#   - reads a domain-specific control file supplied on the command line
#   - determines the domain settings/SUMMA directory
#   - copies all SUMMA base-setting files into that directory
#   - creates a workflow log
#
# IMPORTANT
# ---------
# This script does NOT read or modify control_active.txt.
#
# Usage
# -----
# python 1_copy_base_settings.py \
# /path/to/control_DOMAIN.txt

import sys
from pathlib import Path
from shutil import copy2
from datetime import datetime


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_copy_base_settings.py "
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
#       1a_copy_base_settings/
#         1_copy_base_settings.py

SUMMA_WORKFLOW_DIR = (
    SCRIPT_DIR.parent
)


CWARHM_ROOT = (
    SCRIPT_DIR.parents[2]
)


BASE_SETTINGS_PATH = (
    SUMMA_WORKFLOW_DIR
    / "0_base_settings"
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


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# VALIDATE WORKFLOW INPUTS
# ============================================================

if not BASE_SETTINGS_PATH.exists():

    raise FileNotFoundError(
        "SUMMA base-settings folder not found:\n"
        f"{BASE_SETTINGS_PATH}"
    )


# ============================================================
# OUTPUT SETTINGS PATH
# ============================================================

settings_path = read_from_control(
    CONTROL_FILE,
    "settings_summa_path"
)


if settings_path == "default":

    settings_path = make_default_path(
        "settings/SUMMA"
    )

else:

    settings_path = Path(
        settings_path
    )


settings_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FIND BASE SETTINGS
# ============================================================

base_files = sorted(
    file
    for file in BASE_SETTINGS_PATH.iterdir()
    if file.is_file()
)


if not base_files:

    raise RuntimeError(
        "No SUMMA base-setting files found in:\n"
        f"{BASE_SETTINGS_PATH}"
    )


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("COPY SUMMA BASE SETTINGS")
print("=" * 70)

print(
    f"Domain       : {domain_name}"
)

print(
    f"Control file : {CONTROL_FILE}"
)

print(
    f"Source       : {BASE_SETTINGS_PATH}"
)

print(
    f"Destination  : {settings_path}"
)

print(
    f"Files found  : {len(base_files)}"
)

print()


# ============================================================
# COPY BASE SETTINGS
# ============================================================

copied_files = []


for source_file in base_files:

    destination_file = (
        settings_path
        / source_file.name
    )


    copy2(
        source_file,
        destination_file
    )


    copied_files.append(
        destination_file
    )


    print(
        f"Copied: {source_file.name}"
    )


# ============================================================
# VERIFY COPIED FILES
# ============================================================

missing_outputs = [
    file
    for file in copied_files
    if not file.exists()
]


if missing_outputs:

    missing_text = "\n".join(
        str(file)
        for file in missing_outputs
    )

    raise RuntimeError(
        "One or more SUMMA base-setting files "
        "were not copied successfully:\n"
        f"{missing_text}"
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
        "copy_summa_base_settings.txt"
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
        f"Source base settings: "
        f"{BASE_SETTINGS_PATH}\n"
    )

    file.write(
        f"Destination: "
        f"{settings_path}\n"
    )

    file.write(
        f"Files copied: "
        f"{len(copied_files)}\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("SUMMA BASE SETTINGS COPY COMPLETED")
print("=" * 70)

print(
    f"Domain       : {domain_name}"
)

print(
    f"Files copied : {len(copied_files)}"
)

print(
    f"Destination  : {settings_path}"
)

print(
    f"Workflow log : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)