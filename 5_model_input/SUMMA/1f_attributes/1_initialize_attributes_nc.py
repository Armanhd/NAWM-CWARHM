# Initialize attributes.nc for the active NWAM-SUMMA domain.
#
# SUMMA requires identical HRU ordering in forcing, attributes,
# coldState and trialParams files. The HRU order is therefore
# taken from the first forcing file listed in forcingFileList.txt.
#
# The catchment shapefile is reordered to exactly match that
# forcing HRU order before attributes.nc is written.
#
# Fill values / sources
# ------------------------------------------------------------
# hruId          : configured catchment HRU field
# gruId          : configured catchment GRU field
# hru2gruId      : GRU containing each HRU
# downHRUindex   : initialized to 0
# longitude      : configured catchment longitude field
# latitude       : configured catchment latitude field
# elevation      : -999 placeholder; filled by 2c
# HRUarea        : configured catchment area field [m2]
# tan_slope      : fixed at 0.1
# contourLength  : fixed at 30 m
# slopeTypeIndex : fixed at 1
# soilTypeIndex  : -999 placeholder; filled by 2a
# vegTypeIndex   : -999 placeholder; filled by 2b
# mHeight        : forcing_measurement_height from control file
#
# Modeling assumptions
# ------------------------------------------------------------
# tan_slope and contourLength are placeholders in the current
# workflow. They are important for qbaseTopmodel and should be
# replaced with physically derived values before that option is
# used.
#
# slopeTypeIndex is retained for SUMMA compatibility.
#
# downHRUindex = 0 treats each HRU as an independent column.
# If settings_summa_connect_HRUs = yes, script 2c later replaces
# these values using the HRU elevation ordering within each GRU.
#
# For multi-HRU GRUs, SUMMA requires all HRUs belonging to one
# GRU to occupy consecutive positions in the NetCDF HRU order.
# This script validates that condition but never silently
# reorders forcing-derived HRUs.

from pathlib import Path
from datetime import datetime
from shutil import copy2

import geopandas as gpd
import netCDF4 as nc4
import numpy as np
import pandas as pd
import xarray as xr


# ============================================================
# PROJECT / CONTROL FILE
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM_ROOT = SCRIPT_DIR.parents[2]

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

    with open(file) as contents:

        for line in contents:

            stripped = line.strip()

            if (
                stripped
                and not stripped.startswith("#")
                and "|" in stripped
            ):

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

    value = read_from_control(
        CONTROL_FILE,
        setting
    )

    if value == "default":
        return make_default_path(
            default_suffix
        )

    return Path(value)


def validate_int32(values, name):

    values = np.asarray(
        values,
        dtype=np.int64
    )

    info = np.iinfo(
        np.int32
    )

    if (
        np.any(values < info.min)
        or np.any(values > info.max)
    ):
        raise RuntimeError(
            f"{name} contains values outside "
            "the 32-bit integer range required "
            "by this attributes.nc setup."
        )


def validate_gru_contiguity(gru_values):

    seen = set()
    previous = None

    for value in gru_values:

        value = int(value)

        if value != previous:

            if value in seen:
                raise RuntimeError(
                    f"GRU {value} appears in multiple "
                    "non-contiguous HRU blocks. SUMMA "
                    "requires HRUs belonging to the same "
                    "GRU to be consecutive."
                )

            seen.add(value)
            previous = value


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# CATCHMENT INPUT
# ============================================================

catchment_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
)

# IMPORTANT:
# Stage 00 creates the prepared CWARHM catchment here.
# Do not use the original MERIT source directory from
# catchment_shp_path in the control file.
catchment_path = make_default_path(
    "shapefiles/catchment"
)

catchment_file = (
    catchment_path
    / catchment_name
)


hru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)

gru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_gruid"
)

area_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_area"
)

lat_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_lat"
)

lon_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_lon"
)


if not catchment_file.exists():
    raise FileNotFoundError(
        "Prepared CWARHM catchment shapefile not found:\n"
        f"{catchment_file}\n\n"
        "Run Stage 00 before creating attributes.nc."
    )


# ============================================================
# FORCING / AUTHORITATIVE HRU ORDER
# ============================================================

forcing_path = resolve_path(
    "forcing_summa_path",
    "forcing/4_SUMMA_input"
)

settings_path = resolve_path(
    "settings_summa_path",
    "settings/SUMMA"
)

settings_path.mkdir(
    parents=True,
    exist_ok=True
)


forcing_list_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_forcing_list"
)

forcing_list_file = (
    settings_path
    / forcing_list_name
)


if not forcing_list_file.exists():
    raise FileNotFoundError(
        f"Forcing file list not found:\n"
        f"{forcing_list_file}\n"
        "Run Step 18 first."
    )


with open(forcing_list_file) as file:

    forcing_names = [
        line.strip()
        for line in file
        if line.strip()
    ]


if not forcing_names:
    raise RuntimeError(
        "forcingFileList.txt is empty."
    )


forcing_file = (
    forcing_path
    / forcing_names[0]
)


if not forcing_file.exists():
    raise FileNotFoundError(
        f"Forcing template not found:\n"
        f"{forcing_file}"
    )


with xr.open_dataset(
    forcing_file
) as forcing:

    if "hruId" not in forcing:
        raise RuntimeError(
            f"hruId not found in forcing file:\n"
            f"{forcing_file}"
        )

    forcing_hru_ids = np.asarray(
        forcing["hruId"].values
    ).squeeze()


if forcing_hru_ids.ndim != 1:
    raise RuntimeError(
        "Forcing hruId must be one-dimensional."
    )


if not np.all(
    np.isfinite(forcing_hru_ids)
):
    raise RuntimeError(
        "Non-finite hruId values found in forcing."
    )


forcing_hru_ids = forcing_hru_ids.astype(
    np.int64
)


if len(np.unique(forcing_hru_ids)) != len(
    forcing_hru_ids
):
    raise RuntimeError(
        "Duplicate hruId values found in forcing."
    )


validate_int32(
    forcing_hru_ids,
    "hruId"
)


# ============================================================
# OTHER SETTINGS
# ============================================================

forcing_measurement_height = float(
    read_from_control(
        CONTROL_FILE,
        "forcing_measurement_height"
    )
)

if not np.isfinite(
    forcing_measurement_height
):
    raise ValueError(
        "forcing_measurement_height is not finite."
    )


attribute_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_attributes"
)

attribute_file = (
    settings_path
    / attribute_name
)


# ============================================================
# READ AND VALIDATE CATCHMENTS
# ============================================================

shp = gpd.read_file(
    catchment_file
)


if len(shp) == 0:
    raise RuntimeError(
        "Catchment shapefile contains no HRUs."
    )


required_fields = [
    hru_field,
    gru_field,
    area_field,
    lat_field,
    lon_field,
]


missing_fields = [
    field
    for field in required_fields
    if field not in shp.columns
]


if missing_fields:
    raise RuntimeError(
        "Required catchment fields missing:\n"
        + "\n".join(
            f"  {field}"
            for field in missing_fields
        )
    )


for field in [
    hru_field,
    gru_field,
    area_field,
    lat_field,
    lon_field,
]:

    shp[field] = pd.to_numeric(
        shp[field],
        errors="raise"
    )


if shp[hru_field].duplicated().any():
    raise RuntimeError(
        f"Duplicate {hru_field} values "
        "found in catchment shapefile."
    )


shapefile_hru_ids = set(
    shp[hru_field]
    .astype(np.int64)
    .tolist()
)

forcing_hru_set = set(
    forcing_hru_ids.tolist()
)


missing_from_shape = sorted(
    forcing_hru_set
    - shapefile_hru_ids
)

extra_in_shape = sorted(
    shapefile_hru_ids
    - forcing_hru_set
)


if missing_from_shape or extra_in_shape:

    raise RuntimeError(
        "Catchment and forcing HRU sets differ.\n"
        f"Missing from catchment: {missing_from_shape}\n"
        f"Extra in catchment: {extra_in_shape}"
    )


# ============================================================
# REORDER CATCHMENTS TO FORCING HRU ORDER
# ============================================================

shp[hru_field] = shp[hru_field].astype(
    np.int64
)

shp[gru_field] = shp[gru_field].astype(
    np.int64
)


shp = shp.set_index(
    hru_field,
    drop=False
)


shp = shp.loc[
    forcing_hru_ids
].copy()


shp = shp.reset_index(
    drop=True
)


hru_ids = shp[
    hru_field
].to_numpy(
    dtype=np.int64
)

hru_to_gru = shp[
    gru_field
].to_numpy(
    dtype=np.int64
)

gru_ids = pd.unique(
    hru_to_gru
).astype(
    np.int64
)


validate_int32(
    hru_to_gru,
    "GRU IDs"
)

validate_gru_contiguity(
    hru_to_gru
)


if not np.array_equal(
    hru_ids,
    forcing_hru_ids
):
    raise RuntimeError(
        "HRU ordering failed to match forcing."
    )


# ============================================================
# VALIDATE NUMERIC ATTRIBUTES
# ============================================================

areas = shp[
    area_field
].to_numpy(
    dtype=np.float64
)

latitudes = shp[
    lat_field
].to_numpy(
    dtype=np.float64
)

longitudes = shp[
    lon_field
].to_numpy(
    dtype=np.float64
)


if not np.all(
    np.isfinite(areas)
):
    raise RuntimeError(
        "Non-finite HRU area values found."
    )


if np.any(
    areas <= 0
):
    raise RuntimeError(
        "HRU area must be greater than zero."
    )


if not np.all(
    np.isfinite(latitudes)
):
    raise RuntimeError(
        "Non-finite HRU latitude values found."
    )


if not np.all(
    np.isfinite(longitudes)
):
    raise RuntimeError(
        "Non-finite HRU longitude values found."
    )


if (
    np.any(latitudes < -90)
    or np.any(latitudes > 90)
):
    raise RuntimeError(
        "Invalid latitude values found."
    )


num_hru = len(
    hru_ids
)

num_gru = len(
    gru_ids
)


# ============================================================
# REPORT
# ============================================================

print()
print("============================================================")
print("INITIALIZE SUMMA ATTRIBUTES")
print("============================================================")
print(f"Domain           : {domain_name}")
print(f"Catchment        : {catchment_file}")
print(f"Forcing template : {forcing_file}")
print(f"HRUs             : {num_hru}")
print(f"GRUs             : {num_gru}")
print(f"mHeight          : {forcing_measurement_height} m")
print(f"Output           : {attribute_file}")


# ============================================================
# CREATE attributes.nc
# ============================================================

with nc4.Dataset(
    attribute_file,
    "w",
    format="NETCDF4"
) as att:

    now = datetime.now()

    att.setncattr(
        "Author",
        "NWAM-SUMMA workflow"
    )

    att.setncattr(
        "History",
        "Created "
        + now.strftime(
            "%Y/%m/%d %H:%M:%S"
        )
    )

    att.setncattr(
        "HRU_order_source",
        forcing_file.name
    )


    # --------------------------------------------------------
    # Dimensions
    # --------------------------------------------------------

    att.createDimension(
        "hru",
        num_hru
    )

    att.createDimension(
        "gru",
        num_gru
    )


    # --------------------------------------------------------
    # Variables
    # --------------------------------------------------------

    definitions = {
        "hruId": (
            "i4",
            ("hru",),
            "-",
            "Index of hydrological response unit (HRU)"
        ),
        "gruId": (
            "i4",
            ("gru",),
            "-",
            "Index of grouped response unit (GRU)"
        ),
        "hru2gruId": (
            "i4",
            ("hru",),
            "-",
            "Index of GRU to which the HRU belongs"
        ),
        "downHRUindex": (
            "i4",
            ("hru",),
            "-",
            "Index of downslope HRU (0 = basin outlet)"
        ),
        "longitude": (
            "f8",
            ("hru",),
            "Decimal degree east",
            "Longitude of HRU's centroid"
        ),
        "latitude": (
            "f8",
            ("hru",),
            "Decimal degree north",
            "Latitude of HRU's centroid"
        ),
        "elevation": (
            "f8",
            ("hru",),
            "m",
            "Mean elevation of HRU"
        ),
        "HRUarea": (
            "f8",
            ("hru",),
            "m^2",
            "Area of HRU"
        ),
        "tan_slope": (
            "f8",
            ("hru",),
            "m m-1",
            "Average tangent slope of HRU"
        ),
        "contourLength": (
            "f8",
            ("hru",),
            "m",
            "Contour length of HRU"
        ),
        "slopeTypeIndex": (
            "i4",
            ("hru",),
            "-",
            "Index defining slope"
        ),
        "soilTypeIndex": (
            "i4",
            ("hru",),
            "-",
            "Index defining soil type"
        ),
        "vegTypeIndex": (
            "i4",
            ("hru",),
            "-",
            "Index defining vegetation type"
        ),
        "mHeight": (
            "f8",
            ("hru",),
            "m",
            "Measurement height above bare ground"
        ),
    }


    for (
        name,
        (
            dtype,
            dimensions,
            units,
            long_name
        )
    ) in definitions.items():

        variable = att.createVariable(
            name,
            dtype,
            dimensions
        )

        variable.setncattr(
            "units",
            units
        )

        variable.setncattr(
            "long_name",
            long_name
        )


    # --------------------------------------------------------
    # IDs / spatial information
    # --------------------------------------------------------

    att["hruId"][:] = hru_ids.astype(
        np.int32
    )

    att["gruId"][:] = gru_ids.astype(
        np.int32
    )

    att["hru2gruId"][:] = hru_to_gru.astype(
        np.int32
    )

    att["HRUarea"][:] = areas
    att["latitude"][:] = latitudes
    att["longitude"][:] = longitudes


    # --------------------------------------------------------
    # Current workflow constants
    # --------------------------------------------------------

    att["downHRUindex"][:] = 0

    att["tan_slope"][:] = 0.1

    att["contourLength"][:] = 30.0

    att["slopeTypeIndex"][:] = 1

    att["mHeight"][:] = (
        forcing_measurement_height
    )


    # --------------------------------------------------------
    # Placeholders filled by 2a / 2b / 2c
    # --------------------------------------------------------

    att["elevation"][:] = -999.0

    att["soilTypeIndex"][:] = -999

    att["vegTypeIndex"][:] = -999


# ============================================================
# VERIFY OUTPUT
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r"
) as att:

    output_hru_ids = np.asarray(
        att["hruId"][:],
        dtype=np.int64
    )

    output_hru_to_gru = np.asarray(
        att["hru2gruId"][:],
        dtype=np.int64
    )


if not np.array_equal(
    output_hru_ids,
    forcing_hru_ids
):
    raise RuntimeError(
        "attributes.nc HRU order does not match forcing."
    )


if not np.array_equal(
    output_hru_to_gru,
    hru_to_gru
):
    raise RuntimeError(
        "attributes.nc hru2gruId validation failed."
    )


# ============================================================
# LOGGING
# ============================================================

log_folder = (
    settings_path
    / "_workflow_log"
)

log_folder.mkdir(
    parents=True,
    exist_ok=True
)


this_file = Path(__file__).name

copy2(
    Path(__file__).resolve(),
    log_folder / this_file
)


now = datetime.now()

log_file = (
    log_folder
    / f"{now:%Y%m%d}_initialize_attributes.txt"
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
        f"HRUs: {num_hru}\n"
    )

    file.write(
        f"GRUs: {num_gru}\n"
    )

    file.write(
        f"HRU order source: {forcing_file.name}\n"
    )

    file.write(
        f"Output: {attribute_file}\n"
    )


print()
print("attributes.nc initialized successfully.")
print(f"HRUs: {num_hru}")
print(f"GRUs: {num_gru}")
print(f"Output: {attribute_file}")