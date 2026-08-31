#!/usr/bin/env python3
# coding: utf-8

# Initialize SUMMA attributes.nc for an NWAM-SUMMA domain.
#
# Purpose
# -------
# Create the base SUMMA attributes.nc using:
#
#   - the HRU ordering from the first final SUMMA forcing file
#   - HRU/GRU information from the Stage-00 prepared catchment
#
# SUMMA requires compatible HRU ordering among:
#
#   forcing files
#   attributes.nc
#   coldState.nc
#   trialParams.nc
#
# Therefore, the forcing hruId array is treated as authoritative.
#
# Initial fields
# --------------
# hruId          : prepared catchment HRU ID
# gruId          : unique GRU IDs
# hru2gruId      : GRU containing each HRU
# downHRUindex   : initialized to 0
# longitude      : prepared catchment HRU longitude
# latitude       : prepared catchment HRU latitude
# elevation      : -999 placeholder; populated by script 2c
# HRUarea        : prepared catchment HRU area [m2]
# tan_slope      : current workflow assumption = 0.1
# contourLength  : current workflow assumption = 30 m
# slopeTypeIndex : current workflow assumption = 1
# soilTypeIndex  : -999 placeholder; populated by script 2a
# vegTypeIndex   : -999 placeholder; populated by script 2b
# mHeight        : forcing_measurement_height from control file
#
# IMPORTANT
# ---------
# This script reads the domain-specific control file supplied on
# the command line.
#
# It does NOT read or modify control_active.txt.
#
# The catchment input is always the Stage-00 prepared CWARHM
# working copy:
#
#   <root_path>/domain_<domain_name>/shapefiles/catchment/
#
# and never the original read-only MERIT source shapefile.
#
# For multi-HRU GRUs, SUMMA requires all HRUs belonging to the
# same GRU to occupy consecutive positions in the HRU dimension.
# This script validates that requirement but never silently
# changes the forcing-derived HRU order.
#
# Usage
# -----
#
# python 1_initialize_attributes_nc.py \
#     /path/to/control_DOMAIN.txt

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

import geopandas as gpd
import netCDF4 as nc4
import numpy as np
import pandas as pd
import xarray as xr


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_initialize_attributes_nc.py "
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
    Read one control setting using exact key matching.
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
    Construct:
        <root_path>/domain_<domain_name>/<suffix>
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
    Resolve a control-file path that may be 'default'.
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
    )


def convert_integer_ids(values, name):
    """
    Validate numeric IDs and return int64 values.
    """
    values = (
        np.asarray(
            values
        )
        .reshape(-1)
    )
    
    if values.ndim != 1:

        raise RuntimeError(
            f"{name} must be one-dimensional.\n"
            f"Shape found: {values.shape}"
        )


    if values.size == 0:

        raise RuntimeError(
            f"No values found for {name}."
        )


    try:

        values_float = values.astype(
            np.float64
        )

    except Exception as exc:

        raise RuntimeError(
            f"{name} could not be converted "
            "to numeric values."
        ) from exc


    if not np.all(
        np.isfinite(
            values_float
        )
    ):

        raise RuntimeError(
            f"{name} contains non-finite values."
        )


    if not np.allclose(
        values_float,
        np.round(
            values_float
        )
    ):

        raise RuntimeError(
            f"{name} contains non-integer values."
        )


    return (
        np.round(
            values_float
        )
        .astype(np.int64)
    )


def validate_int32(values, name):
    """
    Ensure IDs fit the int32 representation used in attributes.nc.
    """

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
            f"{name} contains values outside the "
            "32-bit integer range required by "
            "the current attributes.nc format."
        )


def validate_gru_contiguity(gru_values):
    """
    Verify that each GRU occurs in one continuous HRU block.
    """

    seen = set()

    previous = None


    for raw_value in gru_values:

        value = int(
            raw_value
        )


        if value != previous:

            if value in seen:

                raise RuntimeError(
                    f"GRU {value} appears in multiple "
                    "non-contiguous HRU blocks.\n\n"
                    "SUMMA requires all HRUs belonging "
                    "to a GRU to be consecutive in the "
                    "HRU dimension."
                )


            seen.add(
                value
            )

            previous = value


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


# Always use the Stage-00 prepared CWARHM catchment.

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
        "Prepared CWARHM catchment shapefile "
        "not found:\n"
        f"{catchment_file}\n\n"
        "Run Stage 00 before creating "
        "attributes.nc."
    )


# ============================================================
# FORCING / SETTINGS PATHS
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


if not forcing_path.exists():

    raise FileNotFoundError(
        "SUMMA forcing directory not found:\n"
        f"{forcing_path}"
    )


# ============================================================
# FORCING FILE LIST
# ============================================================

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
        "SUMMA forcing-file list not found:\n"
        f"{forcing_list_file}\n\n"
        "Run 1_create_forcing_file_list.py after "
        "the complete forcing archive has been "
        "generated."
    )


with open(
    forcing_list_file
) as file:

    forcing_names = [
        line.strip()
        for line in file
        if line.strip()
        and not line.lstrip().startswith("#")
    ]


if not forcing_names:

    raise RuntimeError(
        "forcingFileList.txt is empty:\n"
        f"{forcing_list_file}"
    )


if len(
    forcing_names
) != len(
    set(
        forcing_names
    )
):

    raise RuntimeError(
        "Duplicate filenames found in "
        "forcingFileList.txt."
    )


forcing_file = (
    forcing_path
    / forcing_names[0]
)


if not forcing_file.exists():

    raise FileNotFoundError(
        "First forcing file listed in "
        "forcingFileList.txt does not exist:\n"
        f"{forcing_file}"
    )


# ============================================================
# READ AUTHORITATIVE HRU ORDER FROM FORCING
# ============================================================

with xr.open_dataset(
    forcing_file
) as forcing:

    if "hru" not in forcing.dims:

        raise RuntimeError(
            "SUMMA forcing file does not contain "
            "an 'hru' dimension:\n"
            f"{forcing_file}"
        )


    if "hruId" not in forcing:

        raise RuntimeError(
            "hruId not found in SUMMA forcing file:\n"
            f"{forcing_file}"
        )


    forcing_hru_ids = convert_integer_ids(
        forcing[
            "hruId"
        ].values,
        "Forcing hruId"
    )


    if (
        forcing.sizes["hru"]
        != len(forcing_hru_ids)
    ):

        raise RuntimeError(
            "Forcing hru dimension and hruId "
            "length do not agree."
        )


if len(
    np.unique(
        forcing_hru_ids
    )
) != len(
    forcing_hru_ids
):

    raise RuntimeError(
        "Duplicate hruId values found in forcing."
    )


validate_int32(
    forcing_hru_ids,
    "Forcing hruId"
)


# ============================================================
# OTHER CONTROL SETTINGS
# ============================================================

try:

    forcing_measurement_height = float(
        read_from_control(
            CONTROL_FILE,
            "forcing_measurement_height"
        )
    )

except Exception as exc:

    raise ValueError(
        "forcing_measurement_height must be numeric."
    ) from exc


if not np.isfinite(
    forcing_measurement_height
):

    raise ValueError(
        "forcing_measurement_height is not finite."
    )


if forcing_measurement_height < 0:

    raise ValueError(
        "forcing_measurement_height cannot "
        "be negative."
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
# READ PREPARED CATCHMENT
# ============================================================

shp = gpd.read_file(
    catchment_file,
    engine="fiona"
)


if len(shp) == 0:

    raise RuntimeError(
        "Prepared catchment contains no HRUs."
    )


if shp.crs is None:

    raise RuntimeError(
        "Prepared catchment has no CRS:\n"
        f"{catchment_file}"
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
        "Prepared catchment is missing required "
        "attribute field(s):\n"
        + "\n".join(
            f"  {field}"
            for field in missing_fields
        )
    )


# ============================================================
# CONVERT / VALIDATE CATCHMENT FIELDS
# ============================================================

for field in required_fields:

    try:

        shp[field] = pd.to_numeric(
            shp[field],
            errors="raise"
        )

    except Exception as exc:

        raise RuntimeError(
            f"Catchment field '{field}' "
            "contains non-numeric values."
        ) from exc


catchment_hru_ids = convert_integer_ids(
    shp[
        hru_field
    ].to_numpy(),
    hru_field
)


catchment_gru_ids = convert_integer_ids(
    shp[
        gru_field
    ].to_numpy(),
    gru_field
)


if len(
    np.unique(
        catchment_hru_ids
    )
) != len(
    catchment_hru_ids
):

    raise RuntimeError(
        f"Duplicate {hru_field} values "
        "found in prepared catchment."
    )


validate_int32(
    catchment_hru_ids,
    hru_field
)


validate_int32(
    catchment_gru_ids,
    gru_field
)


# Replace with validated integer versions.

shp[hru_field] = (
    catchment_hru_ids
)


shp[gru_field] = (
    catchment_gru_ids
)


# ============================================================
# COMPARE HRU SETS
# ============================================================

shapefile_hru_set = set(
    catchment_hru_ids.tolist()
)


forcing_hru_set = set(
    forcing_hru_ids.tolist()
)


missing_from_shape = sorted(
    forcing_hru_set
    - shapefile_hru_set
)


extra_in_shape = sorted(
    shapefile_hru_set
    - forcing_hru_set
)


if (
    missing_from_shape
    or extra_in_shape
):

    raise RuntimeError(
        "Prepared catchment and forcing HRU "
        "sets differ.\n\n"
        f"Missing from catchment: "
        f"{missing_from_shape}\n"
        f"Extra in catchment   : "
        f"{extra_in_shape}"
    )


# ============================================================
# REORDER CATCHMENT TO FORCING HRU ORDER
# ============================================================

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


if not np.array_equal(
    hru_ids,
    forcing_hru_ids
):

    raise RuntimeError(
        "Prepared catchment could not be "
        "reordered to match forcing hruId."
    )


# Unique GRUs in the order in which they first occur.

gru_ids = pd.unique(
    hru_to_gru
).astype(
    np.int64
)


validate_int32(
    hru_to_gru,
    "hru2gruId"
)


validate_int32(
    gru_ids,
    "gruId"
)


# SUMMA grouping requirement.

validate_gru_contiguity(
    hru_to_gru
)


# ============================================================
# VALIDATE NUMERIC SPATIAL ATTRIBUTES
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
    np.isfinite(
        areas
    )
):

    raise RuntimeError(
        "Non-finite HRU area values found."
    )


if np.any(
    areas <= 0
):

    raise RuntimeError(
        "All HRU areas must be greater "
        "than zero."
    )


if not np.all(
    np.isfinite(
        latitudes
    )
):

    raise RuntimeError(
        "Non-finite HRU latitude values found."
    )


if not np.all(
    np.isfinite(
        longitudes
    )
):

    raise RuntimeError(
        "Non-finite HRU longitude values found."
    )


if (
    np.any(
        latitudes < -90
    )
    or np.any(
        latitudes > 90
    )
):

    raise RuntimeError(
        "Invalid latitude values found."
    )


if (
    np.any(
        longitudes < -180
    )
    or np.any(
        longitudes > 180
    )
):

    raise RuntimeError(
        "Invalid longitude values found."
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
print("=" * 70)
print("INITIALIZE SUMMA ATTRIBUTES")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"Catchment        : {catchment_file}"
)

print(
    f"Catchment CRS    : {shp.crs}"
)

print(
    f"Forcing list     : {forcing_list_file}"
)

print(
    f"Forcing template : {forcing_file}"
)

print(
    f"HRUs             : {num_hru}"
)

print(
    f"GRUs             : {num_gru}"
)

print(
    f"First HRU ID     : {hru_ids[0]}"
)

print(
    f"Last HRU ID      : {hru_ids[-1]}"
)

print(
    f"mHeight          : "
    f"{forcing_measurement_height:g} m"
)

print(
    f"Output           : {attribute_file}"
)


# ============================================================
# CREATE attributes.nc
# ============================================================

# Existing output is replaced only after all validations above
# have succeeded.

with nc4.Dataset(
    attribute_file,
    "w",
    format="NETCDF4"
) as att:

    now = datetime.now()


    # --------------------------------------------------------
    # Global attributes
    # --------------------------------------------------------

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
        "Purpose",
        "SUMMA HRU and GRU attributes"
    )

    att.setncattr(
        "Domain",
        domain_name
    )

    att.setncattr(
        "HRU_order_source",
        forcing_file.name
    )

    att.setncattr(
        "Catchment_source",
        str(
            catchment_file
        )
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
    # Variable definitions
    # --------------------------------------------------------

    definitions = {

        "hruId": (
            "i4",
            ("hru",),
            "-",
            "Hydrological response unit identifier"
        ),

        "gruId": (
            "i4",
            ("gru",),
            "-",
            "Grouped response unit identifier"
        ),

        "hru2gruId": (
            "i4",
            ("hru",),
            "-",
            "GRU identifier containing each HRU"
        ),

        "downHRUindex": (
            "i4",
            ("hru",),
            "-",
            "Index of downslope HRU; 0 means no downslope HRU"
        ),

        "longitude": (
            "f8",
            ("hru",),
            "degrees_east",
            "Longitude of HRU centroid"
        ),

        "latitude": (
            "f8",
            ("hru",),
            "degrees_north",
            "Latitude of HRU centroid"
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
            "Index defining slope type"
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
            "Forcing measurement height above ground"
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
    # IDs and spatial attributes
    # --------------------------------------------------------

    att[
        "hruId"
    ][:] = hru_ids.astype(
        np.int32
    )


    att[
        "gruId"
    ][:] = gru_ids.astype(
        np.int32
    )


    att[
        "hru2gruId"
    ][:] = hru_to_gru.astype(
        np.int32
    )


    att[
        "HRUarea"
    ][:] = areas


    att[
        "latitude"
    ][:] = latitudes


    att[
        "longitude"
    ][:] = longitudes


    # --------------------------------------------------------
    # Current workflow constants
    # --------------------------------------------------------

    # Default independent-HRU configuration.
    #
    # If settings_summa_connect_HRUs = yes, script 2c may
    # subsequently replace these values.

    att[
        "downHRUindex"
    ][:] = 0


    att[
        "tan_slope"
    ][:] = 0.1


    att[
        "contourLength"
    ][:] = 30.0


    att[
        "slopeTypeIndex"
    ][:] = 1


    att[
        "mHeight"
    ][:] = forcing_measurement_height


    # --------------------------------------------------------
    # Placeholders populated by 2a / 2b / 2c
    # --------------------------------------------------------

    att[
        "elevation"
    ][:] = -999.0


    att[
        "soilTypeIndex"
    ][:] = -999


    att[
        "vegTypeIndex"
    ][:] = -999


# ============================================================
# VERIFY SAVED OUTPUT
# ============================================================

with xr.open_dataset(
    attribute_file
) as saved:

    # --------------------------------------------------------
    # Dimensions
    # --------------------------------------------------------

    if saved.sizes.get(
        "hru"
    ) != num_hru:

        raise RuntimeError(
            "attributes.nc has incorrect HRU count."
        )


    if saved.sizes.get(
        "gru"
    ) != num_gru:

        raise RuntimeError(
            "attributes.nc has incorrect GRU count."
        )


    # --------------------------------------------------------
    # Required variables
    # --------------------------------------------------------

    required_variables = list(
        definitions.keys()
    )


    missing_variables = [
        name
        for name in required_variables
        if name not in saved
    ]


    if missing_variables:

        raise RuntimeError(
            "attributes.nc is missing required "
            "variable(s):\n"
            + "\n".join(
                f"  {name}"
                for name in missing_variables
            )
        )


    # --------------------------------------------------------
    # HRU order
    # --------------------------------------------------------

    output_hru_ids = (
        saved[
            "hruId"
        ]
        .values
        .astype(np.int64)
    )


    if not np.array_equal(
        output_hru_ids,
        forcing_hru_ids
    ):

        raise RuntimeError(
            "attributes.nc HRU order does not "
            "match SUMMA forcing."
        )


    # --------------------------------------------------------
    # GRU mapping
    # --------------------------------------------------------

    output_hru_to_gru = (
        saved[
            "hru2gruId"
        ]
        .values
        .astype(np.int64)
    )


    if not np.array_equal(
        output_hru_to_gru,
        hru_to_gru
    ):

        raise RuntimeError(
            "attributes.nc hru2gruId does "
            "not match the prepared catchment."
        )


    output_gru_ids = (
        saved[
            "gruId"
        ]
        .values
        .astype(np.int64)
    )


    if not np.array_equal(
        output_gru_ids,
        gru_ids
    ):

        raise RuntimeError(
            "attributes.nc gruId validation failed."
        )


    # --------------------------------------------------------
    # Numeric attributes
    # --------------------------------------------------------

    if not np.allclose(
        saved[
            "HRUarea"
        ].values,
        areas
    ):

        raise RuntimeError(
            "attributes.nc HRUarea validation failed."
        )


    if not np.allclose(
        saved[
            "latitude"
        ].values,
        latitudes
    ):

        raise RuntimeError(
            "attributes.nc latitude validation failed."
        )


    if not np.allclose(
        saved[
            "longitude"
        ].values,
        longitudes
    ):

        raise RuntimeError(
            "attributes.nc longitude validation failed."
        )


    # --------------------------------------------------------
    # Expected initial values
    # --------------------------------------------------------

    if np.count_nonzero(
        saved[
            "downHRUindex"
        ].values
    ) != 0:

        raise RuntimeError(
            "downHRUindex was expected to "
            "initialize entirely to zero."
        )


    if not np.all(
        saved[
            "soilTypeIndex"
        ].values
        == -999
    ):

        raise RuntimeError(
            "soilTypeIndex placeholders were "
            "not initialized correctly."
        )


    if not np.all(
        saved[
            "vegTypeIndex"
        ].values
        == -999
    ):

        raise RuntimeError(
            "vegTypeIndex placeholders were "
            "not initialized correctly."
        )


    if not np.all(
        saved[
            "elevation"
        ].values
        == -999.0
    ):

        raise RuntimeError(
            "elevation placeholders were "
            "not initialized correctly."
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


this_file = Path(
    __file__
).name


copy2(
    Path(
        __file__
    ).resolve(),
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
        "initialize_summa_attributes.txt"
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
        f"Forcing template: {forcing_file}\n"
    )

    file.write(
        f"HRUs: {num_hru}\n"
    )

    file.write(
        f"GRUs: {num_gru}\n"
    )

    file.write(
        f"First HRU ID: {hru_ids[0]}\n"
    )

    file.write(
        f"Last HRU ID: {hru_ids[-1]}\n"
    )

    file.write(
        f"Measurement height: "
        f"{forcing_measurement_height:g} m\n"
    )

    file.write(
        f"Output: {attribute_file}\n"
    )

    file.write(
        "Initial downHRUindex: all zero\n"
    )

    file.write(
        "Initial elevation: -999\n"
    )

    file.write(
        "Initial soilTypeIndex: -999\n"
    )

    file.write(
        "Initial vegTypeIndex: -999\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("SUMMA ATTRIBUTES INITIALIZATION COMPLETED")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"HRUs             : {num_hru}"
)

print(
    f"GRUs             : {num_gru}"
)

print(
    "HRU order        : matches SUMMA forcing"
)

print(
    "downHRUindex     : all 0"
)

print(
    "elevation        : initialized to -999"
)

print(
    "soilTypeIndex    : initialized to -999"
)

print(
    "vegTypeIndex     : initialized to -999"
)

print(
    f"Output           : {attribute_file}"
)

print(
    f"Workflow log     : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)