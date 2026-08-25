#!/usr/bin/env python3

"""
Clean and validate yearly mizuRoute output files.

Purpose
-------
Parallel mizuRoute / PIO runs can occasionally create duplicate
time records at yearly output-file boundaries.

The script is deliberately conservative. It removes a duplicate
timestamp only when the duplicated records are identical for every
time-dependent NetCDF variable.

If duplicate timestamps contain different model values, or if the
time axis contains another kind of error, the script stops without
silently repairing the file.

Usage
-----
Production Stage 6:

    python 4_clean_mizuroute_outputs.py

The mizuRoute output directory is then obtained from
control_active.txt.

Optional explicit directory, useful for testing:

    python 4_clean_mizuroute_outputs.py \
        /path/to/mizuRoute_test_4rank

Workflow
--------
1. Read active domain and experiment from control_active.txt.
2. Determine the mizuRoute output directory.
3. Find yearly mizuRoute history files.
4. Check record counts and time coordinates.
5. Detect duplicate timestamps.
6. Verify duplicate records are exactly identical.
7. Remove only verified-identical duplicate records.
8. Rewrite affected files through temporary NetCDF files.
9. Preserve the original affected file as a backup.
10. Run strict QA over every yearly output file.
11. Record provenance.

Expected hourly yearly record counts:
    normal year = 8760
    leap year   = 8784
"""

from pathlib import Path
from datetime import datetime
import argparse
import calendar
import shutil

import netCDF4 as nc
import numpy as np


# ============================================================
# PATHS
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM_ROOT = SCRIPT_DIR.parent

CONTROL_FILE = (
    CWARHM_ROOT
    / "0_control_files"
    / "control_active.txt"
)


# ============================================================
# COMMAND-LINE ARGUMENTS
# ============================================================

parser = argparse.ArgumentParser(
    description=(
        "Validate and safely remove verified-identical duplicate "
        "timestamps from yearly mizuRoute output files."
    )
)

parser.add_argument(
    "output_directory",
    nargs="?",
    default=None,
    help=(
        "Optional mizuRoute output directory. "
        "If omitted, experiment_output_mizuRoute is read "
        "from control_active.txt."
    ),
)

args = parser.parse_args()


# ============================================================
# CONTROL READER
# ============================================================

def read_control(setting):
    """
    Read one exact setting from control_active.txt.
    """

    if not CONTROL_FILE.exists():
        raise FileNotFoundError(
            "CWARHM control file not found:\n"
            f"{CONTROL_FILE}"
        )

    with open(CONTROL_FILE) as contents:

        for line in contents:

            stripped = line.strip()

            if (
                not stripped
                or stripped.startswith("#")
                or "|" not in stripped
            ):
                continue

            left, right = stripped.split("|", 1)

            if left.strip() == setting:

                return (
                    right
                    .split("#", 1)[0]
                    .strip()
                )

    raise ValueError(
        f"Setting not found in control file: {setting}"
    )


# ============================================================
# CONTROL SETTINGS
# ============================================================

root_path = Path(
    read_control("root_path")
)

domain_name = read_control(
    "domain_name"
)

experiment_id = read_control(
    "experiment_id"
)


# ============================================================
# DETERMINE MIZUROUTE OUTPUT DIRECTORY
# ============================================================

if args.output_directory is not None:

    mizu_output = Path(
        args.output_directory
    ).expanduser().resolve()

    output_source = "command-line argument"

else:

    configured_output = read_control(
        "experiment_output_mizuRoute"
    )

    if configured_output == "default":

        mizu_output = (
            root_path
            / f"domain_{domain_name}"
            / "simulations"
            / experiment_id
            / "mizuRoute"
        )

    else:

        mizu_output = Path(
            configured_output
        )

    mizu_output = mizu_output.resolve()

    output_source = "control_active.txt"


if not mizu_output.exists():

    raise FileNotFoundError(
        "mizuRoute output directory not found:\n"
        f"{mizu_output}"
    )


if not mizu_output.is_dir():

    raise RuntimeError(
        "mizuRoute output path is not a directory:\n"
        f"{mizu_output}"
    )


# ============================================================
# FILE DISCOVERY
# ============================================================

files = sorted(
    mizu_output.glob(
        f"{experiment_id}.h.*.nc"
    ),
    key=lambda path: int(
        path.stem.split(".")[-1]
    ),
)


if not files:

    raise RuntimeError(
        "No yearly mizuRoute output files found.\n\n"
        f"Directory : {mizu_output}\n"
        f"Pattern   : {experiment_id}.h.*.nc"
    )


# ============================================================
# INITIAL REPORT
# ============================================================

print()
print("============================================================")
print("CLEAN MIZUROUTE PARALLEL OUTPUTS")
print("============================================================")
print(f"Domain        : {domain_name}")
print(f"Experiment    : {experiment_id}")
print(f"Output        : {mizu_output}")
print(f"Output source : {output_source}")
print(f"Yearly files  : {len(files)}")
print("============================================================")
print()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def expected_year_records(year):
    """
    Return expected number of hourly records for a year.
    """

    return (
        8784
        if calendar.isleap(year)
        else 8760
    )


def masked_to_array(values):
    """
    Convert a NetCDF masked array into a regular NumPy array.

    Floating masked values are represented by NaN.
    Non-floating arrays retain their underlying fill values.
    """

    if not np.ma.isMaskedArray(values):
        return np.asarray(values)

    if np.issubdtype(
        values.dtype,
        np.floating
    ):
        return np.asarray(
            np.ma.filled(
                values,
                np.nan
            )
        )

    return np.asarray(
        values.filled()
    )


def arrays_identical(a, b):
    """
    Strict equality check allowing NaN == NaN for floating data.
    """

    a = masked_to_array(a)
    b = masked_to_array(b)

    if a.shape != b.shape:
        return False

    if np.issubdtype(
        a.dtype,
        np.floating
    ):

        return np.allclose(
            a,
            b,
            rtol=0.0,
            atol=0.0,
            equal_nan=True,
        )

    return np.array_equal(
        a,
        b
    )


def records_identical(ds, i, j):
    """
    Check whether two records with the same timestamp are
    identical for every time-dependent variable.

    Returns
    -------
    identical : bool
    variable  : str or None
        First variable that differs.
    """

    for name, var in ds.variables.items():

        if "time" not in var.dimensions:
            continue

        if name == "time":
            continue

        time_axis = var.dimensions.index(
            "time"
        )

        slice_i = [
            slice(None)
        ] * var.ndim

        slice_j = [
            slice(None)
        ] * var.ndim

        slice_i[time_axis] = int(i)
        slice_j[time_axis] = int(j)

        a = var[
            tuple(slice_i)
        ]

        b = var[
            tuple(slice_j)
        ]

        if not arrays_identical(
            a,
            b
        ):

            return False, name

    return True, None


def copy_global_attributes(src, dst):
    """
    Copy all global NetCDF attributes.
    """

    for attr in src.ncattrs():

        dst.setncattr(
            attr,
            src.getncattr(attr)
        )


def copy_variable_attributes(src_var, dst_var):
    """
    Copy variable attributes except _FillValue, which must be
    supplied when the destination variable is created.
    """

    for attr in src_var.ncattrs():

        if attr == "_FillValue":
            continue

        dst_var.setncattr(
            attr,
            src_var.getncattr(attr)
        )


def variable_creation_options(src_var):
    """
    Preserve important NetCDF storage properties where possible.
    """

    options = {}

    if "_FillValue" in src_var.ncattrs():

        options["fill_value"] = (
            src_var.getncattr(
                "_FillValue"
            )
        )

    try:

        filters = src_var.filters()

    except Exception:

        filters = None


    if filters:

        if filters.get(
            "zlib",
            False
        ):
            options["zlib"] = True

            options["complevel"] = (
                filters.get(
                    "complevel",
                    4
                )
            )

            options["shuffle"] = (
                filters.get(
                    "shuffle",
                    True
                )
            )


    try:

        chunking = src_var.chunking()

    except Exception:

        chunking = None


    if (
        isinstance(
            chunking,
            list
        )
        and len(chunking) > 0
    ):

        options["chunksizes"] = tuple(
            int(value)
            for value in chunking
        )

    return options


def validate_time_axis(
    time,
    expected_records,
    filename,
):
    """
    Strict validation of a yearly hourly time axis.
    """

    n_records = len(time)

    unique_records = len(
        np.unique(time)
    )

    non_increasing = int(
        np.sum(
            np.diff(time) <= 0
        )
    )

    valid = (
        n_records == expected_records
        and unique_records == expected_records
        and non_increasing == 0
    )

    return (
        valid,
        n_records,
        unique_records,
        non_increasing,
    )


# ============================================================
# PROCESS FILES
# ============================================================

files_modified = 0
duplicates_removed_total = 0

cleaned_files = []

cleanup_time = datetime.now()


for file in files:

    try:

        year = int(
            file.stem.split(".")[-1]
        )

    except ValueError as exc:

        raise RuntimeError(
            "Unable to determine year from mizuRoute filename:\n"
            f"{file}"
        ) from exc


    expected_records = (
        expected_year_records(
            year
        )
    )


    print(
        "------------------------------------------------------------"
    )

    print(
        file.name
    )


    # ========================================================
    # INSPECT ORIGINAL FILE
    # ========================================================

    with nc.Dataset(
        file,
        "r"
    ) as ds:

        if "time" not in ds.variables:

            raise RuntimeError(
                "time variable missing from:\n"
                f"{file}"
            )


        time = np.asarray(
            ds.variables["time"][:]
        )


        if time.ndim != 1:

            raise RuntimeError(
                f"{file.name}: time variable must be "
                "one-dimensional.\n"
                f"Shape found: {time.shape}"
            )


        if len(time) == 0:

            raise RuntimeError(
                f"{file.name}: time variable is empty."
            )


        if not np.all(
            np.isfinite(time)
        ):

            raise RuntimeError(
                f"{file.name}: non-finite timestamps detected."
            )


        differences = np.diff(
            time
        )


        decreasing_indices = np.where(
            differences < 0
        )[0]


        if len(
            decreasing_indices
        ) > 0:

            raise RuntimeError(
                f"{file.name} contains decreasing timestamps.\n"
                f"First indices: "
                f"{decreasing_indices[:20].tolist()}\n\n"
                "This is not treated as a safe duplicate-record "
                "condition. File was not modified."
            )


        duplicate_pairs = np.where(
            differences == 0
        )[0]


        # ----------------------------------------------------
        # Already clean
        # ----------------------------------------------------

        if len(
            duplicate_pairs
        ) == 0:

            (
                valid,
                n_records,
                unique_records,
                non_increasing,
            ) = validate_time_axis(
                time,
                expected_records,
                file.name,
            )


            if not valid:

                raise RuntimeError(
                    f"{file.name} has an invalid yearly time axis "
                    "but contains no simple adjacent duplicate "
                    "timestamps.\n\n"
                    f"Records        : {n_records}\n"
                    f"Expected       : {expected_records}\n"
                    f"Unique         : {unique_records}\n"
                    f"Non-increasing : {non_increasing}\n\n"
                    "File was not modified."
                )


            print(
                f"PASS: records={n_records}, "
                "duplicates=0"
            )

            continue


        # ----------------------------------------------------
        # Duplicate records found
        # ----------------------------------------------------

        print(
            f"Duplicate transitions detected: "
            f"{len(duplicate_pairs)}"
        )


        # ----------------------------------------------------
        # Verify each adjacent duplicate
        # ----------------------------------------------------

        for i in duplicate_pairs:

            i = int(i)

            identical, differing_variable = (
                records_identical(
                    ds,
                    i,
                    i + 1,
                )
            )


            if not identical:

                raise RuntimeError(
                    "Unsafe duplicate timestamp detected.\n\n"
                    f"File       : {file}\n"
                    f"Timestamp  : {time[i]}\n"
                    f"Records    : {i}, {i + 1}\n"
                    f"Difference : {differing_variable}\n\n"
                    "The duplicated timestamp contains different "
                    "model values. The file was NOT modified."
                )


        # ----------------------------------------------------
        # Keep first occurrence of each timestamp
        # ----------------------------------------------------

        _, keep_indices = np.unique(
            time,
            return_index=True,
        )

        keep_indices = np.sort(
            keep_indices
        )


        cleaned_time = time[
            keep_indices
        ]


        removed = (
            len(time)
            - len(cleaned_time)
        )


        if removed <= 0:

            raise RuntimeError(
                f"Internal cleanup error for {file.name}: "
                "duplicates were detected but no records "
                "would be removed."
            )


        (
            valid_cleaned,
            cleaned_records,
            cleaned_unique,
            cleaned_noninc,
        ) = validate_time_axis(
            cleaned_time,
            expected_records,
            file.name,
        )


        if not valid_cleaned:

            raise RuntimeError(
                f"Removing verified duplicate timestamps from "
                f"{file.name} does not produce a valid yearly "
                "time axis.\n\n"
                f"Cleaned records        : {cleaned_records}\n"
                f"Expected               : {expected_records}\n"
                f"Unique                 : {cleaned_unique}\n"
                f"Non-increasing         : {cleaned_noninc}\n\n"
                "File was not modified."
            )


    # ========================================================
    # FILE PATHS FOR SAFE REWRITE
    # ========================================================

    temp_file = Path(
        str(file) + ".tmp"
    )

    backup_file = Path(
        str(file)
        + ".pre_duplicate_cleanup"
    )


    if temp_file.exists():

        temp_file.unlink()


    # ========================================================
    # REWRITE CLEANED FILE
    # ========================================================

    try:

        with nc.Dataset(
            file,
            "r"
        ) as src:

            source_format = (
                src.file_format
            )


            with nc.Dataset(
                temp_file,
                "w",
                format=source_format,
            ) as dst:


                # ============================================
                # DIMENSIONS
                # ============================================

                for (
                    dim_name,
                    dim,
                ) in src.dimensions.items():

                    if dim_name == "time":

                        if dim.isunlimited():

                            dst.createDimension(
                                dim_name,
                                None,
                            )

                        else:

                            dst.createDimension(
                                dim_name,
                                len(
                                    keep_indices
                                ),
                            )

                    else:

                        dst.createDimension(
                            dim_name,
                            None
                            if dim.isunlimited()
                            else len(dim),
                        )


                # ============================================
                # GLOBAL ATTRIBUTES
                # ============================================

                copy_global_attributes(
                    src,
                    dst,
                )


                dst.setncattr(
                    "duplicate_time_cleanup",
                    (
                        "Verified-identical duplicate time "
                        "records removed by "
                        "4_clean_mizuroute_outputs.py"
                    ),
                )


                dst.setncattr(
                    "duplicate_time_cleanup_date",
                    cleanup_time.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                )


                dst.setncattr(
                    "duplicate_time_records_removed",
                    int(removed),
                )


                # ============================================
                # VARIABLES
                # ============================================

                for (
                    name,
                    src_var,
                ) in src.variables.items():

                    creation_options = (
                        variable_creation_options(
                            src_var
                        )
                    )


                    # Time dimension changed. Original chunk size
                    # can occasionally exceed the new dimension.
                    if (
                        "chunksizes"
                        in creation_options
                    ):

                        chunks = list(
                            creation_options[
                                "chunksizes"
                            ]
                        )

                        for axis, dim_name in enumerate(
                            src_var.dimensions
                        ):

                            if dim_name == "time":

                                chunks[axis] = min(
                                    chunks[axis],
                                    len(
                                        keep_indices
                                    ),
                                )

                        creation_options[
                            "chunksizes"
                        ] = tuple(
                            chunks
                        )


                    dst_var = (
                        dst.createVariable(
                            name,
                            src_var.dtype,
                            src_var.dimensions,
                            **creation_options,
                        )
                    )


                    copy_variable_attributes(
                        src_var,
                        dst_var,
                    )


                    # ----------------------------------------
                    # Variables without time dimension
                    # ----------------------------------------

                    if (
                        "time"
                        not in src_var.dimensions
                    ):

                        dst_var[:] = (
                            src_var[:]
                        )

                        continue


                    # ----------------------------------------
                    # Time-dependent variables
                    # ----------------------------------------

                    time_axis = (
                        src_var.dimensions.index(
                            "time"
                        )
                    )


                    data = (
                        src_var[:]
                    )


                    cleaned_data = np.take(
                        data,
                        keep_indices,
                        axis=time_axis,
                    )


                    dst_var[:] = (
                        cleaned_data
                    )


    except Exception:

        if temp_file.exists():
            temp_file.unlink()

        raise


    # ========================================================
    # VERIFY TEMPORARY FILE BEFORE REPLACEMENT
    # ========================================================

    with nc.Dataset(
        temp_file,
        "r"
    ) as check:

        if "time" not in check.variables:

            temp_file.unlink()

            raise RuntimeError(
                "Temporary cleaned file does not contain "
                f"time variable:\n{temp_file}"
            )


        cleaned = np.asarray(
            check.variables["time"][:]
        )


        (
            valid_temp,
            temp_records,
            temp_unique,
            temp_noninc,
        ) = validate_time_axis(
            cleaned,
            expected_records,
            temp_file.name,
        )


        if not valid_temp:

            temp_file.unlink()

            raise RuntimeError(
                "Temporary cleaned file failed QA:\n"
                f"{temp_file}\n\n"
                f"Records        : {temp_records}\n"
                f"Expected       : {expected_records}\n"
                f"Unique         : {temp_unique}\n"
                f"Non-increasing : {temp_noninc}"
            )


    # ========================================================
    # REPLACE ORIGINAL ONLY AFTER SUCCESSFUL QA
    # ========================================================

    if backup_file.exists():

        backup_file.unlink()


    shutil.move(
        str(file),
        str(backup_file),
    )


    try:

        shutil.move(
            str(temp_file),
            str(file),
        )

    except Exception:

        # Restore original if final move fails.
        if not file.exists():
            shutil.move(
                str(backup_file),
                str(file),
            )

        raise


    files_modified += 1

    duplicates_removed_total += (
        removed
    )

    cleaned_files.append(
        (
            file.name,
            removed,
            backup_file.name,
        )
    )


    print(
        f"CLEANED: removed {removed} "
        "verified-identical duplicate "
        "record(s)."
    )

    print(
        f"Backup : {backup_file.name}"
    )


# ============================================================
# FINAL FULL QA
# ============================================================

print()
print("============================================================")
print("FINAL CLEANED OUTPUT QA")
print("============================================================")


all_ok = True


for file in files:

    year = int(
        file.stem.split(".")[-1]
    )

    expected = (
        expected_year_records(
            year
        )
    )


    with nc.Dataset(
        file,
        "r"
    ) as ds:

        if "time" not in ds.variables:

            all_ok = False

            print(
                year,
                "FAIL: time variable missing",
            )

            continue


        time = np.asarray(
            ds.variables["time"][:]
        )


    (
        ok,
        n_records,
        unique_records,
        non_increasing,
    ) = validate_time_axis(
        time,
        expected,
        file.name,
    )


    if not ok:
        all_ok = False


    print(
        year,
        f"records={n_records}",
        f"expected={expected}",
        f"unique={unique_records}",
        f"noninc={non_increasing}",
        "OK" if ok else "FAIL",
    )


# ============================================================
# PROVENANCE
# ============================================================

log_dir = (
    mizu_output
    / "_workflow_log"
)

log_dir.mkdir(
    parents=True,
    exist_ok=True,
)


timestamp = datetime.now()


log_file = (
    log_dir
    / (
        f"{timestamp:%Y%m%d_%H%M%S}_"
        "clean_mizuroute_outputs.txt"
    )
)


with open(
    log_file,
    "w"
) as log:

    log.write(
        "mizuRoute duplicate-time cleanup\n"
    )

    log.write(
        f"Date: {timestamp:%Y-%m-%d %H:%M:%S}\n"
    )

    log.write(
        f"Domain: {domain_name}\n"
    )

    log.write(
        f"Experiment: {experiment_id}\n"
    )

    log.write(
        f"Output directory: {mizu_output}\n"
    )

    log.write(
        f"Output source: {output_source}\n"
    )

    log.write(
        f"Yearly files: {len(files)}\n"
    )

    log.write(
        f"Files modified: {files_modified}\n"
    )

    log.write(
        "Duplicate records removed: "
        f"{duplicates_removed_total}\n"
    )

    log.write(
        f"Final QA: "
        f"{'PASS' if all_ok else 'FAIL'}\n"
    )


    if cleaned_files:

        log.write(
            "\nModified files:\n"
        )

        for (
            filename,
            removed,
            backup,
        ) in cleaned_files:

            log.write(
                f"  {filename}: "
                f"removed={removed}; "
                f"backup={backup}\n"
            )


# ============================================================
# COPY SCRIPT FOR PROVENANCE
# ============================================================

provenance_script = (
    log_dir
    / Path(__file__).name
)


shutil.copyfile(
    Path(__file__).resolve(),
    provenance_script,
)


# ============================================================
# FINAL SUMMARY
# ============================================================

print()
print("============================================================")
print("MIZUROUTE OUTPUT CLEANUP COMPLETE")
print("============================================================")

print(
    f"Yearly files checked       : "
    f"{len(files)}"
)

print(
    f"Files modified             : "
    f"{files_modified}"
)

print(
    f"Duplicate records removed  : "
    f"{duplicates_removed_total}"
)

print(
    f"Final result               : "
    f"{'PASS' if all_ok else 'FAIL'}"
)

print(
    f"Log                        : "
    f"{log_file}"
)

print("============================================================")


if not all_ok:

    raise RuntimeError(
        "One or more mizuRoute output files failed "
        "the final Stage 6 duplicate-time QA."
    )