#!/usr/bin/env python3

import sys
from pathlib import Path

from netCDF4 import Dataset, num2date


if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: python 1_create_file_manager_LST_lumped.py "
        "/path/to/control_DOMAIN_lumped.txt"
    )

CONTROL_FILE = Path(sys.argv[1]).resolve()


def read_control(key):

    with open(CONTROL_FILE) as f:
        for line in f:

            if "|" not in line or line.lstrip().startswith("#"):
                continue

            left, right = line.split("|", 1)

            if left.strip() == key:
                return right.split("#", 1)[0].strip()

    raise ValueError(f"Missing control setting: {key}")


domain = read_control("domain_name")
root_path = Path(read_control("root_path"))
experiment_id = read_control("experiment_id")

domain_root = (
    root_path
    / f"domain_{domain}"
    / "lumped"
)

settings_dir = (
    domain_root
    / "settings"
    / "SUMMA"
)

forcing_dir = (
    domain_root
    / "forcing"
    / "6_SUMMA_input_LST"
)

output_dir = (
    domain_root
    / "simulations"
    / f"{experiment_id}_LST"
    / "SUMMA"
)

settings_dir.mkdir(
    parents=True,
    exist_ok=True
)

output_dir.mkdir(
    parents=True,
    exist_ok=True
)


# ------------------------------------------------------------
# Find LST forcing
# ------------------------------------------------------------

forcing_files = sorted(
    forcing_dir.glob(
        "NWAM_SUMMA_forcing_*_LST.nc"
    )
)

if len(forcing_files) != 1:
    raise RuntimeError(
        f"Expected exactly one LST forcing file; "
        f"found {len(forcing_files)}"
    )

forcing_file = forcing_files[0]


# ------------------------------------------------------------
# Obtain actual LST period
# ------------------------------------------------------------

with Dataset(forcing_file) as ds:

    t = ds.variables["time"]

    dates = num2date(
        t[:],
        units=t.units,
        calendar=getattr(
            t,
            "calendar",
            "standard"
        ),
    )

    sim_start = (
        f"{dates[0].year:04d}-"
        f"{dates[0].month:02d}-"
        f"{dates[0].day:02d} "
        f"{dates[0].hour:02d}:"
        f"{dates[0].minute:02d}"
    )

    sim_end = (
        f"{dates[-1].year:04d}-"
        f"{dates[-1].month:02d}-"
        f"{dates[-1].day:02d} "
        f"{dates[-1].hour:02d}:"
        f"{dates[-1].minute:02d}"
    )

    timezone = getattr(
        ds,
        "time_zone",
        "LST"
    )

    offset = getattr(
        ds,
        "utc_to_lst_offset_hours",
        "unknown"
    )


# ------------------------------------------------------------
# Existing SUMMA filenames
# ------------------------------------------------------------

coldstate = read_control(
    "settings_summa_coldstate"
)

attributes = read_control(
    "settings_summa_attributes"
)

trialparams = read_control(
    "settings_summa_trialParams"
)


required = [
    "modelDecisions.txt",
    "outputControl.txt",
    "localParamInfo.txt",
    "basinParamInfo.txt",
    "TBL_VEGPARM.TBL",
    "TBL_SOILPARM.TBL",
    "TBL_GENPARM.TBL",
    "TBL_MPTABLE.TBL",
    coldstate,
    attributes,
    trialparams,
    "forcingFileList_LST.txt",
]

for name in required:

    f = settings_dir / name

    if not f.is_file():
        raise FileNotFoundError(
            f"Required SUMMA file missing:\n{f}"
        )


# ------------------------------------------------------------
# Write LST fileManager
# ------------------------------------------------------------

filemanager = (
    settings_dir
    / "fileManager_LST.txt"
)


with open(filemanager, "w") as fm:

    fm.write(
        "controlVersion       "
        "'SUMMA_FILE_MANAGER_V3.0.0' !\n"
    )

    fm.write(
        f"simStartTime         '{sim_start}' !\n"
    )

    fm.write(
        f"simEndTime           '{sim_end}' !\n"
    )

    # CRITICAL:
    # timestamps already contain LST.
    fm.write(
        "tmZoneInfo           'localTime' !\n"
    )

    fm.write(
        f"outFilePrefix        "
        f"'{experiment_id}_LST' !\n"
    )

    fm.write(
        f"settingsPath         "
        f"'{settings_dir}/' !\n"
    )

    fm.write(
        f"forcingPath          "
        f"'{forcing_dir}/' !\n"
    )

    fm.write(
        f"outputPath           "
        f"'{output_dir}/' !\n"
    )

    fm.write(
        f"initConditionFile    '{coldstate}' !\n"
    )

    fm.write(
        f"attributeFile        '{attributes}' !\n"
    )

    fm.write(
        f"trialParamFile       '{trialparams}' !\n"
    )

    fm.write(
        "forcingListFile      "
        "'forcingFileList_LST.txt' !\n"
    )

    fm.write(
        "decisionsFile        "
        "'modelDecisions.txt' !\n"
    )

    fm.write(
        "outputControlFile    "
        "'outputControl.txt' !\n"
    )

    fm.write(
        "globalHruParamFile   "
        "'localParamInfo.txt' !\n"
    )

    fm.write(
        "globalGruParamFile   "
        "'basinParamInfo.txt' !\n"
    )

    fm.write(
        "vegTableFile         "
        "'TBL_VEGPARM.TBL' !\n"
    )

    fm.write(
        "soilTableFile        "
        "'TBL_SOILPARM.TBL' !\n"
    )

    fm.write(
        "generalTableFile     "
        "'TBL_GENPARM.TBL' !\n"
    )

    fm.write(
        "noahmpTableFile      "
        "'TBL_MPTABLE.TBL' !\n"
    )


print()
print("=" * 70)
print("LUMPED SUMMA LST FILE MANAGER")
print("=" * 70)
print(f"Domain          : {domain}")
print(f"Timezone        : {timezone}")
print(f"UTC offset      : {offset}")
print(f"Simulation start: {sim_start}")
print(f"Simulation end  : {sim_end}")
print("tmZoneInfo      : localTime")
print(f"Forcing         : {forcing_file}")
print(f"File manager    : {filemanager}")
print(f"Output path     : {output_dir}")
print("=" * 70)
print("PASS: LUMPED SUMMA LST FILE MANAGER")