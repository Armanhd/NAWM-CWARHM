#!/usr/bin/env python3

"""
Prepare and validate Stage 6 model-run inputs.

Purpose
-------
This script performs the final pre-run validation required before
submitting SUMMA and mizuRoute simulations.

It:

1. Reads control_active.txt.
2. Resolves domain, experiment, executable, settings, and output paths.
3. Checks all required SUMMA and mizuRoute inputs.
4. Verifies SUMMA GRUs and mizuRoute HRUs are identical and in
   the same order.
5. Normalizes the mizuRoute v3.1.1 control file defensively.
6. Ensures the control file uses the validated parallel PIO setup:

       <pio_netcdf_type> pnetcdf !
       <pio_netcdf_format> 64bit_offset !

7. Ensures:
       <ro_calendar> standard !
       <seg_outlet> -9999 !

8. Ensures every mizuRoute setting line has a trailing "!".
9. Removes blank lines from the mizuRoute control file.
10. Ensures mizuRoute reads the merged SUMMA runoff filename.
11. Stages param.nml.default where mizuRoute v3.1.1 expects it.
12. Checks that the installed mizuRoute executable is linked against
    MPI, NetCDF, and PnetCDF libraries.
13. Records a concise preparation summary.

Important
---------
This script prepares Stage 6 but does NOT require the merged SUMMA
runoff file to exist yet. That file is generated later by the Stage 6
SUMMA-array merge step.
"""

from pathlib import Path
from shutil import copy2
import re
import subprocess

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

            left, right = stripped.split("|", 1)

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
# MODEL INSTALLATIONS
# ============================================================

summa_install = read_control(
    "install_path_summa"
)

mizu_install = read_control(
    "install_path_mizuroute"
)


if summa_install == "default":

    summa_install = (
        root_path
        / "installs"
        / "summa"
    )

else:

    summa_install = Path(
        summa_install
    )


if mizu_install == "default":

    mizu_install = (
        root_path
        / "installs"
        / "mizuRoute"
    )

else:

    mizu_install = Path(
        mizu_install
    )


# ============================================================
# SETTINGS DIRECTORIES
# ============================================================

summa_settings = read_control(
    "settings_summa_path"
)

mizu_settings = read_control(
    "settings_mizu_path"
)


if summa_settings == "default":

    summa_settings = (
        root_path
        / f"domain_{domain_name}"
        / "settings"
        / "SUMMA"
    )

else:

    summa_settings = Path(
        summa_settings
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


# ============================================================
# OUTPUT DIRECTORIES
# ============================================================

summa_output = read_control(
    "experiment_output_summa"
)

mizu_output = read_control(
    "experiment_output_mizuRoute"
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
# FILE NAMES FROM CONTROL
# ============================================================

summa_exe_name = read_control(
    "exe_name_summa"
)

mizu_exe_name = read_control(
    "exe_name_mizuroute"
)

summa_filemanager_name = read_control(
    "settings_summa_filemanager"
)

summa_attributes_name = read_control(
    "settings_summa_attributes"
)

mizu_control_name = read_control(
    "settings_mizu_control_file"
)

mizu_parameter_name = read_control(
    "settings_mizu_parameters"
)

mizu_topology_name = read_control(
    "settings_mizu_topology"
)


# ============================================================
# RESOLVED FILES
# ============================================================

summa_exe = (
    summa_install
    / "bin"
    / summa_exe_name
)

mizu_exe = (
    mizu_install
    / "route"
    / "bin"
    / mizu_exe_name
)

filemanager = (
    summa_settings
    / summa_filemanager_name
)

attributes_file = (
    summa_settings
    / summa_attributes_name
)

mizu_control = (
    mizu_settings
    / mizu_control_name
)

topology_file = (
    mizu_settings
    / mizu_topology_name
)

parameter_file = (
    mizu_settings
    / mizu_parameter_name
)

merged_runoff = (
    summa_output
    / f"{experiment_id}_timestep.nc"
)


# ============================================================
# REQUIRED FILE CHECK
# ============================================================

required_files = [
    summa_exe,
    mizu_exe,
    filemanager,
    attributes_file,
    mizu_control,
    topology_file,
    parameter_file,
]


missing_files = [
    path
    for path in required_files
    if not path.exists()
]


if missing_files:

    print()
    print("ERROR: required Stage 6 files are missing:")

    for path in missing_files:
        print(f"  {path}")

    raise SystemExit(1)


if not summa_exe.is_file():

    raise RuntimeError(
        f"SUMMA executable is invalid:\n{summa_exe}"
    )


if not mizu_exe.is_file():

    raise RuntimeError(
        f"mizuRoute executable is invalid:\n{mizu_exe}"
    )


# ============================================================
# VERIFY MIZUROUTE PARALLEL LIBRARY LINKAGE
# ============================================================

try:

    result = subprocess.run(
        [
            "ldd",
            str(mizu_exe),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

except (
    subprocess.CalledProcessError,
    FileNotFoundError,
) as exc:

    raise RuntimeError(
        "Unable to inspect mizuRoute shared-library "
        "dependencies with ldd."
    ) from exc


ldd_text = (
    result.stdout
    + result.stderr
)


required_libraries = {
    "MPI": "libmpi",
    "NetCDF": "libnetcdf",
    "PnetCDF": "libpnetcdf",
}


missing_libraries = [
    name
    for name, token
    in required_libraries.items()
    if token not in ldd_text
]


if missing_libraries:

    raise RuntimeError(
        "The installed mizuRoute executable is not linked "
        "against the complete validated parallel I/O stack.\n\n"
        f"Missing linkage: {missing_libraries}\n"
        f"Executable: {mizu_exe}\n\n"
        "Recompile mizuRoute using the nwam_parallel "
        "environment before running Stage 6."
    )


if "not found" in ldd_text:

    bad_lines = [
        line.strip()
        for line in ldd_text.splitlines()
        if "not found" in line
    ]

    raise RuntimeError(
        "mizuRoute has unresolved shared libraries:\n"
        + "\n".join(bad_lines)
    )


# ============================================================
# CHECK SUMMA ATTRIBUTES
# ============================================================

with nc.Dataset(
    attributes_file
) as ds:

    if "gru" not in ds.dimensions:

        raise RuntimeError(
            "SUMMA attributes.nc does not contain "
            "dimension 'gru'."
        )


    total_grus = len(
        ds.dimensions["gru"]
    )


    if "gruId" not in ds.variables:

        raise RuntimeError(
            "SUMMA attributes.nc does not contain "
            "variable 'gruId'."
        )


    summa_ids = np.asarray(
        ds.variables["gruId"][:],
        dtype=np.int64,
    )


if summa_ids.ndim != 1:

    raise RuntimeError(
        "SUMMA attributes gruId must be one-dimensional."
    )


if len(summa_ids) != total_grus:

    raise RuntimeError(
        "SUMMA attributes gruId length does not match "
        "the gru dimension."
    )


if len(
    np.unique(summa_ids)
) != total_grus:

    raise RuntimeError(
        "Duplicate gruId values found in "
        "SUMMA attributes.nc."
    )


# ============================================================
# CHECK MIZUROUTE TOPOLOGY
# ============================================================

with nc.Dataset(
    topology_file
) as ds:

    if "hru" not in ds.dimensions:

        raise RuntimeError(
            "mizuRoute topology.nc does not contain "
            "dimension 'hru'."
        )


    if "hruId" not in ds.variables:

        raise RuntimeError(
            "mizuRoute topology.nc does not contain "
            "variable 'hruId'."
        )


    total_routing_hrus = len(
        ds.dimensions["hru"]
    )


    topology_ids = np.asarray(
        ds.variables["hruId"][:],
        dtype=np.int64,
    )


if topology_ids.ndim != 1:

    raise RuntimeError(
        "mizuRoute topology hruId must be "
        "one-dimensional."
    )


if len(
    topology_ids
) != total_routing_hrus:

    raise RuntimeError(
        "mizuRoute topology hruId length does not "
        "match the hru dimension."
    )


if len(
    np.unique(topology_ids)
) != total_routing_hrus:

    raise RuntimeError(
        "Duplicate hruId values found in "
        "mizuRoute topology.nc."
    )


# ============================================================
# VERIFY SUMMA / MIZUROUTE SPATIAL CONSISTENCY
# ============================================================

if total_grus != total_routing_hrus:

    raise RuntimeError(
        f"SUMMA GRUs ({total_grus}) do not match "
        f"mizuRoute routing HRUs "
        f"({total_routing_hrus})."
    )


if not np.array_equal(
    summa_ids,
    topology_ids,
):

    raise RuntimeError(
        "SUMMA gruId and mizuRoute hruId are not "
        "identical and in the same order."
    )


# ============================================================
# NORMALIZE MIZUROUTE CONTROL FILE
# ============================================================

backup_file = mizu_control.with_suffix(
    mizu_control.suffix
    + ".stage6_backup"
)


# Keep the first pre-Stage-6 control file as provenance.
if not backup_file.exists():

    copy2(
        mizu_control,
        backup_file,
    )


with mizu_control.open() as contents:

    original_lines = (
        contents.readlines()
    )


settings = {}


for raw_line in original_lines:

    line = raw_line.strip()


    # mizuRoute v3.1.1 control parser can be sensitive
    # to blank lines.
    if not line:
        continue


    if line.startswith("!"):
        continue


    if not line.startswith("<"):

        raise RuntimeError(
            "Unexpected non-setting line in mizuRoute "
            "control file:\n"
            f"{raw_line.rstrip()}"
        )


    match = re.match(
        r"(<[^>]+>)\s+(.*)",
        line,
    )


    if not match:

        raise RuntimeError(
            "Unable to parse mizuRoute control line:\n"
            f"{raw_line.rstrip()}"
        )


    key = match.group(1)

    rest = match.group(2)


    value = (
        rest
        .split("!", 1)[0]
        .strip()
    )


    if not value:

        raise RuntimeError(
            "Empty value in mizuRoute control file:\n"
            f"{raw_line.rstrip()}"
        )


    # Older CWARHM control generator used <calendar>.
    # mizuRoute v3.1.1 expects <ro_calendar>.
    if key == "<calendar>":

        key = "<ro_calendar>"


    settings[key] = value


# ============================================================
# REQUIRED / VALIDATED MIZUROUTE SETTINGS
# ============================================================

settings["<ancil_dir>"] = (
    str(mizu_settings)
    + "/"
)

settings["<input_dir>"] = (
    str(summa_output)
    + "/"
)

settings["<output_dir>"] = (
    str(mizu_output)
    + "/"
)


# mizuRoute reads the spatially merged SUMMA runoff file.
settings["<fname_qsim>"] = (
    f"{experiment_id}_timestep.nc"
)


# Validated calendar setting for this workflow.
settings["<ro_calendar>"] = (
    "standard"
)


# Route the complete supplied topology.
settings["<seg_outlet>"] = (
    "-9999"
)


# Validated parallel Stage 6 PIO configuration.
settings["<pio_netcdf_type>"] = (
    "pnetcdf"
)

settings["<pio_netcdf_format>"] = (
    "64bit_offset"
)


# ============================================================
# REQUIRED CONTROL KEYS
# ============================================================

required_control_keys = [
    "<ancil_dir>",
    "<input_dir>",
    "<output_dir>",
    "<param_nml>",
    "<case_name>",
    "<sim_start>",
    "<sim_end>",
    "<route_opt>",
    "<newFileFrequency>",
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
    "<fname_qsim>",
    "<vname_qsim>",
    "<units_qsim>",
    "<dt_qsim>",
    "<dname_time>",
    "<vname_time>",
    "<dname_hruid>",
    "<vname_hruid>",
    "<ro_calendar>",
    "<is_remap>",
    "<pio_netcdf_type>",
    "<pio_netcdf_format>",
    "<doesBasinRoute>",
]


missing_control_keys = [
    key
    for key in required_control_keys
    if key not in settings
]


if missing_control_keys:

    raise RuntimeError(
        "mizuRoute control file is missing required "
        "settings:\n"
        + "\n".join(
            f"  {key}"
            for key in missing_control_keys
        )
    )


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
    (
        "! mizuRoute control file prepared "
        "by NWAM Stage 6"
    )
]


written_keys = set()


for heading, keys in sections:

    output_lines.append(
        heading
    )


    for key in keys:

        if key not in settings:
            continue


        output_lines.append(
            f"{key} {settings[key]} !"
        )


        written_keys.add(
            key
        )


# Preserve any valid optional settings not covered above.
remaining_keys = [
    key
    for key in settings
    if key not in written_keys
]


if remaining_keys:

    output_lines.append(
        "! --- ADDITIONAL SETTINGS"
    )


    for key in remaining_keys:

        output_lines.append(
            f"{key} {settings[key]} !"
        )


mizu_control.write_text(
    "\n".join(
        output_lines
    )
    + "\n"
)


# ============================================================
# VERIFY WRITTEN CONTROL FILE
# ============================================================

written_text = (
    mizu_control.read_text()
)


if "\n\n" in written_text:

    raise RuntimeError(
        "Generated mizuRoute control file contains "
        "blank lines."
    )


for line in written_text.splitlines():

    stripped = line.strip()

    if stripped.startswith("<"):

        if "!" not in stripped:

            raise RuntimeError(
                "mizuRoute setting line does not contain "
                "the required ! delimiter:\n"
                f"{line}"
            )


if (
    "<pio_netcdf_type> pnetcdf !"
    not in written_text
):

    raise RuntimeError(
        "Stage 6 failed to configure the validated "
        "PnetCDF backend."
    )


if (
    "<pio_netcdf_format> 64bit_offset !"
    not in written_text
):

    raise RuntimeError(
        "Stage 6 failed to configure the validated "
        "64bit_offset NetCDF format."
    )


if (
    "<seg_outlet> -9999 !"
    not in written_text
):

    raise RuntimeError(
        "Stage 6 failed to configure full-network routing."
    )


if (
    "<ro_calendar> standard !"
    not in written_text
):

    raise RuntimeError(
        "Stage 6 failed to configure ro_calendar."
    )


# ============================================================
# STAGE PARAMETER FILE WHERE MIZUROUTE V3.1.1 EXPECTS IT
# ============================================================

summa_output.mkdir(
    parents=True,
    exist_ok=True,
)

mizu_output.mkdir(
    parents=True,
    exist_ok=True,
)


param_destination = (
    summa_output
    / parameter_file.name
)


copy2(
    parameter_file,
    param_destination,
)


# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 60)
print("STAGE 6 PREPARATION COMPLETE")
print("=" * 60)

print(
    f"Domain              : {domain_name}"
)

print(
    f"Experiment          : {experiment_id}"
)

print(
    f"SUMMA GRUs          : {total_grus}"
)

print(
    f"mizuRoute HRUs      : {total_routing_hrus}"
)

print()

print(
    f"SUMMA executable    : {summa_exe}"
)

print(
    f"mizuRoute executable: {mizu_exe}"
)

print()

print(
    f"SUMMA settings      : {summa_settings}"
)

print(
    f"SUMMA output        : {summa_output}"
)

print()

print(
    f"mizuRoute settings  : {mizu_settings}"
)

print(
    f"mizuRoute output    : {mizu_output}"
)

print(
    f"mizuRoute control   : {mizu_control}"
)

print()

print(
    f"Expected merged file: {merged_runoff}"
)

print(
    f"param.nml staged    : {param_destination}"
)

print()

print(
    "PIO type            : pnetcdf"
)

print(
    "PIO format          : 64bit_offset"
)

print(
    "Parallel executable : verified"
)

print(
    "Production MPI tasks: configured by "
    "0_submit_stage6.sh / Slurm"
)

print("=" * 60)