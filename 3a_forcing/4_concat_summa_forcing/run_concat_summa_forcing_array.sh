#!/bin/bash

#SBATCH --job-name=summa_concat
#SBATCH --time=02:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --exclude=fc1
#SBATCH --output=slurm_logs/summa_concat_%A_%a.out
#SBATCH --error=slurm_logs/summa_concat_%A_%a.err

set -eo pipefail


# ============================================================
# PATHS
# ============================================================

SCRIPT_DIR="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/3a_forcing/4_concat_summa_forcing"


# ============================================================
# INPUT BASIN TASK FILE
# ============================================================

if [[ $# -ne 1 ]]; then

    echo "Usage:"
    echo "sbatch --array=0-N run_concat_summa_forcing_array.sh BASIN_TASK"

    exit 1

fi


BASIN_TASK="$1"


if [[ ! -f "${BASIN_TASK}" ]]; then

    echo "ERROR: Basin task file not found:"
    echo "${BASIN_TASK}"

    exit 1

fi


# ============================================================
# CONCATENATION PERIOD
# ============================================================

START_YEAR=1950
START_MONTH=1

END_YEAR=2019
END_MONTH=12


# ============================================================
# CONTROL FILE
# ============================================================

CONTROL_FILE=$(sed -n \
    "$((SLURM_ARRAY_TASK_ID + 1))p" \
    "${BASIN_TASK}")


if [[ -z "${CONTROL_FILE}" ]]; then

    echo "ERROR: No control file found for array task ${SLURM_ARRAY_TASK_ID}"

    exit 1

fi


if [[ ! -f "${CONTROL_FILE}" ]]; then

    echo "ERROR: Control file does not exist:"
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


if [[ -z "${DOMAIN}" ]]; then

    echo "ERROR: Could not read domain_name from:"
    echo "${CONTROL_FILE}"

    exit 1

fi


echo "============================================================"
echo "DISTRIBUTED SUMMA FORCING CONCATENATION"
echo "============================================================"

echo "SLURM JOB ID   : ${SLURM_JOB_ID}"
echo "ARRAY TASK ID  : ${SLURM_ARRAY_TASK_ID}"
echo "BASIN TASK     : ${BASIN_TASK}"
echo "CONTROL FILE   : ${CONTROL_FILE}"
echo "DOMAIN         : ${DOMAIN}"

echo "START          : ${START_YEAR}-$(printf '%02d' "${START_MONTH}")"
echo "END            : ${END_YEAR}-$(printf '%02d' "${END_MONTH}")"

echo "TIME HANDLING  : preserve existing monthly UTC timestamps"

echo "============================================================"


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base

conda activate nwam

set -u

echo
echo "Python executable:"
which python
python --version
echo


# ============================================================
# RUN CONCATENATION
# ============================================================

python "${SCRIPT_DIR}/concat_summa_forcing.py" \
    --control-file "${CONTROL_FILE}" \
    --start-year "${START_YEAR}" \
    --start-month "${START_MONTH}" \
    --end-year "${END_YEAR}" \
    --end-month "${END_MONTH}"


echo
echo "============================================================"
echo "DONE: ${DOMAIN}"
echo "============================================================"