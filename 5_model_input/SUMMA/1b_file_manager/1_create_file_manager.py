
# Create the SUMMA fileManager.txt for the active CWARHM domain.
#
# This script:
#   - locates CWARHM from its own file location
#   - reads control_active.txt
#   - resolves all default paths from root_path/domain_name
#   - uses experiment_time_start/end when explicitly provided
#   - otherwise derives simulation dates from forcing_raw_time
#   - validates the main directories
#   - writes fileManager.txt
#   - stores workflow provenance
#
# Reproducible for any domain selected through control_active.txt.

from pathlib import Path
from datetime import datetime
from shutil import copy2


# ============================================================
# PROJECT / CONTROL FILE
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

# Script:
# CWARHM/5_model_input/SUMMA/1b_file_manager/1_create_file_manager.py
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

    with open(file) as contents:

        for line in contents:

            stripped = line.strip()

            if (
                stripped
                and not stripped.startswith("#")
                and "|" in stripped
            ):

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


def resolve_path(setting, default_suffix):

    value = read_from_control(
        CONTROL_FILE,
        setting
    )

    if value == "default":
        return make_default_path(
            default_suffix
        )

    return Path(value)


# ============================================================
# DOMAIN / EXPERIMENT SETTINGS
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
        for item in forcing_raw_time.split(",")
    ]

    start_year = int(start_year_text)
    end_year = int(end_year_text)

except Exception as exc:

    raise ValueError(
        "forcing_raw_time must have format "
        "'START_YEAR,END_YEAR', for example "
        "'1950,2019'."
    ) from exc


if start_year > end_year:

    raise ValueError(
        f"Invalid forcing_raw_time: "
        f"{start_year},{end_year}"
    )


if sim_start == "default":

    sim_start = (
        f"{start_year}-01-01 00:00"
    )


if sim_end == "default":

    sim_end = (
        f"{end_year}-12-31 23:00"
    )


# ============================================================
# PATHS
# ============================================================

settings_path = resolve_path(
    "settings_summa_path",
    "settings/SUMMA"
)

forcing_path = resolve_path(
    "forcing_summa_path",
    "forcing/4_SUMMA_input"
)

output_path_setting = read_from_control(
    CONTROL_FILE,
    "experiment_output_summa"
)

if output_path_setting == "default":

    output_path = make_default_path(
        f"simulations/{experiment_id}/SUMMA"
    )

else:

    output_path = Path(
        output_path_setting
    )


settings_path.mkdir(
    parents=True,
    exist_ok=True
)

output_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FILENAMES
# ============================================================

filemanager_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_filemanager"
)

coldstate_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_coldstate"
)

attributes_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_attributes"
)

trialparams_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_trialParams"
)

forcing_list_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_forcing_list"
)


filemanager_file = (
    settings_path
    / filemanager_name
)


# ============================================================
# VALIDATE REQUIRED DIRECTORIES
# ============================================================

if not forcing_path.exists():

    raise FileNotFoundError(
        f"SUMMA forcing directory not found:\n"
        f"{forcing_path}"
    )


# Base settings should already have been copied in Step 18a.
required_base_files = [
    "modelDecisions.txt",
    "outputControl.txt",
    "localParamInfo.txt",
    "basinParamInfo.txt",
    "TBL_VEGPARM.TBL",
    "TBL_SOILPARM.TBL",
    "TBL_GENPARM.TBL",
    "TBL_MPTABLE.TBL",
]

missing_base_files = [
    name
    for name in required_base_files
    if not (settings_path / name).exists()
]

if missing_base_files:

    raise FileNotFoundError(
        "Required SUMMA base-setting files are missing:\n"
        + "\n".join(
            f"  {name}"
            for name in missing_base_files
        )
        + "\nRun 1a_copy_base_settings first."
    )


# ============================================================
# REPORT
# ============================================================

print()
print("============================================================")
print("CREATE SUMMA FILE MANAGER")
print("============================================================")
print(f"Domain          : {domain_name}")
print(f"Experiment      : {experiment_id}")
print(f"Simulation start: {sim_start}")
print(f"Simulation end  : {sim_end}")
print(f"Settings path   : {settings_path}")
print(f"Forcing path    : {forcing_path}")
print(f"Output path     : {output_path}")
print(f"File manager    : {filemanager_file}")


# ============================================================
# WRITE FILE MANAGER
# ============================================================

with open(
    filemanager_file,
    "w"
) as fm:

    fm.write(
        "controlVersion       "
        "'SUMMA_FILE_MANAGER_V3.0.0' "
        "! file manager version\n"
    )

    fm.write(
        f"simStartTime         "
        f"'{sim_start}' !\n"
    )

    fm.write(
        f"simEndTime           "
        f"'{sim_end}' !\n"
    )

    fm.write(
        "tmZoneInfo           "
        "'utcTime' !\n"
    )

    fm.write(
        f"outFilePrefix        "
        f"'{experiment_id}' !\n"
    )

    fm.write(
        f"settingsPath         "
        f"'{settings_path}/' !\n"
    )

    fm.write(
        f"forcingPath          "
        f"'{forcing_path}/' !\n"
    )

    fm.write(
        f"outputPath           "
        f"'{output_path}/' !\n"
    )

    fm.write(
        f"initConditionFile    "
        f"'{coldstate_name}' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        f"attributeFile        "
        f"'{attributes_name}' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        f"trialParamFile       "
        f"'{trialparams_name}' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        f"forcingListFile      "
        f"'{forcing_list_name}' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "decisionsFile        "
        "'modelDecisions.txt' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "outputControlFile    "
        "'outputControl.txt' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "globalHruParamFile   "
        "'localParamInfo.txt' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "globalGruParamFile   "
        "'basinParamInfo.txt' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "vegTableFile         "
        "'TBL_VEGPARM.TBL' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "soilTableFile        "
        "'TBL_SOILPARM.TBL' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "generalTableFile     "
        "'TBL_GENPARM.TBL' "
        "! Relative to settingsPath\n"
    )

    fm.write(
        "noahmpTableFile      "
        "'TBL_MPTABLE.TBL' "
        "! Relative to settingsPath\n"
    )


# ============================================================
# LOGGING
# ============================================================

log_folder = (
    settings_path
    / "_workflow_log"
)

log_folder.mkdir(
    parents=True,
    exist_ok=True
)


this_file = Path(__file__).name

copy2(
    Path(__file__).resolve(),
    log_folder / this_file
)


now = datetime.now()

log_file = (
    log_folder
    / f"{now:%Y%m%d}_make_file_manager.txt"
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
        f"Experiment: {experiment_id}\n"
    )

    file.write(
        f"Simulation start: {sim_start}\n"
    )

    file.write(
        f"Simulation end: {sim_end}\n"
    )

    file.write(
        f"File manager: {filemanager_file}\n"
    )


print()
print("SUMMA file manager created successfully.")
print(f"Output: {filemanager_file}")