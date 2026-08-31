#!/usr/bin/env python
# coding: utf-8

"""
Sort the prepared CWARHM catchment shapefile by GRU ID and HRU ID.

This ensures HRUs belonging to the same GRU are stored consecutively,
as required by SUMMA for multi-HRU GRUs.

Usage
-----

python 1_sort_catchment_shape.py \
/path/to/control_DOMAIN.txt

Example
-------

python 1_sort_catchment_shape.py \
/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/control_MERIT_717.txt

Multibasin behavior
-------------------

The script reads the supplied domain-specific control file directly.
It does NOT read or modify control_active.txt.
"""

import sys
from pathlib import Path
from shutil import copy2
from datetime import datetime

import geopandas as gpd
import numpy as np
import pandas as pd


# ============================================================
# INPUT CONTROL FILE
# ============================================================

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage:\n"
        "python 1_sort_catchment_shape.py "
        "/path/to/control_DOMAIN.txt"
    )

CONTROL_FILE = Path(sys.argv[1]).resolve()

if not CONTROL_FILE.exists():
    raise FileNotFoundError(
        f"Control file not found:\n{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FUNCTIONS
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

            left, right = stripped.split("|", 1)

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
    Construct a standard domain path.
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


# ============================================================
# DOMAIN SETTINGS
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)

root_path = Path(
    read_from_control(
        CONTROL_FILE,
        "root_path"
    )
)


# ============================================================
# PREPARED CATCHMENT
# ============================================================

catchment_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
)

gru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_gruid"
)

hru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)


# IMPORTANT:
#
# For Stage 4a we want to sort the prepared domain copy,
# not the original source shapefile specified by
# catchment_shp_path.
#
# Stage 00 should already have copied/prepared the catchment in:
#
# domain_<name>/shapefiles/catchment/

catchment_path = make_default_path(
    "shapefiles/catchment"
)

catchment_file = (
    catchment_path
    / catchment_name
)


# ============================================================
# VALIDATE INPUT
# ============================================================

if not catchment_file.exists():
    raise FileNotFoundError(
        "Prepared CWARHM catchment shapefile not found:\n"
        f"{catchment_file}\n\n"
        "Run the domain-preparation step before Stage 4a."
    )


# ============================================================
# READ SHAPEFILE
# ============================================================

shp = gpd.read_file(
    catchment_file
)

if len(shp) == 0:
    raise RuntimeError(
        "Prepared catchment shapefile contains no features."
    )

if shp.crs is None:
    raise RuntimeError(
        "Prepared catchment shapefile has no CRS."
    )


# ============================================================
# VALIDATE REQUIRED FIELDS
# ============================================================

required_fields = [
    gru_field,
    hru_field,
]

missing_fields = [
    field
    for field in required_fields
    if field not in shp.columns
]

if missing_fields:
    raise RuntimeError(
        "Required catchment field(s) missing:\n"
        + "\n".join(
            f"  {field}"
            for field in missing_fields
        )
    )


# Convert IDs explicitly to numeric values before sorting.

for field in required_fields:

    shp[field] = pd.to_numeric(
        shp[field],
        errors="raise"
    )

    if shp[field].isna().any():
        raise RuntimeError(
            f"{field} contains missing values."
        )

    if not np.all(
        np.isfinite(
            shp[field].to_numpy(
                dtype=np.float64
            )
        )
    ):
        raise RuntimeError(
            f"{field} contains non-finite values."
        )


# HRU IDs should be unique.

if shp[hru_field].duplicated().any():

    duplicate_hrus = (
        shp.loc[
            shp[hru_field].duplicated(
                keep=False
            ),
            hru_field
        ]
        .tolist()
    )

    raise RuntimeError(
        f"Duplicate HRU IDs found in {hru_field}:\n"
        f"{duplicate_hrus}"
    )


# ============================================================
# REPORT BEFORE SORTING
# ============================================================

print()
print("=" * 70)
print("SORT CWARHM CATCHMENT SHAPEFILE")
print("=" * 70)
print()
print(f"Domain       : {domain_name}")
print(f"Control file : {CONTROL_FILE}")
print(f"Catchment    : {catchment_file}")
print(f"Features     : {len(shp)}")
print(f"CRS          : {shp.crs}")
print(f"GRU field    : {gru_field}")
print(f"HRU field    : {hru_field}")


# ============================================================
# SORT
# ============================================================

shp = (
    shp
    .sort_values(
        by=[
            gru_field,
            hru_field
        ],
        kind="mergesort"
    )
    .reset_index(
        drop=True
    )
)


# ============================================================
# VERIFY SORT ORDER
# ============================================================

sorted_pairs = list(
    zip(
        shp[gru_field].tolist(),
        shp[hru_field].tolist()
    )
)

if sorted_pairs != sorted(
    sorted_pairs
):
    raise RuntimeError(
        "Catchment sorting verification failed."
    )


# Check that every GRU occupies one contiguous block.

seen_grus = set()
previous_gru = None

for gru in shp[gru_field]:

    gru = int(gru)

    if gru != previous_gru:

        if gru in seen_grus:
            raise RuntimeError(
                f"GRU {gru} appears in multiple "
                "non-contiguous blocks after sorting."
            )

        seen_grus.add(gru)
        previous_gru = gru


# ============================================================
# SAVE
# ============================================================

shp.to_file(
    catchment_file,
    driver="ESRI Shapefile",
    engine="fiona",
    index=False
)


# ============================================================
# VERIFY SAVED OUTPUT
# ============================================================

saved = gpd.read_file(
    catchment_file
)

if len(saved) != len(shp):
    raise RuntimeError(
        "Saved shapefile has an unexpected feature count."
    )

if saved.crs is None:
    raise RuntimeError(
        "Saved shapefile has no CRS."
    )

if saved.crs != shp.crs:
    raise RuntimeError(
        "Saved shapefile CRS changed unexpectedly."
    )

for field in required_fields:

    if field not in saved.columns:
        raise RuntimeError(
            f"{field} missing from saved shapefile."
        )


saved_pairs = list(
    zip(
        saved[gru_field].tolist(),
        saved[hru_field].tolist()
    )
)

if saved_pairs != sorted(
    saved_pairs
):
    raise RuntimeError(
        "Saved shapefile is not sorted by "
        "GRU ID then HRU ID."
    )


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    catchment_path
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

copy2(
    CONTROL_FILE,
    log_folder / CONTROL_FILE.name
)

now = datetime.now()

log_file = (
    log_folder
    / (
        f"{now:%Y%m%d_%H%M%S}_"
        "sort_catchment_shape.txt"
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
        f"Catchment shapefile: {catchment_file}\n"
    )

    file.write(
        f"Features: {len(saved)}\n"
    )

    file.write(
        f"GRU field: {gru_field}\n"
    )

    file.write(
        f"HRU field: {hru_field}\n"
    )

    file.write(
        "Sorted by GRU ID first and HRU ID second.\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("CATCHMENT SORTING COMPLETED")
print("=" * 70)
print(f"Domain       : {domain_name}")
print(f"Features     : {len(saved)}")
print(f"First GRU    : {saved[gru_field].iloc[0]}")
print(f"First HRU    : {saved[hru_field].iloc[0]}")
print(f"Last GRU     : {saved[gru_field].iloc[-1]}")
print(f"Last HRU     : {saved[hru_field].iloc[-1]}")
print(f"Output       : {catchment_file}")
print(f"Workflow log : {log_file}")