#!/usr/bin/env python3

"""
Merge spatially split SUMMA array outputs into one timestep file
for mizuRoute.

Example SUMMA array files:
    run1_G001-010_timestep.nc
    run1_G011-020_timestep.nc
    ...

Output:
    run1_timestep.nc

The script:
    - reads control_active.txt
    - finds the active domain and experiment
    - discovers SUMMA array timestep files
    - ignores interrupted files with zero time steps
    - rejects overlapping/stale GRU-array files
    - verifies all array files use the same time axis
    - verifies GRU IDs are unique
    - verifies GRU IDs exactly match attributes.nc
    - preserves the expected GRU ordering
    - merges averageRoutedRunoff spatially along gru
    - verifies the merged output
    - samples runoff values for NaN/Inf
    - writes provenance information

This merged file is the runoff input expected by mizuRoute.
"""


from pathlib import Path
from datetime import datetime
from shutil import copyfile
import re

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
# CONTROL READER
# ============================================================

def read_control(setting):
    """Read one exact setting from control_active.txt."""

    with CONTROL_FILE.open() as contents:

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
# SETTINGS
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


# ------------------------------------------------------------
# SUMMA output path
# ------------------------------------------------------------

summa_output = read_control(
    "experiment_output_summa"
)

if summa_output == "default":

    summa_output = (
        root_path
        / f"domain_{domain_name}"
        / "simulations"
        / experiment_id
        / "SUMMA"
    )

else:

    summa_output = Path(
        summa_output
    )


# ------------------------------------------------------------
# SUMMA settings path
# ------------------------------------------------------------

settings_path = read_control(
    "settings_summa_path"
)

if settings_path == "default":

    settings_path = (
        root_path
        / f"domain_{domain_name}"
        / "settings"
        / "SUMMA"
    )

else:

    settings_path = Path(
        settings_path
    )


# ------------------------------------------------------------
# SUMMA attributes file
# ------------------------------------------------------------

attributes_name = read_control(
    "settings_summa_attributes"
)

attributes_file = (
    settings_path
    / attributes_name
)


# ============================================================
# INPUT / OUTPUT FILE DISCOVERY
# ============================================================

pattern = re.compile(
    rf"^{re.escape(experiment_id)}_"
    r"G(\d+)-(\d+)_timestep\.nc$"
)


array_files = []


for file in summa_output.glob(
    f"{experiment_id}_G*-*_timestep.nc"
):

    match = pattern.match(
        file.name
    )

    if match:

        start = int(
            match.group(1)
        )

        end = int(
            match.group(2)
        )

        array_files.append(
            (
                start,
                end,
                file
            )
        )


array_files.sort(
    key=lambda item: item[0]
)


output_file = (
    summa_output
    / f"{experiment_id}_timestep.nc"
)


# ============================================================
# BASIC CHECKS
# ============================================================

if not summa_output.exists():

    raise FileNotFoundError(
        "SUMMA output directory does not exist:\n"
        f"{summa_output}"
    )


if not array_files:

    raise RuntimeError(
        "No SUMMA array timestep files found in:\n"
        f"{summa_output}"
    )


if not attributes_file.exists():

    raise FileNotFoundError(
        "SUMMA attributes file not found:\n"
        f"{attributes_file}"
    )


# ============================================================
# EXPECTED GRU INFORMATION FROM ATTRIBUTES.NC
# ============================================================

with nc.Dataset(
    attributes_file
) as ds:

    if "gru" not in ds.dimensions:

        raise RuntimeError(
            "SUMMA attributes file does not contain "
            "the 'gru' dimension."
        )

    if "gruId" not in ds.variables:

        raise RuntimeError(
            "SUMMA attributes file does not contain "
            "the 'gruId' variable."
        )

    expected_grus = len(
        ds.dimensions["gru"]
    )

    expected_gru_ids = np.asarray(
        ds.variables["gruId"][:],
        dtype=np.int64
    )


if len(expected_gru_ids) != expected_grus:

    raise RuntimeError(
        "gruId length in attributes.nc does not match "
        "the gru dimension."
    )


if len(
    np.unique(expected_gru_ids)
) != expected_grus:

    raise RuntimeError(
        "Duplicate gruId values detected in attributes.nc."
    )


# ============================================================
# INITIAL REPORT
# ============================================================

print()
print("============================================================")
print("MERGE SUMMA ARRAY OUTPUTS")
print("============================================================")

print(f"Domain          : {domain_name}")
print(f"Experiment      : {experiment_id}")
print(f"SUMMA output    : {summa_output}")
print(f"Attributes file : {attributes_file}")
print(f"Expected GRUs   : {expected_grus}")

print()


# ============================================================
# INSPECT ARRAY FILES
# ============================================================

valid_files = []

reference_time = None
reference_time_units = None
ntime = None


for start, end, file in array_files:

    with nc.Dataset(
        file
    ) as ds:

        # ----------------------------------------------------
        # Required dimensions
        # ----------------------------------------------------

        if (
            "time" not in ds.dimensions
            or "gru" not in ds.dimensions
        ):

            print(
                f"SKIP: {file.name} "
                "(missing time/gru dimension)"
            )

            continue


        nt = len(
            ds.dimensions["time"]
        )

        ng = len(
            ds.dimensions["gru"]
        )


        # ----------------------------------------------------
        # Ignore interrupted diagnostic files
        # ----------------------------------------------------

        if nt == 0:

            print(
                f"SKIP: {file.name} "
                "(0 time steps)"
            )

            continue


        # ----------------------------------------------------
        # Required variables
        # ----------------------------------------------------

        required_variables = {
            "time",
            "gruId",
            "averageRoutedRunoff"
        }

        missing = (
            required_variables
            - set(ds.variables)
        )

        if missing:

            raise RuntimeError(
                f"{file.name} is missing required variables: "
                f"{sorted(missing)}"
            )


        # ----------------------------------------------------
        # Validate filename range
        # ----------------------------------------------------

        expected_count_from_name = (
            end
            - start
            + 1
        )

        if expected_count_from_name != ng:

            raise RuntimeError(
                f"{file.name}: filename implies "
                f"{expected_count_from_name} GRUs, "
                f"but file contains {ng}."
            )


        # ----------------------------------------------------
        # Time axis
        # ----------------------------------------------------

        time_var = ds.variables[
            "time"
        ]

        times = np.asarray(
            time_var[:]
        )


        if len(times) != nt:

            raise RuntimeError(
                f"{file.name}: time variable length "
                "does not match time dimension."
            )


        if not np.all(
            np.isfinite(times)
        ):

            raise RuntimeError(
                f"{file.name}: non-finite values found "
                "in time coordinate."
            )


        if np.any(
            np.diff(times) <= 0
        ):

            raise RuntimeError(
                f"{file.name}: time values are not "
                "strictly increasing."
            )


        time_units = getattr(
            time_var,
            "units",
            None
        )


        if reference_time is None:

            reference_time = times.copy()

            reference_time_units = (
                time_units
            )

            ntime = nt

        else:

            if nt != ntime:

                raise RuntimeError(
                    f"Time dimension mismatch in "
                    f"{file.name}: "
                    f"{nt} != {ntime}"
                )


            if not np.array_equal(
                times,
                reference_time
            ):

                raise RuntimeError(
                    f"Time values differ in "
                    f"{file.name}"
                )


            if (
                time_units
                != reference_time_units
            ):

                raise RuntimeError(
                    f"Time units differ in "
                    f"{file.name}"
                )


        # ----------------------------------------------------
        # GRU IDs
        # ----------------------------------------------------

        gru_ids = np.asarray(
            ds.variables[
                "gruId"
            ][:],
            dtype=np.int64
        )


        if len(gru_ids) != ng:

            raise RuntimeError(
                f"gruId size mismatch in "
                f"{file.name}"
            )


        if len(
            np.unique(gru_ids)
        ) != ng:

            raise RuntimeError(
                f"Duplicate gruId values inside "
                f"{file.name}"
            )


        # ----------------------------------------------------
        # Runoff dimensions
        # ----------------------------------------------------

        runoff = ds.variables[
            "averageRoutedRunoff"
        ]

        expected_shape = (
            nt,
            ng
        )


        if runoff.shape != expected_shape:

            raise RuntimeError(
                f"{file.name}: "
                "averageRoutedRunoff has shape "
                f"{runoff.shape}, "
                f"expected {expected_shape}."
            )


        valid_files.append(
            (
                start,
                end,
                file,
                ng,
                gru_ids
            )
        )


        print(
            f"OK: {file.name:<32} "
            f"time={nt:<8} "
            f"gru={ng:<5} "
            f"range={start}-{end}"
        )


# ============================================================
# CHECK VALID FILES
# ============================================================

if not valid_files:

    raise RuntimeError(
        "No valid SUMMA timestep files found."
    )


# ============================================================
# CHECK FOR OVERLAPPING / STALE ARRAY FILES
# ============================================================

for previous, current in zip(
    valid_files[:-1],
    valid_files[1:]
):

    previous_start = previous[0]
    previous_end = previous[1]
    previous_file = previous[2]

    current_start = current[0]
    current_end = current[1]
    current_file = current[2]


    if current_start <= previous_end:

        raise RuntimeError(
            "\nOverlapping SUMMA array outputs detected.\n\n"
            f"Previous: {previous_file.name} "
            f"({previous_start}-{previous_end})\n"
            f"Current : {current_file.name} "
            f"({current_start}-{current_end})\n\n"
            "This usually means an old diagnostic or test "
            "SUMMA file remains in the output directory.\n"
            "Remove stale array outputs before merging."
        )


# ============================================================
# CHECK ARRAY RANGE CONTINUITY
# ============================================================

expected_start = 1


for start, end, file, ng, gru_ids in valid_files:

    if start != expected_start:

        raise RuntimeError(
            "Gap detected in SUMMA array ranges.\n"
            f"Expected next range to start at GRU "
            f"{expected_start}, "
            f"but {file.name} starts at {start}."
        )

    expected_start = (
        end
        + 1
    )


if expected_start - 1 != expected_grus:

    raise RuntimeError(
        "SUMMA array ranges do not cover all expected GRUs.\n"
        f"Array files cover GRUs 1-{expected_start - 1}, "
        f"but attributes.nc contains {expected_grus} GRUs."
    )


# ============================================================
# COMBINE GRU IDS
# ============================================================

all_gru_ids = np.concatenate(
    [
        item[4]
        for item in valid_files
    ]
).astype(
    np.int64
)


# ============================================================
# VALIDATE COMBINED GRUS
# ============================================================

if len(all_gru_ids) != expected_grus:

    raise RuntimeError(
        f"Combined SUMMA files contain "
        f"{len(all_gru_ids)} GRUs, "
        f"but attributes.nc contains "
        f"{expected_grus}."
    )


if len(
    np.unique(all_gru_ids)
) != expected_grus:

    raise RuntimeError(
        "Duplicate gruId values detected "
        "across SUMMA array files."
    )


# Strongest check:
# the merged GRU order must exactly match attributes.nc.

if not np.array_equal(
    all_gru_ids,
    expected_gru_ids
):

    print()
    print("First SUMMA array GRU IDs:")
    print(
        all_gru_ids[:10]
    )

    print()
    print("First attributes.nc GRU IDs:")
    print(
        expected_gru_ids[:10]
    )

    raise RuntimeError(
        "SUMMA array GRU order does not exactly match "
        "gruId order in attributes.nc."
    )


print()
print(
    "GRU validation passed: "
    f"{expected_grus} unique GRUs "
    "match attributes.nc exactly."
)


# ============================================================
# REMOVE EXISTING MERGED FILE
# ============================================================

if output_file.exists():

    print()
    print(
        "Removing existing merged file:"
    )
    print(
        output_file
    )

    output_file.unlink()


# ============================================================
# WRITE MERGED FILE
# ============================================================

first_file = valid_files[0][2]


with nc.Dataset(
    first_file
) as source, nc.Dataset(
    output_file,
    "w",
    format="NETCDF4"
) as output:

    # --------------------------------------------------------
    # Dimensions
    # --------------------------------------------------------

    output.createDimension(
        "time",
        ntime
    )

    output.createDimension(
        "gru",
        expected_grus
    )


    # --------------------------------------------------------
    # Time
    # --------------------------------------------------------

    src_time = source.variables[
        "time"
    ]

    dst_time = output.createVariable(
        "time",
        src_time.dtype,
        ("time",)
    )


    for attr in src_time.ncattrs():

        dst_time.setncattr(
            attr,
            src_time.getncattr(
                attr
            )
        )


    dst_time[:] = (
        reference_time
    )


    # --------------------------------------------------------
    # GRU coordinate
    # --------------------------------------------------------

    dst_gru = output.createVariable(
        "gru",
        "i4",
        ("gru",)
    )


    dst_gru[:] = np.arange(
        1,
        expected_grus + 1,
        dtype=np.int32
    )


    # --------------------------------------------------------
    # GRU IDs
    # --------------------------------------------------------

    src_gruid = source.variables[
        "gruId"
    ]


    dst_gruid = output.createVariable(
        "gruId",
        src_gruid.dtype,
        ("gru",)
    )


    for attr in src_gruid.ncattrs():

        dst_gruid.setncattr(
            attr,
            src_gruid.getncattr(
                attr
            )
        )


    dst_gruid[:] = (
        expected_gru_ids
    )


    # --------------------------------------------------------
    # Runoff
    # --------------------------------------------------------

    src_runoff = source.variables[
        "averageRoutedRunoff"
    ]


    dst_runoff = output.createVariable(
        "averageRoutedRunoff",
        src_runoff.dtype,
        ("time", "gru"),
        zlib=True,
        complevel=1,
        chunksizes=(
            min(
                8760,
                ntime
            ),
            min(
                10,
                expected_grus
            )
        )
    )


    for attr in src_runoff.ncattrs():

        dst_runoff.setncattr(
            attr,
            src_runoff.getncattr(
                attr
            )
        )


    # --------------------------------------------------------
    # Copy spatial blocks
    # --------------------------------------------------------

    column_start = 0


    print()
    print("Copying runoff data...")


    for (
        start,
        end,
        file,
        ng,
        gru_ids
    ) in valid_files:

        column_end = (
            column_start
            + ng
        )


        print(
            f"  {file.name}: "
            f"columns "
            f"{column_start + 1}-"
            f"{column_end}"
        )


        with nc.Dataset(
            file
        ) as source_part:

            source_runoff = (
                source_part.variables[
                    "averageRoutedRunoff"
                ]
            )


            # Copy in time chunks to avoid loading an entire
            # large array file into memory.

            time_chunk = 8760


            for t0 in range(
                0,
                ntime,
                time_chunk
            ):

                t1 = min(
                    t0 + time_chunk,
                    ntime
                )


                dst_runoff[
                    t0:t1,
                    column_start:column_end
                ] = source_runoff[
                    t0:t1,
                    :
                ]


        column_start = (
            column_end
        )


    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    output.setncattr(
        "domain",
        domain_name
    )

    output.setncattr(
        "experiment",
        experiment_id
    )

    output.setncattr(
        "source",
        "Merged SUMMA GRU-array timestep outputs"
    )

    output.setncattr(
        "created",
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    output.setncattr(
        "number_of_input_files",
        len(
            valid_files
        )
    )


# ============================================================
# VERIFY MERGED OUTPUT
# ============================================================

print()
print("Verifying merged output...")


with nc.Dataset(
    output_file
) as ds:

    # --------------------------------------------------------
    # Dimensions
    # --------------------------------------------------------

    written_ntime = len(
        ds.dimensions["time"]
    )

    written_grus = len(
        ds.dimensions["gru"]
    )


    if written_ntime != ntime:

        raise RuntimeError(
            "Merged time dimension is incorrect.\n"
            f"Expected: {ntime}\n"
            f"Found   : {written_ntime}"
        )


    if written_grus != expected_grus:

        raise RuntimeError(
            "Merged GRU dimension is incorrect.\n"
            f"Expected: {expected_grus}\n"
            f"Found   : {written_grus}"
        )


    # --------------------------------------------------------
    # Time coordinate
    # --------------------------------------------------------

    written_time = np.asarray(
        ds.variables["time"][:]
    )


    if not np.array_equal(
        written_time,
        reference_time
    ):

        raise RuntimeError(
            "Time values changed during merge."
        )


    if np.any(
        np.diff(written_time) <= 0
    ):

        raise RuntimeError(
            "Merged time coordinate is not strictly increasing."
        )


    # --------------------------------------------------------
    # GRU IDs
    # --------------------------------------------------------

    written_ids = np.asarray(
        ds.variables[
            "gruId"
        ][:],
        dtype=np.int64
    )


    if not np.array_equal(
        written_ids,
        expected_gru_ids
    ):

        raise RuntimeError(
            "Merged gruId values or ordering are incorrect."
        )


    # --------------------------------------------------------
    # Runoff shape
    # --------------------------------------------------------

    runoff = ds.variables[
        "averageRoutedRunoff"
    ]


    runoff_shape = (
        runoff.shape
    )


    expected_shape = (
        ntime,
        expected_grus
    )


    if runoff_shape != expected_shape:

        raise RuntimeError(
            "Merged runoff variable has incorrect shape.\n"
            f"Expected: {expected_shape}\n"
            f"Found   : {runoff_shape}"
        )


    # --------------------------------------------------------
    # Sample runoff values
    # --------------------------------------------------------

    sample_indices = sorted(
        set(
            [
                0,
                ntime // 2,
                ntime - 1
            ]
        )
    )


    for index in sample_indices:

        values = np.ma.asarray(
            runoff[
                index,
                :
            ]
        )


        # Use only unmasked values.
        compressed = (
            values.compressed()
        )


        if compressed.size == 0:

            raise RuntimeError(
                "All runoff values are masked at "
                f"timestep {index}."
            )


        if not np.all(
            np.isfinite(
                compressed
            )
        ):

            raise RuntimeError(
                "Non-finite runoff values detected "
                f"at timestep {index}."
            )


        print(
            f"  runoff timestep {index}: "
            f"finite={compressed.size}/{expected_grus}, "
            f"min={compressed.min():.6e}, "
            f"max={compressed.max():.6e}"
        )


# ============================================================
# PROVENANCE
# ============================================================

log_folder = (
    summa_output
    / "_workflow_log"
)


log_folder.mkdir(
    parents=True,
    exist_ok=True
)


copyfile(
    Path(
        __file__
    ).resolve(),
    log_folder
    / Path(
        __file__
    ).name
)


log_file = (
    log_folder
    / (
        f"{datetime.now():%Y%m%d_%H%M%S}_"
        "merge_summa_array_outputs.txt"
    )
)


with log_file.open(
    "w"
) as log:

    log.write(
        f"Date: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
    )

    log.write(
        f"Domain: {domain_name}\n"
    )

    log.write(
        f"Experiment: {experiment_id}\n"
    )

    log.write(
        f"Attributes file: {attributes_file}\n"
    )

    log.write(
        f"Input files: {len(valid_files)}\n"
    )

    log.write(
        f"Time steps: {ntime}\n"
    )

    log.write(
        f"GRUs: {expected_grus}\n"
    )

    log.write(
        f"Output: {output_file}\n"
    )

    log.write(
        "GRU order matches attributes.nc: yes\n"
    )

    log.write(
        "Time axes identical across inputs: yes\n"
    )

    log.write(
        "Merged runoff sampled for finite values: yes\n"
    )


# ============================================================
# SUMMARY
# ============================================================

print()
print("============================================================")
print("SUMMA ARRAY MERGE COMPLETE")
print("============================================================")

print(f"Input files : {len(valid_files)}")
print(f"Time steps  : {ntime}")
print(f"GRUs        : {expected_grus}")
print(f"Output      : {output_file}")
print(f"Log         : {log_file}")

print()
print("Checks:")
print("  Array ranges     : PASS")
print("  Overlap check    : PASS")
print("  Time axes        : PASS")
print("  GRU uniqueness   : PASS")
print("  GRU order        : PASS")
print("  Runoff dimensions: PASS")
print("  Runoff samples   : PASS")

print("============================================================")