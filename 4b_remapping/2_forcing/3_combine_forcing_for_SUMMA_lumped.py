#!/usr/bin/env python3
# coding: utf-8

"""
Combine lumped ERA5 and EM-Earth forcing into monthly SUMMA forcing.

ERA5 supplies:
    airpres
    LWRadAtm
    SWRadAtm
    spechum
    windspd

EM-Earth supplies:
    pptrate
    airtemp

The output is written under:

    domain_<DOMAIN>/lumped/forcing/4_SUMMA_input/

Usage
-----
One month:

python 3_combine_forcing_for_SUMMA_lumped.py \
    /path/to/control_DOMAIN_lumped.txt \
    YEAR MONTH

Complete period serially:

python 3_combine_forcing_for_SUMMA_lumped.py \
    /path/to/control_DOMAIN_lumped.txt
"""

import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import xarray as xr


# ============================================================
# ARGUMENTS
# ============================================================

if len(sys.argv) not in (2, 4):

    raise SystemExit(
        "Usage:\n\n"
        "Complete forcing period:\n"
        "  python 3_combine_forcing_for_SUMMA_lumped.py "
        "/path/to/control_DOMAIN_lumped.txt\n\n"
        "One month:\n"
        "  python 3_combine_forcing_for_SUMMA_lumped.py "
        "/path/to/control_DOMAIN_lumped.txt YEAR MONTH"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).resolve()


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
                not stripped
                or stripped.startswith("#")
                or "|" not in stripped
            ):
                continue

            left, right = stripped.split("|", 1)

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


# ============================================================
# DOMAIN SETTINGS
# ============================================================

root_path = Path(
    read_from_control(
        CONTROL_FILE,
        "root_path"
    )
)


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
        "START_YEAR,END_YEAR"
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
# LUMPED PATHS
# ============================================================

lumped_root = (
    root_path
    / f"domain_{domain}"
    / "lumped"
)


era5_dir = (
    lumped_root
    / "forcing"
    / "3_basin_averaged_data"
    / "ERA5"
)


emearth_dir = (
    lumped_root
    / "forcing"
    / "3_basin_averaged_data"
    / "EM_Earth"
)


output_dir = (
    lumped_root
    / "forcing"
    / "4_SUMMA_input"
)


if not era5_dir.exists():

    raise FileNotFoundError(
        "Lumped ERA5 forcing directory not found:\n"
        f"{era5_dir}"
    )


if not emearth_dir.exists():

    raise FileNotFoundError(
        "Lumped EM-Earth forcing directory not found:\n"
        f"{emearth_dir}"
    )


output_dir.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# VARIABLES
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
# FILE NAMES
# ============================================================

era5_case = (
    f"{domain}_lumped_ERA5"
)


emearth_case = (
    f"{domain}_lumped_EM_Earth"
)


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
        output_file,
    )


# ============================================================
# VALIDATION
# ============================================================

def validate_source_dataset(
    dataset,
    filename,
    variables,
):

    if "time" not in dataset:

        raise RuntimeError(
            f"time is missing from:\n{filename}"
        )

    if "hruId" not in dataset:

        raise RuntimeError(
            f"hruId is missing from:\n{filename}"
        )

    if "hru" not in dataset.dims:

        raise RuntimeError(
            f"hru dimension is missing from:\n{filename}"
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
    print("COMBINE LUMPED ERA5 + EM-EARTH FOR SUMMA")
    print("=" * 70)

    print(f"Domain       : {domain}")
    print(f"Control file : {CONTROL_FILE}")
    print(f"Month        : {ym}")


    if not era5_file.exists():

        raise FileNotFoundError(
            "Lumped ERA5 forcing not found:\n"
            f"{era5_file}"
        )


    if not emearth_file.exists():

        raise FileNotFoundError(
            "Lumped EM-Earth forcing not found:\n"
            f"{emearth_file}"
        )


    print()
    print(f"ERA5 input    : {era5_file}")
    print(f"EM-Earth input: {emearth_file}")
    print(f"Output        : {output_file}")


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


        era5_hru_count = era5.sizes["hru"]
        emearth_hru_count = emearth.sizes["hru"]


        if era5_hru_count != 1:

            raise RuntimeError(
                "Lumped ERA5 forcing must contain "
                "exactly 1 HRU.\n"
                f"Found: {era5_hru_count}"
            )


        if emearth_hru_count != 1:

            raise RuntimeError(
                "Lumped EM-Earth forcing must contain "
                "exactly 1 HRU.\n"
                f"Found: {emearth_hru_count}"
            )


        era5_time_count = era5.sizes["time"]
        emearth_time_count = emearth.sizes["time"]


        if era5_time_count != emearth_time_count:

            raise RuntimeError(
                "ERA5 and EM-Earth timestep counts differ.\n"
                f"ERA5     : {era5_time_count}\n"
                f"EM-Earth : {emearth_time_count}"
            )


        if not np.array_equal(
            era5["time"].values,
            emearth["time"].values
        ):

            raise RuntimeError(
                "ERA5 and EM-Earth time coordinates "
                f"do not match for {ym}."
            )


        era5_hru_ids = (
            np.asarray(
                era5["hruId"].values
            )
            .reshape(-1)
        )


        emearth_hru_ids = (
            np.asarray(
                emearth["hruId"].values
            )
            .reshape(-1)
        )


        if not np.array_equal(
            era5_hru_ids,
            emearth_hru_ids
        ):

            raise RuntimeError(
                "ERA5 and EM-Earth hruId values differ."
            )


        if int(era5_hru_ids[0]) != 1:

            raise RuntimeError(
                "Lumped hruId must be 1.\n"
                f"Found: {era5_hru_ids.tolist()}"
            )


        print()
        print("HRUs       : 1")
        print("hruId      : 1")
        print(f"Time steps : {era5_time_count}")


        # ----------------------------------------------------
        # ERA5 missing values
        # ----------------------------------------------------

        for variable in ERA5_VARIABLES:

            missing = count_nonfinite(
                era5[variable]
            )

            if missing > 0:

                raise RuntimeError(
                    f"{variable} contains "
                    f"{missing} non-finite ERA5 values."
                )


        # ----------------------------------------------------
        # EM-Earth air temperature
        # ----------------------------------------------------

        missing_airtemp = count_nonfinite(
            emearth["airtemp"]
        )


        if missing_airtemp > 0:

            raise RuntimeError(
                "airtemp contains "
                f"{missing_airtemp} non-finite values."
            )


        # ----------------------------------------------------
        # EM-Earth precipitation
        # ----------------------------------------------------

        missing_pptrate = count_nonfinite(
            emearth["pptrate"]
        )


        if missing_pptrate > 0:

            print()
            print(
                f"WARNING: {missing_pptrate} non-finite "
                "pptrate values will be replaced with 0."
            )


        # ----------------------------------------------------
        # OUTPUT DATASET
        # ----------------------------------------------------

        ds_out = xr.Dataset()


        ds_out = ds_out.assign_coords(
            time=era5["time"].values
        )


        if "hru" in era5.coords:

            ds_out = ds_out.assign_coords(
                hru=era5["hru"].values
            )

        else:

            ds_out = ds_out.assign_coords(
                hru=np.array(
                    [0],
                    dtype=np.int64
                )
            )


        ds_out["hruId"] = (
            ("hru",),
            era5_hru_ids
        )


        if "latitude" in era5:

            ds_out["latitude"] = (
                ("hru",),
                era5["latitude"].values
            )

        elif "latitude" in emearth:

            ds_out["latitude"] = (
                ("hru",),
                emearth["latitude"].values
            )


        if "longitude" in era5:

            ds_out["longitude"] = (
                ("hru",),
                era5["longitude"].values
            )

        elif "longitude" in emearth:

            ds_out["longitude"] = (
                ("hru",),
                emearth["longitude"].values
            )


        for variable in ERA5_VARIABLES:

            ds_out[variable] = (
                ("time", "hru"),
                era5[
                    variable
                ].values.astype(
                    np.float32
                )
            )


        precipitation = (
            emearth[
                "pptrate"
            ]
            .values
            .astype(np.float32)
        )


        precipitation = np.where(
            np.isfinite(
                precipitation
            ),
            precipitation,
            0.0
        ).astype(np.float32)


        ds_out["pptrate"] = (
            ("time", "hru"),
            precipitation
        )


        ds_out["airtemp"] = (
            ("time", "hru"),
            emearth[
                "airtemp"
            ].values.astype(
                np.float32
            )
        )


        ds_out["data_step"] = xr.DataArray(
            np.int32(
                data_step
            )
        )


        ds_out["data_step"].attrs[
            "long_name"
        ] = "data step length in seconds"

        ds_out["data_step"].attrs[
            "units"
        ] = "s"


        ds_out["hruId"].attrs[
            "long_name"
        ] = "hydrologic response unit ID"


        ds_out.attrs[
            "Conventions"
        ] = "CF-1.6"


        ds_out.attrs[
            "History"
        ] = (
            "Combined lumped NWAM forcing prepared "
            f"for SUMMA on "
            f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        )


        ds_out.attrs["Domain"] = domain
        ds_out.attrs["Spatial_configuration"] = "lumped"
        ds_out.attrs["Number_of_HRUs"] = 1


        ds_out.attrs[
            "ERA5_variables"
        ] = (
            "airpres, LWRadAtm, SWRadAtm, "
            "spechum, windspd"
        )


        ds_out.attrs[
            "EM_Earth_variables"
        ] = "pptrate, airtemp"


        ds_out.attrs[
            "forcing_time_step_seconds"
        ] = data_step


        ds_out.attrs[
            "precipitation_values_filled"
        ] = missing_pptrate


        encoding = {}


        for variable in SUMMA_FORCING_VARIABLES:

            encoding[variable] = {
                "dtype": "float32",
                "zlib": True,
                "complevel": 4,
                "_FillValue": -9999.0,
            }


        encoding["hruId"] = {
            "zlib": True,
            "complevel": 4,
        }


        if output_file.exists():

            output_file.unlink()


        ds_out.to_netcdf(
            output_file,
            encoding=encoding
        )


        ds_out.close()


    # ========================================================
    # VERIFY WRITTEN FILE
    # ========================================================

    with xr.open_dataset(
        output_file
    ) as check:


        if check.sizes.get("hru") != 1:

            raise RuntimeError(
                "Combined lumped forcing does not "
                "contain exactly 1 HRU."
            )


        if check.sizes.get(
            "time"
        ) != era5_time_count:

            raise RuntimeError(
                "Combined forcing timestep count is incorrect."
            )


        output_hru_ids = (
            np.asarray(
                check["hruId"].values
            )
            .reshape(-1)
        )


        if (
            output_hru_ids.size != 1
            or int(output_hru_ids[0]) != 1
        ):

            raise RuntimeError(
                "Combined lumped forcing hruId is not 1."
            )


        for variable in SUMMA_FORCING_VARIABLES:

            if variable not in check:

                raise RuntimeError(
                    f"{variable} missing from "
                    "combined SUMMA forcing."
                )


            missing = count_nonfinite(
                check[variable]
            )


            if missing > 0:

                raise RuntimeError(
                    f"{variable} still contains "
                    f"{missing} non-finite values."
                )


        output_time_count = (
            check.sizes["time"]
        )


    # ========================================================
    # LOG
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
            f"combine_lumped_forcing_{ym}.txt"
        )
    )


    with open(
        log_file,
        "w"
    ) as file:

        file.write(
            f"Lumped forcing combination completed "
            f"{now:%Y-%m-%d %H:%M:%S}\n"
        )

        file.write(f"Domain: {domain}\n")
        file.write(f"Control file: {CONTROL_FILE}\n")
        file.write(f"Month: {ym}\n")
        file.write(f"ERA5: {era5_file}\n")
        file.write(f"EM-Earth: {emearth_file}\n")
        file.write(f"Output: {output_file}\n")
        file.write("HRUs: 1\n")
        file.write("hruId: 1\n")
        file.write(f"Time steps: {output_time_count}\n")
        file.write(f"data_step: {data_step} s\n")

        file.write(
            "Missing precipitation values "
            f"replaced with zero: "
            f"{missing_pptrate}\n"
        )

        file.write(
            "Shared control_active.txt used: no\n"
        )


    print()
    print("=" * 70)
    print("LUMPED SUMMA FORCING COMBINATION COMPLETED")
    print("=" * 70)

    print(f"Domain       : {domain}")
    print(f"Month        : {ym}")
    print("HRUs         : 1")
    print("hruId        : 1")
    print(f"Time steps   : {output_time_count}")
    print(f"data_step    : {data_step} s")
    print(f"Output       : {output_file}")
    print(f"Workflow log : {log_file}")

    print()
    print(
        f"PASS: {domain} {ym}"
    )


# ============================================================
# ONE MONTH
# ============================================================

if len(sys.argv) == 4:

    year = int(
        sys.argv[2]
    )

    month = int(
        sys.argv[3]
    )


    if not (
        start_year <= year <= end_year
    ):

        raise ValueError(
            f"Year {year} is outside "
            f"{start_year}-{end_year}"
        )


    if not (
        1 <= month <= 12
    ):

        raise ValueError(
            "Month must be between 1 and 12."
        )


    combine_month(
        year,
        month
    )


# ============================================================
# COMPLETE PERIOD
# ============================================================

else:

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