#!/usr/bin/env python
# coding: utf-8

"""
Crop the existing SoilGrids-derived soil-class raster to one CWARHM domain.

Usage
-----
python extract_domain.py \
/path/to/control_DOMAIN.txt

Purpose
-------
The global/shared SoilGrids-derived categorical soil-class raster is
cropped to the spatial extent specified by forcing_raw_space.

The script is domain-independent and does not use control_active.txt.
All domain-specific settings are read from the control file supplied
on the command line.
"""

from pathlib import Path
from datetime import datetime
from shutil import copy2
import sys

from osgeo import gdal


# ============================================================
# ENABLE GDAL EXCEPTIONS
# ============================================================

gdal.UseExceptions()


# ============================================================
# INPUT CONTROL FILE
# ============================================================

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage:\n"
        "python extract_domain.py "
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
    Read one exact setting from a CWARHM control file.
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


def resolve_path(setting, default_suffix):
    """
    Resolve either a user-defined path or a standard domain path.
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
# SOURCE SOIL-CLASS RASTER DIRECTORY
# ============================================================

soil_raw_path = resolve_path(
    "parameter_soil_raw_path",
    "parameters/soilclass/1_soil_classes_global"
)


if not soil_raw_path.exists():
    raise FileNotFoundError(
        "Soil-class source directory not found:\n"
        f"{soil_raw_path}"
    )


if not soil_raw_path.is_dir():
    raise NotADirectoryError(
        f"Expected a directory:\n"
        f"{soil_raw_path}"
    )


# ============================================================
# OUTPUT DIRECTORY / FILE
# ============================================================

soil_domain_path = resolve_path(
    "parameter_soil_domain_path",
    "parameters/soilclass/2_soil_classes_domain"
)


soil_domain_name = read_from_control(
    CONTROL_FILE,
    "parameter_soil_tif_name"
)


soil_domain_path.mkdir(
    parents=True,
    exist_ok=True
)


output_file = (
    soil_domain_path
    / soil_domain_name
)


# ============================================================
# FIND SOURCE TIFF
# ============================================================

source_files = sorted(
    soil_raw_path.glob(
        "*.tif"
    )
)


if len(source_files) == 0:
    raise FileNotFoundError(
        "No SoilGrids-derived TIFF found in:\n"
        f"{soil_raw_path}"
    )


if len(source_files) > 1:
    raise RuntimeError(
        "Expected exactly one SoilGrids-derived "
        f"soil-class TIFF, but found {len(source_files)}:\n"
        + "\n".join(
            f"  {file}"
            for file in source_files
        )
    )


source_file = source_files[0]


# ============================================================
# DOMAIN EXTENT
# ============================================================

coordinates = read_from_control(
    CONTROL_FILE,
    "forcing_raw_space"
)


parts = [
    value.strip()
    for value in coordinates.split("/")
]


if len(parts) != 4:
    raise ValueError(
        "forcing_raw_space must have format:\n"
        "LAT_MAX/LON_MIN/LAT_MIN/LON_MAX"
    )


try:
    lat_max = float(parts[0])
    lon_min = float(parts[1])
    lat_min = float(parts[2])
    lon_max = float(parts[3])

except ValueError as exc:
    raise ValueError(
        "forcing_raw_space contains a non-numeric value."
    ) from exc


if lat_min >= lat_max:
    raise ValueError(
        "Invalid forcing_raw_space: "
        "LAT_MIN must be smaller than LAT_MAX."
    )


if lon_min >= lon_max:
    raise ValueError(
        "Invalid forcing_raw_space: "
        "LON_MIN must be smaller than LON_MAX."
    )


# gdal.Translate projWin order:
#
# upper-left x
# upper-left y
# lower-right x
# lower-right y

bbox = (
    lon_min,
    lat_max,
    lon_max,
    lat_min
)


# ============================================================
# INSPECT SOURCE RASTER
# ============================================================

source_ds = gdal.Open(
    str(source_file),
    gdal.GA_ReadOnly
)


if source_ds is None:
    raise RuntimeError(
        "Could not open SoilGrids raster:\n"
        f"{source_file}"
    )


source_projection = (
    source_ds.GetProjection()
)

source_geotransform = (
    source_ds.GetGeoTransform()
)

source_nodata = (
    source_ds
    .GetRasterBand(1)
    .GetNoDataValue()
)


if not source_projection:
    source_ds = None

    raise RuntimeError(
        "Source SoilGrids raster has no CRS."
    )


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("EXTRACT SOILGRIDS DOMAIN")
print("=" * 70)
print()
print(f"Domain       : {domain_name}")
print(f"Control file : {CONTROL_FILE}")
print(f"Source TIFF  : {source_file}")
print(f"Output TIFF  : {output_file}")
print()
print("Domain extent:")
print(
    f"  latitude : "
    f"{lat_min:.6f} to {lat_max:.6f}"
)
print(
    f"  longitude: "
    f"{lon_min:.6f} to {lon_max:.6f}"
)
print()
print(
    f"Source size  : "
    f"{source_ds.RasterXSize} x "
    f"{source_ds.RasterYSize}"
)
print(
    f"Source nodata: "
    f"{source_nodata}"
)


source_ds = None


# ============================================================
# REMOVE EXISTING OUTPUT
# ============================================================

if output_file.exists():
    output_file.unlink()


# ============================================================
# CROP SOIL RASTER
# ============================================================

translate_options = gdal.TranslateOptions(
    format="GTiff",
    projWin=bbox,
    creationOptions=[
        "COMPRESS=DEFLATE",
        "TILED=YES",
        "BIGTIFF=IF_SAFER",
    ]
)


try:

    output_ds = gdal.Translate(
        str(output_file),
        str(source_file),
        options=translate_options
    )

except RuntimeError as exc:

    raise RuntimeError(
        "GDAL failed while cropping the "
        "SoilGrids raster."
    ) from exc


if output_ds is None:
    raise RuntimeError(
        "GDAL did not create the cropped "
        "SoilGrids raster."
    )


output_ds.FlushCache()
output_ds = None


# ============================================================
# VERIFY OUTPUT
# ============================================================

if not output_file.exists():
    raise RuntimeError(
        "Output SoilGrids raster was not created:\n"
        f"{output_file}"
    )


check_ds = gdal.Open(
    str(output_file),
    gdal.GA_ReadOnly
)


if check_ds is None:
    raise RuntimeError(
        "Created SoilGrids raster cannot be opened:\n"
        f"{output_file}"
    )


ncols = check_ds.RasterXSize
nrows = check_ds.RasterYSize


if ncols <= 0 or nrows <= 0:
    check_ds = None

    raise RuntimeError(
        "Cropped SoilGrids raster is empty."
    )


if check_ds.RasterCount < 1:
    check_ds = None

    raise RuntimeError(
        "Cropped SoilGrids raster contains no bands."
    )


output_projection = (
    check_ds.GetProjection()
)


if not output_projection:
    check_ds = None

    raise RuntimeError(
        "Cropped SoilGrids raster has no CRS."
    )


band = check_ds.GetRasterBand(
    1
)


output_nodata = (
    band.GetNoDataValue()
)


array = band.ReadAsArray()


if array is None:
    check_ds = None

    raise RuntimeError(
        "Could not read the cropped SoilGrids raster."
    )


# ============================================================
# CHECK VALID SOIL VALUES
# ============================================================

import numpy as np


values = np.asarray(
    array
)


if output_nodata is not None:

    valid = values[
        values != output_nodata
    ]

else:

    valid = values.ravel()


if valid.size == 0:
    check_ds = None

    raise RuntimeError(
        "Cropped SoilGrids raster contains "
        "no valid soil-class pixels."
    )


if np.issubdtype(
    valid.dtype,
    np.floating
):

    valid = valid[
        np.isfinite(valid)
    ]


if valid.size == 0:
    check_ds = None

    raise RuntimeError(
        "Cropped SoilGrids raster contains "
        "no finite soil-class values."
    )


unique_classes = np.unique(
    valid
)


check_ds = None


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    soil_domain_path
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
        "soilclass_cropping_log.txt"
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
        f"Output raster: {output_file}\n"
    )

    file.write(
        f"Domain bounds: "
        f"{lon_min}, {lat_min}, "
        f"{lon_max}, {lat_max}\n"
    )

    file.write(
        f"Output size: "
        f"{ncols} x {nrows}\n"
    )

    file.write(
        f"Output nodata: "
        f"{output_nodata}\n"
    )

    file.write(
        f"Soil classes: "
        f"{unique_classes.tolist()}\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("SOILGRIDS DOMAIN EXTRACTION COMPLETED")
print("=" * 70)
print(f"Domain       : {domain_name}")
print(f"Raster size  : {ncols} x {nrows}")
print(f"NoData value : {output_nodata}")
print(
    f"Soil classes : "
    f"{unique_classes.tolist()}"
)
print(f"Output       : {output_file}")
print(f"Workflow log : {log_file}")