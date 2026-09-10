#!/bin/bash

#SBATCH --job-name=utc_to_lst_lump
#SBATCH --time=02:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --exclude=fc1
#SBATCH --output=slurm_logs/utc_to_lst_lumped_%A_%a.out
#SBATCH --error=slurm_logs/utc_to_lst_lumped_%A_%a.err

set -eo pipefail


# ============================================================
# PATHS
# ============================================================

SCRIPT_DIR="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/3a_forcing/5_utc_to_lst"


# ============================================================
# INPUT LUMPED BASIN TASK FILE
# ============================================================

if [[ $# -ne 1 ]]; then

    echo "Usage:"
    echo "sbatch --array=0-N run_convert_concat_utc_to_lst_lumped_array.sh LUMPED_BASIN_TASK"

    exit 1

fi


LUMPED_BASIN_TASK="$1"


if [[ ! -f "${LUMPED_BASIN_TASK}" ]]; then

    echo "ERROR: Lumped basin task file not found:"
    echo "${LUMPED_BASIN_TASK}"

    exit 1

fi


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


# ============================================================
# VERIFY THIS REALLY IS A LUMPED CONTROL
# ============================================================

if [[ "${CONTROL_FILE}" != *_lumped.txt ]]; then

    echo "ERROR: Expected a lumped control file:"
    echo "${CONTROL_FILE}"

    exit 1

fi


# ============================================================
# DOMAIN
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


if [[ -z "${DOMAIN}" ]]; then

    echo "ERROR: Could not read domain_name from:"
    echo "${CONTROL_FILE}"

    exit 1

fi


echo "============================================================"
echo "LUMPED CONCATENATED UTC -> LST"
echo "============================================================"

echo "SLURM JOB ID  : ${SLURM_JOB_ID}"
echo "ARRAY TASK ID : ${SLURM_ARRAY_TASK_ID}"
echo "BASIN TASK    : ${LUMPED_BASIN_TASK}"
echo "CONTROL FILE  : ${CONTROL_FILE}"
echo "DOMAIN        : ${DOMAIN}"

echo "============================================================"


# ============================================================
# ENVIRONMENT
# ============================================================

source ~/.bashrc

conda activate nwam

set -u


echo
echo "Python:"
which python
python --version
echo


# ============================================================
# RUN
# ============================================================

python \
    "${SCRIPT_DIR}/1_convert_concat_utc_to_lst_lumped.py" \
    --control-file \
    "${CONTROL_FILE}"


echo
echo "============================================================"
echo "DONE: ${DOMAIN}"
echo "============================================================"