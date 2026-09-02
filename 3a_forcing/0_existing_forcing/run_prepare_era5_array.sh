#!/bin/bash
#SBATCH --job-name=era5_prep
#SBATCH --time=08:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --output=slurm_logs/era5_prep_%A_%a.out
#SBATCH --error=slurm_logs/era5_prep_%A_%a.err

# ============================================================
# MULTIBASIN ERA5 FORCING PREPARATION - CHUNKED WORKER
# ============================================================
#
# One Slurm array task processes MANY basin-month tasks.
#
# Task-file format:
#
#   control_file<TAB>year<TAB>month
#
# Example:
#
#   CHUNK_SIZE=500
#   N=$(wc -l < month_tasks.txt)
#   NJOBS=$(( (N + CHUNK_SIZE - 1) / CHUNK_SIZE ))
#
#   sbatch \
#       --array=0-$((NJOBS-1)) \
#       run_prepare_era5_array.sh \
#       month_tasks.txt \
#       "$CHUNK_SIZE"
#
# IMPORTANT
# ---------
# This script:
#
#   - does NOT use control_active.txt
#   - does NOT modify control files
#   - keeps the existing scientific Python workflow unchanged
#   - processes multiple monthly tasks inside one Slurm allocation
#
# ============================================================

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

WORKDIR="${CWARHM}/3a_forcing/0_existing_forcing"

PYTHON_SCRIPT="${WORKDIR}/3_prepare_era5_forcing.py"


# ============================================================
# ARGUMENTS
# ============================================================

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then

    echo "ERROR: Invalid number of arguments."
    echo
    echo "Usage:"
    echo "  sbatch --array=0-N \\"
    echo "    run_prepare_era5_array.sh \\"
    echo "    /path/to/month_tasks.txt \\"
    echo "    [CHUNK_SIZE]"
    echo
    echo "Example:"
    echo "  sbatch --array=0-21 \\"
    echo "    run_prepare_era5_array.sh \\"
    echo "    month_tasks.txt \\"
    echo "    500"

    exit 1

fi


TASK_FILE=$(realpath "$1")

CHUNK_SIZE="${2:-500}"


# ============================================================
# VALIDATE INPUTS
# ============================================================

if [ ! -f "${TASK_FILE}" ]; then

    echo "ERROR: Task file not found:"
    echo "${TASK_FILE}"

    exit 1

fi


if ! [[ "${CHUNK_SIZE}" =~ ^[0-9]+$ ]] || [ "${CHUNK_SIZE}" -lt 1 ]; then

    echo "ERROR: CHUNK_SIZE must be a positive integer."
    echo "Received: ${CHUNK_SIZE}"

    exit 1

fi


if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then

    echo "ERROR: SLURM_ARRAY_TASK_ID is not defined."
    echo "Submit this script using a Slurm array."

    exit 1

fi


if [ ! -f "${PYTHON_SCRIPT}" ]; then

    echo "ERROR: Python script not found:"
    echo "${PYTHON_SCRIPT}"

    exit 1

fi


# ============================================================
# CALCULATE CHUNK RANGE
# ============================================================

TOTAL_TASKS=$(wc -l < "${TASK_FILE}")

START_INDEX=$((SLURM_ARRAY_TASK_ID * CHUNK_SIZE))
END_INDEX=$((START_INDEX + CHUNK_SIZE - 1))

if [ "${START_INDEX}" -ge "${TOTAL_TASKS}" ]; then

    echo "ERROR: Chunk starts beyond end of task file."
    echo
    echo "Array task ID : ${SLURM_ARRAY_TASK_ID}"
    echo "Chunk size    : ${CHUNK_SIZE}"
    echo "Start index   : ${START_INDEX}"
    echo "Total tasks   : ${TOTAL_TASKS}"

    exit 1

fi


if [ "${END_INDEX}" -ge "${TOTAL_TASKS}" ]; then
    END_INDEX=$((TOTAL_TASKS - 1))
fi


START_LINE=$((START_INDEX + 1))
END_LINE=$((END_INDEX + 1))

TASK_COUNT=$((END_INDEX - START_INDEX + 1))


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base

cd "${WORKDIR}"


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "MULTIBASIN ERA5 FORCING PREPARATION - CHUNKED"
echo "======================================================================"
echo
echo "Slurm job ID       : ${SLURM_JOB_ID:-unknown}"
echo "Array task ID      : ${SLURM_ARRAY_TASK_ID}"
echo
echo "Task file          : ${TASK_FILE}"
echo "Python script      : ${PYTHON_SCRIPT}"
echo
echo "Total monthly tasks: ${TOTAL_TASKS}"
echo "Chunk size         : ${CHUNK_SIZE}"
echo "Chunk start index  : ${START_INDEX}"
echo "Chunk end index    : ${END_INDEX}"
echo "Task-file lines    : ${START_LINE}-${END_LINE}"
echo "Tasks in this job  : ${TASK_COUNT}"
echo
echo "Start time         : $(date)"
echo


# ============================================================
# PROCESS CHUNK
# ============================================================

PROCESSED=0
FAILED=0

for TASK_INDEX in $(seq "${START_INDEX}" "${END_INDEX}"); do

    LINE_NUMBER=$((TASK_INDEX + 1))

    TASK_LINE=$(sed -n "${LINE_NUMBER}p" "${TASK_FILE}")

    if [ -z "${TASK_LINE}" ]; then

        echo
        echo "ERROR: No task found at task-file line ${LINE_NUMBER}"
        FAILED=$((FAILED + 1))
        continue

    fi


    # --------------------------------------------------------
    # PARSE TASK
    # --------------------------------------------------------

    IFS=$'\t' read -r CONTROL_FILE YEAR MONTH <<< "${TASK_LINE}"


    if [ -z "${CONTROL_FILE:-}" ] || \
       [ -z "${YEAR:-}" ] || \
       [ -z "${MONTH:-}" ]; then

        echo
        echo "ERROR: Invalid task-file row:"
        echo "${TASK_LINE}"

        FAILED=$((FAILED + 1))
        continue

    fi


    CONTROL_FILE=$(realpath "${CONTROL_FILE}")


    # --------------------------------------------------------
    # VALIDATE TASK
    # --------------------------------------------------------

    if [ ! -f "${CONTROL_FILE}" ]; then

        echo
        echo "ERROR: Control file not found:"
        echo "${CONTROL_FILE}"

        FAILED=$((FAILED + 1))
        continue

    fi


    if ! [[ "${YEAR}" =~ ^[0-9]{4}$ ]]; then

        echo
        echo "ERROR: Invalid year: ${YEAR}"

        FAILED=$((FAILED + 1))
        continue

    fi


    if ! [[ "${MONTH}" =~ ^[0-9]{1,2}$ ]]; then

        echo
        echo "ERROR: Invalid month: ${MONTH}"

        FAILED=$((FAILED + 1))
        continue

    fi


    if [ "${MONTH}" -lt 1 ] || [ "${MONTH}" -gt 12 ]; then

        echo
        echo "ERROR: Month must be between 1 and 12."
        echo "Received: ${MONTH}"

        FAILED=$((FAILED + 1))
        continue

    fi


    # --------------------------------------------------------
    # DOMAIN
    # --------------------------------------------------------

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

        echo
        echo "ERROR: Could not read domain_name from:"
        echo "${CONTROL_FILE}"

        FAILED=$((FAILED + 1))
        continue

    fi


    printf -v MONTH2 "%02d" "${MONTH}"
    YM="${YEAR}${MONTH2}"


    # --------------------------------------------------------
    # REPORT TASK
    # --------------------------------------------------------

    echo
    echo "----------------------------------------------------------------------"
    echo "TASK ${TASK_INDEX} / FILE LINE ${LINE_NUMBER}"
    echo "----------------------------------------------------------------------"
    echo "Domain       : ${DOMAIN}"
    echo "Control file : ${CONTROL_FILE}"
    echo "Month        : ${YM}"
    echo "Start        : $(date)"


    # --------------------------------------------------------
    # RUN EXISTING PYTHON WORKER
    # --------------------------------------------------------

    if conda run --no-capture-output -n nwam \
        python "${PYTHON_SCRIPT}" \
        "${CONTROL_FILE}" \
        "${YEAR}" \
        "${MONTH}"
    then

        PROCESSED=$((PROCESSED + 1))

        echo
        echo "PASS: ${DOMAIN} ${YM}"

    else

        FAILED=$((FAILED + 1))

        echo
        echo "FAIL: ${DOMAIN} ${YM}"

    fi

done


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "ERA5 FORCING PREPARATION CHUNK COMPLETED"
echo "======================================================================"
echo
echo "Array task ID : ${SLURM_ARRAY_TASK_ID}"
echo "Task indices  : ${START_INDEX}-${END_INDEX}"
echo "Expected      : ${TASK_COUNT}"
echo "Completed     : ${PROCESSED}"
echo "Failed        : ${FAILED}"
echo "End time      : $(date)"
echo
echo "No control_active.txt was used or modified."
echo


if [ "${FAILED}" -gt 0 ]; then
    echo "ERROR: ${FAILED} task(s) failed in this chunk."
    exit 1
fi