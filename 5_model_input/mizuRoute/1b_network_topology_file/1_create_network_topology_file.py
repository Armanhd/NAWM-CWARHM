#!/usr/bin/env python3
# coding: utf-8

# Create mizuRoute topology.nc for a selected NWAM/CWARHM domain.
#
# Purpose
# -------
# Translate the prepared Stage-00 river-network and routing-basin
# shapefiles into the topology structure required by mizuRoute.
#
# Output dimensions
# -----------------
#   seg : number of retained river segments
#   hru : number of routing HRUs
#
# Output variables
# ----------------
#   segId       : unique river-segment ID
#   downSegId   : downstream river-segment ID
#   slope       : river-segment slope
#   length      : river-segment length [m]
#   hruId       : routing-HRU ID
#   hruToSegId  : segment receiving runoff from each HRU
#   area        : routing-HRU area [m2]
#
# Outlet handling
# ---------------
# There are two possible outlet types.
#
# 1. Natural clipped-domain outlets
#
#    If the source NextDownID points to a segment that is not
#    contained in the prepared river-network shapefile, this
#    segment leaves the retained domain. Its downSegId is
#    therefore automatically changed to 0.
#
# 2. Explicitly forced outlets
#
#    settings_mizu_make_outlet may contain:
#
#       n/a
#
#    or one/multiple segment IDs:
#
#       12345
#       12345,67890
#
#    Those segments are explicitly assigned downSegId = 0.
#
# IMPORTANT
# ---------
# This script uses the Stage-00 prepared domain shapefiles:
#
#   domain_<name>/shapefiles/river_network/
#   domain_<name>/shapefiles/catchment/
#
# It does not modify the original MERIT source shapefiles.
#
# This script does NOT read, create, or modify control_active.txt.
#
# Usage
# -----
# python 1_create_network_topology_file.py \
# /path/to/control_DOMAIN.txt


import sys
from pathlib import Path
from shutil import copy2
from datetime import datetime

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
        "python 1_create_network_topology_file.py "
        "/path/to/control_DOMAIN.txt"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).resolve()


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
# PROJECT PATHS
# ============================================================

SCRIPT_DIR = Path(
    __file__
).resolve().parent


# Script location:
#
# CWARHM_multibasin/
#   5_model_input/
#     mizuRoute/
#       1b_network_topology_file/
#         1_create_network_topology_file.py

CWARHM_ROOT = (
    SCRIPT_DIR.parents[2]
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
    Resolve a control path setting.
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


def validate_int32(
    values,
    name
):
    """
    Validate IDs before writing them as NetCDF int32.
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
            f"{name} contains values outside the "
            "32-bit integer range required by the "
            "current mizuRoute topology format."
        )


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# PREPARED RIVER NETWORK
# ============================================================

river_network_name = read_from_control(
    CONTROL_FILE,
    "river_network_shp_name"
)


# IMPORTANT:
# Use Stage-00 prepared network rather than original MERIT source.

river_network_path = make_default_path(
    "shapefiles/river_network"
)


river_file = (
    river_network_path
    / river_network_name
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


# ============================================================
# PREPARED ROUTING BASINS
# ============================================================

river_basin_name = read_from_control(
    CONTROL_FILE,
    "river_basin_shp_name"
)


# Stage 00 places the prepared routing-basin representation in
# the domain catchment directory.

river_basin_path = make_default_path(
    "shapefiles/catchment"
)


basin_file = (
    river_basin_path
    / river_basin_name
)


basin_hru_id = read_from_control(
    CONTROL_FILE,
    "river_basin_shp_rm_hruid"
)


basin_hru_area = read_from_control(
    CONTROL_FILE,
    "river_basin_shp_area"
)


basin_hru_to_seg = read_from_control(
    CONTROL_FILE,
    "river_basin_shp_hru_to_seg"
)


# ============================================================
# OUTPUT
# ============================================================

topology_path = resolve_path(
    "settings_mizu_path",
    "settings/mizuRoute"
)


topology_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_topology"
)


topology_path.mkdir(
    parents=True,
    exist_ok=True
)


topology_file = (
    topology_path
    / topology_name
)


# ============================================================
# VALIDATE INPUT FILES
# ============================================================

if not river_file.exists():

    raise FileNotFoundError(
        "Prepared river-network shapefile not found:\n"
        f"{river_file}\n\n"
        "Run Stage 00 first."
    )


if not basin_file.exists():

    raise FileNotFoundError(
        "Prepared routing-basin shapefile not found:\n"
        f"{basin_file}\n\n"
        "Run Stage 00 first."
    )


# ============================================================
# READ SHAPEFILES
# ============================================================

shp_river = gpd.read_file(
    river_file
)


shp_basin = gpd.read_file(
    basin_file
)


if len(shp_river) == 0:

    raise RuntimeError(
        "Prepared river-network shapefile "
        "contains no features."
    )


if len(shp_basin) == 0:

    raise RuntimeError(
        "Prepared routing-basin shapefile "
        "contains no features."
    )


# ============================================================
# VALIDATE REQUIRED FIELDS
# ============================================================

river_required_fields = [
    river_seg_id,
    river_down_seg_id,
    river_slope,
    river_length,
]


basin_required_fields = [
    basin_hru_id,
    basin_hru_area,
    basin_hru_to_seg,
]


missing_river_fields = [
    field
    for field in river_required_fields
    if field not in shp_river.columns
]


missing_basin_fields = [
    field
    for field in basin_required_fields
    if field not in shp_basin.columns
]


if missing_river_fields:

    raise RuntimeError(
        "Prepared river network is missing "
        "required field(s):\n"
        + "\n".join(
            f"  {field}"
            for field in missing_river_fields
        )
    )


if missing_basin_fields:

    raise RuntimeError(
        "Prepared routing basins are missing "
        "required field(s):\n"
        + "\n".join(
            f"  {field}"
            for field in missing_basin_fields
        )
    )


# ============================================================
# CONVERT REQUIRED FIELDS
# ============================================================

try:

    seg_ids = pd.to_numeric(
        shp_river[
            river_seg_id
        ],
        errors="raise"
    ).to_numpy(
        dtype=np.int64
    )


    original_down_seg_ids = pd.to_numeric(
        shp_river[
            river_down_seg_id
        ],
        errors="raise"
    ).to_numpy(
        dtype=np.int64
    )


    down_seg_ids = (
        original_down_seg_ids.copy()
    )


    slopes = pd.to_numeric(
        shp_river[
            river_slope
        ],
        errors="raise"
    ).to_numpy(
        dtype=np.float64
    )


    lengths = pd.to_numeric(
        shp_river[
            river_length
        ],
        errors="raise"
    ).to_numpy(
        dtype=np.float64
    )


    hru_ids = pd.to_numeric(
        shp_basin[
            basin_hru_id
        ],
        errors="raise"
    ).to_numpy(
        dtype=np.int64
    )


    hru_to_seg_ids = pd.to_numeric(
        shp_basin[
            basin_hru_to_seg
        ],
        errors="raise"
    ).to_numpy(
        dtype=np.int64
    )


    areas = pd.to_numeric(
        shp_basin[
            basin_hru_area
        ],
        errors="raise"
    ).to_numpy(
        dtype=np.float64
    )


except Exception as exc:

    raise RuntimeError(
        "Could not convert one or more required "
        "topology fields to numeric values."
    ) from exc


# ============================================================
# BASIC ARRAY VALIDATION
# ============================================================

num_seg = len(
    seg_ids
)


num_hru = len(
    hru_ids
)


if not (
    len(down_seg_ids)
    == len(slopes)
    == len(lengths)
    == num_seg
):

    raise RuntimeError(
        "River-network variable lengths are inconsistent."
    )


if not (
    len(hru_to_seg_ids)
    == len(areas)
    == num_hru
):

    raise RuntimeError(
        "Routing-HRU variable lengths are inconsistent."
    )


# ============================================================
# VALIDATE UNIQUE IDS
# ============================================================

if len(
    np.unique(
        seg_ids
    )
) != num_seg:

    values, counts = np.unique(
        seg_ids,
        return_counts=True
    )

    duplicate_ids = values[
        counts > 1
    ].astype(
        int
    ).tolist()

    raise RuntimeError(
        "Duplicate stream-segment IDs detected:\n"
        f"{duplicate_ids}"
    )


if len(
    np.unique(
        hru_ids
    )
) != num_hru:

    values, counts = np.unique(
        hru_ids,
        return_counts=True
    )

    duplicate_ids = values[
        counts > 1
    ].astype(
        int
    ).tolist()

    raise RuntimeError(
        "Duplicate routing-HRU IDs detected:\n"
        f"{duplicate_ids}"
    )


# ============================================================
# INT32 SAFETY
# ============================================================

validate_int32(
    seg_ids,
    "segId"
)


validate_int32(
    original_down_seg_ids,
    "source downSegId"
)


validate_int32(
    hru_ids,
    "hruId"
)


validate_int32(
    hru_to_seg_ids,
    "hruToSegId"
)


# ============================================================
# VALIDATE PHYSICAL VARIABLES
# ============================================================

if not np.all(
    np.isfinite(
        slopes
    )
):

    raise RuntimeError(
        "Non-finite river slope values detected."
    )


if np.any(
    slopes < 0
):

    raise RuntimeError(
        "Negative river slope values detected."
    )


if not np.all(
    np.isfinite(
        lengths
    )
):

    raise RuntimeError(
        "Non-finite river length values detected."
    )


# Retain historical CWARHM safety behavior.

bad_lengths = (
    lengths <= 0
)


if np.any(
    bad_lengths
):

    number_bad = int(
        np.count_nonzero(
            bad_lengths
        )
    )

    print()
    print(
        "WARNING:"
    )

    print(
        f"{number_bad} river segment(s) "
        "have length <= 0."
    )

    print(
        "These values will be replaced with 1 m."
    )

    lengths[
        bad_lengths
    ] = 1.0


if not np.all(
    np.isfinite(
        areas
    )
):

    raise RuntimeError(
        "Non-finite routing-HRU area values detected."
    )


if np.any(
    areas <= 0
):

    raise RuntimeError(
        "Routing-HRU areas must be greater than zero."
    )


# ============================================================
# SEGMENT SET
# ============================================================

segment_set = set(
    int(value)
    for value in seg_ids
)


# ============================================================
# NATURAL CLIPPED-DOMAIN OUTLETS
# ============================================================

# A MERIT segment may have a valid source NextDownID that is
# outside this retained Pfaf/domain network.
#
# From the perspective of the current mizuRoute model domain,
# such segments are outlets and must have downSegId = 0.

external_downstream_mask = np.asarray(
    [
        (
            int(value) != 0
            and int(value) not in segment_set
        )
        for value in down_seg_ids
    ],
    dtype=bool
)


natural_outlet_segments = (
    seg_ids[
        external_downstream_mask
    ]
    .astype(
        np.int64
    )
)


natural_external_down_ids = (
    down_seg_ids[
        external_downstream_mask
    ]
    .astype(
        np.int64
    )
)


if len(
    natural_outlet_segments
) > 0:

    down_seg_ids[
        external_downstream_mask
    ] = 0


# ============================================================
# EXPLICIT OUTLET SETTING
# ============================================================

outlet_setting = read_from_control(
    CONTROL_FILE,
    "settings_mizu_make_outlet"
).strip()


if outlet_setting.lower() in {
    "",
    "n/a",
    "na",
    "none",
}:

    requested_outlets = []

else:

    try:

        requested_outlets = [
            int(
                value.strip()
            )
            for value in outlet_setting.split(",")
            if value.strip()
        ]

    except ValueError as exc:

        raise ValueError(
            "settings_mizu_make_outlet must be "
            "'n/a' or a comma-separated list "
            "of integer segment IDs."
        ) from exc


# Remove accidental duplicates while preserving order.

requested_outlets = list(
    dict.fromkeys(
        requested_outlets
    )
)


missing_requested_outlets = [
    outlet
    for outlet in requested_outlets
    if outlet not in segment_set
]


if missing_requested_outlets:

    raise RuntimeError(
        "Requested forced outlet segment(s) "
        "were not found in the prepared network:\n"
        f"{missing_requested_outlets}"
    )


forced_outlet_changes = []


for outlet_id in requested_outlets:

    positions = np.where(
        seg_ids == outlet_id
    )[0]


    position = int(
        positions[0]
    )


    original_value = int(
        down_seg_ids[
            position
        ]
    )


    down_seg_ids[
        position
    ] = 0


    forced_outlet_changes.append(
        (
            int(outlet_id),
            original_value
        )
    )


# ============================================================
# VALIDATE NETWORK CONNECTIVITY
# ============================================================

# After natural and explicit outlet handling, every remaining
# non-zero downstream segment must exist within the domain.

invalid_downstream = sorted(
    {
        int(value)
        for value in down_seg_ids
        if (
            int(value) != 0
            and int(value) not in segment_set
        )
    }
)


if invalid_downstream:

    raise RuntimeError(
        "Invalid downstream segment IDs remain "
        "after outlet processing:\n"
        f"{invalid_downstream}"
    )


# Detect self loops.

self_loop_mask = (
    down_seg_ids
    == seg_ids
)


if np.any(
    self_loop_mask
):

    self_loop_segments = (
        seg_ids[
            self_loop_mask
        ]
        .astype(
            int
        )
        .tolist()
    )

    raise RuntimeError(
        "Self-looping river segments detected:\n"
        f"{self_loop_segments}"
    )


# Every routing HRU must map to a segment retained in the
# topology.

invalid_hru_links = sorted(
    {
        int(value)
        for value in hru_to_seg_ids
        if int(value) not in segment_set
    }
)


if invalid_hru_links:

    raise RuntimeError(
        "The following hruToSegId values do not "
        "exist in the prepared river network:\n"
        f"{invalid_hru_links}"
    )


# ============================================================
# FINAL OUTLETS
# ============================================================

outlet_segments = (
    seg_ids[
        down_seg_ids == 0
    ]
    .astype(
        np.int64
    )
)


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("CREATE MIZUROUTE TOPOLOGY")
print("=" * 70)

print(
    f"Domain              : {domain_name}"
)

print(
    f"Control file        : {CONTROL_FILE}"
)

print(
    f"River network       : {river_file}"
)

print(
    f"Routing basins      : {basin_file}"
)

print(
    f"Output              : {topology_file}"
)

print()

print(
    f"Segments            : {num_seg}"
)

print(
    f"Routing HRUs        : {num_hru}"
)

print(
    f"Natural outlets     : {len(natural_outlet_segments)}"
)

print(
    f"Explicit outlets    : {len(requested_outlets)}"
)

print(
    f"Final outlet count  : {len(outlet_segments)}"
)

print()


if len(
    natural_outlet_segments
):

    print(
        "Natural clipped-domain outlets:"
    )

    for (
        segment,
        external_downstream
    ) in zip(
        natural_outlet_segments,
        natural_external_down_ids
    ):

        print(
            f"  {int(segment)}: "
            f"{int(external_downstream)} -> 0"
        )


if forced_outlet_changes:

    print()

    print(
        "Explicitly forced outlets:"
    )

    for (
        segment,
        original_downstream
    ) in forced_outlet_changes:

        print(
            f"  {segment}: "
            f"{original_downstream} -> 0"
        )


print()

print(
    "Final outlet segments:"
)

print(
    outlet_segments.tolist()
)

print()

print(
    f"Slope range         : "
    f"{slopes.min():.8g} to "
    f"{slopes.max():.8g}"
)

print(
    f"Length range        : "
    f"{lengths.min():.3f} to "
    f"{lengths.max():.3f} m"
)

print(
    f"Area range          : "
    f"{areas.min():.3f} to "
    f"{areas.max():.3f} m2"
)


# ============================================================
# NETCDF HELPER
# ============================================================

def create_and_fill_nc_var(
    ncid,
    var_name,
    var_type,
    dimension,
    data,
    long_name,
    units
):
    """
    Create and populate a one-dimensional NetCDF variable.
    """

    variable = ncid.createVariable(
        var_name,
        var_type,
        (
            dimension,
        )
    )


    variable[:] = data


    variable.setncattr(
        "long_name",
        long_name
    )


    variable.setncattr(
        "units",
        units
    )


# ============================================================
# WRITE topology.nc
# ============================================================

with nc4.Dataset(
    topology_file,
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
        "mizuRoute river-network topology"
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
        "seg",
        num_seg
    )


    ncid.createDimension(
        "hru",
        num_hru
    )


    # --------------------------------------------------------
    # Segment variables
    # --------------------------------------------------------

    create_and_fill_nc_var(
        ncid,
        "segId",
        "i4",
        "seg",
        seg_ids.astype(
            np.int32
        ),
        "Unique ID of each stream segment",
        "-"
    )


    create_and_fill_nc_var(
        ncid,
        "downSegId",
        "i4",
        "seg",
        down_seg_ids.astype(
            np.int32
        ),
        "ID of the downstream stream segment",
        "-"
    )


    create_and_fill_nc_var(
        ncid,
        "slope",
        "f8",
        "seg",
        slopes.astype(
            np.float64
        ),
        "Stream-segment slope",
        "m m-1"
    )


    create_and_fill_nc_var(
        ncid,
        "length",
        "f8",
        "seg",
        lengths.astype(
            np.float64
        ),
        "Stream-segment length",
        "m"
    )


    # --------------------------------------------------------
    # Routing-HRU variables
    # --------------------------------------------------------

    create_and_fill_nc_var(
        ncid,
        "hruId",
        "i4",
        "hru",
        hru_ids.astype(
            np.int32
        ),
        "Unique routing-HRU ID",
        "-"
    )


    create_and_fill_nc_var(
        ncid,
        "hruToSegId",
        "i4",
        "hru",
        hru_to_seg_ids.astype(
            np.int32
        ),
        "ID of stream segment receiving HRU runoff",
        "-"
    )


    create_and_fill_nc_var(
        ncid,
        "area",
        "f8",
        "hru",
        areas.astype(
            np.float64
        ),
        "Routing-HRU area",
        "m^2"
    )


# ============================================================
# VERIFY WRITTEN FILE
# ============================================================

with nc4.Dataset(
    topology_file,
    "r"
) as check:

    required_dimensions = {
        "seg",
        "hru",
    }


    required_variables = {
        "segId",
        "downSegId",
        "slope",
        "length",
        "hruId",
        "hruToSegId",
        "area",
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
            "Written topology.nc is missing "
            f"dimension(s): {sorted(missing_dimensions)}"
        )


    if missing_variables:

        raise RuntimeError(
            "Written topology.nc is missing "
            f"variable(s): {sorted(missing_variables)}"
        )


    if len(
        check.dimensions["seg"]
    ) != num_seg:

        raise RuntimeError(
            "Written topology.nc has incorrect "
            "segment dimension."
        )


    if len(
        check.dimensions["hru"]
    ) != num_hru:

        raise RuntimeError(
            "Written topology.nc has incorrect "
            "routing-HRU dimension."
        )


    written_seg_ids = np.asarray(
        check[
            "segId"
        ][:],
        dtype=np.int64
    )


    written_down_ids = np.asarray(
        check[
            "downSegId"
        ][:],
        dtype=np.int64
    )


    written_hru_ids = np.asarray(
        check[
            "hruId"
        ][:],
        dtype=np.int64
    )


    written_hru_to_seg = np.asarray(
        check[
            "hruToSegId"
        ][:],
        dtype=np.int64
    )


    written_slopes = np.asarray(
        check[
            "slope"
        ][:],
        dtype=np.float64
    )


    written_lengths = np.asarray(
        check[
            "length"
        ][:],
        dtype=np.float64
    )


    written_areas = np.asarray(
        check[
            "area"
        ][:],
        dtype=np.float64
    )


if not np.array_equal(
    written_seg_ids,
    seg_ids
):

    raise RuntimeError(
        "segId changed while writing topology.nc."
    )


if not np.array_equal(
    written_down_ids,
    down_seg_ids
):

    raise RuntimeError(
        "downSegId changed while writing topology.nc."
    )


if not np.array_equal(
    written_hru_ids,
    hru_ids
):

    raise RuntimeError(
        "hruId changed while writing topology.nc."
    )


if not np.array_equal(
    written_hru_to_seg,
    hru_to_seg_ids
):

    raise RuntimeError(
        "hruToSegId changed while writing topology.nc."
    )


if not np.allclose(
    written_slopes,
    slopes
):

    raise RuntimeError(
        "slope changed while writing topology.nc."
    )


if not np.allclose(
    written_lengths,
    lengths
):

    raise RuntimeError(
        "length changed while writing topology.nc."
    )


if not np.allclose(
    written_areas,
    areas
):

    raise RuntimeError(
        "area changed while writing topology.nc."
    )


# Final connectivity verification from written data.

written_segment_set = set(
    written_seg_ids.tolist()
)


invalid_written_downstream = sorted(
    {
        int(value)
        for value in written_down_ids
        if (
            int(value) != 0
            and int(value)
            not in written_segment_set
        )
    }
)


if invalid_written_downstream:

    raise RuntimeError(
        "Written topology.nc contains invalid "
        "downstream segment IDs:\n"
        f"{invalid_written_downstream}"
    )


invalid_written_hru_links = sorted(
    {
        int(value)
        for value in written_hru_to_seg
        if int(value)
        not in written_segment_set
    }
)


if invalid_written_hru_links:

    raise RuntimeError(
        "Written topology.nc contains invalid "
        "HRU-to-segment links:\n"
        f"{invalid_written_hru_links}"
    )


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    topology_path
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
        "create_mizuroute_topology.txt"
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
        f"River network: {river_file}\n"
    )


    file.write(
        f"Routing basins: {basin_file}\n"
    )


    file.write(
        f"Segments: {num_seg}\n"
    )


    file.write(
        f"Routing HRUs: {num_hru}\n"
    )


    file.write(
        f"Natural clipped outlets: "
        f"{natural_outlet_segments.tolist()}\n"
    )


    file.write(
        f"Forced outlets: "
        f"{requested_outlets}\n"
    )


    file.write(
        f"Final outlets: "
        f"{outlet_segments.tolist()}\n"
    )


    file.write(
        f"Output: {topology_file}\n"
    )


    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("MIZUROUTE TOPOLOGY CREATION COMPLETED")
print("=" * 70)

print(
    f"Domain             : {domain_name}"
)

print(
    f"Control file       : {CONTROL_FILE}"
)

print(
    f"Segments           : {num_seg}"
)

print(
    f"Routing HRUs       : {num_hru}"
)

print(
    f"Natural outlets    : {len(natural_outlet_segments)}"
)

print(
    f"Forced outlets     : {len(requested_outlets)}"
)

print(
    f"Final outlets      : {len(outlet_segments)}"
)

print(
    f"Outlet segments    : {outlet_segments.tolist()}"
)

print(
    f"Output             : {topology_file}"
)

print(
    f"Workflow log       : {log_file}"
)

print()
print(
    "Network connectivity validation passed."
)

print(
    "HRU-to-segment validation passed."
)

print(
    "No control_active.txt was created or modified."
)