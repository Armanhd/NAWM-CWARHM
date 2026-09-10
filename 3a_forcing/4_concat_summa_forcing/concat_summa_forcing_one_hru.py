#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Concatenate monthly lumped one-HRU SUMMA forcing.

The input and output directories are determined from the lumped
CWARHM control file.

No workflow data root is hard-coded.
"""

from pathlib import Path
from datetime import datetime
import argparse
import re

import numpy as np
from netCDF4 import Dataset, num2date, date2num


# ============================================================
# TIME SETTINGS
# ============================================================

OUTPUT_TIME_UNITS = (
    "hours since 1950-01-01 00:00:00"
)

OUTPUT_TIME_CALENDAR = (
    "proleptic_gregorian"
)


FILE_PATTERN = re.compile(
    r"^NWAM_SUMMA_forcing_(\d{4})(\d{2})\.nc$"
)


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

def read_from_control(
    file,
    setting,
):

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


def resolve_forcing_summa_path(
    control_file,
):
    """
    Resolve the lumped SUMMA forcing directory.

    Normally the lumped control contains an explicit
    forcing_summa_path.

    A default fallback is also retained.
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
            / "lumped"
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


def extract_year_month(
    path,
):

    match = FILE_PATTERN.match(
        path.name
    )

    if match is None:
        return None

    year = int(
        match.group(1)
    )

    month = int(
        match.group(2)
    )

    if not 1 <= month <= 12:

        raise RuntimeError(
            f"Invalid month in forcing filename:\n"
            f"{path}"
        )

    return (
        year,
        month,
    )


def next_month(
    year,
    month,
):

    if month == 12:

        return (
            year + 1,
            1,
        )

    return (
        year,
        month + 1,
    )


def discover_input_files(
    input_dir,
    start_ym=None,
    end_ym=None,
):

    discovered = []

    for file in input_dir.glob(
        "NWAM_SUMMA_forcing_*.nc"
    ):

        year_month = extract_year_month(
            file
        )

        if year_month is None:
            continue

        year, month = year_month

        ym = (
            year * 100
            + month
        )

        if (
            start_ym is not None
            and ym < start_ym
        ):
            continue

        if (
            end_ym is not None
            and ym > end_ym
        ):
            continue

        discovered.append(
            (
                year,
                month,
                file,
            )
        )

    discovered.sort(
        key=lambda item: (
            item[0],
            item[1],
        )
    )

    if not discovered:

        raise RuntimeError(
            "No monthly SUMMA forcing "
            "files found in:\n"
            f"{input_dir}"
        )

    year_months = [
        (
            year,
            month,
        )
        for year, month, _
        in discovered
    ]

    if len(
        set(
            year_months
        )
    ) != len(
        year_months
    ):

        raise RuntimeError(
            "Duplicate monthly forcing files "
            "were detected."
        )

    for current, following in zip(
        year_months[:-1],
        year_months[1:],
    ):

        expected = next_month(
            *current
        )

        if following != expected:

            raise RuntimeError(
                "Monthly forcing files are "
                "not consecutive.\n"
                f"Current month : "
                f"{current[0]:04d}{current[1]:02d}\n"
                f"Expected next : "
                f"{expected[0]:04d}{expected[1]:02d}\n"
                f"Actual next   : "
                f"{following[0]:04d}{following[1]:02d}"
            )

    return discovered


def check_non_time_dimensions(
    reference,
    candidate,
    filename,
):

    reference_dims = {
        name: len(dim)
        for name, dim
        in reference.dimensions.items()
        if name != "time"
    }

    candidate_dims = {
        name: len(dim)
        for name, dim
        in candidate.dimensions.items()
        if name != "time"
    }

    if reference_dims != candidate_dims:

        raise RuntimeError(
            "Non-time dimensions differ "
            "between monthly files.\n"
            f"File: {filename}\n"
            f"Expected: {reference_dims}\n"
            f"Found   : {candidate_dims}"
        )


def check_variable_structure(
    reference,
    candidate,
    filename,
):

    reference_vars = set(
        reference.variables
    )

    candidate_vars = set(
        candidate.variables
    )

    if reference_vars != candidate_vars:

        missing = sorted(
            reference_vars
            - candidate_vars
        )

        extra = sorted(
            candidate_vars
            - reference_vars
        )

        raise RuntimeError(
            "Variable structure differs "
            "between monthly files.\n"
            f"File: {filename}\n"
            f"Missing variables: {missing}\n"
            f"Extra variables  : {extra}"
        )

    for name in reference_vars:

        ref_var = (
            reference.variables[
                name
            ]
        )

        candidate_var = (
            candidate.variables[
                name
            ]
        )

        if (
            ref_var.dimensions
            != candidate_var.dimensions
        ):

            raise RuntimeError(
                "Variable dimensions differ.\n"
                f"File     : {filename}\n"
                f"Variable : {name}\n"
                f"Expected : "
                f"{ref_var.dimensions}\n"
                f"Found    : "
                f"{candidate_var.dimensions}"
            )

        if (
            ref_var.datatype
            != candidate_var.datatype
        ):

            raise RuntimeError(
                "Variable datatype differs.\n"
                f"File     : {filename}\n"
                f"Variable : {name}\n"
                f"Expected : "
                f"{ref_var.datatype}\n"
                f"Found    : "
                f"{candidate_var.datatype}"
            )


def decode_monthly_time(
    src,
    filename,
):

    if "time" not in src.variables:

        raise RuntimeError(
            f"time variable missing:\n"
            f"{filename}"
        )

    time_var = src.variables[
        "time"
    ]

    if not hasattr(
        time_var,
        "units",
    ):

        raise RuntimeError(
            f"time units missing:\n"
            f"{filename}"
        )

    units = time_var.units

    calendar = getattr(
        time_var,
        "calendar",
        "standard",
    )

    values = np.asarray(
        time_var[:]
    )

    if values.size == 0:

        raise RuntimeError(
            f"Empty time coordinate:\n"
            f"{filename}"
        )

    dates = num2date(
        values,
        units=units,
        calendar=calendar,
        only_use_cftime_datetimes=True,
    )

    return np.asarray(
        dates,
        dtype=object,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Concatenate monthly one-HRU "
            "SUMMA forcing files using a "
            "lumped CWARHM control file."
        )
    )

    parser.add_argument(
        "--control-file",
        required=True,
        type=Path,
        help=(
            "Domain-specific lumped "
            "CWARHM control file."
        ),
    )

    parser.add_argument(
        "--start-ym",
        type=int,
        default=None,
        help=(
            "Optional first month as YYYYMM."
        ),
    )

    parser.add_argument(
        "--end-ym",
        type=int,
        default=None,
        help=(
            "Optional last month as YYYYMM."
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Overwrite existing concatenated output."
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
            f"Lumped control file not found:\n"
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

    if (
        args.start_ym is not None
        and args.end_ym is not None
        and args.start_ym > args.end_ym
    ):

        raise ValueError(
            "--start-ym cannot be later "
            "than --end-ym."
        )

    if not input_dir.is_dir():

        raise FileNotFoundError(
            f"Missing lumped forcing input "
            f"directory:\n{input_dir}"
        )


    # ========================================================
    # DISCOVER MONTHLY FILES
    # ========================================================

    discovered = discover_input_files(
        input_dir,
        start_ym=args.start_ym,
        end_ym=args.end_ym,
    )

    first_year = discovered[0][0]
    first_month = discovered[0][1]

    last_year = discovered[-1][0]
    last_month = discovered[-1][1]

    first_ym = (
        f"{first_year:04d}"
        f"{first_month:02d}"
    )

    last_ym = (
        f"{last_year:04d}"
        f"{last_month:02d}"
    )

    input_files = [
        file
        for _, _, file
        in discovered
    ]

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        output_dir
        / (
            f"NWAM_SUMMA_forcing_"
            f"{first_ym}_{last_ym}.nc"
        )
    )


    # ========================================================
    # REPORT
    # ========================================================

    print()
    print("=" * 80)
    print("CONCATENATE ONE-HRU SUMMA FORCING")
    print("=" * 80)

    print(
        f"Control file   : {control_file}"
    )

    print(
        f"Domain         : {domain}"
    )

    print(
        f"Root path      : {root_path}"
    )

    print(
        f"Input          : {input_dir}"
    )

    print(
        f"Monthly files  : {len(input_files)}"
    )

    print(
        f"First month    : {first_ym}"
    )

    print(
        f"Last month     : {last_ym}"
    )

    print(
        f"Output         : {output_file}"
    )

    print(
        f"Output time ref: {OUTPUT_TIME_UNITS}"
    )

    print(
        "Time handling  : preserve monthly NetCDF timestamps"
    )

    print(
        "Timezone shift : none"
    )

    print("=" * 80)
    print()


    # ========================================================
    # PRE-SCAN
    # ========================================================

    monthly_lengths = []

    all_datetimes = []

    with Dataset(
        input_files[0],
        "r",
    ) as reference:

        if "time" not in reference.dimensions:

            raise RuntimeError(
                f"time dimension missing:\n"
                f"{input_files[0]}"
            )

        if "hru" not in reference.dimensions:

            raise RuntimeError(
                f"hru dimension missing:\n"
                f"{input_files[0]}"
            )

        if len(
            reference.dimensions[
                "hru"
            ]
        ) != 1:

            raise RuntimeError(
                "One-HRU forcing file must "
                "contain exactly one HRU.\n"
                f"File: {input_files[0]}"
            )

        missing_required = [
            variable
            for variable in REQUIRED_VARS
            if variable not in reference.variables
        ]

        if missing_required:

            raise RuntimeError(
                "Required SUMMA forcing variables "
                "are missing from the first file:\n"
                + "\n".join(
                    missing_required
                )
            )

        for (
            expected_year,
            expected_month,
            file,
        ) in discovered:

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

                if len(
                    src.dimensions[
                        "hru"
                    ]
                ) != 1:

                    raise RuntimeError(
                        "Expected exactly one HRU.\n"
                        f"File: {file}\n"
                        f"Found: "
                        f"{len(src.dimensions['hru'])}"
                    )

                check_non_time_dimensions(
                    reference,
                    src,
                    file,
                )

                check_variable_structure(
                    reference,
                    src,
                    file,
                )

                dates = decode_monthly_time(
                    src,
                    file,
                )

                first_date = dates[0]

                if (
                    int(first_date.year)
                    != expected_year
                    or int(first_date.month)
                    != expected_month
                ):

                    raise RuntimeError(
                        "Filename month does not "
                        "match first timestamp.\n"
                        f"File          : {file}\n"
                        f"Filename month: "
                        f"{expected_year:04d}"
                        f"{expected_month:02d}\n"
                        f"First time    : "
                        f"{first_date}"
                    )

                nt = len(
                    src.dimensions[
                        "time"
                    ]
                )

                if nt != len(
                    dates
                ):

                    raise RuntimeError(
                        "time dimension and decoded "
                        "time coordinate lengths differ.\n"
                        f"File: {file}"
                    )

                monthly_lengths.append(
                    nt
                )

                all_datetimes.extend(
                    dates.tolist()
                )

                print(
                    f"{file.name}: "
                    f"{nt} timesteps | "
                    f"{dates[0]} -> "
                    f"{dates[-1]}"
                )

    total_time = len(
        all_datetimes
    )

    if total_time <= 0:

        raise RuntimeError(
            "No forcing timesteps were found."
        )


    # ========================================================
    # COMMON TIME ENCODING
    # ========================================================

    output_time_values = np.asarray(
        date2num(
            all_datetimes,
            units=OUTPUT_TIME_UNITS,
            calendar=OUTPUT_TIME_CALENDAR,
        ),
        dtype=np.float64,
    )

    rounded_time_values = np.rint(
        output_time_values
    )

    if not np.allclose(
        output_time_values,
        rounded_time_values,
        rtol=0.0,
        atol=1.0e-8,
    ):

        raise RuntimeError(
            "Decoded forcing timestamps are "
            "not aligned to exact hourly intervals."
        )

    output_time_values = (
        rounded_time_values
        .astype(
            np.int64
        )
    )


    # ========================================================
    # TIME CONTINUITY
    # ========================================================

    if total_time > 1:

        time_differences = np.diff(
            output_time_values
        )

        if np.any(
            time_differences <= 0
        ):

            problem = np.where(
                time_differences <= 0
            )[0][0]

            raise RuntimeError(
                "Duplicate or decreasing forcing "
                "timestamps were detected.\n"
                f"Index: {problem}\n"
                f"Time 1: "
                f"{all_datetimes[problem]}\n"
                f"Time 2: "
                f"{all_datetimes[problem + 1]}"
            )

        if np.any(
            time_differences != 1
        ):

            problem = np.where(
                time_differences != 1
            )[0][0]

            raise RuntimeError(
                "A non-hourly gap was detected.\n"
                f"Index: {problem}\n"
                f"Time 1: "
                f"{all_datetimes[problem]}\n"
                f"Time 2: "
                f"{all_datetimes[problem + 1]}\n"
                f"Difference: "
                f"{time_differences[problem]} hours"
            )

    first_datetime = all_datetimes[
        0
    ]

    last_datetime = all_datetimes[
        -1
    ]

    print()

    print(
        f"Total hourly timesteps: "
        f"{total_time}"
    )

    print(
        f"First actual timestamp : "
        f"{first_datetime}"
    )

    print(
        f"Last actual timestamp  : "
        f"{last_datetime}"
    )


    # ========================================================
    # OUTPUT HANDLING
    # ========================================================

    if output_file.exists():

        if not args.overwrite:

            print()
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
    # CREATE OUTPUT
    # ========================================================

    first_file = input_files[
        0
    ]

    with Dataset(
        first_file,
        "r",
    ) as src0:

        with Dataset(
            output_file,
            "w",
            format=src0.data_model,
        ) as dst:

            for (
                dim_name,
                dim,
            ) in src0.dimensions.items():

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
                    "Concatenated one-HRU NWAM "
                    "SUMMA forcing "
                    f"for {domain} on "
                    f"{datetime.now():%Y-%m-%d %H:%M:%S}; "
                    "timestamps preserved from monthly "
                    "input files and re-encoded using "
                    f"'{OUTPUT_TIME_UNITS}'; "
                    "no UTC-to-local-time shift applied."
                ),
            )

            dst.setncattr(
                "CWARHM_control_file",
                control_file.name,
            )

            dst.setncattr(
                "Concatenated_first_month",
                first_ym,
            )

            dst.setncattr(
                "Concatenated_last_month",
                last_ym,
            )

            dst.setncattr(
                "Concatenated_month_count",
                len(
                    input_files
                ),
            )

            dst.setncattr(
                "Concatenated_time_steps",
                total_time,
            )

            dst.setncattr(
                "Time_reference",
                OUTPUT_TIME_UNITS,
            )

            dst.setncattr(
                "Time_zone_processing",
                (
                    "No timezone shift applied during "
                    "concatenation; source UTC timestamps "
                    "preserved."
                ),
            )

            for (
                var_name,
                src_var,
            ) in src0.variables.items():

                fill_value = None

                if (
                    "_FillValue"
                    in src_var.ncattrs()
                ):

                    fill_value = (
                        src_var.getncattr(
                            "_FillValue"
                        )
                    )

                if fill_value is not None:

                    dst_var = dst.createVariable(
                        var_name,
                        src_var.datatype,
                        src_var.dimensions,
                        fill_value=fill_value,
                    )

                else:

                    dst_var = dst.createVariable(
                        var_name,
                        src_var.datatype,
                        src_var.dimensions,
                    )

                copy_variable_attributes(
                    src_var,
                    dst_var,
                )

            for (
                var_name,
                src_var,
            ) in src0.variables.items():

                if (
                    "time"
                    not in src_var.dimensions
                ):

                    dst.variables[
                        var_name
                    ][:] = src_var[:]

            dst.variables[
                "time"
            ][:] = output_time_values

            dst.variables[
                "time"
            ].setncattr(
                "units",
                OUTPUT_TIME_UNITS,
            )

            dst.variables[
                "time"
            ].setncattr(
                "calendar",
                OUTPUT_TIME_CALENDAR,
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

            out_start = 0

            for (
                file,
                nt,
            ) in zip(
                input_files,
                monthly_lengths,
            ):

                out_end = (
                    out_start
                    + nt
                )

                print(
                    f"Writing {file.name}: "
                    f"{out_start} -> "
                    f"{out_end - 1}"
                )

                with Dataset(
                    file,
                    "r",
                ) as src:

                    for (
                        var_name,
                        src_var,
                    ) in src.variables.items():

                        if var_name == "time":
                            continue

                        if (
                            "time"
                            not in src_var.dimensions
                        ):
                            continue

                        time_axis = (
                            src_var.dimensions
                            .index(
                                "time"
                            )
                        )

                        src_slice = [
                            slice(None)
                        ] * src_var.ndim

                        dst_slice = [
                            slice(None)
                        ] * src_var.ndim

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

                out_start = (
                    out_end
                )


    # ========================================================
    # FINAL VERIFICATION
    # ========================================================

    with Dataset(
        output_file,
        "r",
    ) as ds:

        if (
            len(
                ds.dimensions[
                    "time"
                ]
            )
            != total_time
        ):

            raise RuntimeError(
                "Final time dimension is incorrect."
            )

        if (
            len(
                ds.dimensions[
                    "hru"
                ]
            )
            != 1
        ):

            raise RuntimeError(
                "Final file does not contain "
                "exactly one HRU."
            )

        missing_vars = [
            variable
            for variable in REQUIRED_VARS
            if variable not in ds.variables
        ]

        if missing_vars:

            raise RuntimeError(
                "Missing required forcing variables:\n"
                + "\n".join(
                    missing_vars
                )
            )

        if "hruId" in ds.variables:

            hru_ids = np.asarray(
                ds.variables[
                    "hruId"
                ][:]
            ).reshape(
                -1
            )

            if (
                len(
                    hru_ids
                )
                != 1
                or int(
                    hru_ids[0]
                )
                != 1
            ):

                raise RuntimeError(
                    "Unexpected hruId values:\n"
                    f"{hru_ids.tolist()}"
                )

        saved_time = np.asarray(
            ds.variables[
                "time"
            ][:]
        ).astype(
            np.int64
        )

        if not np.array_equal(
            saved_time,
            output_time_values,
        ):

            raise RuntimeError(
                "Saved time coordinate does not "
                "match decoded monthly timestamps."
            )

        saved_dates = num2date(
            saved_time,
            units=ds.variables[
                "time"
            ].units,
            calendar=getattr(
                ds.variables[
                    "time"
                ],
                "calendar",
                "standard",
            ),
            only_use_cftime_datetimes=True,
        )


    # ========================================================
    # FINISH
    # ========================================================

    print()
    print("=" * 80)
    print("PASS: LUMPED SUMMA FORCING CONCATENATION")
    print("=" * 80)

    print(
        f"Domain          : {domain}"
    )

    print(
        f"Monthly files   : {len(input_files)}"
    )

    print(
        f"First month     : {first_ym}"
    )

    print(
        f"Last month      : {last_ym}"
    )

    print(
        f"Hourly steps    : {total_time}"
    )

    print(
        "HRUs            : 1"
    )

    print(
        f"First timestamp : "
        f"{saved_dates[0]}"
    )

    print(
        f"Last timestamp  : "
        f"{saved_dates[-1]}"
    )

    print(
        f"Time reference  : "
        f"{OUTPUT_TIME_UNITS}"
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