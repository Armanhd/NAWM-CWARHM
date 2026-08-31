#!/usr/bin/env python3

# Prepare river-network shapefile for CWARHM / mizuRoute.
#
# Purpose
# -------
# Read the original MERIT river-network shapefile as a READ-ONLY
# source, validate its required attributes, create the stream-length
# field required by mizuRoute, and write a prepared working copy into
# the active CWARHM domain directory.
#
# IMPORTANT
# ---------
# The original MERIT source shapefile is NEVER overwritten.
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
# CRS handling
# ------------
# Some MERIT shapefiles may not contain a .prj file.
#
# If the CRS is missing, this script checks whether the geometry
# coordinates are plausible longitude/latitude values. If they are,
# EPSG:4326 is assigned to the WORKING COPY only.
#
# The prepared CWARHM river-network shapefile is always written in
# EPSG:4326 with a valid .prj file.
#
# Outlet handling
# ---------------
# This script DOES NOT modify downstream connectivity.
#
# It reports:
#
#   natural outlets:
#       downSegId == 0
#
#   boundary-cut outlets:
#       downSegId != 0 but downstream segment does not occur
#       in the retained river-network shapefile
#
# Boundary-cut outlets are handled later by the mizuRoute topology
# workflow through settings_mizu_make_outlet where required.
#
# Usage
# -----
#
# python 1_prepare_river_network.py \
#     ../0_control_files/control_DOMAIN.txt

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

import geopandas as gpd
import numpy as np


# ============================================================
# INPUT CONTROL FILE
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
    Read one exact setting from a CWARHM control file.
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
# READ CONTROL SETTINGS
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
# CONFIGURATION CHECKS
# ============================================================

if river_length_source == river_length_output:

    raise RuntimeError(
        "River length source and output fields are identical.\n\n"
        f"Source field : {river_length_source}\n"
        f"Output field : {river_length_output}\n\n"
        "Use separate source and output fields."
    )


# ESRI Shapefile DBF field-name limit.
for field in [
    river_seg_id,
    river_down_seg_id,
    river_slope,
    river_length_source,
    river_length_output,
]:

    if len(field) > 10:

        raise RuntimeError(
            "Field name exceeds the ESRI Shapefile "
            "10-character limit:\n"
            f"{field}"
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

print()
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
    SOURCE_FILE,
    engine="fiona"
)


if len(gdf) == 0:

    raise RuntimeError(
        "River-network shapefile contains no features."
    )


print()
print(f"River segments : {len(gdf)}")
print(f"Source CRS     : {gdf.crs}")

print()
print("Source columns:")
print(gdf.columns.tolist())


# ============================================================
# CHECK GEOMETRY
# ============================================================

if gdf.geometry.isna().any():

    raise RuntimeError(
        "River-network shapefile contains missing geometry."
    )


empty_geometry_count = int(
    gdf.geometry.is_empty.sum()
)


if empty_geometry_count > 0:

    raise RuntimeError(
        f"{empty_geometry_count} empty river geometries found."
    )


invalid_geometry_count = int(
    (~gdf.geometry.is_valid).sum()
)


if invalid_geometry_count > 0:

    print()
    print(
        f"WARNING: {invalid_geometry_count} invalid "
        "river geometry/geometries detected."
    )

    print(
        "Attempting geometry repair with make_valid()."
    )

    gdf.geometry = (
        gdf.geometry.make_valid()
    )


    remaining_invalid = int(
        (~gdf.geometry.is_valid).sum()
    )


    if remaining_invalid > 0:

        raise RuntimeError(
            f"{remaining_invalid} river geometries remain "
            "invalid after repair."
        )


# ============================================================
# CRS HANDLING
# ============================================================

if gdf.crs is None:

    bounds = gdf.total_bounds

    lon_min = float(bounds[0])
    lat_min = float(bounds[1])
    lon_max = float(bounds[2])
    lat_max = float(bounds[3])


    looks_like_lonlat = (
        -180.0 <= lon_min <= 180.0
        and -180.0 <= lon_max <= 180.0
        and -90.0 <= lat_min <= 90.0
        and -90.0 <= lat_max <= 90.0
    )


    if not looks_like_lonlat:

        raise RuntimeError(
            "River-network CRS is missing and coordinates "
            "do not look like longitude/latitude.\n\n"
            f"Bounds: {bounds}\n\n"
            "Determine the correct source CRS before "
            "running CWARHM."
        )


    print()
    print(
        "Source CRS is missing."
    )

    print(
        "Coordinate bounds are consistent with "
        "longitude/latitude."
    )

    print(
        "Assigning EPSG:4326 to the WORKING COPY only."
    )


    gdf = gdf.set_crs(
        "EPSG:4326",
        allow_override=True
    )


# Prepared CWARHM working copy always uses WGS84.
gdf = gdf.to_crs(
    "EPSG:4326"
)


print()
print(
    f"Working CRS : {gdf.crs}"
)


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
        + ", ".join(
            missing_fields
        )
    )


# ============================================================
# SEGMENT IDs
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


gdf[river_seg_id] = (
    segment_ids.values
)


# ============================================================
# DOWNSTREAM IDs
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
# SELF-LOOP CHECK
# ============================================================

self_loop_mask = (
    segment_ids.to_numpy()
    == down_ids.to_numpy()
)


self_loop_count = int(
    np.count_nonzero(
        self_loop_mask
    )
)


if self_loop_count > 0:

    self_loop_ids = (
        segment_ids[
            self_loop_mask
        ]
        .astype(int)
        .tolist()
    )

    raise RuntimeError(
        "River network contains self-loop segment(s), "
        "where segId == downSegId:\n"
        f"{self_loop_ids}"
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
    np.isfinite(
        slope_values
    )
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
    np.isfinite(
        source_lengths
    )
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


source_min = float(
    source_lengths.min()
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
    f"{source_min:.6f} - "
    f"{source_max:.6f}"
)

print(
    f"Source median [km]      : "
    f"{source_median:.6f}"
)


# Guard against accidentally configuring a field already
# expressed in metres.
if source_median > 500:

    raise RuntimeError(
        "Source river lengths appear too large for kilometres.\n\n"
        f"Configured field : {river_length_source}\n"
        f"Median           : {source_median:.3f}\n"
        f"Maximum          : {source_max:.3f}\n\n"
        "Check the configured source units."
    )


# ============================================================
# CREATE LENGTH IN METRES
# ============================================================

gdf[river_length_output] = (
    source_lengths.to_numpy(
        dtype=np.float64
    )
    * 1000.0
)


output_lengths = (
    gdf[river_length_output]
    .astype(float)
)


if not np.all(
    np.isfinite(
        output_lengths
    )
):

    raise RuntimeError(
        f"{river_length_output} contains "
        "non-finite values."
    )


if not np.allclose(
    output_lengths.to_numpy(),
    source_lengths.to_numpy() * 1000.0
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
print("First 10 prepared segments:")

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
    .copy()
)


boundary_outlets = (
    gdf.loc[
        boundary_mask,
        [
            river_seg_id,
            river_down_seg_id
        ]
    ]
    .copy()
)


print()
print("Network connectivity summary:")
print(
    f"  Natural outlet(s)      : "
    f"{len(natural_outlets)}"
)

print(
    f"  Boundary-cut outlet(s) : "
    f"{len(boundary_outlets)}"
)

print(
    f"  Self loops             : "
    f"{self_loop_count}"
)


# ============================================================
# CREATE OUTPUT DIRECTORY
# ============================================================

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# REMOVE PREVIOUS WORKING OUTPUT
# ============================================================

# Remove only the existing CWARHM prepared copy.
# The original MERIT source is never touched.

shapefile_extensions = [
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".sbn",
    ".sbx",
    ".qix",
]


for extension in shapefile_extensions:

    existing_file = (
        OUTPUT_DIR
        / f"{OUTPUT_FILE.stem}{extension}"
    )

    if existing_file.exists():

        existing_file.unlink()


# ============================================================
# WRITE PREPARED WORKING COPY
# ============================================================

print()
print("Writing prepared river network...")

print(
    f"Output CRS before writing: "
    f"{gdf.crs}"
)


gdf.to_file(
    OUTPUT_FILE,
    driver="ESRI Shapefile",
    engine="fiona",
    index=False
)


# ============================================================
# VERIFY REQUIRED SHAPEFILE COMPONENTS
# ============================================================

required_components = [
    OUTPUT_FILE,
    OUTPUT_FILE.with_suffix(".shx"),
    OUTPUT_FILE.with_suffix(".dbf"),
    OUTPUT_FILE.with_suffix(".prj"),
]


missing_components = [
    path
    for path in required_components
    if not path.exists()
]


if missing_components:

    missing_text = "\n".join(
        str(path)
        for path in missing_components
    )

    raise RuntimeError(
        "Prepared river network was written incompletely.\n"
        "Missing shapefile component(s):\n"
        f"{missing_text}"
    )


# ============================================================
# VERIFY SAVED OUTPUT
# ============================================================

check = gpd.read_file(
    OUTPUT_FILE,
    engine="fiona"
)


# ------------------------------------------------------------
# Feature count
# ------------------------------------------------------------

if len(check) != len(gdf):

    raise RuntimeError(
        "Saved river-network feature count changed.\n"
        f"Before writing: {len(gdf)}\n"
        f"After writing : {len(check)}"
    )


# ------------------------------------------------------------
# CRS
# ------------------------------------------------------------

if check.crs is None:

    raise RuntimeError(
        "Prepared river network was written without a CRS.\n\n"
        f"Expected: EPSG:4326\n"
        f"Output  : {OUTPUT_FILE}"
    )


saved_epsg = check.crs.to_epsg()


if saved_epsg != 4326:

    raise RuntimeError(
        "Prepared river network has the wrong saved CRS.\n\n"
        f"Expected : EPSG:4326\n"
        f"Found    : {check.crs}\n"
        f"EPSG     : {saved_epsg}"
    )


# ------------------------------------------------------------
# Required fields
# ------------------------------------------------------------

for field in (
    required_fields
    + [river_length_output]
):

    if field not in check.columns:

        raise RuntimeError(
            "Prepared river shapefile is missing field:\n"
            f"{field}"
        )


# ------------------------------------------------------------
# Segment IDs
# ------------------------------------------------------------

saved_segment_ids = (
    check[river_seg_id]
    .astype(np.int64)
    .to_numpy()
)


if not np.array_equal(
    saved_segment_ids,
    segment_ids.to_numpy()
):

    raise RuntimeError(
        "Saved segment IDs differ from the source."
    )


# ------------------------------------------------------------
# Downstream IDs
# ------------------------------------------------------------

saved_down_ids = (
    check[river_down_seg_id]
    .astype(np.int64)
    .to_numpy()
)


if not np.array_equal(
    saved_down_ids,
    down_ids.to_numpy()
):

    raise RuntimeError(
        "Saved downstream IDs differ from the source."
    )


# ------------------------------------------------------------
# Length conversion
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# Slope
# ------------------------------------------------------------

saved_slopes = (
    check[river_slope]
    .astype(float)
    .to_numpy()
)


if not np.all(
    np.isfinite(
        saved_slopes
    )
):

    raise RuntimeError(
        "Saved river slope contains non-finite values."
    )


if np.any(
    saved_slopes < 0
):

    raise RuntimeError(
        "Saved river slope contains negative values."
    )


# ============================================================
# WORKFLOW LOG
# ============================================================

log_dir = (
    OUTPUT_DIR
    / "_workflow_log"
)


log_dir.mkdir(
    parents=True,
    exist_ok=True
)


this_file = Path(
    __file__
).name


copy2(
    Path(__file__).resolve(),
    log_dir / this_file
)


copy2(
    CONTROL_FILE,
    log_dir / CONTROL_FILE.name
)


now = datetime.now()


log_file = (
    log_dir
    / (
        f"{now:%Y%m%d_%H%M%S}_"
        "prepare_river_network.txt"
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
        f"Source: {SOURCE_FILE}\n"
    )

    file.write(
        f"Output: {OUTPUT_FILE}\n"
    )

    file.write(
        f"Segments: {len(check)}\n"
    )

    file.write(
        f"Output EPSG: {saved_epsg}\n"
    )

    file.write(
        f"Length source: {river_length_source} [km]\n"
    )

    file.write(
        f"Length output: {river_length_output} [m]\n"
    )

    file.write(
        f"Natural outlets: {len(natural_outlets)}\n"
    )

    file.write(
        f"Boundary-cut outlets: {len(boundary_outlets)}\n"
    )

    file.write(
        f"Self loops: {self_loop_count}\n"
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
    f"Output CRS                : "
    f"{check.crs}"
)

print(
    f"Output EPSG               : "
    f"{saved_epsg}"
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
    f"Slope range               : "
    f"{saved_slopes.min():.8g} - "
    f"{saved_slopes.max():.8g}"
)

print(
    f"Natural outlet(s)         : "
    f"{len(natural_outlets)}"
)

print(
    f"Boundary-cut outlet(s)    : "
    f"{len(boundary_outlets)}"
)

print(
    f"Self loops                : "
    f"{self_loop_count}"
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
        "outside this Pfaf domain:"
    )

    print(
        boundary_outlets
        .to_string(
            index=False
        )
    )

    print()
    print(
        "These are not changed here. "
        "If required as mizuRoute outlets, handle them "
        "through settings_mizu_make_outlet."
    )


print()
print("MASTER MERIT SOURCE REMAINS UNCHANGED:")
print(SOURCE_FILE)

print()
print("Prepared CWARHM river network:")
print(OUTPUT_FILE)

print()
print("Workflow log:")
print(log_file)

print()
print(
    "No control_active.txt was created or modified."
)