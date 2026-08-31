#!/usr/bin/env python3
# coding: utf-8

"""
Link the MERIT-Hydro elevation tiles required for one CWARHM domain.

The domain-specific control file is supplied explicitly on the command
line. No shared control_active.txt is used or modified.

Usage
-----
python 0_link_existing_tiles.py /path/to/control_DOMAIN.txt

Example
-------
python 0_link_existing_tiles.py \
/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/control_MERIT_717.txt
"""

from pathlib import Path
import math
import os
import re
import subprocess
import sys


# ============================================================
# PROJECT SETTINGS
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM_ROOT = SCRIPT_DIR.parent.parent

MERIT_ARCHIVE = Path(
    "/work/comphyd_lab/data/geospatial-data/MERIT-Hydro/elv"
)


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage:\n"
        "python 0_link_existing_tiles.py "
        "/path/to/control_DOMAIN.txt"
    )

CONTROL_FILE = Path(
    sys.argv[1]
).expanduser().resolve()

if not CONTROL_FILE.exists():
    raise FileNotFoundError(
        f"Control file not found:\n"
        f"{CONTROL_FILE}"
    )

if not CONTROL_FILE.is_file():
    raise RuntimeError(
        f"Control-file path is not a file:\n"
        f"{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(file, setting):
    """
    Read one exact setting from a CWARHM control file.
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

            return (
                right
                .split("#", 1)[0]
                .strip()
            )

    raise ValueError(
        f"Setting '{setting}' not found in:\n"
        f"{file}"
    )


# ============================================================
# DOMAIN SETTINGS
# ============================================================

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

catchment_path_setting = read_from_control(
    CONTROL_FILE,
    "catchment_shp_path"
)

catchment_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
)


# ============================================================
# RESOLVE CATCHMENT SHAPEFILE
# ============================================================

if catchment_path_setting == "default":

    catchment_path = (
        root_path
        / f"domain_{domain_name}"
        / "shapefiles"
        / "catchment"
    )

else:

    catchment_path = Path(
        catchment_path_setting
    )

catchment_file = (
    catchment_path
    / catchment_name
)

if not catchment_file.exists():
    raise FileNotFoundError(
        "Catchment shapefile not found:\n"
        f"{catchment_file}"
    )


# ============================================================
# VALIDATE MERIT ARCHIVE
# ============================================================

if not MERIT_ARCHIVE.exists():
    raise FileNotFoundError(
        "Shared MERIT-Hydro archive directory not found:\n"
        f"{MERIT_ARCHIVE}"
    )

if not MERIT_ARCHIVE.is_dir():
    raise RuntimeError(
        "MERIT-Hydro archive path is not a directory:\n"
        f"{MERIT_ARCHIVE}"
    )


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("LINK EXISTING MERIT-HYDRO ELEVATION TILES")
print("=" * 70)
print()
print(f"Domain        : {domain_name}")
print(f"Control file  : {CONTROL_FILE}")
print(f"Catchment     : {catchment_file}")
print(f"MERIT archive : {MERIT_ARCHIVE}")


# ============================================================
# GET CATCHMENT EXTENT USING ogrinfo
# ============================================================

cmd = [
    "ogrinfo",
    "-so",
    "-al",
    str(catchment_file),
]

try:

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True
    )

except FileNotFoundError as exc:

    raise RuntimeError(
        "ogrinfo was not found.\n"
        "Make sure GDAL is available in the current environment."
    ) from exc

except subprocess.CalledProcessError as exc:

    raise RuntimeError(
        "ogrinfo failed while reading the catchment shapefile.\n"
        f"Command: {' '.join(cmd)}\n"
        f"stderr:\n{exc.stderr}"
    ) from exc


match = re.search(
    r"Extent:\s*"
    r"\(\s*([-0-9.]+),\s*([-0-9.]+)\s*\)"
    r"\s*-\s*"
    r"\(\s*([-0-9.]+),\s*([-0-9.]+)\s*\)",
    result.stdout
)

if not match:
    raise RuntimeError(
        "Could not parse shapefile extent from ogrinfo output."
    )


min_lon = float(
    match.group(1)
)

min_lat = float(
    match.group(2)
)

max_lon = float(
    match.group(3)
)

max_lat = float(
    match.group(4)
)


if min_lon >= max_lon or min_lat >= max_lat:
    raise RuntimeError(
        "Invalid catchment extent returned by ogrinfo:\n"
        f"Longitude: {min_lon} to {max_lon}\n"
        f"Latitude : {min_lat} to {max_lat}"
    )


print()
print("Domain extent:")
print(
    f"  Longitude: "
    f"{min_lon:.6f} to {max_lon:.6f}"
)
print(
    f"  Latitude : "
    f"{min_lat:.6f} to {max_lat:.6f}"
)


# ============================================================
# MERIT-HYDRO TILE NAMING
# ============================================================

def floor_to_30(value):
    return (
        math.floor(
            value / 30.0
        )
        * 30
    )


def format_lat(lat):

    if lat >= 0:
        return f"n{abs(lat):02d}"

    return f"s{abs(lat):02d}"


def format_lon(lon):

    if lon >= 0:
        return f"e{abs(lon):03d}"

    return f"w{abs(lon):03d}"


lat_starts = range(
    floor_to_30(min_lat),
    floor_to_30(max_lat) + 1,
    30
)

lon_starts = range(
    floor_to_30(min_lon),
    floor_to_30(max_lon) + 1,
    30
)


required_tiles = []

for lat in lat_starts:

    for lon in lon_starts:

        filename = (
            f"elv_"
            f"{format_lat(lat)}"
            f"{format_lon(lon)}.tar"
        )

        required_tiles.append(
            filename
        )


if not required_tiles:
    raise RuntimeError(
        "No MERIT-Hydro tiles were identified "
        "for the catchment extent."
    )


# ============================================================
# TARGET DIRECTORY
# ============================================================

target_dir = (
    root_path
    / f"domain_{domain_name}"
    / "parameters"
    / "dem"
    / "1_MERIT_hydro_raw_data"
)

target_dir.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# LINK REQUIRED TILES
# ============================================================

print()
print("Required MERIT-Hydro tiles:")
print("-" * 70)

missing = []
linked = []
existing = []


for filename in required_tiles:

    source = (
        MERIT_ARCHIVE
        / filename
    )

    target = (
        target_dir
        / filename
    )

    print(
        f"{filename}"
    )

    if not source.exists():

        print(
            "  MISSING from shared archive"
        )

        missing.append(
            filename
        )

        continue


    if target.exists() or target.is_symlink():

        # If a symlink already exists, make sure it is valid.
        if target.is_symlink() and not target.exists():

            raise RuntimeError(
                "Broken existing symbolic link found:\n"
                f"{target}"
            )

        print(
            "  already exists"
        )

        existing.append(
            filename
        )

        continue


    os.symlink(
        source,
        target
    )

    print(
        f"  linked -> {source}"
    )

    linked.append(
        filename
    )


# ============================================================
# FAIL IF REQUIRED SOURCE DATA ARE MISSING
# ============================================================

if missing:

    raise FileNotFoundError(
        "One or more required MERIT-Hydro tiles "
        "were not found in the shared archive:\n"
        + "\n".join(
            f"  {filename}"
            for filename in missing
        )
    )


# ============================================================
# VERIFY LINKS
# ============================================================

for filename in required_tiles:

    target = (
        target_dir
        / filename
    )

    if not target.exists():
        raise RuntimeError(
            "Required MERIT-Hydro target is missing "
            "after linking:\n"
            f"{target}"
        )


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)
print("MERIT-HYDRO TILE LINKING COMPLETED")
print("=" * 70)
print(f"Domain          : {domain_name}")
print(f"Tiles required  : {len(required_tiles)}")
print(f"New links       : {len(linked)}")
print(f"Already present : {len(existing)}")
print(f"Missing         : {len(missing)}")
print(f"Target directory: {target_dir}")