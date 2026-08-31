#!/usr/bin/env python3
# coding: utf-8

# Insert dominant soil class into SUMMA attributes.nc.
#
# The Stage-4b soil-processing workflow creates categorical
# soil-pixel counts for each HRU in fields named USGS_<class>.
#
# Selection rules:
#   1. Soil class 0 is excluded from SUMMA soilTypeIndex.
#   2. If valid non-zero soil pixels exist, use the dominant class.
#   3. Exact ties are resolved using the lower class number.
#   4. If no valid non-zero soil pixels exist, use soil class 1
#      as the explicit fallback.
#
# The fallback reproduces the effective behaviour of the original
# CWARHM workflow while making the assumption explicit and traceable.
#
# attributes.nc is authoritative for HRU order.
#
# This script does NOT read or modify control_active.txt.
#
# Usage:
#
# python 2a_insert_soilclass_from_hist_into_attributes.py \
#     /path/to/control_DOMAIN.txt

import sys
import re
from pathlib import Path
from datetime import datetime
from shutil import copy2

import geopandas as gpd
import netCDF4 as nc4
import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

FALLBACK_SOIL_CLASS = 1


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 2a_insert_soilclass_from_hist_into_attributes.py "
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
    Validate IDs and return int64 values.
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
# SOIL-INTERSECTION INPUT
# ============================================================

intersect_path = resolve_path(
    "intersect_soil_path",
    "shapefiles/catchment_intersection/with_soilgrids"
)


intersect_name = read_from_control(
    CONTROL_FILE,
    "intersect_soil_name"
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
# HRU FIELD
# ============================================================

hru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)


# ============================================================
# VALIDATE INPUTS
# ============================================================

if not intersect_file.exists():

    raise FileNotFoundError(
        "Soil-intersection shapefile not found:\n"
        f"{intersect_file}\n\n"
        "Run 2_find_HRU_soil_classes.py first."
    )


if not attribute_file.exists():

    raise FileNotFoundError(
        "SUMMA attributes.nc not found:\n"
        f"{attribute_file}\n\n"
        "Run 1_initialize_attributes_nc.py first."
    )


# ============================================================
# READ SOIL HISTOGRAM
# ============================================================

shp = gpd.read_file(
    intersect_file,
    engine="fiona"
)


if len(shp) == 0:

    raise RuntimeError(
        "Soil-intersection shapefile contains no HRUs."
    )


if hru_field not in shp.columns:

    raise RuntimeError(
        f"Configured HRU field '{hru_field}' "
        "not found in soil-intersection shapefile."
    )


# ============================================================
# VALIDATE HRU IDs
# ============================================================

soil_hru_ids = convert_integer_ids(
    shp[
        hru_field
    ],
    hru_field
)


if len(
    np.unique(
        soil_hru_ids
    )
) != len(
    soil_hru_ids
):

    raise RuntimeError(
        f"Duplicate {hru_field} values found "
        "in soil-intersection shapefile."
    )


shp[
    hru_field
] = soil_hru_ids


# ============================================================
# DETECT USGS HISTOGRAM FIELDS
# ============================================================

class_fields = {}

pattern = re.compile(
    r"^USGS_(\d+)$"
)


for column in shp.columns:

    match = pattern.match(
        str(
            column
        )
    )

    if not match:
        continue

    soil_class = int(
        match.group(1)
    )

    if soil_class in class_fields:

        raise RuntimeError(
            f"Duplicate soil-class field detected "
            f"for class {soil_class}."
        )

    class_fields[
        soil_class
    ] = column


if not class_fields:

    raise RuntimeError(
        "No USGS_<class> histogram fields were "
        "found in the soil-intersection shapefile."
    )


all_classes = sorted(
    class_fields
)


# Soil class 0 represents unclassified/no-soil and is never
# written directly to SUMMA soilTypeIndex.

valid_classes = [
    soil_class
    for soil_class in all_classes
    if soil_class != 0
]


# A domain may legitimately contain only class 0, for example
# permanent snow/ice areas. This is not treated as an error.
# Such HRUs receive FALLBACK_SOIL_CLASS below.


# ============================================================
# VALIDATE HISTOGRAM FIELDS
# ============================================================

for soil_class in all_classes:

    field = class_fields[
        soil_class
    ]

    try:

        values = pd.to_numeric(
            shp[field],
            errors="raise"
        ).to_numpy(
            dtype=np.float64
        )

    except Exception as exc:

        raise RuntimeError(
            f"Soil histogram field '{field}' "
            "contains non-numeric values."
        ) from exc


    finite_values = values[
        np.isfinite(
            values
        )
    ]


    if np.any(
        finite_values < 0
    ):

        raise RuntimeError(
            f"Soil histogram field '{field}' "
            "contains negative pixel counts."
        )


# ============================================================
# READ attributes.nc HRU ORDER
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r"
) as att:

    required_variables = [
        "hruId",
        "soilTypeIndex",
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


if attribute_hrus.ndim != 1:

    raise RuntimeError(
        "attributes.nc hruId must be one-dimensional."
    )


if len(
    np.unique(
        attribute_hrus
    )
) != len(
    attribute_hrus
):

    raise RuntimeError(
        "Duplicate hruId values found in attributes.nc."
    )


# ============================================================
# COMPARE HRU SETS
# ============================================================

soil_hru_set = set(
    soil_hru_ids.tolist()
)


attribute_hru_set = set(
    attribute_hrus.tolist()
)


missing_from_soil = sorted(
    attribute_hru_set
    - soil_hru_set
)


extra_in_soil = sorted(
    soil_hru_set
    - attribute_hru_set
)


if (
    missing_from_soil
    or extra_in_soil
):

    raise RuntimeError(
        "Soil-intersection and attributes.nc "
        "HRU sets differ.\n\n"
        f"Missing from soil intersection: "
        f"{missing_from_soil}\n"
        f"Extra in soil intersection   : "
        f"{extra_in_soil}"
    )


# ============================================================
# REORDER SOIL TABLE TO attributes.nc HRU ORDER
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
        "Could not reorder soil-intersection HRUs "
        "to match attributes.nc."
    )


# ============================================================
# SELECT DOMINANT SOIL CLASS
# ============================================================

selected_classes = np.empty(
    len(
        attribute_hrus
    ),
    dtype=np.int32
)


fallback_hrus = []


for index, hru in enumerate(
    attribute_hrus
):

    row = shp.iloc[
        index
    ]

    counts = []


    for soil_class in valid_classes:

        value = row[
            class_fields[
                soil_class
            ]
        ]

        try:

            value = float(
                value
            )

        except Exception as exc:

            raise RuntimeError(
                f"Invalid histogram value for "
                f"HRU {int(hru)}, "
                f"class {soil_class}."
            ) from exc


        if not np.isfinite(
            value
        ):

            value = 0.0


        if value < 0:

            raise RuntimeError(
                f"Negative soil histogram count "
                f"for HRU {int(hru)}, "
                f"class {soil_class}."
            )


        counts.append(
            value
        )


    counts = np.asarray(
        counts,
        dtype=np.float64
    )


    valid_total = float(
        counts.sum()
    )


    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------
    #
    # If no valid non-zero soil pixels exist, SUMMA still
    # requires a positive soilTypeIndex. Use the explicit
    # fallback class rather than allowing class 0 into SUMMA.

    if valid_total <= 0:

        selected_classes[
            index
        ] = FALLBACK_SOIL_CLASS

        fallback_hrus.append(
            int(hru)
        )

        continue


    # valid_classes is sorted in ascending order.
    # np.argmax returns the first maximum, so exact ties
    # select the lowest soil-class number.

    dominant_index = int(
        np.argmax(
            counts
        )
    )


    selected_classes[
        index
    ] = int(
        valid_classes[
            dominant_index
        ]
    )


# ============================================================
# SUMMARY BEFORE WRITING
# ============================================================

selected_unique = sorted(
    np.unique(
        selected_classes
    ).astype(int).tolist()
)


normal_count = (
    len(attribute_hrus)
    - len(fallback_hrus)
)


print()
print("=" * 70)
print("INSERT SOIL CLASS INTO SUMMA ATTRIBUTES")
print("=" * 70)

print(
    f"Domain               : {domain_name}"
)

print(
    f"HRUs                 : {len(attribute_hrus)}"
)

print(
    f"Histogram classes    : {all_classes}"
)

print(
    f"Selected classes     : {selected_unique}"
)

print(
    f"Normal assignments   : {normal_count}"
)

print(
    f"Fallback assignments : {len(fallback_hrus)}"
)

print(
    f"Fallback soil class  : {FALLBACK_SOIL_CLASS}"
)


# ============================================================
# WRITE soilTypeIndex
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r+"
) as att:

    att[
        "soilTypeIndex"
    ][:] = selected_classes


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

    output_soil = np.asarray(
        att[
            "soilTypeIndex"
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


if not np.array_equal(
    output_soil,
    selected_classes.astype(
        np.int64
    )
):

    raise RuntimeError(
        "Saved soilTypeIndex values do not match "
        "the calculated soil classes."
    )


if np.any(
    output_soil <= 0
):

    raise RuntimeError(
        "Invalid soilTypeIndex values remain "
        "in attributes.nc."
    )


allowed_output_classes = set(
    valid_classes
)

allowed_output_classes.add(
    FALLBACK_SOIL_CLASS
)


unexpected_classes = sorted(
    set(
        output_soil.tolist()
    )
    - allowed_output_classes
)


if unexpected_classes:

    raise RuntimeError(
        "Unexpected soilTypeIndex classes were "
        "written to attributes.nc:\n"
        f"{unexpected_classes}"
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
        "insert_summa_soilclass.txt"
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
        f"HRUs processed: {len(attribute_hrus)}\n"
    )

    file.write(
        f"Histogram classes: {all_classes}\n"
    )

    file.write(
        f"Selected soil classes: {selected_unique}\n"
    )

    file.write(
        f"Fallback soil class: {FALLBACK_SOIL_CLASS}\n"
    )

    file.write(
        f"Normal assignments: {normal_count}\n"
    )

    file.write(
        f"Fallback assignments: {len(fallback_hrus)}\n"
    )

    if fallback_hrus:

        file.write(
            f"Fallback HRUs: {fallback_hrus}\n"
        )


# ============================================================
# FINISH
# ============================================================

print()
print(
    "SUMMA soil-class insertion completed successfully."
)