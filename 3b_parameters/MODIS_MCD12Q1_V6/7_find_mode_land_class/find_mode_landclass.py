#!/usr/bin/env python
# coding: utf-8

"""
Create the representative MODIS land-class raster for one CWARHM domain.

Usage
-----
python find_mode_landclass.py \
/path/to/control_DOMAIN.txt

Purpose
-------
Reads the multiband MODIS MCD12Q1 GeoTIFF created by the preceding
workflow step and determines the representative land-cover class
for every raster cell.

For the current NWAM setup only the 2022 MCD12Q1 layer is used,
so the input contains one band and the output is therefore identical
to that band.

If multiple annual MODIS bands are used in the future, the script
calculates the modal class across valid annual observations while
ignoring nodata values.

The script is fully domain-specific and does not use the shared
control_active.txt file.
"""

from pathlib import Path
from datetime import datetime
from shutil import copy2
import sys

import numpy as np
from osgeo import gdal


# ============================================================
# INPUT CONTROL FILE
# ============================================================

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage:\n"
        "python find_mode_landclass.py "
        "/path/to/control_DOMAIN.txt"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).expanduser().resolve()


if not CONTROL_FILE.exists():
    raise FileNotFoundError(
        f"Control file not found:\n{CONTROL_FILE}"
    )


# ============================================================
# CONTROL-FILE FUNCTIONS
# ============================================================

def read_from_control(file, setting):
    """
    Read one exact setting from the supplied CWARHM control file.
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
                    f"Setting is empty in control file: "
                    f"{setting}"
                )

            return value

    raise ValueError(
        f"Setting not found in control file: "
        f"{setting}"
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


def resolve_path(setting, default_suffix):
    """
    Resolve a control-file path setting.
    """

    value = read_from_control(
        CONTROL_FILE,
        setting
    )

    if value == "default":
        return make_default_path(
            default_suffix
        )

    return Path(
        value
    ).expanduser().resolve()


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# SOURCE MULTIBAND LAND-CLASS RASTER
# ============================================================

land_class_path = resolve_path(
    "parameter_land_tif_path",
    "parameters/landclass/6_tif_multiband"
)


if not land_class_path.exists():
    raise FileNotFoundError(
        "MODIS multiband TIFF directory not found:\n"
        f"{land_class_path}"
    )


if not land_class_path.is_dir():
    raise NotADirectoryError(
        f"Expected a directory:\n"
        f"{land_class_path}"
    )


# ============================================================
# DESTINATION MODE LAND-CLASS DIRECTORY
# ============================================================

mode_land_class_path = resolve_path(
    "parameter_land_mode_path",
    "parameters/landclass/7_mode_land_class"
)


mode_land_class_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# OUTPUT FILENAME
# ============================================================

dest_file_name = read_from_control(
    CONTROL_FILE,
    "parameter_land_tif_name"
)


dest_file = (
    mode_land_class_path
    / dest_file_name
)


# ============================================================
# FIND SOURCE TIFF
# ============================================================

source_files = sorted(
    land_class_path.glob(
        "*.tif"
    )
)


if len(source_files) == 0:
    raise RuntimeError(
        "No MODIS multiband TIFF found in:\n"
        f"{land_class_path}"
    )


if len(source_files) > 1:
    raise RuntimeError(
        "Expected exactly one MODIS multiband TIFF, "
        f"but found {len(source_files)}:\n"
        + "\n".join(
            f"  {file}"
            for file in source_files
        )
    )


source_file = source_files[0]


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("CREATE REPRESENTATIVE MODIS LAND-CLASS RASTER")
print("=" * 70)
print()
print(f"Domain       : {domain_name}")
print(f"Control file : {CONTROL_FILE}")
print(f"Source TIFF  : {source_file}")
print(f"Output TIFF  : {dest_file}")


# ============================================================
# OPEN SOURCE RASTER
# ============================================================

src_ds = gdal.Open(
    str(source_file),
    gdal.GA_ReadOnly
)


if src_ds is None:
    raise RuntimeError(
        "Could not open MODIS land-class raster:\n"
        f"{source_file}"
    )


num_bands = src_ds.RasterCount
ncols = src_ds.RasterXSize
nrows = src_ds.RasterYSize


if num_bands <= 0:
    src_ds = None

    raise RuntimeError(
        "MODIS land-class raster contains no bands."
    )


geo_transform = src_ds.GetGeoTransform()
projection = src_ds.GetProjection()


if not projection:
    src_ds = None

    raise RuntimeError(
        "Source MODIS raster has no projection."
    )


print()
print("Raster information")
print("-" * 70)
print(f"Columns      : {ncols}")
print(f"Rows         : {nrows}")
print(f"Bands        : {num_bands}")


# ============================================================
# DETERMINE NODATA
# ============================================================

nodata_values = []


for band_number in range(
    1,
    num_bands + 1
):

    band = src_ds.GetRasterBand(
        band_number
    )

    if band is None:
        src_ds = None

        raise RuntimeError(
            f"Could not access source band "
            f"{band_number}."
        )

    nodata_values.append(
        band.GetNoDataValue()
    )


defined_nodata = [
    value
    for value in nodata_values
    if value is not None
]


if defined_nodata:

    first_nodata = defined_nodata[0]

    for value in defined_nodata:

        if value != first_nodata:
            src_ds = None

            raise RuntimeError(
                "Source MODIS bands use inconsistent "
                "nodata values."
            )

    nodata = first_nodata

else:

    # MODIS MCD12Q1 standard fill value.
    nodata = 255

if nodata < 0 or nodata > 255:
    src_ds = None
    raise RuntimeError(
        f"MODIS nodata value {nodata} cannot be represented as uint8."
    )

nodata = int(nodata)
print(f"NoData value : {nodata}")


# ============================================================
# READ SOURCE BANDS
# ============================================================

land_class_stack = np.empty(
    (
        num_bands,
        nrows,
        ncols
    ),
    dtype=np.uint8
)


for band_number in range(
    1,
    num_bands + 1
):

    print(
        f"Reading band "
        f"{band_number}/{num_bands}"
    )

    band = src_ds.GetRasterBand(
        band_number
    )

    data = band.ReadAsArray()

    if data is None:
        src_ds = None

        raise RuntimeError(
            f"Could not read values from "
            f"band {band_number}."
        )

    if data.shape != (
        nrows,
        ncols
    ):
        src_ds = None

        raise RuntimeError(
            f"Unexpected shape for band "
            f"{band_number}: {data.shape}"
        )

    land_class_stack[
        band_number - 1,
        :,
        :
    ] = data.astype(
        np.uint8
    )


# ============================================================
# CALCULATE REPRESENTATIVE LAND CLASS
# ============================================================

if num_bands == 1:

    mode = (
        land_class_stack[0]
        .copy()
    )

    print()
    print(
        "Only one MODIS year is available; "
        "the source band is used directly."
    )

else:

    print()
    print(
        f"Calculating modal land class across "
        f"{num_bands} MODIS bands."
    )

    # MODIS IGBP classes are small integer values.
    # Use a deterministic categorical count rather than
    # scipy.stats.mode so that nodata can be excluded explicitly.
    #
    # Valid MODIS values are safely represented in uint8.

    mode = np.full(
        (
            nrows,
            ncols
        ),
        nodata,
        dtype=np.uint8
    )

    valid_mask = (
        land_class_stack
        != nodata
    )

    any_valid = valid_mask.any(
        axis=0
    )

    valid_classes = np.unique(
        land_class_stack[
            valid_mask
        ]
    )


    if valid_classes.size == 0:
        src_ds = None

        raise RuntimeError(
            "No valid MODIS land-cover values "
            "were found."
        )


    # Sort explicitly so an exact tie is resolved
    # consistently toward the lowest class number.
    valid_classes = np.sort(
        valid_classes
    )


    best_count = np.zeros(
        (
            nrows,
            ncols
        ),
        dtype=np.uint16
    )


    for land_class in valid_classes:

        counts = np.sum(
            land_class_stack
            == land_class,
            axis=0
        )

        replace = (
            counts > best_count
        )

        mode[
            replace
        ] = land_class

        best_count[
            replace
        ] = counts[
            replace
        ]


    mode[
        ~any_valid
    ] = np.uint8(
        nodata
    )


# ============================================================
# BASIC QA
# ============================================================

valid_output = mode[
    mode != nodata
]


if valid_output.size == 0:
    src_ds = None

    raise RuntimeError(
        "Output raster contains no valid land classes."
    )


unique_classes = np.unique(
    valid_output
)


nodata_count = int(
    np.count_nonzero(
        mode == nodata
    )
)


print()
print("Output land classes")
print("-" * 70)
print(
    f"Classes      : "
    f"{unique_classes.tolist()}"
)
print(
    f"NoData cells : "
    f"{nodata_count}"
)


# ============================================================
# REMOVE EXISTING OUTPUT
# ============================================================

if dest_file.exists():
    dest_file.unlink()


# ============================================================
# CREATE OUTPUT GEOTIFF
# ============================================================

driver = gdal.GetDriverByName(
    "GTiff"
)


if driver is None:
    src_ds = None

    raise RuntimeError(
        "GDAL GTiff driver is unavailable."
    )


dst_ds = driver.Create(
    str(dest_file),
    ncols,
    nrows,
    1,
    gdal.GDT_Byte,
    options=[
        "COMPRESS=DEFLATE",
        "TILED=YES",
        "BIGTIFF=IF_SAFER",
    ]
)


if dst_ds is None:
    src_ds = None

    raise RuntimeError(
        "Could not create output MODIS raster:\n"
        f"{dest_file}"
    )


dst_ds.SetGeoTransform(
    geo_transform
)

dst_ds.SetProjection(
    projection
)


output_band = dst_ds.GetRasterBand(
    1
)

output_band.SetNoDataValue(
    float(nodata)
)

output_band.WriteArray(
    mode
)

output_band.FlushCache()


dst_ds.FlushCache()


# Close before verification.
dst_ds = None
src_ds = None


# ============================================================
# VERIFY OUTPUT
# ============================================================

check_ds = gdal.Open(
    str(dest_file),
    gdal.GA_ReadOnly
)


if check_ds is None:
    raise RuntimeError(
        "Created MODIS mode raster cannot be opened:\n"
        f"{dest_file}"
    )


if check_ds.RasterXSize != ncols:
    check_ds = None

    raise RuntimeError(
        "Output raster column count changed."
    )


if check_ds.RasterYSize != nrows:
    check_ds = None

    raise RuntimeError(
        "Output raster row count changed."
    )


if check_ds.RasterCount != 1:
    check_ds = None

    raise RuntimeError(
        "Output representative land-class raster "
        "must contain exactly one band."
    )


if check_ds.GetGeoTransform() != geo_transform:
    check_ds = None

    raise RuntimeError(
        "Output geotransform differs from source."
    )


if check_ds.GetProjection() != projection:
    check_ds = None

    raise RuntimeError(
        "Output projection differs from source."
    )


check_band = check_ds.GetRasterBand(
    1
)


output_nodata = check_band.GetNoDataValue()


if output_nodata != float(nodata):
    check_ds = None

    raise RuntimeError(
        "Output nodata value was not preserved."
    )


check_array = check_band.ReadAsArray()


if check_array is None:
    check_ds = None

    raise RuntimeError(
        "Could not read created output raster."
    )


if not np.array_equal(
    check_array,
    mode
):
    check_ds = None

    raise RuntimeError(
        "Output land-class values changed "
        "during GeoTIFF writing."
    )


check_ds = None


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    mode_land_class_path
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
    log_folder
    / this_file
)


copy2(
    CONTROL_FILE,
    log_folder
    / CONTROL_FILE.name
)


now = datetime.now()


log_file = (
    log_folder
    / (
        f"{now:%Y%m%d_%H%M%S}_"
        "create_mode_landclass.txt"
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
        f"Source raster: {source_file}\n"
    )

    file.write(
        f"Output raster: {dest_file}\n"
    )

    file.write(
        f"Raster dimensions: "
        f"{ncols} x {nrows}\n"
    )

    file.write(
        f"MODIS bands: {num_bands}\n"
    )

    file.write(
        f"NoData value: {nodata}\n"
    )

    file.write(
        f"Valid output classes: "
        f"{unique_classes.tolist()}\n"
    )

    file.write(
        f"NoData cells: {nodata_count}\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("MODIS REPRESENTATIVE LAND-CLASS CREATION COMPLETED")
print("=" * 70)
print(f"Domain       : {domain_name}")
print(f"Bands used   : {num_bands}")
print(f"Classes      : {unique_classes.tolist()}")
print(f"NoData value : {nodata}")
print(f"NoData cells : {nodata_count}")
print(f"Output       : {dest_file}")
print(f"Workflow log : {log_file}")