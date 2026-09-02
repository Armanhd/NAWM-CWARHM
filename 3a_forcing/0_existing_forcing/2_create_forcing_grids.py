#!/usr/bin/env python3
# coding: utf-8

# Create forcing-grid shapefiles for NWAM:
#
#   1. EM_Earth_grid.shp
#   2. ERA5_grid.shp
#
# The grids are used by EASYMORE to remap gridded forcing
# to SUMMA HRUs.
#
# MULTIBASIN VERSION
# ------------------
# This script does NOT use control_active.txt.
#
# Usage:
#
#   python 2_create_forcing_grids.py CONTROL_FILE
#
# Example:
#
#   python 2_create_forcing_grids.py \
#       ../../0_control_files/control_MERIT_717.txt

from pathlib import Path
import sys

import shapefile
import xarray as xr


# =====================================================================
# COMMAND-LINE ARGUMENT
# =====================================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "  python 2_create_forcing_grids.py CONTROL_FILE"
    )


controlPath = Path(
    sys.argv[1]
).expanduser().resolve()


if not controlPath.exists():

    raise FileNotFoundError(
        f"Control file not found:\n"
        f"{controlPath}"
    )


# =====================================================================
# CONTROL FILE FUNCTIONS
# =====================================================================

def read_from_control(file, setting):

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


def make_default_path(suffix):

    rootPath = Path(
        read_from_control(
            controlPath,
            "root_path"
        )
    )

    domainName = read_from_control(
        controlPath,
        "domain_name"
    )

    return (
        rootPath
        / f"domain_{domainName}"
        / suffix
    )


# =====================================================================
# DOMAIN
# =====================================================================

domainName = read_from_control(
    controlPath,
    "domain_name"
)


# =====================================================================
# PATHS / SETTINGS
# =====================================================================

shapePath = read_from_control(
    controlPath,
    "forcing_shape_path"
)


if shapePath == "default":

    shapePath = make_default_path(
        "shapefiles/forcing"
    )

else:

    shapePath = Path(
        shapePath
    )


shapePath.mkdir(
    parents=True,
    exist_ok=True
)


emShapeName = read_from_control(
    controlPath,
    "forcing_emearth_shape_name"
)


eraShapeName = read_from_control(
    controlPath,
    "forcing_era5_shape_name"
)


emearthPath = Path(
    read_from_control(
        controlPath,
        "forcing_emearth_path"
    )
)


era5Path = Path(
    read_from_control(
        controlPath,
        "forcing_era5_path"
    )
)


# =====================================================================
# DOMAIN EXTENT
# =====================================================================

space = read_from_control(
    controlPath,
    "forcing_raw_space"
)


try:

    latMax, lonMin, latMin, lonMax = [
        float(x.strip())
        for x in space.split("/")
    ]

except Exception as exc:

    raise ValueError(
        "forcing_raw_space must have format:\n"
        "LAT_MAX/LON_MIN/LAT_MIN/LON_MAX"
    ) from exc


if latMin >= latMax:

    raise ValueError(
        "Invalid forcing_raw_space: "
        "latMin must be smaller than latMax."
    )


if lonMin >= lonMax:

    raise ValueError(
        "Invalid forcing_raw_space: "
        "lonMin must be smaller than lonMax."
    )


# =====================================================================
# FIND SOURCE GRID FILES
# =====================================================================

emearthFiles = sorted(

    (
        emearthPath
        / "prcp"
        / "NorthAmerica"
    ).glob(
        "EM_Earth_deterministic_hourly_NorthAmerica_*.nc"
    )
)


if not emearthFiles:

    raise FileNotFoundError(
        "No EM-Earth precipitation files found in:\n"
        f"{emearthPath / 'prcp' / 'NorthAmerica'}"
    )


emFile = emearthFiles[0]


era5Files = sorted(

    era5Path.glob(
        "ERA5_merged_*.nc"
    )
)


if not era5Files:

    raise FileNotFoundError(
        "No ERA5_merged_*.nc files found in:\n"
        f"{era5Path}"
    )


eraFile = era5Files[0]


# =====================================================================
# REPORT CONFIGURATION
# =====================================================================

print()

print("=" * 70)
print("CREATE FORCING GRID SHAPEFILES")
print("=" * 70)

print(
    f"Domain       : {domainName}"
)

print(
    f"Control file : {controlPath}"
)

print(
    f"Output       : {shapePath}"
)

print(
    "Domain extent:"
)

print(
    f"  latitude : "
    f"{latMin} to {latMax}"
)

print(
    f"  longitude: "
    f"{lonMin} to {lonMax}"
)

print()

print(
    "Grid template files:"
)

print(
    f"  EM-Earth: {emFile}"
)

print(
    f"  ERA5    : {eraFile}"
)


# =====================================================================
# CREATE REGULAR-GRID SHAPEFILE
# =====================================================================

def create_grid_shapefile(
    lat,
    lon,
    output_file,
    domain_buffer
):

    if len(lat) < 2 or len(lon) < 2:

        raise ValueError(
            "Latitude and longitude arrays must contain "
            "at least two grid points."
        )


    dlat = abs(
        float(
            lat[1] - lat[0]
        )
    )


    dlon = abs(
        float(
            lon[1] - lon[0]
        )
    )


    half_dlat = (
        dlat / 2.0
    )

    half_dlon = (
        dlon / 2.0
    )


    # Select grid-cell centers that extend slightly outside
    # the domain bounding box.
    #
    # The buffers correspond to one nominal source-grid cell:
    #
    # EM-Earth = 0.1 degree
    # ERA5     = 0.25 degree

    selected_lat = lat[
        (lat >= latMin - domain_buffer)
        & (lat <= latMax + domain_buffer)
    ]


    selected_lon = lon[
        (lon >= lonMin - domain_buffer)
        & (lon <= lonMax + domain_buffer)
    ]


    if len(selected_lat) == 0:

        raise ValueError(
            f"No latitude cells selected for "
            f"{output_file.name}. "
            "Check forcing_raw_space."
        )


    if len(selected_lon) == 0:

        raise ValueError(
            f"No longitude cells selected for "
            f"{output_file.name}. "
            "Check forcing_raw_space."
        )


    print()

    print(
        f"Creating {output_file.name}"
    )

    print(
        f"Grid spacing : "
        f"{dlat} x {dlon} degrees"
    )

    print(
        f"Latitude cells : "
        f"{len(selected_lat)}"
    )

    print(
        f"Longitude cells: "
        f"{len(selected_lon)}"
    )


    output_base = (
        output_file
        .with_suffix("")
    )


    # Remove stale shapefile components from an older run.
    #
    # This makes rerunning the workflow deterministic.

    for suffix in [
        ".shp",
        ".shx",
        ".dbf",
        ".prj",
        ".cpg",
    ]:

        stale_file = (
            output_base
            .with_suffix(
                suffix
            )
        )

        if stale_file.exists():

            stale_file.unlink()


    with shapefile.Writer(
        str(
            output_base
        )
    ) as writer:

        writer.autoBalance = 1


        writer.field(
            "ID",
            "N"
        )


        writer.field(
            "lat",
            "F",
            decimal=6
        )


        writer.field(
            "lon",
            "F",
            decimal=6
        )


        grid_id = 0


        for center_lat in selected_lat:

            for center_lon in selected_lon:

                grid_id += 1


                center_lat = float(
                    center_lat
                )


                center_lon = float(
                    center_lon
                )


                vertices = [

                    [
                        center_lon - half_dlon,
                        center_lat + half_dlat
                    ],

                    [
                        center_lon + half_dlon,
                        center_lat + half_dlat
                    ],

                    [
                        center_lon + half_dlon,
                        center_lat - half_dlat
                    ],

                    [
                        center_lon - half_dlon,
                        center_lat - half_dlat
                    ],

                    [
                        center_lon - half_dlon,
                        center_lat + half_dlat
                    ],
                ]


                writer.poly(
                    [
                        vertices
                    ]
                )


                writer.record(
                    grid_id,
                    center_lat,
                    center_lon
                )


    # -----------------------------------------------------------------
    # WGS84 / EPSG:4326 projection
    # -----------------------------------------------------------------

    prj = (
        'GEOGCS["WGS 84",'
        'DATUM["WGS_1984",'
        'SPHEROID["WGS 84",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],'
        'UNIT["degree",0.0174532925199433]]'
    )


    with open(
        output_file.with_suffix(
            ".prj"
        ),
        "w"
    ) as file:

        file.write(
            prj
        )


    # -----------------------------------------------------------------
    # VERIFY OUTPUT COMPONENTS
    # -----------------------------------------------------------------

    required_components = [
        output_file.with_suffix(
            ".shp"
        ),
        output_file.with_suffix(
            ".shx"
        ),
        output_file.with_suffix(
            ".dbf"
        ),
        output_file.with_suffix(
            ".prj"
        ),
    ]


    missing_components = [
        path
        for path in required_components
        if not path.exists()
    ]


    if missing_components:

        raise RuntimeError(
            "Forcing-grid shapefile was not created "
            "correctly. Missing:\n"
            + "\n".join(
                str(path)
                for path in missing_components
            )
        )


    print(
        f"Created: "
        f"{output_file}"
    )

    print(
        f"Number of grid cells: "
        f"{grid_id}"
    )


# =====================================================================
# EM-EARTH GRID
# =====================================================================

with xr.open_dataset(
    emFile
) as ds:

    if "lat" not in ds:

        raise RuntimeError(
            f"'lat' coordinate not found in:\n"
            f"{emFile}"
        )

    if "lon" not in ds:

        raise RuntimeError(
            f"'lon' coordinate not found in:\n"
            f"{emFile}"
        )


    em_lat = (
        ds["lat"]
        .values
    )

    em_lon = (
        ds["lon"]
        .values
    )


create_grid_shapefile(
    em_lat,
    em_lon,
    shapePath
    / emShapeName,
    domain_buffer=0.1
)


# =====================================================================
# ERA5 GRID
# =====================================================================

with xr.open_dataset(
    eraFile
) as ds:

    if "latitude" not in ds:

        raise RuntimeError(
            f"'latitude' coordinate not found in:\n"
            f"{eraFile}"
        )

    if "longitude" not in ds:

        raise RuntimeError(
            f"'longitude' coordinate not found in:\n"
            f"{eraFile}"
        )


    era_lat = (
        ds["latitude"]
        .values
    )

    era_lon = (
        ds["longitude"]
        .values
    )


create_grid_shapefile(
    era_lat,
    era_lon,
    shapePath
    / eraShapeName,
    domain_buffer=0.25
)


# =====================================================================
# FINAL SUMMARY
# =====================================================================

print()

print("=" * 70)
print("FORCING GRID CREATION COMPLETED")
print("=" * 70)

print(
    f"Domain       : "
    f"{domainName}"
)

print(
    f"EM-Earth grid: "
    f"{shapePath / emShapeName}"
)

print(
    f"ERA5 grid    : "
    f"{shapePath / eraShapeName}"
)

print(
    f"Output folder: "
    f"{shapePath}"
)