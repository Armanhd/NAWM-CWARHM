# Insert dominant MODIS IGBP land class into attributes.nc.
#
# Step 16 creates categorical land-cover histograms for each HRU
# using fields named:
#
#     IGBP_<class>
#
# This script:
#   - detects available IGBP histogram fields dynamically
#   - matches HRUs by configured HRU ID
#   - selects the dominant land-cover class
#   - treats IGBP 17 (open water) specially:
#
#       * if class 17 dominates but another land class exists,
#         the dominant non-water class is used
#
#       * if the HRU contains only open water, class 17 is kept
#
#   - uses the lowest class number to break an exact count tie
#   - fails if an HRU contains no valid land-cover pixels
#
# HRU ordering is taken from attributes.nc, which already follows
# the forcing HRU order.

from pathlib import Path
from datetime import datetime
from shutil import copy2
import re

import geopandas as gpd
import netCDF4 as nc4
import numpy as np


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


# ============================================================
# PATHS
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


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


hru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)


# ============================================================
# VALIDATE INPUTS
# ============================================================

if not intersect_file.exists():
    raise FileNotFoundError(
        f"Land-intersection shapefile not found:\n"
        f"{intersect_file}"
    )


if not attribute_file.exists():
    raise FileNotFoundError(
        f"attributes.nc not found:\n"
        f"{attribute_file}"
    )


# ============================================================
# READ LAND HISTOGRAM
# ============================================================

shp = gpd.read_file(
    intersect_file
)


if hru_field not in shp.columns:
    raise RuntimeError(
        f"Configured HRU field '{hru_field}' "
        "not found in land shapefile."
    )


shp[hru_field] = shp[
    hru_field
].astype(
    np.int64
)


if shp[hru_field].duplicated().any():
    raise RuntimeError(
        f"Duplicate {hru_field} values "
        "found in land shapefile."
    )


pattern = re.compile(
    r"^IGBP_(\d+)$"
)

class_fields = {}


for column in shp.columns:

    match = pattern.match(
        str(column)
    )

    if match:

        land_class = int(
            match.group(1)
        )

        class_fields[
            land_class
        ] = column


if not class_fields:
    raise RuntimeError(
        "No IGBP_<class> histogram fields "
        "found in land shapefile."
    )


available_classes = sorted(
    class_fields
)


print()
print("============================================================")
print("INSERT LAND CLASS INTO ATTRIBUTES")
print("============================================================")
print(f"Domain     : {domain_name}")
print(f"Input      : {intersect_file}")
print(f"Attributes : {attribute_file}")
print(f"HRU field  : {hru_field}")
print(f"Classes    : {available_classes}")


shp = shp.set_index(
    hru_field,
    drop=False
)


# ============================================================
# UPDATE attributes.nc
# ============================================================

selected_classes = []
water_only_hrus = []


with nc4.Dataset(
    attribute_file,
    "r+"
) as att:

    for required in [
        "hruId",
        "vegTypeIndex"
    ]:

        if required not in att.variables:
            raise RuntimeError(
                f"{required} missing from attributes.nc"
            )


    attribute_hrus = np.asarray(
        att["hruId"][:],
        dtype=np.int64
    )


    missing_hrus = [
        int(hru)
        for hru in attribute_hrus
        if hru not in shp.index
    ]


    if missing_hrus:
        raise RuntimeError(
            "HRUs missing from land intersection:\n"
            f"{missing_hrus}"
        )


    for index, hru in enumerate(
        attribute_hrus
    ):

        row = shp.loc[
            int(hru)
        ]


        counts_by_class = {}


        for land_class in available_classes:

            value = row[
                class_fields[
                    land_class
                ]
            ]

            if not np.isfinite(
                value
            ):
                value = 0

            value = float(
                value
            )

            if value < 0:
                raise RuntimeError(
                    f"Negative land histogram count "
                    f"for HRU {hru}."
                )

            counts_by_class[
                land_class
            ] = value


        total_count = sum(
            counts_by_class.values()
        )


        if total_count <= 0:
            raise RuntimeError(
                f"HRU {hru} has no valid "
                "land-cover pixels."
            )


        # ----------------------------------------------------
        # Initial dominant class
        # ----------------------------------------------------

        class_array = np.asarray(
            available_classes,
            dtype=np.int64
        )

        count_array = np.asarray(
            [
                counts_by_class[
                    land_class
                ]
                for land_class
                in available_classes
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


        # ----------------------------------------------------
        # Handle open water
        # ----------------------------------------------------

        if dominant_class == 17:

            non_water_classes = [
                land_class
                for land_class
                in available_classes
                if land_class != 17
                and counts_by_class[
                    land_class
                ] > 0
            ]


            if non_water_classes:

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
                    int(hru)
                )


        att[
            "vegTypeIndex"
        ][index] = dominant_class


        selected_classes.append(
            dominant_class
        )


        print(
            f"HRU {int(hru)}: "
            f"vegTypeIndex = {dominant_class}"
        )


# ============================================================
# VERIFY
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r"
) as att:

    output = np.asarray(
        att["vegTypeIndex"][:],
        dtype=np.int64
    )


if np.any(
    output <= 0
):
    raise RuntimeError(
        "Invalid vegTypeIndex remains "
        "in attributes.nc."
    )


print()
print(
    "Selected vegetation classes:",
    sorted(
        set(
            selected_classes
        )
    )
)

print(
    f"Open-water-only HRUs: "
    f"{len(water_only_hrus)}"
)

if water_only_hrus:

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


this_file = Path(__file__).name

copy2(
    Path(__file__).resolve(),
    log_folder / this_file
)


now = datetime.now()

log_file = (
    log_folder
    / f"{now:%Y%m%d}_add_veg_to_attributes.txt"
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
        f"Available IGBP classes: "
        f"{available_classes}\n"
    )

    file.write(
        f"Selected classes: "
        f"{sorted(set(selected_classes))}\n"
    )

    file.write(
        f"Open-water-only HRUs: "
        f"{water_only_hrus}\n"
    )


print()
print("Land classes inserted successfully.")