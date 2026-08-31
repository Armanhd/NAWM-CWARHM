#!/usr/bin/env python3
# coding: utf-8

"""
Compute mean MERIT-Hydro elevation for every prepared CWARHM HRU.

The script uses the PREPARED CWARHM catchment:

    <root_path>/domain_<domain_name>/shapefiles/catchment/

It does not modify the original MERIT source shapefile.

Multibasin behavior
-------------------
A domain-specific control file must be supplied explicitly.

The script does NOT read or modify control_active.txt.

Usage
-----

python 1_find_HRU_elevation.py \
/path/to/control_DOMAIN.txt

Output
------
The output shapefile is defined by:

    intersect_dem_path
    intersect_dem_name

and contains:

    elev_mean

representing mean MERIT-Hydro elevation for each HRU.
"""

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds
from rasterstats import zonal_stats


# ============================================================
# INPUT CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_find_HRU_elevation.py "
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
    Construct a standard path inside domain_<domain_name>.
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

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# PREPARED CATCHMENT
# ============================================================

catchment_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
)

hru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)

gru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_gruid"
)


# Always use Stage-00 prepared CWARHM copy.
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
# OUTPUT
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
# VALIDATE INPUT FILES
# ============================================================

if not catchment_file.exists():

    raise FileNotFoundError(
        "Prepared CWARHM catchment not found:\n"
        f"{catchment_file}\n\n"
        "Run Stage 00 and Stage 4a first."
    )


if not dem_file.exists():

    raise FileNotFoundError(
        f"MERIT-Hydro DEM not found:\n"
        f"{dem_file}"
    )


# ============================================================
# READ PREPARED CATCHMENT
# ============================================================

gdf = gpd.read_file(
    catchment_file,
    engine="fiona"
)


if len(gdf) == 0:

    raise RuntimeError(
        "Prepared catchment contains no features."
    )


if gdf.crs is None:

    raise RuntimeError(
        "Prepared catchment has no CRS."
    )


required_fields = [
    hru_field,
    gru_field,
]


missing_fields = [
    field
    for field in required_fields
    if field not in gdf.columns
]


if missing_fields:

    raise RuntimeError(
        "Required catchment fields missing:\n"
        + "\n".join(
            f"  {field}"
            for field in missing_fields
        )
    )


# ============================================================
# VALIDATE HRU / GRU IDS
# ============================================================

for field in required_fields:

    gdf[field] = pd.to_numeric(
        gdf[field],
        errors="raise"
    )

    if gdf[field].isna().any():

        raise RuntimeError(
            f"{field} contains missing values."
        )

    values = gdf[field].to_numpy(
        dtype=np.float64
    )

    if not np.all(
        np.isfinite(values)
    ):

        raise RuntimeError(
            f"{field} contains non-finite values."
        )


gdf[hru_field] = (
    gdf[hru_field]
    .astype(np.int64)
)

gdf[gru_field] = (
    gdf[gru_field]
    .astype(np.int64)
)


if gdf[hru_field].duplicated().any():

    duplicates = (
        gdf.loc[
            gdf[hru_field].duplicated(
                keep=False
            ),
            hru_field
        ]
        .astype(int)
        .tolist()
    )

    raise RuntimeError(
        f"Duplicate HRU IDs found:\n"
        f"{duplicates}"
    )


# Preserve authoritative Stage-4a ordering.
input_hru_ids = (
    gdf[hru_field]
    .to_numpy(
        dtype=np.int64
    )
    .copy()
)

input_gru_ids = (
    gdf[gru_field]
    .to_numpy(
        dtype=np.int64
    )
    .copy()
)


original_crs = gdf.crs
num_hru = len(gdf)


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("CALCULATE HRU MEAN ELEVATION")
print("=" * 70)

print()
print(f"Domain       : {domain_name}")
print(f"Control file : {CONTROL_FILE}")
print(f"Catchment    : {catchment_file}")
print(f"Catchment CRS: {original_crs}")
print(f"HRUs         : {num_hru}")
print(f"DEM          : {dem_file}")
print(f"Output       : {output_file}")

print()
print(
    f"First HRU ID : "
    f"{input_hru_ids[0]}"
)

print(
    f"Last HRU ID  : "
    f"{input_hru_ids[-1]}"
)


# ============================================================
# OPEN DEM
# ============================================================

with rasterio.open(
    dem_file
) as src:

    if src.crs is None:

        raise RuntimeError(
            "MERIT-Hydro DEM has no CRS."
        )

    if src.count < 1:

        raise RuntimeError(
            "MERIT-Hydro DEM contains no raster bands."
        )


    print()
    print(f"DEM CRS      : {src.crs}")
    print(f"DEM nodata   : {src.nodata}")
    print(
        f"DEM size     : "
        f"{src.width} x {src.height}"
    )


    # --------------------------------------------------------
    # REPROJECT HRUS FOR DEM PROCESSING
    # --------------------------------------------------------

    processing_gdf = gdf.copy()


    if processing_gdf.crs != src.crs:

        print()
        print(
            "Reprojecting HRUs temporarily for DEM processing:"
        )

        print(
            f"  {processing_gdf.crs}"
        )

        print(
            f"  -> {src.crs}"
        )

        processing_gdf = (
            processing_gdf
            .to_crs(
                src.crs
            )
        )


    # --------------------------------------------------------
    # CHECK GEOMETRIES
    # --------------------------------------------------------

    if processing_gdf.geometry.isna().any():

        raise RuntimeError(
            "Catchment contains missing geometries."
        )


    if processing_gdf.geometry.is_empty.any():

        raise RuntimeError(
            "Catchment contains empty geometries."
        )


    # --------------------------------------------------------
    # GET DOMAIN WINDOW
    # --------------------------------------------------------

    minx, miny, maxx, maxy = (
        processing_gdf.total_bounds
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
            "Catchment and MERIT-Hydro DEM do not overlap.\n\n"
            f"Catchment bounds: "
            f"{processing_gdf.total_bounds}\n"
            f"DEM bounds      : "
            f"{src.bounds}"
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


    if array.size == 0:

        raise RuntimeError(
            "DEM subset is empty."
        )


    affine = src.window_transform(
        window
    )


    nodata = src.nodata


print()
print(
    f"DEM subset shape: "
    f"{array.shape}"
)


# ============================================================
# ZONAL MEAN
# ============================================================

print()
print(
    "Calculating mean elevation for each HRU..."
)


stats = zonal_stats(
    processing_gdf.geometry,
    array,
    affine=affine,
    nodata=nodata,
    stats=[
        "mean"
    ],
    all_touched=True
)


if len(stats) != num_hru:

    raise RuntimeError(
        "Unexpected number of zonal-statistic results.\n"
        f"Expected: {num_hru}\n"
        f"Found   : {len(stats)}"
    )


elev_mean = np.asarray(
    [
        item.get(
            "mean"
        )
        for item in stats
    ],
    dtype=object
)


# ============================================================
# VALIDATE ELEVATION RESULTS
# ============================================================

invalid_positions = []


for index, value in enumerate(
    elev_mean
):

    if value is None:

        invalid_positions.append(
            index
        )

        continue


    try:

        value_float = float(
            value
        )

    except Exception:

        invalid_positions.append(
            index
        )

        continue


    if not np.isfinite(
        value_float
    ):

        invalid_positions.append(
            index
        )


if invalid_positions:

    invalid_hrus = [
        int(
            input_hru_ids[
                index
            ]
        )
        for index
        in invalid_positions
    ]

    raise RuntimeError(
        "No valid MERIT-Hydro elevation found for "
        f"{len(invalid_hrus)} HRU(s).\n"
        f"HRU IDs: {invalid_hrus}"
    )


elev_mean = elev_mean.astype(
    np.float64
)


gdf[
    "elev_mean"
] = elev_mean


if not np.all(
    np.isfinite(
        gdf["elev_mean"]
        .to_numpy(
            dtype=np.float64
        )
    )
):

    raise RuntimeError(
        "Non-finite elev_mean values remain."
    )


print()
print(
    f"Elevation range [m]: "
    f"{gdf['elev_mean'].min():.3f} - "
    f"{gdf['elev_mean'].max():.3f}"
)

print(
    f"Mean elevation [m] : "
    f"{gdf['elev_mean'].mean():.3f}"
)


# ============================================================
# PREPARE NUMERIC SHAPEFILE FIELDS
# ============================================================

for field in [
    "HRU_area",
    "area"
]:

    if field in gdf.columns:

        gdf[field] = (
            pd.to_numeric(
                gdf[field],
                errors="raise"
            )
            .astype(float)
            .round(2)
        )


# ============================================================
# VERIFY ORDER BEFORE WRITING
# ============================================================

if not np.array_equal(
    gdf[hru_field]
    .to_numpy(
        dtype=np.int64
    ),
    input_hru_ids
):

    raise RuntimeError(
        "HRU ordering changed during elevation processing."
    )


if not np.array_equal(
    gdf[gru_field]
    .to_numpy(
        dtype=np.int64
    ),
    input_gru_ids
):

    raise RuntimeError(
        "GRU ordering changed during elevation processing."
    )


# ============================================================
# REMOVE PREVIOUS OUTPUT
# ============================================================

shapefile_extensions = [
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".sbn",
    ".sbx",
    ".qix",
]


for extension in shapefile_extensions:

    old_file = (
        intersect_path
        / (
            output_file.stem
            + extension
        )
    )

    if old_file.exists():

        old_file.unlink()


# ============================================================
# WRITE OUTPUT
# ============================================================

gdf.to_file(
    output_file,
    driver="ESRI Shapefile",
    engine="fiona",
    index=False
)


# ============================================================
# VERIFY SAVED OUTPUT
# ============================================================

saved = gpd.read_file(
    output_file,
    engine="fiona"
)


if len(saved) != num_hru:

    raise RuntimeError(
        "Saved elevation shapefile has incorrect HRU count.\n"
        f"Expected: {num_hru}\n"
        f"Found   : {len(saved)}"
    )


if saved.crs is None:

    raise RuntimeError(
        "Saved elevation shapefile has no CRS."
    )


if saved.crs != original_crs:

    raise RuntimeError(
        "Saved elevation shapefile CRS changed unexpectedly.\n"
        f"Expected: {original_crs}\n"
        f"Found   : {saved.crs}"
    )


for field in [
    hru_field,
    gru_field,
    "elev_mean"
]:

    if field not in saved.columns:

        raise RuntimeError(
            f"{field} missing from saved elevation output."
        )


saved_hru_ids = (
    saved[hru_field]
    .astype(np.int64)
    .to_numpy()
)


saved_gru_ids = (
    saved[gru_field]
    .astype(np.int64)
    .to_numpy()
)


if not np.array_equal(
    saved_hru_ids,
    input_hru_ids
):

    raise RuntimeError(
        "Saved elevation shapefile HRU order changed."
    )


if not np.array_equal(
    saved_gru_ids,
    input_gru_ids
):

    raise RuntimeError(
        "Saved elevation shapefile GRU order changed."
    )


saved_elevation = (
    saved[
        "elev_mean"
    ]
    .astype(float)
    .to_numpy()
)


if not np.all(
    np.isfinite(
        saved_elevation
    )
):

    raise RuntimeError(
        "Saved elev_mean contains non-finite values."
    )


# ============================================================
# WORKFLOW LOG
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
        "catchment_dem_intersection.txt"
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
        f"Domain: {domain_name}\n"
    )

    file.write(
        f"Control file: {CONTROL_FILE}\n"
    )

    file.write(
        f"Prepared catchment: {catchment_file}\n"
    )

    file.write(
        f"DEM: {dem_file}\n"
    )

    file.write(
        f"HRUs processed: {num_hru}\n"
    )

    file.write(
        f"Elevation minimum: "
        f"{saved_elevation.min():.6f} m\n"
    )

    file.write(
        f"Elevation maximum: "
        f"{saved_elevation.max():.6f} m\n"
    )

    file.write(
        f"Output CRS: {saved.crs}\n"
    )

    file.write(
        f"Output: {output_file}\n"
    )

    file.write(
        "HRU ordering preserved: yes\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("HRU ELEVATION PROCESSING COMPLETED")
print("=" * 70)

print(
    f"Domain          : {domain_name}"
)

print(
    f"HRUs processed  : {len(saved)}"
)

print(
    f"Elevation range : "
    f"{saved_elevation.min():.3f} - "
    f"{saved_elevation.max():.3f} m"
)

print(
    f"Output CRS      : {saved.crs}"
)

print(
    f"HRU order       : preserved"
)

print(
    f"Output          : {output_file}"
)

print(
    f"Workflow log    : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)