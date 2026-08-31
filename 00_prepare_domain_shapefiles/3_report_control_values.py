#!/usr/bin/env python3
# coding: utf-8

"""
Derive and update domain-specific CWARHM control-file values.

Purpose
-------
Read the PREPARED CWARHM catchment and river-network shapefiles
created by:

    1_prepare_river_network.py
    2_prepare_catchment.py

and automatically derive/update:

    forcing_raw_space
    settings_mizu_make_outlet

The supplied domain-specific control file is updated directly.

IMPORTANT
---------
This script:

    - does NOT use control_active.txt
    - does NOT modify original MERIT source shapefiles
    - only updates the explicitly supplied domain control file
    - creates a timestamped backup before modifying the control file

Prepared inputs are expected at:

    <root_path>/domain_<domain_name>/shapefiles/catchment/
    <root_path>/domain_<domain_name>/shapefiles/river_network/

forcing_raw_space
-----------------
The prepared catchment extent is calculated in EPSG:4326 and a
small geographic buffer is added.

CWARHM format:

    LAT_MAX/LON_MIN/LAT_MIN/LON_MAX

The buffer used here is:

    0.05 degrees

The forcing-specific preparation scripts may add their own
additional grid-cell buffers later.

Outlet handling
---------------
Natural MERIT outlet:

    NextDownID = 0

These already represent outlets and require no forced change.

Boundary-cut outlet:

    NextDownID != 0

but the downstream COMID is not present in the selected domain.

These segments are written to:

    settings_mizu_make_outlet

so topology generation can assign their downSegId = 0.

Multiple boundary-cut outlets are supported.

Usage
-----
python 3_report_control_values.py \
/path/to/control_DOMAIN.txt
"""

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

import geopandas as gpd
import numpy as np


# ============================================================
# CONFIGURATION
# ============================================================

DOMAIN_BUFFER_DEGREES = 0.05


# ============================================================
# INPUT CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 3_report_control_values.py "
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


def update_control_setting(
    file,
    setting,
    new_value
):
    """
    Replace one existing setting while preserving:

        - key name
        - comments
        - overall control-file structure

    Exact key matching is used.
    """

    original_lines = (
        file
        .read_text()
        .splitlines()
    )

    updated_lines = []

    matched = False

    for line in original_lines:

        stripped = line.strip()

        if (
            not stripped
            or stripped.startswith("#")
            or "|" not in line
        ):

            updated_lines.append(
                line
            )

            continue


        left, right = line.split(
            "|",
            1
        )


        if left.strip() != setting:

            updated_lines.append(
                line
            )

            continue


        if matched:

            raise RuntimeError(
                f"Control setting '{setting}' occurs "
                "more than once:\n"
                f"{file}"
            )


        comment = ""

        if "#" in right:

            comment_text = (
                right
                .split("#", 1)[1]
                .strip()
            )

            if comment_text:

                comment = (
                    f"  # {comment_text}"
                )


        # Preserve the existing key text before "|".
        key_text = left.rstrip()

        new_line = (
            f"{key_text:<28} | "
            f"{new_value}"
            f"{comment}"
        )


        updated_lines.append(
            new_line
        )

        matched = True


    if not matched:

        raise RuntimeError(
            f"Could not update setting "
            f"'{setting}' because it was not found in:\n"
            f"{file}"
        )


    file.write_text(
        "\n".join(
            updated_lines
        )
        + "\n"
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
# PREPARED INPUT FILES
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


# ============================================================
# INITIAL REPORT
# ============================================================

print()
print("=" * 70)
print("DERIVE CWARHM DOMAIN CONTROL VALUES")
print("=" * 70)

print()
print(f"Domain       : {domain_name}")
print(f"Control file : {CONTROL_FILE}")

print()
print(
    f"Catchment    : {catchment_file}"
)

print(
    f"River network: {river_file}"
)


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
# CALCULATE DOMAIN EXTENT
# ============================================================

catchment_wgs84 = (
    catchment
    .to_crs(
        "EPSG:4326"
    )
)


bounds = np.asarray(
    catchment_wgs84.total_bounds,
    dtype=np.float64
)


if (
    bounds.size != 4
    or not np.all(
        np.isfinite(
            bounds
        )
    )
):

    raise RuntimeError(
        "Could not calculate a valid catchment extent."
    )


lon_min, lat_min, lon_max, lat_max = (
    bounds
)


if (
    lon_min < -180.0
    or lon_max > 180.0
    or lat_min < -90.0
    or lat_max > 90.0
):

    raise RuntimeError(
        "Prepared catchment extent is outside valid "
        "longitude/latitude limits.\n\n"
        f"Bounds: {bounds}"
    )


# ============================================================
# ADD DOMAIN BUFFER
# ============================================================

buffered_lat_max = min(
    90.0,
    lat_max
    + DOMAIN_BUFFER_DEGREES
)

buffered_lat_min = max(
    -90.0,
    lat_min
    - DOMAIN_BUFFER_DEGREES
)

buffered_lon_min = max(
    -180.0,
    lon_min
    - DOMAIN_BUFFER_DEGREES
)

buffered_lon_max = min(
    180.0,
    lon_max
    + DOMAIN_BUFFER_DEGREES
)


if (
    buffered_lat_min
    >= buffered_lat_max
    or buffered_lon_min
    >= buffered_lon_max
):

    raise RuntimeError(
        "Buffered catchment extent is invalid."
    )


forcing_raw_space = (
    f"{buffered_lat_max:.6f}/"
    f"{buffered_lon_min:.6f}/"
    f"{buffered_lat_min:.6f}/"
    f"{buffered_lon_max:.6f}"
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

if river[
    river_seg_id
].isna().any():

    raise RuntimeError(
        f"{river_seg_id} contains missing values."
    )


if river[
    river_down_seg_id
].isna().any():

    raise RuntimeError(
        f"{river_down_seg_id} contains missing values."
    )


try:

    seg_ids = (
        river[
            river_seg_id
        ]
        .astype(
            np.int64
        )
    )


    down_ids = (
        river[
            river_down_seg_id
        ]
        .astype(
            np.int64
        )
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
# CHECK SELF LOOPS
# ============================================================

self_loop_mask = (
    seg_ids.to_numpy()
    ==
    down_ids.to_numpy()
)


self_loop_count = int(
    np.count_nonzero(
        self_loop_mask
    )
)


if self_loop_count > 0:

    self_loop_ids = (
        seg_ids[
            self_loop_mask
        ]
        .astype(int)
        .tolist()
    )

    raise RuntimeError(
        "Self-looping river segments detected:\n"
        f"{self_loop_ids}"
    )


# ============================================================
# OUTLET TYPES
# ============================================================

natural_mask = (
    down_ids == 0
)


boundary_mask = (
    (down_ids != 0)
    & (~down_ids.isin(
        segment_set
    ))
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


if (
    len(natural_outlets) == 0
    and len(boundary_outlets) == 0
):

    print()
    print(
        "WARNING: No natural or boundary-cut "
        "outlets were identified."
    )


# ============================================================
# MIZUROUTE CONTROL VALUE
# ============================================================

if len(
    boundary_outlets
) == 0:

    mizu_outlet_setting = (
        "n/a"
    )

else:

    boundary_ids = (
        boundary_outlets[
            river_seg_id
        ]
        .astype(
            np.int64
        )
        .tolist()
    )


    boundary_ids = sorted(
        int(value)
        for value
        in boundary_ids
    )


    mizu_outlet_setting = (
        ",".join(
            str(value)
            for value
            in boundary_ids
        )
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
# REPORT EXTENT
# ============================================================

print()
print("-" * 70)
print("DOMAIN EXTENT")
print("-" * 70)

print()
print("Prepared catchment extent:")

print(
    f"  Longitude min : "
    f"{lon_min:.6f}"
)

print(
    f"  Longitude max : "
    f"{lon_max:.6f}"
)

print(
    f"  Latitude min  : "
    f"{lat_min:.6f}"
)

print(
    f"  Latitude max  : "
    f"{lat_max:.6f}"
)


print()
print(
    f"Domain buffer  : "
    f"{DOMAIN_BUFFER_DEGREES:.3f} degrees"
)


print()
print("Buffered forcing extent:")

print(
    f"  Longitude min : "
    f"{buffered_lon_min:.6f}"
)

print(
    f"  Longitude max : "
    f"{buffered_lon_max:.6f}"
)

print(
    f"  Latitude min  : "
    f"{buffered_lat_min:.6f}"
)

print(
    f"  Latitude max  : "
    f"{buffered_lat_max:.6f}"
)


# ============================================================
# NETWORK SUMMARY
# ============================================================

print()
print("-" * 70)
print("RIVER NETWORK SUMMARY")
print("-" * 70)

print(
    f"Segments             : "
    f"{len(river):,}"
)

print(
    f"Unique segment IDs   : "
    f"{len(segment_set):,}"
)

print(
    f"Natural outlets      : "
    f"{len(natural_outlets):,}"
)

print(
    f"Boundary-cut outlets : "
    f"{len(boundary_outlets):,}"
)

print(
    f"Self loops           : "
    f"{self_loop_count:,}"
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


if len(
    natural_outlets
) > 0:

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
# BOUNDARY OUTLETS
# ============================================================

print()
print("-" * 70)
print("BOUNDARY-CUT OUTLETS")
print("-" * 70)

print(
    f"Count: "
    f"{len(boundary_outlets):,}"
)


if len(
    boundary_outlets
) > 0:

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
# EXISTING CONTROL VALUES
# ============================================================

old_forcing_raw_space = (
    read_from_control(
        CONTROL_FILE,
        "forcing_raw_space"
    )
)


old_mizu_outlet = (
    read_from_control(
        CONTROL_FILE,
        "settings_mizu_make_outlet"
    )
)


# ============================================================
# BACK UP CONTROL FILE
# ============================================================

timestamp = datetime.now()


backup_file = (
    CONTROL_FILE.parent
    / (
        f"{CONTROL_FILE.stem}_"
        f"backup_{timestamp:%Y%m%d_%H%M%S}"
        f"{CONTROL_FILE.suffix}"
    )
)


copy2(
    CONTROL_FILE,
    backup_file
)


# ============================================================
# UPDATE CONTROL FILE
# ============================================================

update_control_setting(
    CONTROL_FILE,
    "forcing_raw_space",
    forcing_raw_space
)


update_control_setting(
    CONTROL_FILE,
    "settings_mizu_make_outlet",
    mizu_outlet_setting
)


# ============================================================
# VERIFY CONTROL-FILE UPDATE
# ============================================================

verified_forcing_raw_space = (
    read_from_control(
        CONTROL_FILE,
        "forcing_raw_space"
    )
)


verified_mizu_outlet = (
    read_from_control(
        CONTROL_FILE,
        "settings_mizu_make_outlet"
    )
)


if (
    verified_forcing_raw_space
    != forcing_raw_space
):

    raise RuntimeError(
        "forcing_raw_space verification failed.\n"
        f"Expected: {forcing_raw_space}\n"
        f"Found   : {verified_forcing_raw_space}"
    )


if (
    verified_mizu_outlet
    != mizu_outlet_setting
):

    raise RuntimeError(
        "settings_mizu_make_outlet verification failed.\n"
        f"Expected: {mizu_outlet_setting}\n"
        f"Found   : {verified_mizu_outlet}"
    )


# ============================================================
# CONTROL UPDATE REPORT
# ============================================================

print()
print("=" * 70)
print("CONTROL FILE UPDATED")
print("=" * 70)

print()
print(
    "forcing_raw_space"
)

print(
    f"  Old: {old_forcing_raw_space}"
)

print(
    f"  New: {forcing_raw_space}"
)


print()
print(
    "settings_mizu_make_outlet"
)

print(
    f"  Old: {old_mizu_outlet}"
)

print(
    f"  New: {mizu_outlet_setting}"
)


print()
print(
    f"Backup: {backup_file}"
)

print(
    f"Updated control: {CONTROL_FILE}"
)


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    DOMAIN_ROOT
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
    Path(__file__).resolve(),
    log_folder / this_file
)


copy2(
    CONTROL_FILE,
    log_folder / CONTROL_FILE.name
)


log_file = (
    log_folder
    / (
        f"{timestamp:%Y%m%d_%H%M%S}_"
        "derive_domain_control_values.txt"
    )
)


with open(
    log_file,
    "w"
) as file:

    file.write(
        f"Log generated by {this_file} "
        f"on {timestamp:%Y/%m/%d %H:%M:%S}\n"
    )

    file.write(
        f"Domain: {domain_name}\n"
    )

    file.write(
        f"Control file: {CONTROL_FILE}\n"
    )

    file.write(
        f"Control backup: {backup_file}\n"
    )

    file.write(
        f"Catchment: {catchment_file}\n"
    )

    file.write(
        f"River network: {river_file}\n"
    )

    file.write(
        f"Catchment extent: "
        f"{lat_max:.6f}/"
        f"{lon_min:.6f}/"
        f"{lat_min:.6f}/"
        f"{lon_max:.6f}\n"
    )

    file.write(
        f"Domain buffer degrees: "
        f"{DOMAIN_BUFFER_DEGREES}\n"
    )

    file.write(
        f"forcing_raw_space old: "
        f"{old_forcing_raw_space}\n"
    )

    file.write(
        f"forcing_raw_space new: "
        f"{forcing_raw_space}\n"
    )

    file.write(
        f"settings_mizu_make_outlet old: "
        f"{old_mizu_outlet}\n"
    )

    file.write(
        f"settings_mizu_make_outlet new: "
        f"{mizu_outlet_setting}\n"
    )

    file.write(
        f"Segments: {len(river)}\n"
    )

    file.write(
        f"Natural outlets: "
        f"{len(natural_outlets)}\n"
    )

    file.write(
        f"Boundary-cut outlets: "
        f"{len(boundary_outlets)}\n"
    )

    file.write(
        f"Self loops: {self_loop_count}\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("DOMAIN CONTROL PREPARATION COMPLETED")
print("=" * 70)

print(
    f"Domain                    : "
    f"{domain_name}"
)

print(
    f"forcing_raw_space         : "
    f"{forcing_raw_space}"
)

print(
    f"settings_mizu_make_outlet : "
    f"{mizu_outlet_setting}"
)

print(
    f"Natural outlets           : "
    f"{len(natural_outlets)}"
)

print(
    f"Boundary-cut outlets      : "
    f"{len(boundary_outlets)}"
)

print(
    f"Control file              : "
    f"{CONTROL_FILE}"
)

print(
    f"Backup                    : "
    f"{backup_file}"
)

print(
    f"Workflow log              : "
    f"{log_file}"
)

print()
print(
    "The supplied domain control file is now ready "
    "for subsequent CWARHM stages."
)

print(
    "No control_active.txt was created or modified."
)