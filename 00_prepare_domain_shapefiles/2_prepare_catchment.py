#!/usr/bin/env python3

# Prepare catchment / routing-basin shapefile for CWARHM.
#
# Purpose
# -------
# Read the original MERIT catchment shapefile as a READ-ONLY source,
# construct the attributes required by SUMMA and mizuRoute, and write
# a prepared working copy into the CWARHM domain directory.
#
# IMPORTANT
# ---------
# The original MERIT source shapefile is NEVER overwritten.
#
# Output:
#
#   <root_path>/domain_<domain_name>/shapefiles/catchment/
#       <catchment_shp_name>
#
# For the current NWAM one-HRU-per-GRU configuration:
#
#   GRU_ID     = MERIT COMID
#   HRU_ID     = consecutive integer 1...N
#   HRU_area   = polygon area [m2]
#   area       = HRU_area
#   center_lat = HRU centroid latitude
#   center_lon = HRU centroid longitude
#   hru_to_seg = MERIT COMID
#
# Area calculation
# ----------------
# Areas are calculated using EPSG:6933, a global equal-area CRS.
# This is preferable to using a single UTM zone because NWAM will
# process large Pfafstetter domains that may span multiple UTM zones.
#
# CRS handling
# ------------
# MERIT Pfaf basin shapefiles may not contain a .prj file. If the CRS
# is missing, this script checks whether the coordinates are plausible
# longitude/latitude values and, if so, explicitly assigns EPSG:4326.
#
# Usage
# -----
# python 2_prepare_catchment.py \
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
        "python 2_prepare_catchment.py "
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
        "catchment_shp_path"
    )
)


source_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
)


catchment_gruid = read_from_control(
    CONTROL_FILE,
    "catchment_shp_gruid"
)


catchment_hruid = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)


catchment_area = read_from_control(
    CONTROL_FILE,
    "catchment_shp_area"
)


catchment_lat = read_from_control(
    CONTROL_FILE,
    "catchment_shp_lat"
)


catchment_lon = read_from_control(
    CONTROL_FILE,
    "catchment_shp_lon"
)


basin_hruid = read_from_control(
    CONTROL_FILE,
    "river_basin_shp_rm_hruid"
)


basin_area = read_from_control(
    CONTROL_FILE,
    "river_basin_shp_area"
)


basin_to_seg = read_from_control(
    CONTROL_FILE,
    "river_basin_shp_hru_to_seg"
)


SOURCE_FILE = (
    source_path
    / source_name
)


OUTPUT_DIR = (
    get_domain_root()
    / "shapefiles"
    / "catchment"
)


OUTPUT_FILE = (
    OUTPUT_DIR
    / source_name
)


# ============================================================
# SHAPEFILE FIELD-NAME CHECKS
# ============================================================

output_field_names = [
    catchment_gruid,
    catchment_hruid,
    catchment_area,
    catchment_lat,
    catchment_lon,
    basin_area,
    basin_to_seg,
]


for field in output_field_names:

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
        f"Source catchment shapefile not found:\n"
        f"{SOURCE_FILE}"
    )


print()
print("=" * 70)
print("PREPARE CATCHMENT")
print("=" * 70)

print(f"Domain       : {domain_name}")
print(f"Control file : {CONTROL_FILE}")

print()
print("READ-ONLY SOURCE:")
print(SOURCE_FILE)

print()
print("CWARHM OUTPUT:")
print(OUTPUT_FILE)


# ============================================================
# READ SOURCE SHAPEFILE
# ============================================================

# Fiona is explicitly used for this ARC workflow.
gdf = gpd.read_file(
    SOURCE_FILE,
    engine="fiona"
)


if len(gdf) == 0:

    raise RuntimeError(
        "Catchment shapefile contains no features."
    )


print()
print(f"Features    : {len(gdf)}")
print(f"Source CRS  : {gdf.crs}")

print()
print("Source columns:")
print(gdf.columns.tolist())


# ============================================================
# CHECK BASIN ID
# ============================================================

if basin_hruid not in gdf.columns:

    raise RuntimeError(
        f"Required basin ID field "
        f"'{basin_hruid}' was not found."
    )


if gdf[basin_hruid].isna().any():

    raise RuntimeError(
        f"{basin_hruid} contains missing values."
    )


try:

    basin_ids = (
        gdf[basin_hruid]
        .astype(np.int64)
    )

except Exception as exc:

    raise RuntimeError(
        f"{basin_hruid} could not be converted "
        "to integer IDs."
    ) from exc


if basin_ids.duplicated().any():

    duplicates = (
        basin_ids[
            basin_ids.duplicated(
                keep=False
            )
        ]
        .unique()
        .astype(int)
        .tolist()
    )

    raise RuntimeError(
        "Duplicate basin IDs found:\n"
        f"{duplicates}"
    )


gdf[basin_hruid] = (
    basin_ids.values
)


# ============================================================
# CHECK GEOMETRY
# ============================================================

if gdf.geometry.isna().any():

    raise RuntimeError(
        "Catchment shapefile contains missing geometry."
    )


empty_geometry_count = int(
    gdf.geometry.is_empty.sum()
)


if empty_geometry_count > 0:

    raise RuntimeError(
        f"{empty_geometry_count} empty geometries found."
    )


invalid_geometry_count = int(
    (~gdf.geometry.is_valid).sum()
)


if invalid_geometry_count > 0:

    print()
    print(
        f"WARNING: {invalid_geometry_count} invalid "
        "geometry/geometries detected."
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
            f"{remaining_invalid} geometries remain "
            "invalid after repair."
        )


# ============================================================
# CRS
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
            "Catchment CRS is missing and coordinates do not "
            "look like geographic longitude/latitude.\n\n"
            f"Bounds: {bounds}\n\n"
            "Do not assign EPSG:4326 automatically. "
            "Determine the correct source CRS first."
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


# Convert working copy to WGS84.
gdf = gdf.to_crs(
    "EPSG:4326"
)


print()
print(
    f"Working CRS : {gdf.crs}"
)


# ============================================================
# ADD GRU / HRU IDS
# ============================================================

gdf[catchment_gruid] = (
    basin_ids.values
)


gdf[catchment_hruid] = (
    np.arange(
        1,
        len(gdf) + 1,
        dtype=np.int64
    )
)


# ============================================================
# AREA CALCULATION
# ============================================================

# EPSG:6933 is a global equal-area CRS and is more suitable
# for large NWAM domains than selecting one UTM zone for an
# entire Pfafstetter basin.
AREA_CRS = "EPSG:6933"


print()
print(
    f"Area calculation CRS: {AREA_CRS}"
)


gdf_equal_area = (
    gdf.to_crs(
        AREA_CRS
    )
)


areas_m2 = (
    gdf_equal_area
    .geometry
    .area
    .to_numpy()
)


if not np.all(
    np.isfinite(areas_m2)
):

    raise RuntimeError(
        "Non-finite HRU area values were calculated."
    )


if np.any(
    areas_m2 <= 0
):

    bad_count = int(
        np.sum(
            areas_m2 <= 0
        )
    )

    raise RuntimeError(
        f"{bad_count} HRUs have area <= 0."
    )


gdf[catchment_area] = (
    areas_m2
)


gdf[basin_area] = (
    areas_m2
)


# ============================================================
# CENTROIDS
# ============================================================

# Calculate centroids in the projected equal-area CRS,
# then convert the points back to EPSG:4326.

centroid_geometry = (
    gdf_equal_area
    .geometry
    .centroid
)


centroids = gpd.GeoSeries(
    centroid_geometry,
    crs=AREA_CRS
).to_crs(
    "EPSG:4326"
)


gdf[catchment_lon] = (
    centroids.x
    .to_numpy()
)


gdf[catchment_lat] = (
    centroids.y
    .to_numpy()
)


if not np.all(
    np.isfinite(
        gdf[catchment_lon]
    )
):

    raise RuntimeError(
        "Non-finite centroid longitude values found."
    )


if not np.all(
    np.isfinite(
        gdf[catchment_lat]
    )
):

    raise RuntimeError(
        "Non-finite centroid latitude values found."
    )


# ============================================================
# CONNECT ROUTING BASIN TO RIVER SEGMENT
# ============================================================

# Current NWAM/MERIT design:
#
# Each routing basin corresponds to the river reach having
# the same MERIT COMID.

gdf[basin_to_seg] = (
    basin_ids.values
)


# ============================================================
# VALIDATE GENERATED IDS
# ============================================================

expected_hru_ids = np.arange(
    1,
    len(gdf) + 1,
    dtype=np.int64
)


actual_hru_ids = (
    gdf[catchment_hruid]
    .astype(np.int64)
    .to_numpy()
)


if not np.array_equal(
    expected_hru_ids,
    actual_hru_ids
):

    raise RuntimeError(
        "Generated HRU IDs are not consecutive 1...N."
    )


if not np.array_equal(
    gdf[catchment_gruid]
    .astype(np.int64)
    .to_numpy(),
    basin_ids.to_numpy()
):

    raise RuntimeError(
        "GRU IDs do not match routing-basin IDs."
    )


if not np.array_equal(
    gdf[basin_to_seg]
    .astype(np.int64)
    .to_numpy(),
    basin_ids.to_numpy()
):

    raise RuntimeError(
        "hru_to_seg does not match the routing COMID."
    )


# ============================================================
# REPORT
# ============================================================

fields = [
    basin_hruid,
    catchment_gruid,
    catchment_hruid,
    catchment_area,
    catchment_lat,
    catchment_lon,
    basin_area,
    basin_to_seg,
]


print()
print("Prepared attributes — first 10 HRUs:")

print(
    gdf[
        fields
    ]
    .head(10)
    .to_string(
        index=False
    )
)


print()
print(
    f"HRU area range [m2]: "
    f"{areas_m2.min():.3f} - "
    f"{areas_m2.max():.3f}"
)

print(
    f"Total domain area [km2]: "
    f"{areas_m2.sum() / 1.0e6:.3f}"
)

# ============================================================
# CREATE OUTPUT DIRECTORY
# ============================================================

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# ENSURE FINAL OUTPUT CRS
# ============================================================

# All downstream CWARHM / EASYMORE operations expect the
# prepared catchment shapefile to have an explicitly defined
# geographic CRS.
#
# The original MERIT shapefile may have no .prj file. That is
# acceptable because it is treated as a read-only source.
#
# The prepared CWARHM copy MUST, however, permanently contain
# EPSG:4326.

if gdf.crs is None:

    raise RuntimeError(
        "Internal error: prepared catchment lost its CRS "
        "before writing."
    )


gdf = gdf.to_crs(
    "EPSG:4326"
)


if gdf.crs.to_epsg() != 4326:

    raise RuntimeError(
        "Prepared catchment could not be converted "
        "to EPSG:4326."
    )


# ============================================================
# REMOVE PREVIOUS WORKING OUTPUT
# ============================================================

# Remove only an existing CWARHM working copy.
# The original MERIT source is never touched.
#
# This prevents stale .shp/.dbf/.shx/.prj components from an
# interrupted previous run being mixed with the new output.

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
print("Writing prepared catchment...")

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
# VERIFY SHAPEFILE COMPONENTS
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
        "Prepared catchment was written incompletely.\n"
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
        "Saved catchment feature count changed.\n"
        f"Before writing: {len(gdf)}\n"
        f"After writing : {len(check)}"
    )


# ------------------------------------------------------------
# CRS
# ------------------------------------------------------------

if check.crs is None:

    raise RuntimeError(
        "Prepared catchment was written without a CRS.\n\n"
        f"Expected: EPSG:4326\n"
        f"Output  : {OUTPUT_FILE}\n\n"
        "The .prj file may not have been written correctly."
    )


saved_epsg = check.crs.to_epsg()


if saved_epsg != 4326:

    raise RuntimeError(
        "Prepared catchment has the wrong saved CRS.\n\n"
        f"Expected : EPSG:4326\n"
        f"Found    : {check.crs}\n"
        f"EPSG     : {saved_epsg}"
    )


# ------------------------------------------------------------
# Required attributes
# ------------------------------------------------------------

required_output_fields = [
    basin_hruid,
    catchment_gruid,
    catchment_hruid,
    catchment_area,
    catchment_lat,
    catchment_lon,
    basin_area,
    basin_to_seg,
]


missing_output_fields = [
    field
    for field in required_output_fields
    if field not in check.columns
]


if missing_output_fields:

    raise RuntimeError(
        "Prepared catchment is missing field(s): "
        + ", ".join(
            missing_output_fields
        )
    )


# ------------------------------------------------------------
# HRU IDs
# ------------------------------------------------------------

saved_hru_ids = (
    check[catchment_hruid]
    .astype(np.int64)
    .to_numpy()
)


if not np.array_equal(
    saved_hru_ids,
    expected_hru_ids
):

    raise RuntimeError(
        "Saved HRU IDs do not match expected 1...N."
    )


# ------------------------------------------------------------
# GRU IDs
# ------------------------------------------------------------

saved_gru_ids = (
    check[catchment_gruid]
    .astype(np.int64)
    .to_numpy()
)


if not np.array_equal(
    saved_gru_ids,
    basin_ids.to_numpy()
):

    raise RuntimeError(
        "Saved GRU IDs do not match MERIT COMIDs."
    )


# ------------------------------------------------------------
# HRU-to-segment mapping
# ------------------------------------------------------------

saved_hru_to_seg = (
    check[basin_to_seg]
    .astype(np.int64)
    .to_numpy()
)


if not np.array_equal(
    saved_hru_to_seg,
    basin_ids.to_numpy()
):

    raise RuntimeError(
        "Saved hru_to_seg values do not match "
        "MERIT COMIDs."
    )


# ------------------------------------------------------------
# HRU areas
# ------------------------------------------------------------

saved_areas = (
    check[catchment_area]
    .astype(float)
    .to_numpy()
)


if not np.all(
    np.isfinite(saved_areas)
):

    raise RuntimeError(
        "Saved HRU areas contain non-finite values."
    )


if np.any(
    saved_areas <= 0
):

    raise RuntimeError(
        "Saved HRU areas contain values <= 0."
    )


# ------------------------------------------------------------
# Centroid coordinates
# ------------------------------------------------------------

saved_lon = (
    check[catchment_lon]
    .astype(float)
    .to_numpy()
)

saved_lat = (
    check[catchment_lat]
    .astype(float)
    .to_numpy()
)


if not np.all(
    np.isfinite(saved_lon)
):

    raise RuntimeError(
        "Saved centroid longitudes contain "
        "non-finite values."
    )


if not np.all(
    np.isfinite(saved_lat)
):

    raise RuntimeError(
        "Saved centroid latitudes contain "
        "non-finite values."
    )


if np.any(
    (saved_lon < -180.0)
    | (saved_lon > 180.0)
):

    raise RuntimeError(
        "Saved centroid longitude values are "
        "outside the valid geographic range."
    )


if np.any(
    (saved_lat < -90.0)
    | (saved_lat > 90.0)
):

    raise RuntimeError(
        "Saved centroid latitude values are "
        "outside the valid geographic range."
    )


# ============================================================
# FINAL REPORT
# ============================================================

print()
print("=" * 70)
print("CATCHMENT PREPARATION COMPLETE")
print("=" * 70)

print(
    f"HRUs / GRUs        : {len(check)}"
)

print(
    f"HRU IDs            : "
    f"1 - {len(check)}"
)

print(
    f"Area CRS            : "
    f"{AREA_CRS}"
)

print(
    f"Output CRS          : "
    f"{check.crs}"
)

print(
    f"Output EPSG         : "
    f"{saved_epsg}"
)

print(
    f"PRJ file            : "
    f"{OUTPUT_FILE.with_suffix('.prj')}"
)

print(
    f"Total area [km2]    : "
    f"{saved_areas.sum() / 1.0e6:.3f}"
)

print()
print(
    "MASTER MERIT SOURCE REMAINS UNCHANGED:"
)

print(
    SOURCE_FILE
)

print()
print(
    "Prepared CWARHM catchment:"
)

print(
    OUTPUT_FILE
)

print()
print(
    "Prepared catchment is ready for "
    "EASYMORE and subsequent CWARHM stages."
)