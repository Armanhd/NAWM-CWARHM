# Create forcingFileList.txt for the active SUMMA domain.
#
# This script:
#   - locates CWARHM from its own file location
#   - reads control_active.txt
#   - finds NWAM_SUMMA_forcing_YYYYMM.nc files
#   - validates filenames and chronological continuity
#   - compares available months against forcing_raw_time
#   - writes forcingFileList.txt in chronological order
#   - stores workflow provenance
#
# Reproducible for any domain selected through control_active.txt.

from pathlib import Path
from datetime import datetime
from shutil import copy2
import re


# ============================================================
# PROJECT / CONTROL FILE
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

# Script:
# CWARHM/5_model_input/SUMMA/1c_forcing_file_list/
# 1_create_forcing_file_list.py
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


def month_sequence(start_year, end_year):

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
        f"SUMMA forcing directory not found:\n"
        f"{forcing_path}"
    )


# ============================================================
# OUTPUT FILE LIST PATH
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

    start_year_text, end_year_text = [
        item.strip()
        for item in forcing_raw_time.split(",")
    ]

    start_year = int(start_year_text)
    end_year = int(end_year_text)

except Exception as exc:

    raise ValueError(
        "forcing_raw_time must have format "
        "'START_YEAR,END_YEAR', for example "
        "'1950,2019'."
    ) from exc


if start_year > end_year:

    raise ValueError(
        f"Invalid forcing_raw_time: "
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
        f"No NWAM SUMMA forcing files found in:\n"
        f"{forcing_path}"
    )


# ============================================================
# VALIDATE FILENAMES AND EXTRACT YYYYMM
# ============================================================

pattern = re.compile(
    r"^NWAM_SUMMA_forcing_(\d{6})\.nc$"
)


files_by_month = {}

invalid_files = []


for file in forcing_files:

    match = pattern.match(
        file.name
    )

    if not match:

        invalid_files.append(
            file.name
        )

        continue

    month = match.group(1)

    if month in files_by_month:

        raise RuntimeError(
            f"Duplicate forcing month found: {month}"
        )

    files_by_month[month] = file


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
# CHECK MONTH VALIDITY
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
print("============================================================")
print("CREATE SUMMA FORCING FILE LIST")
print("============================================================")
print(f"Domain          : {domain_name}")
print(f"Forcing path    : {forcing_path}")
print(f"Expected period : {expected_months[0]} - {expected_months[-1]}")
print(f"Expected files  : {len(expected_months)}")
print(f"Available files : {len(available_months)}")


if missing_months:

    print()
    print(
        f"Missing months: "
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
        f"Months outside forcing_raw_time: "
        f"{len(extra_months)}"
    )

    for month in extra_months[:20]:

        print(
            f"  {month}"
        )


if missing_months:

    raise RuntimeError(
        "SUMMA forcing archive is incomplete "
        "for forcing_raw_time. "
        f"Missing {len(missing_months)} month(s)."
    )


# Only use the months specified by forcing_raw_time.
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
    / f"{now:%Y%m%d}_make_forcing_file_list.txt"
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


# ============================================================
# SUMMARY
# ============================================================

print()
print("SUMMA forcing file list created successfully.")
print(f"Files listed : {len(ordered_files)}")
print(f"First file   : {ordered_files[0].name}")
print(f"Last file    : {ordered_files[-1].name}")
print(f"Output       : {file_list_file}")