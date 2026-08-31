#!/usr/bin/env python3
# coding: utf-8

# Insert MERIT-Hydro mean HRU elevation into SUMMA attributes.nc.
#
# Purpose
# -------
# Stage 4b creates a DEM-intersection shapefile containing:
#
#     elev_mean
#
# for every prepared CWARHM HRU.
#
# This script:
#
#   - reads the domain-specific control file supplied on the
#     command line
#   - reads HRU mean elevation from the DEM-intersection shapefile
#   - uses attributes.nc as the authoritative HRU order
#   - validates HRU and GRU consistency
#   - inserts elevation into attributes.nc
#   - optionally calculates downHRUindex when
#     settings_summa_connect_HRUs = yes
#   - verifies the completed elevation and connectivity fields
#
# HRU connectivity
# ------------------------------------------------------------
# If:
#
#     settings_summa_connect_HRUs | no
#
# every downHRUindex remains 0.
#
# If:
#
#     settings_summa_connect_HRUs | yes
#
# HRUs within each GRU are connected from higher elevation to
# lower elevation. The lowest-elevation HRU in each GRU has
# downHRUindex = 0.
#
# IMPORTANT
# ---------
# downHRUindex is a one-based HRU POSITION in attributes.nc,
# not an hruId.
#
# This script does NOT read or modify control_active.txt.
#
# Usage
# -----
#
# python 2c_insert_elevation_into_attributes.py \
#     /path/to/control_DOMAIN.txt

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

import geopandas as gpd
import netCDF4 as nc4
import numpy as np
import pandas as pd


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 2c_insert_elevation_into_attributes.py "
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
    Validate numeric integer IDs and return int64 array.
    """

    try:

        numeric = pd.to_numeric(
            values,
            errors="raise"
        ).to_numpy(
            dtype=np.float64
        )

    except Exception as exc:

        raise RuntimeError(
            f"{name} contains non-numeric values."
        ) from exc


    if not np.all(
        np.isfinite(
            numeric
        )
    ):

        raise RuntimeError(
            f"{name} contains non-finite values."
        )


    if not np.allclose(
        numeric,
        np.round(
            numeric
        )
    ):

        raise RuntimeError(
            f"{name} contains non-integer values."
        )


    return (
        np.round(
            numeric
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
# DEM INTERSECTION INPUT
# ============================================================

intersect_path = resolve_path(
    "intersect_dem_path",
    "shapefiles/catchment_intersection/with_dem"
)


intersect_name = read_from_control(
    CONTROL_FILE,
    "intersect_dem_name"
)


intersect_file = (
    intersect_path
    / intersect_name
)


# ============================================================
# SUMMA ATTRIBUTES
# ============================================================

settings_path = resolve_path(
    "settings_summa_path",
    "settings/SUMMA"
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
# HRU / GRU SETTINGS
# ============================================================

hru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)


gru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_gruid"
)


connect_hrus = (
    read_from_control(
        CONTROL_FILE,
        "settings_summa_connect_HRUs"
    )
    .strip()
    .lower()
)


if connect_hrus not in [
    "yes",
    "no"
]:

    raise ValueError(
        "settings_summa_connect_HRUs "
        "must be either 'yes' or 'no'."
    )


# ============================================================
# VALIDATE FILES
# ============================================================

if not intersect_file.exists():

    raise FileNotFoundError(
        "DEM-intersection shapefile not found:\n"
        f"{intersect_file}\n\n"
        "Run 1_find_HRU_elevation.py first."
    )


if not attribute_file.exists():

    raise FileNotFoundError(
        "SUMMA attributes.nc not found:\n"
        f"{attribute_file}\n\n"
        "Run 1_initialize_attributes_nc.py first."
    )


# ============================================================
# READ ELEVATION SHAPEFILE
# ============================================================

shp = gpd.read_file(
    intersect_file,
    engine="fiona"
)


if len(shp) == 0:

    raise RuntimeError(
        "DEM-intersection shapefile contains no HRUs."
    )


required_fields = [
    hru_field,
    gru_field,
    "elev_mean",
]


missing_fields = [
    field
    for field in required_fields
    if field not in shp.columns
]


if missing_fields:

    raise RuntimeError(
        "DEM-intersection shapefile is missing "
        "required field(s):\n"
        + "\n".join(
            f"  {field}"
            for field in missing_fields
        )
    )


# ============================================================
# VALIDATE HRU / GRU IDS
# ============================================================

shp[
    hru_field
] = convert_integer_ids(
    shp[
        hru_field
    ],
    hru_field
)


shp[
    gru_field
] = convert_integer_ids(
    shp[
        gru_field
    ],
    gru_field
)


if shp[
    hru_field
].duplicated().any():

    raise RuntimeError(
        f"Duplicate {hru_field} values found "
        "in DEM-intersection shapefile."
    )


# ============================================================
# VALIDATE ELEVATION
# ============================================================

try:

    elevation_values = pd.to_numeric(
        shp[
            "elev_mean"
        ],
        errors="raise"
    ).to_numpy(
        dtype=np.float64
    )

except Exception as exc:

    raise RuntimeError(
        "elev_mean contains non-numeric values."
    ) from exc


if not np.all(
    np.isfinite(
        elevation_values
    )
):

    raise RuntimeError(
        "Non-finite elev_mean values found."
    )


shp[
    "elev_mean"
] = elevation_values


# ============================================================
# READ ATTRIBUTES ORDER
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r"
) as att:

    required_variables = [
        "hruId",
        "hru2gruId",
        "elevation",
        "downHRUindex",
    ]


    missing_variables = [
        variable
        for variable in required_variables
        if variable not in att.variables
    ]


    if missing_variables:

        raise RuntimeError(
            "attributes.nc is missing required "
            "variable(s):\n"
            + "\n".join(
                f"  {variable}"
                for variable in missing_variables
            )
        )


    attribute_hrus = np.asarray(
        att[
            "hruId"
        ][:],
        dtype=np.int64
    )


    attribute_grus = np.asarray(
        att[
            "hru2gruId"
        ][:],
        dtype=np.int64
    )


# ============================================================
# VALIDATE ATTRIBUTES DIMENSIONS
# ============================================================

if attribute_hrus.ndim != 1:

    raise RuntimeError(
        "attributes.nc hruId must be one-dimensional."
    )


if attribute_grus.ndim != 1:

    raise RuntimeError(
        "attributes.nc hru2gruId must be one-dimensional."
    )


num_hru = len(
    attribute_hrus
)


if len(
    attribute_grus
) != num_hru:

    raise RuntimeError(
        "hruId and hru2gruId lengths differ "
        "in attributes.nc."
    )


if len(
    np.unique(
        attribute_hrus
    )
) != num_hru:

    raise RuntimeError(
        "Duplicate hruId values found in attributes.nc."
    )


# ============================================================
# COMPARE HRU SETS
# ============================================================

shape_hru_set = set(
    shp[
        hru_field
    ].tolist()
)


attribute_hru_set = set(
    attribute_hrus.tolist()
)


missing_from_shape = sorted(
    attribute_hru_set
    - shape_hru_set
)


extra_in_shape = sorted(
    shape_hru_set
    - attribute_hru_set
)


if (
    missing_from_shape
    or extra_in_shape
):

    raise RuntimeError(
        "DEM-intersection and attributes.nc "
        "HRU sets differ.\n\n"
        f"Missing from DEM intersection: "
        f"{missing_from_shape}\n"
        f"Extra in DEM intersection   : "
        f"{extra_in_shape}"
    )


# ============================================================
# REORDER DEM TABLE TO ATTRIBUTES ORDER
# ============================================================

shp = shp.set_index(
    hru_field,
    drop=False
)


shp = shp.loc[
    attribute_hrus
].copy()


reordered_hrus = shp[
    hru_field
].to_numpy(
    dtype=np.int64
)


if not np.array_equal(
    reordered_hrus,
    attribute_hrus
):

    raise RuntimeError(
        "Could not reorder DEM-intersection HRUs "
        "to match attributes.nc."
    )


# ============================================================
# BUILD ELEVATION / GRU ARRAYS
# ============================================================

elevations = shp[
    "elev_mean"
].to_numpy(
    dtype=np.float64
)


shape_grus = shp[
    gru_field
].to_numpy(
    dtype=np.int64
)


if not np.array_equal(
    shape_grus,
    attribute_grus
):

    raise RuntimeError(
        "GRU assignments differ between "
        "attributes.nc and DEM-intersection shapefile."
    )


# ============================================================
# BUILD downHRUindex
# ============================================================

downstream_index = np.zeros(
    num_hru,
    dtype=np.int32
)


if connect_hrus == "yes":

    unique_grus = []

    for gru in attribute_grus:

        gru = int(
            gru
        )

        if gru not in unique_grus:

            unique_grus.append(
                gru
            )


    for gru in unique_grus:

        positions = np.where(
            attribute_grus
            == gru
        )[0]


        if len(
            positions
        ) == 1:

            downstream_index[
                positions[0]
            ] = 0

            continue


        gru_elevations = elevations[
            positions
        ]


        # Sort highest elevation -> lowest elevation.
        #
        # Primary key:
        #     descending elevation
        #
        # Tie-break:
        #     existing attributes.nc position
        #
        # This gives deterministic behavior when two HRUs
        # have identical mean elevation.

        order = np.lexsort(
            (
                positions,
                -gru_elevations,
            )
        )


        ordered_positions = positions[
            order
        ]


        for (
            current_position,
            downstream_position
        ) in zip(
            ordered_positions[:-1],
            ordered_positions[1:],
        ):

            # SUMMA downHRUindex is one-based.
            downstream_index[
                current_position
            ] = int(
                downstream_position
                + 1
            )


        # Lowest HRU is the GRU outlet.

        downstream_index[
            ordered_positions[-1]
        ] = 0


# ============================================================
# VALIDATE CONNECTIVITY
# ============================================================

for position, downstream in enumerate(
    downstream_index
):

    downstream = int(
        downstream
    )


    if downstream == 0:

        continue


    if (
        downstream < 1
        or downstream > num_hru
    ):

        raise RuntimeError(
            f"Invalid downHRUindex {downstream} "
            f"at HRU position {position + 1}."
        )


    downstream_position = (
        downstream
        - 1
    )


    if downstream_position == position:

        raise RuntimeError(
            f"HRU at position {position + 1} "
            "drains to itself."
        )


    if (
        attribute_grus[
            downstream_position
        ]
        != attribute_grus[
            position
        ]
    ):

        raise RuntimeError(
            "A downstream HRU crosses a GRU boundary."
        )


# ============================================================
# ADDITIONAL CONNECTIVITY VALIDATION
# ============================================================

if connect_hrus == "no":

    if np.any(
        downstream_index != 0
    ):

        raise RuntimeError(
            "settings_summa_connect_HRUs = no, "
            "but non-zero downHRUindex values "
            "were generated."
        )


# ============================================================
# REPORT BEFORE WRITING
# ============================================================

unique_grus = np.unique(
    attribute_grus
)


print()
print("=" * 70)
print("INSERT ELEVATION INTO SUMMA ATTRIBUTES")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"DEM intersection : {intersect_file}"
)

print(
    f"Attributes       : {attribute_file}"
)

print(
    f"HRUs             : {num_hru}"
)

print(
    f"GRUs             : {len(unique_grus)}"
)

print(
    f"Connect HRUs     : {connect_hrus}"
)

print(
    f"Elevation range  : "
    f"{elevations.min():.3f} - "
    f"{elevations.max():.3f} m"
)

print(
    f"Mean elevation   : "
    f"{elevations.mean():.3f} m"
)

print(
    f"Non-zero links   : "
    f"{np.count_nonzero(downstream_index)}"
)

print(
    "HRU order        : matched attributes.nc"
)


# ============================================================
# WRITE attributes.nc
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r+"
) as att:

    att[
        "elevation"
    ][:] = elevations


    # Explicitly overwrite downHRUindex on every run.
    #
    # This is important because a previous run may have used
    # settings_summa_connect_HRUs = yes.

    att[
        "downHRUindex"
    ][:] = downstream_index


# ============================================================
# VERIFY OUTPUT
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r"
) as att:

    output_hrus = np.asarray(
        att[
            "hruId"
        ][:],
        dtype=np.int64
    )


    output_elevation = np.asarray(
        att[
            "elevation"
        ][:],
        dtype=np.float64
    )


    output_downstream = np.asarray(
        att[
            "downHRUindex"
        ][:],
        dtype=np.int64
    )


if not np.array_equal(
    output_hrus,
    attribute_hrus
):

    raise RuntimeError(
        "attributes.nc HRU order changed unexpectedly."
    )


if not np.allclose(
    output_elevation,
    elevations
):

    raise RuntimeError(
        "Elevation verification failed."
    )


if not np.array_equal(
    output_downstream,
    downstream_index.astype(
        np.int64
    )
):

    raise RuntimeError(
        "downHRUindex verification failed."
    )


if not np.all(
    np.isfinite(
        output_elevation
    )
):

    raise RuntimeError(
        "Non-finite elevation values remain "
        "in attributes.nc."
    )


if np.any(
    output_elevation == -999
):

    raise RuntimeError(
        "-999 elevation placeholders remain "
        "in attributes.nc."
    )


if connect_hrus == "no":

    if np.count_nonzero(
        output_downstream
    ) != 0:

        raise RuntimeError(
            "settings_summa_connect_HRUs = no, "
            "but attributes.nc contains non-zero "
            "downHRUindex values."
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
        "insert_summa_elevation.txt"
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
        f"DEM intersection: {intersect_file}\n"
    )

    file.write(
        f"Attributes: {attribute_file}\n"
    )

    file.write(
        f"HRUs processed: {num_hru}\n"
    )

    file.write(
        f"GRUs: {len(unique_grus)}\n"
    )

    file.write(
        f"Connect HRUs: {connect_hrus}\n"
    )

    file.write(
        f"Elevation range: "
        f"{elevations.min():.3f} - "
        f"{elevations.max():.3f} m\n"
    )

    file.write(
        f"Mean elevation: "
        f"{elevations.mean():.3f} m\n"
    )

    file.write(
        f"Non-zero downHRUindex values: "
        f"{np.count_nonzero(downstream_index)}\n"
    )

    file.write(
        "HRU order source: attributes.nc\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("SUMMA ELEVATION INSERTION COMPLETED")
print("=" * 70)

print(
    f"Domain            : {domain_name}"
)

print(
    f"Control file      : {CONTROL_FILE}"
)

print(
    f"HRUs processed    : {num_hru}"
)

print(
    f"GRUs              : {len(unique_grus)}"
)

print(
    f"Elevation range   : "
    f"{output_elevation.min():.3f} - "
    f"{output_elevation.max():.3f} m"
)

print(
    f"Mean elevation    : "
    f"{output_elevation.mean():.3f} m"
)

print(
    f"Connect HRUs      : {connect_hrus}"
)

print(
    f"Non-zero downHRU  : "
    f"{np.count_nonzero(output_downstream)}"
)

print(
    "Elevation -999   : "
    f"{np.count_nonzero(output_elevation == -999)}"
)

print(
    f"Attributes        : {attribute_file}"
)

print(
    f"Workflow log      : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)