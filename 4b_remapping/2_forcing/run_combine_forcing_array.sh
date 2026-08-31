#!/bin/bash
#SBATCH --job-name=combine_forcing
#SBATCH --time=01:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1

# ============================================================
# MULTIBASIN SUMMA FORCING COMBINATION SLURM WORKER
# ============================================================
#
# Purpose
# -------
# Process one basin-month task and combine:
#
#   ERA5:
#       airpres
#       LWRadAtm
#       SWRadAtm
#       spechum
#       windspd
#
# with EM-Earth:
#       pptrate
#       airtemp
#
# into:
#
#   NWAM_SUMMA_forcing_YYYYMM.nc
#
# Each SLURM_ARRAY_TASK_ID selects one row from a task file.
#
# Task-file format:
#
#   control_file<TAB>year<TAB>month
#
# Example:
#
# /work/.../control_MERIT_861.txt    1950    1
# /work/.../control_MERIT_861.txt    1950    2
# /work/.../control_MERIT_862.txt    1950    1
#
# IMPORTANT
# ---------
# This script:
#
#   - does NOT use control_active.txt
#   - does NOT modify any control file
#   - is safe for simultaneous multibasin execution
#   - uses the same task file as the ERA5 and EM-Earth
#     remapping workers
#
# Submission example:
#
#   TASK_FILE="/work/comphyd_lab/users/arman.haddadchi/NWAM/\
# CWARHM_multibasin/0_control_files/\
# multibasin_month_tasks_MERIT_86.txt"
#
#   N=$(wc -l < "${TASK_FILE}")
#
#   sbatch \
#       --array=0-$((N-1))%20 \
#       run_combine_forcing_array.sh \
#       "${TASK_FILE}"
#
# ============================================================

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

SCRIPT_DIR="${CWARHM}/4b_remapping/2_forcing"

PYTHON_SCRIPT="${SCRIPT_DIR}/3_combine_forcing_for_SUMMA.py"


# ============================================================
# CHECK TASK FILE ARGUMENT
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "ERROR: A task file must be supplied."
    echo
    echo "Usage:"
    echo "  sbatch --array=0-N%20 \\"
    echo "    run_combine_forcing_array.sh \\"
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

    echo "ERROR: Forcing-combination script not found:"
    echo "${PYTHON_SCRIPT}"

    exit 1

fi


# ============================================================
# REPORT
# ============================================================

printf -v MONTH2 "%02d" "${MONTH}"

YM="${YEAR}${MONTH2}"


echo
echo "======================================================================"
echo "MULTIBASIN SUMMA FORCING COMBINATION"
echo "======================================================================"
echo
echo "Slurm job ID       : ${SLURM_JOB_ID:-unknown}"
echo "Array task ID      : ${SLURM_ARRAY_TASK_ID}"
echo "Task-file line     : ${LINE_NUMBER}"
echo
echo "Domain             : ${DOMAIN}"
echo "Control file       : ${CONTROL_FILE}"
echo "Year               : ${YEAR}"
echo "Month              : ${MONTH2}"
echo "YYYYMM             : ${YM}"
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
# COMBINE ERA5 + EM-EARTH FOR SUMMA
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
echo "SUMMA FORCING COMBINATION ARRAY TASK COMPLETED"
echo "======================================================================"
echo
echo "Domain : ${DOMAIN}"
echo "Month  : ${YEAR}-${MONTH2}"
echo
echo "No control_active.txt was used or modified."