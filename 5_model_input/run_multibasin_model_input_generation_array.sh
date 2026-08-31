#!/bin/bash
#SBATCH --job-name=nwam_model_input
#SBATCH --time=02:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1
#SBATCH --output=slurm_logs/model_input_%A_%a.out
#SBATCH --error=slurm_logs/model_input_%A_%a.err

set -euo pipefail


# ============================================================
# NWAM MULTIBASIN MODEL-INPUT GENERATION
# ============================================================
#
# One array task = one basin/domain.
#
# Generates:
#
#   SUMMA
#   -----
#   base settings
#   forcingFileList.txt
#   fileManager.txt
#   coldState.nc
#   trialParams.nc
#   attributes.nc
#
#   mizuRoute
#   ---------
#   base settings
#   topology.nc
#   optional remapping file
#   mizuroute.control
#
# IMPORTANT
# ---------
# No control_active.txt is used or modified.
#
# Task-file format:
#
#   one control-file path per line
#
# Example:
#
# /work/.../control_MERIT_861.txt
# /work/.../control_MERIT_862.txt
# /work/.../control_MERIT_863.txt
#
# ============================================================


# ============================================================
# PATHS
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

MODEL_INPUT="${CWARHM}/5_model_input"

SUMMA="${MODEL_INPUT}/SUMMA"

MIZU="${MODEL_INPUT}/mizuRoute"


# ============================================================
# INPUT TASK FILE
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "ERROR: Supply one multibasin task file."
    echo
    echo "Usage:"
    echo
    echo "sbatch --array=0-N run_multibasin_model_input_generation_array.sh \\"
    echo "    /path/to/multibasin_preprocessing.txt"

    exit 1

fi


TASK_FILE="$1"


if [ ! -f "${TASK_FILE}" ]; then

    echo "ERROR: Task file not found:"
    echo "${TASK_FILE}"

    exit 1

fi


# ============================================================
# ARRAY TASK
# ============================================================

if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then

    echo "ERROR: SLURM_ARRAY_TASK_ID is not defined."
    echo "Submit this script as a Slurm array."

    exit 1

fi


LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))


CONTROL_FILE=$(sed -n "${LINE_NUMBER}p" "${TASK_FILE}" | xargs)


if [ -z "${CONTROL_FILE}" ]; then

    echo "ERROR: No control file found on task-file line:"
    echo "${LINE_NUMBER}"

    exit 1

fi


if [ ! -f "${CONTROL_FILE}" ]; then

    echo "ERROR: Control file not found:"
    echo "${CONTROL_FILE}"

    exit 1

fi


# ============================================================
# CONTROL READER
# ============================================================

read_control() {

    local setting="$1"
    local value

    value=$(
        grep -m 1 "^${setting}[[:space:]]*|" "${CONTROL_FILE}" \
        | cut -d'|' -f2- \
        | cut -d'#' -f1 \
        | xargs
    )

    if [ -z "${value}" ]; then

        echo "ERROR: Setting not found or empty:"
        echo "${setting}"
        echo
        echo "Control file:"
        echo "${CONTROL_FILE}"

        exit 1

    fi

    echo "${value}"
}


# ============================================================
# DOMAIN SETTINGS
# ============================================================

DOMAIN=$(read_control "domain_name")
ROOT_PATH=$(read_control "root_path")

DOMAIN_ROOT="${ROOT_PATH}/domain_${DOMAIN}"


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base

PYTHON=$(conda run -n nwam which python)


if [ ! -x "${PYTHON}" ]; then

    echo "ERROR: Could not locate Python in nwam environment."
    exit 1

fi


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "NWAM MULTIBASIN MODEL-INPUT GENERATION"
echo "======================================================================"
echo
echo "Slurm job ID   : ${SLURM_JOB_ID:-unknown}"
echo "Array task ID  : ${SLURM_ARRAY_TASK_ID}"
echo "Task-file line : ${LINE_NUMBER}"
echo
echo "Domain         : ${DOMAIN}"
echo "Control file   : ${CONTROL_FILE}"
echo "Domain root    : ${DOMAIN_ROOT}"
echo "Task file      : ${TASK_FILE}"
echo
echo "Python         : ${PYTHON}"
echo "Start time     : $(date)"
echo


# ============================================================
# HELPER
# ============================================================

run_python_step() {

    local label="$1"
    local script="$2"

    echo
    echo "----------------------------------------------------------------------"
    echo "${label}"
    echo "----------------------------------------------------------------------"
    echo

    if [ ! -f "${script}" ]; then

        echo "ERROR: Script not found:"
        echo "${script}"

        exit 1

    fi

    "${PYTHON}" \
        "${script}" \
        "${CONTROL_FILE}"

    echo
    echo "${label}: PASS"
}


# ============================================================
# VERIFY UPSTREAM INPUTS
# ============================================================

echo
echo "======================================================================"
echo "VERIFY UPSTREAM INPUTS"
echo "======================================================================"
echo


FORCING_DIR="${DOMAIN_ROOT}/forcing/4_SUMMA_input"

DEM_INTERSECTION="${DOMAIN_ROOT}/shapefiles/catchment_intersection/with_dem"
SOIL_INTERSECTION="${DOMAIN_ROOT}/shapefiles/catchment_intersection/with_soilgrids"
LAND_INTERSECTION="${DOMAIN_ROOT}/shapefiles/catchment_intersection/with_modis"


if [ ! -d "${FORCING_DIR}" ]; then

    echo "ERROR: SUMMA forcing directory missing:"
    echo "${FORCING_DIR}"

    exit 1

fi


FORCING_COUNT=$(
    find "${FORCING_DIR}" \
        -maxdepth 1 \
        -type f \
        -name "NWAM_SUMMA_forcing_*.nc" \
        | wc -l
)


if [ "${FORCING_COUNT}" -eq 0 ]; then

    echo "ERROR: No final SUMMA forcing files found."
    exit 1

fi


for directory in \
    "${DEM_INTERSECTION}" \
    "${SOIL_INTERSECTION}" \
    "${LAND_INTERSECTION}"
do

    if [ ! -d "${directory}" ]; then

        echo "ERROR: Required HRU parameter directory missing:"
        echo "${directory}"

        exit 1

    fi

done


echo "SUMMA forcing files : ${FORCING_COUNT}"
echo "HRU parameter data  : PASS"


# ============================================================
# PART A: SUMMA
# ============================================================

echo
echo "======================================================================"
echo "PART A: SUMMA MODEL INPUT"
echo "======================================================================"


# ------------------------------------------------------------
# SUMMA STEP 1
# ------------------------------------------------------------

run_python_step \
    "SUMMA STEP 1: COPY BASE SETTINGS" \
    "${SUMMA}/1a_copy_base_settings/1_copy_base_settings.py"


# ------------------------------------------------------------
# SUMMA STEP 2
#
# Validate complete forcing archive before anything else that
# depends upon it.
# ------------------------------------------------------------

run_python_step \
    "SUMMA STEP 2: CREATE FORCING FILE LIST" \
    "${SUMMA}/1c_forcing_file_list/1_create_forcing_file_list.py"


# ------------------------------------------------------------
# SUMMA STEP 3
# ------------------------------------------------------------

run_python_step \
    "SUMMA STEP 3: CREATE FILE MANAGER" \
    "${SUMMA}/1b_file_manager/1_create_file_manager.py"


# ------------------------------------------------------------
# SUMMA STEP 4
# ------------------------------------------------------------

run_python_step \
    "SUMMA STEP 4: CREATE COLD STATE" \
    "${SUMMA}/1d_initial_conditions/1_create_coldState.py"


# ------------------------------------------------------------
# SUMMA STEP 5
# ------------------------------------------------------------

run_python_step \
    "SUMMA STEP 5: CREATE TRIAL PARAMETERS" \
    "${SUMMA}/1e_trial_parameters/1_create_trialParams.py"


# ------------------------------------------------------------
# SUMMA STEP 6
# ------------------------------------------------------------

run_python_step \
    "SUMMA STEP 6: INITIALIZE ATTRIBUTES" \
    "${SUMMA}/1f_attributes/1_initialize_attributes_nc.py"


# ------------------------------------------------------------
# SUMMA STEP 7
# ------------------------------------------------------------

run_python_step \
    "SUMMA STEP 7: INSERT SOIL CLASS" \
    "${SUMMA}/1f_attributes/2a_insert_soilclass_from_hist_into_attributes.py"


# ------------------------------------------------------------
# SUMMA STEP 8
# ------------------------------------------------------------

run_python_step \
    "SUMMA STEP 8: INSERT LAND CLASS" \
    "${SUMMA}/1f_attributes/2b_insert_landclass_from_hist_into_attributes.py"


# ------------------------------------------------------------
# SUMMA STEP 9
# ------------------------------------------------------------

run_python_step \
    "SUMMA STEP 9: INSERT ELEVATION" \
    "${SUMMA}/1f_attributes/2c_insert_elevation_into_attributes.py"


# ============================================================
# PART B: MIZUROUTE
# ============================================================

echo
echo "======================================================================"
echo "PART B: MIZUROUTE MODEL INPUT"
echo "======================================================================"


# ------------------------------------------------------------
# MIZU STEP 1
# ------------------------------------------------------------

run_python_step \
    "MIZUROUTE STEP 1: COPY BASE SETTINGS" \
    "${MIZU}/1a_copy_base_settings/1_copy_base_settings.py"


# ------------------------------------------------------------
# MIZU STEP 2
# ------------------------------------------------------------

run_python_step \
    "MIZUROUTE STEP 2: CREATE NETWORK TOPOLOGY" \
    "${MIZU}/1b_network_topology_file/1_create_network_topology_file.py"


# ------------------------------------------------------------
# MIZU STEP 3: OPTIONAL REMAPPING
# ------------------------------------------------------------

REMAP=$(read_control "river_basin_needs_remap")

REMAP=$(echo "${REMAP}" | tr '[:upper:]' '[:lower:]')


echo
echo "----------------------------------------------------------------------"
echo "MIZUROUTE STEP 3: OPTIONAL SUMMA-TO-MIZUROUTE REMAPPING"
echo "----------------------------------------------------------------------"
echo


case "${REMAP}" in

    no)

        echo "river_basin_needs_remap = no"
        echo
        echo "Remapping is not required."
        echo "Step skipped safely."
        ;;


    yes)

        REMAP_SCRIPT="${MIZU}/1c_optional_remapping_file/1_remap_summa_catchments_to_routing.py"

        echo "river_basin_needs_remap = yes"
        echo

        echo "ERROR:"
        echo "The current optional mizuRoute remapping script still"
        echo "uses control_active.txt and is not multibasin-safe."
        echo
        echo "Do not run this basin concurrently until that script"
        echo "has been converted to explicit control-file input."

        exit 1
        ;;


    *)

        echo "ERROR:"
        echo "river_basin_needs_remap must be yes or no."
        echo "Found: ${REMAP}"

        exit 1
        ;;

esac


# ------------------------------------------------------------
# MIZU STEP 4
# ------------------------------------------------------------

run_python_step \
    "MIZUROUTE STEP 4: CREATE CONTROL FILE" \
    "${MIZU}/1d_control_file/1_create_control_file.py"


# ============================================================
# FINAL FILE PATHS
# ============================================================

SUMMA_SETTINGS="${DOMAIN_ROOT}/settings/SUMMA"
MIZU_SETTINGS="${DOMAIN_ROOT}/settings/mizuRoute"


SUMMA_FILE_MANAGER=$(read_control "settings_summa_filemanager")
SUMMA_FORCING_LIST=$(read_control "settings_summa_forcing_list")
SUMMA_COLDSTATE=$(read_control "settings_summa_coldstate")
SUMMA_TRIALPARAMS=$(read_control "settings_summa_trialParams")
SUMMA_ATTRIBUTES=$(read_control "settings_summa_attributes")

MIZU_TOPOLOGY=$(read_control "settings_mizu_topology")
MIZU_CONTROL=$(read_control "settings_mizu_control_file")
MIZU_PARAMETERS=$(read_control "settings_mizu_parameters")


# ============================================================
# FINAL VERIFICATION
# ============================================================

echo
echo "======================================================================"
echo "VERIFY FINAL MODEL INPUT FILES"
echo "======================================================================"
echo


FINAL_FILES=(

    "${SUMMA_SETTINGS}/${SUMMA_FILE_MANAGER}"
    "${SUMMA_SETTINGS}/${SUMMA_FORCING_LIST}"
    "${SUMMA_SETTINGS}/${SUMMA_COLDSTATE}"
    "${SUMMA_SETTINGS}/${SUMMA_TRIALPARAMS}"
    "${SUMMA_SETTINGS}/${SUMMA_ATTRIBUTES}"

    "${MIZU_SETTINGS}/${MIZU_TOPOLOGY}"
    "${MIZU_SETTINGS}/${MIZU_CONTROL}"
    "${MIZU_SETTINGS}/${MIZU_PARAMETERS}"
)


for file in "${FINAL_FILES[@]}"
do

    if [ ! -s "${file}" ]; then

        echo "ERROR: Required model-input file missing or empty:"
        echo "${file}"

        exit 1

    fi

    echo "PASS: ${file}"

done


# ============================================================
# NETCDF QA
# ============================================================

"${PYTHON}" - \
    "${SUMMA_SETTINGS}/${SUMMA_COLDSTATE}" \
    "${SUMMA_SETTINGS}/${SUMMA_TRIALPARAMS}" \
    "${SUMMA_SETTINGS}/${SUMMA_ATTRIBUTES}" \
    "${MIZU_SETTINGS}/${MIZU_TOPOLOGY}" <<'PY'

import sys
from pathlib import Path

import netCDF4 as nc4
import numpy as np


coldstate = Path(sys.argv[1])
trialparams = Path(sys.argv[2])
attributes = Path(sys.argv[3])
topology = Path(sys.argv[4])


for file in [
    coldstate,
    trialparams,
    attributes,
    topology,
]:

    with nc4.Dataset(file) as ds:

        if len(ds.dimensions) == 0:
            raise RuntimeError(
                f"No dimensions found in {file}"
            )


with nc4.Dataset(attributes) as ds:

    hru = np.asarray(
        ds.variables["hruId"][:],
        dtype=np.int64
    )

    soil = np.asarray(
        ds.variables["soilTypeIndex"][:]
    )

    veg = np.asarray(
        ds.variables["vegTypeIndex"][:]
    )

    elevation = np.asarray(
        ds.variables["elevation"][:],
        dtype=np.float64
    )

    if np.any(soil == -999):
        raise RuntimeError(
            "attributes.nc still contains "
            "soilTypeIndex = -999"
        )

    if np.any(veg == -999):
        raise RuntimeError(
            "attributes.nc still contains "
            "vegTypeIndex = -999"
        )

    if np.any(elevation == -999):
        raise RuntimeError(
            "attributes.nc still contains "
            "elevation = -999"
        )

    if not np.all(np.isfinite(elevation)):
        raise RuntimeError(
            "attributes.nc contains non-finite elevation."
        )


with nc4.Dataset(coldstate) as ds:

    cold_hru = np.asarray(
        ds.variables["hruId"][:],
        dtype=np.int64
    )


with nc4.Dataset(trialparams) as ds:

    trial_hru = np.asarray(
        ds.variables["hruId"][:],
        dtype=np.int64
    )


if not np.array_equal(
    hru,
    cold_hru
):

    raise RuntimeError(
        "attributes.nc and coldState.nc HRU order differ."
    )


if not np.array_equal(
    hru,
    trial_hru
):

    raise RuntimeError(
        "attributes.nc and trialParams.nc HRU order differ."
    )


with nc4.Dataset(topology) as ds:

    seg = np.asarray(
        ds.variables["segId"][:],
        dtype=np.int64
    )

    down = np.asarray(
        ds.variables["downSegId"][:],
        dtype=np.int64
    )

    hru_to_seg = np.asarray(
        ds.variables["hruToSegId"][:],
        dtype=np.int64
    )


    seg_set = set(
        seg.tolist()
    )


    invalid_down = [
        int(value)
        for value in down
        if (
            int(value) != 0
            and int(value) not in seg_set
        )
    ]


    if invalid_down:

        raise RuntimeError(
            f"Invalid topology downSegId: "
            f"{invalid_down}"
        )


    invalid_hru_links = [
        int(value)
        for value in hru_to_seg
        if int(value) not in seg_set
    ]


    if invalid_hru_links:

        raise RuntimeError(
            f"Invalid topology hruToSegId: "
            f"{invalid_hru_links}"
        )


print()
print("NetCDF model-input QA: PASS")
print(f"SUMMA HRUs           : {len(hru)}")
print(f"mizuRoute segments   : {len(seg)}")

PY


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "NWAM MODEL-INPUT GENERATION COMPLETED SUCCESSFULLY"
echo "======================================================================"
echo
echo "Domain       : ${DOMAIN}"
echo "Control file : ${CONTROL_FILE}"
echo
echo "SUMMA settings:"
echo "  ${SUMMA_SETTINGS}"
echo
echo "mizuRoute settings:"
echo "  ${MIZU_SETTINGS}"
echo
echo "End time     : $(date)"
echo
echo "Next workflow stage:"
echo "  Run SUMMA, merge SUMMA output, then run mizuRoute."
echo
echo "No control_active.txt was used or modified."