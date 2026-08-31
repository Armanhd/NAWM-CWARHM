#!/usr/bin/env python3
# coding: utf-8

# Create forcingFileList.txt for a selected SUMMA domain.
#
# Purpose
# -------
# This script:
#   - reads a domain-specific control file supplied on the command line
#   - finds NWAM_SUMMA_forcing_YYYYMM.nc files
#   - validates filenames and chronological continuity
#   - compares available months against forcing_raw_time
#   - writes forcingFileList.txt in chronological order
#   - stores workflow provenance
#
# IMPORTANT
# ---------
# This script does NOT read or modify control_active.txt.
#
# Usage
# -----
# python 1_create_forcing_file_list.py \
# /path/to/control_DOMAIN.txt

import sys
import re
from pathlib import Path
from datetime import datetime
from shutil import copy2


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_create_forcing_file_list.py "
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


def month_sequence(
    start_year,
    end_year
):
    """
    Return YYYYMM strings for every month in the period.
    """

    months = []

    for year in range(
        start_year,
        end_year + 1
    ):

        for month in range(
            1,
            13
        ):

            months.append(
                f"{year}{month:02d}"
            )

    return months


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# FORCING PATH
# ============================================================

forcing_path_setting = read_from_control(
    CONTROL_FILE,
    "forcing_summa_path"
)


if forcing_path_setting == "default":

    forcing_path = make_default_path(
        "forcing/4_SUMMA_input"
    )

else:

    forcing_path = Path(
        forcing_path_setting
    )


if not forcing_path.exists():

    raise FileNotFoundError(
        "SUMMA forcing directory not found:\n"
        f"{forcing_path}"
    )


# ============================================================
# OUTPUT SETTINGS PATH
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


settings_path.mkdir(
    parents=True,
    exist_ok=True
)


file_list_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_forcing_list"
)


file_list_file = (
    settings_path
    / file_list_name
)


# ============================================================
# EXPECTED FORCING PERIOD
# ============================================================

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


expected_months = month_sequence(
    start_year,
    end_year
)


# ============================================================
# FIND SUMMA FORCING FILES
# ============================================================

forcing_files = sorted(
    forcing_path.glob(
        "NWAM_SUMMA_forcing_*.nc"
    )
)


if not forcing_files:

    raise RuntimeError(
        "No NWAM SUMMA forcing files found in:\n"
        f"{forcing_path}"
    )


# ============================================================
# VALIDATE FILENAMES
# ============================================================

pattern = re.compile(
    r"^NWAM_SUMMA_forcing_(\d{6})\.nc$"
)


files_by_month = {}
invalid_files = []


for forcing_file in forcing_files:

    match = pattern.match(
        forcing_file.name
    )

    if not match:

        invalid_files.append(
            forcing_file.name
        )

        continue


    month = match.group(1)


    if month in files_by_month:

        raise RuntimeError(
            "Duplicate forcing month found:\n"
            f"{month}"
        )


    files_by_month[
        month
    ] = forcing_file


if invalid_files:

    raise RuntimeError(
        "Unexpected forcing filenames found:\n"
        + "\n".join(
            f"  {name}"
            for name in invalid_files
        )
    )


available_months = sorted(
    files_by_month.keys()
)


# ============================================================
# CHECK YYYYMM VALUES
# ============================================================

invalid_months = []


for month in available_months:

    year = int(
        month[:4]
    )

    month_number = int(
        month[4:6]
    )


    if (
        year < 1
        or month_number < 1
        or month_number > 12
    ):

        invalid_months.append(
            month
        )


if invalid_months:

    raise RuntimeError(
        "Invalid YYYYMM values found:\n"
        + "\n".join(
            f"  {month}"
            for month in invalid_months
        )
    )


# ============================================================
# CHECK COVERAGE
# ============================================================

expected_set = set(
    expected_months
)

available_set = set(
    available_months
)


missing_months = sorted(
    expected_set
    - available_set
)


extra_months = sorted(
    available_set
    - expected_set
)


print()
print("=" * 70)
print("CREATE SUMMA FORCING FILE LIST")
print("=" * 70)

print(
    f"Domain          : {domain_name}"
)

print(
    f"Control file    : {CONTROL_FILE}"
)

print(
    f"Forcing path    : {forcing_path}"
)

print(
    f"Expected period : "
    f"{expected_months[0]} - "
    f"{expected_months[-1]}"
)

print(
    f"Expected files  : "
    f"{len(expected_months)}"
)

print(
    f"Available files : "
    f"{len(available_months)}"
)


if missing_months:

    print()
    print(
        f"Missing months  : "
        f"{len(missing_months)}"
    )

    print(
        "First missing months:"
    )

    for month in missing_months[:20]:

        print(
            f"  {month}"
        )


if extra_months:

    print()
    print(
        "Months outside forcing_raw_time: "
        f"{len(extra_months)}"
    )

    for month in extra_months[:20]:

        print(
            f"  {month}"
        )


if missing_months:

    raise RuntimeError(
        "SUMMA forcing archive is incomplete for "
        "forcing_raw_time.\n"
        f"Missing {len(missing_months)} month(s)."
    )


# ============================================================
# BUILD ORDERED FILE LIST
# ============================================================

ordered_files = [
    files_by_month[month]
    for month in expected_months
]


# ============================================================
# WRITE FORCING FILE LIST
# ============================================================

with open(
    file_list_file,
    "w"
) as file:

    for forcing_file in ordered_files:

        file.write(
            forcing_file.name
            + "\n"
        )


# ============================================================
# VERIFY WRITTEN LIST
# ============================================================

written_lines = [
    line.strip()
    for line in file_list_file.read_text().splitlines()
    if line.strip()
]


if len(written_lines) != len(
    expected_months
):

    raise RuntimeError(
        "forcingFileList.txt has an incorrect "
        "number of entries.\n"
        f"Expected: {len(expected_months)}\n"
        f"Found   : {len(written_lines)}"
    )


expected_first = (
    f"NWAM_SUMMA_forcing_"
    f"{expected_months[0]}.nc"
)


expected_last = (
    f"NWAM_SUMMA_forcing_"
    f"{expected_months[-1]}.nc"
)


if written_lines[0] != expected_first:

    raise RuntimeError(
        "Unexpected first forcing file.\n"
        f"Expected: {expected_first}\n"
        f"Found   : {written_lines[0]}"
    )


if written_lines[-1] != expected_last:

    raise RuntimeError(
        "Unexpected last forcing file.\n"
        f"Expected: {expected_last}\n"
        f"Found   : {written_lines[-1]}"
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
        "create_summa_forcing_file_list.txt"
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
        f"Forcing path: {forcing_path}\n"
    )

    file.write(
        f"First forcing month: "
        f"{expected_months[0]}\n"
    )

    file.write(
        f"Last forcing month: "
        f"{expected_months[-1]}\n"
    )

    file.write(
        f"Forcing files listed: "
        f"{len(ordered_files)}\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("SUMMA FORCING FILE LIST CREATION COMPLETED")
print("=" * 70)

print(
    f"Domain       : {domain_name}"
)

print(
    f"Files listed : {len(ordered_files)}"
)

print(
    f"First file   : {ordered_files[0].name}"
)

print(
    f"Last file    : {ordered_files[-1].name}"
)

print(
    f"Output       : {file_list_file}"
)

print(
    f"Workflow log : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)