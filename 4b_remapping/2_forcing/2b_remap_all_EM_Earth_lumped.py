#!/usr/bin/env python3
# coding: utf-8

"""
Remap prepared EM-Earth forcing to one lumped SUMMA HRU using
reusable EASYMORE remapping weights.

Purpose
-------
This is the lumped equivalent of:

    2b_remap_all_EM_Earth.py

The distributed prepared EM-Earth forcing is reused directly.
Only the spatial remapping target changes.

Input forcing:
    <root_path>/domain_<domain>/forcing/1_raw_data/EM_Earth_prepared/

Lumped target:
    <root_path>/domain_<domain>/lumped/shapefiles/catchment/
        <domain>_lumped_basin.shp

Reusable lumped remapping:
    <root_path>/domain_<domain>/lumped/shapefiles/
        catchment_intersection/with_forcing/EM_Earth/

Output:
    <root_path>/domain_<domain>/lumped/forcing/
        3_basin_averaged_data/EM_Earth/

Usage
-----
One month:

    python 2b_remap_all_EM_Earth_lumped.py \
        /path/to/control_DOMAIN_lumped.txt YEAR MONTH

Complete period serially:

    python 2b_remap_all_EM_Earth_lumped.py \
        /path/to/control_DOMAIN_lumped.txt
"""

import sys
from pathlib import Path
from shutil import rmtree
from datetime import datetime

import easymore
import geopandas as gpd
import numpy as np
import xarray as xr


# ============================================================
# INPUT ARGUMENTS
# ============================================================

if len(sys.argv) not in (2, 4):

    raise SystemExit(
        "Usage:\n\n"
        "One month:\n"
        "  python 2b_remap_all_EM_Earth_lumped.py "
        "/path/to/control_DOMAIN_lumped.txt YEAR MONTH\n\n"
        "Complete period serially:\n"
        "  python 2b_remap_all_EM_Earth_lumped.py "
        "/path/to/control_DOMAIN_lumped.txt"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).expanduser().resolve()


if not CONTROL_FILE.exists():

    raise FileNotFoundError(
        f"Control file not found:\n{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(file, setting):

    with file.open() as contents:

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

            value = (
                right
                .split("#", 1)[0]
                .strip()
            )

            if not value:

                raise ValueError(
                    f"Setting '{setting}' is empty in:\n"
                    f"{file}"
                )

            return value

    raise ValueError(
        f"Setting '{setting}' not found in:\n"
        f"{file}"
    )


# ============================================================
# DOMAIN PATH HELPERS
# ============================================================

root_path = Path(
    read_from_control(
        CONTROL_FILE,
        "root_path"
    )
)


domain = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


domain_root = (
    root_path
    / f"domain_{domain}"
)


lumped_root = (
    domain_root
    / "lumped"
)


def make_distributed_path(suffix):

    return (
        domain_root
        / suffix
    )


def make_lumped_path(suffix):

    return (
        lumped_root
        / suffix
    )


# ============================================================
# FORCING PERIOD
# ============================================================

forcing_raw_time = read_from_control(
    CONTROL_FILE,
    "forcing_raw_time"
)


try:

    start_year, end_year = [
        int(value.strip())
        for value in forcing_raw_time.split(",")
    ]

except Exception as exc:

    raise RuntimeError(
        "forcing_raw_time must contain:\n"
        "START_YEAR,END_YEAR\n\n"
        f"Found: {forcing_raw_time}"
    ) from exc


if start_year > end_year:

    raise RuntimeError(
        "forcing_raw_time has start year greater "
        "than end year."
    )


# ============================================================
# INPUT / OUTPUT PATHS
# ============================================================

# IMPORTANT:
# Reuse the already prepared distributed forcing.
input_dir = make_distributed_path(
    "forcing/1_raw_data/EM_Earth_prepared"
)


output_dir = make_lumped_path(
    "forcing/3_basin_averaged_data/EM_Earth"
)


remap_dir = make_lumped_path(
    "shapefiles/catchment_intersection/"
    "with_forcing/EM_Earth"
)


temp_root = make_lumped_path(
    "forcing/3_temp_easymore/EM_Earth"
)


output_dir.mkdir(
    parents=True,
    exist_ok=True
)


temp_root.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FORCING GRID
# ============================================================

forcing_shape_name = read_from_control(
    CONTROL_FILE,
    "forcing_emearth_shape_name"
)


# The lumped remapping initialization uses the existing
# distributed forcing grid rather than regenerating it.
distributed_forcing_shape_path = make_distributed_path(
    "shapefiles/forcing"
)


forcing_shape_file = (
    distributed_forcing_shape_path
    / forcing_shape_name
)


source_lat_field = read_from_control(
    CONTROL_FILE,
    "forcing_shape_lat_name"
)


source_lon_field = read_from_control(
    CONTROL_FILE,
    "forcing_shape_lon_name"
)


# ============================================================
# LUMPED CATCHMENT
# ============================================================

# Do NOT use catchment_shp_name from the control here.
# The control intentionally retains the distributed source
# catchment name.
#
# The lumped catchment generated by
# 2_prepare_lumped_catchment.py follows this naming convention.

catchment_name = (
    f"{domain}_lumped_basin.shp"
)


catchment_file = make_lumped_path(
    f"shapefiles/catchment/{catchment_name}"
)


target_hru_id = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)


target_lat = read_from_control(
    CONTROL_FILE,
    "catchment_shp_lat"
)


target_lon = read_from_control(
    CONTROL_FILE,
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
        "EM-Earth forcing-grid shapefile not found:\n"
        f"{forcing_shape_file}"
    )


if not catchment_file.exists():

    raise FileNotFoundError(
        "Lumped catchment shapefile not found:\n"
        f"{catchment_file}\n\n"
        "Run the lumped catchment preparation step first."
    )


if not remap_dir.exists():

    raise FileNotFoundError(
        "Lumped EM-Earth remapping directory not found:\n"
        f"{remap_dir}\n\n"
        "Run the lumped forcing remapping initialization first."
    )


# ============================================================
# VALIDATE LUMPED CATCHMENT
# ============================================================

catchment = gpd.read_file(
    catchment_file,
    engine="fiona"
)


if len(catchment) != 1:

    raise RuntimeError(
        "Lumped catchment must contain exactly one feature.\n"
        f"Found: {len(catchment)}"
    )


if catchment.crs is None:

    raise RuntimeError(
        "Lumped catchment has no CRS:\n"
        f"{catchment_file}"
    )


if catchment.crs.to_epsg() != 4326:

    raise RuntimeError(
        "Lumped catchment must use EPSG:4326.\n\n"
        f"Found: {catchment.crs}"
    )


required_target_fields = [
    target_hru_id,
    target_lat,
    target_lon,
]


missing_target_fields = [
    field
    for field in required_target_fields
    if field not in catchment.columns
]


if missing_target_fields:

    raise RuntimeError(
        "Lumped catchment is missing required field(s):\n"
        + "\n".join(
            f"  {field}"
            for field in missing_target_fields
        )
    )


expected_hru_ids = (
    catchment[target_hru_id]
    .astype(np.int64)
    .to_numpy()
)


if expected_hru_ids.size != 1:

    raise RuntimeError(
        "Expected exactly one lumped HRU."
    )


if int(expected_hru_ids[0]) != 1:

    raise RuntimeError(
        "Expected lumped HRU_ID = 1.\n"
        f"Found: {expected_hru_ids.tolist()}"
    )


for field in [
    target_lat,
    target_lon,
]:

    values = (
        catchment[field]
        .astype(float)
        .to_numpy()
    )

    if not np.all(
        np.isfinite(values)
    ):

        raise RuntimeError(
            f"{field} contains non-finite values."
        )


# ============================================================
# VALIDATE SOURCE GRID
# ============================================================

source_grid = gpd.read_file(
    forcing_shape_file,
    engine="fiona"
)


if len(source_grid) == 0:

    raise RuntimeError(
        "EM-Earth forcing grid contains no features."
    )


if source_grid.crs is None:

    raise RuntimeError(
        "EM-Earth forcing grid has no CRS."
    )


if source_grid.crs.to_epsg() != 4326:

    raise RuntimeError(
        "EM-Earth forcing grid must use EPSG:4326.\n\n"
        f"Found: {source_grid.crs}"
    )


for field in [
    source_lat_field,
    source_lon_field,
]:

    if field not in source_grid.columns:

        raise RuntimeError(
            "EM-Earth forcing grid is missing field:\n"
            f"{field}"
        )


# ============================================================
# FIND REUSABLE LUMPED REMAPPING CSV
# ============================================================

case_name = (
    f"{domain}_lumped_EM_Earth"
)


remap_files = sorted(
    remap_dir.glob(
        f"{case_name}_remapping_file_*.csv"
    )
)


if not remap_files:

    raise RuntimeError(
        "No lumped EM-Earth EASYMORE remapping CSV "
        "was found in:\n"
        f"{remap_dir}\n\n"
        "Run the lumped remapping initialization first."
    )


# Re-runs can leave multiple mapping files.
# Always use the newest.
remap_csv = max(
    remap_files,
    key=lambda path: path.stat().st_mtime
)


# ============================================================
# VARIABLES
# ============================================================

EMEARTH_VARIABLES = [
    "pptrate",
    "airtemp",
]


# ============================================================
# REPORT GLOBAL SETTINGS
# ============================================================

print()
print("=" * 78)
print("LUMPED EM-EARTH MONTHLY REMAPPING")
print("=" * 78)

print(f"Domain             : {domain}")
print(f"Control file       : {CONTROL_FILE}")
print(f"Forcing period     : {start_year}-{end_year}")
print(f"Input forcing      : {input_dir}")
print(f"Lumped catchment   : {catchment_file}")
print(f"Target HRUs        : {len(catchment)}")
print(f"HRU IDs            : {expected_hru_ids.tolist()}")
print(f"EM-Earth grid      : {forcing_shape_file}")
print(f"Source grid cells  : {len(source_grid)}")
print(f"Remapping CSV      : {remap_csv}")
print(f"Output directory   : {output_dir}")
print(
    "Variables           : "
    + ", ".join(
        EMEARTH_VARIABLES
    )
)


# ============================================================
# OUTPUT VALIDATION
# ============================================================

def validate_output(
    output_file,
    source_file,
):

    if not output_file.exists():

        raise RuntimeError(
            "Expected lumped EM-Earth output "
            "was not created:\n"
            f"{output_file}"
        )


    with xr.open_dataset(
        source_file
    ) as source_ds:

        expected_time_steps = (
            source_ds.sizes.get(
                "time"
            )
        )


    with xr.open_dataset(
        output_file
    ) as ds:

        if "hru" not in ds.sizes:

            raise RuntimeError(
                "Lumped EM-Earth output has no "
                "'hru' dimension."
            )


        if ds.sizes["hru"] != 1:

            raise RuntimeError(
                "Lumped EM-Earth output must contain "
                "exactly one HRU.\n\n"
                f"Found: {ds.sizes['hru']}"
            )


        if "time" not in ds.sizes:

            raise RuntimeError(
                "Lumped EM-Earth output has no "
                "time dimension."
            )


        if (
            expected_time_steps is not None
            and ds.sizes["time"] != expected_time_steps
        ):

            raise RuntimeError(
                "Lumped EM-Earth time-step count "
                "differs from source.\n\n"
                f"Expected: {expected_time_steps}\n"
                f"Found   : {ds.sizes['time']}"
            )


        if "hruId" not in ds.variables:

            raise RuntimeError(
                "hruId is missing from lumped "
                "EM-Earth output."
            )


        output_hru_ids = (
            np.asarray(
                ds["hruId"].values
            )
            .astype(np.int64)
            .reshape(-1)
        )


        if not np.array_equal(
            output_hru_ids,
            expected_hru_ids
        ):

            raise RuntimeError(
                "Lumped EM-Earth hruId does not match "
                "the lumped catchment.\n\n"
                f"Expected: {expected_hru_ids.tolist()}\n"
                f"Found   : {output_hru_ids.tolist()}"
            )


        missing_variables = [
            variable
            for variable in EMEARTH_VARIABLES
            if variable not in ds.variables
        ]


        if missing_variables:

            raise RuntimeError(
                "Lumped EM-Earth output is missing "
                "variable(s): "
                + ", ".join(
                    missing_variables
                )
            )


        missing_counts = {}
        value_ranges = {}


        for variable in EMEARTH_VARIABLES:

            data = ds[
                variable
            ]


            missing_counts[
                variable
            ] = int(
                data
                .isnull()
                .sum()
                .values
            )


            if (
                missing_counts[
                    variable
                ]
                < data.size
            ):

                value_ranges[
                    variable
                ] = (
                    float(
                        data.min(
                            skipna=True
                        )
                    ),
                    float(
                        data.max(
                            skipna=True
                        )
                    )
                )

            else:

                value_ranges[
                    variable
                ] = (
                    np.nan,
                    np.nan
                )


        output_time_steps = (
            ds.sizes["time"]
        )


    return (
        output_time_steps,
        missing_counts,
        value_ranges
    )


# ============================================================
# MONTH PROCESSOR
# ============================================================

def remap_month(
    year,
    month,
):

    ym = (
        f"{year}{month:02d}"
    )


    forcing_file = (
        input_dir
        / f"EM_Earth_SUMMA_{ym}.nc"
    )


    expected_output = (
        output_dir
        / (
            f"{case_name}_remapped_"
            f"{forcing_file.name}"
        )
    )


    if not forcing_file.exists():

        raise FileNotFoundError(
            "Prepared EM-Earth forcing file "
            "not found:\n"
            f"{forcing_file}"
        )


    print()
    print("-" * 78)
    print(f"LUMPED EM-EARTH REMAPPING: {ym}")
    print("-" * 78)

    print(f"Input       : {forcing_file}")
    print(f"Output      : {expected_output}")
    print(f"Remap CSV   : {remap_csv}")
    print("Target HRUs : 1")


    # --------------------------------------------------------
    # EXISTING OUTPUT
    # --------------------------------------------------------

    if expected_output.exists():

        print()
        print(
            "Output already exists. "
            "Validating existing file..."
        )


        (
            output_time_steps,
            missing_counts,
            value_ranges,
        ) = validate_output(
            expected_output,
            forcing_file,
        )


        print(
            "Existing output passed validation."
        )

        print(
            f"Time steps : {output_time_steps}"
        )

        print(
            "PASS: "
            f"{domain} {ym}"
        )

        return


    # --------------------------------------------------------
    # UNIQUE TEMP DIRECTORY
    # --------------------------------------------------------

    temp_dir = (
        temp_root
        / ym
    )


    if temp_dir.exists():

        rmtree(
            temp_dir
        )


    temp_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    # --------------------------------------------------------
    # EASYMORE
    # --------------------------------------------------------

    esmr = easymore.Easymore()


    esmr.case_name = (
        case_name
    )


    esmr.author_name = (
        "NWAM-SUMMA lumped workflow"
    )


    esmr.license = (
        "EM-Earth meteorological forcing"
    )


    esmr.var_names = (
        EMEARTH_VARIABLES
    )

    esmr.var_lat = (
        "latitude"
    )

    esmr.var_lon = (
        "longitude"
    )

    esmr.var_time = (
        "time"
    )


    esmr.source_shp = str(
        forcing_shape_file
    )

    esmr.source_shp_lat = (
        source_lat_field
    )

    esmr.source_shp_lon = (
        source_lon_field
    )


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


    esmr.source_nc = str(
        forcing_file
    )


    esmr.output_dir = (
        str(
            output_dir
        )
        + "/"
    )


    esmr.temp_dir = (
        str(
            temp_dir
        )
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


    # Reuse the previously generated one-HRU mapping.
    esmr.remap_csv = str(
        remap_csv
    )


    esmr.sort_ID = False


    esmr.overwrite_existing_remap = (
        False
    )


    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

    print()
    print("Running EASYMORE...")


    esmr.nc_remapper()


    # --------------------------------------------------------
    # VERIFY
    # --------------------------------------------------------

    if not expected_output.exists():

        alternatives = sorted(
            output_dir.glob(
                f"*{ym}*.nc"
            )
        )


        alternative_text = (
            "\n".join(
                str(path)
                for path in alternatives
            )
            if alternatives
            else "None"
        )


        raise RuntimeError(
            "EASYMORE completed but the expected "
            "lumped EM-Earth output was not created.\n\n"
            f"Expected:\n{expected_output}\n\n"
            f"Other files containing {ym}:\n"
            f"{alternative_text}"
        )


    (
        output_time_steps,
        missing_counts,
        value_ranges,
    ) = validate_output(
        expected_output,
        forcing_file,
    )


    # --------------------------------------------------------
    # CLEAN TEMP DIRECTORY
    # --------------------------------------------------------

    try:

        rmtree(
            temp_dir
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


    timestamp = datetime.now()


    log_file = (
        log_dir
        / (
            f"{timestamp:%Y%m%d_%H%M%S}_"
            f"EM_Earth_lumped_remap_{ym}.txt"
        )
    )


    with log_file.open("w") as file:

        file.write(
            "Lumped EM-Earth monthly remapping "
            f"completed {timestamp:%Y-%m-%d %H:%M:%S}\n"
        )

        file.write(
            f"Domain: {domain}\n"
        )

        file.write(
            f"Control file: {CONTROL_FILE}\n"
        )

        file.write(
            f"Month: {ym}\n"
        )

        file.write(
            f"Input: {forcing_file}\n"
        )

        file.write(
            f"Output: {expected_output}\n"
        )

        file.write(
            f"Lumped catchment: {catchment_file}\n"
        )

        file.write(
            "Target HRUs: 1\n"
        )

        file.write(
            f"Remapping CSV: {remap_csv}\n"
        )

        file.write(
            f"Time steps: {output_time_steps}\n"
        )

        file.write(
            f"Missing values: {missing_counts}\n"
        )

        file.write(
            f"Value ranges: {value_ranges}\n"
        )

        file.write(
            "Shared control_active.txt used: no\n"
        )


    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    print()
    print("Validation:")
    print("  HRUs       : 1")
    print(
        f"  hruId      : "
        f"{expected_hru_ids.tolist()}"
    )
    print(
        f"  Time steps : "
        f"{output_time_steps}"
    )


    print()
    print("Missing values:")

    for variable in EMEARTH_VARIABLES:

        print(
            f"  {variable:<10}: "
            f"{missing_counts[variable]}"
        )


    print()
    print("Value ranges:")

    for variable in EMEARTH_VARIABLES:

        minimum, maximum = (
            value_ranges[
                variable
            ]
        )

        print(
            f"  {variable:<10}: "
            f"{minimum:.6g} to "
            f"{maximum:.6g}"
        )


    print()
    print(
        f"PASS: {domain} {ym}"
    )

    print(
        f"Workflow log: {log_file}"
    )


# ============================================================
# COMMAND-LINE MODE
# ============================================================

if len(sys.argv) == 4:

    try:

        selected_year = int(
            sys.argv[2]
        )

        selected_month = int(
            sys.argv[3]
        )

    except ValueError as exc:

        raise SystemExit(
            "YEAR and MONTH must be integers."
        ) from exc


    if not (
        start_year
        <= selected_year
        <= end_year
    ):

        raise ValueError(
            f"Year {selected_year} is outside "
            f"forcing_raw_time "
            f"{start_year},{end_year}."
        )


    if not (
        1
        <= selected_month
        <= 12
    ):

        raise ValueError(
            "Month must be between 1 and 12."
        )


    remap_month(
        selected_year,
        selected_month,
    )


# ============================================================
# SERIAL MODE
# ============================================================

else:

    print()
    print(
        "No YEAR/MONTH supplied."
    )

    print(
        "Processing complete forcing period serially."
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
                month,
            )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 78)
print("LUMPED EM-EARTH MONTHLY REMAPPING COMPLETED")
print("=" * 78)

print(f"Domain       : {domain}")
print(f"Control file : {CONTROL_FILE}")
print(f"Output       : {output_dir}")
print(f"Remap CSV    : {remap_csv}")
print("Target HRUs  : 1")

print()
print(
    "No control_active.txt was created or modified."
)
