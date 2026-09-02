#!/usr/bin/env python3
# coding: utf-8

# Prepare ERA5 forcing for the NWAM-SUMMA workflow.
#
# MULTIBASIN VERSION
# ------------------
# This script does NOT use control_active.txt.
#
# Usage:
#
#   python 3_prepare_era5_forcing.py CONTROL_FILE
#
#       -> process all months in forcing_raw_time
#
#   python 3_prepare_era5_forcing.py CONTROL_FILE YEAR MONTH
#
#       -> process one month only
#
# Example:
#
#   python 3_prepare_era5_forcing.py \
#       ../../0_control_files/control_MERIT_717.txt \
#       1950 1

from pathlib import Path
from datetime import datetime
from shutil import copyfile
import sys

import xarray as xr


# =====================================================================
# COMMAND-LINE ARGUMENTS
# =====================================================================

if len(sys.argv) not in (2, 4):

    raise SystemExit(
        "Usage:\n"
        "  python 3_prepare_era5_forcing.py CONTROL_FILE\n"
        "or\n"
        "  python 3_prepare_era5_forcing.py CONTROL_FILE YEAR MONTH"
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
# PATHS
# =====================================================================

era5Path = Path(
    read_from_control(
        controlPath,
        "forcing_era5_path"
    )
)


forcingRawPath = read_from_control(
    controlPath,
    "forcing_raw_path"
)


if forcingRawPath == "default":

    forcingRawPath = make_default_path(
        "forcing/1_raw_data"
    )

else:

    forcingRawPath = Path(
        forcingRawPath
    )


outputPath = (
    forcingRawPath
    / "ERA5_prepared"
)


outputPath.mkdir(
    parents=True,
    exist_ok=True
)


# =====================================================================
# TIME PERIOD
# =====================================================================

years = read_from_control(
    controlPath,
    "forcing_raw_time"
)


try:

    startYear, endYear = [
        int(x.strip())
        for x in years.split(",")
    ]

except Exception as exc:

    raise ValueError(
        "forcing_raw_time must have format:\n"
        "START_YEAR,END_YEAR\n"
        "For example: 1950,2019"
    ) from exc


if startYear > endYear:

    raise ValueError(
        f"Invalid forcing_raw_time: "
        f"{startYear},{endYear}"
    )


# =====================================================================
# SPATIAL EXTENT
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


# One ERA5 grid-cell buffer.

buffer = 0.25


subset_lat_max = (
    latMax + buffer
)

subset_lat_min = (
    latMin - buffer
)

subset_lon_min = (
    lonMin - buffer
)

subset_lon_max = (
    lonMax + buffer
)


# =====================================================================
# VARIABLES RETAINED FROM ERA5
# =====================================================================

keep_variables = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "spechum",
    "windspd",
]


# =====================================================================
# SELECT MONTHS TO PROCESS
# =====================================================================

if len(sys.argv) == 2:

    months_to_process = [
        (year, month)
        for year in range(
            startYear,
            endYear + 1
        )
        for month in range(
            1,
            13
        )
    ]


else:

    try:

        runYear = int(
            sys.argv[2]
        )

        runMonth = int(
            sys.argv[3]
        )

    except ValueError as exc:

        raise ValueError(
            "YEAR and MONTH must be integers."
        ) from exc


    if (
        runYear < startYear
        or runYear > endYear
    ):

        raise ValueError(
            f"Year {runYear} is outside "
            f"forcing_raw_time "
            f"{startYear}-{endYear}"
        )


    if (
        runMonth < 1
        or runMonth > 12
    ):

        raise ValueError(
            "Month must be between 1 and 12."
        )


    months_to_process = [
        (
            runYear,
            runMonth
        )
    ]


# =====================================================================
# REPORT CONFIGURATION
# =====================================================================

print()

print("=" * 70)
print("PREPARE ERA5 FORCING")
print("=" * 70)

print(
    f"Domain       : {domainName}"
)

print(
    f"Control file : {controlPath}"
)

print(
    f"ERA5 root    : {era5Path}"
)

print(
    f"Output       : {outputPath}"
)

print(
    f"Forcing years: "
    f"{startYear}-{endYear}"
)

print(
    f"Months this run: "
    f"{len(months_to_process)}"
)

print(
    "Subset bounds:"
)

print(
    f"  latitude : "
    f"{subset_lat_min} to "
    f"{subset_lat_max}"
)

print(
    f"  longitude: "
    f"{subset_lon_min} to "
    f"{subset_lon_max}"
)

print()


# =====================================================================
# PROCESS MONTHS
# =====================================================================

processed_months = []
skipped_months = []
missing_months = []


for year, month in months_to_process:

    ym = (
        f"{year}"
        f"{month:02d}"
    )


    inputFile = (
        era5Path
        / f"ERA5_merged_{ym}.nc"
    )


    outputFile = (
        outputPath
        / f"ERA5_SUMMA_{ym}.nc"
    )


    print(
        f"Processing {ym}"
    )


    # -----------------------------------------------------------------
    # CHECK INPUT
    # -----------------------------------------------------------------

    if not inputFile.exists():

        print(
            f"  Missing: "
            f"{inputFile}"
        )

        missing_months.append(
            ym
        )

        continue


    if outputFile.exists():

        print(
            f"  Output already exists: "
            f"{outputFile}"
        )

        skipped_months.append(
            ym
        )

        continue


    # -----------------------------------------------------------------
    # OPEN DATASET
    # -----------------------------------------------------------------

    with xr.open_dataset(
        inputFile
    ) as ds:


        # -------------------------------------------------------------
        # CHECK REQUIRED COORDINATES
        # -------------------------------------------------------------

        required_coordinates = [
            "time",
            "latitude",
            "longitude",
        ]


        missing_coordinates = [
            coordinate
            for coordinate in required_coordinates
            if coordinate not in ds
        ]


        if missing_coordinates:

            raise ValueError(
                f"Missing required ERA5 coordinates "
                f"in {ym}: "
                f"{missing_coordinates}"
            )


        # -------------------------------------------------------------
        # CHECK VARIABLES
        # -------------------------------------------------------------

        missing_variables = [
            variable
            for variable in keep_variables
            if variable not in ds.variables
        ]


        if missing_variables:

            raise ValueError(
                f"Missing required ERA5 variables "
                f"in {ym}: "
                f"{missing_variables}"
            )


        # -------------------------------------------------------------
        # SPATIAL SUBSET
        #
        # Existing NWAM ERA5 files use latitude decreasing
        # north -> south and longitude increasing west -> east.
        # -------------------------------------------------------------

        ds_sub = ds.sel(

            latitude=slice(
                subset_lat_max,
                subset_lat_min
            ),

            longitude=slice(
                subset_lon_min,
                subset_lon_max
            )
        )


        # -------------------------------------------------------------
        # CHECK SUBSET
        # -------------------------------------------------------------

        if ds_sub.sizes.get(
            "latitude",
            0
        ) == 0:

            raise ValueError(
                f"ERA5 latitude subset is empty "
                f"for {ym}. "
                f"Check forcing_raw_space."
            )


        if ds_sub.sizes.get(
            "longitude",
            0
        ) == 0:

            raise ValueError(
                f"ERA5 longitude subset is empty "
                f"for {ym}. "
                f"Check forcing_raw_space."
            )


        if ds_sub.sizes.get(
            "time",
            0
        ) == 0:

            raise ValueError(
                f"ERA5 time dimension is empty "
                f"for {ym}."
            )


        # -------------------------------------------------------------
        # KEEP REQUIRED VARIABLES
        # -------------------------------------------------------------

        ds_out = (
            ds_sub[
                keep_variables
            ]
            .astype(
                "float32"
            )
        )


        # Preserve coordinates explicitly.

        ds_out = ds_out.assign_coords(

            time=ds_sub[
                "time"
            ],

            latitude=ds_sub[
                "latitude"
            ],

            longitude=ds_sub[
                "longitude"
            ],
        )


        # -------------------------------------------------------------
        # GLOBAL METADATA
        # -------------------------------------------------------------

        ds_out.attrs[
            "History"
        ] = (
            "Prepared ERA5 forcing "
            "for NWAM-SUMMA"
        )


        ds_out.attrs[
            "Reason"
        ] = (
            "Domain subset of existing "
            "ERA5 merged forcing. "
            "ERA5 precipitation and temperature "
            "excluded because NWAM uses EM-Earth "
            "for pptrate and airtemp."
        )


        ds_out.attrs[
            "Domain"
        ] = (
            domainName
        )


        ds_out.attrs[
            "Control file"
        ] = (
            str(
                controlPath
            )
        )


        # -------------------------------------------------------------
        # COMPRESSION
        # -------------------------------------------------------------

        encoding = {}


        for variable in keep_variables:

            encoding[
                variable
            ] = {
                "dtype": "float32",
                "zlib": True,
                "complevel": 4,
            }


        # -------------------------------------------------------------
        # WRITE OUTPUT
        # -------------------------------------------------------------

        ds_out.to_netcdf(
            outputFile,
            encoding=encoding
        )


        ds_out.close()


    processed_months.append(
        ym
    )


    print(
        f"  Created: "
        f"{outputFile}"
    )


# =====================================================================
# LOGGING
# =====================================================================

logFolder = (
    outputPath
    / "_workflow_log"
)


logFolder.mkdir(
    parents=True,
    exist_ok=True
)


thisFile = Path(
    __file__
).name


try:

    copyfile(
        Path(
            __file__
        ).resolve(),
        logFolder
        / thisFile
    )

except Exception as exc:

    print(
        "Warning: could not copy "
        f"script to log folder: {exc}"
    )


now = datetime.now()


if len(
    months_to_process
) == 1:

    run_label = (
        months_to_process[0][0]
        * 100
        + months_to_process[0][1]
    )


    logFile = (
        logFolder
        / (
            f"{now:%Y%m%d_%H%M%S}_"
            f"prepare_era5_{run_label}.txt"
        )
    )


else:

    logFile = (
        logFolder
        / (
            f"{now:%Y%m%d_%H%M%S}_"
            "prepare_era5_forcing_log.txt"
        )
    )


with open(
    logFile,
    "w"
) as file:

    file.write(
        f"Log generated by {thisFile} on "
        f"{now:%Y/%m/%d %H:%M:%S}\n"
    )

    file.write(
        f"Domain: "
        f"{domainName}\n"
    )

    file.write(
        f"Control file: "
        f"{controlPath}\n"
    )

    file.write(
        f"ERA5 source: "
        f"{era5Path}\n"
    )

    file.write(
        f"Output directory: "
        f"{outputPath}\n"
    )

    file.write(
        f"Configured forcing period: "
        f"{startYear}-{endYear}\n"
    )

    file.write(
        f"Months requested: "
        f"{len(months_to_process)}\n"
    )

    file.write(
        f"Months created: "
        f"{len(processed_months)}\n"
    )

    file.write(
        "Months skipped because output "
        f"already existed: "
        f"{len(skipped_months)}\n"
    )

    file.write(
        f"Missing input months: "
        f"{len(missing_months)}\n"
    )

    file.write(
        "Retained airpres, LWRadAtm, "
        "SWRadAtm, spechum and windspd.\n"
    )

    file.write(
        "Excluded ERA5 pptrate and airtemp "
        "because NWAM uses EM-Earth "
        "equivalents.\n"
    )


# =====================================================================
# FINAL SUMMARY
# =====================================================================

print()

print("=" * 70)
print("ERA5 FORCING PREPARATION COMPLETED")
print("=" * 70)

print(
    f"Domain          : "
    f"{domainName}"
)

print(
    f"Months requested: "
    f"{len(months_to_process)}"
)

print(
    f"Months created  : "
    f"{len(processed_months)}"
)

print(
    f"Months skipped  : "
    f"{len(skipped_months)}"
)

print(
    f"Missing inputs  : "
    f"{len(missing_months)}"
)

print(
    f"Output directory: "
    f"{outputPath}"
)

print(
    f"Workflow log    : "
    f"{logFile}"
)