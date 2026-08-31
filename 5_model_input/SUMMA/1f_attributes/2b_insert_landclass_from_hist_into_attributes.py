#!/usr/bin/env python3
# coding: utf-8

# Insert dominant MODIS IGBP land class into SUMMA attributes.nc.
#
# Purpose
# -------
# The Stage-4b land-cover workflow creates one land-intersection
# shapefile containing categorical pixel counts for each HRU:
#
#     IGBP_<class>
#
# Examples:
#
#     IGBP_1
#     IGBP_3
#     IGBP_4
#     IGBP_5
#     IGBP_7
#     IGBP_8
#     IGBP_9
#     IGBP_10
#     IGBP_11
#     IGBP_13
#     IGBP_17
#
# This script:
#
#   - reads the domain-specific control file supplied on the
#     command line
#   - reads the land-class histogram shapefile
#   - detects available IGBP_<class> fields dynamically
#   - matches HRUs using the configured HRU-ID field
#   - follows attributes.nc HRU ordering exactly
#   - selects the dominant land-cover class
#   - treats IGBP 17 (open water) specially:
#
#       * if class 17 dominates but another land class exists,
#         the dominant non-water class is selected
#
#       * if an HRU contains only open water, class 17 is kept
#
#   - uses the lowest class number to break exact count ties
#   - verifies the completed vegTypeIndex field
#
# IMPORTANT
# ---------
# attributes.nc is authoritative for HRU order because its HRU
# order already follows the final SUMMA forcing.
#
# This script does NOT read or modify control_active.txt.
#
# Usage
# -----
#
# python 2b_insert_landclass_from_hist_into_attributes.py \
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
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 2b_insert_landclass_from_hist_into_attributes.py "
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
# LAND-INTERSECTION INPUT
# ============================================================

intersect_path = resolve_path(
    "intersect_land_path",
    "shapefiles/catchment_intersection/with_modis"
)


intersect_name = read_from_control(
    CONTROL_FILE,
    "intersect_land_name"
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
        "Land-intersection shapefile not found:\n"
        f"{intersect_file}\n\n"
        "Run 3_find_HRU_land_classes.py first."
    )


if not attribute_file.exists():

    raise FileNotFoundError(
        "SUMMA attributes.nc not found:\n"
        f"{attribute_file}\n\n"
        "Run 1_initialize_attributes_nc.py first."
    )


# ============================================================
# READ LAND HISTOGRAM
# ============================================================

shp = gpd.read_file(
    intersect_file,
    engine="fiona"
)


if len(shp) == 0:

    raise RuntimeError(
        "Land-intersection shapefile contains no HRUs."
    )


if hru_field not in shp.columns:

    raise RuntimeError(
        f"Configured HRU field '{hru_field}' "
        "not found in land-intersection shapefile."
    )


# ============================================================
# VALIDATE HRU IDs
# ============================================================

land_hru_ids = convert_integer_ids(
    shp[
        hru_field
    ],
    hru_field
)


if len(
    np.unique(
        land_hru_ids
    )
) != len(
    land_hru_ids
):

    raise RuntimeError(
        f"Duplicate {hru_field} values found "
        "in land-intersection shapefile."
    )


shp[
    hru_field
] = land_hru_ids


# ============================================================
# DETECT IGBP HISTOGRAM FIELDS
# ============================================================

class_fields = {}


pattern = re.compile(
    r"^IGBP_(\d+)$"
)


for column in shp.columns:

    match = pattern.match(
        str(
            column
        )
    )

    if not match:
        continue


    land_class = int(
        match.group(1)
    )


    if land_class in class_fields:

        raise RuntimeError(
            f"Duplicate land-class field detected "
            f"for class {land_class}."
        )


    class_fields[
        land_class
    ] = column


if not class_fields:

    raise RuntimeError(
        "No IGBP_<class> histogram fields were "
        "found in the land-intersection shapefile."
    )


available_classes = sorted(
    class_fields
)


# ============================================================
# VALIDATE HISTOGRAM FIELDS
# ============================================================

for land_class in available_classes:

    field = class_fields[
        land_class
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
            f"Land histogram field '{field}' "
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
            f"Land histogram field '{field}' "
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
        "vegTypeIndex",
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

land_hru_set = set(
    land_hru_ids.tolist()
)


attribute_hru_set = set(
    attribute_hrus.tolist()
)


missing_from_land = sorted(
    attribute_hru_set
    - land_hru_set
)


extra_in_land = sorted(
    land_hru_set
    - attribute_hru_set
)


if (
    missing_from_land
    or extra_in_land
):

    raise RuntimeError(
        "Land-intersection and attributes.nc "
        "HRU sets differ.\n\n"
        f"Missing from land intersection: "
        f"{missing_from_land}\n"
        f"Extra in land intersection   : "
        f"{extra_in_land}"
    )


# ============================================================
# REORDER LAND TABLE TO attributes.nc HRU ORDER
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
        "Could not reorder land-intersection HRUs "
        "to match attributes.nc."
    )


# ============================================================
# SELECT DOMINANT LAND CLASS
# ============================================================

selected_classes = np.empty(
    len(
        attribute_hrus
    ),
    dtype=np.int32
)


water_only_hrus = []


for index, hru in enumerate(
    attribute_hrus
):

    row = shp.iloc[
        index
    ]


    counts_by_class = {}


    for land_class in available_classes:

        value = row[
            class_fields[
                land_class
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
                f"class {land_class}."
            ) from exc


        if not np.isfinite(
            value
        ):

            value = 0.0


        if value < 0:

            raise RuntimeError(
                f"Negative land histogram count "
                f"for HRU {int(hru)}, "
                f"class {land_class}."
            )


        counts_by_class[
            land_class
        ] = value


    total_count = float(
        sum(
            counts_by_class.values()
        )
    )


    if total_count <= 0:

        raise RuntimeError(
            f"HRU {int(hru)} has no valid "
            "land-cover pixels."
        )


    # --------------------------------------------------------
    # Initial dominant class
    # --------------------------------------------------------
    #
    # available_classes is sorted ascending.
    # np.argmax returns the first maximum, therefore ties are
    # deterministically resolved toward the lowest IGBP class.

    class_array = np.asarray(
        available_classes,
        dtype=np.int64
    )


    count_array = np.asarray(
        [
            counts_by_class[
                land_class
            ]
            for land_class in available_classes
        ],
        dtype=np.float64
    )


    dominant_class = int(
        class_array[
            np.argmax(
                count_array
            )
        ]
    )


    # --------------------------------------------------------
    # OPEN-WATER HANDLING
    # --------------------------------------------------------

    if dominant_class == 17:

        non_water_classes = [
            land_class
            for land_class in available_classes
            if (
                land_class != 17
                and counts_by_class[
                    land_class
                ] > 0
            )
        ]


        if non_water_classes:

            # non_water_classes remains in ascending class order,
            # so an exact tie selects the lowest class number.

            non_water_counts = np.asarray(
                [
                    counts_by_class[
                        land_class
                    ]
                    for land_class
                    in non_water_classes
                ],
                dtype=np.float64
            )


            dominant_class = int(
                non_water_classes[
                    int(
                        np.argmax(
                            non_water_counts
                        )
                    )
                ]
            )


        else:

            water_only_hrus.append(
                int(
                    hru
                )
            )


    selected_classes[
        index
    ] = dominant_class


# ============================================================
# REPORT BEFORE WRITING
# ============================================================

selected_unique = sorted(
    np.unique(
        selected_classes
    ).astype(int).tolist()
)


print()
print("=" * 70)
print("INSERT LAND CLASS INTO SUMMA ATTRIBUTES")
print("=" * 70)

print(
    f"Domain            : {domain_name}"
)

print(
    f"Control file      : {CONTROL_FILE}"
)

print(
    f"Land intersection : {intersect_file}"
)

print(
    f"Attributes        : {attribute_file}"
)

print(
    f"HRU field         : {hru_field}"
)

print(
    f"HRUs              : {len(attribute_hrus)}"
)

print(
    f"Available classes : {available_classes}"
)

print(
    f"Selected classes  : {selected_unique}"
)

print(
    f"Water-only HRUs   : {len(water_only_hrus)}"
)

print(
    "HRU order         : matched attributes.nc"
)


# ============================================================
# WRITE vegTypeIndex
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r+"
) as att:

    att[
        "vegTypeIndex"
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


    output_veg = np.asarray(
        att[
            "vegTypeIndex"
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
    output_veg,
    selected_classes.astype(
        np.int64
    )
):

    raise RuntimeError(
        "Saved vegTypeIndex values do not match "
        "the calculated dominant land classes."
    )


if np.any(
    output_veg <= 0
):

    raise RuntimeError(
        "Invalid vegTypeIndex values remain "
        "in attributes.nc."
    )


if np.any(
    output_veg == -999
):

    raise RuntimeError(
        "-999 vegTypeIndex placeholders remain "
        "in attributes.nc."
    )


unexpected_classes = sorted(
    set(
        output_veg.tolist()
    )
    - set(
        available_classes
    )
)


if unexpected_classes:

    raise RuntimeError(
        "Unexpected vegTypeIndex classes were "
        "written to attributes.nc:\n"
        f"{unexpected_classes}"
    )


# ============================================================
# CLASS SUMMARY
# ============================================================

class_summary = {}


for land_class in selected_unique:

    class_summary[
        land_class
    ] = int(
        np.count_nonzero(
            selected_classes
            == land_class
        )
    )


print()
print("-" * 70)
print("LAND-CLASS SUMMARY")
print("-" * 70)


for land_class in selected_unique:

    print(
        f"IGBP class {land_class:<3}: "
        f"{class_summary[land_class]:,} HRUs"
    )


if water_only_hrus:

    print()
    print(
        "Open-water-only HRUs:"
    )

    print(
        water_only_hrus
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
        "insert_summa_landclass.txt"
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
        f"Land intersection: {intersect_file}\n"
    )

    file.write(
        f"Attributes: {attribute_file}\n"
    )

    file.write(
        f"HRUs processed: "
        f"{len(attribute_hrus)}\n"
    )

    file.write(
        f"Available IGBP classes: "
        f"{available_classes}\n"
    )

    file.write(
        f"Selected vegetation classes: "
        f"{selected_unique}\n"
    )

    file.write(
        f"Open-water-only HRUs: "
        f"{water_only_hrus}\n"
    )


    for land_class in selected_unique:

        file.write(
            f"Class {land_class}: "
            f"{class_summary[land_class]} HRUs\n"
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
print("SUMMA LAND-CLASS INSERTION COMPLETED")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"HRUs processed   : {len(attribute_hrus)}"
)

print(
    f"Available classes: {available_classes}"
)

print(
    f"Selected classes : {selected_unique}"
)

print(
    f"Water-only HRUs  : {len(water_only_hrus)}"
)

print(
    "vegTypeIndex     : fully populated"
)

print(
    f"Attributes       : {attribute_file}"
)

print(
    f"Workflow log     : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)