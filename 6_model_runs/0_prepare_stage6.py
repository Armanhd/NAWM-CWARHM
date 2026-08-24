#!/usr/bin/env python3

"""
Prepare and validate Stage 6 model-run inputs.

This script:
  - reads control_active.txt
  - resolves SUMMA/mizuRoute paths
  - checks the required executables and model-input files
  - normalizes the Stage-5 mizuRoute control file for mizuRoute v3.1.1
  - removes blank lines from the mizuRoute control file
  - ensures every mizuRoute setting line contains a trailing "!"
  - converts <calendar> to <ro_calendar>
  - uses <seg_outlet> -9999 to route the complete network
  - forces the currently validated serial NetCDF PIO backend
  - ensures mizuRoute reads the merged SUMMA runoff file
  - copies param.nml.default into the runoff input directory because
    mizuRoute v3.1.1 reads param_nml relative to input_dir
  - verifies SUMMA GRU count against mizuRoute topology
"""

from pathlib import Path
from shutil import copy2
import re

import netCDF4 as nc
import numpy as np


# ============================================================
# PATHS
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM = SCRIPT_DIR.parent
CONTROL_FILE = CWARHM / "0_control_files" / "control_active.txt"


# ============================================================
# CONTROL READER
# ============================================================

def read_control(key):

    with CONTROL_FILE.open() as f:
        for line in f:

            line = line.strip()

            if not line or line.startswith("#") or "|" not in line:
                continue

            left, right = line.split("|", 1)

            if left.strip() == key:
                return right.split("#", 1)[0].strip()

    raise KeyError(f"Control setting not found: {key}")


# ============================================================
# SETTINGS
# ============================================================

root = Path(read_control("root_path"))
domain = read_control("domain_name")
experiment = read_control("experiment_id")

summa_install = read_control("install_path_summa")
mizu_install = read_control("install_path_mizuroute")

summa_settings = read_control("settings_summa_path")
mizu_settings = read_control("settings_mizu_path")

summa_output = read_control("experiment_output_summa")
mizu_output = read_control("experiment_output_mizuRoute")

summa_exe_name = read_control("exe_name_summa")
mizu_exe_name = read_control("exe_name_mizuroute")

summa_filemanager_name = read_control("settings_summa_filemanager")
mizu_control_name = read_control("settings_mizu_control_file")
summa_attributes_name = read_control("settings_summa_attributes")


# ============================================================
# DEFAULT PATHS
# ============================================================

if summa_install == "default":
    summa_install = root / "installs" / "summa"
else:
    summa_install = Path(summa_install)

if mizu_install == "default":
    mizu_install = root / "installs" / "mizuRoute"
else:
    mizu_install = Path(mizu_install)

if summa_settings == "default":
    summa_settings = root / f"domain_{domain}" / "settings" / "SUMMA"
else:
    summa_settings = Path(summa_settings)

if mizu_settings == "default":
    mizu_settings = root / f"domain_{domain}" / "settings" / "mizuRoute"
else:
    mizu_settings = Path(mizu_settings)

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


# ============================================================
# FILES
# ============================================================

summa_exe = summa_install / "bin" / summa_exe_name

mizu_exe = (
    mizu_install
    / "route"
    / "bin"
    / mizu_exe_name
)

filemanager = summa_settings / summa_filemanager_name
attributes = summa_settings / summa_attributes_name

mizu_control = mizu_settings / mizu_control_name
topology = mizu_settings / "topology.nc"

param_file = mizu_settings / "param.nml.default"

merged_runoff = summa_output / f"{experiment}_timestep.nc"


# ============================================================
# REQUIRED FILE CHECK
# ============================================================

required = [
    summa_exe,
    mizu_exe,
    filemanager,
    attributes,
    mizu_control,
    topology,
    param_file,
]

missing = [p for p in required if not p.exists()]

if missing:
    print("ERROR: required Stage 6 files are missing:")
    for p in missing:
        print("  ", p)
    raise SystemExit(1)


# ============================================================
# CHECK SUMMA / TOPOLOGY COUNTS AND IDS
# ============================================================

with nc.Dataset(attributes) as ds:

    if "gru" not in ds.dimensions:
        raise RuntimeError(
            "SUMMA attributes.nc does not contain dimension 'gru'."
        )

    total_grus = len(ds.dimensions["gru"])

    if "gruId" in ds.variables:
        summa_ids = np.asarray(
            ds.variables["gruId"][:],
            dtype=np.int64,
        )
    else:
        summa_ids = None


with nc.Dataset(topology) as ds:

    if "hru" not in ds.dimensions:
        raise RuntimeError(
            "mizuRoute topology.nc does not contain dimension 'hru'."
        )

    total_hru = len(ds.dimensions["hru"])

    topology_ids = np.asarray(
        ds.variables["hruId"][:],
        dtype=np.int64,
    )


if total_grus != total_hru:
    raise RuntimeError(
        f"SUMMA GRUs ({total_grus}) != "
        f"mizuRoute routing HRUs ({total_hru})."
    )

if summa_ids is not None:

    if not np.array_equal(summa_ids, topology_ids):
        raise RuntimeError(
            "SUMMA gruId and mizuRoute hruId are not identical "
            "and in the same order."
        )


# ============================================================
# NORMALIZE MIZUROUTE CONTROL FILE
# ============================================================

backup = mizu_control.with_suffix(
    mizu_control.suffix + ".stage6_backup"
)

if not backup.exists():
    copy2(mizu_control, backup)


with mizu_control.open() as f:
    original_lines = f.readlines()


settings = {}
comments = []

for raw in original_lines:

    line = raw.strip()

    # mizuRoute v3.1.1 parser does not tolerate blank lines well.
    if not line:
        continue

    if line.startswith("!"):
        comments.append(line)
        continue

    if line.startswith("<"):

        # Find keyword.
        match = re.match(r"(<[^>]+>)\s+(.*)", line)

        if not match:
            raise RuntimeError(
                f"Unable to parse mizuRoute control line:\n{raw}"
            )

        key = match.group(1)
        rest = match.group(2)

        value = rest.split("!", 1)[0].strip()

        if key == "<calendar>":
            key = "<ro_calendar>"

        settings[key] = value


# ============================================================
# REQUIRED/VALIDATED MIZUROUTE SETTINGS
# ============================================================

settings["<ancil_dir>"] = str(mizu_settings) + "/"
settings["<input_dir>"] = str(summa_output) + "/"
settings["<output_dir>"] = str(mizu_output) + "/"

settings["<fname_qsim>"] = f"{experiment}_timestep.nc"

settings["<ro_calendar>"] = "standard"

# Negative means route the complete supplied network.
settings["<seg_outlet>"] = "-9999"

# Validated safe output configuration for the current build.
settings["<pio_netcdf_type>"] = "netcdf"
settings["<pio_netcdf_format>"] = "64bit_offset"


# ============================================================
# WRITE CONTROL FILE IN STABLE ORDER
# ============================================================

sections = [
    (
        "! --- DEFINE DIRECTORIES",
        [
            "<ancil_dir>",
            "<input_dir>",
            "<output_dir>",
        ],
    ),
    (
        "! --- NAMELIST FILENAME",
        [
            "<param_nml>",
        ],
    ),
    (
        "! --- DEFINE SIMULATION CONTROLS",
        [
            "<case_name>",
            "<sim_start>",
            "<sim_end>",
            "<route_opt>",
            "<newFileFrequency>",
        ],
    ),
    (
        "! --- DEFINE TOPOLOGY FILE",
        [
            "<fname_ntopOld>",
            "<dname_sseg>",
            "<dname_nhru>",
            "<seg_outlet>",
            "<varname_area>",
            "<varname_length>",
            "<varname_slope>",
            "<varname_HRUid>",
            "<varname_hruSegId>",
            "<varname_segId>",
            "<varname_downSegId>",
        ],
    ),
    (
        "! --- DEFINE RUNOFF FILE",
        [
            "<fname_qsim>",
            "<vname_qsim>",
            "<units_qsim>",
            "<dt_qsim>",
            "<dname_time>",
            "<vname_time>",
            "<dname_hruid>",
            "<vname_hruid>",
            "<ro_calendar>",
        ],
    ),
    (
        "! --- DEFINE RUNOFF MAPPING FILE",
        [
            "<is_remap>",
        ],
    ),
    (
        "! --- OUTPUT I/O",
        [
            "<pio_netcdf_type>",
            "<pio_netcdf_format>",
        ],
    ),
    (
        "! --- MISCELLANEOUS",
        [
            "<doesBasinRoute>",
        ],
    ),
]


output_lines = [
    "! mizuRoute control file prepared by NWAM Stage 6"
]

written = set()

for heading, keys in sections:

    output_lines.append(heading)

    for key in keys:

        if key in settings:

            output_lines.append(
                f"{key} {settings[key]} !"
            )

            written.add(key)


# Keep any additional valid settings not covered above.
remaining = [
    key
    for key in settings
    if key not in written
]

if remaining:

    output_lines.append("! --- ADDITIONAL SETTINGS")

    for key in remaining:
        output_lines.append(
            f"{key} {settings[key]} !"
        )


mizu_control.write_text(
    "\n".join(output_lines) + "\n"
)


# ============================================================
# STAGE PARAMETER FILE WHERE V3.1.1 EXPECTS IT
# ============================================================

summa_output.mkdir(
    parents=True,
    exist_ok=True,
)

mizu_output.mkdir(
    parents=True,
    exist_ok=True,
)

param_destination = summa_output / param_file.name

copy2(
    param_file,
    param_destination,
)


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 60)
print("STAGE 6 PREPARATION COMPLETE")
print("=" * 60)

print("Domain             :", domain)
print("Experiment         :", experiment)
print("SUMMA GRUs         :", total_grus)
print("mizuRoute HRUs     :", total_hru)

print()
print("SUMMA executable   :", summa_exe)
print("mizuRoute executable:", mizu_exe)

print()
print("SUMMA settings     :", summa_settings)
print("SUMMA output       :", summa_output)

print()
print("mizuRoute settings :", mizu_settings)
print("mizuRoute output   :", mizu_output)
print("mizuRoute control  :", mizu_control)

print()
print("param.nml staged   :", param_destination)

print()
print("PIO type           : netcdf")
print("mizuRoute MPI tasks: 1 required for current build")

print("=" * 60)