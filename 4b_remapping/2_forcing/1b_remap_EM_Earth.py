#!/usr/bin/env python3
# coding: utf-8

# Create EM-Earth -> SUMMA HRU EASYMORE remapping information.
#
# Purpose
# -------
# Use one prepared EM-Earth monthly forcing file to generate
# reusable spatial remapping information for all EM-Earth months.
#
# NWAM uses EM-Earth for:
#
#   pptrate
#   airtemp
#
# IMPORTANT
# ---------
# The EASYMORE target shapefile is the Stage-00 prepared CWARHM
# catchment:
#
#   <root_path>/domain_<domain_name>/shapefiles/catchment/
#
# It is NOT the original read-only MERIT source shapefile.
#
# The prepared copy must contain the SUMMA HRU fields and a
# persistent EPSG:4326 CRS.
#
# Usage
# -----
# python 1b_remap_EM_Earth.py

import os
import glob
from pathlib import Path
from shutil import rmtree, copyfile
from datetime import datetime

import geopandas as gpd
import easymore


# ============================================================
# PROJECT PATHS
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

# Script:
# CWARHM/4b_remapping/2_forcing/
#
# parents[1] = CWARHM
CWARHM_ROOT = SCRIPT_DIR.parents[1]


CONTROL_FILE = (
    CWARHM_ROOT
    / "0_control_files"
    / "control_active.txt"
)


if not CONTROL_FILE.exists():

    raise FileNotFoundError(
        f"Control file not found:\n"
        f"{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FILE HANDLING
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

            return (
                right
                .split("#", 1)[0]
                .strip()
            )

    raise ValueError(
        f"Setting '{setting}' not found in:\n"
        f"{file}"
    )


def make_default_path(suffix):
    """
    Construct a path within the active CWARHM domain.
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

domain = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


print()
print("=" * 70)
print("EM-EARTH EASYMORE REMAPPING")
print("=" * 70)

print(
    f"Domain: {domain}"
)


# ============================================================
# PREPARED CATCHMENT / HRU SHAPEFILE
# ============================================================

catchment_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
)


catchment_path = make_default_path(
    "shapefiles/catchment"
)


catchment_file = (
    catchment_path
    / catchment_name
)


if not catchment_file.exists():

    raise FileNotFoundError(
        "Prepared CWARHM catchment shapefile was not found:\n"
        f"{catchment_file}\n\n"
        "Run Stage 00 "
        "00_prepare_domain_shapefiles first."
    )


# ============================================================
# VALIDATE TARGET CATCHMENT
# ============================================================

target_gdf = gpd.read_file(
    catchment_file,
    engine="fiona"
)


if len(target_gdf) == 0:

    raise RuntimeError(
        "Prepared target catchment contains no features."
    )


if target_gdf.crs is None:

    raise RuntimeError(
        "Prepared CWARHM catchment has no CRS:\n"
        f"{catchment_file}\n\n"
        "Stage 00 should create this file with EPSG:4326 "
        "and a persistent .prj file."
    )


target_epsg = (
    target_gdf.crs.to_epsg()
)


if target_epsg != 4326:

    raise RuntimeError(
        "Prepared CWARHM catchment has an unexpected CRS.\n\n"
        f"Expected : EPSG:4326\n"
        f"Found    : {target_gdf.crs}\n"
        f"File     : {catchment_file}"
    )


target_id_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)

target_lat_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_lat"
)

target_lon_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_lon"
)


required_target_fields = [
    target_id_field,
    target_lat_field,
    target_lon_field,
]


missing_target_fields = [
    field
    for field in required_target_fields
    if field not in target_gdf.columns
]


if missing_target_fields:

    raise RuntimeError(
        "Prepared catchment is missing required EASYMORE "
        "field(s): "
        + ", ".join(
            missing_target_fields
        )
    )


if target_gdf[
    target_id_field
].isna().any():

    raise RuntimeError(
        f"{target_id_field} contains missing values."
    )


if target_gdf[
    target_id_field
].duplicated().any():

    raise RuntimeError(
        f"{target_id_field} contains duplicate HRU IDs."
    )


# ============================================================
# EM-EARTH GRID SHAPEFILE
# ============================================================

forcing_shape_path = read_from_control(
    CONTROL_FILE,
    "forcing_shape_path"
)


if forcing_shape_path == "default":

    forcing_shape_path = make_default_path(
        "shapefiles/forcing"
    )

else:

    forcing_shape_path = Path(
        forcing_shape_path
    )


forcing_shape_name = read_from_control(
    CONTROL_FILE,
    "forcing_emearth_shape_name"
)


forcing_shape_file = (
    forcing_shape_path
    / forcing_shape_name
)


if not forcing_shape_file.exists():

    raise FileNotFoundError(
        "EM-Earth forcing-grid shapefile not found:\n"
        f"{forcing_shape_file}"
    )


# ============================================================
# VALIDATE EM-EARTH GRID SHAPEFILE
# ============================================================

source_grid_gdf = gpd.read_file(
    forcing_shape_file,
    engine="fiona"
)


if len(source_grid_gdf) == 0:

    raise RuntimeError(
        "EM-Earth forcing-grid shapefile contains no features."
    )


if source_grid_gdf.crs is None:

    raise RuntimeError(
        "EM-Earth forcing-grid shapefile has no CRS:\n"
        f"{forcing_shape_file}"
    )


source_grid_epsg = (
    source_grid_gdf.crs.to_epsg()
)


if source_grid_epsg != 4326:

    raise RuntimeError(
        "EM-Earth forcing-grid shapefile has an unexpected CRS.\n\n"
        f"Expected : EPSG:4326\n"
        f"Found    : {source_grid_gdf.crs}"
    )


source_lat_field = read_from_control(
    CONTROL_FILE,
    "forcing_shape_lat_name"
)

source_lon_field = read_from_control(
    CONTROL_FILE,
    "forcing_shape_lon_name"
)


missing_source_fields = [
    field
    for field in [
        source_lat_field,
        source_lon_field,
    ]
    if field not in source_grid_gdf.columns
]


if missing_source_fields:

    raise RuntimeError(
        "EM-Earth forcing grid is missing required field(s): "
        + ", ".join(
            missing_source_fields
        )
    )


# ============================================================
# PREPARED EM-EARTH FORCING
# ============================================================

forcing_path = make_default_path(
    "forcing/1_raw_data/EM_Earth_prepared"
)


forcing_files = sorted(
    forcing_path.glob(
        "EM_Earth_SUMMA_*.nc"
    )
)


if not forcing_files:

    raise FileNotFoundError(
        "No prepared EM-Earth forcing files were found in:\n"
        f"{forcing_path}"
    )


forcing_file = forcing_files[0]


# ============================================================
# EM-EARTH INTERSECTION / REMAPPING OUTPUT
# ============================================================

intersect_path = make_default_path(
    "shapefiles/catchment_intersection/"
    "with_forcing/EM_Earth"
)


intersect_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# TEMPORARY EASYMORE DIRECTORY
# ============================================================

forcing_easymore_path = make_default_path(
    "forcing/3_temp_easymore/EM_Earth"
)


if forcing_easymore_path.exists():

    rmtree(
        forcing_easymore_path
    )


forcing_easymore_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# EM-EARTH BASIN-AVERAGED OUTPUT DIRECTORY
# ============================================================

forcing_basin_path = make_default_path(
    "forcing/3_basin_averaged_data/EM_Earth"
)


forcing_basin_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# REPORT INPUTS
# ============================================================

print()
print("Inputs")
print("-" * 70)

print(
    f"Source forcing : {forcing_file}"
)

print(
    f"Source grid    : {forcing_shape_file}"
)

print(
    f"Source CRS     : {source_grid_gdf.crs}"
)

print(
    f"Target HRUs    : {catchment_file}"
)

print(
    f"Target CRS     : {target_gdf.crs}"
)

print(
    f"Target HRUs    : {len(target_gdf):,}"
)


# ============================================================
# EASYMORE SETUP
# ============================================================

esmr = easymore.Easymore()


esmr.author_name = (
    "NWAM-SUMMA workflow"
)

esmr.license = (
    "EM-Earth meteorological forcing"
)


esmr.case_name = (
    domain
    + "_EM_Earth"
)


# ------------------------------------------------------------
# Source forcing-grid shapefile
# ------------------------------------------------------------

esmr.source_shp = str(
    forcing_shape_file
)

esmr.source_shp_lat = (
    source_lat_field
)

esmr.source_shp_lon = (
    source_lon_field
)


# ------------------------------------------------------------
# Target HRU shapefile
# ------------------------------------------------------------

esmr.target_shp = str(
    catchment_file
)

esmr.target_shp_ID = (
    target_id_field
)

esmr.target_shp_lat = (
    target_lat_field
)

esmr.target_shp_lon = (
    target_lon_field
)


# ------------------------------------------------------------
# EM-Earth NetCDF
# ------------------------------------------------------------

esmr.source_nc = str(
    forcing_file
)


esmr.var_names = [
    "pptrate",
    "airtemp",
]


esmr.var_lat = "latitude"
esmr.var_lon = "longitude"
esmr.var_time = "time"


# ------------------------------------------------------------
# EASYMORE directories
# ------------------------------------------------------------

esmr.temp_dir = (
    str(
        forcing_easymore_path
    )
    + "/"
)


esmr.output_dir = (
    str(
        forcing_basin_path
    )
    + "/"
)


# ------------------------------------------------------------
# SUMMA-compatible remapped structure
# ------------------------------------------------------------

esmr.remapped_dim_id = "hru"
esmr.remapped_var_id = "hruId"


esmr.format_list = [
    "f4"
]


esmr.fill_value_list = [
    "-9999"
]


esmr.save_csv = False
esmr.remap_csv = ""
esmr.sort_ID = False


# ============================================================
# RUN EASYMORE
# ============================================================

print()
print("Running EASYMORE...")


esmr.nc_remapper()


# ============================================================
# SAVE REMAPPING PRODUCTS
# ============================================================

print()
print("Saving remapping products...")


# ------------------------------------------------------------
# Remapping NetCDF
# ------------------------------------------------------------

remap_nc = (
    Path(
        esmr.temp_dir
    )
    / (
        f"{esmr.case_name}"
        "_remapping.nc"
    )
)


if remap_nc.exists():

    destination = (
        intersect_path
        / remap_nc.name
    )

    copyfile(
        remap_nc,
        destination
    )

    print(
        f"Saved remapping NetCDF:\n"
        f"{destination}"
    )

else:

    print(
        "WARNING: EASYMORE remapping NetCDF "
        "was not found."
    )


# ------------------------------------------------------------
# Hashed remapping CSV
# ------------------------------------------------------------

remap_csv_files = list(
    Path(
        esmr.temp_dir
    ).glob(
        f"{esmr.case_name}"
        "_remapping_file_*.csv"
    )
)


if remap_csv_files:

    for remap_csv in remap_csv_files:

        destination = (
            intersect_path
            / remap_csv.name
        )

        copyfile(
            remap_csv,
            destination
        )

        print(
            f"Saved remapping CSV:\n"
            f"{destination}"
        )

else:

    print(
        "WARNING: No EASYMORE remapping CSV "
        "was found."
    )


# ------------------------------------------------------------
# Intersected shapefile
# ------------------------------------------------------------

intersect_files = glob.glob(
    esmr.temp_dir
    + esmr.case_name
    + "_intersected_shapefile.*"
)


if intersect_files:

    for file in intersect_files:

        destination = (
            intersect_path
            / os.path.basename(
                file
            )
        )

        copyfile(
            file,
            destination
        )

    print(
        "Saved intersected shapefile components."
    )

else:

    print(
        "WARNING: No intersected shapefile "
        "components were found."
    )


# ============================================================
# REMOVE TEMPORARY EASYMORE DIRECTORY
# ============================================================

try:

    rmtree(
        esmr.temp_dir
    )

except OSError as error:

    print()
    print(
        "WARNING: Could not remove temporary "
        "EASYMORE directory:"
    )

    print(
        error
    )


# ============================================================
# LOGGING
# ============================================================

log_folder = (
    intersect_path
    / "_workflow_log"
)


log_folder.mkdir(
    parents=True,
    exist_ok=True
)


this_file = Path(
    __file__
).name


try:

    copyfile(
        Path(__file__).resolve(),
        log_folder
        / this_file
    )

except OSError:

    pass


now = datetime.now()


log_file = (
    log_folder
    / (
        f"{now:%Y%m%d}_"
        "EM_Earth_remapping_log.txt"
    )
)


with open(
    log_file,
    "w"
) as file:

    file.write(
        f"Log generated by {this_file} on "
        f"{now:%Y/%m/%d %H:%M:%S}\n"
    )

    file.write(
        f"Domain: {domain}\n"
    )

    file.write(
        f"Target catchment: "
        f"{catchment_file}\n"
    )

    file.write(
        "Target CRS: EPSG:4326\n"
    )

    file.write(
        f"Template forcing file: "
        f"{forcing_file.name}\n"
    )

    file.write(
        "Created EM-Earth-to-HRU "
        "EASYMORE remapping.\n"
    )

    file.write(
        "Variables: pptrate, airtemp.\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("EM-EARTH ONE-MONTH REMAPPING COMPLETED")
print("=" * 70)

print()
print(
    "Prepared target HRUs:"
)

print(
    catchment_file
)

print()
print(
    "Basin-averaged forcing:"
)

print(
    forcing_basin_path
)

print()
print(
    "Reusable remapping products:"
)

print(
    intersect_path
)

print()
print(
    "Workflow log:"
)

print(
    log_file
)