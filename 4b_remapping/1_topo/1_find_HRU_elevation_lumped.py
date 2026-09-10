#!/usr/bin/env python3
# coding: utf-8

"""
Calculate mean MERIT-Hydro elevation for a one-HRU lumped basin.

The distributed parameter raster is reused:

    domain_<DOMAIN>/parameters/dem/5_elevation/elevation.tif

The target catchment is:

    domain_<DOMAIN>/lumped/shapefiles/catchment/
        <DOMAIN>_lumped_basin.shp

The result is written to:

    domain_<DOMAIN>/lumped/shapefiles/
        catchment_intersection/with_dem/

Requirements
------------
The lumped catchment must contain exactly:

    1 HRU
    HRU_ID = 1
    GRU_ID = 1

Usage
-----
python 1_find_HRU_elevation_lumped.py \
    /path/to/control_DOMAIN_lumped.txt
"""

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterstats import zonal_stats


# ============================================================
# INPUT
# ============================================================

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage:\n"
        "python 1_find_HRU_elevation_lumped.py "
        "/path/to/control_DOMAIN_lumped.txt"
    )

CONTROL_FILE = Path(sys.argv[1]).resolve()

if not CONTROL_FILE.exists():
    raise FileNotFoundError(
        f"Control file not found:\n{CONTROL_FILE}"
    )


# ============================================================
# CONTROL READER
# ============================================================

def read_from_control(file, setting):

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

            value = (
                right
                .split("#", 1)[0]
                .strip()
            )

            if not value:
                raise ValueError(
                    f"Setting '{setting}' is empty in:\n{file}"
                )

            return value

    raise ValueError(
        f"Setting '{setting}' not found in:\n{file}"
    )


# ============================================================
# DOMAIN
# ============================================================

domain = read_from_control(
    CONTROL_FILE,
    "domain_name"
)

root_path = Path(
    read_from_control(
        CONTROL_FILE,
        "root_path"
    )
)

domain_root = (
    root_path
    / f"domain_{domain}"
)

lumped_root = (
    domain_root
    / "lumped"
)


# ============================================================
# LUMPED CATCHMENT
# ============================================================

catchment_file = (
    lumped_root
    / "shapefiles/catchment"
    / f"{domain}_lumped_basin.shp"
)

if not catchment_file.exists():
    raise FileNotFoundError(
        "Lumped catchment shapefile not found:\n"
        f"{catchment_file}"
    )


gdf = gpd.read_file(
    catchment_file,
    engine="fiona"
)


# ============================================================
# VALIDATE ONE-HRU STRUCTURE
# ============================================================

required_fields = [
    "HRU_ID",
    "GRU_ID",
]

for field in required_fields:

    if field not in gdf.columns:
        raise RuntimeError(
            f"{field} missing from lumped catchment."
        )


if len(gdf) != 1:
    raise RuntimeError(
        "Lumped catchment must contain exactly one feature.\n"
        f"Found: {len(gdf)}"
    )


if int(gdf.iloc[0]["HRU_ID"]) != 1:
    raise RuntimeError(
        "Lumped catchment HRU_ID must equal 1."
    )


if int(gdf.iloc[0]["GRU_ID"]) != 1:
    raise RuntimeError(
        "Lumped catchment GRU_ID must equal 1."
    )


if gdf.crs is None:
    raise RuntimeError(
        "Lumped catchment has no CRS."
    )


if (
    gdf.geometry.iloc[0].is_empty
    or not gdf.geometry.iloc[0].is_valid
):
    raise RuntimeError(
        "Lumped catchment geometry is empty or invalid."
    )


original_crs = gdf.crs


# ============================================================
# REUSE EXISTING DISTRIBUTED DEM
# ============================================================

dem_name = read_from_control(
    CONTROL_FILE,
    "parameter_dem_tif_name"
)

dem_path = (
    domain_root
    / "parameters/dem/5_elevation"
)

dem_file = (
    dem_path
    / dem_name
)

if not dem_file.exists():

    raise FileNotFoundError(
        "Existing distributed MERIT-Hydro elevation raster "
        "not found:\n"
        f"{dem_file}"
    )


# ============================================================
# OUTPUT
# ============================================================

output_dir = (
    lumped_root
    / "shapefiles/catchment_intersection/with_dem"
)

output_dir.mkdir(
    parents=True,
    exist_ok=True
)


try:
    output_name = read_from_control(
        CONTROL_FILE,
        "intersect_dem_name"
    )
except ValueError:
    output_name = "catchment_with_merit_dem.shp"


output_file = (
    output_dir
    / output_name
)


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("LUMPED HRU ELEVATION")
print("=" * 70)

print(f"Domain       : {domain}")
print(f"Control      : {CONTROL_FILE}")
print(f"Catchment    : {catchment_file}")
print(f"HRUs         : {len(gdf)}")
print(f"HRU_ID       : {int(gdf.iloc[0]['HRU_ID'])}")
print(f"GRU_ID       : {int(gdf.iloc[0]['GRU_ID'])}")
print(f"DEM          : {dem_file}")
print(f"Output       : {output_file}")


# ============================================================
# READ DEM WINDOW
# ============================================================

with rasterio.open(dem_file) as src:

    if src.crs is None:
        raise RuntimeError(
            "DEM has no CRS."
        )

    processing = gdf.to_crs(
        src.crs
    )

    minx, miny, maxx, maxy = (
        processing.total_bounds
    )

    overlap_minx = max(
        minx,
        src.bounds.left
    )

    overlap_maxx = min(
        maxx,
        src.bounds.right
    )

    overlap_miny = max(
        miny,
        src.bounds.bottom
    )

    overlap_maxy = min(
        maxy,
        src.bounds.top
    )


    if (
        overlap_minx >= overlap_maxx
        or overlap_miny >= overlap_maxy
    ):
        raise RuntimeError(
            "Lumped catchment and DEM do not overlap."
        )


    window = from_bounds(
        overlap_minx,
        overlap_miny,
        overlap_maxx,
        overlap_maxy,
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


# ============================================================
# ZONAL MEAN
# ============================================================

stats = zonal_stats(
    processing.geometry,
    array,
    affine=affine,
    nodata=nodata,
    stats=["mean"],
    all_touched=True
)


value = stats[0].get("mean")


if value is None or not np.isfinite(
    float(value)
):
    raise RuntimeError(
        "No valid elevation was found for the lumped basin."
    )


gdf["elev_mean"] = [
    float(value)
]


# ============================================================
# REMOVE OLD SHAPEFILE
# ============================================================

for extension in [
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".sbn",
    ".sbx",
    ".qix",
]:

    old = (
        output_dir
        / f"{output_file.stem}{extension}"
    )

    if old.exists():
        old.unlink()


# ============================================================
# WRITE
# ============================================================

gdf.to_file(
    output_file,
    driver="ESRI Shapefile",
    engine="fiona",
    index=False
)


# ============================================================
# VERIFY
# ============================================================

saved = gpd.read_file(
    output_file,
    engine="fiona"
)


if len(saved) != 1:
    raise RuntimeError(
        "Saved elevation shapefile does not contain one HRU."
    )


if int(saved.iloc[0]["HRU_ID"]) != 1:
    raise RuntimeError(
        "Saved elevation HRU_ID is not 1."
    )


if int(saved.iloc[0]["GRU_ID"]) != 1:
    raise RuntimeError(
        "Saved elevation GRU_ID is not 1."
    )


if "elev_mean" not in saved.columns:
    raise RuntimeError(
        "elev_mean missing from saved output."
    )


if not np.isfinite(
    float(saved.iloc[0]["elev_mean"])
):
    raise RuntimeError(
        "Saved elevation is invalid."
    )


# ============================================================
# LOG
# ============================================================

log_dir = (
    output_dir
    / "_workflow_log"
)

log_dir.mkdir(
    parents=True,
    exist_ok=True
)


copy2(
    Path(__file__).resolve(),
    log_dir / Path(__file__).name
)

copy2(
    CONTROL_FILE,
    log_dir / CONTROL_FILE.name
)


now = datetime.now()

log_file = (
    log_dir
    / f"{now:%Y%m%d_%H%M%S}_lumped_elevation.txt"
)


with open(log_file, "w") as file:

    file.write(
        f"Domain: {domain}\n"
    )

    file.write(
        "HRUs: 1\n"
    )

    file.write(
        "HRU_ID: 1\n"
    )

    file.write(
        "GRU_ID: 1\n"
    )

    file.write(
        f"Elevation: {float(saved.iloc[0]['elev_mean'])}\n"
    )

    file.write(
        f"Input DEM: {dem_file}\n"
    )

    file.write(
        f"Output: {output_file}\n"
    )


print()
print("=" * 70)
print("LUMPED HRU ELEVATION COMPLETED")
print("=" * 70)

print(f"Domain     : {domain}")
print("HRUs       : 1")
print("HRU_ID     : 1")
print("GRU_ID     : 1")
print(
    f"Elevation  : "
    f"{float(saved.iloc[0]['elev_mean']):.3f} m"
)
print(f"Output     : {output_file}")
print()
print(f"PASS: {domain} lumped elevation")