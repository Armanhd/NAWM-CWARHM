# Report domain-specific control-file values for CWARHM.
#
# Purpose
# -------
# Read the PREPARED CWARHM catchment and river-network shapefiles
# created by:
#
#   1_prepare_river_network.py
#   2_prepare_catchment.py
#
# and report:
#
#   forcing_raw_space
#   settings_mizu_make_outlet
#
# IMPORTANT
# ---------
# This script does NOT read or modify the original MERIT source files.
#
# Prepared inputs are expected at:
#
#   <root_path>/domain_<domain_name>/shapefiles/catchment/
#   <root_path>/domain_<domain_name>/shapefiles/river_network/
#
#
# Outlet handling
# ---------------
# Natural MERIT outlet:
#
#   NextDownID = 0
#
# Such reaches already represent outlets and require no forced
# modification in topology.nc.
#
# Boundary-cut outlet:
#
#   NextDownID != 0
#
# but the downstream COMID is not present in the selected domain.
#
# These segments must be listed in:
#
#   settings_mizu_make_outlet
#
# so that topology generation changes their downSegId to 0.
#
# Multiple boundary-cut outlets are supported.
#
# Usage
# -----
# python 3_report_control_values.py \
#     ../0_control_files/control_DOMAIN.txt

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 3_report_control_values.py "
        "../0_control_files/control_DOMAIN.txt"
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
# CONTROL-FILE FUNCTIONS
# ============================================================

def read_from_control(file, setting):
    """
    Read one setting using exact control-key matching.
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

            return (
                right
                .split("#", 1)[0]
                .strip()
            )

    raise ValueError(
        f"Setting '{setting}' not found in:\n"
        f"{file}"
    )


def get_domain_root():
    """
    Return:
        <root_path>/domain_<domain_name>
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
    )


# ============================================================
# DOMAIN / FILE SETTINGS
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


catchment_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
)


river_name = read_from_control(
    CONTROL_FILE,
    "river_network_shp_name"
)


river_seg_id = read_from_control(
    CONTROL_FILE,
    "river_network_shp_segid"
)


river_down_seg_id = read_from_control(
    CONTROL_FILE,
    "river_network_shp_downsegid"
)


river_slope = read_from_control(
    CONTROL_FILE,
    "river_network_shp_slope"
)


river_length = read_from_control(
    CONTROL_FILE,
    "river_network_shp_length"
)


DOMAIN_ROOT = get_domain_root()


# ============================================================
# PREPARED CWARHM INPUT FILES
# ============================================================

catchment_file = (
    DOMAIN_ROOT
    / "shapefiles"
    / "catchment"
    / catchment_name
)


river_file = (
    DOMAIN_ROOT
    / "shapefiles"
    / "river_network"
    / river_name
)


# ============================================================
# CHECK INPUT FILES
# ============================================================

if not catchment_file.exists():

    raise FileNotFoundError(
        "Prepared CWARHM catchment shapefile "
        "was not found:\n"
        f"{catchment_file}\n\n"
        "Run 2_prepare_catchment.py first."
    )


if not river_file.exists():

    raise FileNotFoundError(
        "Prepared CWARHM river-network shapefile "
        "was not found:\n"
        f"{river_file}\n\n"
        "Run 1_prepare_river_network.py first."
    )


print()
print("=" * 70)
print("CWARHM DOMAIN CONTROL VALUES")
print("=" * 70)

print(f"Domain       : {domain_name}")
print(f"Control file : {CONTROL_FILE}")

print()
print("Prepared catchment:")
print(catchment_file)

print()
print("Prepared river network:")
print(river_file)


# ============================================================
# READ PREPARED CATCHMENT
# ============================================================

catchment = gpd.read_file(
    catchment_file,
    engine="fiona"
)


if len(catchment) == 0:

    raise RuntimeError(
        "Prepared catchment shapefile contains "
        "no features."
    )


if catchment.crs is None:

    raise RuntimeError(
        "Prepared catchment shapefile has no CRS.\n"
        "2_prepare_catchment.py should produce "
        "an EPSG:4326 working copy."
    )


# ============================================================
# DOMAIN EXTENT
# ============================================================

catchment_wgs84 = (
    catchment.to_crs(
        "EPSG:4326"
    )
)


bounds = np.asarray(
    catchment_wgs84.total_bounds,
    dtype=float
)


if (
    bounds.size != 4
    or not np.all(
        np.isfinite(bounds)
    )
):

    raise RuntimeError(
        "Could not calculate a valid catchment extent."
    )


lon_min, lat_min, lon_max, lat_max = (
    bounds
)


if (
    lon_min < -180
    or lon_max > 180
    or lat_min < -90
    or lat_max > 90
):

    raise RuntimeError(
        "Prepared catchment extent is outside valid "
        "longitude/latitude limits.\n\n"
        f"Bounds: {bounds}"
    )


forcing_raw_space = (
    f"{lat_max:.6f}/"
    f"{lon_min:.6f}/"
    f"{lat_min:.6f}/"
    f"{lon_max:.6f}"
)


# ============================================================
# READ PREPARED RIVER NETWORK
# ============================================================

river = gpd.read_file(
    river_file,
    engine="fiona"
)


if len(river) == 0:

    raise RuntimeError(
        "Prepared river-network shapefile "
        "contains no features."
    )


# ============================================================
# REQUIRED RIVER FIELDS
# ============================================================

required_fields = [
    river_seg_id,
    river_down_seg_id,
]


missing_fields = [
    field
    for field in required_fields
    if field not in river.columns
]


if missing_fields:

    raise RuntimeError(
        "Prepared river-network shapefile is "
        "missing field(s): "
        + ", ".join(
            missing_fields
        )
    )


# ============================================================
# SEGMENT IDS
# ============================================================

if river[river_seg_id].isna().any():

    raise RuntimeError(
        f"{river_seg_id} contains missing values."
    )


if river[river_down_seg_id].isna().any():

    raise RuntimeError(
        f"{river_down_seg_id} contains missing values."
    )


try:

    seg_ids = (
        river[river_seg_id]
        .astype(np.int64)
    )

    down_ids = (
        river[river_down_seg_id]
        .astype(np.int64)
    )

except Exception as exc:

    raise RuntimeError(
        "River segment/downstream IDs could not "
        "be converted to integers."
    ) from exc


if seg_ids.duplicated().any():

    duplicates = (
        seg_ids[
            seg_ids.duplicated(
                keep=False
            )
        ]
        .unique()
        .astype(int)
        .tolist()
    )

    raise RuntimeError(
        "Duplicate river segment IDs detected:\n"
        f"{duplicates}"
    )


segment_set = set(
    seg_ids
    .astype(int)
    .tolist()
)


# ============================================================
# OUTLET TYPES
# ============================================================

# Natural MERIT outlet:
#
# NextDownID = 0

natural_mask = (
    down_ids == 0
)


# Boundary-cut outlet:
#
# NextDownID is non-zero, but that downstream COMID is not
# contained in the selected river network.

boundary_mask = (
    (down_ids != 0)
    & (~down_ids.isin(segment_set))
)


natural_outlets = (
    river.loc[
        natural_mask
    ]
    .copy()
)


boundary_outlets = (
    river.loc[
        boundary_mask
    ]
    .copy()
)


# ============================================================
# SANITY CHECK OUTLETS
# ============================================================

if (
    len(natural_outlets) == 0
    and len(boundary_outlets) == 0
):

    print()
    print(
        "WARNING: No natural or boundary-cut "
        "outlets were identified."
    )

    print(
        "Check the river-network connectivity "
        "before continuing."
    )


# ============================================================
# DISPLAY COLUMNS
# ============================================================

display_columns = [
    river_seg_id,
    river_down_seg_id,
]


if river_slope in river.columns:

    display_columns.append(
        river_slope
    )


if river_length in river.columns:

    display_columns.append(
        river_length
    )


# ============================================================
# MIZUROUTE CONTROL VALUE
# ============================================================

# Natural outlets already have NextDownID = 0, therefore they
# do not need to appear in settings_mizu_make_outlet.
#
# Only boundary-cut segments must be forced to zero.

if len(boundary_outlets) == 0:

    mizu_outlet_setting = "n/a"

else:

    boundary_ids = (
        boundary_outlets[
            river_seg_id
        ]
        .astype(np.int64)
        .tolist()
    )

    # Sort IDs to make output deterministic/reproducible.
    boundary_ids = sorted(
        int(value)
        for value in boundary_ids
    )


    mizu_outlet_setting = ",".join(
        str(value)
        for value in boundary_ids
    )


# ============================================================
# REPORT DOMAIN EXTENT
# ============================================================

print()
print("-" * 70)
print("DOMAIN EXTENT")
print("-" * 70)

print(
    f"Longitude min: {lon_min:.6f}"
)

print(
    f"Longitude max: {lon_max:.6f}"
)

print(
    f"Latitude min : {lat_min:.6f}"
)

print(
    f"Latitude max : {lat_max:.6f}"
)


# ============================================================
# NETWORK SUMMARY
# ============================================================

print()
print("-" * 70)
print("RIVER NETWORK SUMMARY")
print("-" * 70)

print(
    f"Segments              : "
    f"{len(river):,}"
)

print(
    f"Unique segment IDs    : "
    f"{len(segment_set):,}"
)

print(
    f"Natural outlets       : "
    f"{len(natural_outlets):,}"
)

print(
    f"Boundary-cut outlets  : "
    f"{len(boundary_outlets):,}"
)


# ============================================================
# NATURAL OUTLETS
# ============================================================

print()
print("-" * 70)
print("NATURAL MERIT OUTLETS")
print("-" * 70)

print(
    f"Count: "
    f"{len(natural_outlets):,}"
)


if len(natural_outlets) > 0:

    print()

    print(
        natural_outlets[
            display_columns
        ]
        .to_string(
            index=False
        )
    )


# ============================================================
# DOMAIN-BOUNDARY OUTLETS
# ============================================================

print()
print("-" * 70)
print("BOUNDARY-CUT OUTLETS")
print("-" * 70)

print(
    f"Count: "
    f"{len(boundary_outlets):,}"
)


if len(boundary_outlets) > 0:

    print()

    print(
        boundary_outlets[
            display_columns
        ]
        .to_string(
            index=False
        )
    )


# ============================================================
# COPYABLE CONTROL VALUES
# ============================================================

print()
print("=" * 70)
print("CONTROL FILE VALUES TO COPY")
print("=" * 70)

print(
    f"forcing_raw_space           | "
    f"{forcing_raw_space}"
)

print(
    f"settings_mizu_make_outlet   | "
    f"{mizu_outlet_setting}"
)

print("=" * 70)


# ============================================================
# EXPLANATION
# ============================================================

if len(boundary_outlets) == 0:

    print()
    print(
        "No boundary-cut outlets require modification."
    )

    print(
        "Natural MERIT outlets already have "
        "NextDownID = 0."
    )

else:

    print()
    print(
        f"{len(boundary_outlets)} boundary-cut "
        "segment(s) must be forced to downSegId = 0 "
        "when topology.nc is created."
    )


print()
print("=" * 70)
print("REPORT COMPLETE")
print("=" * 70)