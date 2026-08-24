#!/usr/bin/env python3

# Prepare river-network shapefile for CWARHM / mizuRoute.
#
# Purpose
# -------
# Read the original MERIT river-network shapefile as a READ-ONLY
# source, validate its required attributes, create the stream-length
# field required by mizuRoute, and write a prepared working copy into
# the CWARHM domain directory.
#
# IMPORTANT
# ---------
# The original MERIT source shapefile is NEVER overwritten.
#
# Input:
#
#   river_network_shp_path
#   river_network_shp_name
#
# Output:
#
#   <root_path>/domain_<domain_name>/shapefiles/river_network/
#       <river_network_shp_name>
#
# For the NWAM MERIT workflow:
#
#   river_network_shp_length_source | lengthkm
#   river_network_shp_length        | length_m
#
# Therefore:
#
#   length_m = lengthkm * 1000
#
# The output shapefile contains the original river attributes plus
# the new length_m field.
#
# Usage
# -----
# python 1_prepare_river_network.py \
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
        "python 1_prepare_river_network.py "
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
# READ SETTINGS
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


source_path = Path(
    read_from_control(
        CONTROL_FILE,
        "river_network_shp_path"
    )
)


source_name = read_from_control(
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


river_length_source = read_from_control(
    CONTROL_FILE,
    "river_network_shp_length_source"
)


river_length_output = read_from_control(
    CONTROL_FILE,
    "river_network_shp_length"
)


SOURCE_FILE = (
    source_path
    / source_name
)


OUTPUT_DIR = (
    get_domain_root()
    / "shapefiles"
    / "river_network"
)


OUTPUT_FILE = (
    OUTPUT_DIR
    / source_name
)


# ============================================================
# BASIC CONFIGURATION CHECKS
# ============================================================

if river_length_source == river_length_output:

    raise RuntimeError(
        "River length source and output fields are identical.\n\n"
        f"Source field : {river_length_source}\n"
        f"Output field : {river_length_output}\n\n"
        "Use separate source and output fields."
    )


# ESRI Shapefile DBF field names are limited to 10 characters.
if len(river_length_output) > 10:

    raise RuntimeError(
        "Output field name exceeds the ESRI Shapefile "
        "10-character limit:\n"
        f"{river_length_output}"
    )


# ============================================================
# CHECK SOURCE FILE
# ============================================================

if not SOURCE_FILE.exists():

    raise FileNotFoundError(
        f"Source river-network shapefile not found:\n"
        f"{SOURCE_FILE}"
    )


print()
print("=" * 70)
print("PREPARE RIVER NETWORK")
print("=" * 70)

print(f"Domain        : {domain_name}")
print(f"Control file  : {CONTROL_FILE}")

print()
print("READ-ONLY SOURCE:")
print(SOURCE_FILE)

print()
print("CWARHM OUTPUT:")
print(OUTPUT_FILE)

print()
print(f"Length source : {river_length_source}")
print(f"Length output : {river_length_output}")


# ============================================================
# READ SOURCE SHAPEFILE
# ============================================================

gdf = gpd.read_file(
    SOURCE_FILE
)


if len(gdf) == 0:

    raise RuntimeError(
        "River-network shapefile contains no features."
    )


if gdf.crs is None:

    raise RuntimeError(
        "River-network shapefile has no CRS.\n"
        "Assign the correct CRS to the MASTER river dataset "
        "before running CWARHM."
    )


print()
print(f"River segments: {len(gdf)}")
print(f"Source CRS    : {gdf.crs}")


# ============================================================
# CHECK REQUIRED FIELDS
# ============================================================

required_fields = [
    river_seg_id,
    river_down_seg_id,
    river_slope,
    river_length_source,
]


missing_fields = [
    field
    for field in required_fields
    if field not in gdf.columns
]


if missing_fields:

    raise RuntimeError(
        "Missing required river-network field(s): "
        + ", ".join(missing_fields)
    )


# ============================================================
# SEGMENT IDS
# ============================================================

if gdf[river_seg_id].isna().any():

    raise RuntimeError(
        f"{river_seg_id} contains missing values."
    )


try:

    segment_ids = (
        gdf[river_seg_id]
        .astype(np.int64)
    )

except Exception as exc:

    raise RuntimeError(
        f"{river_seg_id} could not be converted "
        "to integer segment IDs."
    ) from exc


if segment_ids.duplicated().any():

    duplicates = (
        segment_ids[
            segment_ids.duplicated(
                keep=False
            )
        ]
        .unique()
        .astype(int)
        .tolist()
    )

    raise RuntimeError(
        "Duplicate river segment IDs found:\n"
        f"{duplicates}"
    )


# Store standardized integer values in working copy.
gdf[river_seg_id] = (
    segment_ids.values
)


# ============================================================
# DOWNSTREAM IDS
# ============================================================

if gdf[river_down_seg_id].isna().any():

    raise RuntimeError(
        f"{river_down_seg_id} contains missing values."
    )


try:

    down_ids = (
        gdf[river_down_seg_id]
        .astype(np.int64)
    )

except Exception as exc:

    raise RuntimeError(
        f"{river_down_seg_id} could not be converted "
        "to integer downstream IDs."
    ) from exc


gdf[river_down_seg_id] = (
    down_ids.values
)


# ============================================================
# SLOPE
# ============================================================

try:

    slope_values = (
        gdf[river_slope]
        .astype(float)
    )

except Exception as exc:

    raise RuntimeError(
        f"{river_slope} could not be converted "
        "to numeric values."
    ) from exc


if not np.all(
    np.isfinite(slope_values)
):

    raise RuntimeError(
        f"{river_slope} contains non-finite values."
    )


if np.any(
    slope_values < 0
):

    raise RuntimeError(
        f"{river_slope} contains negative values."
    )


gdf[river_slope] = (
    slope_values.values
)


# ============================================================
# SOURCE LENGTHS
# ============================================================

try:

    source_lengths = (
        gdf[river_length_source]
        .astype(float)
    )

except Exception as exc:

    raise RuntimeError(
        f"{river_length_source} could not be "
        "converted to numeric values."
    ) from exc


if not np.all(
    np.isfinite(source_lengths)
):

    raise RuntimeError(
        f"{river_length_source} contains "
        "non-finite values."
    )


if np.any(
    source_lengths < 0
):

    raise RuntimeError(
        f"{river_length_source} contains "
        "negative values."
    )


source_max = float(
    source_lengths.max()
)

source_median = float(
    source_lengths.median()
)


print()
print(
    f"Source length range [km]: "
    f"{source_lengths.min():.6f} - "
    f"{source_max:.6f}"
)

print(
    f"Source median [km]      : "
    f"{source_median:.6f}"
)


# Guard against accidentally using a field already in metres.
if source_median > 500:

    raise RuntimeError(
        "Source river lengths appear too large for kilometres.\n\n"
        f"Configured field : {river_length_source}\n"
        f"Median           : {source_median:.3f}\n"
        f"Maximum          : {source_max:.3f}\n\n"
        "Check the source units before continuing."
    )


# ============================================================
# CREATE LENGTH IN METRES
# ============================================================

gdf[river_length_output] = (
    source_lengths.values
    * 1000.0
)


output_lengths = (
    gdf[river_length_output]
    .astype(float)
)


if not np.all(
    np.isfinite(output_lengths)
):

    raise RuntimeError(
        f"{river_length_output} contains "
        "non-finite values."
    )


if not np.allclose(
    output_lengths.values,
    source_lengths.values * 1000.0
):

    raise RuntimeError(
        "River length conversion validation failed."
    )


print()
print("Length conversion:")
print(
    f"  {river_length_source} [km] "
    f"-> {river_length_output} [m]"
)


print()
print(
    gdf[
        [
            river_seg_id,
            river_down_seg_id,
            river_slope,
            river_length_source,
            river_length_output,
        ]
    ]
    .head(10)
    .to_string(
        index=False
    )
)


# ============================================================
# NETWORK OUTLET SUMMARY
# ============================================================

segment_set = set(
    segment_ids
    .astype(int)
    .tolist()
)


natural_mask = (
    down_ids == 0
)


boundary_mask = (
    (down_ids != 0)
    & (~down_ids.isin(segment_set))
)


natural_outlets = (
    gdf.loc[
        natural_mask,
        [
            river_seg_id,
            river_down_seg_id
        ]
    ]
)


boundary_outlets = (
    gdf.loc[
        boundary_mask,
        [
            river_seg_id,
            river_down_seg_id
        ]
    ]
)


# ============================================================
# CREATE OUTPUT DIRECTORY
# ============================================================

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# WRITE PREPARED WORKING COPY
# ============================================================

# Fiona is used explicitly because it has been more reliable
# than pyogrio for the ARC shapefile workflow.
gdf.to_file(
    OUTPUT_FILE,
    driver="ESRI Shapefile",
    engine="fiona",
    index=False
)


# ============================================================
# VERIFY SAVED OUTPUT
# ============================================================

check = gpd.read_file(
    OUTPUT_FILE,
    engine="fiona"
)


if len(check) != len(gdf):

    raise RuntimeError(
        "Saved river-network feature count changed."
    )


for field in required_fields + [
    river_length_output
]:

    if field not in check.columns:

        raise RuntimeError(
            "Prepared river shapefile is missing field:\n"
            f"{field}"
        )


saved_source = (
    check[river_length_source]
    .astype(float)
    .to_numpy()
)


saved_output = (
    check[river_length_output]
    .astype(float)
    .to_numpy()
)


if not np.allclose(
    saved_output,
    saved_source * 1000.0
):

    raise RuntimeError(
        "Saved river shapefile failed "
        "length-conversion verification."
    )


# ============================================================
# FINAL REPORT
# ============================================================

print()
print("=" * 70)
print("RIVER-NETWORK PREPARATION COMPLETE")
print("=" * 70)

print(
    f"Segments processed        : "
    f"{len(check)}"
)

print(
    f"Source range [km]         : "
    f"{saved_source.min():.6f} - "
    f"{saved_source.max():.6f}"
)

print(
    f"Output range [m]          : "
    f"{saved_output.min():.3f} - "
    f"{saved_output.max():.3f}"
)

print(
    f"Natural outlet(s)         : "
    f"{len(natural_outlets)}"
)

print(
    f"Boundary-cut outlet(s)    : "
    f"{len(boundary_outlets)}"
)


if len(natural_outlets) > 0:

    print()
    print("Natural outlets:")
    print(
        natural_outlets
        .to_string(
            index=False
        )
    )


if len(boundary_outlets) > 0:

    print()
    print(
        "Segments whose downstream segment lies "
        "outside this domain:"
    )

    print(
        boundary_outlets
        .to_string(
            index=False
        )
    )


print()
print("MASTER SOURCE REMAINS UNCHANGED:")
print(SOURCE_FILE)

print()
print("Prepared CWARHM river network:")
print(OUTPUT_FILE)