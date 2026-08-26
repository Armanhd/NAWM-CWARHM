# Create the mizuRoute river-network topology NetCDF.
#
# Core assumption
# ---------------
# Routing is performed between routing HRUs / GRUs.
# The routing-basin shapefile provides the routing HRUs and
# their receiving stream segments, while the river-network
# shapefile provides stream connectivity.
#
# Output topology.nc contains:
#
# Dimensions
# ----------
#   seg : number of river segments
#   hru : number of routing HRUs
#
# Variables
# ---------
#   segId       : unique stream-segment ID
#   downSegId   : downstream stream-segment ID
#   slope       : stream-segment slope
#   length      : stream-segment length [m]
#   hruId       : routing HRU ID
#   hruToSegId  : stream segment receiving runoff from each HRU
#   area        : routing HRU area [m2]
#
# Outlet handling
# ---------------
# settings_mizu_make_outlet may contain:
#
#   n/a
#
# or one/multiple segment IDs:
#
#   12345
#   12345,67890
#
# Requested outlet segments are assigned downSegId = 0
# before network-connectivity validation.
#
# Reproducibility / validation improvements
# -----------------------------------------
#   - robust control-file location based on script location
#   - exact control-setting matching
#   - validates all required files and fields
#   - checks segment and routing-HRU ID uniqueness
#   - validates slope, length and area values
#   - validates requested outlet IDs
#   - applies outlet correction before connectivity checking
#   - verifies downstream-segment connectivity
#   - verifies HRU-to-segment connectivity
#   - verifies written NetCDF structure
#   - records provenance in _workflow_log


from pathlib import Path
from shutil import copyfile
from datetime import datetime

import geopandas as gpd
import numpy as np
import netCDF4 as nc4


# ============================================================
# PROJECT / CONTROL FILE
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

# Script location:
# CWARHM/5_model_input/mizuRoute/1b_network_topology_file/
#
# parents[2] = CWARHM
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
    """
    Read one exact setting from the CWARHM control file.
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

            return (
                right
                .split("#", 1)[0]
                .strip()
            )

    raise ValueError(
        f"Setting not found in control file: {setting}"
    )


def make_default_path(suffix):
    """
    Construct a default path inside domain_<domain_name>.
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
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# RIVER NETWORK SHAPEFILE
# ============================================================

river_network_name = read_from_control(
    CONTROL_FILE,
    "river_network_shp_name"
)

# Stage 00 creates the prepared river-network working copy
# inside the active domain.
#
# Stage 5 must use this prepared copy rather than the raw
# source river-network path from control_active.txt because
# Stage 00 adds standardized fields required by downstream
# workflow steps, including:
#
#   length_m
#
# The raw MERIT source generally contains lengthkm, while the
# prepared domain copy contains:
#
#   length_m = lengthkm * 1000
#
# This mirrors the handling of the prepared routing-basin /
# catchment shapefile below.

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
# ROUTING BASIN SHAPEFILE
# ============================================================

river_basin_name = read_from_control(
    CONTROL_FILE,
    "river_basin_shp_name"
)

# Stage 00 creates the prepared routing-basin/catchment
# working copy in the domain directory. This prepared file
# contains area and hru_to_seg required by mizuRoute.
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
# OUTPUT TOPOLOGY FILE
# ============================================================

topology_path = read_from_control(
    CONTROL_FILE,
    "settings_mizu_path"
)

topology_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_topology"
)

if topology_path == "default":

    topology_path = make_default_path(
        "settings/mizuRoute"
    )

else:

    topology_path = Path(
        topology_path
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
        f"River-network shapefile not found:\n"
        f"{river_file}"
    )


if not basin_file.exists():
    raise FileNotFoundError(
        "Prepared routing-basin shapefile not found:\n"
        f"{basin_file}\n\n"
        "Run Stage 00 before creating topology.nc."
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
        "River-network shapefile contains no features."
    )


if len(shp_basin) == 0:
    raise RuntimeError(
        "Routing-basin shapefile contains no features."
    )


# ============================================================
# VALIDATE REQUIRED FIELDS
# ============================================================

river_required_fields = [
    river_seg_id,
    river_down_seg_id,
    river_slope,
    river_length
]

basin_required_fields = [
    basin_hru_id,
    basin_hru_area,
    basin_hru_to_seg
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
        "Missing required river-network field(s): "
        + ", ".join(missing_river_fields)
    )


if missing_basin_fields:
    raise RuntimeError(
        "Missing required routing-basin field(s): "
        + ", ".join(missing_basin_fields)
    )


# ============================================================
# CONVERT REQUIRED FIELDS TO NUMERIC ARRAYS
# ============================================================

try:

    seg_ids = (
        shp_river[river_seg_id]
        .astype(np.int64)
        .to_numpy()
    )

    down_seg_ids = (
        shp_river[river_down_seg_id]
        .astype(np.int64)
        .to_numpy()
    )

    slopes = (
        shp_river[river_slope]
        .astype(float)
        .to_numpy()
    )

    lengths = (
        shp_river[river_length]
        .astype(float)
        .to_numpy()
    )

    hru_ids = (
        shp_basin[basin_hru_id]
        .astype(np.int64)
        .to_numpy()
    )

    hru_to_seg_ids = (
        shp_basin[basin_hru_to_seg]
        .astype(np.int64)
        .to_numpy()
    )

    areas = (
        shp_basin[basin_hru_area]
        .astype(float)
        .to_numpy()
    )

except Exception as exc:

    raise RuntimeError(
        "Could not convert required topology fields "
        "to numeric values."
    ) from exc


# ============================================================
# VALIDATE UNIQUE IDS
# ============================================================

if len(np.unique(seg_ids)) != len(seg_ids):

    values, counts = np.unique(
        seg_ids,
        return_counts=True
    )

    duplicate_ids = (
        values[counts > 1]
        .astype(int)
        .tolist()
    )

    raise RuntimeError(
        "Duplicate stream-segment IDs detected:\n"
        f"{duplicate_ids}"
    )


if len(np.unique(hru_ids)) != len(hru_ids):

    values, counts = np.unique(
        hru_ids,
        return_counts=True
    )

    duplicate_ids = (
        values[counts > 1]
        .astype(int)
        .tolist()
    )

    raise RuntimeError(
        "Duplicate routing HRU IDs detected:\n"
        f"{duplicate_ids}"
    )


# ============================================================
# VALIDATE PHYSICAL VARIABLES
# ============================================================

if not np.all(
    np.isfinite(slopes)
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
    np.isfinite(lengths)
):
    raise RuntimeError(
        "Non-finite river length values detected."
    )


# Preserve original CWARHM behavior:
# replace zero or negative stream lengths with 1 m.
zero_length = (
    lengths <= 0
)


if np.any(
    zero_length
):

    count = int(
        np.sum(zero_length)
    )

    print()
    print(
        f"WARNING: {count} segment(s) "
        "have length <= 0."
    )

    print(
        "Setting these segment lengths to 1 m."
    )

    lengths[
        zero_length
    ] = 1.0


if not np.all(
    np.isfinite(areas)
):
    raise RuntimeError(
        "Non-finite routing-basin area values detected."
    )


if np.any(
    areas <= 0
):
    raise RuntimeError(
        "Routing-basin area must be > 0."
    )


# ============================================================
# BUILD SEGMENT SET
# ============================================================

segment_set = {
    int(value)
    for value in seg_ids
}


# ============================================================
# OPTIONAL OUTLET ENFORCEMENT
# ============================================================

outlet_setting = read_from_control(
    CONTROL_FILE,
    "settings_mizu_make_outlet"
).strip()


if outlet_setting.lower() in {
    "n/a",
    "na",
    "none",
    ""
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


missing_outlets = [
    value
    for value in requested_outlets
    if value not in segment_set
]


if missing_outlets:

    raise RuntimeError(
        "Requested outlet segment(s) not found "
        "in river network:\n"
        f"{missing_outlets}"
    )


# Convert the configured domain outlet(s)
# to mizuRoute outlet(s).
#
# Important:
# This is done BEFORE downstream connectivity validation,
# because a clipped-domain outlet can legitimately have a
# NextDownID outside the retained river network.

for outlet_id in requested_outlets:

    mask = (
        seg_ids
        == outlet_id
    )

    original_downstream = (
        down_seg_ids[
            mask
        ].copy()
    )

    down_seg_ids[
        mask
    ] = 0

    print()
    print(
        f"Forced outlet {outlet_id}: "
        f"downSegId "
        f"{int(original_downstream[0])} -> 0"
    )


# ============================================================
# VALIDATE NETWORK CONNECTIVITY
# ============================================================

# After configured outlet correction, every remaining
# downstream segment must either:
#
#   1. exist in the current network, or
#   2. equal 0 for an outlet.

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
        "The following downSegId values are not "
        "present in the river network and are not 0:\n"
        f"{invalid_downstream}\n\n"
        "If one of these corresponds to the intended "
        "domain outlet, set its segment ID in "
        "settings_mizu_make_outlet."
    )


# Every routing HRU must discharge to an existing
# stream segment.

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
        "exist in the river network:\n"
        f"{invalid_hru_links}"
    )


# ============================================================
# NETWORK SUMMARY
# ============================================================

num_seg = len(
    seg_ids
)

num_hru = len(
    hru_ids
)


outlet_segments = (
    seg_ids[
        down_seg_ids == 0
    ]
)


print()
print("============================================================")
print("CREATE MIZUROUTE TOPOLOGY")
print("============================================================")

print(
    f"Domain          : "
    f"{domain_name}"
)

print(
    f"River network   : "
    f"{river_file}"
)

print(
    f"Routing basins  : "
    f"{basin_file}"
)

print(
    f"Output          : "
    f"{topology_file}"
)

print(
    f"Segments        : "
    f"{num_seg}"
)

print(
    f"Routing HRUs    : "
    f"{num_hru}"
)

print(
    f"Outlet segments : "
    f"{outlet_segments.tolist()}"
)


if requested_outlets:

    print(
        f"Forced outlets  : "
        f"{requested_outlets}"
    )

else:

    print(
        "Forced outlets  : none"
    )


print()

print(
    f"Slope range     : "
    f"{slopes.min():.8g} - "
    f"{slopes.max():.8g}"
)

print(
    f"Length range    : "
    f"{lengths.min():.3f} - "
    f"{lengths.max():.3f} m"
)

print(
    f"Area range      : "
    f"{areas.min():.3f} - "
    f"{areas.max():.3f} m2"
)


# ============================================================
# NETCDF HELPER
# ============================================================

def create_and_fill_nc_var(
    ncid,
    var_name,
    var_type,
    dim,
    data,
    long_name,
    units
):
    """
    Create and populate a one-dimensional NetCDF variable.
    """

    ncvar = ncid.createVariable(
        var_name,
        var_type,
        (dim,)
    )

    ncvar[:] = data

    ncvar.long_name = (
        long_name
    )

    # Preserve existing CWARHM / mizuRoute
    # topology metadata convention.
    ncvar.unit = units


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
        "Created by SUMMA workflow scripts"
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
        "Create a river network .nc file "
        "for mizuRoute routing"
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
        "ID of the downstream segment",
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
        "Segment slope",
        "-"
    )


    create_and_fill_nc_var(
        ncid,
        "length",
        "f8",
        "seg",
        lengths.astype(
            np.float64
        ),
        "Segment length",
        "m"
    )


    # --------------------------------------------------------
    # Routing HRU variables
    # --------------------------------------------------------

    create_and_fill_nc_var(
        ncid,
        "hruId",
        "i4",
        "hru",
        hru_ids.astype(
            np.int32
        ),
        "Unique hru ID",
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
        "ID of the stream segment to which "
        "the HRU discharges",
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
        "HRU area",
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
        "hru"
    }

    required_variables = {
        "segId",
        "downSegId",
        "slope",
        "length",
        "hruId",
        "hruToSegId",
        "area"
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
            "Written topology file is missing "
            f"dimension(s): {missing_dimensions}"
        )


    if missing_variables:

        raise RuntimeError(
            "Written topology file is missing "
            f"variable(s): {missing_variables}"
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


    written_seg_ids = (
        check["segId"][:]
        .astype(np.int64)
    )

    written_down_ids = (
        check["downSegId"][:]
        .astype(np.int64)
    )

    written_hru_ids = (
        check["hruId"][:]
        .astype(np.int64)
    )

    written_hru_to_seg = (
        check["hruToSegId"][:]
        .astype(np.int64)
    )


    if not np.array_equal(
        written_seg_ids,
        seg_ids
    ):

        raise RuntimeError(
            "segId values changed while "
            "writing topology.nc."
        )


    if not np.array_equal(
        written_down_ids,
        down_seg_ids
    ):

        raise RuntimeError(
            "downSegId values changed while "
            "writing topology.nc."
        )


    if not np.array_equal(
        written_hru_ids,
        hru_ids
    ):

        raise RuntimeError(
            "hruId values changed while "
            "writing topology.nc."
        )


    if not np.array_equal(
        written_hru_to_seg,
        hru_to_seg_ids
    ):

        raise RuntimeError(
            "hruToSegId values changed while "
            "writing topology.nc."
        )


# ============================================================
# LOGGING / PROVENANCE
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


copyfile(
    Path(__file__).resolve(),
    log_folder
    / this_file
)


now = datetime.now()


log_file = (
    log_folder
    / (
        f"{now:%Y%m%d}_"
        f"make_river_network_topology.txt"
    )
)


with open(
    log_file,
    "w"
) as f:

    f.write(
        f"Log generated by {this_file} "
        f"on {now:%Y/%m/%d %H:%M:%S}\n"
    )

    f.write(
        f"Domain: "
        f"{domain_name}\n"
    )

    f.write(
        f"River network: "
        f"{river_file}\n"
    )

    f.write(
        f"Routing basins: "
        f"{basin_file}\n"
    )

    f.write(
        f"Segments: "
        f"{num_seg}\n"
    )

    f.write(
        f"Routing HRUs: "
        f"{num_hru}\n"
    )

    f.write(
        "Outlet segments: "
        f"{outlet_segments.tolist()}\n"
    )

    f.write(
        "Forced outlets: "
        f"{requested_outlets}\n"
    )


# ============================================================
# SUMMARY
# ============================================================

print()
print(
    "mizuRoute topology created successfully."
)

print(
    f"Segments     : "
    f"{num_seg}"
)

print(
    f"Routing HRUs : "
    f"{num_hru}"
)

print(
    f"Outlets      : "
    f"{outlet_segments.tolist()}"
)

print(
    f"Output       : "
    f"{topology_file}"
)