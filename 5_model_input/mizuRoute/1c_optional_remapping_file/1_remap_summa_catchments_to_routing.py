#!/usr/bin/env python3
# coding: utf-8

"""
Create the optional SUMMA-to-mizuRoute catchment remapping file.

Purpose
-------
This script is required only when:

    river_basin_needs_remap | yes

It creates the mizuRoute remapping NetCDF used when the spatial
units supplying runoff from SUMMA differ from the routing catchments
used by mizuRoute.

The workflow assumes that mizuRoute receives SUMMA runoff at the
SUMMA GRU level.

IMPORTANT
---------
This multibasin version:

    - receives a domain-specific control file explicitly
    - does NOT read or modify control_active.txt
    - uses prepared/domain-specific shapefiles
    - validates all required IDs and intersection weights
    - creates the remapping NetCDF
    - verifies the written NetCDF
    - records workflow provenance

Usage
-----
python 1_remap_summa_catchments_to_routing.py \
    /path/to/control_DOMAIN.txt
"""

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

import geopandas as gpd
import netCDF4 as nc4
import numpy as np
import pandas as pd

import easymore.easymore as esmr


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_remap_summa_catchments_to_routing.py "
        "/path/to/control_DOMAIN.txt"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).expanduser().resolve()


if not CONTROL_FILE.exists():

    raise FileNotFoundError(
        "Control file not found:\n"
        f"{CONTROL_FILE}"
    )


if not CONTROL_FILE.is_file():

    raise RuntimeError(
        "Control-file path is not a file:\n"
        f"{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(
    file,
    setting
):
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


def make_default_path(
    suffix
):
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


def resolve_path(
    setting,
    default_suffix
):
    """
    Resolve a path setting that may be 'default'.
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
    ).expanduser().resolve()


def convert_integer_ids(
    values,
    name
):
    """
    Validate ID values and return int64.
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


def validate_int32(
    values,
    name
):
    """
    Ensure IDs fit the NetCDF int32 representation.
    """

    values = np.asarray(
        values,
        dtype=np.int64
    )

    limits = np.iinfo(
        np.int32
    )


    if (
        np.any(values < limits.min)
        or np.any(values > limits.max)
    ):

        raise RuntimeError(
            f"{name} contains values outside "
            "the int32 range."
        )


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# CHECK WHETHER REMAPPING IS REQUIRED
# ============================================================

do_remap = (
    read_from_control(
        CONTROL_FILE,
        "river_basin_needs_remap"
    )
    .strip()
    .lower()
)


if do_remap not in {
    "yes",
    "no",
}:

    raise ValueError(
        "river_basin_needs_remap must be "
        "'yes' or 'no'."
    )


if do_remap == "no":

    print()
    print("=" * 70)
    print("MIZUROUTE OPTIONAL REMAPPING")
    print("=" * 70)
    print()
    print(f"Domain       : {domain_name}")
    print(f"Control file : {CONTROL_FILE}")
    print()
    print(
        "river_basin_needs_remap = no"
    )
    print()
    print(
        "SUMMA-to-mizuRoute remapping is not required."
    )
    print(
        "No remapping file was created."
    )
    print()
    print(
        "No control_active.txt was created or modified."
    )

    sys.exit(0)


# ============================================================
# HYDROLOGIC MODEL CATCHMENTS
# ============================================================
#
# For SUMMA, runoff is routed at the GRU level.
#
# Use the prepared Stage-00 catchment rather than the original
# source shapefile.

hm_catchment_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
)


hm_gru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_gruid"
)


hm_catchment_path = make_default_path(
    "shapefiles/catchment"
)


hm_catchment_file = (
    hm_catchment_path
    / hm_catchment_name
)


# ============================================================
# ROUTING MODEL CATCHMENTS
# ============================================================
#
# If the routing-basin path is explicitly configured, use it.
#
# Otherwise use the standard prepared routing-basin directory.

rm_catchment_path = resolve_path(
    "river_basin_shp_path",
    "shapefiles/river_basins"
)


rm_catchment_name = read_from_control(
    CONTROL_FILE,
    "river_basin_shp_name"
)


rm_hru_field = read_from_control(
    CONTROL_FILE,
    "river_basin_shp_rm_hruid"
)


rm_catchment_file = (
    rm_catchment_path
    / rm_catchment_name
)


# ============================================================
# INTERSECTION OUTPUT
# ============================================================

intersect_path = resolve_path(
    "intersect_routing_path",
    "shapefiles/catchment_intersection/with_routing"
)


intersect_name = read_from_control(
    CONTROL_FILE,
    "intersect_routing_name"
)


intersect_path.mkdir(
    parents=True,
    exist_ok=True
)


intersect_file = (
    intersect_path
    / intersect_name
)


# ============================================================
# REMAPPING NETCDF OUTPUT
# ============================================================

remap_path = resolve_path(
    "settings_mizu_path",
    "settings/mizuRoute"
)


remap_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_remap"
)


remap_path.mkdir(
    parents=True,
    exist_ok=True
)


remap_file = (
    remap_path
    / remap_name
)


# ============================================================
# VALIDATE INPUT FILES
# ============================================================

if not hm_catchment_file.exists():

    raise FileNotFoundError(
        "Prepared SUMMA catchment shapefile "
        "not found:\n"
        f"{hm_catchment_file}"
    )


if not rm_catchment_file.exists():

    raise FileNotFoundError(
        "Prepared mizuRoute catchment shapefile "
        "not found:\n"
        f"{rm_catchment_file}"
    )


# ============================================================
# READ SHAPEFILES
# ============================================================

hm_shape = gpd.read_file(
    hm_catchment_file,
    engine="fiona"
)


rm_shape = gpd.read_file(
    rm_catchment_file,
    engine="fiona"
)


if len(hm_shape) == 0:

    raise RuntimeError(
        "SUMMA catchment shapefile contains "
        "no features."
    )


if len(rm_shape) == 0:

    raise RuntimeError(
        "mizuRoute catchment shapefile contains "
        "no features."
    )


if hm_shape.crs is None:

    raise RuntimeError(
        "SUMMA catchment shapefile has no CRS."
    )


if rm_shape.crs is None:

    raise RuntimeError(
        "mizuRoute catchment shapefile has no CRS."
    )


# ============================================================
# VALIDATE REQUIRED FIELDS
# ============================================================

if hm_gru_field not in hm_shape.columns:

    raise RuntimeError(
        "SUMMA GRU field not found:\n"
        f"{hm_gru_field}"
    )


if rm_hru_field not in rm_shape.columns:

    raise RuntimeError(
        "mizuRoute HRU field not found:\n"
        f"{rm_hru_field}"
    )


# ============================================================
# VALIDATE IDS
# ============================================================

hm_gru_ids = convert_integer_ids(
    hm_shape[
        hm_gru_field
    ],
    hm_gru_field
)


rm_hru_ids = convert_integer_ids(
    rm_shape[
        rm_hru_field
    ],
    rm_hru_field
)


if len(
    np.unique(
        hm_gru_ids
    )
) != len(
    hm_gru_ids
):

    raise RuntimeError(
        "Duplicate SUMMA GRU IDs found."
    )


if len(
    np.unique(
        rm_hru_ids
    )
) != len(
    rm_hru_ids
):

    raise RuntimeError(
        "Duplicate mizuRoute routing-HRU IDs found."
    )


validate_int32(
    hm_gru_ids,
    "SUMMA GRU IDs"
)


validate_int32(
    rm_hru_ids,
    "mizuRoute HRU IDs"
)


hm_shape[
    hm_gru_field
] = hm_gru_ids


rm_shape[
    rm_hru_field
] = rm_hru_ids


# ============================================================
# VALIDATE GEOMETRIES
# ============================================================

for label, shape in [
    (
        "SUMMA catchment",
        hm_shape
    ),
    (
        "mizuRoute catchment",
        rm_shape
    ),
]:

    if shape.geometry.isna().any():

        raise RuntimeError(
            f"{label} contains missing geometries."
        )


    if shape.geometry.is_empty.any():

        raise RuntimeError(
            f"{label} contains empty geometries."
        )


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("CREATE SUMMA-TO-MIZUROUTE REMAPPING FILE")
print("=" * 70)

print()
print(f"Domain           : {domain_name}")
print(f"Control file     : {CONTROL_FILE}")

print()
print(
    f"SUMMA catchment  : "
    f"{hm_catchment_file}"
)

print(
    f"SUMMA GRU field  : "
    f"{hm_gru_field}"
)

print(
    f"SUMMA GRUs       : "
    f"{len(hm_shape)}"
)

print()
print(
    f"Routing catchment: "
    f"{rm_catchment_file}"
)

print(
    f"Routing HRU field: "
    f"{rm_hru_field}"
)

print(
    f"Routing HRUs     : "
    f"{len(rm_shape)}"
)

print()
print(
    f"Intersection     : "
    f"{intersect_file}"
)

print(
    f"Remapping output : "
    f"{remap_file}"
)


# ============================================================
# PROJECT TO EQUAL-AREA CRS
# ============================================================
#
# Area fractions must be calculated in an equal-area CRS.

equal_area_crs = "EPSG:6933"


hm_equal_area = hm_shape.to_crs(
    equal_area_crs
)


rm_equal_area = rm_shape.to_crs(
    equal_area_crs
)


# ============================================================
# EASYMORE INTERSECTION
# ============================================================

print()
print(
    "Intersecting SUMMA and routing catchments..."
)


esmr_caller = esmr()


intersected_shape = esmr.intersection_shp(
    esmr_caller,
    rm_equal_area,
    hm_equal_area
)


if intersected_shape is None:

    raise RuntimeError(
        "EASYMORE returned no intersection."
    )


if len(intersected_shape) == 0:

    raise RuntimeError(
        "SUMMA and routing catchments do not "
        "produce any intersections."
    )


# ============================================================
# EASYMORE FIELD NAMES
# ============================================================

int_rm_id = (
    "S_1_"
    + rm_hru_field
)


int_hm_id = (
    "S_2_"
    + hm_gru_field
)


int_weight = "AP1N"


required_intersection_fields = [
    int_rm_id,
    int_hm_id,
    int_weight,
]


missing_fields = [
    field
    for field in required_intersection_fields
    if field not in intersected_shape.columns
]


if missing_fields:

    raise RuntimeError(
        "EASYMORE intersection is missing required "
        "field(s):\n"
        + "\n".join(
            f"  {field}"
            for field in missing_fields
        )
        + "\n\nAvailable fields:\n"
        + "\n".join(
            f"  {field}"
            for field
            in intersected_shape.columns
        )
    )


# ============================================================
# CONVERT INTERSECTION FIELDS
# ============================================================

intersected_shape[
    int_rm_id
] = convert_integer_ids(
    intersected_shape[
        int_rm_id
    ],
    int_rm_id
)


intersected_shape[
    int_hm_id
] = convert_integer_ids(
    intersected_shape[
        int_hm_id
    ],
    int_hm_id
)


try:

    weights = pd.to_numeric(
        intersected_shape[
            int_weight
        ],
        errors="raise"
    ).to_numpy(
        dtype=np.float64
    )

except Exception as exc:

    raise RuntimeError(
        "Could not convert EASYMORE overlap "
        "weights to numeric values."
    ) from exc


if not np.all(
    np.isfinite(
        weights
    )
):

    raise RuntimeError(
        "Non-finite EASYMORE overlap weights found."
    )


if np.any(
    weights < 0
):

    raise RuntimeError(
        "Negative EASYMORE overlap weights found."
    )


intersected_shape[
    int_weight
] = weights


# ============================================================
# VALIDATE INTERSECTION IDS
# ============================================================

rm_id_set = set(
    rm_hru_ids.tolist()
)


hm_id_set = set(
    hm_gru_ids.tolist()
)


unexpected_rm_ids = sorted(
    set(
        intersected_shape[
            int_rm_id
        ].tolist()
    )
    - rm_id_set
)


unexpected_hm_ids = sorted(
    set(
        intersected_shape[
            int_hm_id
        ].tolist()
    )
    - hm_id_set
)


if unexpected_rm_ids:

    raise RuntimeError(
        "Intersection contains unexpected routing "
        "HRU IDs:\n"
        f"{unexpected_rm_ids}"
    )


if unexpected_hm_ids:

    raise RuntimeError(
        "Intersection contains unexpected SUMMA "
        "GRU IDs:\n"
        f"{unexpected_hm_ids}"
    )


# ============================================================
# VERIFY EVERY ROUTING HRU HAS AN OVERLAP
# ============================================================

intersected_rm_set = set(
    intersected_shape[
        int_rm_id
    ].tolist()
)


missing_rm_hrus = sorted(
    rm_id_set
    - intersected_rm_set
)


if missing_rm_hrus:

    raise RuntimeError(
        "The following routing HRUs have no "
        "SUMMA catchment overlap:\n"
        f"{missing_rm_hrus}"
    )


# ============================================================
# SAVE INTERSECTION SHAPEFILE
# ============================================================

# Store final intersection in WGS84 for convenient inspection.

intersected_output = (
    intersected_shape
    .to_crs(
        "EPSG:4326"
    )
)


# Remove existing shapefile components before writing.

for extension in [
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".sbn",
    ".sbx",
    ".qix",
]:

    old_file = (
        intersect_path
        / (
            intersect_file.stem
            + extension
        )
    )

    if old_file.exists():

        old_file.unlink()


intersected_output.to_file(
    intersect_file,
    driver="ESRI Shapefile",
    engine="fiona",
    index=False
)


# ============================================================
# SORT FOR MIZUROUTE REMAPPING
# ============================================================

intersected_shape = (
    intersected_shape
    .sort_values(
        by=[
            int_rm_id,
            int_hm_id,
        ],
        kind="stable"
    )
    .reset_index(
        drop=True
    )
)


# ============================================================
# BUILD REMAPPING ARRAYS
# ============================================================
#
# Important:
#
# RN_hruId and nOverlaps must correspond to the same routing-HRU
# order.
#
# Use the routing-shapefile order as authoritative rather than
# relying on pandas groupby sorting.

rn_hru_ids = (
    rm_hru_ids
    .astype(
        np.int64
    )
)


n_overlaps = np.zeros(
    len(
        rn_hru_ids
    ),
    dtype=np.int32
)


hm_gru_output = []
weight_output = []


for index, routing_hru in enumerate(
    rn_hru_ids
):

    subset = intersected_shape.loc[
        intersected_shape[
            int_rm_id
        ]
        == routing_hru
    ].copy()


    if len(subset) == 0:

        raise RuntimeError(
            "Routing HRU unexpectedly has no "
            f"intersection: {int(routing_hru)}"
        )


    subset = (
        subset
        .sort_values(
            by=int_hm_id,
            kind="stable"
        )
    )


    n_overlaps[
        index
    ] = len(
        subset
    )


    hm_gru_output.extend(
        subset[
            int_hm_id
        ]
        .astype(
            np.int64
        )
        .tolist()
    )


    weight_output.extend(
        subset[
            int_weight
        ]
        .astype(
            np.float64
        )
        .tolist()
    )


hm_gru_output = np.asarray(
    hm_gru_output,
    dtype=np.int64
)


weight_output = np.asarray(
    weight_output,
    dtype=np.float64
)


# ============================================================
# VALIDATE REMAPPING ARRAYS
# ============================================================

num_hru = len(
    rn_hru_ids
)


num_data = len(
    hm_gru_output
)


if num_data != len(
    weight_output
):

    raise RuntimeError(
        "HM_hruId and weight lengths differ."
    )


if int(
    n_overlaps.sum()
) != num_data:

    raise RuntimeError(
        "Sum of nOverlaps does not equal "
        "the remapping data dimension."
    )


if np.any(
    n_overlaps <= 0
):

    raise RuntimeError(
        "One or more routing HRUs have "
        "zero overlaps."
    )


validate_int32(
    rn_hru_ids,
    "RN_hruId"
)


validate_int32(
    hm_gru_output,
    "HM_hruId"
)


# ============================================================
# CHECK WEIGHT SUMS
# ============================================================
#
# EASYMORE AP1N weights should represent the contribution
# fractions associated with each routing HRU.
#
# Report weight totals. Small floating-point deviations from 1
# are acceptable, but gross errors indicate a problem.

weight_sums = []


offset = 0


for overlap_count in n_overlaps:

    next_offset = (
        offset
        + int(
            overlap_count
        )
    )


    total = float(
        np.sum(
            weight_output[
                offset:next_offset
            ]
        )
    )


    weight_sums.append(
        total
    )


    offset = next_offset


weight_sums = np.asarray(
    weight_sums,
    dtype=np.float64
)


if not np.all(
    np.isfinite(
        weight_sums
    )
):

    raise RuntimeError(
        "Non-finite routing-HRU weight sums found."
    )


print()
print(
    f"Intersection rows : {num_data}"
)

print(
    f"Weight-sum range  : "
    f"{weight_sums.min():.8f} to "
    f"{weight_sums.max():.8f}"
)


# Do not require machine-precision equality because geometric
# intersections can introduce small numerical differences.

bad_weight_sums = np.where(
    ~np.isclose(
        weight_sums,
        1.0,
        rtol=0.0,
        atol=1.0e-4
    )
)[0]


if len(
    bad_weight_sums
) > 0:

    bad_ids = [
        int(
            rn_hru_ids[
                index
            ]
        )
        for index
        in bad_weight_sums
    ]


    bad_values = [
        float(
            weight_sums[
                index
            ]
        )
        for index
        in bad_weight_sums
    ]


    print()
    print(
        "WARNING:"
    )

    print(
        "Some routing HRU overlap weights "
        "do not sum to 1 within tolerance."
    )

    print(
        "Routing HRUs:"
    )

    for hru, value in zip(
        bad_ids,
        bad_values
    ):

        print(
            f"  {hru}: {value:.8f}"
        )


# ============================================================
# WRITE REMAPPING NETCDF
# ============================================================

with nc4.Dataset(
    remap_file,
    "w",
    format="NETCDF4"
) as ncid:

    now = datetime.now()


    # --------------------------------------------------------
    # Global attributes
    # --------------------------------------------------------

    ncid.setncattr(
        "Author",
        "NWAM-SUMMA workflow"
    )


    ncid.setncattr(
        "History",
        "Created "
        + now.strftime(
            "%Y/%m/%d %H:%M:%S"
        )
    )


    ncid.setncattr(
        "Purpose",
        "SUMMA GRU to mizuRoute routing-HRU remapping"
    )


    ncid.setncattr(
        "Domain",
        domain_name
    )


    ncid.setncattr(
        "Control_file",
        str(
            CONTROL_FILE
        )
    )


    # --------------------------------------------------------
    # Dimensions
    # --------------------------------------------------------

    ncid.createDimension(
        "hru",
        num_hru
    )


    ncid.createDimension(
        "data",
        num_data
    )


    # --------------------------------------------------------
    # RN_hruId
    # --------------------------------------------------------

    variable = ncid.createVariable(
        "RN_hruId",
        "i4",
        (
            "hru",
        )
    )


    variable[:] = (
        rn_hru_ids
        .astype(
            np.int32
        )
    )


    variable.setncattr(
        "long_name",
        "River network HRU ID"
    )


    variable.setncattr(
        "units",
        "-"
    )


    # --------------------------------------------------------
    # nOverlaps
    # --------------------------------------------------------

    variable = ncid.createVariable(
        "nOverlaps",
        "i4",
        (
            "hru",
        )
    )


    variable[:] = (
        n_overlaps
    )


    variable.setncattr(
        "long_name",
        "Number of overlapping SUMMA GRUs "
        "for each routing HRU"
    )


    variable.setncattr(
        "units",
        "-"
    )


    # --------------------------------------------------------
    # HM_hruId
    # --------------------------------------------------------

    variable = ncid.createVariable(
        "HM_hruId",
        "i4",
        (
            "data",
        )
    )


    variable[:] = (
        hm_gru_output
        .astype(
            np.int32
        )
    )


    variable.setncattr(
        "long_name",
        "Overlapping hydrologic-model HRU IDs; "
        "SUMMA refers to these as GRUs"
    )


    variable.setncattr(
        "units",
        "-"
    )


    # --------------------------------------------------------
    # weight
    # --------------------------------------------------------

    variable = ncid.createVariable(
        "weight",
        "f8",
        (
            "data",
        )
    )


    variable[:] = (
        weight_output
    )


    variable.setncattr(
        "long_name",
        "Areal weight of overlapping SUMMA GRUs"
    )


    variable.setncattr(
        "units",
        "-"
    )


# ============================================================
# VERIFY WRITTEN NETCDF
# ============================================================

with nc4.Dataset(
    remap_file,
    "r"
) as check:

    required_dimensions = {
        "hru",
        "data",
    }


    required_variables = {
        "RN_hruId",
        "nOverlaps",
        "HM_hruId",
        "weight",
    }


    missing_dimensions = (
        required_dimensions
        - set(
            check.dimensions.keys()
        )
    )


    missing_variables = (
        required_variables
        - set(
            check.variables.keys()
        )
    )


    if missing_dimensions:

        raise RuntimeError(
            "Remapping NetCDF is missing "
            f"dimension(s): {sorted(missing_dimensions)}"
        )


    if missing_variables:

        raise RuntimeError(
            "Remapping NetCDF is missing "
            f"variable(s): {sorted(missing_variables)}"
        )


    if len(
        check.dimensions[
            "hru"
        ]
    ) != num_hru:

        raise RuntimeError(
            "Incorrect hru dimension in remapping file."
        )


    if len(
        check.dimensions[
            "data"
        ]
    ) != num_data:

        raise RuntimeError(
            "Incorrect data dimension in remapping file."
        )


    saved_rn_hru = np.asarray(
        check[
            "RN_hruId"
        ][:],
        dtype=np.int64
    )


    saved_n_overlaps = np.asarray(
        check[
            "nOverlaps"
        ][:],
        dtype=np.int64
    )


    saved_hm_hru = np.asarray(
        check[
            "HM_hruId"
        ][:],
        dtype=np.int64
    )


    saved_weights = np.asarray(
        check[
            "weight"
        ][:],
        dtype=np.float64
    )


if not np.array_equal(
    saved_rn_hru,
    rn_hru_ids
):

    raise RuntimeError(
        "RN_hruId changed while writing NetCDF."
    )


if not np.array_equal(
    saved_n_overlaps,
    n_overlaps.astype(
        np.int64
    )
):

    raise RuntimeError(
        "nOverlaps changed while writing NetCDF."
    )


if not np.array_equal(
    saved_hm_hru,
    hm_gru_output
):

    raise RuntimeError(
        "HM_hruId changed while writing NetCDF."
    )


if not np.allclose(
    saved_weights,
    weight_output,
    rtol=0.0,
    atol=0.0
):

    raise RuntimeError(
        "Remapping weights changed while "
        "writing NetCDF."
    )


if not np.all(
    np.isfinite(
        saved_weights
    )
):

    raise RuntimeError(
        "Non-finite weights exist in written "
        "remapping file."
    )


if np.any(
    saved_weights < 0
):

    raise RuntimeError(
        "Negative weights exist in written "
        "remapping file."
    )


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    remap_path
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
        "create_mizuroute_remapping.txt"
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
        f"SUMMA catchment: "
        f"{hm_catchment_file}\n"
    )


    file.write(
        f"Routing catchment: "
        f"{rm_catchment_file}\n"
    )


    file.write(
        f"SUMMA GRUs: "
        f"{len(hm_shape)}\n"
    )


    file.write(
        f"Routing HRUs: "
        f"{num_hru}\n"
    )


    file.write(
        f"Intersection records: "
        f"{num_data}\n"
    )


    file.write(
        f"Weight-sum range: "
        f"{weight_sums.min():.8f} to "
        f"{weight_sums.max():.8f}\n"
    )


    file.write(
        f"Intersection output: "
        f"{intersect_file}\n"
    )


    file.write(
        f"Remapping output: "
        f"{remap_file}\n"
    )


    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("MIZUROUTE REMAPPING FILE CREATION COMPLETED")
print("=" * 70)

print(
    f"Domain             : {domain_name}"
)

print(
    f"SUMMA GRUs         : {len(hm_shape)}"
)

print(
    f"Routing HRUs       : {num_hru}"
)

print(
    f"Intersection rows  : {num_data}"
)

print(
    f"Weight-sum range   : "
    f"{weight_sums.min():.8f} - "
    f"{weight_sums.max():.8f}"
)

print(
    f"Intersection       : {intersect_file}"
)

print(
    f"Remapping NetCDF   : {remap_file}"
)

print(
    f"Workflow log       : {log_file}"
)

print()
print(
    "Remapping NetCDF validation passed."
)

print(
    "No control_active.txt was created or modified."
)