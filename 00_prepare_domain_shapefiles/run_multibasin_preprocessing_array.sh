#!/bin/bash
#SBATCH --job-name=nwam_preprocess
#SBATCH --time=02:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2
#SBATCH --output=slurm_logs/preprocess_%A_%a.out
#SBATCH --error=slurm_logs/preprocess_%A_%a.err

# ============================================================
# MULTIBASIN NWAM DOMAIN + FORCING-GRID PREPROCESSING
# ============================================================
#
# One SLURM array task processes one domain.
#
# Workflow:
#
#   1. Stage 00 domain shapefile preparation
#      - prepare river network
#      - prepare catchment
#      - derive/report domain control values
#
#   2. Create forcing-grid shapefiles
#      - ERA5_grid.shp
#      - EM_Earth_grid.shp
#
#   3. Verify required outputs
#
# IMPORTANT
# ---------
# This worker does NOT:
#
#   - prepare monthly forcing files
#   - generate EASYMORE remapping weights
#   - remap monthly forcing
#   - combine SUMMA forcing
#
# Those are later workflow stages.
#
# No control_active.txt is used or modified.
#
# Task-file format:
#
#   one absolute control-file path per line
#
# Example:
#
#   /work/.../control_MERIT_861.txt
#   /work/.../control_MERIT_862.txt
#
# Usage:
#
#   N=$(wc -l < multibasin_preprocessing_MERIT_86.txt)
#
#   sbatch \
#       --array=0-$((N-1))%6 \
#       run_multibasin_preprocessing_array.sh \
#       /path/to/multibasin_preprocessing_MERIT_86.txt
#
# ============================================================

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

PREP_DIR="${CWARHM}/00_prepare_domain_shapefiles"

FORCING_PREP_DIR="${CWARHM}/3a_forcing/0_existing_forcing"

PREP_SCRIPT="${PREP_DIR}/run_prepare_domain_shapefiles.sh"

GRID_SCRIPT="${FORCING_PREP_DIR}/2_create_forcing_grids.py"


# ============================================================
# INPUT TASK FILE
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "ERROR: preprocessing task file must be supplied."
    echo
    echo "Usage:"
    echo "  sbatch --array=0-N%6 \\"
    echo "    run_multibasin_preprocessing_array.sh \\"
    echo "    /path/to/multibasin_preprocessing.txt"

    exit 1

fi


TASK_FILE=$(realpath "$1")


if [ ! -f "${TASK_FILE}" ]; then

    echo "ERROR: Task file not found:"
    echo "${TASK_FILE}"

    exit 1

fi


# ============================================================
# SLURM ARRAY ID
# ============================================================

if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then

    echo "ERROR: SLURM_ARRAY_TASK_ID is not defined."
    echo "Submit this script as a Slurm array."

    exit 1

fi


LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))


CONTROL_FILE=$(sed -n "${LINE_NUMBER}p" "${TASK_FILE}" | xargs)


if [ -z "${CONTROL_FILE}" ]; then

    echo "ERROR: No task found for array index:"
    echo "${SLURM_ARRAY_TASK_ID}"

    exit 1

fi


CONTROL_FILE=$(realpath "${CONTROL_FILE}")


if [ ! -f "${CONTROL_FILE}" ]; then

    echo "ERROR: Control file not found:"
    echo "${CONTROL_FILE}"

    exit 1

fi


# ============================================================
# READ CONTROL SETTINGS
# ============================================================

read_control() {

    local setting="$1"

    awk -F'|' -v key="${setting}" '
        {
            left=$1
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", left)

            if (left == key) {
                value=$2
                sub(/#.*/, "", value)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
                print value
                exit
            }
        }
    ' "${CONTROL_FILE}"
}


DOMAIN=$(read_control "domain_name")

ROOT_PATH=$(read_control "root_path")

CATCHMENT_NAME=$(read_control "catchment_shp_name")

RIVER_NAME=$(read_control "river_network_shp_name")

EMEARTH_GRID_NAME=$(read_control "forcing_emearth_shape_name")

ERA5_GRID_NAME=$(read_control "forcing_era5_shape_name")


if [ -z "${DOMAIN}" ]; then
    echo "ERROR: Could not read domain_name."
    exit 1
fi


if [ -z "${ROOT_PATH}" ]; then
    echo "ERROR: Could not read root_path."
    exit 1
fi


if [ -z "${CATCHMENT_NAME}" ]; then
    echo "ERROR: Could not read catchment_shp_name."
    exit 1
fi


if [ -z "${RIVER_NAME}" ]; then
    echo "ERROR: Could not read river_network_shp_name."
    exit 1
fi


if [ -z "${EMEARTH_GRID_NAME}" ]; then
    echo "ERROR: Could not read forcing_emearth_shape_name."
    exit 1
fi


if [ -z "${ERA5_GRID_NAME}" ]; then
    echo "ERROR: Could not read forcing_era5_shape_name."
    exit 1
fi


# ============================================================
# VALIDATE WORKFLOW FILES
# ============================================================

for FILE in \
    "${PREP_SCRIPT}" \
    "${GRID_SCRIPT}"
do

    if [ ! -f "${FILE}" ]; then

        echo "ERROR: Required workflow file not found:"
        echo "${FILE}"

        exit 1

    fi

done


# ============================================================
# ENVIRONMENT / LOG DIRECTORY
# ============================================================

module load conda/base


mkdir -p "${PREP_DIR}/slurm_logs"


# ============================================================
# DOMAIN OUTPUT PATHS
# ============================================================

DOMAIN_ROOT="${ROOT_PATH}/domain_${DOMAIN}"

CATCHMENT_FILE="${DOMAIN_ROOT}/shapefiles/catchment/${CATCHMENT_NAME}"

RIVER_FILE="${DOMAIN_ROOT}/shapefiles/river_network/${RIVER_NAME}"

FORCING_GRID_DIR="${DOMAIN_ROOT}/shapefiles/forcing"

EMEARTH_GRID="${FORCING_GRID_DIR}/${EMEARTH_GRID_NAME}"

ERA5_GRID="${FORCING_GRID_DIR}/${ERA5_GRID_NAME}"


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "NWAM MULTIBASIN DOMAIN + FORCING-GRID PREPROCESSING"
echo "======================================================================"
echo
echo "Slurm job ID  : ${SLURM_JOB_ID:-unknown}"
echo "Array task ID : ${SLURM_ARRAY_TASK_ID}"
echo "Task line     : ${LINE_NUMBER}"
echo
echo "Domain        : ${DOMAIN}"
echo "Control file  : ${CONTROL_FILE}"
echo "Task file     : ${TASK_FILE}"
echo
echo "Start time    : $(date)"
echo


# ============================================================
# STEP 1
# PREPARE DOMAIN SHAPEFILES
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "STEP 1: PREPARE DOMAIN SHAPEFILES"
echo "----------------------------------------------------------------------"
echo


bash "${PREP_SCRIPT}" \
    "${CONTROL_FILE}"


echo
echo "Domain preparation passed."


# ============================================================
# STEP 2
# CREATE FORCING GRID SHAPEFILES
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "STEP 2: CREATE ERA5 + EM-EARTH FORCING GRIDS"
echo "----------------------------------------------------------------------"
echo


cd "${FORCING_PREP_DIR}"


conda run --no-capture-output -n nwam \
    python "${GRID_SCRIPT}" \
    "${CONTROL_FILE}"


echo
echo "Forcing-grid creation passed."


# ============================================================
# STEP 3
# VERIFY PREPARED DOMAIN
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "STEP 3: VERIFY OUTPUTS"
echo "----------------------------------------------------------------------"
echo


if [ ! -f "${CATCHMENT_FILE}" ]; then

    echo "ERROR: Prepared catchment not found:"
    echo "${CATCHMENT_FILE}"

    exit 1

fi


if [ ! -f "${RIVER_FILE}" ]; then

    echo "ERROR: Prepared river network not found:"
    echo "${RIVER_FILE}"

    exit 1

fi


if [ ! -f "${EMEARTH_GRID}" ]; then

    echo "ERROR: EM-Earth forcing grid not found:"
    echo "${EMEARTH_GRID}"

    exit 1

fi


if [ ! -f "${ERA5_GRID}" ]; then

    echo "ERROR: ERA5 forcing grid not found:"
    echo "${ERA5_GRID}"

    exit 1

fi


# Check required shapefile components.

for SHAPEFILE in \
    "${CATCHMENT_FILE}" \
    "${RIVER_FILE}" \
    "${EMEARTH_GRID}" \
    "${ERA5_GRID}"
do

    BASE="${SHAPEFILE%.shp}"

    for EXT in shp shx dbf prj
    do

        COMPONENT="${BASE}.${EXT}"

        if [ ! -f "${COMPONENT}" ]; then

            echo "ERROR: Required shapefile component missing:"
            echo "${COMPONENT}"

            exit 1

        fi

    done

done


echo
echo "Prepared catchment : PASS"
echo "Prepared river     : PASS"
echo "EM-Earth grid      : PASS"
echo "ERA5 grid          : PASS"


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "NWAM PREPROCESSING COMPLETED SUCCESSFULLY"
echo "======================================================================"
echo
echo "Domain          : ${DOMAIN}"
echo "Control file    : ${CONTROL_FILE}"
echo
echo "Prepared catchment:"
echo "  ${CATCHMENT_FILE}"
echo
echo "Prepared river network:"
echo "  ${RIVER_FILE}"
echo
echo "EM-Earth grid:"
echo "  ${EMEARTH_GRID}"
echo
echo "ERA5 grid:"
echo "  ${ERA5_GRID}"
echo
echo "End time        : $(date)"
echo
echo "Next workflow stage:"
echo "  Prepare monthly ERA5 and EM-Earth forcing files."
echo
echo "No control_active.txt was used or modified."
echo