#!/bin/bash
#SBATCH --job-name=emearth_remap
#SBATCH --time=02:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1

# ============================================================
# MULTIBASIN EM-EARTH REMAPPING SLURM WORKER
# ============================================================
#
# Purpose
# -------
# Process one basin-month EM-Earth remapping task.
#
# Each SLURM_ARRAY_TASK_ID selects one row from a task file.
#
# Task-file format:
#
#   control_file<TAB>year<TAB>month
#
# Example:
#
# /work/.../control_MERIT_717.txt    1950    1
# /work/.../control_MERIT_717.txt    1950    2
# /work/.../control_MERIT_718.txt    1950    1
#
# IMPORTANT
# ---------
# This script:
#
#   - does NOT use control_active.txt
#   - does NOT modify any control file
#   - is safe for simultaneous multibasin execution
#
# Submission example:
#
#   N=$(wc -l < multibasin_month_tasks.txt)
#
#   sbatch \
#     --array=0-$((N-1))%20 \
#     run_remap_EM_Earth_array.sh \
#     multibasin_month_tasks.txt
#
# ============================================================

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

SCRIPT_DIR="${CWARHM}/4b_remapping/2_forcing"

PYTHON_SCRIPT="${SCRIPT_DIR}/2b_remap_all_EM_Earth.py"


# ============================================================
# CHECK TASK FILE ARGUMENT
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "ERROR: A task file must be supplied."
    echo
    echo "Usage:"
    echo "  sbatch --array=0-N%20 \\"
    echo "    run_remap_EM_Earth_array.sh \\"
    echo "    /path/to/multibasin_month_tasks.txt"

    exit 1

fi


TASK_FILE="$1"


if [ ! -f "${TASK_FILE}" ]; then

    echo "ERROR: Task file not found:"
    echo "${TASK_FILE}"

    exit 1

fi


# ============================================================
# CHECK SLURM ARRAY ID
# ============================================================

if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then

    echo "ERROR: SLURM_ARRAY_TASK_ID is not defined."
    echo "Submit this script as a Slurm array."

    exit 1

fi


# ============================================================
# READ TASK
# ============================================================

LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))

TASK_LINE=$(sed -n "${LINE_NUMBER}p" "${TASK_FILE}")


if [ -z "${TASK_LINE}" ]; then

    echo "ERROR: No task found for array index:"
    echo "${SLURM_ARRAY_TASK_ID}"

    echo
    echo "Task file:"
    echo "${TASK_FILE}"

    exit 1

fi


IFS=$'\t' read -r CONTROL_FILE YEAR MONTH <<< "${TASK_LINE}"


# ============================================================
# VALIDATE TASK
# ============================================================

if [ -z "${CONTROL_FILE:-}" ] || \
   [ -z "${YEAR:-}" ] || \
   [ -z "${MONTH:-}" ]; then

    echo "ERROR: Invalid task-file row:"
    echo "${TASK_LINE}"

    echo
    echo "Expected format:"
    echo "control_file<TAB>year<TAB>month"

    exit 1

fi


if [ ! -f "${CONTROL_FILE}" ]; then

    echo "ERROR: Control file not found:"
    echo "${CONTROL_FILE}"

    exit 1

fi


if ! [[ "${YEAR}" =~ ^[0-9]{4}$ ]]; then

    echo "ERROR: Invalid year:"
    echo "${YEAR}"

    exit 1

fi


if ! [[ "${MONTH}" =~ ^[0-9]{1,2}$ ]]; then

    echo "ERROR: Invalid month:"
    echo "${MONTH}"

    exit 1

fi


if [ "${MONTH}" -lt 1 ] || [ "${MONTH}" -gt 12 ]; then

    echo "ERROR: Month must be between 1 and 12."
    echo "Received: ${MONTH}"

    exit 1

fi


# ============================================================
# READ DOMAIN NAME FOR REPORTING
# ============================================================

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

    echo "ERROR: Could not read domain_name from:"
    echo "${CONTROL_FILE}"

    exit 1

fi


# ============================================================
# VALIDATE PYTHON SCRIPT
# ============================================================

if [ ! -f "${PYTHON_SCRIPT}" ]; then

    echo "ERROR: EM-Earth remapping script not found:"
    echo "${PYTHON_SCRIPT}"

    exit 1

fi


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "MULTIBASIN EM-EARTH HRU REMAPPING"
echo "======================================================================"
echo
echo "Slurm job ID       : ${SLURM_JOB_ID:-unknown}"
echo "Array task ID      : ${SLURM_ARRAY_TASK_ID}"
echo "Task-file line     : ${LINE_NUMBER}"
echo
echo "Domain             : ${DOMAIN}"
echo "Control file       : ${CONTROL_FILE}"
echo "Year               : ${YEAR}"
echo "Month              : ${MONTH}"
echo
echo "Python script      : ${PYTHON_SCRIPT}"
echo "Task file          : ${TASK_FILE}"
echo


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base


cd "${SCRIPT_DIR}"


# ============================================================
# RUN EM-EARTH REMAPPING
# ============================================================

conda run --no-capture-output -n nwam \
    python "${PYTHON_SCRIPT}" \
    "${CONTROL_FILE}" \
    "${YEAR}" \
    "${MONTH}"


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "EM-EARTH ARRAY TASK COMPLETED"
echo "======================================================================"
echo
echo "Domain : ${DOMAIN}"
echo "Month  : ${YEAR}-$(printf '%02d' "${MONTH}")"
echo
echo "No control_active.txt was used or modified."