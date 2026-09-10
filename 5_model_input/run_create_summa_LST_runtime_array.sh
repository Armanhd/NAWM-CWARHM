#!/bin/bash

#SBATCH --job-name=summa_lst_cfg
#SBATCH --time=00:30:00
#SBATCH --mem=2G
#SBATCH --cpus-per-task=1
#SBATCH --output=slurm_logs/summa_lst_cfg_%A_%a.out
#SBATCH --error=slurm_logs/summa_lst_cfg_%A_%a.err

set -eo pipefail


# ============================================================
# PATHS
# ============================================================

SUMMA_DIR="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/5_model_input/SUMMA"

FORCING_LIST_SCRIPT="${SUMMA_DIR}/1c_forcing_file_list/1_create_forcing_file_list_LST.py"

FILE_MANAGER_SCRIPT="${SUMMA_DIR}/1b_file_manager/1_create_file_manager_LST.py"


# ============================================================
# BASIN TASK
# ============================================================

if [[ $# -ne 1 ]]; then
    echo "Usage:"
    echo "sbatch --array=0-N run_create_summa_LST_runtime_array.sh BASIN_TASK"
    exit 1
fi


BASIN_TASK="$1"


if [[ ! -f "${BASIN_TASK}" ]]; then
    echo "ERROR: Basin task file not found:"
    echo "${BASIN_TASK}"
    exit 1
fi


CONTROL_FILE=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "${BASIN_TASK}")


if [[ -z "${CONTROL_FILE}" ]]; then
    echo "ERROR: No control file for array task ${SLURM_ARRAY_TASK_ID}"
    exit 1
fi


if [[ ! -f "${CONTROL_FILE}" ]]; then
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


echo "============================================================"
echo "CREATE SUMMA LST RUNTIME CONFIGURATION"
echo "============================================================"
echo "ARRAY TASK   : ${SLURM_ARRAY_TASK_ID}"
echo "CONTROL FILE : ${CONTROL_FILE}"
echo "DOMAIN       : ${DOMAIN}"
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
# CREATE LST FORCING LIST
# ============================================================

python "${FORCING_LIST_SCRIPT}" \
    "${CONTROL_FILE}"


# ============================================================
# CREATE LST FILE MANAGER
# ============================================================

python "${FILE_MANAGER_SCRIPT}" \
    "${CONTROL_FILE}"


echo
echo "============================================================"
echo "PASS: SUMMA LST RUNTIME CONFIGURATION"
echo "DOMAIN: ${DOMAIN}"
echo "============================================================"