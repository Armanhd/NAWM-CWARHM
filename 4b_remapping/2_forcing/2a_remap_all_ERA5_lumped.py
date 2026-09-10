#!/usr/bin/env python3
# coding: utf-8

"""
Remap prepared ERA5 forcing to one lumped SUMMA HRU using reusable
EASYMORE remapping weights created by the lumped forcing-remapping step.

Purpose
-------
This is the lumped equivalent of:

    2a_remap_all_ERA5.py

The important difference is:

INPUT forcing is reused from the distributed workflow:

    <root_path>/domain_<domain_name>/forcing/1_raw_data/ERA5_prepared/

but all remapping products and outputs are written under:

    <root_path>/domain_<domain_name>/lumped/

Expected lumped target:

    exactly 1 HRU
    HRU_ID = 1

Reusable remapping files are expected at:

    domain_<DOMAIN>/lumped/
    shapefiles/catchment_intersection/with_forcing/ERA5/

Output monthly forcing is written to:

    domain_<DOMAIN>/lumped/
    forcing/3_basin_averaged_data/ERA5/

IMPORTANT
---------
This script:

    - does NOT read control_active.txt
    - does NOT modify distributed products
    - reuses distributed prepared ERA5 forcing
    - writes only lumped remapped forcing
    - supports one-month or full-period serial processing

Usage
-----

One month:

    python 2a_remap_all_ERA5_lumped.py \
        /path/to/control_DOMAIN_lumped.txt \
        YEAR MONTH

Example:

    python 2a_remap_all_ERA5_lumped.py \
        ../../0_control_files/control_CAN_01AD003_lumped.txt \
        1950 1

Complete forcing period serially:

    python 2a_remap_all_ERA5_lumped.py \
        /path/to/control_DOMAIN_lumped.txt

For production, YEAR/MONTH mode should be called from the
lumped Slurm array runner.
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
        "  python 2a_remap_all_ERA5_lumped.py "
        "/path/to/control_DOMAIN_lumped.txt YEAR MONTH\n\n"
        "Complete period serially:\n"
        "  python 2a_remap_all_ERA5_lumped.py "
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
    """
    Read one exact setting from a CWARHM control file.
    """

    with file.open() as contents:

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


# ============================================================
# DOMAIN PATH HELPERS
# ============================================================

root_path = Path(
    read_from_control(
        CONTROL_FILE,
        "root_path"
    )
).expanduser().resolve()


domain = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


DOMAIN_ROOT = (
    root_path
    / f"domain_{domain}"
)


LUMPED_ROOT = (
    DOMAIN_ROOT
    / "lumped"
)


def make_distributed_path(suffix):
    """
    Path inside the original distributed domain.

    Used only for inputs that are intentionally reused.
    """

    return (
        DOMAIN_ROOT
        / suffix
    )


def make_lumped_path(suffix):
    """
    Path inside domain_<DOMAIN>/lumped/.
    """

    return (
        LUMPED_ROOT
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
# INPUT PREPARED ERA5
# ============================================================

# IMPORTANT:
# Prepared monthly ERA5 forcing is reused from the distributed
# workflow and is NOT regenerated for the lumped workflow.

input_dir = make_distributed_path(
    "forcing/1_raw_data/ERA5_prepared"
)


if not input_dir.exists():

    raise FileNotFoundError(
        "Distributed prepared ERA5 directory not found:\n"
        f"{input_dir}\n\n"
        "The lumped workflow expects Step 4 prepared forcing "
        "to already exist."
    )


# ============================================================
# LUMPED OUTPUT DIRECTORIES
# ============================================================

output_dir = make_lumped_path(
    "forcing/3_basin_averaged_data/ERA5"
)


temp_root = make_lumped_path(
    "forcing/3_temp_easymore/ERA5"
)


remap_dir = make_lumped_path(
    "shapefiles/"
    "catchment_intersection/"
    "with_forcing/"
    "ERA5"
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
# LUMPED CATCHMENT
# ============================================================

# The lumped catchment is generated by
# 2_prepare_lumped_catchment.py using this fixed naming scheme.
#
# Do NOT use catchment_shp_name from the control here because
# that setting intentionally retains the distributed source
# catchment name.

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


if not catchment_file.exists():

    raise FileNotFoundError(
        "Lumped catchment shapefile not found:\n"
        f"{catchment_file}\n\n"
        "Run the lumped catchment preparation step first."
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
        "Lumped catchment must contain exactly one feature.\n\n"
        f"Found : {len(catchment)}\n"
        f"File  : {catchment_file}"
    )


if catchment.crs is None:

    raise RuntimeError(
        "Lumped catchment has no CRS:\n"
        f"{catchment_file}"
    )


if catchment.crs.to_epsg() != 4326:

    raise RuntimeError(
        "Lumped catchment must use EPSG:4326.\n\n"
        f"Found: {catchment.crs}\n"
        f"File : {catchment_file}"
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
        "Lumped catchment must contain exactly one HRU ID."
    )


if int(expected_hru_ids[0]) != 1:

    raise RuntimeError(
        "Lumped HRU_ID must equal 1.\n\n"
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
# ERA5 FORCING GRID
# ============================================================

forcing_shape_path_setting = read_from_control(
    CONTROL_FILE,
    "forcing_shape_path"
)


if forcing_shape_path_setting == "default":

    # For completeness. Current lumped controls normally point
    # forcing_shape_path explicitly to the lumped folder.
    forcing_shape_path = make_lumped_path(
        "shapefiles/forcing"
    )

else:

    forcing_shape_path = Path(
        forcing_shape_path_setting
    ).expanduser().resolve()


forcing_shape_name = read_from_control(
    CONTROL_FILE,
    "forcing_era5_shape_name"
)


forcing_shape_file = (
    forcing_shape_path
    / forcing_shape_name
)


if not forcing_shape_file.exists():

    # The forcing-grid geometry is unchanged between distributed
    # and lumped processing, so permit reuse of the distributed
    # forcing-grid shapefile if no separate lumped copy exists.

    distributed_grid = make_distributed_path(
        f"shapefiles/forcing/{forcing_shape_name}"
    )

    if distributed_grid.exists():

        forcing_shape_file = distributed_grid

    else:

        raise FileNotFoundError(
            "ERA5 forcing-grid shapefile not found.\n\n"
            f"Lumped path:\n"
            f"{forcing_shape_path / forcing_shape_name}\n\n"
            f"Distributed fallback:\n"
            f"{distributed_grid}"
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
# VALIDATE ERA5 GRID
# ============================================================

source_grid = gpd.read_file(
    forcing_shape_file,
    engine="fiona"
)


if len(source_grid) == 0:

    raise RuntimeError(
        "ERA5 forcing-grid shapefile contains no features."
    )


if source_grid.crs is None:

    raise RuntimeError(
        "ERA5 forcing-grid shapefile has no CRS."
    )


if source_grid.crs.to_epsg() != 4326:

    raise RuntimeError(
        "ERA5 forcing grid must use EPSG:4326.\n\n"
        f"Found: {source_grid.crs}"
    )


for field in [
    source_lat_field,
    source_lon_field,
]:

    if field not in source_grid.columns:

        raise RuntimeError(
            "ERA5 forcing grid is missing field:\n"
            f"{field}"
        )


# ============================================================
# FIND LUMPED EASYMORE REMAPPING CSV
# ============================================================

if not remap_dir.exists():

    raise FileNotFoundError(
        "Lumped ERA5 remapping directory not found:\n"
        f"{remap_dir}\n\n"
        "Run LUMPED STEP 4 first."
    )


case_name = (
    f"{domain}_lumped_ERA5"
)


remap_files = sorted(
    remap_dir.glob(
        f"{case_name}_remapping_file_*.csv"
    )
)


if not remap_files:

    # Fallback to a broader search in case an EASYMORE version
    # produced a slightly different hashed filename.
    remap_files = sorted(
        remap_dir.glob(
            "*ERA5*remapping_file_*.csv"
        )
    )


if not remap_files:

    raise RuntimeError(
        "No lumped ERA5 EASYMORE remapping CSV found in:\n"
        f"{remap_dir}\n\n"
        "Run the lumped forcing-remapping initialization first."
    )


# Use newest mapping if older files remain after re-running Step 4.

remap_csv = max(
    remap_files,
    key=lambda path: path.stat().st_mtime
)


# ============================================================
# ERA5 VARIABLES
# ============================================================

ERA5_VARIABLES = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "spechum",
    "windspd",
]


# ============================================================
# GLOBAL REPORT
# ============================================================

print()
print("=" * 78)
print("LUMPED ERA5 MONTHLY REMAPPING")
print("=" * 78)

print()
print(f"Domain              : {domain}")
print(f"Control file        : {CONTROL_FILE}")
print(f"Forcing period      : {start_year}-{end_year}")

print()
print("REUSED DISTRIBUTED INPUT")
print(f"Prepared ERA5       : {input_dir}")

print()
print("LUMPED TARGET")
print(f"Catchment           : {catchment_file}")
print(f"Target HRUs         : {len(catchment)}")
print(f"HRU IDs             : {expected_hru_ids.tolist()}")

print()
print("ERA5 GRID")
print(f"Grid shapefile      : {forcing_shape_file}")
print(f"Grid cells          : {len(source_grid)}")

print()
print("LUMPED REMAPPING")
print(f"Remapping CSV       : {remap_csv}")
print(f"Output directory    : {output_dir}")
print(f"Temporary directory : {temp_root}")

print()
print(
    "Variables            : "
    + ", ".join(
        ERA5_VARIABLES
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
            "Expected lumped ERA5 output was not created:\n"
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
                "Lumped ERA5 output has no 'hru' dimension."
            )


        if ds.sizes["hru"] != 1:

            raise RuntimeError(
                "Lumped ERA5 output must contain exactly "
                "one HRU.\n\n"
                f"Found: {ds.sizes['hru']}"
            )


        if "time" not in ds.sizes:

            raise RuntimeError(
                "Lumped ERA5 output has no time dimension."
            )


        if (
            expected_time_steps is not None
            and ds.sizes["time"] != expected_time_steps
        ):

            raise RuntimeError(
                "Lumped ERA5 time-step count differs "
                "from the prepared source forcing.\n\n"
                f"Expected: {expected_time_steps}\n"
                f"Found   : {ds.sizes['time']}"
            )


        if "hruId" not in ds.variables:

            raise RuntimeError(
                "hruId variable is missing from lumped "
                "ERA5 output."
            )


        output_hru_ids = (
            np.asarray(
                ds["hruId"].values
            )
            .astype(np.int64)
            .reshape(-1)
        )


        if output_hru_ids.size != 1:

            raise RuntimeError(
                "Lumped ERA5 output has unexpected "
                "hruId count.\n\n"
                f"Found: {output_hru_ids.tolist()}"
            )


        if int(output_hru_ids[0]) != 1:

            raise RuntimeError(
                "Lumped ERA5 hruId must equal 1.\n\n"
                f"Found: {output_hru_ids.tolist()}"
            )


        missing_variables = [
            variable
            for variable in ERA5_VARIABLES
            if variable not in ds.variables
        ]


        if missing_variables:

            raise RuntimeError(
                "Lumped ERA5 output is missing variable(s): "
                + ", ".join(
                    missing_variables
                )
            )


        missing_counts = {}
        value_ranges = {}


        for variable in ERA5_VARIABLES:

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
                missing_counts[variable]
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
                    ),
                )

            else:

                value_ranges[
                    variable
                ] = (
                    np.nan,
                    np.nan,
                )


        output_time_steps = (
            ds.sizes["time"]
        )


    return (
        output_time_steps,
        missing_counts,
        value_ranges,
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
        / f"ERA5_SUMMA_{ym}.nc"
    )


    if not forcing_file.exists():

        raise FileNotFoundError(
            "Prepared ERA5 forcing file not found:\n"
            f"{forcing_file}"
        )


    expected_output = (
        output_dir
        / (
            f"{case_name}_remapped_"
            f"{forcing_file.name}"
        )
    )


    print()
    print("-" * 78)
    print(f"LUMPED ERA5 REMAPPING: {ym}")
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


        print()
        print(
            "PASS: existing lumped ERA5 output "
            "passed validation."
        )

        print(
            f"Time steps: {output_time_steps}"
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
        "Copernicus ERA5 data"
    )


    # Variables

    esmr.var_names = (
        ERA5_VARIABLES
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


    # Source forcing grid

    esmr.source_shp = str(
        forcing_shape_file
    )

    esmr.source_shp_lat = (
        source_lat_field
    )

    esmr.source_shp_lon = (
        source_lon_field
    )


    # Lumped target

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


    # Prepared ERA5 forcing

    esmr.source_nc = str(
        forcing_file
    )


    # Directories

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


    # SUMMA-compatible output

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


    esmr.save_csv = (
        False
    )


    # Reuse lumped spatial mapping.

    esmr.remap_csv = str(
        remap_csv
    )


    esmr.sort_ID = (
        False
    )


    esmr.overwrite_existing_remap = (
        False
    )


    # --------------------------------------------------------
    # RUN EASYMORE
    # --------------------------------------------------------

    print()
    print("Running EASYMORE...")


    esmr.nc_remapper()


    # --------------------------------------------------------
    # FIND OUTPUT IF EASYMORE NAMING DIFFERS
    # --------------------------------------------------------

    if not expected_output.exists():

        alternatives = sorted(
            output_dir.glob(
                f"*{ym}*.nc"
            ),
            key=lambda path: path.stat().st_mtime
        )


        if len(alternatives) == 1:

            actual_output = alternatives[0]

        elif alternatives:

            actual_output = alternatives[-1]

        else:

            raise RuntimeError(
                "EASYMORE completed but no lumped ERA5 "
                "output was found.\n\n"
                f"Expected:\n{expected_output}"
            )

    else:

        actual_output = (
            expected_output
        )


    # --------------------------------------------------------
    # VALIDATE
    # --------------------------------------------------------

    (
        output_time_steps,
        missing_counts,
        value_ranges,
    ) = validate_output(
        actual_output,
        forcing_file,
    )


    # --------------------------------------------------------
    # REMOVE TEMP DIRECTORY
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
    # WORKFLOW LOG
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
            f"ERA5_lumped_remap_{ym}.txt"
        )
    )


    with log_file.open(
        "w"
    ) as file:

        file.write(
            "Lumped ERA5 monthly remapping completed "
            f"{timestamp:%Y-%m-%d %H:%M:%S}\n"
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
            f"Distributed prepared input: "
            f"{forcing_file}\n"
        )

        file.write(
            f"Lumped output: "
            f"{actual_output}\n"
        )

        file.write(
            f"Lumped catchment: "
            f"{catchment_file}\n"
        )

        file.write(
            "Target HRUs: 1\n"
        )

        file.write(
            "Target HRU ID: 1\n"
        )

        file.write(
            f"Remapping CSV: "
            f"{remap_csv}\n"
        )

        file.write(
            f"Time steps: "
            f"{output_time_steps}\n"
        )

        file.write(
            f"Missing values: "
            f"{missing_counts}\n"
        )

        file.write(
            f"Value ranges: "
            f"{value_ranges}\n"
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
    print("  hruId      : 1")
    print(
        f"  Time steps : "
        f"{output_time_steps}"
    )


    print()
    print("Missing values:")

    for variable in ERA5_VARIABLES:

        print(
            f"  {variable:<10}: "
            f"{missing_counts[variable]}"
        )


    print()
    print("Value ranges:")

    for variable in ERA5_VARIABLES:

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
        f"PASS: {domain} ERA5 {ym}"
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
print("LUMPED ERA5 MONTHLY REMAPPING COMPLETED")
print("=" * 78)

print(f"Domain         : {domain}")
print(f"Control file   : {CONTROL_FILE}")
print("Target HRUs    : 1")
print(f"Input forcing  : {input_dir}")
print(f"Output         : {output_dir}")
print(f"Remapping CSV  : {remap_csv}")

print()
print(
    "Distributed prepared ERA5 forcing was reused."
)

print(
    "Distributed remapped forcing was not modified."
)

print(
    "No control_active.txt was created or modified."
)