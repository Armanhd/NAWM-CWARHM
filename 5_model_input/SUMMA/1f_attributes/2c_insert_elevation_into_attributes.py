# Insert MERIT-Hydro mean HRU elevation into attributes.nc.
#
# Step 16 stores mean HRU elevation in:
#
#     elev_mean
#
# This script matches the elevation shapefile to attributes.nc
# through the configured HRU ID field and replaces the initial
# elevation placeholder.
#
# HRU connectivity
# ------------------------------------------------------------
# If:
#
#     settings_summa_connect_HRUs | no
#
# every downHRUindex remains 0, meaning each HRU behaves as an
# independent SUMMA column.
#
# If:
#
#     settings_summa_connect_HRUs | yes
#
# HRUs within each GRU are connected from higher elevation to
# the next lower-elevation HRU. The lowest HRU in each GRU has
# downHRUindex = 0.
#
# IMPORTANT:
# downHRUindex is an HRU INDEX, not an hruId. The index refers
# to the one-based HRU position in attributes.nc. This matters
# whenever HRU IDs are not identical to 1..N.
#
# SUMMA requires connected downslope HRUs to remain inside the
# same GRU. This script validates that condition.

from pathlib import Path
from datetime import datetime
from shutil import copy2

import geopandas as gpd
import netCDF4 as nc4
import numpy as np


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
    "intersect_dem_path",
    "shapefiles/catchment_intersection/with_dem"
)

intersect_name = read_from_control(
    CONTROL_FILE,
    "intersect_dem_name"
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

gru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_gruid"
)


connect_hrus = read_from_control(
    CONTROL_FILE,
    "settings_summa_connect_HRUs"
).strip().lower()


if connect_hrus not in [
    "yes",
    "no"
]:
    raise ValueError(
        "settings_summa_connect_HRUs "
        "must be 'yes' or 'no'."
    )


# ============================================================
# VALIDATE FILES
# ============================================================

if not intersect_file.exists():
    raise FileNotFoundError(
        f"DEM-intersection shapefile not found:\n"
        f"{intersect_file}"
    )


if not attribute_file.exists():
    raise FileNotFoundError(
        f"attributes.nc not found:\n"
        f"{attribute_file}"
    )


# ============================================================
# READ ELEVATION SHAPEFILE
# ============================================================

shp = gpd.read_file(
    intersect_file
)


required_fields = [
    hru_field,
    gru_field,
    "elev_mean",
]


missing_fields = [
    field
    for field in required_fields
    if field not in shp.columns
]


if missing_fields:
    raise RuntimeError(
        "Required elevation fields missing:\n"
        + "\n".join(
            f"  {field}"
            for field in missing_fields
        )
    )


shp[hru_field] = shp[
    hru_field
].astype(
    np.int64
)

shp[gru_field] = shp[
    gru_field
].astype(
    np.int64
)


if shp[hru_field].duplicated().any():
    raise RuntimeError(
        f"Duplicate {hru_field} values "
        "found in elevation shapefile."
    )


if not np.all(
    np.isfinite(
        shp["elev_mean"]
        .to_numpy(
            dtype=np.float64
        )
    )
):
    raise RuntimeError(
        "Non-finite elev_mean values found."
    )


shp = shp.set_index(
    hru_field,
    drop=False
)


# ============================================================
# READ ATTRIBUTES ORDER
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r"
) as att:

    for required in [
        "hruId",
        "hru2gruId",
        "elevation",
        "downHRUindex"
    ]:

        if required not in att.variables:
            raise RuntimeError(
                f"{required} missing from attributes.nc"
            )


    attribute_hrus = np.asarray(
        att["hruId"][:],
        dtype=np.int64
    )

    attribute_grus = np.asarray(
        att["hru2gruId"][:],
        dtype=np.int64
    )


num_hru = len(
    attribute_hrus
)


if len(attribute_grus) != num_hru:
    raise RuntimeError(
        "hruId and hru2gruId lengths differ."
    )


missing_hrus = [
    int(hru)
    for hru in attribute_hrus
    if hru not in shp.index
]


if missing_hrus:
    raise RuntimeError(
        "HRUs missing from elevation intersection:\n"
        f"{missing_hrus}"
    )


# ============================================================
# BUILD ELEVATION ARRAY IN ATTRIBUTES ORDER
# ============================================================

elevations = np.asarray(
    [
        float(
            shp.loc[
                int(hru),
                "elev_mean"
            ]
        )
        for hru
        in attribute_hrus
    ],
    dtype=np.float64
)


shape_grus = np.asarray(
    [
        int(
            shp.loc[
                int(hru),
                gru_field
            ]
        )
        for hru
        in attribute_hrus
    ],
    dtype=np.int64
)


if not np.array_equal(
    shape_grus,
    attribute_grus
):
    raise RuntimeError(
        "GRU assignments differ between "
        "attributes.nc and elevation shapefile."
    )


# ============================================================
# BUILD downHRUindex
# ============================================================

downstream_index = np.zeros(
    num_hru,
    dtype=np.int32
)


if connect_hrus == "yes":

    unique_grus = []

    for gru in attribute_grus:

        gru = int(gru)

        if gru not in unique_grus:
            unique_grus.append(
                gru
            )


    for gru in unique_grus:

        positions = np.where(
            attribute_grus == gru
        )[0]


        if len(positions) == 1:

            downstream_index[
                positions[0]
            ] = 0

            continue


        gru_elevations = elevations[
            positions
        ]


        # Sort from highest to lowest elevation.
        #
        # np.lexsort uses the second key first:
        #   primary   = -elevation
        #   tie-break = existing attributes position
        #
        # This gives deterministic behavior for tied elevation.

        order = np.lexsort(
            (
                positions,
                -gru_elevations
            )
        )


        ordered_positions = positions[
            order
        ]


        for current, downstream in zip(
            ordered_positions[:-1],
            ordered_positions[1:]
        ):

            # SUMMA downHRUindex is one-based.
            downstream_index[
                current
            ] = int(
                downstream + 1
            )


        # Lowest HRU is the GRU outlet.

        downstream_index[
            ordered_positions[-1]
        ] = 0


# ============================================================
# VALIDATE CONNECTIVITY
# ============================================================

for position, downstream in enumerate(
    downstream_index
):

    downstream = int(
        downstream
    )


    if downstream == 0:
        continue


    if (
        downstream < 1
        or downstream > num_hru
    ):
        raise RuntimeError(
            f"Invalid downHRUindex {downstream} "
            f"at HRU position {position + 1}."
        )


    downstream_position = (
        downstream - 1
    )


    if attribute_grus[
        downstream_position
    ] != attribute_grus[
        position
    ]:

        raise RuntimeError(
            "A downstream HRU crosses a GRU boundary."
        )


    if downstream_position == position:

        raise RuntimeError(
            "An HRU cannot drain to itself."
        )


# ============================================================
# REPORT
# ============================================================

print()
print("============================================================")
print("INSERT ELEVATION INTO ATTRIBUTES")
print("============================================================")
print(f"Domain         : {domain_name}")
print(f"Input          : {intersect_file}")
print(f"Attributes     : {attribute_file}")
print(f"HRUs           : {num_hru}")
print(f"Connect HRUs   : {connect_hrus}")
print(
    f"Elevation range: "
    f"{elevations.min():.3f} - "
    f"{elevations.max():.3f} m"
)


# ============================================================
# WRITE attributes.nc
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r+"
) as att:

    att["elevation"][:] = (
        elevations
    )

    # Explicitly write all zeros when connectivity is disabled.
    # This ensures a clean rerun after a previous connected run.

    att["downHRUindex"][:] = (
        downstream_index
    )


# ============================================================
# VERIFY OUTPUT
# ============================================================

with nc4.Dataset(
    attribute_file,
    "r"
) as att:

    output_elevation = np.asarray(
        att["elevation"][:],
        dtype=np.float64
    )

    output_downstream = np.asarray(
        att["downHRUindex"][:],
        dtype=np.int64
    )


if not np.allclose(
    output_elevation,
    elevations
):
    raise RuntimeError(
        "Elevation verification failed."
    )


if not np.array_equal(
    output_downstream,
    downstream_index.astype(
        np.int64
    )
):
    raise RuntimeError(
        "downHRUindex verification failed."
    )


print()
print(
    f"downHRUindex non-zero count: "
    f"{np.count_nonzero(output_downstream)}"
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
    / f"{now:%Y%m%d}_add_elevation_to_attributes.txt"
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
        f"HRUs: {num_hru}\n"
    )

    file.write(
        f"Connect HRUs: {connect_hrus}\n"
    )

    file.write(
        f"Elevation range: "
        f"{elevations.min():.3f} - "
        f"{elevations.max():.3f} m\n"
    )

    file.write(
        f"Non-zero downHRUindex values: "
        f"{np.count_nonzero(downstream_index)}\n"
    )


print()
print("Elevation inserted successfully.")