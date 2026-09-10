#!/bin/bash
#SBATCH --job-name=lumped_summa_input
#SBATCH --time=02:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1
#SBATCH --output=slurm_logs/lumped_summa_input_%A_%a.out
#SBATCH --error=slurm_logs/lumped_summa_input_%A_%a.err

set -euo pipefail

# ============================================================
# LUMPED MULTIBASIN SUMMA MODEL-INPUT GENERATION
# ============================================================
#
# One Slurm array task = one lumped basin.
#
# Generates:
#
#   lumped/settings/SUMMA/
#
# including:
#
#   base settings
#   forcingFileList.txt
#   fileManager.txt
#   coldState.nc
#   trialParams.nc
#   attributes.nc
#
# IMPORTANT
# ---------
#
# - Uses lumped control files.
# - Uses the one-HRU lumped catchment.
# - Does NOT modify distributed SUMMA products.
# - Does NOT use control_active.txt.
#
# ============================================================


# ============================================================
# PATHS
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

MODEL_INPUT="${CWARHM}/5_model_input"

SUMMA="${MODEL_INPUT}/SUMMA"


# ============================================================
# INPUT TASK FILE
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "ERROR: Supply one lumped basin task file."
    echo
    echo "Usage:"
    echo
    echo "sbatch --array=0-N \\"
    echo "    run_lumped_SUMMA_model_input_generation_array.sh \\"
    echo "    /path/to/lumped_multibasin_preprocessing.txt"

    exit 1

fi


TASK_FILE=$(realpath "$1")


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

    exit 1

fi


LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))


CONTROL_FILE=$(
    sed -n "${LINE_NUMBER}p" "${TASK_FILE}" \
    | xargs
)


if [ -z "${CONTROL_FILE}" ]; then

    echo "ERROR: No control file found for:"
    echo "array index ${SLURM_ARRAY_TASK_ID}"

    exit 1

fi


CONTROL_FILE=$(realpath "${CONTROL_FILE}")


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
        grep -m 1 "^[[:space:]]*${setting}[[:space:]]*|" \
        "${CONTROL_FILE}" \
        | cut -d'|' -f2- \
        | cut -d'#' -f1 \
        | xargs
    )

    if [ -z "${value}" ]; then

        echo "ERROR: Setting not found or empty:"
        echo "${setting}"

        exit 1

    fi

    echo "${value}"
}


# ============================================================
# DOMAIN
# ============================================================

DOMAIN=$(read_control "domain_name")

ROOT_PATH=$(read_control "root_path")

DOMAIN_ROOT="${ROOT_PATH}/domain_${DOMAIN}"

LUMPED_ROOT="${DOMAIN_ROOT}/lumped"


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base

PYTHON=$(conda run -n nwam which python)


if [ ! -x "${PYTHON}" ]; then

    echo "ERROR: Could not locate Python in nwam environment."

    exit 1

fi


mkdir -p "${MODEL_INPUT}/slurm_logs"


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "LUMPED SUMMA MODEL-INPUT GENERATION"
echo "======================================================================"
echo
echo "Slurm job ID   : ${SLURM_JOB_ID:-unknown}"
echo "Array task ID  : ${SLURM_ARRAY_TASK_ID}"
echo "Task-file line : ${LINE_NUMBER}"
echo
echo "Domain         : ${DOMAIN}"
echo "Control file   : ${CONTROL_FILE}"
echo "Lumped root    : ${LUMPED_ROOT}"
echo "Task file      : ${TASK_FILE}"
echo
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
    echo "PASS: ${label}"
}


# ============================================================
# VERIFY LUMPED UPSTREAM INPUTS
# ============================================================

echo
echo "======================================================================"
echo "VERIFY LUMPED UPSTREAM INPUTS"
echo "======================================================================"
echo


FORCING_DIR="${LUMPED_ROOT}/forcing/4_SUMMA_input"

DEM_INTERSECTION="${LUMPED_ROOT}/shapefiles/catchment_intersection/with_dem"

SOIL_INTERSECTION="${LUMPED_ROOT}/shapefiles/catchment_intersection/with_soilgrids"

LAND_INTERSECTION="${LUMPED_ROOT}/shapefiles/catchment_intersection/with_modis"

LUMPED_CATCHMENT="${LUMPED_ROOT}/shapefiles/catchment/${DOMAIN}_lumped_basin.shp"


if [ ! -s "${LUMPED_CATCHMENT}" ]; then

    echo "ERROR: Lumped catchment missing:"
    echo "${LUMPED_CATCHMENT}"

    exit 1

fi


if [ ! -d "${FORCING_DIR}" ]; then

    echo "ERROR: Lumped SUMMA forcing directory missing:"
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

    echo "ERROR: No lumped SUMMA forcing files found."

    exit 1

fi


for directory in \
    "${DEM_INTERSECTION}" \
    "${SOIL_INTERSECTION}" \
    "${LAND_INTERSECTION}"
do

    if [ ! -d "${directory}" ]; then

        echo "ERROR: Required lumped HRU parameter directory missing:"
        echo "${directory}"

        exit 1

    fi

done


echo "Lumped catchment    : PASS"
echo "SUMMA forcing files : ${FORCING_COUNT}"
echo "Lumped parameter data: PASS"


# ============================================================
# SUMMA STEP 1
# ============================================================

run_python_step \
    "SUMMA STEP 1: COPY BASE SETTINGS" \
    "${SUMMA}/1a_copy_base_settings/1_copy_base_settings.py"


# ============================================================
# SUMMA STEP 2
# ============================================================

run_python_step \
    "SUMMA STEP 2: CREATE FORCING FILE LIST" \
    "${SUMMA}/1c_forcing_file_list/1_create_forcing_file_list.py"


# ============================================================
# SUMMA STEP 3
# ============================================================

run_python_step \
    "SUMMA STEP 3: CREATE FILE MANAGER" \
    "${SUMMA}/1b_file_manager/1_create_file_manager.py"


# ============================================================
# SUMMA STEP 4
# ============================================================

run_python_step \
    "SUMMA STEP 4: CREATE COLD STATE" \
    "${SUMMA}/1d_initial_conditions/1_create_coldState.py"


# ============================================================
# SUMMA STEP 5
# ============================================================

run_python_step \
    "SUMMA STEP 5: CREATE TRIAL PARAMETERS" \
    "${SUMMA}/1e_trial_parameters/1_create_trialParams.py"


# ============================================================
# SUMMA STEP 6
# LUMPED-SPECIFIC
# ============================================================

run_python_step \
    "SUMMA STEP 6: INITIALIZE LUMPED ATTRIBUTES" \
    "${SUMMA}/1f_attributes/1_initialize_attributes_nc_lumped.py"


# ============================================================
# SUMMA STEP 7
# ============================================================

run_python_step \
    "SUMMA STEP 7: INSERT SOIL CLASS" \
    "${SUMMA}/1f_attributes/2a_insert_soilclass_from_hist_into_attributes.py"


# ============================================================
# SUMMA STEP 8
# ============================================================

run_python_step \
    "SUMMA STEP 8: INSERT LAND CLASS" \
    "${SUMMA}/1f_attributes/2b_insert_landclass_from_hist_into_attributes.py"


# ============================================================
# SUMMA STEP 9
# ============================================================

run_python_step \
    "SUMMA STEP 9: INSERT ELEVATION" \
    "${SUMMA}/1f_attributes/2c_insert_elevation_into_attributes.py"


# ============================================================
# FINAL PATHS
# ============================================================

SUMMA_SETTINGS="${LUMPED_ROOT}/settings/SUMMA"


SUMMA_FILE_MANAGER=$(read_control "settings_summa_filemanager")

SUMMA_FORCING_LIST=$(read_control "settings_summa_forcing_list")

SUMMA_COLDSTATE=$(read_control "settings_summa_coldstate")

SUMMA_TRIALPARAMS=$(read_control "settings_summa_trialParams")

SUMMA_ATTRIBUTES=$(read_control "settings_summa_attributes")


# ============================================================
# VERIFY FINAL FILES
# ============================================================

echo
echo "======================================================================"
echo "VERIFY FINAL LUMPED SUMMA INPUT FILES"
echo "======================================================================"
echo


FINAL_FILES=(

    "${SUMMA_SETTINGS}/${SUMMA_FILE_MANAGER}"
    "${SUMMA_SETTINGS}/${SUMMA_FORCING_LIST}"
    "${SUMMA_SETTINGS}/${SUMMA_COLDSTATE}"
    "${SUMMA_SETTINGS}/${SUMMA_TRIALPARAMS}"
    "${SUMMA_SETTINGS}/${SUMMA_ATTRIBUTES}"

)


for file in "${FINAL_FILES[@]}"
do

    if [ ! -s "${file}" ]; then

        echo "ERROR: Required lumped SUMMA input missing:"
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
    "${SUMMA_SETTINGS}/${SUMMA_ATTRIBUTES}" <<'PY'

import sys

import netCDF4 as nc4
import numpy as np


coldstate = sys.argv[1]
trialparams = sys.argv[2]
attributes = sys.argv[3]


with nc4.Dataset(attributes) as ds:

    hru = np.asarray(
        ds.variables["hruId"][:],
        dtype=np.int64
    )

    gru = np.asarray(
        ds.variables["gruId"][:],
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

    down = np.asarray(
        ds.variables["downHRUindex"][:],
        dtype=np.int64
    )


if len(hru) != 1:

    raise RuntimeError(
        f"Lumped attributes must contain 1 HRU. Found: {len(hru)}"
    )


if len(gru) != 1:

    raise RuntimeError(
        f"Lumped attributes must contain 1 GRU. Found: {len(gru)}"
    )


if int(hru[0]) != 1:

    raise RuntimeError(
        f"Expected lumped hruId=1. Found: {hru.tolist()}"
    )


if int(gru[0]) != 1:

    raise RuntimeError(
        f"Expected lumped gruId=1. Found: {gru.tolist()}"
    )


if np.any(soil == -999):

    raise RuntimeError(
        "soilTypeIndex still contains -999."
    )


if np.any(veg == -999):

    raise RuntimeError(
        "vegTypeIndex still contains -999."
    )


if np.any(elevation == -999):

    raise RuntimeError(
        "elevation still contains -999."
    )


if not np.all(np.isfinite(elevation)):

    raise RuntimeError(
        "elevation contains non-finite values."
    )


if np.any(down != 0):

    raise RuntimeError(
        "A one-HRU lumped basin must have downHRUindex=0."
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
        "attributes.nc and coldState.nc HRU IDs differ."
    )


if not np.array_equal(
    hru,
    trial_hru
):

    raise RuntimeError(
        "attributes.nc and trialParams.nc HRU IDs differ."
    )


print()
print("Lumped SUMMA NetCDF QA: PASS")
print(f"HRUs          : {len(hru)}")
print(f"GRUs          : {len(gru)}")
print(f"hruId         : {int(hru[0])}")
print(f"gruId         : {int(gru[0])}")
print(f"soilTypeIndex : {int(soil[0])}")
print(f"vegTypeIndex  : {int(veg[0])}")
print(f"elevation     : {float(elevation[0]):.3f}")
print(f"downHRUindex  : {int(down[0])}")

PY


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "LUMPED SUMMA MODEL-INPUT GENERATION COMPLETED SUCCESSFULLY"
echo "======================================================================"
echo
echo "Domain       : ${DOMAIN}"
echo "Control file : ${CONTROL_FILE}"
echo
echo "SUMMA settings:"
echo "  ${SUMMA_SETTINGS}"
echo
echo "End time     : $(date)"
echo
echo "PASS: ${DOMAIN}"
echo
echo "No control_active.txt was used or modified."