#!/usr/bin/env python3
# coding: utf-8

"""
Create mizuroute.control for a selected NWAM/CWARHM domain.

Purpose
-------
Create the mizuRoute runtime control file using an explicitly
specified domain control file.

The generated control defines:

  - ancillary/settings directory
  - SUMMA runoff input directory
  - mizuRoute output directory
  - routing parameter namelist
  - simulation period
  - routing option
  - topology file and variable names
  - SUMMA runoff file and variable names
  - optional SUMMA-to-mizuRoute remapping
  - within-basin routing
  - NetCDF/PIO output configuration

IMPORTANT
---------
This script does NOT read, create, or modify control_active.txt.

Usage
-----
python 1_create_control_file.py \
/path/to/control_DOMAIN.txt
"""


import sys
from pathlib import Path
from shutil import copy2
from datetime import datetime


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_create_control_file.py "
        "/path/to/control_DOMAIN.txt"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).resolve()


if not CONTROL_FILE.exists():

    raise FileNotFoundError(
        "Control file not found:\n"
        f"{CONTROL_FILE}"
    )


if not CONTROL_FILE.is_file():

    raise RuntimeError(
        "Control-file path is not a file:\n"
        f"{CONTROL_FILE}"
    )


# ============================================================
# PROJECT PATHS
# ============================================================

SCRIPT_DIR = Path(
    __file__
).resolve().parent


# Script location:
#
# CWARHM_multibasin/
#   5_model_input/
#     mizuRoute/
#       1d_control_file/
#         1_create_control_file.py

CWARHM_ROOT = (
    SCRIPT_DIR.parents[2]
)


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(
    file,
    setting
):
    """
    Read one control setting using exact key matching.
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


def make_default_path(
    suffix
):
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


def resolve_path(
    setting,
    default_suffix
):
    """
    Resolve a control-file path setting.
    """

    value = read_from_control(
        CONTROL_FILE,
        setting
    )

    if value == "default":

        return make_default_path(
            default_suffix
        )

    return Path(
        value
    )


# ============================================================
# DOMAIN / EXPERIMENT
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


experiment_id = read_from_control(
    CONTROL_FILE,
    "experiment_id"
)


# ============================================================
# MIZUROUTE SETTINGS DIRECTORY
# ============================================================

control_path = resolve_path(
    "settings_mizu_path",
    "settings/mizuRoute"
)


control_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_control_file"
)


control_path.mkdir(
    parents=True,
    exist_ok=True
)


control_output = (
    control_path
    / control_name
)


# mizuRoute ancillary directory.

path_to_settings = (
    control_path
)


# ============================================================
# SUMMA OUTPUT / MIZUROUTE INPUT DIRECTORY
# ============================================================

summa_output_setting = read_from_control(
    CONTROL_FILE,
    "experiment_output_summa"
)


if summa_output_setting == "default":

    path_to_input = make_default_path(
        f"simulations/{experiment_id}/SUMMA"
    )

else:

    path_to_input = Path(
        summa_output_setting
    )


# SUMMA output may not exist yet at Stage 5, so creating the
# directory is appropriate.

path_to_input.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# MIZUROUTE OUTPUT DIRECTORY
# ============================================================

mizu_output_setting = read_from_control(
    CONTROL_FILE,
    "experiment_output_mizuRoute"
)


if mizu_output_setting == "default":

    path_to_output = make_default_path(
        f"simulations/{experiment_id}/mizuRoute"
    )

else:

    path_to_output = Path(
        mizu_output_setting
    )


path_to_output.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# PARAMETER NAMELIST
# ============================================================

parameter_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_parameters"
)


parameter_file = (
    path_to_settings
    / parameter_name
)


if not parameter_file.exists():

    raise FileNotFoundError(
        "mizuRoute parameter namelist not found:\n"
        f"{parameter_file}\n\n"
        "Run the mizuRoute base-settings copy step first."
    )


# ------------------------------------------------------------
# Stage parameter file in SUMMA-output/input directory
# ------------------------------------------------------------
#
# Current mizuRoute configuration uses:
#
#   <input_dir> .../SUMMA/
#   <param_nml> param.nml.default
#
# so retain the tested workflow behavior and copy the namelist
# there as well.

parameter_input_file = (
    path_to_input
    / parameter_name
)


copy2(
    parameter_file,
    parameter_input_file
)


# ============================================================
# SIMULATION PERIOD
# ============================================================

sim_start = read_from_control(
    CONTROL_FILE,
    "experiment_time_start"
)


sim_end = read_from_control(
    CONTROL_FILE,
    "experiment_time_end"
)


forcing_raw_time = read_from_control(
    CONTROL_FILE,
    "forcing_raw_time"
)


try:

    start_year_text, end_year_text = [
        item.strip()
        for item in forcing_raw_time.split(
            ",",
            1
        )
    ]

    start_year = int(
        start_year_text
    )

    end_year = int(
        end_year_text
    )

except Exception as exc:

    raise ValueError(
        "forcing_raw_time must have format:\n"
        "START_YEAR,END_YEAR\n"
        "for example:\n"
        "1950,2019"
    ) from exc


if start_year > end_year:

    raise ValueError(
        "forcing_raw_time start year is greater "
        "than end year."
    )


if sim_start == "default":

    sim_start = (
        f"{start_year}-01-01 00:00"
    )


if sim_end == "default":

    sim_end = (
        f"{end_year}-12-31 23:00"
    )


try:

    start_datetime = datetime.strptime(
        sim_start,
        "%Y-%m-%d %H:%M"
    )

    end_datetime = datetime.strptime(
        sim_end,
        "%Y-%m-%d %H:%M"
    )

except ValueError as exc:

    raise ValueError(
        "experiment_time_start and "
        "experiment_time_end must use:\n"
        "YYYY-MM-DD HH:MM"
    ) from exc


if end_datetime < start_datetime:

    raise RuntimeError(
        "Simulation end occurs before simulation start."
    )


# ============================================================
# TOPOLOGY FILE
# ============================================================

topology_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_topology"
)


topology_file = (
    path_to_settings
    / topology_name
)


if not topology_file.exists():

    raise FileNotFoundError(
        "mizuRoute topology file not found:\n"
        f"{topology_file}\n\n"
        "Run 1_create_network_topology_file.py first."
    )


# Names generated by topology.nc.

topology_seg_dim = "seg"
topology_hru_dim = "hru"

topology_var_area = "area"
topology_var_length = "length"
topology_var_slope = "slope"

topology_var_hru_id = "hruId"
topology_var_hru_to_seg = "hruToSegId"

topology_var_seg_id = "segId"
topology_var_down_seg_id = "downSegId"


# Negative value means use the complete supplied topology.

topology_outlet = "-9999"


# ============================================================
# OPTIONAL SUMMA -> MIZUROUTE REMAPPING
# ============================================================

remap_flag = read_from_control(
    CONTROL_FILE,
    "river_basin_needs_remap"
).strip().lower()


if remap_flag not in {
    "yes",
    "no",
}:

    raise ValueError(
        "river_basin_needs_remap must be "
        "'yes' or 'no'."
    )


if remap_flag == "yes":

    do_remap = "T"

    remap_name = read_from_control(
        CONTROL_FILE,
        "settings_mizu_remap"
    )

    remap_file = (
        path_to_settings
        / remap_name
    )

    if not remap_file.exists():

        raise FileNotFoundError(
            "river_basin_needs_remap = yes, "
            "but routing remapping file was not found:\n"
            f"{remap_file}"
        )


    # Variables generated by optional remapping script.

    remap_var_rn_hru = "RN_hruId"
    remap_var_weight = "weight"
    remap_var_hm_gru = "HM_hruId"
    remap_var_overlap = "nOverlaps"

    remap_dim_hru = "hru"
    remap_dim_data = "data"


else:

    do_remap = "F"

    remap_name = None
    remap_file = None


# ============================================================
# SUMMA RUNOFF INPUT
# ============================================================

# Stage 6 merges SUMMA output into:
#
#   <experiment_id>_timestep.nc
#
# Example:
#
#   run1_timestep.nc

routing_nc = (
    f"{experiment_id}_timestep.nc"
)


routing_var_flow = read_from_control(
    CONTROL_FILE,
    "settings_mizu_routing_var"
)


routing_var_flow_units = read_from_control(
    CONTROL_FILE,
    "settings_mizu_routing_units"
)


routing_dt_text = read_from_control(
    CONTROL_FILE,
    "settings_mizu_routing_dt"
)


try:

    routing_dt_value = float(
        routing_dt_text
    )

except ValueError as exc:

    raise ValueError(
        "settings_mizu_routing_dt must be numeric."
    ) from exc


if routing_dt_value <= 0:

    raise ValueError(
        "settings_mizu_routing_dt must be > 0."
    )


# Use integer text where possible.

if routing_dt_value.is_integer():

    routing_dt = str(
        int(
            routing_dt_value
        )
    )

else:

    routing_dt = str(
        routing_dt_value
    )


# Standard merged SUMMA dimensions.

routing_dim_time = "time"
routing_var_time = "time"

routing_dim_id = "gru"
routing_var_id = "gruId"

routing_calendar = "standard"


# ============================================================
# ROUTING OPTION
# ============================================================

# Historical CWARHM control key:
#
# settings_mizu_output_vars
#
# is being retained here because it currently stores route_opt
# in the existing control files.

route_opt_text = read_from_control(
    CONTROL_FILE,
    "settings_mizu_output_vars"
)


try:

    route_opt = int(
        route_opt_text
    )

except ValueError as exc:

    raise ValueError(
        "settings_mizu_output_vars currently represents "
        "mizuRoute route_opt and must be an integer."
    ) from exc


valid_route_options = {
    0,
    1,
    2,
    3,
    4,
    5,
}


if route_opt not in valid_route_options:

    raise ValueError(
        "Invalid mizuRoute route_opt.\n"
        "Expected:\n"
        "0 = Sum\n"
        "1 = IRF\n"
        "2 = KWT\n"
        "3 = KW\n"
        "4 = MC\n"
        "5 = DW"
    )


# ============================================================
# OUTPUT FREQUENCY
# ============================================================

output_frequency = read_from_control(
    CONTROL_FILE,
    "settings_mizu_output_freq"
).strip().lower()


valid_output_frequencies = {
    "single",
    "daily",
    "monthly",
    "yearly",
}


if output_frequency not in valid_output_frequencies:

    raise ValueError(
        "settings_mizu_output_freq must be one of:\n"
        "single, daily, monthly, yearly"
    )


# ============================================================
# WITHIN-BASIN ROUTING
# ============================================================

within_basin_text = read_from_control(
    CONTROL_FILE,
    "settings_mizu_within_basin"
)


try:

    within_basin = int(
        within_basin_text
    )

except ValueError as exc:

    raise ValueError(
        "settings_mizu_within_basin must be 0 or 1."
    ) from exc


if within_basin not in {
    0,
    1,
}:

    raise ValueError(
        "settings_mizu_within_basin must be:\n"
        "0 = no within-basin routing\n"
        "1 = IRF within-basin routing"
    )


# ============================================================
# PIO / NETCDF SETTINGS
# ============================================================

# Current tested NWAM configuration.

pio_netcdf_type = "netcdf"
pio_netcdf_format = "64bit_offset"


# ============================================================
# REPORT BEFORE WRITING
# ============================================================

print()
print("=" * 70)
print("CREATE MIZUROUTE CONTROL FILE")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"Experiment       : {experiment_id}"
)

print(
    f"Simulation start : {sim_start}"
)

print(
    f"Simulation end   : {sim_end}"
)

print(
    f"Settings path    : {path_to_settings}"
)

print(
    f"SUMMA input      : {path_to_input}"
)

print(
    f"mizuRoute output : {path_to_output}"
)

print(
    f"Topology         : {topology_file}"
)

print(
    f"Parameters       : {parameter_file}"
)

print(
    f"Parameter staged : {parameter_input_file}"
)

print(
    f"SUMMA runoff     : {routing_nc}"
)

print(
    f"Runoff variable  : {routing_var_flow}"
)

print(
    f"Routing dt       : {routing_dt} s"
)

print(
    f"Route option     : {route_opt}"
)

print(
    f"Within basin     : {within_basin}"
)

print(
    f"Remapping        : {do_remap}"
)

print(
    f"Output frequency : {output_frequency}"
)

print(
    f"PIO type         : {pio_netcdf_type}"
)

print(
    f"PIO format       : {pio_netcdf_format}"
)

print(
    f"Control output   : {control_output}"
)


# ============================================================
# BUILD CONTROL FILE
# ============================================================

control_lines = []


# ------------------------------------------------------------
# Header
# ------------------------------------------------------------

control_lines.append(
    "! mizuRoute control file generated by NWAM/CWARHM"
)


# ------------------------------------------------------------
# Directories
# ------------------------------------------------------------

control_lines.append(
    "! --- DEFINE DIRECTORIES"
)

control_lines.append(
    f"<ancil_dir> {path_to_settings}/ ! ancillary/topology files"
)

control_lines.append(
    f"<input_dir> {path_to_input}/ ! SUMMA runoff input"
)

control_lines.append(
    f"<output_dir> {path_to_output}/ ! mizuRoute output"
)


# ------------------------------------------------------------
# Parameter file
# ------------------------------------------------------------

control_lines.append(
    "! --- NAMELIST FILENAME"
)

control_lines.append(
    f"<param_nml> {parameter_name} ! routing parameter namelist"
)


# ------------------------------------------------------------
# Simulation
# ------------------------------------------------------------

control_lines.append(
    "! --- DEFINE SIMULATION CONTROLS"
)

control_lines.append(
    f"<case_name> {experiment_id} !"
)

control_lines.append(
    f"<sim_start> {sim_start} !"
)

control_lines.append(
    f"<sim_end> {sim_end} !"
)

control_lines.append(
    f"<route_opt> {route_opt} !"
)

control_lines.append(
    f"<newFileFrequency> {output_frequency} !"
)


# ------------------------------------------------------------
# Topology
# ------------------------------------------------------------

control_lines.append(
    "! --- DEFINE TOPOLOGY FILE"
)

control_lines.append(
    f"<fname_ntopOld> {topology_name} !"
)

control_lines.append(
    f"<dname_sseg> {topology_seg_dim} !"
)

control_lines.append(
    f"<dname_nhru> {topology_hru_dim} !"
)

control_lines.append(
    f"<seg_outlet> {topology_outlet} !"
)

control_lines.append(
    f"<varname_area> {topology_var_area} !"
)

control_lines.append(
    f"<varname_length> {topology_var_length} !"
)

control_lines.append(
    f"<varname_slope> {topology_var_slope} !"
)

control_lines.append(
    f"<varname_HRUid> {topology_var_hru_id} !"
)

control_lines.append(
    f"<varname_hruSegId> {topology_var_hru_to_seg} !"
)

control_lines.append(
    f"<varname_segId> {topology_var_seg_id} !"
)

control_lines.append(
    f"<varname_downSegId> {topology_var_down_seg_id} !"
)


# ------------------------------------------------------------
# SUMMA runoff
# ------------------------------------------------------------

control_lines.append(
    "! --- DEFINE RUNOFF FILE"
)

control_lines.append(
    f"<fname_qsim> {routing_nc} !"
)

control_lines.append(
    f"<vname_qsim> {routing_var_flow} !"
)

control_lines.append(
    f"<units_qsim> {routing_var_flow_units} !"
)

control_lines.append(
    f"<dt_qsim> {routing_dt} !"
)

control_lines.append(
    f"<dname_time> {routing_dim_time} !"
)

control_lines.append(
    f"<vname_time> {routing_var_time} !"
)

control_lines.append(
    f"<dname_hruid> {routing_dim_id} !"
)

control_lines.append(
    f"<vname_hruid> {routing_var_id} !"
)

control_lines.append(
    f"<ro_calendar> {routing_calendar} !"
)


# ------------------------------------------------------------
# Optional remapping
# ------------------------------------------------------------

control_lines.append(
    "! --- DEFINE RUNOFF MAPPING FILE"
)

control_lines.append(
    f"<is_remap> {do_remap} !"
)


if remap_flag == "yes":

    control_lines.append(
        f"<fname_remap> {remap_name} !"
    )

    control_lines.append(
        f"<vname_hruid_in_remap> {remap_var_rn_hru} !"
    )

    control_lines.append(
        f"<vname_weight> {remap_var_weight} !"
    )

    control_lines.append(
        f"<vname_qhruid> {remap_var_hm_gru} !"
    )

    control_lines.append(
        f"<vname_num_qhru> {remap_var_overlap} !"
    )

    control_lines.append(
        f"<dname_hru_remap> {remap_dim_hru} !"
    )

    control_lines.append(
        f"<dname_data_remap> {remap_dim_data} !"
    )


# ------------------------------------------------------------
# NetCDF / PIO
# ------------------------------------------------------------

control_lines.append(
    "! --- OUTPUT I/O"
)

control_lines.append(
    f"<pio_netcdf_type> {pio_netcdf_type} !"
)

control_lines.append(
    f"<pio_netcdf_format> {pio_netcdf_format} !"
)


# ------------------------------------------------------------
# Miscellaneous
# ------------------------------------------------------------

control_lines.append(
    "! --- MISCELLANEOUS"
)

control_lines.append(
    f"<doesBasinRoute> {within_basin} !"
)


# ============================================================
# WRITE
# ============================================================

control_output.write_text(
    "\n".join(
        control_lines
    )
    + "\n"
)


# ============================================================
# VERIFY GENERATED CONTROL
# ============================================================

if not control_output.exists():

    raise RuntimeError(
        "mizuroute.control was not created."
    )


generated_lines = (
    control_output
    .read_text()
    .splitlines()
)


# ------------------------------------------------------------
# Blank-line check
# ------------------------------------------------------------

blank_lines = [
    index + 1
    for index, line in enumerate(
        generated_lines
    )
    if not line.strip()
]


if blank_lines:

    raise RuntimeError(
        "Generated mizuroute.control contains "
        f"blank lines: {blank_lines}"
    )


# ------------------------------------------------------------
# Every setting must have !
# ------------------------------------------------------------

bad_setting_lines = [
    (
        index + 1,
        line
    )
    for index, line in enumerate(
        generated_lines
    )
    if (
        line.lstrip().startswith("<")
        and "!" not in line
    )
]


if bad_setting_lines:

    raise RuntimeError(
        "Generated mizuroute.control contains "
        "setting lines without '!':\n"
        + "\n".join(
            f"{line_number}: {line}"
            for line_number, line
            in bad_setting_lines
        )
    )


# ------------------------------------------------------------
# Required entries
# ------------------------------------------------------------

control_text = "\n".join(
    generated_lines
)


required_entries = [
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
    "<seg_outlet>",
    "<fname_qsim>",
    "<vname_qsim>",
    "<dt_qsim>",
    "<ro_calendar>",
    "<is_remap>",
    "<pio_netcdf_type>",
    "<pio_netcdf_format>",
    "<doesBasinRoute>",
]


missing_entries = [
    entry
    for entry in required_entries
    if entry not in control_text
]


if missing_entries:

    raise RuntimeError(
        "Generated mizuroute.control is missing "
        "required entries:\n"
        + "\n".join(
            missing_entries
        )
    )


# ------------------------------------------------------------
# Reject obsolete calendar syntax
# ------------------------------------------------------------

if "<calendar>" in control_text:

    raise RuntimeError(
        "Generated control contains obsolete "
        "<calendar>. Use <ro_calendar>."
    )


# ------------------------------------------------------------
# Verify exact settings
# ------------------------------------------------------------

required_exact_lines = {
    f"<seg_outlet> {topology_outlet} !",
    f"<ro_calendar> {routing_calendar} !",
    f"<pio_netcdf_type> {pio_netcdf_type} !",
    f"<pio_netcdf_format> {pio_netcdf_format} !",
    f"<is_remap> {do_remap} !",
    f"<doesBasinRoute> {within_basin} !",
}


missing_exact_lines = (
    required_exact_lines
    - set(
        generated_lines
    )
)


if missing_exact_lines:

    raise RuntimeError(
        "Generated mizuroute.control does not "
        "contain the required exact settings:\n"
        + "\n".join(
            sorted(
                missing_exact_lines
            )
        )
    )


# ------------------------------------------------------------
# Verify parameter staging
# ------------------------------------------------------------

if not parameter_input_file.exists():

    raise RuntimeError(
        "Parameter namelist was not staged into "
        "the mizuRoute input directory:\n"
        f"{parameter_input_file}"
    )


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    control_path
    / "_workflow_log"
)


log_folder.mkdir(
    parents=True,
    exist_ok=True
)


this_file = Path(
    __file__
).name


copy2(
    Path(__file__).resolve(),
    log_folder
    / this_file
)


# Preserve the actual domain-specific control file,
# under its actual filename.

copy2(
    CONTROL_FILE,
    log_folder
    / CONTROL_FILE.name
)


now = datetime.now()


log_file = (
    log_folder
    / (
        f"{now:%Y%m%d_%H%M%S}_"
        "create_mizuroute_control.txt"
    )
)


with open(
    log_file,
    "w"
) as file:

    file.write(
        f"Log generated by {this_file} "
        f"on {now:%Y/%m/%d %H:%M:%S}\n"
    )

    file.write(
        f"Domain: {domain_name}\n"
    )

    file.write(
        f"Control file: {CONTROL_FILE}\n"
    )

    file.write(
        f"Experiment: {experiment_id}\n"
    )

    file.write(
        f"Simulation: "
        f"{sim_start} to {sim_end}\n"
    )

    file.write(
        f"Route option: {route_opt}\n"
    )

    file.write(
        f"Within-basin routing: "
        f"{within_basin}\n"
    )

    file.write(
        f"Remapping: {do_remap}\n"
    )

    file.write(
        f"Topology: {topology_file}\n"
    )

    file.write(
        f"SUMMA runoff file: {routing_nc}\n"
    )

    file.write(
        f"Runoff variable: "
        f"{routing_var_flow}\n"
    )

    file.write(
        f"Routing timestep: "
        f"{routing_dt} s\n"
    )

    file.write(
        f"Output frequency: "
        f"{output_frequency}\n"
    )

    file.write(
        f"seg_outlet: "
        f"{topology_outlet}\n"
    )

    file.write(
        f"Runoff calendar: "
        f"{routing_calendar}\n"
    )

    file.write(
        f"PIO NetCDF type: "
        f"{pio_netcdf_type}\n"
    )

    file.write(
        f"PIO NetCDF format: "
        f"{pio_netcdf_format}\n"
    )

    file.write(
        f"Parameter source: "
        f"{parameter_file}\n"
    )

    file.write(
        f"Parameter staged: "
        f"{parameter_input_file}\n"
    )

    file.write(
        f"Control output: "
        f"{control_output}\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

print()
print("=" * 70)
print("MIZUROUTE CONTROL FILE CREATION COMPLETED")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"Experiment       : {experiment_id}"
)

print(
    f"Simulation       : "
    f"{sim_start} to {sim_end}"
)

print(
    f"Route option     : {route_opt}"
)

print(
    f"Within basin     : {within_basin}"
)

print(
    f"Remapping        : {do_remap}"
)

print(
    f"Output frequency : {output_frequency}"
)

print(
    f"Runoff file      : {routing_nc}"
)

print(
    f"Runoff variable  : {routing_var_flow}"
)

print(
    f"Routing dt       : {routing_dt} s"
)

print(
    f"Output           : {control_output}"
)

print(
    f"Parameter staged : {parameter_input_file}"
)

print(
    f"Workflow log     : {log_file}"
)

print()
print(
    "Control syntax validation passed."
)

print(
    "No control_active.txt was created or modified."
)