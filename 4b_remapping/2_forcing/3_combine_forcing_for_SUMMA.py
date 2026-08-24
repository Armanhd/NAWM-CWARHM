#!/usr/bin/env python
# coding: utf-8

# Combine remapped ERA5 and EM-Earth forcing into monthly
# SUMMA forcing files.
#
# ERA5 supplies:
#   airpres
#   LWRadAtm
#   SWRadAtm
#   spechum
#   windspd
#
# EM-Earth supplies:
#   pptrate
#   airtemp
#
# Usage:
#
#   One month:
#       python 3_combine_forcing_for_SUMMA.py YEAR MONTH
#
#   Example:
#       python 3_combine_forcing_for_SUMMA.py 1950 1
#
#   No arguments:
#       Processes the complete forcing_raw_time period serially.
#
# For HPC processing, YEAR and MONTH should be supplied by a
# SLURM array.

from pathlib import Path
from datetime import datetime
import sys

import numpy as np
import xarray as xr


# ============================================================
# PROJECT PATHS
# ============================================================

script_dir = Path(__file__).resolve().parent
cwarhm_root = script_dir.parent.parent

control_file = (
    cwarhm_root
    / "0_control_files"
    / "control_active.txt"
)

if not control_file.exists():
    raise FileNotFoundError(
        f"Control file not found:\n{control_file}"
    )


# ============================================================
# CONTROL FILE
# ============================================================

def read_from_control(file, setting):

    with open(file) as contents:

        for line in contents:

            if line.startswith(setting) and not line.startswith("#"):

                value = line.split("|", 1)[1]
                value = value.split("#", 1)[0]

                return value.strip()

    raise ValueError(
        f"Setting not found in control file: {setting}"
    )


def make_default_path(suffix):

    root_path = Path(
        read_from_control(
            control_file,
            "root_path"
        )
    )

    domain_name = read_from_control(
        control_file,
        "domain_name"
    )

    return (
        root_path
        / f"domain_{domain_name}"
        / suffix
    )


# ============================================================
# DOMAIN / TIME SETTINGS
# ============================================================

domain = read_from_control(
    control_file,
    "domain_name"
)

forcing_years = read_from_control(
    control_file,
    "forcing_raw_time"
)

start_year, end_year = [
    int(x.strip())
    for x in forcing_years.split(",")
]

data_step = int(
    read_from_control(
        control_file,
        "forcing_time_step_size"
    )
)


# ============================================================
# PATHS
# ============================================================

era5_dir = make_default_path(
    "forcing/3_basin_averaged_data/ERA5"
)

emearth_dir = make_default_path(
    "forcing/3_basin_averaged_data/EM_Earth"
)

output_dir = make_default_path(
    "forcing/4_SUMMA_input"
)

output_dir.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# VARIABLE DEFINITIONS
# ============================================================

era5_variables = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "spechum",
    "windspd"
]

emearth_variables = [
    "pptrate",
    "airtemp"
]


# ============================================================
# FILE NAMING
# ============================================================

era5_case = f"{domain}_ERA5"
emearth_case = f"{domain}_EM_Earth"


def get_month_files(year, month):

    ym = f"{year}{month:02d}"

    era5_file = (
        era5_dir
        / (
            f"{era5_case}_remapped_"
            f"ERA5_SUMMA_{ym}.nc"
        )
    )

    emearth_file = (
        emearth_dir
        / (
            f"{emearth_case}_remapped_"
            f"EM_Earth_SUMMA_{ym}.nc"
        )
    )

    output_file = (
        output_dir
        / f"NWAM_SUMMA_forcing_{ym}.nc"
    )

    return (
        ym,
        era5_file,
        emearth_file,
        output_file
    )


# ============================================================
# COMBINE ONE MONTH
# ============================================================

def combine_month(year, month):

    (
        ym,
        era5_file,
        emearth_file,
        output_file
    ) = get_month_files(
        year,
        month
    )

    print()
    print("============================================================")
    print(f"COMBINING SUMMA FORCING: {ym}")
    print("============================================================")

    # --------------------------------------------------------
    # Check required files
    # --------------------------------------------------------

    if not era5_file.exists():

        raise FileNotFoundError(
            f"Remapped ERA5 forcing not found:\n"
            f"{era5_file}"
        )

    if not emearth_file.exists():

        raise FileNotFoundError(
            f"Remapped EM-Earth forcing not found:\n"
            f"{emearth_file}"
        )

    # --------------------------------------------------------
    # Restart-safe
    # --------------------------------------------------------

    if output_file.exists():

        print(
            f"Output already exists; skipping:\n"
            f"{output_file}"
        )

        return

    print(f"ERA5 input    : {era5_file}")
    print(f"EM-Earth input: {emearth_file}")
    print(f"Output        : {output_file}")

    # --------------------------------------------------------
    # Open datasets
    # --------------------------------------------------------

    with xr.open_dataset(era5_file) as era5, \
         xr.open_dataset(emearth_file) as emearth:

        # ----------------------------------------------------
        # Check expected variables
        # ----------------------------------------------------

        for variable in era5_variables:

            if variable not in era5:

                raise RuntimeError(
                    f"{variable} missing from "
                    f"{era5_file.name}"
                )

        for variable in emearth_variables:

            if variable not in emearth:

                raise RuntimeError(
                    f"{variable} missing from "
                    f"{emearth_file.name}"
                )

        # ----------------------------------------------------
        # Check coordinates
        # ----------------------------------------------------

        if "time" not in era5 or "time" not in emearth:

            raise RuntimeError(
                f"Missing time coordinate for {ym}"
            )

        if not np.array_equal(
            era5["time"].values,
            emearth["time"].values
        ):

            raise RuntimeError(
                f"ERA5 and EM-Earth time mismatch "
                f"for {ym}"
            )

        if "hruId" not in era5 or "hruId" not in emearth:

            raise RuntimeError(
                f"Missing hruId for {ym}"
            )

        if not np.array_equal(
            era5["hruId"].values,
            emearth["hruId"].values
        ):

            raise RuntimeError(
                f"ERA5 and EM-Earth HRU ID mismatch "
                f"for {ym}"
            )

        # ----------------------------------------------------
        # Create SUMMA dataset
        # ----------------------------------------------------

        ds_out = xr.Dataset()

        # Coordinates
        ds_out = ds_out.assign_coords(
            time=era5["time"]
        )

        if "hru" in era5.coords:
            ds_out = ds_out.assign_coords(
                hru=era5["hru"]
            )

        elif "hru" in era5.dims:
            ds_out = ds_out.assign_coords(
                hru=np.arange(
                    era5.sizes["hru"]
                )
            )

        # HRU identifier
        ds_out["hruId"] = era5["hruId"]

        # ----------------------------------------------------
        # Retain HRU latitude / longitude if available
        # ----------------------------------------------------

        if "latitude" in era5:
            ds_out["latitude"] = era5["latitude"]

        elif "latitude" in emearth:
            ds_out["latitude"] = emearth["latitude"]

        if "longitude" in era5:
            ds_out["longitude"] = era5["longitude"]

        elif "longitude" in emearth:
            ds_out["longitude"] = emearth["longitude"]

        # ----------------------------------------------------
        # ERA5 variables
        # ----------------------------------------------------

        for variable in era5_variables:

            ds_out[variable] = (
                era5[variable]
                .astype("float32")
            )

        # ----------------------------------------------------
        # EM-Earth precipitation
        # ----------------------------------------------------

        missing_pptrate = int(
            np.count_nonzero(
                ~np.isfinite(
                    emearth["pptrate"].values
                )
            )
        )

        if missing_pptrate > 0:

            print(
                f"WARNING: {missing_pptrate} non-finite "
                f"pptrate values found."
            )

            print(
                "Replacing non-finite pptrate values "
                "with 0.0."
            )

        ds_out["pptrate"] = (
            emearth["pptrate"]
            .where(
                np.isfinite(
                    emearth["pptrate"]
                ),
                0.0
            )
            .astype("float32")
        )

        # ----------------------------------------------------
        # EM-Earth temperature
        # ----------------------------------------------------

        ds_out["airtemp"] = (
            emearth["airtemp"]
            .astype("float32")
        )

        # ----------------------------------------------------
        # SUMMA data step
        # ----------------------------------------------------

        ds_out["data_step"] = xr.DataArray(
            data_step
        )

        ds_out["data_step"].attrs[
            "long_name"
        ] = "data step length in seconds"

        ds_out["data_step"].attrs[
            "units"
        ] = "s"

        # ----------------------------------------------------
        # Metadata
        # ----------------------------------------------------

        ds_out.attrs["History"] = (
            "Combined NWAM forcing prepared for SUMMA"
        )

        ds_out.attrs["Domain"] = domain

        ds_out.attrs["ERA5_variables"] = (
            "airpres, LWRadAtm, SWRadAtm, "
            "spechum, windspd"
        )

        ds_out.attrs["EM_Earth_variables"] = (
            "pptrate, airtemp"
        )

        ds_out.attrs[
            "forcing_time_step_seconds"
        ] = data_step

        ds_out.attrs[
            "precipitation_missing_value_treatment"
        ] = (
            "Non-finite EM-Earth pptrate values "
            "filled with 0.0."
        )

        # ----------------------------------------------------
        # Compression
        # ----------------------------------------------------

        encoding = {}

        for variable in (
            era5_variables
            + emearth_variables
        ):

            encoding[variable] = {
                "dtype": "float32",
                "zlib": True,
                "complevel": 4
            }

        # ----------------------------------------------------
        # Write
        # ----------------------------------------------------

        ds_out.to_netcdf(
            output_file,
            encoding=encoding
        )

        ds_out.close()

    # --------------------------------------------------------
    # Log
    # --------------------------------------------------------

    log_dir = (
        output_dir
        / "_workflow_log"
    )

    log_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    log_file = (
        log_dir
        / f"combine_forcing_{ym}.txt"
    )

    with open(log_file, "w") as f:

        f.write(
            f"Combined forcing completed "
            f"{datetime.now():%Y-%m-%d %H:%M:%S}\n"
        )

        f.write(
            f"Domain: {domain}\n"
        )

        f.write(
            f"Month: {ym}\n"
        )

        f.write(
            f"ERA5: {era5_file}\n"
        )

        f.write(
            f"EM-Earth: {emearth_file}\n"
        )

        f.write(
            f"Output: {output_file}\n"
        )

        f.write(
            f"data_step: {data_step} s\n"
        )

    print()
    print(f"Created: {output_file}")


# ============================================================
# COMMAND-LINE MODE
# ============================================================

if len(sys.argv) == 3:

    year = int(
        sys.argv[1]
    )

    month = int(
        sys.argv[2]
    )

    if year < start_year or year > end_year:

        raise ValueError(
            f"Year {year} is outside forcing_raw_time "
            f"{start_year},{end_year}"
        )

    if month < 1 or month > 12:

        raise ValueError(
            "Month must be between 1 and 12."
        )

    combine_month(
        year,
        month
    )


# ============================================================
# SERIAL FALLBACK
# ============================================================

elif len(sys.argv) == 1:

    print(
        "No YEAR MONTH arguments supplied. "
        "Running complete forcing period serially."
    )

    for year in range(
        start_year,
        end_year + 1
    ):

        for month in range(
            1,
            13
        ):

            combine_month(
                year,
                month
            )


else:

    raise SystemExit(
        "Usage:\n"
        "  python 3_combine_forcing_for_SUMMA.py\n"
        "or\n"
        "  python 3_combine_forcing_for_SUMMA.py YEAR MONTH"
    )


print()
print("Finished combining forcing.")
print(f"Output directory: {output_dir}")