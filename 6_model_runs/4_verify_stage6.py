#!/usr/bin/env python3

from pathlib import Path
from datetime import datetime
import calendar

import netCDF4 as nc
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM = SCRIPT_DIR.parent
CONTROL_FILE = CWARHM / "0_control_files" / "control_active.txt"


def read_control(key):

    with CONTROL_FILE.open() as f:

        for line in f:

            line = line.strip()

            if not line or line.startswith("#") or "|" not in line:
                continue

            left, right = line.split("|", 1)

            if left.strip() == key:
                return right.split("#", 1)[0].strip()

    raise KeyError(key)


root = Path(read_control("root_path"))
domain = read_control("domain_name")
experiment = read_control("experiment_id")


summa_output = read_control("experiment_output_summa")

if summa_output == "default":
    summa_output = (
        root
        / f"domain_{domain}"
        / "simulations"
        / experiment
        / "SUMMA"
    )
else:
    summa_output = Path(summa_output)


mizu_output = read_control("experiment_output_mizuRoute")

if mizu_output == "default":
    mizu_output = (
        root
        / f"domain_{domain}"
        / "simulations"
        / experiment
        / "mizuRoute"
    )
else:
    mizu_output = Path(mizu_output)


mizu_settings = read_control("settings_mizu_path")

if mizu_settings == "default":
    mizu_settings = (
        root
        / f"domain_{domain}"
        / "settings"
        / "mizuRoute"
    )
else:
    mizu_settings = Path(mizu_settings)


control_name = read_control(
    "settings_mizu_control_file"
)

mizu_control = mizu_settings / control_name
topology = mizu_settings / "topology.nc"

merged_summa = (
    summa_output
    / f"{experiment}_timestep.nc"
)


# ============================================================
# READ SIMULATION PERIOD
# ============================================================

sim_start = None
sim_end = None

with mizu_control.open() as f:

    for line in f:

        if line.startswith("<sim_start>"):
            sim_start = line.split(">", 1)[1].split("!", 1)[0].strip()

        if line.startswith("<sim_end>"):
            sim_end = line.split(">", 1)[1].split("!", 1)[0].strip()


if sim_start is None or sim_end is None:
    raise RuntimeError(
        "Unable to determine simulation period from mizuRoute control."
    )


start_year = int(sim_start[:4])
end_year = int(sim_end[:4])

expected_years = list(
    range(start_year, end_year + 1)
)


# ============================================================
# SUMMA MERGED FILE
# ============================================================

print()
print("=" * 70)
print("STAGE 6 FINAL VERIFICATION")
print("=" * 70)

print("Domain     :", domain)
print("Experiment :", experiment)

print()
print("SUMMA merged runoff:")

if not merged_summa.exists():
    raise RuntimeError(
        f"Missing merged SUMMA file:\n{merged_summa}"
    )


with nc.Dataset(merged_summa) as ds:

    ntime = len(ds.dimensions["time"])
    ngrus = len(ds.dimensions["gru"])

    runoff = ds.variables["averageRoutedRunoff"]

    print("  time :", ntime)
    print("  GRUs :", ngrus)

    for index in [0, ntime // 2, ntime - 1]:

        x = np.asarray(
            runoff[index, :]
        )

        if not np.all(np.isfinite(x)):
            raise RuntimeError(
                f"SUMMA runoff contains non-finite values "
                f"at timestep {index}."
            )


# ============================================================
# TOPOLOGY
# ============================================================

with nc.Dataset(topology) as ds:

    nseg = len(ds.dimensions["seg"])
    nhru = len(ds.dimensions["hru"])

    topology_ids = np.asarray(
        ds.variables["hruId"][:],
        dtype=np.int64,
    )


with nc.Dataset(merged_summa) as ds:

    summa_ids = np.asarray(
        ds.variables["gruId"][:],
        dtype=np.int64,
    )


if not np.array_equal(
    summa_ids,
    topology_ids
):
    raise RuntimeError(
        "Merged SUMMA gruId does not match topology hruId."
    )


print()
print("Topology:")
print("  segments :", nseg)
print("  HRUs     :", nhru)
print("  IDs      : MATCH")


# ============================================================
# MIZUROUTE OUTPUT
# ============================================================

files = sorted(
    mizu_output.glob(
        f"{experiment}.h.*.nc"
    )
)

print()
print("mizuRoute yearly files:")
print("  found    :", len(files))
print("  expected :", len(expected_years))


if len(files) != len(expected_years):
    raise RuntimeError(
        "Incorrect number of mizuRoute yearly files."
    )


all_ok = True


for year in expected_years:

    f = (
        mizu_output
        / f"{experiment}.h.{year}.nc"
    )

    if not f.exists():

        print(year, "MISSING")

        all_ok = False
        continue


    expected_hours = (
        8784
        if calendar.isleap(year)
        else 8760
    )


    with nc.Dataset(f) as ds:

        if len(ds.dimensions["seg"]) != nseg:
            raise RuntimeError(
                f"{f.name}: incorrect segment count."
            )

        t = np.asarray(
            ds.variables["time"][:]
        )

        ntime_year = len(t)
        unique = len(np.unique(t))
        noninc = int(
            np.sum(np.diff(t) <= 0)
        )


        routed = np.ma.asarray(
            ds.variables["KWTroutedRunoff"][:]
        )

        routed_values = routed.compressed()

        finite = np.all(
            np.isfinite(routed_values)
        )


        ok = (
            ntime_year == expected_hours
            and unique == expected_hours
            and noninc == 0
            and finite
        )


        if not ok:
            all_ok = False


        print(
            year,
            f"records={ntime_year}",
            f"expected={expected_hours}",
            f"unique={unique}",
            f"noninc={noninc}",
            f"finite={finite}",
            "OK" if ok else "FAIL"
        )


# ============================================================
# MODEL LOG
# ============================================================

model_log = (
    mizu_output
    / "mizuRoute_logs"
    / "mizuRoute_log.txt"
)

if not model_log.exists():

    # Support direct final-run layout too.
    alternative = (
        mizu_output
        / "mizuRoute_log.txt"
    )

    if alternative.exists():
        model_log = alternative


if not model_log.exists():
    raise RuntimeError(
        "mizuRoute log file was not found."
    )


if "SUCCESSFUL EXECUTION" not in model_log.read_text(
    errors="ignore"
):
    raise RuntimeError(
        "mizuRoute did not report SUCCESSFUL EXECUTION."
    )


# ============================================================
# FINAL RESULT
# ============================================================

print()
print("=" * 70)

if all_ok:
    print("ALL STAGE 6 CHECKS PASSED")
else:
    print("STAGE 6 VERIFICATION FAILED")
    raise SystemExit(1)

print("=" * 70)