#!/usr/bin/env python3
# coding: utf-8

"""
Create reusable EASYMORE forcing remapping for lumped SUMMA.

The distributed forcing preparation is reused.

Source data:
    domain_<DOMAIN>/forcing/1_raw_data/
    domain_<DOMAIN>/shapefiles/forcing/

Target:
    domain_<DOMAIN>/lumped/shapefiles/catchment/
        <DOMAIN>_lumped_basin.shp

Outputs:
    domain_<DOMAIN>/lumped/
        shapefiles/catchment_intersection/with_forcing/
        forcing/3_basin_averaged_data/

No distributed products are modified.
"""

import sys
from pathlib import Path
from shutil import rmtree, copy2

import easymore
import geopandas as gpd
import numpy as np
import xarray as xr


# ============================================================
# INPUT
# ============================================================

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage:\n"
        "python 1_create_lumped_forcing_remapping.py "
        "/path/to/control_DOMAIN_lumped.txt"
    )

CONTROL_FILE = Path(sys.argv[1]).resolve()

if not CONTROL_FILE.exists():
    raise FileNotFoundError(
        f"Control file not found:\n{CONTROL_FILE}"
    )


# ============================================================
# CONTROL READER
# ============================================================

def read_control(setting):

    with CONTROL_FILE.open() as f:

        for line in f:

            s = line.strip()

            if (
                not s
                or s.startswith("#")
                or "|" not in s
            ):
                continue

            left, right = s.split("|", 1)

            if left.strip() == setting:

                value = (
                    right
                    .split("#", 1)[0]
                    .strip()
                )

                if not value:
                    raise RuntimeError(
                        f"Empty control setting: {setting}"
                    )

                return value

    raise RuntimeError(
        f"Control setting not found: {setting}"
    )


# ============================================================
# DOMAIN PATHS
# ============================================================

ROOT = Path(
    read_control("root_path")
)

DOMAIN = read_control(
    "domain_name"
)

DOMAIN_ROOT = (
    ROOT
    / f"domain_{DOMAIN}"
)

LUMPED_ROOT = (
    DOMAIN_ROOT
    / "lumped"
)

DISTRIBUTED_FORCING = (
    DOMAIN_ROOT
    / "forcing"
    / "1_raw_data"
)

DISTRIBUTED_GRID = (
    DOMAIN_ROOT
    / "shapefiles"
    / "forcing"
)

LUMPED_CATCHMENT = (
    LUMPED_ROOT
    / "shapefiles"
    / "catchment"
    / f"{DOMAIN}_lumped_basin.shp"
)


# ============================================================
# TARGET FIELDS
# ============================================================

TARGET_ID = read_control(
    "catchment_shp_hruid"
)

TARGET_LAT = read_control(
    "catchment_shp_lat"
)

TARGET_LON = read_control(
    "catchment_shp_lon"
)

SOURCE_LAT = read_control(
    "forcing_shape_lat_name"
)

SOURCE_LON = read_control(
    "forcing_shape_lon_name"
)


# ============================================================
# VERIFY LUMPED CATCHMENT
# ============================================================

if not LUMPED_CATCHMENT.exists():
    raise FileNotFoundError(
        "Lumped catchment not found:\n"
        f"{LUMPED_CATCHMENT}"
    )

target = gpd.read_file(
    LUMPED_CATCHMENT
)

if len(target) != 1:
    raise RuntimeError(
        f"Lumped catchment must contain exactly 1 HRU. "
        f"Found: {len(target)}"
    )

if target.crs is None or target.crs.to_epsg() != 4326:
    raise RuntimeError(
        "Lumped catchment must use EPSG:4326."
    )

for field in [
    TARGET_ID,
    TARGET_LAT,
    TARGET_LON,
]:
    if field not in target.columns:
        raise RuntimeError(
            f"Missing target field: {field}"
        )

target_ids = (
    target[TARGET_ID]
    .astype(np.int64)
    .to_numpy()
)

if len(target_ids) != 1 or target_ids[0] != 1:
    raise RuntimeError(
        f"Expected lumped HRU_ID=1. Found: {target_ids}"
    )


# ============================================================
# FORCING CONFIGURATION
# ============================================================

PRODUCTS = {

    "ERA5": {
        "grid":
            read_control(
                "forcing_era5_shape_name"
            ),

        "prepared_dir":
            "ERA5_prepared",

        "pattern":
            "ERA5_SUMMA_*.nc",

        "variables": [
            "airpres",
            "LWRadAtm",
            "SWRadAtm",
            "spechum",
            "windspd",
        ],
    },

    "EM_Earth": {
        "grid":
            read_control(
                "forcing_emearth_shape_name"
            ),

        "prepared_dir":
            "EM_Earth_prepared",

        "pattern":
            "EM_Earth_SUMMA_*.nc",

        "variables": [
            "pptrate",
            "airtemp",
        ],
    },
}


# ============================================================
# PROCESS EACH FORCING PRODUCT
# ============================================================

for product, cfg in PRODUCTS.items():

    print()
    print("=" * 78)
    print(
        f"CREATE LUMPED {product} EASYMORE REMAPPING"
    )
    print("=" * 78)

    grid_file = (
        DISTRIBUTED_GRID
        / cfg["grid"]
    )

    prepared_dir = (
        DISTRIBUTED_FORCING
        / cfg["prepared_dir"]
    )

    forcing_files = sorted(
        prepared_dir.glob(
            cfg["pattern"]
        )
    )

    if not grid_file.exists():
        raise FileNotFoundError(
            f"Distributed forcing grid not found:\n"
            f"{grid_file}"
        )

    if not forcing_files:
        raise FileNotFoundError(
            f"No prepared {product} files found:\n"
            f"{prepared_dir}"
        )

    forcing_file = forcing_files[0]

    grid = gpd.read_file(
        grid_file
    )

    if grid.crs is None:
        raise RuntimeError(
            f"{product} grid has no CRS."
        )

    if grid.crs.to_epsg() != 4326:
        raise RuntimeError(
            f"{product} grid must be EPSG:4326."
        )

    for field in [
        SOURCE_LAT,
        SOURCE_LON,
    ]:
        if field not in grid.columns:
            raise RuntimeError(
                f"{product} grid missing field: {field}"
            )

    with xr.open_dataset(
        forcing_file
    ) as ds:

        missing = [
            v
            for v in cfg["variables"]
            if v not in ds.variables
        ]

        if missing:
            raise RuntimeError(
                f"{product} template missing: "
                + ", ".join(missing)
            )

        input_time = ds.sizes.get(
            "time",
            0
        )

    remap_dir = (
        LUMPED_ROOT
        / "shapefiles"
        / "catchment_intersection"
        / "with_forcing"
        / product
    )

    temp_dir = (
        LUMPED_ROOT
        / "forcing"
        / "3_temp_easymore"
        / product
    )

    output_dir = (
        LUMPED_ROOT
        / "forcing"
        / "3_basin_averaged_data"
        / product
    )

    remap_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    if temp_dir.exists():
        rmtree(temp_dir)

    temp_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    case_name = (
        f"{DOMAIN}_lumped_{product}"
    )

    print(f"Domain          : {DOMAIN}")
    print(f"Target HRUs     : 1")
    print(f"Target          : {LUMPED_CATCHMENT}")
    print(f"Source grid     : {grid_file}")
    print(f"Prepared input  : {forcing_file}")
    print(f"Remap output    : {remap_dir}")
    print(f"Forcing output  : {output_dir}")

    esmr = easymore.Easymore()

    esmr.case_name = case_name

    esmr.author_name = (
        "NAWM lumped SUMMA workflow"
    )

    esmr.license = product

    # Source grid
    esmr.source_shp = str(
        grid_file
    )

    esmr.source_shp_lat = (
        SOURCE_LAT
    )

    esmr.source_shp_lon = (
        SOURCE_LON
    )

    # Lumped target
    esmr.target_shp = str(
        LUMPED_CATCHMENT
    )

    esmr.target_shp_ID = (
        TARGET_ID
    )

    esmr.target_shp_lat = (
        TARGET_LAT
    )

    esmr.target_shp_lon = (
        TARGET_LON
    )

    # Source forcing
    esmr.source_nc = str(
        forcing_file
    )

    esmr.var_names = (
        cfg["variables"]
    )

    esmr.var_lat = "latitude"
    esmr.var_lon = "longitude"
    esmr.var_time = "time"

    esmr.temp_dir = (
        str(temp_dir)
        + "/"
    )

    esmr.output_dir = (
        str(output_dir)
        + "/"
    )

    esmr.remapped_dim_id = "hru"
    esmr.remapped_var_id = "hruId"

    esmr.format_list = ["f4"]
    esmr.fill_value_list = ["-9999"]

    esmr.save_csv = False
    esmr.remap_csv = ""
    esmr.sort_ID = False

    print()
    print("Running EASYMORE...")

    esmr.nc_remapper()

    # --------------------------------------------------------
    # SAVE REUSABLE REMAPPING PRODUCT
    # --------------------------------------------------------

    temp_path = Path(
        esmr.temp_dir
    )

    remap_files = (
        list(
            temp_path.glob(
                f"{case_name}*remap*.csv"
            )
        )
        +
        list(
            temp_path.glob(
                f"{case_name}*remap*.nc"
            )
        )
    )

    if not remap_files:
        raise RuntimeError(
            f"No reusable {product} remapping "
            "file was generated."
        )

    for src in remap_files:

        dst = (
            remap_dir
            / src.name
        )

        copy2(
            src,
            dst
        )

        print(
            f"Saved remapping: {dst}"
        )

    # --------------------------------------------------------
    # VERIFY TEST OUTPUT
    # --------------------------------------------------------

    outputs = sorted(
        output_dir.glob(
            "*.nc"
        ),
        key=lambda p: p.stat().st_mtime
    )

    if not outputs:
        raise RuntimeError(
            f"No lumped {product} test output created."
        )

    output_file = outputs[-1]

    with xr.open_dataset(
        output_file
    ) as ds:

        if ds.sizes.get(
            "hru",
            0
        ) != 1:

            raise RuntimeError(
                f"{product}: expected hru=1."
            )

        if "hruId" not in ds.variables:
            raise RuntimeError(
                f"{product}: hruId missing."
            )

        hru_ids = (
            np.asarray(
                ds["hruId"].values
            )
            .astype(np.int64)
            .reshape(-1)
        )

        if not np.array_equal(
            hru_ids,
            np.array([1])
        ):
            raise RuntimeError(
                f"{product}: expected hruId=[1], "
                f"found {hru_ids}"
            )

        if ds.sizes.get(
            "time",
            0
        ) != input_time:
            raise RuntimeError(
                f"{product}: output time dimension differs "
                "from source."
            )

    print()
    print(
        f"PASS: {product} lumped remapping"
    )
    print(
        f"Test output: {output_file}"
    )

    rmtree(
        temp_dir,
        ignore_errors=True
    )


print()
print("=" * 78)
print("LUMPED FORCING REMAPPING INITIALIZATION COMPLETE")
print("=" * 78)
print(f"Domain : {DOMAIN}")
print("HRUs   : 1")
print("ERA5   : PASS")
print("EM-Earth: PASS")