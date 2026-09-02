#!/usr/bin/env python
# coding: utf-8

# Prepare EM-Earth forcing for the NWAM-SUMMA workflow.
#
# MULTI-BASIN SAFE
# ----------------
# This script does NOT read control_active.txt.
# A domain-specific control file must be supplied explicitly.
#
# Usage:
#
#   Process all months in forcing_raw_time:
#
#       python 1_prepare_emearth_forcing.py CONTROL_FILE
#
#   Process one month:
#
#       python 1_prepare_emearth_forcing.py CONTROL_FILE YEAR MONTH
#
# Example:
#
#       python 1_prepare_emearth_forcing.py \
#       ../../0_control_files/control_MERIT_717.txt \
#       1950 1

from pathlib import Path
from datetime import datetime
from shutil import copyfile
import sys

import xarray as xr


# ---------------------------------------------------------------------
# COMMAND-LINE ARGUMENTS
# ---------------------------------------------------------------------

if len(sys.argv) not in [2, 4]:

    raise SystemExit(
        "Usage:\n"
        "python 1_prepare_emearth_forcing.py CONTROL_FILE\n"
        "or\n"
        "python 1_prepare_emearth_forcing.py "
        "CONTROL_FILE YEAR MONTH"
    )


controlPath = Path(
    sys.argv[1]
).expanduser().resolve()


if not controlPath.exists():

    raise FileNotFoundError(
        f"Control file not found:\n"
        f"{controlPath}"
    )


if not controlPath.is_file():

    raise RuntimeError(
        f"Control-file path is not a file:\n"
        f"{controlPath}"
    )


# ---------------------------------------------------------------------
# CONTROL FILE
# ---------------------------------------------------------------------

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


def make_default_path(suffix):
    """
    Construct a standard path inside the active domain.
    """

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


# ---------------------------------------------------------------------
# DOMAIN
# ---------------------------------------------------------------------

domainName = read_from_control(
    controlPath,
    "domain_name"
)


# ---------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------

emearthPath = Path(
    read_from_control(
        controlPath,
        "forcing_emearth_path"
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
    / "EM_Earth_prepared"
)


outputPath.mkdir(
    parents=True,
    exist_ok=True
)


# ---------------------------------------------------------------------
# TIME PERIOD
# ---------------------------------------------------------------------

years = read_from_control(
    controlPath,
    "forcing_raw_time"
)


try:

    startYear, endYear = [
        int(
            x.strip()
        )
        for x in years.split(",")
    ]

except Exception as exc:

    raise ValueError(
        "forcing_raw_time must have format:\n"
        "START_YEAR,END_YEAR\n"
        "For example:\n"
        "1950,2019"
    ) from exc


if startYear > endYear:

    raise ValueError(
        f"Invalid forcing_raw_time: "
        f"{startYear},{endYear}"
    )


# ---------------------------------------------------------------------
# SPATIAL EXTENT
# ---------------------------------------------------------------------

space = read_from_control(
    controlPath,
    "forcing_raw_space"
)


try:

    latMax, lonMin, latMin, lonMax = [
        float(
            x.strip()
        )
        for x in space.split("/")
    ]

except Exception as exc:

    raise ValueError(
        "forcing_raw_space must have format:\n"
        "LAT_MAX/LON_MIN/LAT_MIN/LON_MAX"
    ) from exc


if latMin >= latMax:

    raise ValueError(
        "forcing_raw_space has invalid latitude bounds."
    )


if lonMin >= lonMax:

    raise ValueError(
        "forcing_raw_space has invalid longitude bounds."
    )


# Add one EM-Earth grid-cell buffer.

buffer = 0.1

subset_lat_max = latMax + buffer
subset_lat_min = latMin - buffer
subset_lon_min = lonMin - buffer
subset_lon_max = lonMax + buffer


# ---------------------------------------------------------------------
# INPUT DIRECTORIES
# ---------------------------------------------------------------------

prcpPath = (
    emearthPath
    / "prcp"
    / "NorthAmerica"
)


tmeanPath = (
    emearthPath
    / "tmean"
    / "NorthAmerica"
)


if not prcpPath.exists():

    raise FileNotFoundError(
        "EM-Earth precipitation directory not found:\n"
        f"{prcpPath}"
    )


if not tmeanPath.exists():

    raise FileNotFoundError(
        "EM-Earth temperature directory not found:\n"
        f"{tmeanPath}"
    )


# ---------------------------------------------------------------------
# SELECT MONTHS TO PROCESS
# ---------------------------------------------------------------------

# CONTROL_FILE only:
# process every month in forcing_raw_time.

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


# CONTROL_FILE YEAR MONTH:
# process one specific month.

elif len(sys.argv) == 4:

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


# ---------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------

print()

print("=" * 70)
print("PREPARE EM-EARTH FORCING")
print("=" * 70)

print(
    f"Domain       : {domainName}"
)

print(
    f"Control file : {controlPath}"
)

print(
    f"EM-Earth root: {emearthPath}"
)

print(
    f"Output       : {outputPath}"
)

print(
    f"Forcing years: {startYear}-{endYear}"
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


# ---------------------------------------------------------------------
# PROCESS MONTHS
# ---------------------------------------------------------------------

processed_months = []
skipped_months = []
missing_months = []


for year, month in months_to_process:

    ym = f"{year}{month:02d}"


    filename = (
        "EM_Earth_deterministic_hourly_"
        f"NorthAmerica_{ym}.nc"
    )


    prcpFile = (
        prcpPath
        / filename
    )


    tmeanFile = (
        tmeanPath
        / filename
    )


    outputFile = (
        outputPath
        / f"EM_Earth_SUMMA_{ym}.nc"
    )


    print(
        f"Processing {ym}"
    )


    # -------------------------------------------------------------
    # CHECK INPUTS
    # -------------------------------------------------------------

    if not prcpFile.exists():

        print(
            "  Missing precipitation file: "
            f"{prcpFile}"
        )

        missing_months.append(
            ym
        )

        continue


    if not tmeanFile.exists():

        print(
            "  Missing temperature file: "
            f"{tmeanFile}"
        )

        missing_months.append(
            ym
        )

        continue


    if outputFile.exists():

        print(
            "  Output already exists: "
            f"{outputFile}"
        )

        skipped_months.append(
            ym
        )

        continue


    # -------------------------------------------------------------
    # OPEN INPUT DATASETS
    # -------------------------------------------------------------

    with (
        xr.open_dataset(
            prcpFile
        ) as ds_prcp,
        xr.open_dataset(
            tmeanFile
        ) as ds_tmean
    ):


        # ---------------------------------------------------------
        # SPATIAL SUBSET
        #
        # EM-Earth latitude decreases north -> south.
        # Longitude increases west -> east.
        # ---------------------------------------------------------

        ds_prcp = ds_prcp.sel(
            lat=slice(
                subset_lat_max,
                subset_lat_min
            ),
            lon=slice(
                subset_lon_min,
                subset_lon_max
            )
        )


        ds_tmean = ds_tmean.sel(
            lat=slice(
                subset_lat_max,
                subset_lat_min
            ),
            lon=slice(
                subset_lon_min,
                subset_lon_max
            )
        )


        # ---------------------------------------------------------
        # CHECK SUBSET
        # ---------------------------------------------------------

        if (
            ds_prcp.sizes.get(
                "lat",
                0
            ) == 0
            or
            ds_prcp.sizes.get(
                "lon",
                0
            ) == 0
        ):

            raise ValueError(
                "EM-Earth precipitation subset "
                f"is empty for {ym}. "
                "Check forcing_raw_space."
            )


        if (
            ds_tmean.sizes.get(
                "lat",
                0
            ) == 0
            or
            ds_tmean.sizes.get(
                "lon",
                0
            ) == 0
        ):

            raise ValueError(
                "EM-Earth temperature subset "
                f"is empty for {ym}. "
                "Check forcing_raw_space."
            )


        # ---------------------------------------------------------
        # VERIFY TIME / GRID MATCH
        # ---------------------------------------------------------

        if not ds_prcp[
            "time"
        ].identical(
            ds_tmean["time"]
        ):

            raise ValueError(
                "Time mismatch between "
                "precipitation and temperature "
                f"for {ym}"
            )


        if not ds_prcp[
            "lat"
        ].identical(
            ds_tmean["lat"]
        ):

            raise ValueError(
                f"Latitude mismatch for {ym}"
            )


        if not ds_prcp[
            "lon"
        ].identical(
            ds_tmean["lon"]
        ):

            raise ValueError(
                f"Longitude mismatch for {ym}"
            )


        # ---------------------------------------------------------
        # PRECIPITATION
        #
        # EM-Earth:
        #   prcp_corrected = mm hour-1
        #
        # SUMMA:
        #   pptrate = kg m-2 s-1
        #
        # 1 mm water = 1 kg m-2
        # ---------------------------------------------------------

        pptrate = (
            ds_prcp[
                "prcp_corrected"
            ]
            / 3600.0
        ).astype(
            "float32"
        )


        pptrate.attrs = {
            "units": "kg m-2 s-1",
            "long_name": (
                "precipitation rate from "
                "EM-Earth corrected precipitation"
            ),
            "standard_name": (
                "precipitation_flux"
            )
        }


        # ---------------------------------------------------------
        # TEMPERATURE
        #
        # EM-Earth:
        #   tmean = Celsius
        #
        # SUMMA:
        #   airtemp = K
        # ---------------------------------------------------------

        airtemp = (
            ds_tmean[
                "tmean"
            ]
            + 273.15
        ).astype(
            "float32"
        )


        airtemp.attrs = {
            "units": "K",
            "long_name": (
                "air temperature from "
                "EM-Earth mean air temperature"
            ),
            "standard_name": (
                "air_temperature"
            )
        }


        # ---------------------------------------------------------
        # OUTPUT DATASET
        # ---------------------------------------------------------

        ds_out = xr.Dataset(
            data_vars={
                "pptrate": pptrate,
                "airtemp": airtemp
            },
            coords={
                "time": ds_prcp["time"],
                "lat": ds_prcp["lat"],
                "lon": ds_prcp["lon"]
            }
        )


        ds_out = ds_out.rename(
            {
                "lat": "latitude",
                "lon": "longitude"
            }
        )


        # ---------------------------------------------------------
        # GLOBAL METADATA
        # ---------------------------------------------------------

        ds_out.attrs[
            "History"
        ] = (
            "Created from EM-Earth "
            "deterministic hourly forcing"
        )


        ds_out.attrs[
            "Reason"
        ] = (
            "Prepare EM-Earth precipitation "
            "and air temperature for NWAM-SUMMA"
        )


        ds_out.attrs[
            "Source precipitation"
        ] = (
            "EM-Earth prcp_corrected"
        )


        ds_out.attrs[
            "Source temperature"
        ] = (
            "EM-Earth tmean"
        )


        ds_out.attrs[
            "CWARHM domain"
        ] = domainName


        ds_out.attrs[
            "CWARHM control file"
        ] = controlPath.name


        # ---------------------------------------------------------
        # WRITE OUTPUT
        # ---------------------------------------------------------

        encoding = {

            "pptrate": {
                "dtype": "float32",
                "zlib": True,
                "complevel": 4
            },

            "airtemp": {
                "dtype": "float32",
                "zlib": True,
                "complevel": 4
            }
        }


        ds_out.to_netcdf(
            outputFile,
            encoding=encoding
        )


        ds_out.close()


    processed_months.append(
        ym
    )


    print(
        f"  Created: {outputFile}"
    )


# ---------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------

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
        "Warning: could not copy script "
        f"to log folder: {exc}"
    )


# Also preserve the exact domain control file used for this run.

try:

    copyfile(
        controlPath,
        logFolder
        / controlPath.name
    )

except Exception as exc:

    print(
        "Warning: could not copy control file "
        f"to log folder: {exc}"
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
            f"prepare_emearth_{run_label}.txt"
        )
    )


else:

    logFile = (
        logFolder
        / (
            f"{now:%Y%m%d_%H%M%S}_"
            "prepare_emearth_forcing_log.txt"
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
        f"Domain: {domainName}\n"
    )

    file.write(
        f"Control file: {controlPath}\n"
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
        f"already existed: {len(skipped_months)}\n"
    )

    file.write(
        f"Missing input months: "
        f"{len(missing_months)}\n"
    )

    file.write(
        "Converted prcp_corrected from "
        "mm hour-1 to pptrate in "
        "kg m-2 s-1.\n"
    )

    file.write(
        "Converted tmean from Celsius "
        "to airtemp in Kelvin.\n"
    )


# ---------------------------------------------------------------------
# FINISH
# ---------------------------------------------------------------------

print()

print("=" * 70)
print("EM-EARTH FORCING PREPARATION COMPLETED")
print("=" * 70)

print(
    f"Domain          : {domainName}"
)

print(
    f"Months requested: {len(months_to_process)}"
)

print(
    f"Months created  : {len(processed_months)}"
)

print(
    f"Months skipped  : {len(skipped_months)}"
)

print(
    f"Missing inputs  : {len(missing_months)}"
)

print(
    f"Output directory: {outputPath}"
)

print(
    f"Workflow log    : {logFile}"
)