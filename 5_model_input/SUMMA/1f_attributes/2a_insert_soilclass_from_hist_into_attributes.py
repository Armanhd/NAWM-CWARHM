# Insert dominant soil class into attributes.nc.
#
# Step 16 creates categorical soil histograms for every HRU using
# fields named:
#
#     USGS_<class>
#
# This script:
#   - reads those fields dynamically rather than assuming that
#     USGS_0 through USGS_12 all exist
#   - matches HRUs by the configured catchment HRU ID field
#   - ignores soil class 0 when selecting the dominant valid class
#   - uses the dominant non-zero soil class as soilTypeIndex
#   - uses the lowest class number to break an exact count tie
#   - assigns a documented fallback soil class when an HRU has
#     no valid non-zero soil-class pixels
#
# Soil class 0 is not written to SUMMA. It represents an
# unclassified/no-soil category in the current processed raster.
#
# If an HRU contains no valid non-zero soil-class pixels, SUMMA
# still requires a valid positive soilTypeIndex. In that case,
# soil class 1 is assigned explicitly as the fallback. This
# reproduces the effective fallback behaviour of the original
# CWARHM implementation, but makes the fallback explicit,
# traceable, and reportable.
#
# HRU order is not inferred from the shapefile. attributes.nc is
# authoritative, preserving the forcing-derived HRU order.

from pathlib import Path
from datetime import datetime
from shutil import copy2
import re

import geopandas as gpd
import netCDF4 as nc4
import numpy as np


# ============================================================
# CONFIGURATION
# ============================================================

# SUMMA requires a valid positive soilTypeIndex.
#
# Use class 1 when the soil histogram contains no valid
# non-zero soil-class pixels. Keeping this as an explicit
# constant makes the assumption visible and easy to revise
# in the future if the SUMMA soil parameterization changes.

FALLBACK_SOIL_CLASS = 1


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
        f"Soil-intersection shapefile not found:\n"
        f"{intersect_file}"
    )


if not attribute_file.exists():
    raise FileNotFoundError(
        f"attributes.nc not found:\n"
        f"{attribute_file}\n"
        "Run 1_initialize_attributes_nc.py first."
    )


# ============================================================
# READ SOIL HISTOGRAM
# ============================================================

shp = gpd.read_file(
    intersect_file
)


if hru_field not in shp.columns:
    raise RuntimeError(
        f"Configured HRU field '{hru_field}' "
        "not found in soil shapefile."
    )


shp[hru_field] = shp[
    hru_field
].astype(
    np.int64
)


if shp[hru_field].duplicated().any():
    raise RuntimeError(
        f"Duplicate {hru_field} values "
        "found in soil shapefile."
    )


# Detect USGS_<integer> fields dynamically.

class_fields = {}

pattern = re.compile(
    r"^USGS_(\d+)$"
)


for column in shp.columns:

    match = pattern.match(
        str(column)
    )

    if match:

        soil_class = int(
            match.group(1)
        )

        class_fields[
            soil_class
        ] = column


if not class_fields:
    raise RuntimeError(
        "No USGS_<class> histogram fields "
        "found in soil shapefile."
    )


all_classes = sorted(
    class_fields
)


valid_classes = [
    soil_class
    for soil_class in all_classes
    if soil_class != 0
]


# It is acceptable for a domain to contain no observed
# non-zero soil classes. Such HRUs will receive the explicit
# fallback soil class below.
#
# Therefore, do NOT fail here simply because valid_classes
# is empty.


print()
print("============================================================")
print("INSERT SOIL CLASS INTO ATTRIBUTES")
print("============================================================")
print(f"Domain         : {domain_name}")
print(f"Input          : {intersect_file}")
print(f"Attributes     : {attribute_file}")
print(f"HRU field      : {hru_field}")
print(f"Classes        : {all_classes}")
print(f"Valid SUMMA    : {valid_classes}")
print(f"Fallback class : {FALLBACK_SOIL_CLASS}")


# Build HRU -> row mapping.

shp = shp.set_index(
    hru_field,
    drop=False
)


# ============================================================
# UPDATE attributes.nc
# ============================================================

selected_classes = []

fallback_hrus = []


with nc4.Dataset(
    attribute_file,
    "r+"
) as att:

    for required in [
        "hruId",
        "soilTypeIndex"
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
            "HRUs missing from soil intersection:\n"
            f"{missing_hrus}"
        )


    for index, hru in enumerate(
        attribute_hrus
    ):

        row = shp.loc[
            int(hru)
        ]


        counts = []

        for soil_class in valid_classes:

            value = row[
                class_fields[
                    soil_class
                ]
            ]

            if not np.isfinite(
                value
            ):
                value = 0

            counts.append(
                float(value)
            )


        counts = np.asarray(
            counts,
            dtype=np.float64
        )


        if np.any(
            counts < 0
        ):
            raise RuntimeError(
                f"Negative soil histogram count "
                f"found for HRU {hru}."
            )


        # ----------------------------------------------------
        # SELECT SOIL CLASS
        # ----------------------------------------------------
        #
        # Normal case:
        # At least one valid non-zero soil class is present.
        # Select the dominant class.
        #
        # Fallback case:
        # No valid non-zero soil-class pixels are available.
        # Assign the explicit SUMMA fallback class.

        if (
            len(counts) == 0
            or counts.sum() <= 0
        ):

            soil_class = FALLBACK_SOIL_CLASS

            fallback_hrus.append(
                int(hru)
            )

            print(
                f"HRU {int(hru)}: "
                "no valid non-zero soil pixels -> "
                f"fallback soilTypeIndex = {soil_class}"
            )

        else:

            # valid_classes is sorted, so np.argmax
            # deterministically selects the lowest class
            # number if there is an exact tie.

            dominant_index = int(
                np.argmax(
                    counts
                )
            )

            soil_class = int(
                valid_classes[
                    dominant_index
                ]
            )

            print(
                f"HRU {int(hru)}: "
                f"soilTypeIndex = {soil_class}"
            )


        att[
            "soilTypeIndex"
        ][index] = soil_class


        selected_classes.append(
            soil_class
        )


# ============================================================
# VERIFY OUTPUT
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r"
) as att:

    output = np.asarray(
        att["soilTypeIndex"][:],
        dtype=np.int64
    )


if np.any(
    output <= 0
):
    raise RuntimeError(
        "Invalid soilTypeIndex remains in attributes.nc."
    )


normal_count = (
    len(selected_classes)
    - len(fallback_hrus)
)


print()
print("============================================================")
print("SOIL CLASS SUMMARY")
print("============================================================")

print(
    f"HRUs processed       : "
    f"{len(selected_classes)}"
)

print(
    f"Normal assignments   : "
    f"{normal_count}"
)

print(
    f"Fallback assignments : "
    f"{len(fallback_hrus)}"
)

print(
    f"Fallback soil class  : "
    f"{FALLBACK_SOIL_CLASS}"
)

print(
    "Selected soil classes:",
    sorted(
        set(
            selected_classes
        )
    )
)


if fallback_hrus:

    print(
        "Fallback HRUs        : "
        f"{fallback_hrus}"
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
    / f"{now:%Y%m%d}_add_soil_to_attributes.txt"
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
        f"Soil histogram classes: {all_classes}\n"
    )

    file.write(
        "Soil class 0 excluded from "
        "soilTypeIndex selection.\n"
    )

    file.write(
        f"Fallback soil class: "
        f"{FALLBACK_SOIL_CLASS}\n"
    )

    file.write(
        f"HRUs processed: "
        f"{len(selected_classes)}\n"
    )

    file.write(
        f"Normal assignments: "
        f"{normal_count}\n"
    )

    file.write(
        f"Fallback assignments: "
        f"{len(fallback_hrus)}\n"
    )

    file.write(
        f"Fallback HRUs: "
        f"{fallback_hrus}\n"
    )

    file.write(
        f"Selected soil classes: "
        f"{sorted(set(selected_classes))}\n"
    )


print()
print("Soil classes inserted successfully.")
print(f"Workflow log: {log_file}")
