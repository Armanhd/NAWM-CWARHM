#!/usr/bin/env python
# coding: utf-8

# Compute mean MERIT-Hydro elevation for every prepared CWARHM HRU.
#
# IMPORTANT
# ---------
# This script uses the PREPARED CWARHM catchment created in Stage 00:
#
#   <root_path>/domain_<domain_name>/shapefiles/catchment/
#
# It does NOT use the original MERIT source shapefile.
#
# Improvements:
#   - robust control-file location
#   - exact control-setting matching
#   - always uses prepared CWARHM catchment
#   - validates input files and HRU field
#   - reprojects HRUs to DEM CRS only for raster processing
#   - reads only the DEM window covering the domain
#   - restores the original prepared-catchment CRS before output
#   - validates elevation results
#
# Output:
#   catchment_with_merit_dem.shp
#
# Added field:
#   elev_mean

from pathlib import Path
from datetime import datetime
from shutil import copyfile

import geopandas as gpd
import numpy as np
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
# DEM
# ============================================================

dem_path = read_from_control(
    CONTROL_FILE,
    "parameter_dem_tif_path"
)

dem_name = read_from_control(
    CONTROL_FILE,
    "parameter_dem_tif_name"
)

if dem_path == "default":

    dem_path = make_default_path(
        "parameters/dem/5_elevation"
    )

else:

    dem_path = Path(
        dem_path
    )

dem_file = (
    dem_path
    / dem_name
)


# ============================================================
# OUTPUT PATH
# ============================================================

intersect_path = read_from_control(
    CONTROL_FILE,
    "intersect_dem_path"
)

intersect_name = read_from_control(
    CONTROL_FILE,
    "intersect_dem_name"
)

if intersect_path == "default":

    intersect_path = make_default_path(
        "shapefiles/catchment_intersection/with_dem"
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

if not dem_file.exists():
    raise FileNotFoundError(
        f"DEM raster not found:\n{dem_file}"
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
        "is missing from prepared catchment."
    )

if gdf[hru_field].duplicated().any():
    raise RuntimeError(
        f"Duplicate HRU IDs found in {hru_field}."
    )

original_crs = gdf.crs


print()
print("=" * 70)
print("HRU ELEVATION")
print("=" * 70)
print(f"Domain    : {domain_name}")
print(f"Catchment : {catchment_file}")
print(f"CRS       : {original_crs}")
print(f"HRUs      : {len(gdf)}")
print(f"DEM       : {dem_file}")
print(f"Output    : {output_file}")


# ============================================================
# OPEN DEM AND READ DOMAIN WINDOW
# ============================================================

with rasterio.open(
    dem_file
) as src:

    if src.crs is None:
        raise RuntimeError(
            "DEM has no CRS."
        )

    print()
    print(f"DEM CRS   : {src.crs}")
    print(f"DEM nodata: {src.nodata}")

    if gdf.crs != src.crs:

        print(
            "Reprojecting catchments for DEM processing:"
        )
        print(f"  {gdf.crs}")
        print(f"  -> {src.crs}")

        gdf = gdf.to_crs(
            src.crs
        )

    minx, miny, maxx, maxy = (
        gdf.total_bounds
    )

    # Restrict bounds to actual raster coverage.
    minx = max(minx, src.bounds.left)
    maxx = min(maxx, src.bounds.right)
    miny = max(miny, src.bounds.bottom)
    maxy = min(maxy, src.bounds.top)

    if (
        minx >= maxx
        or miny >= maxy
    ):
        raise RuntimeError(
            "Catchment and DEM do not overlap."
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

    nodata = src.nodata


print(
    f"DEM subset shape: {array.shape}"
)


# ============================================================
# ZONAL MEAN
# ============================================================

stats = zonal_stats(
    gdf,
    array,
    affine=affine,
    nodata=nodata,
    stats=["mean"],
    all_touched=True
)

elev_mean = [
    item.get("mean")
    for item in stats
]


# ============================================================
# VALIDATE RESULTS
# ============================================================

missing = [
    i
    for i, value in enumerate(elev_mean)
    if value is None
    or not np.isfinite(value)
]

if missing:
    raise RuntimeError(
        f"No valid DEM elevation found for "
        f"{len(missing)} HRU(s). "
        f"Feature indices: {missing}"
    )

gdf["elev_mean"] = np.asarray(
    elev_mean,
    dtype="float64"
)


print()
print(
    f"Elevation range [m]: "
    f"{gdf['elev_mean'].min():.3f} - "
    f"{gdf['elev_mean'].max():.3f}"
)


# ============================================================
# RETURN TO PREPARED CATCHMENT CRS
# ============================================================

if gdf.crs != original_crs:

    gdf = gdf.to_crs(
        original_crs
    )


# ============================================================
# PREPARE SHAPEFILE NUMERIC FIELDS
# ============================================================

for field in [
    "HRU_area",
    "area"
]:

    if field in gdf.columns:

        gdf[field] = (
            gdf[field]
            .astype(float)
            .round(2)
        )


# ============================================================
# SAVE
# ============================================================

gdf.to_file(
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

if len(saved) != len(gdf):
    raise RuntimeError(
        "Saved elevation shapefile has incorrect HRU count."
    )

if saved.crs is None:
    raise RuntimeError(
        "Saved elevation shapefile has no CRS."
    )

if saved.crs != original_crs:
    raise RuntimeError(
        "Saved elevation shapefile CRS changed unexpectedly."
    )

if hru_field not in saved.columns:
    raise RuntimeError(
        f"{hru_field} missing from saved output."
    )

if "elev_mean" not in saved.columns:
    raise RuntimeError(
        "elev_mean missing from saved output."
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
        "catchment_dem_intersect_log.txt"
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
        f"Output CRS: {saved.crs}\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("ELEVATION PROCESSING COMPLETED")
print("=" * 70)
print(f"HRUs processed : {len(saved)}")
print(f"Output CRS     : {saved.crs}")
print(f"Output         : {output_file}")