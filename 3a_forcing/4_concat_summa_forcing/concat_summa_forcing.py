#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Concatenate monthly distributed SUMMA forcing files for one basin.

Paths are obtained from the domain-specific CWARHM control file.

IMPORTANT
---------
This script does NOT generate or shift timestamps.

The decoded timestamps stored in every monthly NetCDF file are retained
exactly. Because individual monthly NetCDF files may use different numeric
time origins, their decoded timestamps are re-encoded using the time units
and calendar of the first monthly file.

Therefore:

    physical timestamp before concatenation
    ==
    physical timestamp after concatenation

No UTC-to-LST conversion is performed here.

Example
-------
python concat_summa_forcing.py \
    --control-file ../../0_control_files/control_CAN_05BB001.txt \
    --start-year 1950 \
    --start-month 1 \
    --end-year 2019 \
    --end-month 12
"""

from pathlib import Path
from datetime import datetime
import argparse

import numpy as np
from netCDF4 import Dataset, num2date, date2num


# ============================================================
# REQUIRED SUMMA FORCING VARIABLES
# ============================================================

REQUIRED_VARS = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "pptrate",
    "airtemp",
    "spechum",
    "windspd",
]


# ============================================================
# CONTROL FILE
# ============================================================

def read_from_control(file, setting):
    """
    Read one setting using exact control-key matching.
    """

    with file.open() as contents:

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
                1,
            )

            if left.strip() != setting:
                continue

            value = (
                right
                .split("#", 1)[0]
                .strip()
            )

            if not value:

                raise RuntimeError(
                    f"Setting '{setting}' is empty in:\n"
                    f"{file}"
                )

            return value

    raise RuntimeError(
        f"Setting '{setting}' not found in:\n"
        f"{file}"
    )


def resolve_forcing_summa_path(control_file):
    """
    Resolve forcing_summa_path from the control file.

    If forcing_summa_path is 'default', use:

        root_path/domain_<DOMAIN>/forcing/4_SUMMA_input
    """

    domain = read_from_control(
        control_file,
        "domain_name",
    )

    root_path = Path(
        read_from_control(
            control_file,
            "root_path",
        )
    ).expanduser()

    forcing_summa_path = read_from_control(
        control_file,
        "forcing_summa_path",
    )

    if forcing_summa_path == "default":

        input_dir = (
            root_path
            / f"domain_{domain}"
            / "forcing"
            / "4_SUMMA_input"
        )

    else:

        input_dir = Path(
            forcing_summa_path
        ).expanduser()

    input_dir = input_dir.resolve()

    output_dir = (
        input_dir.parent
        / "5_SUMMA_input_concat"
    )

    return (
        domain,
        root_path.resolve(),
        input_dir,
        output_dir,
    )


# ============================================================
# FUNCTIONS
# ============================================================

def monthly_dates(
    start_year,
    start_month,
    end_year,
    end_month,
):

    dates = []

    year = start_year
    month = start_month

    while (year, month) <= (end_year, end_month):

        dates.append(
            (
                year,
                month,
            )
        )

        month += 1

        if month == 13:

            month = 1
            year += 1

    return dates


def copy_variable_attributes(
    src_var,
    dst_var,
):

    for attr in src_var.ncattrs():

        if attr == "_FillValue":
            continue

        dst_var.setncattr(
            attr,
            src_var.getncattr(attr),
        )


def decode_time_variable(
    time_var,
):

    if "units" not in time_var.ncattrs():

        raise RuntimeError(
            "time variable has no units attribute."
        )

    units = time_var.getncattr(
        "units"
    )

    calendar = getattr(
        time_var,
        "calendar",
        "standard",
    )

    dates = num2date(
        time_var[:],
        units=units,
        calendar=calendar,
        only_use_cftime_datetimes=True,
    )

    return (
        np.asarray(
            dates,
            dtype=object,
        ),
        units,
        calendar,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Concatenate monthly distributed "
            "SUMMA forcing files for one basin."
        )
    )

    parser.add_argument(
        "--control-file",
        required=True,
        type=Path,
        help=(
            "Domain-specific distributed CWARHM "
            "control file."
        ),
    )

    parser.add_argument(
        "--start-year",
        required=True,
        type=int,
    )

    parser.add_argument(
        "--start-month",
        required=True,
        type=int,
    )

    parser.add_argument(
        "--end-year",
        required=True,
        type=int,
    )

    parser.add_argument(
        "--end-month",
        required=True,
        type=int,
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Overwrite existing concatenated file."
        ),
    )

    args = parser.parse_args()

    control_file = (
        args.control_file
        .expanduser()
        .resolve()
    )

    if not control_file.is_file():

        raise FileNotFoundError(
            f"Control file not found:\n"
            f"{control_file}"
        )

    (
        domain,
        root_path,
        input_dir,
        output_dir,
    ) = resolve_forcing_summa_path(
        control_file
    )

    start_year = args.start_year
    start_month = args.start_month

    end_year = args.end_year
    end_month = args.end_month


    # ========================================================
    # VALIDATE PERIOD
    # ========================================================

    if not 1 <= start_month <= 12:

        raise ValueError(
            "start-month must be 1-12."
        )

    if not 1 <= end_month <= 12:

        raise ValueError(
            "end-month must be 1-12."
        )

    if (
        start_year,
        start_month,
    ) > (
        end_year,
        end_month,
    ):

        raise ValueError(
            "Start date occurs after end date."
        )


    # ========================================================
    # PATHS
    # ========================================================

    period_start = (
        f"{start_year:04d}"
        f"{start_month:02d}"
    )

    period_end = (
        f"{end_year:04d}"
        f"{end_month:02d}"
    )

    output_filename = (
        "NWAM_SUMMA_forcing_"
        f"{period_start}_{period_end}.nc"
    )

    output_file = (
        output_dir
        / output_filename
    )


    # ========================================================
    # REPORT
    # ========================================================

    print()
    print("=" * 80)
    print("CONCATENATE DISTRIBUTED SUMMA FORCING")
    print("=" * 80)

    print(
        f"CONTROL FILE : {control_file}"
    )

    print(
        f"DOMAIN       : {domain}"
    )

    print(
        f"ROOT PATH    : {root_path}"
    )

    print(
        f"INPUT        : {input_dir}"
    )

    print(
        f"OUTPUT       : {output_file}"
    )

    print(
        f"PERIOD       : "
        f"{start_year:04d}-{start_month:02d} "
        f"through "
        f"{end_year:04d}-{end_month:02d}"
    )

    print(
        "TIME HANDLING: retain monthly UTC timestamps"
    )

    print(
        "UTC -> LST   : NOT performed"
    )

    print("=" * 80)


    # ========================================================
    # DIRECTORY CHECKS
    # ========================================================

    if not input_dir.is_dir():

        raise FileNotFoundError(
            f"Missing SUMMA forcing directory:\n"
            f"{input_dir}"
        )


    # ========================================================
    # MONTH LIST
    # ========================================================

    dates = monthly_dates(
        start_year,
        start_month,
        end_year,
        end_month,
    )

    expected_months = len(
        dates
    )

    print(
        f"Expected monthly files: "
        f"{expected_months}"
    )

    input_files = [

        input_dir
        / (
            "NWAM_SUMMA_forcing_"
            f"{year:04d}{month:02d}.nc"
        )

        for year, month in dates
    ]


    # ========================================================
    # CHECK ALL MONTHLY FILES EXIST
    # ========================================================

    missing_files = [

        file
        for file in input_files
        if not file.is_file()
    ]

    if missing_files:

        raise FileNotFoundError(
            f"{len(missing_files)} required monthly "
            "SUMMA forcing files are missing:\n"
            + "\n".join(
                str(file)
                for file in missing_files
            )
        )

    print(
        f"Monthly files found: "
        f"{len(input_files)}"
    )


    # ========================================================
    # FIRST FILE DEFINES STRUCTURE AND TIME ENCODING
    # ========================================================

    first_file = input_files[0]

    with Dataset(
        first_file,
        "r",
    ) as src0:

        if "time" not in src0.variables:

            raise RuntimeError(
                "First monthly file has no time variable."
            )

        if "time" not in src0.dimensions:

            raise RuntimeError(
                "First monthly file has no time dimension."
            )

        if "hru" not in src0.dimensions:

            raise RuntimeError(
                "First monthly file has no hru dimension."
            )

        num_hru = len(
            src0.dimensions[
                "hru"
            ]
        )

        if num_hru <= 0:

            raise RuntimeError(
                "First monthly file contains no HRUs."
            )

        output_time_units = (
            src0.variables[
                "time"
            ].getncattr(
                "units"
            )
        )

        output_calendar = getattr(
            src0.variables[
                "time"
            ],
            "calendar",
            "standard",
        )

        reference_variables = set(
            src0.variables.keys()
        )

        reference_hru_ids = None

        if "hruId" in src0.variables:

            reference_hru_ids = np.asarray(
                src0.variables[
                    "hruId"
                ][:]
            ).reshape(-1)

    print(
        f"HRUs              : {num_hru}"
    )

    print(
        f"Output time units : {output_time_units}"
    )

    print(
        f"Output calendar   : {output_calendar}"
    )


    # ========================================================
    # SCAN ALL MONTHS
    # ========================================================

    monthly_lengths = []

    total_time = 0

    previous_last_time = None

    first_actual_time = None
    last_actual_time = None

    for file in input_files:

        with Dataset(
            file,
            "r",
        ) as src:

            if "time" not in src.dimensions:

                raise RuntimeError(
                    f"time dimension missing:\n"
                    f"{file}"
                )

            if "hru" not in src.dimensions:

                raise RuntimeError(
                    f"hru dimension missing:\n"
                    f"{file}"
                )

            current_num_hru = len(
                src.dimensions[
                    "hru"
                ]
            )

            if current_num_hru != num_hru:

                raise RuntimeError(
                    "HRU count changed between "
                    "monthly files.\n"
                    f"Reference: {num_hru}\n"
                    f"Current  : {current_num_hru}\n"
                    f"File     : {file}"
                )

            missing_required = [
                variable
                for variable in REQUIRED_VARS
                if variable not in src.variables
            ]

            if missing_required:

                raise RuntimeError(
                    "Required SUMMA forcing "
                    "variables missing from:\n"
                    f"{file}\n"
                    f"{missing_required}"
                )

            current_variables = set(
                src.variables.keys()
            )

            if current_variables != reference_variables:

                missing = sorted(
                    reference_variables
                    - current_variables
                )

                extra = sorted(
                    current_variables
                    - reference_variables
                )

                raise RuntimeError(
                    "NetCDF variable structure "
                    "changes between months.\n"
                    f"File: {file}\n"
                    f"Missing variables: {missing}\n"
                    f"Extra variables  : {extra}"
                )

            if reference_hru_ids is not None:

                if "hruId" not in src.variables:

                    raise RuntimeError(
                        f"hruId missing from:\n"
                        f"{file}"
                    )

                current_hru_ids = np.asarray(
                    src.variables[
                        "hruId"
                    ][:]
                ).reshape(-1)

                if not np.array_equal(
                    reference_hru_ids,
                    current_hru_ids,
                ):

                    raise RuntimeError(
                        "hruId values/order changed "
                        "between monthly files:\n"
                        f"{file}"
                    )

            (
                current_dates,
                _,
                _,
            ) = decode_time_variable(
                src.variables[
                    "time"
                ]
            )

            nt = len(
                current_dates
            )

            if nt <= 0:

                raise RuntimeError(
                    f"No timesteps found:\n"
                    f"{file}"
                )

            monthly_lengths.append(
                nt
            )

            total_time += nt

            if nt > 1:

                for i in range(
                    nt - 1
                ):

                    delta_seconds = (
                        current_dates[i + 1]
                        - current_dates[i]
                    ).total_seconds()

                    if delta_seconds != 3600:

                        raise RuntimeError(
                            "Non-hourly timestamp spacing "
                            f"in:\n{file}\n"
                            f"At index {i}: "
                            f"{current_dates[i]} -> "
                            f"{current_dates[i + 1]}"
                        )

            if previous_last_time is not None:

                delta_seconds = (
                    current_dates[0]
                    - previous_last_time
                ).total_seconds()

                if delta_seconds != 3600:

                    raise RuntimeError(
                        "Timestamp discontinuity between "
                        "monthly NetCDF files.\n"
                        f"Previous last : "
                        f"{previous_last_time}\n"
                        f"Current first : "
                        f"{current_dates[0]}\n"
                        f"File          : "
                        f"{file}"
                    )

            if first_actual_time is None:

                first_actual_time = (
                    current_dates[0]
                )

            previous_last_time = (
                current_dates[-1]
            )

            last_actual_time = (
                current_dates[-1]
            )

            print(
                f"{file.name}: "
                f"{nt} timesteps | "
                f"{current_dates[0]} -> "
                f"{current_dates[-1]}"
            )

    print()

    print(
        f"Total hourly timesteps: "
        f"{total_time}"
    )

    print(
        f"First timestamp       : "
        f"{first_actual_time}"
    )

    print(
        f"Last timestamp        : "
        f"{last_actual_time}"
    )


    # ========================================================
    # OUTPUT
    # ========================================================

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output_file.exists():

        if not args.overwrite:

            print(
                f"Output already exists:\n"
                f"{output_file}"
            )

            print(
                "Use --overwrite to recreate it."
            )

            return

        output_file.unlink()


    # ========================================================
    # CREATE CONCATENATED FILE
    # ========================================================

    with Dataset(
        first_file,
        "r",
    ) as src0:

        with Dataset(
            output_file,
            "w",
            format=src0.data_model,
        ) as dst:

            for dim_name, dim in (
                src0.dimensions.items()
            ):

                if dim_name == "time":

                    dst.createDimension(
                        "time",
                        total_time,
                    )

                else:

                    dst.createDimension(
                        dim_name,
                        len(dim),
                    )

            for attr in src0.ncattrs():

                if attr == "History":
                    continue

                dst.setncattr(
                    attr,
                    src0.getncattr(
                        attr
                    ),
                )

            dst.setncattr(
                "History",
                (
                    "Concatenated distributed "
                    "NWAM SUMMA forcing for "
                    f"{domain}; "
                    f"{first_actual_time} through "
                    f"{last_actual_time}; "
                    "original monthly UTC timestamps "
                    "retained without timezone shift; "
                    f"created "
                    f"{datetime.now():%Y-%m-%d %H:%M:%S}"
                ),
            )

            dst.setncattr(
                "time_processing",
                (
                    "Monthly timestamps decoded from "
                    "their original NetCDF units and "
                    "re-encoded using the first monthly "
                    "file's time reference. "
                    "No UTC-to-LST shift applied."
                ),
            )

            dst.setncattr(
                "CWARHM_control_file",
                control_file.name,
            )

            for var_name, src_var in (
                src0.variables.items()
            ):

                fill_value = None

                if "_FillValue" in (
                    src_var.ncattrs()
                ):

                    fill_value = (
                        src_var.getncattr(
                            "_FillValue"
                        )
                    )

                if fill_value is not None:

                    dst_var = (
                        dst.createVariable(
                            var_name,
                            src_var.datatype,
                            src_var.dimensions,
                            fill_value=fill_value,
                        )
                    )

                else:

                    dst_var = (
                        dst.createVariable(
                            var_name,
                            src_var.datatype,
                            src_var.dimensions,
                        )
                    )

                copy_variable_attributes(
                    src_var,
                    dst_var,
                )

            for var_name, src_var in (
                src0.variables.items()
            ):

                if "time" not in (
                    src_var.dimensions
                ):

                    dst.variables[
                        var_name
                    ][:] = src_var[:]

            out_start = 0

            for file, nt in zip(
                input_files,
                monthly_lengths,
            ):

                out_end = (
                    out_start
                    + nt
                )

                print(
                    f"{file.name}: "
                    f"{out_start} -> "
                    f"{out_end - 1}"
                )

                with Dataset(
                    file,
                    "r",
                ) as src:

                    (
                        current_dates,
                        _,
                        _,
                    ) = decode_time_variable(
                        src.variables[
                            "time"
                        ]
                    )

                    converted_time = date2num(
                        current_dates.tolist(),
                        units=output_time_units,
                        calendar=output_calendar,
                    )

                    dst.variables[
                        "time"
                    ][
                        out_start:out_end
                    ] = converted_time

                    for (
                        var_name,
                        src_var,
                    ) in src.variables.items():

                        if var_name == "time":
                            continue

                        if "time" not in (
                            src_var.dimensions
                        ):
                            continue

                        time_axis = (
                            src_var.dimensions.index(
                                "time"
                            )
                        )

                        src_slice = (
                            [slice(None)]
                            * src_var.ndim
                        )

                        dst_slice = (
                            [slice(None)]
                            * src_var.ndim
                        )

                        src_slice[
                            time_axis
                        ] = slice(
                            0,
                            nt,
                        )

                        dst_slice[
                            time_axis
                        ] = slice(
                            out_start,
                            out_end,
                        )

                        dst.variables[
                            var_name
                        ][
                            tuple(
                                dst_slice
                            )
                        ] = src_var[
                            tuple(
                                src_slice
                            )
                        ]

                out_start = out_end

            dst.variables[
                "time"
            ].setncattr(
                "units",
                output_time_units,
            )

            dst.variables[
                "time"
            ].setncattr(
                "calendar",
                output_calendar,
            )

            if (
                "long_name"
                not in dst.variables[
                    "time"
                ].ncattrs()
            ):

                dst.variables[
                    "time"
                ].setncattr(
                    "long_name",
                    "time",
                )

            if (
                "standard_name"
                not in dst.variables[
                    "time"
                ].ncattrs()
            ):

                dst.variables[
                    "time"
                ].setncattr(
                    "standard_name",
                    "time",
                )

            if (
                "axis"
                not in dst.variables[
                    "time"
                ].ncattrs()
            ):

                dst.variables[
                    "time"
                ].setncattr(
                    "axis",
                    "T",
                )


    # ========================================================
    # FINAL VERIFICATION
    # ========================================================

    with Dataset(
        output_file,
        "r",
    ) as ds:

        if len(
            ds.dimensions[
                "time"
            ]
        ) != total_time:

            raise RuntimeError(
                "Final time dimension "
                "is incorrect."
            )

        if len(
            ds.dimensions[
                "hru"
            ]
        ) != num_hru:

            raise RuntimeError(
                "Final HRU dimension "
                "is incorrect."
            )

        missing_vars = [
            var
            for var in REQUIRED_VARS
            if var not in ds.variables
        ]

        if missing_vars:

            raise RuntimeError(
                "Missing required forcing "
                "variables:\n"
                + "\n".join(
                    missing_vars
                )
            )

        if (
            reference_hru_ids
            is not None
        ):

            output_hru_ids = np.asarray(
                ds.variables[
                    "hruId"
                ][:]
            ).reshape(-1)

            if not np.array_equal(
                output_hru_ids,
                reference_hru_ids,
            ):

                raise RuntimeError(
                    "Final hruId values/order "
                    "do not match monthly files."
                )

        output_dates, _, _ = (
            decode_time_variable(
                ds.variables[
                    "time"
                ]
            )
        )

        if (
            output_dates[0]
            != first_actual_time
        ):

            raise RuntimeError(
                "First output timestamp changed."
            )

        if (
            output_dates[-1]
            != last_actual_time
        ):

            raise RuntimeError(
                "Last output timestamp changed."
            )

        if len(
            output_dates
        ) > 1:

            for i in range(
                len(output_dates) - 1
            ):

                delta_seconds = (
                    output_dates[i + 1]
                    - output_dates[i]
                ).total_seconds()

                if delta_seconds != 3600:

                    raise RuntimeError(
                        "Final concatenated "
                        "time coordinate is not "
                        "continuous hourly."
                    )


    # ========================================================
    # FINISH
    # ========================================================

    print()
    print("=" * 80)
    print("PASS: DISTRIBUTED SUMMA FORCING CONCATENATION")
    print("=" * 80)

    print(
        f"Domain          : {domain}"
    )

    print(
        f"Monthly files   : {len(input_files)}"
    )

    print(
        f"Hourly steps    : {total_time}"
    )

    print(
        f"HRUs            : {num_hru}"
    )

    print(
        f"First timestamp : {first_actual_time}"
    )

    print(
        f"Last timestamp  : {last_actual_time}"
    )

    print(
        f"Time reference  : {output_time_units}"
    )

    print(
        "Timezone shift  : none"
    )

    print(
        f"Output          : {output_file}"
    )

    print("=" * 80)


if __name__ == "__main__":

    main()