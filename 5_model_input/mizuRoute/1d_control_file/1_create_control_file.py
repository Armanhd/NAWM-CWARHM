#!/usr/bin/env python3

"""
Create the mizuRoute control file.

Purpose
-------
Populate mizuroute.control using the active CWARHM control file.

The generated control file defines:
    - mizuRoute ancillary, input and output directories
    - routing parameter namelist
    - simulation period
    - routing scheme
    - topology file and variable names
    - SUMMA runoff input file and variable names
    - optional SUMMA-to-mizuRoute remapping
    - within-basin routing option
    - ParallelIO/NetCDF output configuration

Reproducibility improvements
----------------------------
    - robust control-file path based on this script's location
    - exact control-setting matching
    - validates required settings and files
    - validates simulation dates
    - validates routing option, timestep and output frequency
    - validates remapping configuration
    - validates topology and parameter files
    - writes mizuRoute v3.1.1-compatible control syntax
    - uses <ro_calendar>, not <calendar>
    - writes "!" delimiter on every setting line
    - writes no blank lines
    - explicitly configures the validated serial NetCDF PIO backend
    - stages param.nml.default where mizuRoute v3.1.1 expects it
    - verifies the generated control file
    - records workflow provenance
"""


from pathlib import Path
from shutil import copyfile, copy2
from datetime import datetime


# ============================================================
# PROJECT / CONTROL FILE
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

# Script:
# CWARHM/5_model_input/mizuRoute/1d_control_file/
#
# parents[2] = CWARHM
CWARHM_ROOT = SCRIPT_DIR.parents[2]

CONTROL_FILE = (
    CWARHM_ROOT
    / "0_control_files"
    / "control_active.txt"
)

if not CONTROL_FILE.exists():

    raise FileNotFoundError(
        f"Control file not found:\n{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(file, setting):
    """
    Read one exact setting from the CWARHM control file.
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

            left, right = stripped.split("|", 1)

            if left.strip() != setting:
                continue

            return (
                right
                .split("#", 1)[0]
                .strip()
            )

    raise ValueError(
        f"Setting not found in control file: {setting}"
    )


def make_default_path(suffix):
    """
    Construct a default domain path.
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

control_path = read_from_control(
    CONTROL_FILE,
    "settings_mizu_path"
)

control_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_control_file"
)


if control_path == "default":

    control_path = make_default_path(
        "settings/mizuRoute"
    )

else:

    control_path = Path(
        control_path
    )


control_path.mkdir(
    parents=True,
    exist_ok=True
)


control_output = (
    control_path
    / control_name
)


# Ancillary directory is the mizuRoute settings folder.
path_to_settings = control_path


# ============================================================
# SUMMA OUTPUT / MIZUROUTE INPUT DIRECTORY
# ============================================================

path_to_input = read_from_control(
    CONTROL_FILE,
    "experiment_output_summa"
)


if path_to_input == "default":

    path_to_input = make_default_path(
        f"simulations/{experiment_id}/SUMMA"
    )

else:

    path_to_input = Path(
        path_to_input
    )


# This directory may not contain SUMMA output yet,
# but Stage 5 can safely create the folder.
path_to_input.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# MIZUROUTE OUTPUT DIRECTORY
# ============================================================

path_to_output = read_from_control(
    CONTROL_FILE,
    "experiment_output_mizuRoute"
)


if path_to_output == "default":

    path_to_output = make_default_path(
        f"simulations/{experiment_id}/mizuRoute"
    )

else:

    path_to_output = Path(
        path_to_output
    )


path_to_output.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# PARAMETER FILE
# ============================================================

par_file = read_from_control(
    CONTROL_FILE,
    "settings_mizu_parameters"
)


parameter_file = (
    path_to_settings
    / par_file
)


if not parameter_file.exists():

    raise FileNotFoundError(
        "mizuRoute parameter namelist not found:\n"
        f"{parameter_file}\n\n"
        "Complete the mizuRoute base-settings step "
        "before creating mizuroute.control."
    )


# ------------------------------------------------------------
# Stage parameter namelist where mizuRoute v3.1.1 expects it.
#
# With:
#   <input_dir> .../SUMMA/
#   <param_nml> param.nml.default
#
# mizuRoute looks for the parameter file under input_dir.
# ------------------------------------------------------------

parameter_input_file = (
    path_to_input
    / par_file
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


if sim_start == "default":

    raw_time = read_from_control(
        CONTROL_FILE,
        "forcing_raw_time"
    )

    year_start, _ = [
        value.strip()
        for value in raw_time.split(",", 1)
    ]

    sim_start = (
        f"{year_start}-01-01 00:00"
    )


if sim_end == "default":

    raw_time = read_from_control(
        CONTROL_FILE,
        "forcing_raw_time"
    )

    _, year_end = [
        value.strip()
        for value in raw_time.split(",", 1)
    ]

    sim_end = (
        f"{year_end}-12-31 23:00"
    )


# Validate date strings.
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
        "experiment_time_start and experiment_time_end "
        "must use format:\n"
        "YYYY-MM-DD HH:MM"
    ) from exc


if end_datetime < start_datetime:

    raise RuntimeError(
        "Simulation end occurs before simulation start."
    )


# ============================================================
# TOPOLOGY SETTINGS
# ============================================================

topology_nc = read_from_control(
    CONTROL_FILE,
    "settings_mizu_topology"
)


topology_file = (
    path_to_settings
    / topology_nc
)


if not topology_file.exists():

    raise FileNotFoundError(
        "mizuRoute topology file not found:\n"
        f"{topology_file}\n\n"
        "Complete the mizuRoute topology step "
        "before creating mizuroute.control."
    )


# Names correspond exactly to topology.nc generated by
# 1_create_network_topology_file.py.

topology_seg = "seg"
topology_hru = "hru"

# Negative outlet ID tells mizuRoute to route the complete
# supplied network rather than mask the topology to one
# selected downstream reach.
topology_outlet = "-9999"

topology_var_area = "area"
topology_var_length = "length"
topology_var_slope = "slope"
topology_var_hru_id = "hruId"
topology_var_hru_to_seg_id = "hruToSegId"
topology_var_seg_id = "segId"
topology_var_down_seg_id = "downSegId"


# ============================================================
# OPTIONAL SUMMA -> MIZUROUTE REMAPPING
# ============================================================

remap_flag = read_from_control(
    CONTROL_FILE,
    "river_basin_needs_remap"
).lower()


if remap_flag not in {
    "yes",
    "no"
}:

    raise ValueError(
        "river_basin_needs_remap must be "
        "'yes' or 'no'."
    )


if remap_flag == "yes":

    do_remap = "T"

    remap_nc = read_from_control(
        CONTROL_FILE,
        "settings_mizu_remap"
    )

    remap_file = (
        path_to_settings
        / remap_nc
    )

    if not remap_file.exists():

        raise FileNotFoundError(
            "river_basin_needs_remap = yes, "
            "but remapping NetCDF was not found:\n"
            f"{remap_file}"
        )


    # Names generated by the CWARHM routing-remap script.
    remap_var_rn_hru = "RN_hruId"
    remap_var_weight = "weight"
    remap_var_hm_gru = "HM_hruId"
    remap_var_overlap = "nOverlaps"

    remap_dim_hm_gru = "hru"
    remap_dim_data = "data"

else:

    do_remap = "F"


# ============================================================
# SUMMA RUNOFF INPUT
# ============================================================

# Stage 6 merges the SUMMA array outputs into:
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


routing_dt = read_from_control(
    CONTROL_FILE,
    "settings_mizu_routing_dt"
)


try:

    routing_dt_value = float(
        routing_dt
    )

except ValueError as exc:

    raise ValueError(
        "settings_mizu_routing_dt must be numeric."
    ) from exc


if routing_dt_value <= 0:

    raise ValueError(
        "settings_mizu_routing_dt must be > 0."
    )


# Standard merged SUMMA runoff dimensions/variables.

routing_dim_time = "time"
routing_var_time = "time"

routing_dim_id = "gru"
routing_var_id = "gruId"

routing_nc_calendar = "standard"


# ============================================================
# PIO / NETCDF OUTPUT SETTINGS
# ============================================================

# Current NWAM mizuRoute v3.1.1 build is validated with:
#
#   - PIO enabled
#   - serial NetCDF backend
#   - one mizuRoute MPI task
#
# Multi-rank operation with this serial backend produced
# corrupted NetCDF history-file record indices during testing.
#
# Stage 6 therefore currently enforces one mizuRoute task.

pio_netcdf_type = "netcdf"
pio_netcdf_format = "64bit_offset"


# ============================================================
# ROUTING OPTIONS
# ============================================================

# NOTE:
# The existing CWARHM setting is named
# settings_mizu_output_vars, but its actual meaning in this
# workflow is the mizuRoute route_opt value.

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
        "settings_mizu_output_vars must be an "
        "integer mizuRoute routing option."
    ) from exc


if route_opt not in {
    0, 1, 2, 3, 4, 5
}:

    raise ValueError(
        "Invalid mizuRoute routing option.\n"
        "Expected one of:\n"
        "0 = Sum\n"
        "1 = IRF\n"
        "2 = KWT\n"
        "3 = KW\n"
        "4 = MC\n"
        "5 = DW"
    )


output_freq = read_from_control(
    CONTROL_FILE,
    "settings_mizu_output_freq"
).lower()


valid_output_frequencies = {
    "single",
    "daily",
    "monthly",
    "yearly"
}


if output_freq not in valid_output_frequencies:

    raise ValueError(
        "settings_mizu_output_freq must be one of:\n"
        "single, daily, monthly, yearly"
    )


do_basin_route_text = read_from_control(
    CONTROL_FILE,
    "settings_mizu_within_basin"
)


try:

    do_basin_route = int(
        do_basin_route_text
    )

except ValueError as exc:

    raise ValueError(
        "settings_mizu_within_basin must be 0 or 1."
    ) from exc


if do_basin_route not in {
    0,
    1
}:

    raise ValueError(
        "settings_mizu_within_basin must be:\n"
        "0 = no within-basin routing\n"
        "1 = IRF within-basin routing"
    )


# ============================================================
# SUMMARY BEFORE WRITING
# ============================================================

print()
print("============================================================")
print("CREATE MIZUROUTE CONTROL FILE")
print("============================================================")

print(f"Domain           : {domain_name}")
print(f"Experiment       : {experiment_id}")
print(f"Simulation start : {sim_start}")
print(f"Simulation end   : {sim_end}")
print(f"Settings path    : {path_to_settings}")
print(f"SUMMA input      : {path_to_input}")
print(f"mizuRoute output : {path_to_output}")
print(f"Topology         : {topology_file}")
print(f"Parameters       : {parameter_file}")
print(f"Parameter staged : {parameter_input_file}")
print(f"SUMMA runoff     : {routing_nc}")
print(f"Runoff variable  : {routing_var_flow}")
print(f"Routing dt       : {routing_dt} s")
print(f"Route option     : {route_opt}")
print(f"Within basin     : {do_basin_route}")
print(f"Remapping        : {do_remap}")
print(f"Output frequency : {output_freq}")
print(f"PIO type         : {pio_netcdf_type}")
print(f"PIO format       : {pio_netcdf_format}")
print(f"Control output   : {control_output}")


# ============================================================
# BUILD CONTROL FILE
# ============================================================

# Important:
#
# mizuRoute v3.1.1 parsing proved sensitive to:
#
#   - blank lines
#   - setting lines without the "!" delimiter
#
# Build the complete file as a list of non-empty lines.

control_lines = []


# ------------------------------------------------------------
# Header
# ------------------------------------------------------------

control_lines.append(
    "! mizuRoute control file generated by the NWAM/CWARHM workflow"
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
# Parameter namelist
# ------------------------------------------------------------

control_lines.append(
    "! --- NAMELIST FILENAME"
)

control_lines.append(
    f"<param_nml> {par_file} ! routing parameter namelist"
)


# ------------------------------------------------------------
# Simulation controls
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
    f"<route_opt> {route_opt} ! 0 Sum; 1 IRF; 2 KWT; 3 KW; 4 MC; 5 DW"
)

control_lines.append(
    f"<newFileFrequency> {output_freq} !"
)


# ------------------------------------------------------------
# Topology
# ------------------------------------------------------------

control_lines.append(
    "! --- DEFINE TOPOLOGY FILE"
)

control_lines.append(
    f"<fname_ntopOld> {topology_nc} !"
)

control_lines.append(
    f"<dname_sseg> {topology_seg} !"
)

control_lines.append(
    f"<dname_nhru> {topology_hru} !"
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
    f"<varname_hruSegId> {topology_var_hru_to_seg_id} !"
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

# mizuRoute v3.1.1 setting name.
control_lines.append(
    f"<ro_calendar> {routing_nc_calendar} !"
)


# ------------------------------------------------------------
# Remapping
# ------------------------------------------------------------

control_lines.append(
    "! --- DEFINE RUNOFF MAPPING FILE"
)

control_lines.append(
    f"<is_remap> {do_remap} !"
)


if remap_flag == "yes":

    control_lines.append(
        f"<fname_remap> {remap_nc} !"
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
        f"<dname_hru_remap> {remap_dim_hm_gru} !"
    )

    control_lines.append(
        f"<dname_data_remap> {remap_dim_data} !"
    )


# ------------------------------------------------------------
# Output I/O
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
    f"<doesBasinRoute> {do_basin_route} !"
)


# ============================================================
# WRITE CONTROL FILE
# ============================================================

control_output.write_text(
    "\n".join(control_lines)
    + "\n"
)


# ============================================================
# VERIFY GENERATED CONTROL FILE
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
# No blank lines
# ------------------------------------------------------------

blank_lines = [
    index + 1
    for index, line in enumerate(generated_lines)
    if not line.strip()
]


if blank_lines:

    raise RuntimeError(
        "Generated mizuroute.control contains blank lines:\n"
        f"{blank_lines}"
    )


# ------------------------------------------------------------
# Every setting line must contain !
# ------------------------------------------------------------

bad_setting_lines = [
    (index + 1, line)
    for index, line in enumerate(generated_lines)
    if line.lstrip().startswith("<")
    and "!" not in line
]


if bad_setting_lines:

    raise RuntimeError(
        "Generated mizuroute.control contains setting "
        "lines without '!':\n"
        + "\n".join(
            f"{line_number}: {line}"
            for line_number, line in bad_setting_lines
        )
    )


# ------------------------------------------------------------
# Required settings
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
        f"{missing_entries}"
    )


# ------------------------------------------------------------
# Reject obsolete calendar setting
# ------------------------------------------------------------

if "<calendar>" in control_text:

    raise RuntimeError(
        "Generated control file contains obsolete "
        "<calendar> setting. Use <ro_calendar>."
    )


# ------------------------------------------------------------
# Verify exact validated settings
# ------------------------------------------------------------

required_exact_lines = {
    f"<seg_outlet> {topology_outlet} !",
    f"<ro_calendar> {routing_nc_calendar} !",
    f"<pio_netcdf_type> {pio_netcdf_type} !",
    f"<pio_netcdf_format> {pio_netcdf_format} !",
}


missing_exact_lines = (
    required_exact_lines
    - set(generated_lines)
)


if missing_exact_lines:

    raise RuntimeError(
        "Generated control file does not contain "
        "the required validated mizuRoute settings:\n"
        + "\n".join(
            sorted(missing_exact_lines)
        )
    )


# ------------------------------------------------------------
# Verify staged parameter file
# ------------------------------------------------------------

if not parameter_input_file.exists():

    raise RuntimeError(
        "mizuRoute parameter namelist was not staged "
        "into the SUMMA/mizuRoute input directory:\n"
        f"{parameter_input_file}"
    )


# ============================================================
# LOGGING / PROVENANCE
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


copyfile(
    Path(__file__).resolve(),
    log_folder
    / this_file
)


# Preserve the active workflow control file too.
copyfile(
    CONTROL_FILE,
    log_folder
    / "control_active.txt"
)


now = datetime.now()


log_file = (
    log_folder
    / (
        f"{now:%Y%m%d}_"
        "make_control_file.txt"
    )
)


with log_file.open(
    "w"
) as f:

    f.write(
        f"Log generated by {this_file} "
        f"on {now:%Y/%m/%d %H:%M:%S}\n"
    )

    f.write(
        f"Domain: {domain_name}\n"
    )

    f.write(
        f"Experiment: {experiment_id}\n"
    )

    f.write(
        f"Simulation: {sim_start} to {sim_end}\n"
    )

    f.write(
        f"Route option: {route_opt}\n"
    )

    f.write(
        f"Within-basin routing: {do_basin_route}\n"
    )

    f.write(
        f"Remapping: {do_remap}\n"
    )

    f.write(
        f"seg_outlet: {topology_outlet}\n"
    )

    f.write(
        f"Runoff calendar setting: "
        f"{routing_nc_calendar}\n"
    )

    f.write(
        f"PIO NetCDF type: {pio_netcdf_type}\n"
    )

    f.write(
        f"PIO NetCDF format: {pio_netcdf_format}\n"
    )

    f.write(
        f"Parameter source: {parameter_file}\n"
    )

    f.write(
        f"Parameter staged: {parameter_input_file}\n"
    )

    f.write(
        f"Control output: {control_output}\n"
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

print()
print("============================================================")
print("MIZUROUTE CONTROL FILE CREATED SUCCESSFULLY")
print("============================================================")

print(f"Output           : {control_output}")
print(f"Parameter staged : {parameter_input_file}")

print()
print("Validated settings:")

print(
    f"  <seg_outlet>       {topology_outlet}"
)

print(
    f"  <ro_calendar>      {routing_nc_calendar}"
)

print(
    f"  <pio_netcdf_type>  {pio_netcdf_type}"
)

print(
    f"  <pio_netcdf_format> {pio_netcdf_format}"
)

print()
print("Control syntax:")
print("  Blank lines       : NONE")
print("  Setting delimiter : PASS")
print("  Required entries  : PASS")

print()
print(f"Workflow log      : {log_file}")

print("============================================================")