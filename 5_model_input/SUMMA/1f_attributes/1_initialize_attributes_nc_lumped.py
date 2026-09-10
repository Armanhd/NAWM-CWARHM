#!/usr/bin/env python3
# coding: utf-8

"""
Initialize SUMMA attributes.nc for a one-HRU lumped NWAM basin.

Purpose
-------
Create the base SUMMA attributes.nc using:

    - HRU ordering from the first final lumped SUMMA forcing file
    - the one-HRU lumped catchment shapefile
    - domain-specific lumped control-file paths

Expected lumped structure
-------------------------
The catchment must contain exactly:

    1 HRU
    1 GRU
    HRU_ID = 1
    GRU_ID = 1

The generated attributes.nc initially contains:

    hruId          = 1
    gruId          = 1
    hru2gruId      = 1
    downHRUindex   = 0
    elevation      = -999
    soilTypeIndex  = -999
    vegTypeIndex   = -999

The placeholders are populated later by:

    2a_insert_soilclass_from_hist_into_attributes.py
    2b_insert_landclass_from_hist_into_attributes.py
    2c_insert_elevation_into_attributes.py

IMPORTANT
---------
This script:

    - uses the supplied control_<DOMAIN>_lumped.txt
    - does NOT use control_active.txt
    - does NOT modify the distributed catchment
    - writes only to the lumped SUMMA settings directory

Usage
-----
python 1_initialize_attributes_nc_lumped.py \
    /path/to/control_DOMAIN_lumped.txt
"""

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
        "python 1_initialize_attributes_nc_lumped.py "
        "/path/to/control_DOMAIN_lumped.txt"
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
    Construct the ordinary physical domain path:

        <root_path>/domain_<domain_name>/<suffix>

    This is retained only as a fallback for settings that are
    not explicitly redirected by the lumped control file.
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
    Resolve a control-file path.

    For lumped controls, important paths such as:

        catchment_shp_path
        forcing_summa_path
        settings_summa_path

    should explicitly point to domain_<DOMAIN>/lumped/.
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

    values = np.asarray(
        values
    ).reshape(-1)


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


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# LUMPED CATCHMENT
# ============================================================

root_path = Path(
    read_from_control(
        CONTROL_FILE,
        "root_path"
    )
)

domain_root = (
    root_path
    / f"domain_{domain_name}"
)

catchment_file = (
    domain_root
    / "lumped"
    / "shapefiles"
    / "catchment"
    / f"{domain_name}_lumped_basin.shp"
)


# Keep field names from the control file.

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
        "Lumped catchment shapefile not found:\n"
        f"{catchment_file}"
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
        "Lumped SUMMA forcing directory not found:\n"
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
        "Run 1_create_forcing_file_list.py first."
    )


with open(
    forcing_list_file
) as file:

    forcing_names = [
        line.strip()
        for line in file
        if (
            line.strip()
            and not line.lstrip().startswith("#")
        )
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
        "First SUMMA forcing file does not exist:\n"
        f"{forcing_file}"
    )


# ============================================================
# READ HRU ORDER FROM LUMPED FORCING
# ============================================================

with xr.open_dataset(
    forcing_file
) as forcing:

    if "hru" not in forcing.dims:

        raise RuntimeError(
            "Lumped forcing file does not contain "
            "an 'hru' dimension."
        )


    if "hruId" not in forcing:

        raise RuntimeError(
            "hruId not found in lumped forcing."
        )


    forcing_hru_ids = convert_integer_ids(
        forcing[
            "hruId"
        ].values,
        "Forcing hruId"
    )


    forcing_hru_count = (
        forcing.sizes["hru"]
    )


if forcing_hru_count != 1:

    raise RuntimeError(
        "Lumped SUMMA forcing must contain exactly 1 HRU.\n"
        f"Found: {forcing_hru_count}"
    )


if len(
    forcing_hru_ids
) != 1:

    raise RuntimeError(
        "Lumped forcing must contain exactly one hruId."
    )


if int(
    forcing_hru_ids[0]
) != 1:

    raise RuntimeError(
        "Lumped forcing hruId must equal 1.\n"
        f"Found: {forcing_hru_ids.tolist()}"
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


if (
    not np.isfinite(
        forcing_measurement_height
    )
    or forcing_measurement_height < 0
):

    raise ValueError(
        "forcing_measurement_height must be finite "
        "and non-negative."
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
# READ LUMPED CATCHMENT
# ============================================================

shp = gpd.read_file(
    catchment_file,
    engine="fiona"
)


if len(shp) != 1:

    raise RuntimeError(
        "Lumped catchment must contain exactly 1 feature.\n"
        f"Found: {len(shp)}"
    )


if shp.crs is None:

    raise RuntimeError(
        "Lumped catchment has no CRS:\n"
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
        "Lumped catchment is missing required fields:\n"
        + "\n".join(
            f"  {field}"
            for field in missing_fields
        )
    )


# ============================================================
# VALIDATE CATCHMENT FIELDS
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
    ].values,
    hru_field
)


catchment_gru_ids = convert_integer_ids(
    shp[
        gru_field
    ].values,
    gru_field
)


if int(
    catchment_hru_ids[0]
) != 1:

    raise RuntimeError(
        "Lumped catchment HRU_ID must equal 1.\n"
        f"Found: {catchment_hru_ids.tolist()}"
    )


if int(
    catchment_gru_ids[0]
) != 1:

    raise RuntimeError(
        "Lumped catchment GRU_ID must equal 1.\n"
        f"Found: {catchment_gru_ids.tolist()}"
    )


if not np.array_equal(
    forcing_hru_ids,
    catchment_hru_ids
):

    raise RuntimeError(
        "Lumped catchment HRU ID does not match "
        "lumped SUMMA forcing.\n\n"
        f"Forcing: {forcing_hru_ids.tolist()}\n"
        f"Shape  : {catchment_hru_ids.tolist()}"
    )


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


if (
    not np.all(
        np.isfinite(
            areas
        )
    )
    or np.any(
        areas <= 0
    )
):

    raise RuntimeError(
        "Lumped HRU area must be finite "
        "and greater than zero."
    )


if not np.all(
    np.isfinite(
        latitudes
    )
):

    raise RuntimeError(
        "Invalid lumped HRU latitude."
    )


if not np.all(
    np.isfinite(
        longitudes
    )
):

    raise RuntimeError(
        "Invalid lumped HRU longitude."
    )


if (
    latitudes[0] < -90
    or latitudes[0] > 90
):

    raise RuntimeError(
        "Invalid latitude value."
    )


if (
    longitudes[0] < -180
    or longitudes[0] > 180
):

    raise RuntimeError(
        "Invalid longitude value."
    )


# ============================================================
# AUTHORITATIVE LUMPED IDS
# ============================================================

hru_ids = np.asarray(
    [1],
    dtype=np.int32
)


gru_ids = np.asarray(
    [1],
    dtype=np.int32
)


hru_to_gru = np.asarray(
    [1],
    dtype=np.int32
)


downstream_index = np.asarray(
    [0],
    dtype=np.int32
)


num_hru = 1
num_gru = 1


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("INITIALIZE LUMPED SUMMA ATTRIBUTES")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"Lumped catchment : {catchment_file}"
)

print(
    f"Forcing template : {forcing_file}"
)

print(
    f"Settings path    : {settings_path}"
)

print(
    f"HRUs             : {num_hru}"
)

print(
    f"GRUs             : {num_gru}"
)

print(
    f"hruId            : {hru_ids[0]}"
)

print(
    f"gruId            : {gru_ids[0]}"
)

print(
    f"HRU area         : {areas[0]:.3f} m2"
)

print(
    f"Latitude         : {latitudes[0]:.6f}"
)

print(
    f"Longitude        : {longitudes[0]:.6f}"
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

with nc4.Dataset(
    attribute_file,
    "w",
    format="NETCDF4"
) as att:

    now = datetime.now()


    # --------------------------------------------------------
    # GLOBAL ATTRIBUTES
    # --------------------------------------------------------

    att.setncattr(
        "Author",
        "NWAM-SUMMA lumped workflow"
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
        "SUMMA lumped HRU and GRU attributes"
    )

    att.setncattr(
        "Domain",
        domain_name
    )

    att.setncattr(
        "Configuration",
        "one-HRU lumped basin"
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
    # DIMENSIONS
    # --------------------------------------------------------

    att.createDimension(
        "hru",
        1
    )

    att.createDimension(
        "gru",
        1
    )


    # --------------------------------------------------------
    # VARIABLES
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
    # IDS
    # --------------------------------------------------------

    att[
        "hruId"
    ][:] = hru_ids


    att[
        "gruId"
    ][:] = gru_ids


    att[
        "hru2gruId"
    ][:] = hru_to_gru


    att[
        "downHRUindex"
    ][:] = downstream_index


    # --------------------------------------------------------
    # SPATIAL ATTRIBUTES
    # --------------------------------------------------------

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
    # CURRENT SUMMA WORKFLOW CONSTANTS
    # --------------------------------------------------------

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
    # PLACEHOLDERS
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
# VERIFY OUTPUT
# ============================================================

with xr.open_dataset(
    attribute_file
) as saved:

    if saved.sizes.get(
        "hru"
    ) != 1:

        raise RuntimeError(
            "Lumped attributes.nc must have hru=1."
        )


    if saved.sizes.get(
        "gru"
    ) != 1:

        raise RuntimeError(
            "Lumped attributes.nc must have gru=1."
        )


    required_variables = [
        "hruId",
        "gruId",
        "hru2gruId",
        "downHRUindex",
        "longitude",
        "latitude",
        "elevation",
        "HRUarea",
        "tan_slope",
        "contourLength",
        "slopeTypeIndex",
        "soilTypeIndex",
        "vegTypeIndex",
        "mHeight",
    ]


    missing_variables = [
        name
        for name in required_variables
        if name not in saved
    ]


    if missing_variables:

        raise RuntimeError(
            "Lumped attributes.nc is missing variables:\n"
            + "\n".join(
                f"  {name}"
                for name in missing_variables
            )
        )


    output_hru = int(
        saved[
            "hruId"
        ].values[0]
    )


    output_gru = int(
        saved[
            "gruId"
        ].values[0]
    )


    output_hru_to_gru = int(
        saved[
            "hru2gruId"
        ].values[0]
    )


    output_downstream = int(
        saved[
            "downHRUindex"
        ].values[0]
    )


    if output_hru != 1:

        raise RuntimeError(
            f"Expected hruId=1, found {output_hru}."
        )


    if output_gru != 1:

        raise RuntimeError(
            f"Expected gruId=1, found {output_gru}."
        )


    if output_hru_to_gru != 1:

        raise RuntimeError(
            "Expected hru2gruId=1."
        )


    if output_downstream != 0:

        raise RuntimeError(
            "A one-HRU lumped basin must have "
            "downHRUindex=0."
        )


    if not np.isclose(
        float(
            saved[
                "HRUarea"
            ].values[0]
        ),
        float(
            areas[0]
        )
    ):

        raise RuntimeError(
            "HRUarea validation failed."
        )


    if int(
        saved[
            "soilTypeIndex"
        ].values[0]
    ) != -999:

        raise RuntimeError(
            "soilTypeIndex placeholder should be -999."
        )


    if int(
        saved[
            "vegTypeIndex"
        ].values[0]
    ) != -999:

        raise RuntimeError(
            "vegTypeIndex placeholder should be -999."
        )


    if not np.isclose(
        float(
            saved[
                "elevation"
            ].values[0]
        ),
        -999.0
    ):

        raise RuntimeError(
            "elevation placeholder should be -999."
        )


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    settings_path
    / "_workflow_log"
)


log_folder.mkdir(
    parents=True,
    exist_ok=True
)


copy2(
    Path(
        __file__
    ).resolve(),
    log_folder
    / Path(
        __file__
    ).name
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
        "initialize_lumped_summa_attributes.txt"
    )
)


with open(
    log_file,
    "w"
) as file:

    file.write(
        f"Created: {now:%Y-%m-%d %H:%M:%S}\n"
    )

    file.write(
        f"Domain: {domain_name}\n"
    )

    file.write(
        f"Control file: {CONTROL_FILE}\n"
    )

    file.write(
        f"Lumped catchment: {catchment_file}\n"
    )

    file.write(
        f"Forcing template: {forcing_file}\n"
    )

    file.write(
        "HRUs: 1\n"
    )

    file.write(
        "GRUs: 1\n"
    )

    file.write(
        "hruId: 1\n"
    )

    file.write(
        "gruId: 1\n"
    )

    file.write(
        "hru2gruId: 1\n"
    )

    file.write(
        "downHRUindex: 0\n"
    )

    file.write(
        f"HRU area: {areas[0]:.6f} m2\n"
    )

    file.write(
        f"Output: {attribute_file}\n"
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
print("LUMPED SUMMA ATTRIBUTES INITIALIZATION COMPLETED")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"HRUs             : {num_hru}"
)

print(
    f"GRUs             : {num_gru}"
)

print(
    "hruId            : 1"
)

print(
    "gruId            : 1"
)

print(
    "hru2gruId        : 1"
)

print(
    "downHRUindex     : 0"
)

print(
    "elevation        : -999 placeholder"
)

print(
    "soilTypeIndex    : -999 placeholder"
)

print(
    "vegTypeIndex     : -999 placeholder"
)

print(
    f"Output           : {attribute_file}"
)

print(
    f"Workflow log     : {log_file}"
)

print()
print(
    f"PASS: {domain_name} lumped attributes initialization"
)

print()
print(
    "No control_active.txt was created or modified."
)