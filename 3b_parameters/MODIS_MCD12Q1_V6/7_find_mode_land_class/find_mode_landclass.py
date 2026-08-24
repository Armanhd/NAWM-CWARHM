#!/usr/bin/env python
# coding: utf-8

# Find mode land class
#
# Reads the multiband MODIS land-class GeoTIFF and calculates
# the modal land class across all available bands/years.
#
# For the current Example setup there is only one band (2022),
# so the output will simply equal the 2022 land-class raster.
#
# This implementation is also reusable later if multiple annual
# MODIS bands are available.

# Modules
import numpy as np
from pathlib import Path
import scipy.stats as sc
from shutil import copyfile
from datetime import datetime
from osgeo import gdal


# =========================================================
# Control file handling
# =========================================================

controlFolder = Path('../../../0_control_files')
controlFile = 'control_active.txt'


def read_from_control(file, setting):

    with open(file) as contents:

        for line in contents:

            if line.startswith(setting) and not line.startswith('#'):

                value = line.split('|', 1)[1]
                value = value.split('#', 1)[0]

                return value.strip()

    raise ValueError(
        f"Setting not found in control file: {setting}"
    )


def make_default_path(suffix):

    rootPath = Path(
        read_from_control(
            controlFolder / controlFile,
            'root_path'
        )
    )

    domainName = read_from_control(
        controlFolder / controlFile,
        'domain_name'
    )

    domainFolder = 'domain_' + domainName

    return rootPath / domainFolder / suffix


# =========================================================
# Source multiband land-class raster
# =========================================================

landClassPath = read_from_control(
    controlFolder / controlFile,
    'parameter_land_tif_path'
)

if landClassPath == 'default':

    landClassPath = make_default_path(
        'parameters/landclass/6_tif_multiband'
    )

else:

    landClassPath = Path(landClassPath)


# =========================================================
# Destination mode land-class folder
# =========================================================

modeLandClassPath = read_from_control(
    controlFolder / controlFile,
    'parameter_land_mode_path'
)

if modeLandClassPath == 'default':

    modeLandClassPath = make_default_path(
        'parameters/landclass/7_mode_land_class'
    )

else:

    modeLandClassPath = Path(modeLandClassPath)


modeLandClassPath.mkdir(
    parents=True,
    exist_ok=True
)


# =========================================================
# Find source TIFF
# =========================================================

source_files = sorted(
    landClassPath.glob("*.tif")
)

if len(source_files) == 0:

    raise RuntimeError(
        f"No land-class TIFF found in: "
        f"{landClassPath}"
    )


if len(source_files) > 1:

    raise RuntimeError(
        f"Expected one multiband land-class TIFF, "
        f"but found {len(source_files)}:\n"
        + "\n".join(
            f"  {f.name}"
            for f in source_files
        )
    )


source_file = source_files[0]

print(
    f"Source land-class file: "
    f"{source_file}"
)


# =========================================================
# Destination filename
# =========================================================

dest_file_name = read_from_control(
    controlFolder / controlFile,
    'parameter_land_tif_name'
)

dest_file = (
    modeLandClassPath
    / dest_file_name
)

print(
    f"Output mode land-class file: "
    f"{dest_file}"
)


# =========================================================
# Open source raster
# =========================================================

src_ds = gdal.Open(
    str(source_file),
    gdal.GA_ReadOnly
)

if src_ds is None:

    raise RuntimeError(
        f"Could not open land-class raster: "
        f"{source_file}"
    )


num_bands = src_ds.RasterCount
ncols = src_ds.RasterXSize
nrows = src_ds.RasterYSize

print()
print("Land-class raster information")
print("-----------------------------")
print(f"Columns: {ncols}")
print(f"Rows   : {nrows}")
print(f"Bands  : {num_bands}")


if num_bands == 0:

    src_ds = None

    raise RuntimeError(
        "Land-class raster contains no bands."
    )


# =========================================================
# Read all available bands
# =========================================================

land_use_classes = []

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

    if band is None:

        src_ds = None

        raise RuntimeError(
            f"Could not read band "
            f"{band_number}"
        )

    data = band.ReadAsArray()

    if data is None:

        src_ds = None

        raise RuntimeError(
            f"Could not read raster values "
            f"from band {band_number}"
        )

    land_use_classes.append(
        data
    )


# Stack to:
#
# rows x columns x bands
#
land_use_classes = np.dstack(
    land_use_classes
)

print()
print(
    "Stacked land-class shape:",
    land_use_classes.shape
)


# =========================================================
# Calculate modal land class
# =========================================================

if num_bands == 1:

    # With one year there is no temporal mode calculation
    # to perform; the only band is the representative class.
    mode = land_use_classes[:, :, 0]

    print(
        "Only one MODIS band available; "
        "using that band directly."
    )

else:

    print(
        f"Calculating modal land class "
        f"across {num_bands} bands."
    )

    mode_result = sc.mode(
        land_use_classes,
        axis=2,
        keepdims=False
    )

    mode = mode_result.mode


# =========================================================
# Basic QA
# =========================================================

unique_classes = np.unique(
    mode
)

print()
print(
    "Land classes in output:",
    unique_classes
)


# =========================================================
# Write output GeoTIFF
# =========================================================

geo_transform = (
    src_ds.GetGeoTransform()
)

projection = (
    src_ds.GetProjection()
)

driver = gdal.GetDriverByName(
    "GTiff"
)

if driver is None:

    src_ds = None

    raise RuntimeError(
        "GDAL GTiff driver is unavailable."
    )


# Land classes are integer categorical values.
# Byte is sufficient for MODIS IGBP classes.
dst_ds = driver.Create(
    str(dest_file),
    ncols,
    nrows,
    1,
    gdal.GDT_Byte,
    options=[
        'COMPRESS=DEFLATE'
    ]
)

if dst_ds is None:

    src_ds = None

    raise RuntimeError(
        f"Could not create output file: "
        f"{dest_file}"
    )


dst_ds.SetGeoTransform(
    geo_transform
)

dst_ds.SetProjection(
    projection
)


output_band = (
    dst_ds.GetRasterBand(1)
)

output_band.WriteArray(
    mode.astype(np.uint8)
)

output_band.FlushCache()


# Close raster datasets
dst_ds = None
src_ds = None


print()
print(
    f"Created: {dest_file}"
)


# =========================================================
# Code provenance
# =========================================================

logPath = modeLandClassPath
logFolder = '_workflow_log'

(
    logPath
    / logFolder
).mkdir(
    parents=True,
    exist_ok=True
)


thisFile = 'find_mode_landclass.py'

try:

    copyfile(
        thisFile,
        logPath
        / logFolder
        / thisFile
    )

except FileNotFoundError:

    pass


now = datetime.now()

logFile = (
    logPath
    / logFolder
    / (
        now.strftime('%Y%m%d')
        + '_mode_over_years_log.txt'
    )
)


with open(
    logFile,
    'w'
) as file:

    file.write(
        f"Log generated by {thisFile} on "
        f"{now.strftime('%Y/%m/%d %H:%M:%S')}\n"
    )

    file.write(
        f"Source file: {source_file.name}\n"
    )

    file.write(
        f"Number of MODIS bands: "
        f"{num_bands}\n"
    )

    file.write(
        "Created representative/modal "
        "land-class raster.\n"
    )


print(
    f"Workflow log: {logFile}"
)