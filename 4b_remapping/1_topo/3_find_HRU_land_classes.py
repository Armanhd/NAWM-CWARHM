#!/usr/bin/env python
# coding: utf-8

# Compute categorical MODIS/IGBP land-class occurrence for every
# prepared CWARHM HRU.
#
# IMPORTANT
# ---------
# This script uses the PREPARED CWARHM catchment created in Stage 00:
#
#   <root_path>/domain_<domain_name>/shapefiles/catchment/
#
# It does NOT use the original MERIT source shapefile.
#
# Output fields:
#   IGBP_<class>

from pathlib import Path
from datetime import datetime
from shutil import copyfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds
from rasterstats import zonal_stats


# ============================================================
# PROJECT / CONTROL FILE
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM_ROOT = SCRIPT_DIR.parent.parent

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
    """Read one setting using exact control-key matching."""

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
    """Construct a standard domain path."""

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
# DOMAIN / PREPARED CATCHMENT
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)

catchment_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
)

hru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)

catchment_path = make_default_path(
    "shapefiles/catchment"
)

catchment_file = (
    catchment_path
    / catchment_name
)


# ============================================================
# LAND-COVER RASTER
# ============================================================

land_path = read_from_control(
    CONTROL_FILE,
    "parameter_land_mode_path"
)

land_name = read_from_control(
    CONTROL_FILE,
    "parameter_land_tif_name"
)

if land_path == "default":

    land_path = make_default_path(
        "parameters/landclass/"
        "7_mode_land_class"
    )

else:

    land_path = Path(
        land_path
    )

land_file = (
    land_path
    / land_name
)


# ============================================================
# OUTPUT PATH
# ============================================================

intersect_path = read_from_control(
    CONTROL_FILE,
    "intersect_land_path"
)

intersect_name = read_from_control(
    CONTROL_FILE,
    "intersect_land_name"
)

if intersect_path == "default":

    intersect_path = make_default_path(
        "shapefiles/catchment_intersection/"
        "with_modis"
    )

else:

    intersect_path = Path(
        intersect_path
    )

intersect_path.mkdir(
    parents=True,
    exist_ok=True
)

output_file = (
    intersect_path
    / intersect_name
)


# ============================================================
# VALIDATE INPUTS
# ============================================================

if not catchment_file.exists():
    raise FileNotFoundError(
        "Prepared CWARHM catchment not found:\n"
        f"{catchment_file}"
    )

if not land_file.exists():
    raise FileNotFoundError(
        f"Land-class raster not found:\n{land_file}"
    )


# ============================================================
# READ PREPARED CATCHMENT
# ============================================================

gdf = gpd.read_file(
    catchment_file
)

if len(gdf) == 0:
    raise RuntimeError(
        "Prepared catchment contains no features."
    )

if gdf.crs is None:
    raise RuntimeError(
        "Prepared catchment has no CRS."
    )

if hru_field not in gdf.columns:
    raise RuntimeError(
        f"Configured HRU field '{hru_field}' "
        "not found in prepared catchment."
    )

if gdf[hru_field].isna().any():
    raise RuntimeError(
        f"{hru_field} contains missing values."
    )

if gdf[hru_field].duplicated().any():
    raise RuntimeError(
        f"Duplicate HRU IDs found in {hru_field}."
    )

original_crs = gdf.crs


print()
print("=" * 70)
print("HRU LAND CLASSES")
print("=" * 70)
print(f"Domain    : {domain_name}")
print(f"Catchment : {catchment_file}")
print(f"CRS       : {original_crs}")
print(f"HRUs      : {len(gdf)}")
print(f"Land      : {land_file}")
print(f"Output    : {output_file}")


# ============================================================
# READ DOMAIN-SIZED LAND RASTER WINDOW
# ============================================================

with rasterio.open(
    land_file
) as src:

    if src.crs is None:
        raise RuntimeError(
            "Land-class raster has no CRS."
        )

    if src.nodata is not None:

        nodata = src.nodata

    else:

        nodata = 255

    print()
    print(f"Land CRS   : {src.crs}")
    print(f"Land nodata: {nodata}")

    if gdf.crs != src.crs:

        print(
            "Reprojecting catchments for land processing:"
        )
        print(f"  {gdf.crs}")
        print(f"  -> {src.crs}")

        gdf = gdf.to_crs(
            src.crs
        )

    minx, miny, maxx, maxy = (
        gdf.total_bounds
    )

    minx = max(minx, src.bounds.left)
    maxx = min(maxx, src.bounds.right)
    miny = max(miny, src.bounds.bottom)
    maxy = min(maxy, src.bounds.top)

    if (
        minx >= maxx
        or miny >= maxy
    ):
        raise RuntimeError(
            "Catchment and land-class raster do not overlap."
        )

    window = from_bounds(
        minx,
        miny,
        maxx,
        maxy,
        transform=src.transform
    )

    window = (
        window
        .round_offsets()
        .round_lengths()
    )

    array = src.read(
        1,
        window=window,
        masked=False
    )

    affine = src.window_transform(
        window
    )


print(
    f"Raster subset shape: {array.shape}"
)


# ============================================================
# VALID LAND CLASSES
# ============================================================

unique_values = np.unique(
    array
)

unique_values = unique_values[
    unique_values != nodata
]

if np.issubdtype(
    unique_values.dtype,
    np.floating
):

    unique_values = unique_values[
        np.isfinite(unique_values)
    ]

unique_values = (
    unique_values
    .astype(int)
)

if len(unique_values) == 0:
    raise RuntimeError(
        "No valid land-cover classes found within domain."
    )

print()
print(
    f"IGBP classes found: "
    f"{unique_values.tolist()}"
)


# ============================================================
# CATEGORICAL ZONAL STATISTICS
# ============================================================

stats = zonal_stats(
    gdf,
    array,
    affine=affine,
    nodata=nodata,
    categorical=True,
    all_touched=True
)


# ============================================================
# HISTOGRAM TABLE
# ============================================================

histogram = []

for stat in stats:

    row = {}

    for value in unique_values:

        row[
            f"IGBP_{int(value)}"
        ] = int(
            stat.get(
                int(value),
                0
            )
        )

    histogram.append(
        row
    )

df_stats = (
    pd.DataFrame(histogram)
    .fillna(0)
    .astype(int)
)

result = gdf.join(
    df_stats
)


# ============================================================
# VALIDATE RESULTS
# ============================================================

class_columns = [
    column
    for column in result.columns
    if column.startswith("IGBP_")
]

if not class_columns:
    raise RuntimeError(
        "No IGBP histogram columns generated."
    )

pixel_totals = (
    result[class_columns]
    .sum(axis=1)
)

missing_hrus = result.loc[
    pixel_totals == 0,
    hru_field
].tolist()

if missing_hrus:

    print()
    print(
        "WARNING: No valid land-cover pixels "
        "found for these HRUs:"
    )

    print(
        missing_hrus
    )


# ============================================================
# RETURN TO PREPARED CATCHMENT CRS
# ============================================================

if result.crs != original_crs:

    result = result.to_crs(
        original_crs
    )


# ============================================================
# PREPARE SHAPEFILE NUMERIC FIELDS
# ============================================================

for field in [
    "HRU_area",
    "area"
]:

    if field in result.columns:

        result[field] = (
            result[field]
            .astype(float)
            .round(2)
        )


# ============================================================
# SAVE
# ============================================================

result.to_file(
    output_file,
    driver="ESRI Shapefile",
    engine="fiona",
    index=False
)


# ============================================================
# VERIFY OUTPUT
# ============================================================

saved = gpd.read_file(
    output_file
)

if len(saved) != len(result):
    raise RuntimeError(
        "Saved land intersection has incorrect HRU count."
    )

if saved.crs is None:
    raise RuntimeError(
        "Saved land intersection has no CRS."
    )

if saved.crs != original_crs:
    raise RuntimeError(
        "Saved land intersection CRS changed unexpectedly."
    )

if hru_field not in saved.columns:
    raise RuntimeError(
        f"{hru_field} missing from saved output."
    )

saved_class_columns = [
    column
    for column in saved.columns
    if column.startswith("IGBP_")
]

if not saved_class_columns:
    raise RuntimeError(
        "Saved output contains no IGBP land-class fields."
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

this_file = Path(__file__).name

copyfile(
    Path(__file__).resolve(),
    log_folder / this_file
)

now = datetime.now()

log_file = (
    log_folder
    / (
        f"{now:%Y%m%d}_"
        "catchment_modis_intersect_log.txt"
    )
)

with open(
    log_file,
    "w"
) as f:

    f.write(
        f"Log generated by {this_file} "
        f"on {now:%Y/%m/%d %H:%M:%S}\n"
    )

    f.write(
        f"Domain: {domain_name}\n"
    )

    f.write(
        f"Prepared catchment: {catchment_file}\n"
    )

    f.write(
        f"HRUs processed: {len(saved)}\n"
    )

    f.write(
        f"IGBP classes: {unique_values.tolist()}\n"
    )

    f.write(
        f"Output CRS: {saved.crs}\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("LAND-CLASS PROCESSING COMPLETED")
print("=" * 70)
print(f"HRUs processed : {len(saved)}")
print(f"IGBP classes   : {unique_values.tolist()}")
print(f"Output CRS     : {saved.crs}")
print(f"Output         : {output_file}")