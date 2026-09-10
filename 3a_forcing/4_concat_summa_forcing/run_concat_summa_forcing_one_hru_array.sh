#!/bin/bash

#SBATCH --job-name=summa_concat_1hru
#SBATCH --time=02:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --exclude=fc1
#SBATCH --output=slurm_logs/summa_concat_1hru_%A_%a.out
#SBATCH --error=slurm_logs/summa_concat_1hru_%A_%a.err

set -eo pipefail


# ============================================================
# PATHS
# ============================================================

SCRIPT_DIR="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/3a_forcing/4_concat_summa_forcing"


# ============================================================
# INPUT LUMPED BASIN TASK FILE
# ============================================================

if [[ $# -ne 1 ]]; then

    echo "Usage:"
    echo "sbatch --array=0-N run_concat_summa_forcing_one_hru_array.sh LUMPED_BASIN_TASK"

    exit 1

fi


LUMPED_BASIN_TASK="$1"


if [[ ! -f "${LUMPED_BASIN_TASK}" ]]; then

    echo "ERROR: Lumped basin task file not found:"
    echo "${LUMPED_BASIN_TASK}"

    exit 1

fi


# ============================================================
# OPTIONAL DATE FILTER
# ============================================================
#
# Leave empty to concatenate every available monthly file.
#
# Example:
#
# START_YM="198110"
# END_YM="198909"

START_YM=""
END_YM=""


# ============================================================
# CONTROL FILE
# ============================================================

CONTROL_FILE=$(sed -n \
    "$((SLURM_ARRAY_TASK_ID + 1))p" \
    "${LUMPED_BASIN_TASK}")


if [[ -z "${CONTROL_FILE}" ]]; then

    echo "ERROR: No lumped control file found for array task ${SLURM_ARRAY_TASK_ID}"

    exit 1

fi


if [[ ! -f "${CONTROL_FILE}" ]]; then

    echo "ERROR: Lumped control file does not exist:"
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
echo "LUMPED SUMMA FORCING CONCATENATION"
echo "============================================================"

echo "SLURM JOB ID  : ${SLURM_JOB_ID}"
echo "ARRAY TASK ID : ${SLURM_ARRAY_TASK_ID}"
echo "BASIN TASK    : ${LUMPED_BASIN_TASK}"
echo "CONTROL FILE  : ${CONTROL_FILE}"
echo "DOMAIN        : ${DOMAIN}"
echo "START_YM      : ${START_YM:-ALL}"
echo "END_YM        : ${END_YM:-ALL}"
echo "TIME HANDLING : preserve existing monthly UTC timestamps"

echo "============================================================"


# ============================================================
# ENVIRONMENT
# ============================================================

source ~/.bashrc

conda activate nwam

set -u


echo
echo "Python executable:"
which python
python --version
echo


# ============================================================
# BUILD COMMAND
# ============================================================

CMD=(
    python
    "${SCRIPT_DIR}/concat_summa_forcing_one_hru.py"
    --control-file
    "${CONTROL_FILE}"
)


if [[ -n "${START_YM}" ]]; then

    CMD+=(
        --start-ym
        "${START_YM}"
    )

fi


if [[ -n "${END_YM}" ]]; then

    CMD+=(
        --end-ym
        "${END_YM}"
    )

fi


# ============================================================
# RUN
# ============================================================

echo "Command:"

printf ' %q' "${CMD[@]}"

echo
echo


"${CMD[@]}"


echo
echo "============================================================"
echo "DONE: ${DOMAIN}"
echo "============================================================"