#!/usr/bin/env python3
# coding: utf-8

"""
Create reusable ERA5 -> SUMMA HRU EASYMORE remapping information.

Purpose
-------
Use one prepared ERA5 monthly forcing file to:

1. intersect the ERA5 forcing grid with the prepared CWARHM HRUs;
2. generate reusable EASYMORE remapping information;
3. create one test basin-averaged ERA5 forcing file.

NWAM uses ERA5 for:

    airpres
    LWRadAtm
    SWRadAtm
    spechum
    windspd

Multibasin behavior
-------------------
A domain-specific control file must be supplied explicitly.

The script does NOT read or modify control_active.txt.

Target shapefile
----------------
The EASYMORE target shapefile is always the prepared CWARHM
catchment:

    <root_path>/domain_<domain_name>/shapefiles/catchment/

It is NOT the original read-only MERIT source shapefile.

Source forcing
--------------
Prepared ERA5 forcing is expected at:

    forcing/1_raw_data/ERA5_prepared/

with filenames:

    ERA5_SUMMA_YYYYMM.nc

Source forcing grid
-------------------
The ERA5 grid shapefile is defined by:

    forcing_shape_path
    forcing_era5_shape_name

Output
------
Reusable remapping products are stored in:

    shapefiles/catchment_intersection/with_forcing/ERA5/

The one-month test remapped forcing is stored in:

    forcing/3_basin_averaged_data/ERA5/

Usage
-----
python 1a_remap_ERA5.py \
/path/to/control_DOMAIN.txt
"""

import sys
from pathlib import Path
from shutil import rmtree, copy2
from datetime import datetime

import geopandas as gpd
import numpy as np
import xarray as xr
import easymore


# ============================================================
# INPUT CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1a_remap_ERA5.py "
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
    Construct a standard domain path.
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


# ============================================================
# TARGET HRU SHAPEFILE
# ============================================================

catchment_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
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


catchment_path = make_default_path(
    "shapefiles/catchment"
)


catchment_file = (
    catchment_path
    / catchment_name
)


if not catchment_file.exists():

    raise FileNotFoundError(
        "Prepared CWARHM catchment shapefile "
        "was not found:\n"
        f"{catchment_file}\n\n"
        "Run Stage 00 before forcing remapping."
    )


# ============================================================
# VALIDATE TARGET HRUS
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
        "Prepared target catchment has no CRS."
    )


target_epsg = (
    target_gdf.crs.to_epsg()
)


if target_epsg != 4326:

    raise RuntimeError(
        "Prepared target catchment has unexpected CRS.\n\n"
        "Expected: EPSG:4326\n"
        f"Found   : {target_gdf.crs}"
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
        "Prepared target catchment is missing field(s): "
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
        f"{target_id_field} contains duplicate IDs."
    )


target_hru_ids = (
    target_gdf[
        target_id_field
    ]
    .astype(np.int64)
    .to_numpy()
)


if not np.all(
    np.isfinite(
        target_gdf[
            target_lat_field
        ].astype(float)
    )
):

    raise RuntimeError(
        f"{target_lat_field} contains "
        "non-finite values."
    )


if not np.all(
    np.isfinite(
        target_gdf[
            target_lon_field
        ].astype(float)
    )
):

    raise RuntimeError(
        f"{target_lon_field} contains "
        "non-finite values."
    )


# ============================================================
# ERA5 GRID SHAPEFILE
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
    "forcing_era5_shape_name"
)


forcing_shape_file = (
    forcing_shape_path
    / forcing_shape_name
)


if not forcing_shape_file.exists():

    raise FileNotFoundError(
        "ERA5 forcing-grid shapefile "
        "not found:\n"
        f"{forcing_shape_file}\n\n"
        "Run 2_create_forcing_grids.py first."
    )


# ============================================================
# VALIDATE SOURCE GRID
# ============================================================

source_grid_gdf = gpd.read_file(
    forcing_shape_file,
    engine="fiona"
)


if len(source_grid_gdf) == 0:

    raise RuntimeError(
        "ERA5 grid shapefile contains no features."
    )


if source_grid_gdf.crs is None:

    raise RuntimeError(
        "ERA5 forcing-grid shapefile has no CRS."
    )


if source_grid_gdf.crs.to_epsg() != 4326:

    raise RuntimeError(
        "ERA5 forcing grid has unexpected CRS.\n\n"
        "Expected: EPSG:4326\n"
        f"Found   : {source_grid_gdf.crs}"
    )


source_lat_field = read_from_control(
    CONTROL_FILE,
    "forcing_shape_lat_name"
)

source_lon_field = read_from_control(
    CONTROL_FILE,
    "forcing_shape_lon_name"
)


required_source_fields = [
    source_lat_field,
    source_lon_field,
]


missing_source_fields = [
    field
    for field in required_source_fields
    if field not in source_grid_gdf.columns
]


if missing_source_fields:

    raise RuntimeError(
        "ERA5 forcing grid is missing field(s): "
        + ", ".join(
            missing_source_fields
        )
    )


# ============================================================
# PREPARED ERA5 FORCING FILES
# ============================================================

forcing_path = make_default_path(
    "forcing/1_raw_data/ERA5_prepared"
)


if not forcing_path.exists():

    raise FileNotFoundError(
        "Prepared ERA5 directory not found:\n"
        f"{forcing_path}"
    )


forcing_files = sorted(
    forcing_path.glob(
        "ERA5_SUMMA_*.nc"
    )
)


if not forcing_files:

    raise FileNotFoundError(
        "No prepared ERA5 files found in:\n"
        f"{forcing_path}\n\n"
        "Run 3_prepare_era5_forcing.py first."
    )


# Earliest available month is sufficient to generate
# the reusable spatial remapping information.
forcing_file = forcing_files[0]


# ============================================================
# VALIDATE TEMPLATE NETCDF
# ============================================================

required_variables = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "spechum",
    "windspd",
]


with xr.open_dataset(
    forcing_file
) as ds:

    missing_variables = [
        variable
        for variable in required_variables
        if variable not in ds.variables
    ]


    if missing_variables:

        raise RuntimeError(
            "Template ERA5 forcing is missing "
            "required variable(s): "
            + ", ".join(
                missing_variables
            )
        )


    required_coordinates = [
        "time",
        "latitude",
        "longitude",
    ]


    missing_coordinates = [
        coordinate
        for coordinate in required_coordinates
        if coordinate not in ds.variables
        and coordinate not in ds.coords
    ]


    if missing_coordinates:

        raise RuntimeError(
            "Template ERA5 forcing is missing "
            "coordinate(s): "
            + ", ".join(
                missing_coordinates
            )
        )


    source_time_steps = (
        ds.sizes.get(
            "time",
            0
        )
    )


    source_lat_count = (
        ds.sizes.get(
            "latitude",
            0
        )
    )


    source_lon_count = (
        ds.sizes.get(
            "longitude",
            0
        )
    )


    if (
        source_time_steps == 0
        or source_lat_count == 0
        or source_lon_count == 0
    ):

        raise RuntimeError(
            "Template ERA5 forcing contains "
            "an empty required dimension."
        )


# ============================================================
# INTERSECTION / REMAPPING OUTPUT
# ============================================================

intersect_path = make_default_path(
    "shapefiles/"
    "catchment_intersection/"
    "with_forcing/"
    "ERA5"
)


intersect_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# TEMPORARY EASYMORE DIRECTORY
# ============================================================

forcing_easymore_path = make_default_path(
    "forcing/"
    "3_temp_easymore/"
    "ERA5"
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
# BASIN-AVERAGED OUTPUT DIRECTORY
# ============================================================

forcing_basin_path = make_default_path(
    "forcing/"
    "3_basin_averaged_data/"
    "ERA5"
)


forcing_basin_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# REPORT INPUTS
# ============================================================

print()
print("=" * 70)
print("CREATE ERA5 -> HRU EASYMORE REMAPPING")
print("=" * 70)

print()
print(f"Domain       : {domain}")
print(f"Control file : {CONTROL_FILE}")

print()
print(f"Target HRUs  : {catchment_file}")
print(f"HRU count    : {len(target_gdf)}")
print(f"First HRU ID : {target_hru_ids[0]}")
print(f"Last HRU ID  : {target_hru_ids[-1]}")
print(f"Target CRS   : {target_gdf.crs}")

print()
print(f"Source grid  : {forcing_shape_file}")
print(f"Grid cells   : {len(source_grid_gdf)}")
print(f"Source CRS   : {source_grid_gdf.crs}")

print()
print(f"Template NC  : {forcing_file}")
print(f"Time steps   : {source_time_steps}")
print(f"Latitude     : {source_lat_count}")
print(f"Longitude    : {source_lon_count}")

print()
print(
    "Variables    : "
    + ", ".join(
        required_variables
    )
)

print()
print(f"Temp folder  : {forcing_easymore_path}")
print(f"Output folder: {forcing_basin_path}")
print(f"Remap folder : {intersect_path}")


# ============================================================
# EASYMORE SETUP
# ============================================================

esmr = easymore.Easymore()


esmr.author_name = (
    "NWAM-SUMMA workflow"
)


esmr.license = (
    "Copernicus ERA5 data"
)


esmr.case_name = (
    f"{domain}_ERA5"
)


# ------------------------------------------------------------
# SOURCE GRID SHAPEFILE
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
# TARGET HRU SHAPEFILE
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
# SOURCE NETCDF
# ------------------------------------------------------------

esmr.source_nc = str(
    forcing_file
)


esmr.var_names = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "spechum",
    "windspd",
]


esmr.var_lat = (
    "latitude"
)

esmr.var_lon = (
    "longitude"
)

esmr.var_time = (
    "time"
)


# ------------------------------------------------------------
# EASYMORE DIRECTORIES
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
# SUMMA-COMPATIBLE OUTPUT
# ------------------------------------------------------------

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
esmr.remap_csv = ""

# Preserve prepared catchment HRU ordering.
esmr.sort_ID = False


# ============================================================
# RUN EASYMORE
# ============================================================

print()
print("-" * 70)
print("RUN EASYMORE")
print("-" * 70)
print()


esmr.nc_remapper()


# ============================================================
# FIND EASYMORE REMAPPING PRODUCTS
# ============================================================

temp_dir = Path(
    esmr.temp_dir
)


if not temp_dir.exists():

    raise RuntimeError(
        "EASYMORE temporary directory disappeared "
        "before remapping products could be collected:\n"
        f"{temp_dir}"
    )


# EASYMORE versions can use slightly different names.
# Preserve all matching remapping products.

remap_nc_files = sorted(
    temp_dir.glob(
        f"{esmr.case_name}*remap*.nc"
    )
)


remap_csv_files = sorted(
    temp_dir.glob(
        f"{esmr.case_name}*remap*.csv"
    )
)


intersect_files = sorted(
    temp_dir.glob(
        f"{esmr.case_name}_intersected_shapefile.*"
    )
)


# ============================================================
# REQUIRE REUSABLE REMAPPING INFORMATION
# ============================================================

if (
    not remap_nc_files
    and not remap_csv_files
):

    print()
    print("Temporary EASYMORE files:")

    for path in sorted(
        temp_dir.iterdir()
    ):

        print(
            f"  {path.name}"
        )


    raise RuntimeError(
        "EASYMORE completed but no reusable "
        "remapping NetCDF or CSV was found."
    )


# ============================================================
# COPY REMAPPING PRODUCTS
# ============================================================

print()
print("-" * 70)
print("SAVE REMAPPING PRODUCTS")
print("-" * 70)


saved_remap_files = []


for source in (
    remap_nc_files
    + remap_csv_files
):

    destination = (
        intersect_path
        / source.name
    )


    copy2(
        source,
        destination
    )


    saved_remap_files.append(
        destination
    )


    print(
        f"Saved: {destination}"
    )


# ============================================================
# COPY INTERSECTION SHAPEFILE
# ============================================================

saved_intersection_files = []


for source in intersect_files:

    destination = (
        intersect_path
        / source.name
    )


    copy2(
        source,
        destination
    )


    saved_intersection_files.append(
        destination
    )


if saved_intersection_files:

    print()
    print(
        "Saved intersected shapefile components:"
    )

    for path in saved_intersection_files:

        print(
            f"  {path.name}"
        )


# ============================================================
# FIND ONE-MONTH REMAPPED OUTPUT
# ============================================================

remapped_nc_files = sorted(
    forcing_basin_path.glob(
        "*.nc"
    ),
    key=lambda path: path.stat().st_mtime
)


if not remapped_nc_files:

    raise RuntimeError(
        "EASYMORE did not create a basin-averaged "
        "ERA5 NetCDF file in:\n"
        f"{forcing_basin_path}"
    )


test_output = (
    remapped_nc_files[-1]
)


# ============================================================
# VERIFY REMAPPED NETCDF
# ============================================================

with xr.open_dataset(
    test_output
) as ds:

    missing_variables = [
        variable
        for variable in required_variables
        if variable not in ds.variables
    ]


    if missing_variables:

        raise RuntimeError(
            "Remapped ERA5 output is missing "
            "required variable(s): "
            + ", ".join(
                missing_variables
            )
        )


    if "hruId" not in ds.variables:

        raise RuntimeError(
            "Remapped ERA5 output does not "
            "contain hruId."
        )


    saved_hru_ids = (
        np.asarray(
            ds[
                "hruId"
            ].values
        )
        .squeeze()
        .astype(
            np.int64
        )
    )


    if saved_hru_ids.size != len(
        target_hru_ids
    ):

        raise RuntimeError(
            "Remapped ERA5 HRU count does "
            "not match prepared catchment.\n"
            f"Expected: {len(target_hru_ids)}\n"
            f"Found   : {saved_hru_ids.size}"
        )


    if not np.array_equal(
        saved_hru_ids,
        target_hru_ids
    ):

        raise RuntimeError(
            "Remapped ERA5 hruId ordering "
            "does not match the prepared catchment."
        )


    output_time_steps = (
        ds.sizes.get(
            "time",
            0
        )
    )


    output_hru_count = (
        saved_hru_ids.size
    )


    missing_counts = {}

    for variable in required_variables:

        missing_counts[
            variable
        ] = int(
            ds[
                variable
            ]
            .isnull()
            .sum()
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


copy2(
    Path(__file__).resolve(),
    log_folder / this_file
)


copy2(
    CONTROL_FILE,
    log_folder / CONTROL_FILE.name
)


now = datetime.now()


log_file = (
    log_folder
    / (
        f"{now:%Y%m%d_%H%M%S}_"
        "ERA5_remapping.txt"
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
        f"Domain: {domain}\n"
    )

    file.write(
        f"Control file: {CONTROL_FILE}\n"
    )

    file.write(
        f"Target catchment: {catchment_file}\n"
    )

    file.write(
        f"Target HRUs: {len(target_hru_ids)}\n"
    )

    file.write(
        f"Source grid: {forcing_shape_file}\n"
    )

    file.write(
        f"Source grid cells: "
        f"{len(source_grid_gdf)}\n"
    )

    file.write(
        f"Template forcing: {forcing_file}\n"
    )

    file.write(
        "Variables: airpres, LWRadAtm, SWRadAtm, "
        "spechum, windspd\n"
    )

    file.write(
        f"Test output: {test_output}\n"
    )

    file.write(
        f"Output HRUs: {output_hru_count}\n"
    )

    file.write(
        f"Output time steps: {output_time_steps}\n"
    )

    file.write(
        "HRU ordering preserved: yes\n"
    )

    for variable in required_variables:

        file.write(
            f"Missing {variable}: "
            f"{missing_counts[variable]}\n"
        )

    file.write(
        f"Reusable remapping products: "
        f"{len(saved_remap_files)}\n"
    )

    for path in saved_remap_files:

        file.write(
            f"Remapping file: {path}\n"
        )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# REMOVE TEMPORARY DIRECTORY
# ============================================================

try:

    rmtree(
        forcing_easymore_path
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
# FINISH
# ============================================================

print()
print("=" * 70)
print("ERA5 EASYMORE REMAPPING COMPLETED")
print("=" * 70)

print(
    f"Domain             : {domain}"
)

print(
    f"Target HRUs        : {len(target_hru_ids)}"
)

print(
    f"Source grid cells  : {len(source_grid_gdf)}"
)

print(
    "Variables          : "
    "airpres, LWRadAtm, SWRadAtm, "
    "spechum, windspd"
)

print(
    f"Template month     : {forcing_file.name}"
)

print(
    f"Test output        : {test_output}"
)

print(
    f"Output HRUs        : {output_hru_count}"
)

print(
    f"Output time steps  : {output_time_steps}"
)

print(
    "HRU order          : preserved"
)

print()
print("Missing values:")

for variable in required_variables:

    print(
        f"  {variable:<10}: "
        f"{missing_counts[variable]}"
    )

print()
print(
    f"Remapping products : {len(saved_remap_files)}"
)

print(
    f"Remap folder       : {intersect_path}"
)

print(
    f"Workflow log       : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)