#!/usr/bin/env python
# coding: utf-8

"""
CWARHM / NWAM workflow: make folder structure

MULTIBASIN VERSION

This script:

1. Reads a domain-specific control file supplied as a command-line argument;
2. Uses that control file directly -- no shared control_active.txt is created;
3. Creates the domain folder structure;
4. Stores copies of the control file and this script in the workflow log.

Usage:

python make_folder_structure.py \
../0_control_files/control_pfaf_713.txt

This design allows multiple domains to be prepared simultaneously because
each process uses its own control file.
"""

import sys
from pathlib import Path
from shutil import copyfile
from datetime import datetime


# ============================================================
# SCRIPT / PROJECT LOCATION
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM_ROOT = SCRIPT_DIR.parent


# ============================================================
# INPUT CONTROL FILE
# ============================================================

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage:\n"
        "python make_folder_structure.py "
        "../0_control_files/control_DOMAIN.txt"
    )


control_file = Path(sys.argv[1]).resolve()

if not control_file.exists():
    raise FileNotFoundError(
        f"Control file not found:\n{control_file}"
    )

if not control_file.is_file():
    raise RuntimeError(
        f"Control path is not a file:\n{control_file}"
    )


print()
print("=" * 70)
print("CREATE CWARHM DOMAIN FOLDER STRUCTURE")
print("=" * 70)

print()
print("Control file:")
print(control_file)


# ============================================================
# FUNCTION TO READ CONTROL SETTINGS
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

            left, right = stripped.split("|", 1)

            if left.strip() != setting:
                continue

            return (
                right
                .split("#", 1)[0]
                .strip()
            )

    raise ValueError(
        f"Setting '{setting}' not found in:\n{file}"
    )


# ============================================================
# DOMAIN SETTINGS
# ============================================================

root_path = Path(
    read_from_control(
        control_file,
        "root_path"
    )
)

domain_name = read_from_control(
    control_file,
    "domain_name"
)

if not domain_name:
    raise ValueError(
        "domain_name is empty in control file."
    )


domain_folder = (
    root_path
    / f"domain_{domain_name}"
)


print()
print(f"Domain      : {domain_name}")
print(f"Root path   : {root_path}")
print(f"Domain path : {domain_folder}")


# ============================================================
# CREATE DOMAIN ROOT
# ============================================================

domain_folder.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# CREATE MAIN CWARHM DOMAIN FOLDERS
# ============================================================

folders = [

    "forcing/0_geopotential",
    "forcing/1_raw_data",
    "forcing/2_merged_data",
    "forcing/3_temp_easymore",
    "forcing/3_basin_averaged_data",
    "forcing/4_SUMMA_input",

    "parameters/dem/1_MERIT_hydro_raw_data",
    "parameters/dem/2_MERIT_hydro_unpacked_data",
    "parameters/dem/3_vrt",
    "parameters/dem/4_domain_vrt",
    "parameters/dem/5_elevation",

    "parameters/soilclass/1_soil_classes_global",
    "parameters/soilclass/2_soil_classes_domain",

    "parameters/landclass/1_MODIS_raw_data",
    "parameters/landclass/2_vrt_native_crs",
    "parameters/landclass/3_vrt_epsg_4326",
    "parameters/landclass/4_domain_vrt_epsg_4326",
    "parameters/landclass/5_multiband_domain_vrt_epsg_4326",
    "parameters/landclass/6_tif_multiband",
    "parameters/landclass/7_mode_land_class",

    "settings/SUMMA",
    "settings/mizuRoute",

    "shapefiles/catchment",
    "shapefiles/river_network",
    "shapefiles/river_basins",

    "shapefiles/catchment_intersection/with_dem",
    "shapefiles/catchment_intersection/with_soilgrids",
    "shapefiles/catchment_intersection/with_modis",
    "shapefiles/catchment_intersection/with_forcing",
    "shapefiles/catchment_intersection/with_routing",

    "shapefiles/forcing",

    "simulations",

    "visualization",
]


for folder in folders:

    (
        domain_folder
        / folder
    ).mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    domain_folder
    / "_workflow_log"
)

log_folder.mkdir(
    parents=True,
    exist_ok=True
)


# ------------------------------------------------------------
# Store domain-specific control file
# ------------------------------------------------------------

logged_control = (
    log_folder
    / control_file.name
)

copyfile(
    control_file,
    logged_control
)


# ------------------------------------------------------------
# Store script
# ------------------------------------------------------------

this_file = Path(__file__).name

copyfile(
    Path(__file__).resolve(),
    log_folder / this_file
)


# ============================================================
# CREATE LOG FILE
# ============================================================

now = datetime.now()

log_file = (
    log_folder
    / (
        f"{now:%Y%m%d_%H%M%S}_"
        "folder_structure_log.txt"
    )
)


with open(log_file, "w") as file:

    file.write(
        f"Log generated by {this_file} on "
        f"{now:%Y/%m/%d %H:%M:%S}\n"
    )

    file.write(
        f"Control file: {control_file}\n"
    )

    file.write(
        f"Domain name: {domain_name}\n"
    )

    file.write(
        f"Domain folder: {domain_folder}\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("FOLDER STRUCTURE CREATED SUCCESSFULLY")
print("=" * 70)

print()
print(f"Domain       : {domain_name}")
print(f"Domain folder: {domain_folder}")
print(f"Control file : {control_file}")
print(f"Workflow log : {log_file}")

print()
print("No control_active.txt was created or modified.")