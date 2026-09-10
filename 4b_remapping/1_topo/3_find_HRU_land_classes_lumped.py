#!/usr/bin/env python3
# coding: utf-8

"""
Calculate MODIS/IGBP land-class occurrence for a one-HRU lumped basin.

Reuses:

    domain_<DOMAIN>/parameters/landclass/
        7_mode_land_class/land_classes.tif

Target:

    domain_<DOMAIN>/lumped/shapefiles/catchment/
        <DOMAIN>_lumped_basin.shp

Output:

    domain_<DOMAIN>/lumped/shapefiles/
        catchment_intersection/with_modis/
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
        "python 3_find_HRU_land_classes_lumped.py "
        "/path/to/control_DOMAIN_lumped.txt"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).resolve()


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
        "Lumped catchment not found:\n"
        f"{catchment_file}"
    )


gdf = gpd.read_file(
    catchment_file,
    engine="fiona"
)


if len(gdf) != 1:
    raise RuntimeError(
        "Lumped catchment must contain exactly one HRU."
    )


for field in [
    "HRU_ID",
    "GRU_ID",
]:

    if field not in gdf.columns:
        raise RuntimeError(
            f"{field} missing from lumped catchment."
        )


if int(gdf.iloc[0]["HRU_ID"]) != 1:
    raise RuntimeError(
        "HRU_ID must equal 1."
    )


if int(gdf.iloc[0]["GRU_ID"]) != 1:
    raise RuntimeError(
        "GRU_ID must equal 1."
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
        "Lumped geometry is empty or invalid."
    )


# ============================================================
# REUSE EXISTING DISTRIBUTED MODIS LAND-CLASS RASTER
# ============================================================

land_name = read_from_control(
    CONTROL_FILE,
    "parameter_land_tif_name"
)

land_path = (
    domain_root
    / "parameters/landclass/7_mode_land_class"
)

land_file = (
    land_path
    / land_name
)

if not land_file.exists():

    raise FileNotFoundError(
        "Existing distributed MODIS land-class raster "
        "not found:\n"
        f"{land_file}"
    )


# ============================================================
# OUTPUT
# ============================================================

output_dir = (
    lumped_root
    / "shapefiles/catchment_intersection/with_modis"
)

output_dir.mkdir(
    parents=True,
    exist_ok=True
)


try:
    output_name = read_from_control(
        CONTROL_FILE,
        "intersect_land_name"
    )
except ValueError:
    output_name = "catchment_with_modis.shp"


output_file = (
    output_dir
    / output_name
)


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("LUMPED HRU LAND CLASSES")
print("=" * 70)

print(f"Domain      : {domain}")
print(f"Control     : {CONTROL_FILE}")
print(f"Catchment   : {catchment_file}")
print("HRUs        : 1")
print("HRU_ID      : 1")
print("GRU_ID      : 1")
print(f"Land raster : {land_file}")
print(f"Output      : {output_file}")


# ============================================================
# READ RASTER
# ============================================================

with rasterio.open(
    land_file
) as src:

    if src.crs is None:
        raise RuntimeError(
            "Land-class raster has no CRS."
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
            "Lumped catchment and land raster do not overlap."
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

    source_nodata = src.nodata


# ============================================================
# LAND CLASSES
# ============================================================

rasterstats_nodata = (
    source_nodata
    if source_nodata is not None
    else 255
)


unique_values = np.unique(
    array
)


if source_nodata is not None:

    unique_values = unique_values[
        unique_values != source_nodata
    ]

else:

    unique_values = unique_values[
        unique_values != rasterstats_nodata
    ]


if np.issubdtype(
    unique_values.dtype,
    np.floating
):

    unique_values = unique_values[
        np.isfinite(unique_values)
    ]


if len(unique_values) == 0:
    raise RuntimeError(
        "No valid land-cover classes found."
    )


if not np.allclose(
    unique_values,
    np.round(unique_values)
):
    raise RuntimeError(
        "Land-cover values are not integer categorical values."
    )


unique_values = (
    np.round(unique_values)
    .astype(np.int64)
)

unique_values = np.sort(
    np.unique(unique_values)
)


# ============================================================
# ZONAL STATISTICS
# ============================================================

stats = zonal_stats(
    processing.geometry,
    array,
    affine=affine,
    nodata=rasterstats_nodata,
    categorical=True,
    all_touched=True
)


if len(stats) != 1:
    raise RuntimeError(
        "Expected one MODIS zonal-statistics result."
    )


stat = stats[0]


class_fields = []


for value in unique_values:

    field = (
        f"IGBP_{int(value)}"
    )


    if len(field) > 10:
        raise RuntimeError(
            f"Shapefile field exceeds 10 characters: {field}"
        )


    gdf[field] = [
        int(
            stat.get(
                int(value),
                0
            )
        )
    ]

    class_fields.append(
        field
    )


total_pixels = int(
    gdf[
        class_fields
    ]
    .sum(axis=1)
    .iloc[0]
)


if total_pixels <= 0:
    raise RuntimeError(
        "No valid MODIS pixels were assigned "
        "to the lumped HRU."
    )


# ============================================================
# REMOVE PREVIOUS OUTPUT
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
# WRITE + VERIFY
# ============================================================

gdf.to_file(
    output_file,
    driver="ESRI Shapefile",
    engine="fiona",
    index=False
)


saved = gpd.read_file(
    output_file,
    engine="fiona"
)


if len(saved) != 1:
    raise RuntimeError(
        "Saved MODIS output does not contain one HRU."
    )


if int(saved.iloc[0]["HRU_ID"]) != 1:
    raise RuntimeError(
        "Saved MODIS HRU_ID is not 1."
    )


if int(saved.iloc[0]["GRU_ID"]) != 1:
    raise RuntimeError(
        "Saved MODIS GRU_ID is not 1."
    )


saved_fields = [
    field
    for field in saved.columns
    if field.startswith("IGBP_")
]


if not saved_fields:
    raise RuntimeError(
        "No IGBP fields found in saved output."
    )


saved_total = int(
    saved[
        saved_fields
    ]
    .sum(axis=1)
    .iloc[0]
)


if saved_total <= 0:
    raise RuntimeError(
        "Saved MODIS histogram contains no pixels."
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
    / f"{now:%Y%m%d_%H%M%S}_lumped_land.txt"
)


with open(
    log_file,
    "w"
) as file:

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
        f"Land raster: {land_file}\n"
    )

    file.write(
        f"IGBP classes: {unique_values.tolist()}\n"
    )

    file.write(
        f"Total pixels: {saved_total}\n"
    )

    file.write(
        f"Output: {output_file}\n"
    )


print()
print("=" * 70)
print("LUMPED HRU LAND-CLASS PROCESSING COMPLETED")
print("=" * 70)

print(f"Domain       : {domain}")
print("HRUs         : 1")
print("HRU_ID       : 1")
print("GRU_ID       : 1")
print(
    f"IGBP classes : "
    f"{unique_values.tolist()}"
)
print(
    f"Pixels       : {saved_total}"
)
print(f"Output       : {output_file}")
print()
print(f"PASS: {domain} lumped land classes")