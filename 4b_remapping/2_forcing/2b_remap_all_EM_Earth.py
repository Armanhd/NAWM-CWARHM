#!/usr/bin/env python
# coding: utf-8

# Remap prepared EM-Earth forcing to SUMMA HRUs using the reusable
# EASYMORE remapping weights created in Step 13.
#
# Usage:
#
#   One month:
#       python 2b_remap_all_EM_Earth.py YEAR MONTH
#
#   Example:
#       python 2b_remap_all_EM_Earth.py 1950 1
#
#   No arguments:
#       Processes the complete forcing_raw_time period serially.
#
# For HPC processing, YEAR and MONTH are supplied by a SLURM array.
#
# IMPORTANT
# ---------
# The original MERIT catchment shapefile is treated as source data only.
#
# EASYMORE must use the prepared CWARHM catchment created during Stage 00:
#
#   <root_path>/domain_<domain_name>/shapefiles/catchment/
#
# This prepared shapefile contains:
#
#   HRU_ID
#   center_lat
#   center_lon
#
# and has a persisted EPSG:4326 CRS.

from pathlib import Path
from shutil import rmtree
from datetime import datetime
import sys

import easymore
import geopandas as gpd
import numpy as np


# ============================================================
# PROJECT PATHS
# ============================================================

script_dir = Path(__file__).resolve().parent
cwarhm_root = script_dir.parent.parent

control_file = (
    cwarhm_root
    / "0_control_files"
    / "control_active.txt"
)

if not control_file.exists():
    raise FileNotFoundError(
        f"Control file not found:\n{control_file}"
    )


# ============================================================
# CONTROL FILE
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
    """
    Construct a standard path inside domain_<domain_name>.
    """

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

    return (
        root_path
        / f"domain_{domain_name}"
        / suffix
    )


# ============================================================
# DOMAIN SETTINGS
# ============================================================

domain = read_from_control(
    control_file,
    "domain_name"
)

years = read_from_control(
    control_file,
    "forcing_raw_time"
)

start_year, end_year = [
    int(x.strip())
    for x in years.split(",")
]


# ============================================================
# FORCING PATHS
# ============================================================

input_dir = make_default_path(
    "forcing/1_raw_data/EM_Earth_prepared"
)

output_dir = make_default_path(
    "forcing/3_basin_averaged_data/EM_Earth"
)

remap_dir = make_default_path(
    "shapefiles/catchment_intersection/"
    "with_forcing/EM_Earth"
)


# ============================================================
# EM-EARTH GRID SHAPEFILE
# ============================================================

forcing_shape_path = read_from_control(
    control_file,
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
    control_file,
    "forcing_emearth_shape_name"
)

forcing_shape_file = (
    forcing_shape_path
    / forcing_shape_name
)


# ============================================================
# PREPARED CWARHM CATCHMENT SHAPEFILE
# ============================================================

# Do NOT use catchment_shp_path here.
#
# catchment_shp_path points to the original MERIT source.
# EASYMORE must use the prepared Stage-00 working copy.

catchment_name = read_from_control(
    control_file,
    "catchment_shp_name"
)

catchment_path = make_default_path(
    "shapefiles/catchment"
)

catchment_file = (
    catchment_path
    / catchment_name
)


# ============================================================
# TARGET HRU FIELD NAMES
# ============================================================

target_hru_id = read_from_control(
    control_file,
    "catchment_shp_hruid"
)

target_lat = read_from_control(
    control_file,
    "catchment_shp_lat"
)

target_lon = read_from_control(
    control_file,
    "catchment_shp_lon"
)


# ============================================================
# CHECK INPUTS
# ============================================================

if not input_dir.exists():

    raise FileNotFoundError(
        "Prepared EM-Earth directory not found:\n"
        f"{input_dir}"
    )


if not forcing_shape_file.exists():

    raise FileNotFoundError(
        "EM-Earth forcing grid not found:\n"
        f"{forcing_shape_file}"
    )


if not catchment_file.exists():

    raise FileNotFoundError(
        "Prepared CWARHM catchment shapefile not found:\n"
        f"{catchment_file}\n\n"
        "This script must use the Stage-00 prepared catchment, "
        "not the original MERIT source shapefile.\n"
        "Run Stage 00 first."
    )


if not remap_dir.exists():

    raise FileNotFoundError(
        "EM-Earth remapping directory not found:\n"
        f"{remap_dir}\n\n"
        "Run Step 13 first."
    )


output_dir.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# VALIDATE PREPARED CATCHMENT
# ============================================================

catchment_check = gpd.read_file(
    catchment_file,
    engine="fiona"
)


if len(catchment_check) == 0:

    raise RuntimeError(
        "Prepared CWARHM catchment contains no features."
    )


if catchment_check.crs is None:

    raise RuntimeError(
        "Prepared CWARHM catchment has no CRS:\n"
        f"{catchment_file}\n\n"
        "Stage 00 should write this file with EPSG:4326."
    )


catchment_epsg = (
    catchment_check.crs.to_epsg()
)


if catchment_epsg != 4326:

    raise RuntimeError(
        "Prepared CWARHM catchment is not EPSG:4326.\n\n"
        f"File: {catchment_file}\n"
        f"CRS : {catchment_check.crs}"
    )


required_target_fields = [
    target_hru_id,
    target_lat,
    target_lon
]


missing_target_fields = [
    field
    for field in required_target_fields
    if field not in catchment_check.columns
]


if missing_target_fields:

    raise RuntimeError(
        "Prepared CWARHM catchment is missing "
        "required EASYMORE field(s):\n"
        + ", ".join(missing_target_fields)
        + "\n\n"
        + "Available fields:\n"
        + f"{catchment_check.columns.tolist()}"
    )


if catchment_check[target_hru_id].isna().any():

    raise RuntimeError(
        f"{target_hru_id} contains missing values."
    )


if catchment_check[target_hru_id].duplicated().any():

    raise RuntimeError(
        f"{target_hru_id} contains duplicate values."
    )


for field in [
    target_lat,
    target_lon
]:

    values = (
        catchment_check[field]
        .astype(float)
        .to_numpy()
    )

    if not np.all(
        np.isfinite(values)
    ):

        raise RuntimeError(
            f"{field} contains non-finite values."
        )


print()
print("============================================================")
print("EM-EARTH HRU REMAPPING")
print("============================================================")

print(
    f"Domain            : {domain}"
)

print(
    f"Prepared catchment: {catchment_file}"
)

print(
    f"Catchment CRS     : {catchment_check.crs}"
)

print(
    f"HRUs              : {len(catchment_check)}"
)


# ============================================================
# FIND REUSABLE EASYMORE REMAPPING CSV
# ============================================================

case_name = (
    f"{domain}_EM_Earth"
)


remap_files = list(
    remap_dir.glob(
        f"{case_name}_remapping_file_*.csv"
    )
)


if not remap_files:

    raise RuntimeError(
        "No EM-Earth EASYMORE remapping CSV found in:\n"
        f"{remap_dir}\n\n"
        "Run Step 13 first."
    )


remap_csv = max(
    remap_files,
    key=lambda f: f.stat().st_mtime
)


print(
    f"EM-Earth remapping CSV: {remap_csv}"
)


# ============================================================
# MONTH PROCESSOR
# ============================================================

def remap_month(year, month):

    ym = (
        f"{year}{month:02d}"
    )


    forcing_file = (
        input_dir
        / f"EM_Earth_SUMMA_{ym}.nc"
    )


    if not forcing_file.exists():

        raise FileNotFoundError(
            "Prepared EM-Earth forcing file not found:\n"
            f"{forcing_file}"
        )


    expected_output = (
        output_dir
        / (
            f"{case_name}_remapped_"
            f"{forcing_file.name}"
        )
    )


    if expected_output.exists():

        print(
            f"{ym}: output already exists; skipping."
        )

        return


    print()
    print("=" * 60)
    print(
        f"EM-EARTH REMAPPING: {ym}"
    )
    print("=" * 60)

    print(
        f"Input : {forcing_file}"
    )

    print(
        f"Output: {output_dir}"
    )

    print(
        f"Target: {catchment_file}"
    )


    # Each SLURM array task uses an independent
    # temporary EASYMORE directory.
    temp_dir = make_default_path(
        f"forcing/3_temp_easymore/EM_Earth/{ym}"
    )


    temp_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    esmr = easymore.Easymore()


    esmr.case_name = (
        case_name
    )

    esmr.author_name = (
        "NWAM-SUMMA workflow"
    )


    # --------------------------------------------------------
    # Variables
    # --------------------------------------------------------

    esmr.var_names = [
        "pptrate",
        "airtemp"
    ]

    esmr.var_lat = "latitude"
    esmr.var_lon = "longitude"
    esmr.var_time = "time"


    # --------------------------------------------------------
    # Source forcing grid
    # --------------------------------------------------------

    esmr.source_shp = str(
        forcing_shape_file
    )

    esmr.source_shp_lat = read_from_control(
        control_file,
        "forcing_shape_lat_name"
    )

    esmr.source_shp_lon = read_from_control(
        control_file,
        "forcing_shape_lon_name"
    )


    # --------------------------------------------------------
    # Target HRUs
    # --------------------------------------------------------

    esmr.target_shp = str(
        catchment_file
    )

    esmr.target_shp_ID = (
        target_hru_id
    )

    esmr.target_shp_lat = (
        target_lat
    )

    esmr.target_shp_lon = (
        target_lon
    )


    # --------------------------------------------------------
    # EASYMORE
    # --------------------------------------------------------

    esmr.source_nc = str(
        forcing_file
    )


    esmr.output_dir = (
        str(output_dir)
        + "/"
    )


    esmr.temp_dir = (
        str(temp_dir)
        + "/"
    )


    esmr.remapped_dim_id = (
        "hru"
    )

    esmr.remapped_var_id = (
        "hruId"
    )


    esmr.format_list = [
        "f4"
    ]

    esmr.fill_value_list = [
        "-9999"
    ]


    esmr.save_csv = False


    # Reuse the spatial mapping created in Step 13.
    esmr.remap_csv = str(
        remap_csv
    )


    esmr.sort_ID = False

    esmr.overwrite_existing_remap = False


    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

    esmr.nc_remapper()


    # --------------------------------------------------------
    # VERIFY OUTPUT
    # --------------------------------------------------------

    if not expected_output.exists():

        # EASYMORE naming can vary slightly between versions.
        alternatives = list(
            output_dir.glob(
                f"*{ym}*.nc"
            )
        )

        if not alternatives:

            raise RuntimeError(
                "EASYMORE completed without producing "
                "the expected EM-Earth remapped NetCDF.\n\n"
                f"Expected approximately:\n"
                f"{expected_output}"
            )


    # --------------------------------------------------------
    # CLEAN TEMPORARY DIRECTORY
    # --------------------------------------------------------

    try:

        rmtree(
            temp_dir
        )

    except OSError:

        pass


    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    log_dir = (
        output_dir
        / "_workflow_log"
    )


    log_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    log_file = (
        log_dir
        / f"EM_Earth_remap_{ym}.txt"
    )


    with open(
        log_file,
        "w"
    ) as f:

        f.write(
            "EM-Earth remapping completed "
            f"{datetime.now():%Y-%m-%d %H:%M:%S}\n"
        )

        f.write(
            f"Domain: {domain}\n"
        )

        f.write(
            f"Month: {ym}\n"
        )

        f.write(
            f"Input: {forcing_file}\n"
        )

        f.write(
            f"Target catchment: {catchment_file}\n"
        )

        f.write(
            f"Target CRS: {catchment_check.crs}\n"
        )

        f.write(
            f"Remapping CSV: {remap_csv}\n"
        )


    print(
        f"{ym}: completed."
    )


# ============================================================
# COMMAND-LINE MODE
# ============================================================

if len(sys.argv) == 3:

    try:

        year = int(
            sys.argv[1]
        )

        month = int(
            sys.argv[2]
        )

    except ValueError as exc:

        raise SystemExit(
            "YEAR and MONTH must be integers."
        ) from exc


    if (
        year < start_year
        or year > end_year
    ):

        raise ValueError(
            f"Year {year} is outside "
            f"forcing_raw_time "
            f"{start_year},{end_year}"
        )


    if (
        month < 1
        or month > 12
    ):

        raise ValueError(
            "Month must be between 1 and 12."
        )


    remap_month(
        year,
        month
    )


# ============================================================
# SERIAL FALLBACK
# ============================================================

elif len(sys.argv) == 1:

    print(
        "No YEAR MONTH arguments supplied. "
        "Running complete period serially."
    )


    for year in range(
        start_year,
        end_year + 1
    ):

        for month in range(
            1,
            13
        ):

            remap_month(
                year,
                month
            )


else:

    raise SystemExit(
        "Usage:\n"
        "  python 2b_remap_all_EM_Earth.py\n"
        "or\n"
        "  python 2b_remap_all_EM_Earth.py YEAR MONTH"
    )