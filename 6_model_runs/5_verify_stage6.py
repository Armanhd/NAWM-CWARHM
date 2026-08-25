#!/usr/bin/env python3

"""
Final Stage 6 verification for the NWAM/CWARHM workflow.

This script verifies the completed SUMMA -> mizuRoute simulation.

Checks
------
1. Reads the active domain and experiment from control_active.txt.
2. Resolves SUMMA and mizuRoute paths.
3. Reads the simulation period from mizuroute.control.
4. Verifies the merged SUMMA runoff file:
       - required dimensions and variables exist
       - time is finite and strictly increasing
       - GRU IDs are unique
       - runoff dimensions are correct
       - sampled runoff values are finite
5. Verifies mizuRoute topology:
       - required dimensions/variables exist
       - segment and HRU IDs are unique
       - merged SUMMA gruId exactly matches topology hruId
6. Verifies the mizuRoute control file uses:
       - PnetCDF
       - 64bit_offset
       - full-network routing
7. Verifies all expected yearly mizuRoute history files exist.
8. For every yearly history file verifies:
       - expected hourly record count
       - unique timestamps
       - strictly increasing timestamps
       - expected segment count
       - reach IDs match topology segId
       - routed discharge contains valid finite values
9. Verifies the mizuRoute model log contains:
       SUCCESSFUL EXECUTION
10. Writes final Stage 6 QA provenance.

Stage 6 is considered complete only if every check passes.
"""

from pathlib import Path
from datetime import datetime
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
# CONTROL READER
# ============================================================

def read_control(key):
    """
    Read one exact setting from control_active.txt.
    """

    if not CONTROL_FILE.exists():

        raise FileNotFoundError(
            "Active CWARHM control file not found:\n"
            f"{CONTROL_FILE}"
        )


    with CONTROL_FILE.open() as contents:

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


            if left.strip() == key:

                return (
                    right
                    .split("#", 1)[0]
                    .strip()
                )


    raise KeyError(
        f"Control setting not found: {key}"
    )


# ============================================================
# GENERAL SETTINGS
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
# SUMMA OUTPUT
# ============================================================

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


merged_summa = (
    summa_output
    / f"{experiment_id}_timestep.nc"
)


# ============================================================
# MIZUROUTE OUTPUT
# ============================================================

mizu_output = read_control(
    "experiment_output_mizuRoute"
)


if mizu_output == "default":

    mizu_output = (
        root_path
        / f"domain_{domain_name}"
        / "simulations"
        / experiment_id
        / "mizuRoute"
    )

else:

    mizu_output = Path(
        mizu_output
    )


# ============================================================
# MIZUROUTE SETTINGS
# ============================================================

mizu_settings = read_control(
    "settings_mizu_path"
)


if mizu_settings == "default":

    mizu_settings = (
        root_path
        / f"domain_{domain_name}"
        / "settings"
        / "mizuRoute"
    )

else:

    mizu_settings = Path(
        mizu_settings
    )


control_name = read_control(
    "settings_mizu_control_file"
)

topology_name = read_control(
    "settings_mizu_topology"
)


mizu_control = (
    mizu_settings
    / control_name
)

topology_file = (
    mizu_settings
    / topology_name
)


# ============================================================
# REQUIRED FILE CHECKS
# ============================================================

required_files = [
    merged_summa,
    mizu_control,
    topology_file,
]


missing_files = [
    path
    for path in required_files
    if not path.exists()
]


if missing_files:

    raise FileNotFoundError(
        "Required Stage 6 file(s) missing:\n"
        + "\n".join(
            f"  {path}"
            for path in missing_files
        )
    )


# ============================================================
# READ MIZUROUTE CONTROL SETTINGS
# ============================================================

mizu_settings_dict = {}


with mizu_control.open() as contents:

    for line in contents:

        stripped = line.strip()


        if (
            not stripped
            or stripped.startswith("!")
            or not stripped.startswith("<")
        ):
            continue


        if ">" not in stripped:
            continue


        key = (
            stripped
            .split(">", 1)[0]
            + ">"
        )


        value = (
            stripped
            .split(">", 1)[1]
            .split("!", 1)[0]
            .strip()
        )


        mizu_settings_dict[key] = value


# ============================================================
# SIMULATION PERIOD
# ============================================================

sim_start = mizu_settings_dict.get(
    "<sim_start>"
)

sim_end = mizu_settings_dict.get(
    "<sim_end>"
)


if sim_start is None or sim_end is None:

    raise RuntimeError(
        "Unable to determine simulation period "
        "from mizuRoute control file."
    )


start_datetime = datetime.strptime(
    sim_start,
    "%Y-%m-%d %H:%M",
)

end_datetime = datetime.strptime(
    sim_end,
    "%Y-%m-%d %H:%M",
)


if end_datetime < start_datetime:

    raise RuntimeError(
        "mizuRoute simulation end occurs before start."
    )


start_year = (
    start_datetime.year
)

end_year = (
    end_datetime.year
)


expected_years = list(
    range(
        start_year,
        end_year + 1,
    )
)


# ============================================================
# VERIFY MIZUROUTE CONTROL CONFIGURATION
# ============================================================

required_control_values = {

    "<pio_netcdf_type>":
        "pnetcdf",

    "<pio_netcdf_format>":
        "64bit_offset",

    "<seg_outlet>":
        "-9999",

    "<ro_calendar>":
        "standard",
}


for key, expected_value in required_control_values.items():

    actual_value = (
        mizu_settings_dict.get(
            key
        )
    )


    if actual_value != expected_value:

        raise RuntimeError(
            "Unexpected mizuRoute control setting.\n\n"
            f"Setting : {key}\n"
            f"Expected: {expected_value}\n"
            f"Found   : {actual_value}"
        )


# ============================================================
# INITIAL REPORT
# ============================================================

print()
print("=" * 70)
print("STAGE 6 FINAL VERIFICATION")
print("=" * 70)

print(
    f"Domain       : {domain_name}"
)

print(
    f"Experiment   : {experiment_id}"
)

print(
    f"Simulation   : {sim_start} to {sim_end}"
)

print(
    f"SUMMA output : {summa_output}"
)

print(
    f"mizu output  : {mizu_output}"
)

print()
print(
    "mizuRoute I/O:"
)

print(
    "  backend : pnetcdf"
)

print(
    "  format  : 64bit_offset"
)


# ============================================================
# VERIFY MERGED SUMMA FILE
# ============================================================

print()
print("SUMMA merged runoff:")


with nc.Dataset(
    merged_summa
) as ds:

    required_dimensions = {
        "time",
        "gru",
    }


    missing_dimensions = (
        required_dimensions
        - set(ds.dimensions)
    )


    if missing_dimensions:

        raise RuntimeError(
            "Merged SUMMA file is missing dimensions:\n"
            f"{sorted(missing_dimensions)}"
        )


    required_variables = {
        "time",
        "gruId",
        "averageRoutedRunoff",
    }


    missing_variables = (
        required_variables
        - set(ds.variables)
    )


    if missing_variables:

        raise RuntimeError(
            "Merged SUMMA file is missing variables:\n"
            f"{sorted(missing_variables)}"
        )


    ntime = len(
        ds.dimensions["time"]
    )

    ngrus = len(
        ds.dimensions["gru"]
    )


    summa_time = np.asarray(
        ds.variables["time"][:]
    )


    if summa_time.ndim != 1:

        raise RuntimeError(
            "SUMMA time coordinate is not one-dimensional."
        )


    if len(summa_time) != ntime:

        raise RuntimeError(
            "SUMMA time coordinate length does not "
            "match the time dimension."
        )


    if not np.all(
        np.isfinite(
            summa_time
        )
    ):

        raise RuntimeError(
            "SUMMA time coordinate contains "
            "non-finite values."
        )


    if np.any(
        np.diff(summa_time) <= 0
    ):

        raise RuntimeError(
            "SUMMA time coordinate is not "
            "strictly increasing."
        )


    summa_ids = np.asarray(
        ds.variables["gruId"][:],
        dtype=np.int64,
    )


    if summa_ids.ndim != 1:

        raise RuntimeError(
            "Merged SUMMA gruId must be one-dimensional."
        )


    if len(summa_ids) != ngrus:

        raise RuntimeError(
            "Merged SUMMA gruId length does not "
            "match the gru dimension."
        )


    if len(
        np.unique(summa_ids)
    ) != ngrus:

        raise RuntimeError(
            "Duplicate gruId values found in "
            "merged SUMMA output."
        )


    runoff = (
        ds.variables[
            "averageRoutedRunoff"
        ]
    )


    expected_runoff_shape = (
        ntime,
        ngrus,
    )


    if runoff.shape != expected_runoff_shape:

        raise RuntimeError(
            "Merged SUMMA runoff has incorrect shape.\n"
            f"Expected: {expected_runoff_shape}\n"
            f"Found   : {runoff.shape}"
        )


    sample_indices = sorted(
        set(
            [
                0,
                ntime // 2,
                ntime - 1,
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


        compressed = (
            values.compressed()
        )


        if compressed.size == 0:

            raise RuntimeError(
                "All SUMMA runoff values are masked "
                f"at timestep {index}."
            )


        if not np.all(
            np.isfinite(
                compressed
            )
        ):

            raise RuntimeError(
                "SUMMA runoff contains non-finite "
                f"values at timestep {index}."
            )


        print(
            f"  timestep {index}: "
            f"finite={compressed.size}/{ngrus}, "
            f"min={compressed.min():.6e}, "
            f"max={compressed.max():.6e}"
        )


print(
    f"  time : {ntime}"
)

print(
    f"  GRUs : {ngrus}"
)


# ============================================================
# VERIFY TOPOLOGY
# ============================================================

with nc.Dataset(
    topology_file
) as ds:

    required_dimensions = {
        "seg",
        "hru",
    }


    missing_dimensions = (
        required_dimensions
        - set(ds.dimensions)
    )


    if missing_dimensions:

        raise RuntimeError(
            "mizuRoute topology is missing dimensions:\n"
            f"{sorted(missing_dimensions)}"
        )


    required_variables = {
        "segId",
        "hruId",
    }


    missing_variables = (
        required_variables
        - set(ds.variables)
    )


    if missing_variables:

        raise RuntimeError(
            "mizuRoute topology is missing variables:\n"
            f"{sorted(missing_variables)}"
        )


    nseg = len(
        ds.dimensions["seg"]
    )

    nhru = len(
        ds.dimensions["hru"]
    )


    topology_seg_ids = np.asarray(
        ds.variables["segId"][:],
        dtype=np.int64,
    )


    topology_hru_ids = np.asarray(
        ds.variables["hruId"][:],
        dtype=np.int64,
    )


if len(
    np.unique(
        topology_seg_ids
    )
) != nseg:

    raise RuntimeError(
        "Duplicate segId values found in topology.nc."
    )


if len(
    np.unique(
        topology_hru_ids
    )
) != nhru:

    raise RuntimeError(
        "Duplicate hruId values found in topology.nc."
    )


if ngrus != nhru:

    raise RuntimeError(
        "Merged SUMMA GRU count does not match "
        "mizuRoute topology HRU count.\n"
        f"SUMMA GRUs : {ngrus}\n"
        f"mizu HRUs  : {nhru}"
    )


if not np.array_equal(
    summa_ids,
    topology_hru_ids,
):

    raise RuntimeError(
        "Merged SUMMA gruId does not exactly match "
        "mizuRoute topology hruId."
    )


print()
print("Topology:")

print(
    f"  segments : {nseg}"
)

print(
    f"  HRUs     : {nhru}"
)

print(
    "  GRU/HRU IDs : MATCH"
)


# ============================================================
# DISCOVER MIZUROUTE YEARLY FILES
# ============================================================

files = sorted(
    mizu_output.glob(
        f"{experiment_id}.h.*.nc"
    ),
    key=lambda path: int(
        path.stem.split(".")[-1]
    ),
)


print()
print("mizuRoute yearly files:")

print(
    f"  found    : {len(files)}"
)

print(
    f"  expected : {len(expected_years)}"
)


if len(files) != len(
    expected_years
):

    found_years = [
        path.stem.split(".")[-1]
        for path in files
    ]


    raise RuntimeError(
        "Incorrect number of mizuRoute yearly files.\n"
        f"Expected years: {expected_years[0]}-"
        f"{expected_years[-1]}\n"
        f"Found years   : {found_years}"
    )


# ============================================================
# VERIFY EACH MIZUROUTE YEAR
# ============================================================

all_years_ok = True


for year in expected_years:

    file = (
        mizu_output
        / f"{experiment_id}.h.{year}.nc"
    )


    if not file.exists():

        print(
            year,
            "MISSING"
        )

        all_years_ok = False

        continue


    expected_hours = (
        8784
        if calendar.isleap(year)
        else 8760
    )


    with nc.Dataset(
        file
    ) as ds:

        required_dimensions = {
            "time",
            "seg",
        }


        missing_dimensions = (
            required_dimensions
            - set(ds.dimensions)
        )


        if missing_dimensions:

            raise RuntimeError(
                f"{file.name} is missing dimensions: "
                f"{sorted(missing_dimensions)}"
            )


        required_variables = {
            "time",
            "reachID",
            "KWTroutedRunoff",
        }


        missing_variables = (
            required_variables
            - set(ds.variables)
        )


        if missing_variables:

            raise RuntimeError(
                f"{file.name} is missing variables: "
                f"{sorted(missing_variables)}"
            )


        if len(
            ds.dimensions["seg"]
        ) != nseg:

            raise RuntimeError(
                f"{file.name}: incorrect segment count.\n"
                f"Expected: {nseg}\n"
                f"Found   : "
                f"{len(ds.dimensions['seg'])}"
            )


        reach_ids = np.asarray(
            ds.variables["reachID"][:],
            dtype=np.int64,
        )


        if not np.array_equal(
            reach_ids,
            topology_seg_ids,
        ):

            raise RuntimeError(
                f"{file.name}: reachID does not exactly "
                "match topology segId."
            )


        time = np.asarray(
            ds.variables["time"][:]
        )


        ntime_year = len(
            time
        )


        unique_times = len(
            np.unique(
                time
            )
        )


        non_increasing = int(
            np.sum(
                np.diff(time) <= 0
            )
        )


        finite_time = bool(
            np.all(
                np.isfinite(
                    time
                )
            )
        )


        routed = np.ma.asarray(
            ds.variables[
                "KWTroutedRunoff"
            ][:]
        )


        expected_routed_shape = (
            expected_hours,
            nseg,
        )


        routed_shape_ok = (
            routed.shape
            == expected_routed_shape
        )


        routed_values = (
            routed.compressed()
        )


        if routed_values.size == 0:

            finite_routed = False

        else:

            finite_routed = bool(
                np.all(
                    np.isfinite(
                        routed_values
                    )
                )
            )


        ok = (
            ntime_year == expected_hours
            and unique_times == expected_hours
            and non_increasing == 0
            and finite_time
            and routed_shape_ok
            and finite_routed
        )


        if not ok:

            all_years_ok = False


        print(
            year,
            f"records={ntime_year}",
            f"expected={expected_hours}",
            f"unique={unique_times}",
            f"noninc={non_increasing}",
            f"finite_time={finite_time}",
            f"finite_Q={finite_routed}",
            "OK" if ok else "FAIL",
        )


# ============================================================
# VERIFY MIZUROUTE MODEL LOG
# ============================================================

model_log = (
    mizu_output
    / "mizuRoute_logs"
    / "mizuRoute_log.txt"
)


if not model_log.exists():

    alternative_log = (
        mizu_output
        / "mizuRoute_log.txt"
    )


    if alternative_log.exists():

        model_log = (
            alternative_log
        )


if not model_log.exists():

    raise RuntimeError(
        "mizuRoute log file was not found."
    )


model_log_text = (
    model_log.read_text(
        errors="ignore"
    )
)


if (
    "SUCCESSFUL EXECUTION"
    not in model_log_text
):

    raise RuntimeError(
        "mizuRoute did not report "
        "SUCCESSFUL EXECUTION."
    )


print()
print(
    f"mizuRoute log: {model_log}"
)

print(
    "  SUCCESSFUL EXECUTION : FOUND"
)


# ============================================================
# FINAL RESULT
# ============================================================

final_pass = (
    all_years_ok
)


# ============================================================
# PROVENANCE
# ============================================================

workflow_log = (
    mizu_output
    / "_workflow_log"
)


workflow_log.mkdir(
    parents=True,
    exist_ok=True,
)


timestamp = datetime.now()


qa_log = (
    workflow_log
    / (
        f"{timestamp:%Y%m%d_%H%M%S}_"
        "stage6_final_verification.txt"
    )
)


with qa_log.open(
    "w"
) as log:

    log.write(
        "NWAM Stage 6 final verification\n"
    )

    log.write(
        f"Date: "
        f"{timestamp:%Y-%m-%d %H:%M:%S}\n"
    )

    log.write(
        f"Domain: {domain_name}\n"
    )

    log.write(
        f"Experiment: {experiment_id}\n"
    )

    log.write(
        f"Simulation: "
        f"{sim_start} to {sim_end}\n"
    )

    log.write(
        f"SUMMA merged file: "
        f"{merged_summa}\n"
    )

    log.write(
        f"SUMMA time steps: {ntime}\n"
    )

    log.write(
        f"SUMMA GRUs: {ngrus}\n"
    )

    log.write(
        f"mizuRoute segments: {nseg}\n"
    )

    log.write(
        f"mizuRoute HRUs: {nhru}\n"
    )

    log.write(
        f"Expected yearly files: "
        f"{len(expected_years)}\n"
    )

    log.write(
        f"Found yearly files: "
        f"{len(files)}\n"
    )

    log.write(
        "PIO backend: pnetcdf\n"
    )

    log.write(
        "PIO format: 64bit_offset\n"
    )

    log.write(
        f"mizuRoute log: {model_log}\n"
    )

    log.write(
        f"Final QA: "
        f"{'PASS' if final_pass else 'FAIL'}\n"
    )


# Copy final verifier for provenance.

shutil.copyfile(
    Path(__file__).resolve(),
    workflow_log
    / Path(__file__).name,
)


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 70)


if final_pass:

    print(
        "ALL STAGE 6 CHECKS PASSED"
    )

else:

    print(
        "STAGE 6 VERIFICATION FAILED"
    )


print(
    f"QA log: {qa_log}"
)

print("=" * 70)


if not final_pass:

    raise SystemExit(1)