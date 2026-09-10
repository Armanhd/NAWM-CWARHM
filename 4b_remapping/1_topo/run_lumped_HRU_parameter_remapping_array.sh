#!/bin/bash
#SBATCH --job-name=lumped_hru_param
#SBATCH --time=04:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1
#SBATCH --output=slurm_logs/lumped_hru_parameter_%A_%a.out
#SBATCH --error=slurm_logs/lumped_hru_parameter_%A_%a.err

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

SCRIPT_DIR="${CWARHM}/4b_remapping/1_topo"

ELEVATION_SCRIPT="${SCRIPT_DIR}/1_find_HRU_elevation_lumped.py"
SOIL_SCRIPT="${SCRIPT_DIR}/2_find_HRU_soil_classes_lumped.py"
LAND_SCRIPT="${SCRIPT_DIR}/3_find_HRU_land_classes_lumped.py"


# ============================================================
# ARGUMENT
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "ERROR: Lumped basin task file is required."
    echo
    echo "Usage:"
    echo "  sbatch --array=0-N \\"
    echo "    run_lumped_HRU_parameter_remapping_array.sh \\"
    echo "    /path/to/lumped_multibasin_preprocessing.txt"

    exit 1

fi


TASK_FILE=$(realpath "$1")


if [ ! -f "${TASK_FILE}" ]; then

    echo "ERROR: Task file not found:"
    echo "${TASK_FILE}"

    exit 1

fi


if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then

    echo "ERROR: SLURM_ARRAY_TASK_ID is not defined."

    exit 1

fi


# ============================================================
# CONTROL FILE
# ============================================================

LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))

CONTROL_FILE=$(
    sed -n "${LINE_NUMBER}p" "${TASK_FILE}" \
    | xargs
)


if [ -z "${CONTROL_FILE}" ]; then

    echo "ERROR: No control file for array index:"
    echo "${SLURM_ARRAY_TASK_ID}"

    exit 1

fi


CONTROL_FILE=$(realpath "${CONTROL_FILE}")


if [ ! -f "${CONTROL_FILE}" ]; then

    echo "ERROR: Control file not found:"
    echo "${CONTROL_FILE}"

    exit 1

fi


DOMAIN=$(awk -F'|' '
    /^[[:space:]]*domain_name[[:space:]]*\|/ {
        value=$2
        sub(/#.*/, "", value)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        print value
        exit
    }
' "${CONTROL_FILE}")


if [ -z "${DOMAIN}" ]; then

    echo "ERROR: Could not determine domain_name."

    exit 1

fi


# ============================================================
# VALIDATE SCRIPTS
# ============================================================

for FILE in \
    "${ELEVATION_SCRIPT}" \
    "${SOIL_SCRIPT}" \
    "${LAND_SCRIPT}"
do

    if [ ! -f "${FILE}" ]; then

        echo "ERROR: Required script not found:"
        echo "${FILE}"

        exit 1

    fi

done


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base

cd "${SCRIPT_DIR}"

mkdir -p slurm_logs


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "LUMPED HRU PARAMETER REMAPPING"
echo "======================================================================"
echo
echo "Job ID       : ${SLURM_JOB_ID:-unknown}"
echo "Array task   : ${SLURM_ARRAY_TASK_ID}"
echo "Domain       : ${DOMAIN}"
echo "Control file : ${CONTROL_FILE}"
echo "Start        : $(date)"
echo


# ============================================================
# ELEVATION
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "LUMPED ELEVATION"
echo "----------------------------------------------------------------------"

conda run --no-capture-output -n nwam \
    python "${ELEVATION_SCRIPT}" \
    "${CONTROL_FILE}"

echo
echo "PASS: ${DOMAIN} lumped elevation"


# ============================================================
# SOIL
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "LUMPED SOIL CLASSES"
echo "----------------------------------------------------------------------"

conda run --no-capture-output -n nwam \
    python "${SOIL_SCRIPT}" \
    "${CONTROL_FILE}"

echo
echo "PASS: ${DOMAIN} lumped soil classes"


# ============================================================
# LAND
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "LUMPED LAND CLASSES"
echo "----------------------------------------------------------------------"

conda run --no-capture-output -n nwam \
    python "${LAND_SCRIPT}" \
    "${CONTROL_FILE}"

echo
echo "PASS: ${DOMAIN} lumped land classes"


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "LUMPED HRU PARAMETER REMAPPING COMPLETED"
echo "======================================================================"
echo
echo "Domain : ${DOMAIN}"
echo "End    : $(date)"
echo
echo "PASS: ${DOMAIN}"