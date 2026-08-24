#!/usr/bin/env python
# coding: utf-8

"""
CWARHM workflow: make folder structure

This script:

1. Reads a domain-specific control file supplied as a command-line argument;
2. Copies it to 0_control_files/control_active.txt;
3. Creates the domain folder structure;
4. Stores copies of the control file and this script in the workflow log.

Usage:

python make_folder_structure.py \
../0_control_files/control_DOMAIN.txt
"""

import sys
from pathlib import Path
from shutil import copyfile
from datetime import datetime


# ============================================================
# INPUT CONTROL FILE
# ============================================================

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage:\n"
        "python make_folder_structure.py "
        "../0_control_files/control_DOMAIN.txt"
    )


source_control = Path(sys.argv[1]).resolve()

if not source_control.exists():
    raise FileNotFoundError(
        f"Control file not found:\n{source_control}"
    )


# ============================================================
# CONTROL-FILE LOCATIONS
# ============================================================

controlFolder = Path("../0_control_files").resolve()

controlFile = "control_active.txt"

active_control = controlFolder / controlFile


# ============================================================
# COPY DOMAIN CONTROL TO control_active.txt
# ============================================================

copyfile(
    source_control,
    active_control
)

print("Source control file:")
print(source_control)

print("\nActive control file:")
print(active_control)


# ============================================================
# FUNCTION TO READ CONTROL SETTINGS
# ============================================================

def read_from_control(file, setting):

    with open(file) as contents:

        for line in contents:

            if (
                line.startswith(setting)
                and not line.startswith("#")
            ):

                value = line.split("|", 1)[1]
                value = value.split("#", 1)[0]

                return value.strip()

    raise ValueError(
        f"Setting '{setting}' not found in:\n{file}"
    )


# ============================================================
# DOMAIN SETTINGS
# ============================================================

rootPath = Path(
    read_from_control(
        active_control,
        "root_path"
    )
)

domainName = read_from_control(
    active_control,
    "domain_name"
)

domainFolder = (
    rootPath /
    f"domain_{domainName}"
)

domainFolder.mkdir(
    parents=True,
    exist_ok=True
)


print("\nDomain:")
print(domainName)

print("\nDomain folder:")
print(domainFolder)


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
        domainFolder /
        folder
    ).mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# WORKFLOW LOG
# ============================================================

logFolder = (
    domainFolder /
    "_workflow_log"
)

logFolder.mkdir(
    parents=True,
    exist_ok=True
)


# Copy the original domain-specific control file.

copyfile(
    source_control,
    logFolder / source_control.name
)


# Copy this script.

thisFile = Path(__file__).name

copyfile(
    Path(__file__).resolve(),
    logFolder / thisFile
)


# ============================================================
# CREATE LOG FILE
# ============================================================

now = datetime.now()

logFile = (
    logFolder /
    f"{now.strftime('%Y%m%d')}_folder_structure_log.txt"
)


with open(logFile, "w") as file:

    file.write(
        f"Log generated by {thisFile} on "
        f"{now.strftime('%Y/%m/%d %H:%M:%S')}\n"
    )

    file.write(
        f"Source control file: "
        f"{source_control}\n"
    )

    file.write(
        f"Active control file: "
        f"{active_control}\n"
    )

    file.write(
        f"Domain folder: "
        f"{domainFolder}\n"
    )


print("\nFolder structure created successfully.")

print("\nWorkflow log:")
print(logFile)