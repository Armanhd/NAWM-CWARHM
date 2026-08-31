#!/usr/bin/env python3
# coding: utf-8

"""
Compute categorical soil-class occurrence for every prepared CWARHM HRU.

The script uses the PREPARED CWARHM catchment created in Stage 00:

    <root_path>/domain_<domain_name>/shapefiles/catchment/

It does NOT use the original MERIT source shapefile.

Multibasin behavior
-------------------
A domain-specific control file must be supplied explicitly.

The script does NOT read or modify control_active.txt.

Soil raster
-----------
The soil raster is defined by:

    parameter_soil_domain_path
    parameter_soil_tif_name

This supports both:

    - a shared ARC soil-class raster, or
    - a domain-specific raster

depending on the control file.

Output
------
The output shapefile contains categorical soil-pixel counts:

    USGS_<class>

for every soil class encountered over the domain.

Soil class 0 is retained. The later SUMMA attributes step decides
how soil class values are interpreted.

Usage
-----
python 2_find_HRU_soil_classes.py \
/path/to/control_DOMAIN.txt
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
        "python 2_find_HRU_soil_classes.py "
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


# Always use prepared CWARHM catchment.
catchment_path = make_default_path(
    "shapefiles/catchment"
)

catchment_file = (
    catchment_path
    / catchment_name
)


# ============================================================
# SOIL RASTER
# ============================================================

soil_path = read_from_control(
    CONTROL_FILE,
    "parameter_soil_domain_path"
)

soil_name = read_from_control(
    CONTROL_FILE,
    "parameter_soil_tif_name"
)


if soil_path == "default":

    soil_path = make_default_path(
        "parameters/soilclass/"
        "2_soil_classes_domain"
    )

else:

    soil_path = Path(
        soil_path
    )


soil_file = (
    soil_path
    / soil_name
)


# ============================================================
# OUTPUT
# ============================================================

intersect_path = read_from_control(
    CONTROL_FILE,
    "intersect_soil_path"
)

intersect_name = read_from_control(
    CONTROL_FILE,
    "intersect_soil_name"
)


if intersect_path == "default":

    intersect_path = make_default_path(
        "shapefiles/"
        "catchment_intersection/"
        "with_soilgrids"
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


if not soil_file.exists():

    raise FileNotFoundError(
        "Configured soil-class raster not found:\n"
        f"{soil_file}\n\n"
        "Check parameter_soil_domain_path and "
        "parameter_soil_tif_name."
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
        "Required catchment field(s) missing:\n"
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

    values = gdf[
        field
    ].to_numpy(
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

    duplicate_hrus = (
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
        f"{duplicate_hrus}"
    )


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
print("CALCULATE HRU SOIL CLASSES")
print("=" * 70)

print()
print(f"Domain       : {domain_name}")
print(f"Control file : {CONTROL_FILE}")
print(f"Catchment    : {catchment_file}")
print(f"Catchment CRS: {original_crs}")
print(f"HRUs         : {num_hru}")
print(f"Soil raster  : {soil_file}")
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
# OPEN SOIL RASTER
# ============================================================

with rasterio.open(
    soil_file
) as src:

    if src.crs is None:

        raise RuntimeError(
            "Soil raster has no CRS."
        )


    if src.count < 1:

        raise RuntimeError(
            "Soil raster contains no raster bands."
        )


    print()
    print(
        f"Soil CRS      : "
        f"{src.crs}"
    )

    print(
        f"Soil nodata   : "
        f"{src.nodata}"
    )

    print(
        f"Soil size     : "
        f"{src.width} x {src.height}"
    )

    print(
        f"Soil bounds   : "
        f"{src.bounds}"
    )


    # --------------------------------------------------------
    # TEMPORARY REPROJECTION
    # --------------------------------------------------------

    processing_gdf = (
        gdf.copy()
    )


    if processing_gdf.crs != src.crs:

        print()
        print(
            "Reprojecting HRUs temporarily for soil processing:"
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
    # GEOMETRY CHECKS
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
    # DOMAIN BOUNDS
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
            "Catchment and soil raster do not overlap.\n\n"
            f"Catchment bounds: "
            f"{processing_gdf.total_bounds}\n"
            f"Soil bounds     : "
            f"{src.bounds}"
        )


    # --------------------------------------------------------
    # READ ONLY DOMAIN WINDOW
    # --------------------------------------------------------

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
            "Soil raster subset is empty."
        )


    affine = src.window_transform(
        window
    )


    source_nodata = (
        src.nodata
    )


# ============================================================
# NODATA HANDLING
# ============================================================

if source_nodata is None:

    # This value is used only internally by rasterstats.
    #
    # It is safely outside normal categorical soil classes.
    rasterstats_nodata = -9999

    print()
    print(
        "Soil raster has no defined NoData value."
    )

    print(
        "Using -9999 as an internal "
        "rasterstats NoData sentinel."
    )

else:

    rasterstats_nodata = (
        source_nodata
    )


print()
print(
    f"Raster subset shape: "
    f"{array.shape}"
)


# ============================================================
# VALID SOIL CLASSES IN DOMAIN WINDOW
# ============================================================

unique_values = np.unique(
    array
)


if source_nodata is not None:

    unique_values = unique_values[
        unique_values
        != source_nodata
    ]


if np.issubdtype(
    unique_values.dtype,
    np.floating
):

    unique_values = unique_values[
        np.isfinite(
            unique_values
        )
    ]


if len(
    unique_values
) == 0:

    raise RuntimeError(
        "No valid soil classes found "
        "within the catchment raster window."
    )


# Soil classes should be categorical integers.

if not np.allclose(
    unique_values,
    np.round(
        unique_values
    )
):

    raise RuntimeError(
        "Soil raster contains non-integer "
        "categorical values."
    )


unique_values = (
    np.round(
        unique_values
    )
    .astype(
        np.int64
    )
)


unique_values = np.sort(
    np.unique(
        unique_values
    )
)


print()
print(
    "Soil classes found in domain window:"
)

print(
    unique_values.tolist()
)


# ============================================================
# CATEGORICAL ZONAL STATISTICS
# ============================================================

print()
print(
    "Calculating categorical soil-class "
    "pixel counts for each HRU..."
)


stats = zonal_stats(
    processing_gdf.geometry,
    array,
    affine=affine,
    nodata=rasterstats_nodata,
    categorical=True,
    all_touched=True
)


if len(stats) != num_hru:

    raise RuntimeError(
        "Unexpected number of zonal-statistic results.\n"
        f"Expected: {num_hru}\n"
        f"Found   : {len(stats)}"
    )


# ============================================================
# HISTOGRAM TABLE
# ============================================================

histogram = []


for stat in stats:

    row = {}

    for value in unique_values:

        field_name = (
            f"USGS_{int(value)}"
        )


        # ESRI Shapefile DBF names are limited to 10 chars.
        if len(field_name) > 10:

            raise RuntimeError(
                "Generated soil-class field name exceeds "
                "the ESRI Shapefile 10-character limit:\n"
                f"{field_name}"
            )


        row[
            field_name
        ] = int(
            stat.get(
                int(value),
                0
            )
        )


    histogram.append(
        row
    )


hist_df = (
    pd.DataFrame(
        histogram
    )
    .fillna(0)
    .astype(
        np.int64
    )
)


if len(hist_df) != num_hru:

    raise RuntimeError(
        "Soil histogram table has incorrect HRU count."
    )


# Avoid index-alignment surprises.
hist_df.index = (
    gdf.index
)


result = (
    gdf.copy()
)


for column in hist_df.columns:

    result[
        column
    ] = hist_df[
        column
    ].to_numpy()


# ============================================================
# VALIDATE RESULT FIELDS
# ============================================================

class_columns = [
    column
    for column in result.columns
    if column.startswith(
        "USGS_"
    )
]


if not class_columns:

    raise RuntimeError(
        "No soil-class histogram columns were generated."
    )


pixel_totals = (
    result[
        class_columns
    ]
    .sum(
        axis=1
    )
)


missing_mask = (
    pixel_totals == 0
)


missing_hrus = (
    result.loc[
        missing_mask,
        hru_field
    ]
    .astype(int)
    .tolist()
)


if missing_hrus:

    print()
    print(
        "WARNING: No valid soil pixels were found "
        "for the following HRUs:"
    )

    print(
        missing_hrus
    )


valid_hru_count = int(
    np.count_nonzero(
        ~missing_mask
    )
)


missing_hru_count = int(
    np.count_nonzero(
        missing_mask
    )
)


# ============================================================
# VERIFY HRU / GRU ORDER
# ============================================================

if not np.array_equal(
    result[
        hru_field
    ]
    .to_numpy(
        dtype=np.int64
    ),
    input_hru_ids
):

    raise RuntimeError(
        "HRU ordering changed during soil processing."
    )


if not np.array_equal(
    result[
        gru_field
    ]
    .to_numpy(
        dtype=np.int64
    ),
    input_gru_ids
):

    raise RuntimeError(
        "GRU ordering changed during soil processing."
    )


# ============================================================
# PREPARE NUMERIC SHAPEFILE FIELDS
# ============================================================

for field in [
    "HRU_area",
    "area"
]:

    if field in result.columns:

        result[field] = (
            pd.to_numeric(
                result[field],
                errors="raise"
            )
            .astype(float)
            .round(2)
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

result.to_file(
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
        "Saved soil intersection has incorrect HRU count.\n"
        f"Expected: {num_hru}\n"
        f"Found   : {len(saved)}"
    )


if saved.crs is None:

    raise RuntimeError(
        "Saved soil intersection has no CRS."
    )


if saved.crs != original_crs:

    raise RuntimeError(
        "Saved soil intersection CRS changed unexpectedly.\n"
        f"Expected: {original_crs}\n"
        f"Found   : {saved.crs}"
    )


for field in [
    hru_field,
    gru_field
]:

    if field not in saved.columns:

        raise RuntimeError(
            f"{field} missing from saved soil output."
        )


saved_class_columns = [
    column
    for column in saved.columns
    if column.startswith(
        "USGS_"
    )
]


if set(
    saved_class_columns
) != set(
    class_columns
):

    raise RuntimeError(
        "Saved soil-class columns differ "
        "from generated columns."
    )


saved_hru_ids = (
    saved[
        hru_field
    ]
    .astype(
        np.int64
    )
    .to_numpy()
)


saved_gru_ids = (
    saved[
        gru_field
    ]
    .astype(
        np.int64
    )
    .to_numpy()
)


if not np.array_equal(
    saved_hru_ids,
    input_hru_ids
):

    raise RuntimeError(
        "Saved soil shapefile HRU order changed."
    )


if not np.array_equal(
    saved_gru_ids,
    input_gru_ids
):

    raise RuntimeError(
        "Saved soil shapefile GRU order changed."
    )


for column in saved_class_columns:

    values = (
        saved[
            column
        ]
        .to_numpy(
            dtype=np.float64
        )
    )

    if not np.all(
        np.isfinite(
            values
        )
    ):

        raise RuntimeError(
            f"{column} contains non-finite values."
        )


    if np.any(
        values < 0
    ):

        raise RuntimeError(
            f"{column} contains negative pixel counts."
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
        "catchment_soilclass_intersection.txt"
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
        f"Soil raster: {soil_file}\n"
    )

    file.write(
        f"HRUs processed: {num_hru}\n"
    )

    file.write(
        f"HRUs with valid soil pixels: "
        f"{valid_hru_count}\n"
    )

    file.write(
        f"HRUs without valid soil pixels: "
        f"{missing_hru_count}\n"
    )

    file.write(
        f"Soil classes: "
        f"{unique_values.tolist()}\n"
    )

    file.write(
        f"Soil class fields: "
        f"{class_columns}\n"
    )

    file.write(
        f"Rasterstats nodata value: "
        f"{rasterstats_nodata}\n"
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
print("HRU SOIL-CLASS PROCESSING COMPLETED")
print("=" * 70)

print(
    f"Domain           : "
    f"{domain_name}"
)

print(
    f"HRUs processed   : "
    f"{len(saved)}"
)

print(
    f"Valid HRUs       : "
    f"{valid_hru_count}"
)

print(
    f"Missing HRUs     : "
    f"{missing_hru_count}"
)

print(
    f"Soil classes     : "
    f"{unique_values.tolist()}"
)

print(
    f"Soil class fields: "
    f"{saved_class_columns}"
)

print(
    f"Output CRS       : "
    f"{saved.crs}"
)

print(
    f"HRU order        : preserved"
)

print(
    f"Output           : "
    f"{output_file}"
)

print(
    f"Workflow log     : "
    f"{log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)