#!/usr/bin/env python3
# coding: utf-8

# Combine remapped ERA5 and EM-Earth forcing into monthly
# SUMMA forcing files.
#
# ERA5 supplies:
#
#   airpres
#   LWRadAtm
#   SWRadAtm
#   spechum
#   windspd
#
# EM-Earth supplies:
#
#   pptrate
#   airtemp
#
# Usage
# -----
#
# One month:
#
# python 3_combine_forcing_for_SUMMA.py \
# /path/to/control_DOMAIN.txt \
# YEAR MONTH
#
# Example:
#
# python 3_combine_forcing_for_SUMMA.py \
# /work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/control_MERIT_717.txt \
# 1950 1
#
# Complete forcing period serially:
#
# python 3_combine_forcing_for_SUMMA.py \
# /path/to/control_DOMAIN.txt
#
#
# IMPORTANT
# ---------
#
# This script reads the supplied domain-specific control file.
#
# It does NOT read or modify control_active.txt.
#
# ERA5 and EM-Earth HRU order must be identical before the
# datasets are combined.
#
# Missing EM-Earth precipitation values are replaced by zero.
# The number of values replaced is explicitly reported and
# written to the workflow log.

import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import xarray as xr


# ============================================================
# INPUT CONTROL FILE / ARGUMENTS
# ============================================================

if len(sys.argv) not in (2, 4):

    raise SystemExit(
        "Usage:\n"
        "\n"
        "Complete forcing period:\n"
        "  python 3_combine_forcing_for_SUMMA.py "
        "/path/to/control_DOMAIN.txt\n"
        "\n"
        "One month:\n"
        "  python 3_combine_forcing_for_SUMMA.py "
        "/path/to/control_DOMAIN.txt YEAR MONTH"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).resolve()


if not CONTROL_FILE.exists():

    raise FileNotFoundError(
        f"Control file not found:\n"
        f"{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FILE FUNCTIONS
# ============================================================

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


def make_default_path(suffix):
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


# ============================================================
# DOMAIN / TIME SETTINGS
# ============================================================

domain = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


forcing_years = read_from_control(
    CONTROL_FILE,
    "forcing_raw_time"
)


try:

    start_year, end_year = [
        int(value.strip())
        for value in forcing_years.split(",")
    ]

except Exception as exc:

    raise ValueError(
        "forcing_raw_time must have format:\n"
        "START_YEAR,END_YEAR\n\n"
        f"Current value: {forcing_years}"
    ) from exc


if start_year > end_year:

    raise ValueError(
        "forcing_raw_time start year is greater "
        "than end year."
    )


data_step = int(
    read_from_control(
        CONTROL_FILE,
        "forcing_time_step_size"
    )
)


if data_step <= 0:

    raise ValueError(
        "forcing_time_step_size must be greater than zero."
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


if not era5_dir.exists():

    raise FileNotFoundError(
        "ERA5 basin-averaged forcing directory not found:\n"
        f"{era5_dir}"
    )


if not emearth_dir.exists():

    raise FileNotFoundError(
        "EM-Earth basin-averaged forcing directory not found:\n"
        f"{emearth_dir}"
    )


output_dir.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# VARIABLE DEFINITIONS
# ============================================================

ERA5_VARIABLES = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "spechum",
    "windspd",
]


EMEARTH_VARIABLES = [
    "pptrate",
    "airtemp",
]


SUMMA_FORCING_VARIABLES = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "pptrate",
    "airtemp",
    "spechum",
    "windspd",
]


# ============================================================
# CASE / FILE NAMES
# ============================================================

era5_case = (
    f"{domain}_ERA5"
)


emearth_case = (
    f"{domain}_EM_Earth"
)


def get_month_files(year, month):

    ym = (
        f"{year}{month:02d}"
    )


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
        output_file,
    )


# ============================================================
# DATASET VALIDATION FUNCTIONS
# ============================================================

def validate_source_dataset(
    dataset,
    filename,
    variables
):

    if "time" not in dataset:

        raise RuntimeError(
            f"time is missing from:\n"
            f"{filename}"
        )


    if "hruId" not in dataset:

        raise RuntimeError(
            f"hruId is missing from:\n"
            f"{filename}"
        )


    if "hru" not in dataset.dims:

        raise RuntimeError(
            f"hru dimension is missing from:\n"
            f"{filename}"
        )


    for variable in variables:

        if variable not in dataset:

            raise RuntimeError(
                f"{variable} is missing from:\n"
                f"{filename}"
            )


def count_nonfinite(data_array):

    return int(
        np.count_nonzero(
            ~np.isfinite(
                data_array.values
            )
        )
    )


# ============================================================
# COMBINE ONE MONTH
# ============================================================

def combine_month(year, month):

    (
        ym,
        era5_file,
        emearth_file,
        output_file,
    ) = get_month_files(
        year,
        month
    )


    print()
    print("=" * 70)
    print("COMBINE ERA5 + EM-EARTH FOR SUMMA")
    print("=" * 70)

    print(
        f"Domain       : {domain}"
    )

    print(
        f"Control file : {CONTROL_FILE}"
    )

    print(
        f"Month        : {ym}"
    )


    # ========================================================
    # INPUT CHECKS
    # ========================================================

    if not era5_file.exists():

        raise FileNotFoundError(
            "Remapped ERA5 forcing not found:\n"
            f"{era5_file}"
        )


    if not emearth_file.exists():

        raise FileNotFoundError(
            "Remapped EM-Earth forcing not found:\n"
            f"{emearth_file}"
        )


    print()
    print(
        f"ERA5 input    : {era5_file}"
    )

    print(
        f"EM-Earth input: {emearth_file}"
    )

    print(
        f"Output        : {output_file}"
    )


    # ========================================================
    # OPEN INPUT DATASETS
    # ========================================================

    with xr.open_dataset(
        era5_file
    ) as era5, xr.open_dataset(
        emearth_file
    ) as emearth:


        validate_source_dataset(
            era5,
            era5_file,
            ERA5_VARIABLES
        )


        validate_source_dataset(
            emearth,
            emearth_file,
            EMEARTH_VARIABLES
        )


        # ====================================================
        # DIMENSION CHECKS
        # ====================================================

        era5_hru_count = (
            era5.sizes["hru"]
        )

        emearth_hru_count = (
            emearth.sizes["hru"]
        )


        if era5_hru_count != emearth_hru_count:

            raise RuntimeError(
                "ERA5 and EM-Earth HRU counts differ.\n\n"
                f"ERA5     : {era5_hru_count}\n"
                f"EM-Earth : {emearth_hru_count}"
            )


        era5_time_count = (
            era5.sizes["time"]
        )

        emearth_time_count = (
            emearth.sizes["time"]
        )


        if era5_time_count != emearth_time_count:

            raise RuntimeError(
                "ERA5 and EM-Earth timestep counts differ.\n\n"
                f"ERA5     : {era5_time_count}\n"
                f"EM-Earth : {emearth_time_count}"
            )


        # ====================================================
        # TIME CHECK
        # ====================================================

        if not np.array_equal(
            era5["time"].values,
            emearth["time"].values
        ):

            raise RuntimeError(
                "ERA5 and EM-Earth time coordinates "
                f"do not match for {ym}."
            )


        # ====================================================
        # HRU ID CHECK
        # ====================================================

        era5_hru_ids = (
            era5["hruId"]
            .values
        )


        emearth_hru_ids = (
            emearth["hruId"]
            .values
        )


        if not np.array_equal(
            era5_hru_ids,
            emearth_hru_ids
        ):

            raise RuntimeError(
                "ERA5 and EM-Earth HRU IDs/order "
                f"do not match for {ym}."
            )


        if len(
            np.unique(
                era5_hru_ids
            )
        ) != era5_hru_count:

            raise RuntimeError(
                "Duplicate hruId values found."
            )


        print()
        print(
            f"HRUs         : {era5_hru_count}"
        )

        print(
            f"Time steps   : {era5_time_count}"
        )

        print(
            "HRU order    : ERA5 and EM-Earth match"
        )


        # ====================================================
        # CHECK ERA5 MISSING VALUES
        # ====================================================

        print()
        print("ERA5 missing values")
        print("-" * 70)


        for variable in ERA5_VARIABLES:

            missing = count_nonfinite(
                era5[variable]
            )

            print(
                f"{variable:<10}: {missing}"
            )


            if missing > 0:

                raise RuntimeError(
                    f"{variable} contains {missing} "
                    "non-finite ERA5 values.\n\n"
                    "Do not create SUMMA forcing until "
                    "this is resolved."
                )


        # ====================================================
        # CHECK EM-EARTH TEMPERATURE
        # ====================================================

        missing_airtemp = (
            count_nonfinite(
                emearth["airtemp"]
            )
        )


        print()
        print("EM-Earth missing values")
        print("-" * 70)

        print(
            f"{'airtemp':<10}: "
            f"{missing_airtemp}"
        )


        if missing_airtemp > 0:

            raise RuntimeError(
                f"airtemp contains "
                f"{missing_airtemp} non-finite values.\n\n"
                "Temperature values are not automatically "
                "filled."
            )


        # ====================================================
        # PRECIPITATION MISSING VALUES
        # ====================================================

        missing_pptrate = (
            count_nonfinite(
                emearth["pptrate"]
            )
        )


        print(
            f"{'pptrate':<10}: "
            f"{missing_pptrate}"
        )


        if missing_pptrate > 0:

            print()
            print(
                "WARNING:"
            )

            print(
                f"{missing_pptrate} non-finite "
                "EM-Earth precipitation values "
                "will be replaced with 0.0."
            )


        # ====================================================
        # CREATE OUTPUT DATASET
        # ====================================================

        ds_out = xr.Dataset()


        # ----------------------------------------------------
        # Coordinates
        # ----------------------------------------------------

        ds_out = ds_out.assign_coords(
            time=era5["time"].values
        )


        if "hru" in era5.coords:

            ds_out = ds_out.assign_coords(
                hru=era5["hru"].values
            )

        else:

            ds_out = ds_out.assign_coords(
                hru=np.arange(
                    era5_hru_count,
                    dtype=np.int64
                )
            )


        # ----------------------------------------------------
        # HRU identifiers
        # ----------------------------------------------------

        ds_out["hruId"] = (
            (
                "hru",
            ),
            era5_hru_ids
        )


        # ----------------------------------------------------
        # HRU latitude / longitude
        # ----------------------------------------------------

        if "latitude" in era5:

            ds_out["latitude"] = (
                (
                    "hru",
                ),
                era5["latitude"].values
            )

        elif "latitude" in emearth:

            ds_out["latitude"] = (
                (
                    "hru",
                ),
                emearth["latitude"].values
            )


        if "longitude" in era5:

            ds_out["longitude"] = (
                (
                    "hru",
                ),
                era5["longitude"].values
            )

        elif "longitude" in emearth:

            ds_out["longitude"] = (
                (
                    "hru",
                ),
                emearth["longitude"].values
            )


        # ====================================================
        # ERA5 VARIABLES
        # ====================================================

        for variable in ERA5_VARIABLES:

            ds_out[variable] = (
                (
                    "time",
                    "hru",
                ),
                era5[
                    variable
                ]
                .values
                .astype(
                    np.float32
                )
            )


        # ====================================================
        # EM-EARTH PRECIPITATION
        # ====================================================

        precipitation = (
            emearth[
                "pptrate"
            ]
            .values
            .astype(
                np.float32
            )
        )


        precipitation = np.where(
            np.isfinite(
                precipitation
            ),
            precipitation,
            0.0
        ).astype(
            np.float32
        )


        ds_out[
            "pptrate"
        ] = (
            (
                "time",
                "hru",
            ),
            precipitation
        )


        # ====================================================
        # EM-EARTH TEMPERATURE
        # ====================================================

        ds_out[
            "airtemp"
        ] = (
            (
                "time",
                "hru",
            ),
            emearth[
                "airtemp"
            ]
            .values
            .astype(
                np.float32
            )
        )


        # ====================================================
        # DATA STEP
        # ====================================================

        ds_out[
            "data_step"
        ] = xr.DataArray(
            np.int32(
                data_step
            )
        )


        ds_out[
            "data_step"
        ].attrs[
            "long_name"
        ] = (
            "data step length in seconds"
        )


        ds_out[
            "data_step"
        ].attrs[
            "units"
        ] = "s"


        # ====================================================
        # VARIABLE ATTRIBUTES
        # ====================================================

        ds_out[
            "hruId"
        ].attrs[
            "long_name"
        ] = "hydrologic response unit ID"


        # ====================================================
        # GLOBAL METADATA
        # ====================================================

        ds_out.attrs[
            "Conventions"
        ] = "CF-1.6"


        ds_out.attrs[
            "History"
        ] = (
            "Combined NWAM forcing prepared for SUMMA "
            f"on {datetime.now():%Y-%m-%d %H:%M:%S}"
        )


        ds_out.attrs[
            "Domain"
        ] = domain


        ds_out.attrs[
            "ERA5_variables"
        ] = (
            "airpres, LWRadAtm, SWRadAtm, "
            "spechum, windspd"
        )


        ds_out.attrs[
            "EM_Earth_variables"
        ] = (
            "pptrate, airtemp"
        )


        ds_out.attrs[
            "forcing_time_step_seconds"
        ] = (
            data_step
        )


        ds_out.attrs[
            "precipitation_missing_value_treatment"
        ] = (
            "Non-finite EM-Earth pptrate values "
            "were replaced with 0.0."
        )


        ds_out.attrs[
            "precipitation_values_filled"
        ] = (
            missing_pptrate
        )


        # ====================================================
        # OUTPUT ENCODING
        # ====================================================

        encoding = {}


        for variable in SUMMA_FORCING_VARIABLES:

            encoding[
                variable
            ] = {
                "dtype": "float32",
                "zlib": True,
                "complevel": 4,
                "_FillValue": -9999.0,
            }


        encoding[
            "hruId"
        ] = {
            "zlib": True,
            "complevel": 4,
        }


        # ====================================================
        # REMOVE STALE OUTPUT
        # ====================================================

        if output_file.exists():

            print()
            print(
                "Existing output found."
            )

            print(
                "It will be replaced after "
                "validation of the source files."
            )

            output_file.unlink()


        # ====================================================
        # WRITE OUTPUT
        # ====================================================

        ds_out.to_netcdf(
            output_file,
            encoding=encoding
        )


        ds_out.close()


    # ========================================================
    # VERIFY WRITTEN OUTPUT
    # ========================================================

    if not output_file.exists():

        raise RuntimeError(
            "Combined SUMMA forcing file "
            "was not created."
        )


    with xr.open_dataset(
        output_file
    ) as check:


        if check.sizes.get(
            "hru",
            0
        ) != era5_hru_count:

            raise RuntimeError(
                "Output HRU count is incorrect."
            )


        if check.sizes.get(
            "time",
            0
        ) != era5_time_count:

            raise RuntimeError(
                "Output timestep count is incorrect."
            )


        if not np.array_equal(
            check[
                "hruId"
            ].values,
            era5_hru_ids
        ):

            raise RuntimeError(
                "Output HRU IDs/order changed."
            )


        missing_output = {}


        for variable in SUMMA_FORCING_VARIABLES:

            if variable not in check:

                raise RuntimeError(
                    f"{variable} missing from "
                    "combined SUMMA forcing."
                )


            missing_output[
                variable
            ] = count_nonfinite(
                check[
                    variable
                ]
            )


        if any(
            value > 0
            for value in missing_output.values()
        ):

            raise RuntimeError(
                "Combined SUMMA forcing still "
                "contains non-finite values:\n"
                + "\n".join(
                    f"{key}: {value}"
                    for key, value
                    in missing_output.items()
                )
            )


        output_hru_count = (
            check.sizes["hru"]
        )

        output_time_count = (
            check.sizes["time"]
        )


    # ========================================================
    # WORKFLOW LOG
    # ========================================================

    log_dir = (
        output_dir
        / "_workflow_log"
    )


    log_dir.mkdir(
        parents=True,
        exist_ok=True
    )


    now = datetime.now()


    log_file = (
        log_dir
        / (
            f"{now:%Y%m%d_%H%M%S}_"
            f"combine_forcing_{ym}.txt"
        )
    )


    with open(
        log_file,
        "w"
    ) as file:

        file.write(
            f"Combined forcing completed "
            f"{now:%Y-%m-%d %H:%M:%S}\n"
        )

        file.write(
            f"Domain: {domain}\n"
        )

        file.write(
            f"Control file: {CONTROL_FILE}\n"
        )

        file.write(
            f"Month: {ym}\n"
        )

        file.write(
            f"ERA5: {era5_file}\n"
        )

        file.write(
            f"EM-Earth: {emearth_file}\n"
        )

        file.write(
            f"Output: {output_file}\n"
        )

        file.write(
            f"HRUs: {output_hru_count}\n"
        )

        file.write(
            f"Time steps: {output_time_count}\n"
        )

        file.write(
            f"data_step: {data_step} s\n"
        )

        file.write(
            f"Missing precipitation values "
            f"replaced with zero: "
            f"{missing_pptrate}\n"
        )

        file.write(
            "Shared control_active.txt used: no\n"
        )


    # ========================================================
    # FINAL REPORT
    # ========================================================

    print()
    print("=" * 70)
    print("SUMMA FORCING COMBINATION COMPLETED")
    print("=" * 70)

    print(
        f"Domain       : {domain}"
    )

    print(
        f"Control file : {CONTROL_FILE}"
    )

    print(
        f"Month        : {ym}"
    )

    print(
        f"HRUs         : {output_hru_count}"
    )

    print(
        f"Time steps   : {output_time_count}"
    )

    print(
        f"data_step    : {data_step} s"
    )

    print(
        f"Filled precip: {missing_pptrate}"
    )

    print(
        f"Output       : {output_file}"
    )

    print(
        f"Workflow log : {log_file}"
    )

    print()
    print(
        "All seven SUMMA forcing variables "
        "contain finite values."
    )


# ============================================================
# COMMAND-LINE MODE
# ============================================================

if len(sys.argv) == 4:

    try:

        year = int(
            sys.argv[2]
        )

        month = int(
            sys.argv[3]
        )

    except ValueError as exc:

        raise SystemExit(
            "YEAR and MONTH must be integers."
        ) from exc


    if (
        year < start_year
        or year > end_year
    ):

        raise ValueError(
            f"Year {year} is outside "
            f"forcing_raw_time "
            f"{start_year},{end_year}"
        )


    if (
        month < 1
        or month > 12
    ):

        raise ValueError(
            "Month must be between 1 and 12."
        )


    combine_month(
        year,
        month
    )


# ============================================================
# SERIAL MODE
# ============================================================

elif len(sys.argv) == 2:

    print()
    print("=" * 70)
    print("SUMMA FORCING SERIAL COMBINATION")
    print("=" * 70)

    print(
        f"Domain       : {domain}"
    )

    print(
        f"Control file : {CONTROL_FILE}"
    )

    print(
        f"Forcing range: "
        f"{start_year} - {end_year}"
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


print()
print(
    "No control_active.txt was created or modified."
)