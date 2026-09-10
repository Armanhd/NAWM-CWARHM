#!/bin/bash

#SBATCH --job-name=summa_lst_lump
#SBATCH --time=00:30:00
#SBATCH --mem=2G
#SBATCH --cpus-per-task=1
#SBATCH --exclude=fc1
#SBATCH --output=slurm_logs/summa_lst_lumped_%A_%a.out
#SBATCH --error=slurm_logs/summa_lst_lumped_%A_%a.err

set -eo pipefail


if [[ $# -ne 1 ]]; then
    echo "Usage:"
    echo "sbatch --array=0-N run_create_summa_LST_runtime_lumped_array.sh LUMPED_BASIN_TASK"
    exit 1
fi


LUMPED_BASIN_TASK="$1"


CONTROL_FILE=$(sed -n \
    "$((SLURM_ARRAY_TASK_ID + 1))p" \
    "$LUMPED_BASIN_TASK")


if [[ -z "$CONTROL_FILE" ]]; then
    echo "ERROR: No control file for array task."
    exit 1
fi


if [[ ! -f "$CONTROL_FILE" ]]; then
    echo "ERROR: Control file does not exist:"
    echo "$CONTROL_FILE"
    exit 1
fi


ROOT="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

FILE_LIST_SCRIPT="${ROOT}/5_model_input/SUMMA/1c_forcing_file_list/1_create_forcing_file_list_LST_lumped.py"

FILE_MANAGER_SCRIPT="${ROOT}/5_model_input/SUMMA/1b_file_manager/1_create_file_manager_LST_lumped.py"


source ~/.bashrc
conda activate nwam


echo "============================================================"
echo "CREATE LUMPED SUMMA LST RUNTIME"
echo "============================================================"
echo "Task ID      : ${SLURM_ARRAY_TASK_ID}"
echo "Control file : ${CONTROL_FILE}"
echo "============================================================"


python "$FILE_LIST_SCRIPT" \
    "$CONTROL_FILE"


python "$FILE_MANAGER_SCRIPT" \
    "$CONTROL_FILE"


echo
echo "============================================================"
echo "PASS: LUMPED SUMMA LST RUNTIME"
echo "============================================================"