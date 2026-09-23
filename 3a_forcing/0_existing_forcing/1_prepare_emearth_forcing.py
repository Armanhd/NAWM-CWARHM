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
#
# =====================================================================
# KNOWN EM-EARTH ARCHIVE-GAP HANDLING
# =====================================================================
#
# EM-Earth contains a known seven-hour gap at:
#
#   1950-01-01 00:00 through 06:00 UTC
#   1979-01-01 00:00 through 06:00 UTC
#
# These two gaps are repaired explicitly before the prepared forcing
# files are written.
#
# Precipitation
# -------------
#
# For BOTH known gaps:
#
#   prcp / prcp_corrected = 0.0 mm hour-1
#
#
# Temperature
# -----------
#
# For BOTH known gaps:
#
#   1950-01-01 00:00 through 06:00 UTC
#   1979-01-01 00:00 through 06:00 UTC
#
# the missing temperatures are filled using the first available valid
# EM-Earth temperature at:
#
#   07:00 UTC on the same day.
#
# No temporal interpolation is performed.
#
#
# IMPORTANT
# ---------
#
# Existing valid values are NEVER overwritten.
#
# No other missing timestamps are automatically repaired.
# Any other unexpected temporal gap causes the workflow to FAIL.
#
# This preserves the existing NWAM/CWARHM missing-value behavior:
#
#   ERA5 variables       -> non-finite values fail later
#   EM-Earth airtemp     -> non-finite values fail later
#   EM-Earth pptrate     -> non-finite values are handled later by
#                           the existing forcing-combination workflow
#
# =====================================================================


from pathlib import Path
from datetime import datetime
from shutil import copyfile
import sys

import numpy as np
import pandas as pd
import xarray as xr


# =====================================================================
# ARGUMENTS
# =====================================================================

if len(sys.argv) not in (2, 4):
    raise SystemExit(
        "Usage:\n"
        "  python 1_prepare_emearth_forcing.py CONTROL_FILE\n"
        "or\n"
        "  python 1_prepare_emearth_forcing.py CONTROL_FILE YEAR MONTH"
    )

controlPath = Path(sys.argv[1]).expanduser().resolve()

if not controlPath.is_file():
    raise FileNotFoundError(f"Control file not found:\n{controlPath}")


# =====================================================================
# CONTROL FUNCTIONS
# =====================================================================

def read_from_control(file, setting):
    with open(file) as contents:
        for line in contents:
            stripped = line.strip()

            if not stripped or stripped.startswith("#") or "|" not in stripped:
                continue

            left, right = stripped.split("|", 1)

            if left.strip() == setting:
                value = right.split("#", 1)[0].strip()

                if not value:
                    raise ValueError(f"Setting '{setting}' is empty in:\n{file}")

                return value

    raise ValueError(f"Setting '{setting}' not found in:\n{file}")


def make_default_path(suffix):
    root = Path(read_from_control(controlPath, "root_path"))
    domain = read_from_control(controlPath, "domain_name")
    return root / f"domain_{domain}" / suffix


# =====================================================================
# KNOWN GAP SETTINGS
# =====================================================================

KNOWN_GAP_MONTHS = {(1950, 1), (1979, 1)}


def expected_month_time(year, month):
    """Return the complete expected hourly time coordinate for one month."""

    start = pd.Timestamp(year=year, month=month, day=1)

    if month == 12:
        end = pd.Timestamp(year=year + 1, month=1, day=1)
    else:
        end = pd.Timestamp(year=year, month=month + 1, day=1)

    return pd.date_range(start=start, end=end, freq="h", inclusive="left")


def expected_known_gap(year):
    """Return the documented seven missing timestamps for 1 January."""

    return pd.date_range(
        start=pd.Timestamp(year=year, month=1, day=1, hour=0),
        periods=7,
        freq="h",
    )


def check_known_gap(dataset, year, month):
    """
    Check the time coordinate for missing timestamps.

    Returns an empty index if no timestamps are missing.

    The only automatically repairable gaps are:
        1950-01-01 00:00-06:00 UTC
        1979-01-01 00:00-06:00 UTC

    Any other gap stops the workflow.
    """

    expected = expected_month_time(year, month)
    actual = pd.DatetimeIndex(dataset["time"].values)

    if actual.has_duplicates:
        raise RuntimeError(
            f"Duplicate EM-Earth timestamps found for {year}-{month:02d}."
        )

    missing = expected.difference(actual)

    if len(missing) == 0:
        return missing

    if (year, month) not in KNOWN_GAP_MONTHS:
        raise RuntimeError(
            f"Unexpected EM-Earth timestamp gap for {year}-{month:02d}:\n"
            + "\n".join(f"  {timestamp}" for timestamp in missing)
        )

    allowed = expected_known_gap(year)

    if not missing.equals(allowed):
        raise RuntimeError(
            f"Unexpected EM-Earth timestamp gap for {year}-{month:02d}.\n\n"
            "Automatic repair is permitted only for:\n"
            f"{allowed[0]} through {allowed[-1]}\n\n"
            "Actual missing timestamps:\n"
            + "\n".join(f"  {timestamp}" for timestamp in missing)
        )

    return missing


def repair_precipitation_gap(dataset, year, month, variable_name):
    """
    Repair the known seven-hour precipitation gap.

    Missing timestamps from 00:00 through 06:00 UTC are inserted and
    precipitation is set to 0.0 mm hour-1.

    Existing valid values are not modified.
    """

    missing = check_known_gap(dataset, year, month)

    if len(missing) == 0:
        return dataset, 0

    expected = expected_month_time(year, month)
    repaired = dataset.reindex(time=expected)

    repaired[variable_name].loc[dict(time=missing)] = 0.0

    if bool(repaired[variable_name].sel(time=missing).isnull().any()):
        raise RuntimeError(
            f"Precipitation gap repair failed for {year}-{month:02d}."
        )

    print(
        f"  Repaired precipitation gap: "
        f"{len(missing)} hours -> 0.0 mm h-1"
    )

    return repaired, len(missing)


def repair_temperature_gap(dataset, year, month):
    """
    Repair the known seven-hour temperature gap.

    For both 1950 and 1979, missing temperatures from 00:00 through
    06:00 UTC are filled using the first available valid temperature
    at 07:00 UTC on the same day.

    No temporal interpolation is performed.
    Existing valid values are not modified.
    """

    missing = check_known_gap(dataset, year, month)

    if len(missing) == 0:
        return dataset, 0, "none"

    expected = expected_month_time(year, month)
    repaired = dataset.reindex(time=expected)

    first_valid = pd.Timestamp(year=year, month=1, day=1, hour=7)

    if first_valid not in pd.DatetimeIndex(dataset["time"].values):
        raise RuntimeError(
            f"Cannot repair {year} temperature gap because "
            f"{first_valid} is missing."
        )

    first_temperature = repaired["tmean"].sel(time=first_valid)

    for timestamp in missing:
        repaired["tmean"].loc[dict(time=timestamp)] = first_temperature

    if bool(repaired["tmean"].sel(time=missing).isnull().any()):
        raise RuntimeError(
            f"Temperature gap repair failed for {year}-{month:02d}."
        )

    method = "filled from first valid temperature at 07:00"

    print(
        f"  Repaired temperature gap: "
        f"{len(missing)} hours -> {method}"
    )

    return repaired, len(missing), method


# =====================================================================
# DOMAIN / SETTINGS
# =====================================================================

domainName = read_from_control(controlPath, "domain_name")
emearthPath = Path(read_from_control(controlPath, "forcing_emearth_path"))

try:
    emearthPrecip = read_from_control(controlPath, "forcing_emearth_precip")
except ValueError:
    emearthPrecip = "prcp_corrected"
    print(
        "WARNING: forcing_emearth_precip not defined. "
        "Defaulting to prcp_corrected."
    )

if emearthPrecip not in {"prcp", "prcp_corrected"}:
    raise ValueError(
        f"Invalid forcing_emearth_precip: {emearthPrecip}\n"
        "Allowed: prcp, prcp_corrected"
    )

forcingRawPath = read_from_control(controlPath, "forcing_raw_path")

if forcingRawPath == "default":
    forcingRawPath = make_default_path("forcing/1_raw_data")
else:
    forcingRawPath = Path(forcingRawPath)

outputPath = forcingRawPath / "EM_Earth_prepared"
outputPath.mkdir(parents=True, exist_ok=True)


# =====================================================================
# TIME PERIOD
# =====================================================================

years = read_from_control(controlPath, "forcing_raw_time")

try:
    startYear, endYear = [int(x.strip()) for x in years.split(",")]
except Exception as exc:
    raise ValueError(
        "forcing_raw_time must use START_YEAR,END_YEAR format."
    ) from exc

if startYear > endYear:
    raise ValueError(f"Invalid forcing_raw_time: {startYear},{endYear}")


# =====================================================================
# SPATIAL EXTENT
# =====================================================================

space = read_from_control(controlPath, "forcing_raw_space")

try:
    latMax, lonMin, latMin, lonMax = [float(x.strip()) for x in space.split("/")]
except Exception as exc:
    raise ValueError(
        "forcing_raw_space must use LAT_MAX/LON_MIN/LAT_MIN/LON_MAX."
    ) from exc

if latMin >= latMax or lonMin >= lonMax:
    raise ValueError("Invalid forcing_raw_space bounds.")

buffer = 0.1

subset_lat_max = latMax + buffer
subset_lat_min = latMin - buffer
subset_lon_min = lonMin - buffer
subset_lon_max = lonMax + buffer


# =====================================================================
# INPUT DIRECTORIES
# =====================================================================

prcpPath = emearthPath / "prcp" / "NorthAmerica"
tmeanPath = emearthPath / "tmean" / "NorthAmerica"

if not prcpPath.exists():
    raise FileNotFoundError(
        f"EM-Earth precipitation directory not found:\n{prcpPath}"
    )

if not tmeanPath.exists():
    raise FileNotFoundError(
        f"EM-Earth temperature directory not found:\n{tmeanPath}"
    )


# =====================================================================
# MONTHS TO PROCESS
# =====================================================================

if len(sys.argv) == 2:
    months_to_process = [
        (year, month)
        for year in range(startYear, endYear + 1)
        for month in range(1, 13)
    ]

else:
    runYear = int(sys.argv[2])
    runMonth = int(sys.argv[3])

    if not startYear <= runYear <= endYear:
        raise ValueError(f"Year {runYear} outside {startYear}-{endYear}.")

    if not 1 <= runMonth <= 12:
        raise ValueError("Month must be between 1 and 12.")

    months_to_process = [(runYear, runMonth)]


# =====================================================================
# REPORT
# =====================================================================

print()
print("=" * 70)
print("PREPARE EM-EARTH FORCING")
print("=" * 70)
print(f"Domain        : {domainName}")
print(f"Control file  : {controlPath}")
print(f"EM-Earth root : {emearthPath}")
print(f"Precip source : {emearthPrecip}")
print(f"Output        : {outputPath}")
print(f"Forcing years : {startYear}-{endYear}")
print(f"Months run    : {len(months_to_process)}")
print(f"Latitude      : {subset_lat_min} to {subset_lat_max}")
print(f"Longitude     : {subset_lon_min} to {subset_lon_max}")
print()


# =====================================================================
# PROCESS MONTHS
# =====================================================================

processed_months = []
skipped_months = []
missing_months = []
gap_repairs = []


for year, month in months_to_process:

    ym = f"{year}{month:02d}"
    filename = f"EM_Earth_deterministic_hourly_NorthAmerica_{ym}.nc"

    prcpFile = prcpPath / filename
    tmeanFile = tmeanPath / filename
    outputFile = outputPath / f"EM_Earth_SUMMA_{ym}.nc"

    print(f"Processing {ym}")

    if not prcpFile.exists():
        print(f"  Missing precipitation file: {prcpFile}")
        missing_months.append(ym)
        continue

    if not tmeanFile.exists():
        print(f"  Missing temperature file: {tmeanFile}")
        missing_months.append(ym)
        continue

    if outputFile.exists():
        print(f"  Output already exists: {outputFile}")
        skipped_months.append(ym)
        continue


    with xr.open_dataset(prcpFile) as ds_prcp_raw, xr.open_dataset(tmeanFile) as ds_tmean_raw:

        ds_prcp = ds_prcp_raw.load()
        ds_tmean = ds_tmean_raw.load()


        # -------------------------------------------------------------
        # REPAIR KNOWN ARCHIVE GAPS
        # -------------------------------------------------------------

        ds_prcp, precip_inserted = repair_precipitation_gap(
            ds_prcp,
            year,
            month,
            emearthPrecip,
        )

        ds_tmean, temp_inserted, temp_method = repair_temperature_gap(
            ds_tmean,
            year,
            month,
        )

        if precip_inserted or temp_inserted:
            gap_repairs.append(
                {
                    "month": ym,
                    "precip_hours": precip_inserted,
                    "temperature_hours": temp_inserted,
                    "temperature_method": temp_method,
                }
            )


        # -------------------------------------------------------------
        # SPATIAL SUBSET
        # -------------------------------------------------------------

        ds_prcp = ds_prcp.sel(
            lat=slice(subset_lat_max, subset_lat_min),
            lon=slice(subset_lon_min, subset_lon_max),
        )

        ds_tmean = ds_tmean.sel(
            lat=slice(subset_lat_max, subset_lat_min),
            lon=slice(subset_lon_min, subset_lon_max),
        )

        if ds_prcp.sizes.get("lat", 0) == 0 or ds_prcp.sizes.get("lon", 0) == 0:
            raise ValueError(
                f"EM-Earth precipitation subset empty for {ym}."
            )

        if ds_tmean.sizes.get("lat", 0) == 0 or ds_tmean.sizes.get("lon", 0) == 0:
            raise ValueError(
                f"EM-Earth temperature subset empty for {ym}."
            )


        # -------------------------------------------------------------
        # TIME / GRID CHECKS
        # -------------------------------------------------------------

        if not ds_prcp["time"].identical(ds_tmean["time"]):
            raise ValueError(
                f"Precipitation/temperature time mismatch for {ym}."
            )

        if not ds_prcp["lat"].identical(ds_tmean["lat"]):
            raise ValueError(f"Latitude mismatch for {ym}.")

        if not ds_prcp["lon"].identical(ds_tmean["lon"]):
            raise ValueError(f"Longitude mismatch for {ym}.")

        if emearthPrecip not in ds_prcp.variables:
            raise RuntimeError(
                f"{emearthPrecip} missing from:\n{prcpFile}\n"
                f"Available: {list(ds_prcp.variables)}"
            )


        # -------------------------------------------------------------
        # PRECIPITATION
        # -------------------------------------------------------------

        pptrate = (ds_prcp[emearthPrecip] / 3600.0).astype("float32")

        pptrate.attrs = {
            "units": "kg m-2 s-1",
            "long_name": f"precipitation rate from EM-Earth {emearthPrecip}",
            "standard_name": "precipitation_flux",
        }


        # -------------------------------------------------------------
        # TEMPERATURE
        # -------------------------------------------------------------

        airtemp = (ds_tmean["tmean"] + 273.15).astype("float32")

        airtemp.attrs = {
            "units": "K",
            "long_name": "air temperature from EM-Earth mean air temperature",
            "standard_name": "air_temperature",
        }


        # -------------------------------------------------------------
        # OUTPUT
        # -------------------------------------------------------------

        ds_out = xr.Dataset(
            data_vars={
                "pptrate": pptrate,
                "airtemp": airtemp,
            },
            coords={
                "time": ds_prcp["time"],
                "lat": ds_prcp["lat"],
                "lon": ds_prcp["lon"],
            },
        ).rename(
            {
                "lat": "latitude",
                "lon": "longitude",
            }
        )

        ds_out.attrs.update(
            {
                "History": "Created from EM-Earth deterministic hourly forcing",
                "Reason": "Prepare EM-Earth precipitation and air temperature for NWAM-SUMMA",
                "Source precipitation": f"EM-Earth {emearthPrecip}",
                "Source temperature": "EM-Earth tmean",
                "CWARHM domain": domainName,
                "CWARHM control file": controlPath.name,
            }
        )

        if precip_inserted or temp_inserted:
            ds_out.attrs["known_EM_Earth_gap_repair"] = (
                f"{ym}: inserted missing 00:00-06:00 UTC timestamps. "
                "Precipitation filled with 0.0 mm hour-1. "
                "Temperature filled using the valid 07:00 temperature."
            )

            ds_out.attrs["known_EM_Earth_gap_hours_inserted"] = 7

        encoding = {
            "pptrate": {
                "dtype": "float32",
                "zlib": True,
                "complevel": 4,
            },
            "airtemp": {
                "dtype": "float32",
                "zlib": True,
                "complevel": 4,
            },
        }

        ds_out.to_netcdf(
            outputFile,
            encoding=encoding,
        )

        ds_out.close()


    processed_months.append(ym)
    print(f"  Created: {outputFile}")


# =====================================================================
# LOGGING
# =====================================================================

logFolder = outputPath / "_workflow_log"
logFolder.mkdir(parents=True, exist_ok=True)

thisFile = Path(__file__).name

try:
    copyfile(Path(__file__).resolve(), logFolder / thisFile)
except Exception as exc:
    print(f"Warning: could not copy script to log folder: {exc}")

try:
    copyfile(controlPath, logFolder / controlPath.name)
except Exception as exc:
    print(f"Warning: could not copy control file to log folder: {exc}")


now = datetime.now()

if len(months_to_process) == 1:
    run_label = months_to_process[0][0] * 100 + months_to_process[0][1]
    logFile = (
        logFolder
        / f"{now:%Y%m%d_%H%M%S}_prepare_emearth_{run_label}.txt"
    )
else:
    logFile = (
        logFolder
        / f"{now:%Y%m%d_%H%M%S}_prepare_emearth_forcing_log.txt"
    )


with open(logFile, "w") as file:

    file.write(
        f"Log generated by {thisFile} "
        f"on {now:%Y/%m/%d %H:%M:%S}\n"
    )

    file.write(f"Domain: {domainName}\n")
    file.write(f"Control file: {controlPath}\n")
    file.write(f"Configured forcing period: {startYear}-{endYear}\n")
    file.write(f"Months requested: {len(months_to_process)}\n")
    file.write(f"Months created: {len(processed_months)}\n")
    file.write(f"Months skipped: {len(skipped_months)}\n")
    file.write(f"Missing input months: {len(missing_months)}\n")
    file.write(f"EM-Earth precipitation source: {emearthPrecip}\n")

    file.write("\nKnown EM-Earth archive-gap handling:\n")

    file.write("1950-01-01 00:00-06:00 UTC:\n")
    file.write("  precipitation = 0.0 mm hour-1\n")
    file.write("  temperature = first valid 07:00 temperature\n")

    file.write("1979-01-01 00:00-06:00 UTC:\n")
    file.write("  precipitation = 0.0 mm hour-1\n")
    file.write("  temperature = first valid 07:00 temperature\n")

    file.write(f"Months repaired: {len(gap_repairs)}\n")

    for repair in gap_repairs:
        file.write(
            f"{repair['month']}: "
            f"precip_hours={repair['precip_hours']}, "
            f"temperature_hours={repair['temperature_hours']}, "
            f"temperature_method={repair['temperature_method']}\n"
        )


# =====================================================================
# FINISH
# =====================================================================

print()
print("=" * 70)
print("EM-EARTH FORCING PREPARATION COMPLETED")
print("=" * 70)
print(f"Domain           : {domainName}")
print(f"Months requested : {len(months_to_process)}")
print(f"Months created   : {len(processed_months)}")
print(f"Months skipped   : {len(skipped_months)}")
print(f"Missing inputs   : {len(missing_months)}")
print(f"Known gaps fixed : {len(gap_repairs)}")
print(f"Output directory : {outputPath}")
print(f"Workflow log     : {logFile}")