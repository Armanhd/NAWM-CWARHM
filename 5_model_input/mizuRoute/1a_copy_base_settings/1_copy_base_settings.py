# Copy mizuRoute base settings into the active domain settings folder.
#
# The script:
#   - locates CWARHM relative to this script
#   - reads control_active.txt
#   - resolves settings_mizu_path
#   - copies files from ../0_base_settings
#   - validates the source and destination paths
#   - records script provenance in _workflow_log
#
# Expected output includes:
#   settings/mizuRoute/param.nml.default

from pathlib import Path
from shutil import copyfile
from datetime import datetime


# ============================================================
# PROJECT / CONTROL FILE
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

# Script location:
# CWARHM/5_model_input/mizuRoute/1a_copy_base_settings
#
# Therefore CWARHM root is three levels above this directory.
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
    Read one exact setting from a CWARHM control file.
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
    Construct a default domain path from root_path/domain_name.
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
# DOMAIN INFORMATION
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# SOURCE BASE SETTINGS
# ============================================================

base_settings_path = (
    SCRIPT_DIR.parent
    / "0_base_settings"
)

if not base_settings_path.exists():
    raise FileNotFoundError(
        f"mizuRoute base-settings directory not found:\n"
        f"{base_settings_path}"
    )

if not base_settings_path.is_dir():
    raise NotADirectoryError(
        f"Expected a directory:\n{base_settings_path}"
    )


# ============================================================
# DESTINATION SETTINGS PATH
# ============================================================

settings_path = read_from_control(
    CONTROL_FILE,
    "settings_mizu_path"
)

if settings_path == "default":

    settings_path = make_default_path(
        "settings/mizuRoute"
    )

else:

    settings_path = Path(
        settings_path
    )

settings_path.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FIND FILES TO COPY
# ============================================================

base_files = sorted(
    file
    for file in base_settings_path.iterdir()
    if file.is_file()
)

if len(base_files) == 0:
    raise RuntimeError(
        f"No base-setting files found in:\n"
        f"{base_settings_path}"
    )


print()
print("============================================================")
print("COPY MIZUROUTE BASE SETTINGS")
print("============================================================")
print(f"Domain      : {domain_name}")
print(f"Source      : {base_settings_path}")
print(f"Destination : {settings_path}")
print(f"Files found : {len(base_files)}")
print()


# ============================================================
# COPY FILES
# ============================================================

copied_files = []

for source_file in base_files:

    destination_file = (
        settings_path
        / source_file.name
    )

    copyfile(
        source_file,
        destination_file
    )

    copied_files.append(
        destination_file
    )

    print(
        f"Copied: {source_file.name}"
    )


# ============================================================
# VERIFY EXPECTED PARAMETER FILE
# ============================================================

parameter_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_parameters"
)

parameter_file = (
    settings_path
    / parameter_name
)

if not parameter_file.exists():

    print()
    print(
        "WARNING: The parameter file specified in "
        "control_active.txt was not found after copying:"
    )

    print(
        parameter_file
    )

    print()
    print(
        "Files that were copied:"
    )

    for file in copied_files:
        print(
            f"  {file.name}"
        )

    raise FileNotFoundError(
        "Configured mizuRoute parameter file "
        "was not produced."
    )


# ============================================================
# LOGGING / PROVENANCE
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

copyfile(
    Path(__file__).resolve(),
    log_folder / this_file
)


now = datetime.now()

log_file = (
    log_folder
    / f"{now:%Y%m%d}_copy_mizuroute_base_settings.txt"
)


with open(
    log_file,
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
        f"Source directory: {base_settings_path}\n"
    )

    f.write(
        f"Destination directory: {settings_path}\n"
    )

    f.write(
        f"Files copied: {len(copied_files)}\n"
    )

    for file in copied_files:
        f.write(
            f"  {file.name}\n"
        )


# ============================================================
# SUMMARY
# ============================================================

print()
print("mizuRoute base settings copied successfully.")
print(f"Files copied : {len(copied_files)}")
print(f"Parameter file: {parameter_file}")
print(f"Output folder : {settings_path}")