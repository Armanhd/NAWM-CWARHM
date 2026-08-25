#!/bin/bash

#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=2-00:00:00
#SBATCH --partition=cpu2025,cpu2023,cpu2022
#SBATCH --output=SUMMA_%A_%a.out
#SBATCH --error=SUMMA_%A_%a.err

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CWARHM="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONTROL="${CWARHM}/0_control_files/control_active.txt"


# ============================================================
# CONTROL READER
# ============================================================

read_control() {

    local key="$1"

    awk -F'|' -v key="$key" '

        /^[[:space:]]*#/ {
            next
        }

        NF >= 2 {

            left=$1
            gsub(/^[ \t]+|[ \t]+$/, "", left)

            if (left == key) {

                right=$2
                sub(/#.*/, "", right)
                gsub(/^[ \t]+|[ \t]+$/, "", right)

                print right
                exit
            }
        }

    ' "$CONTROL"
}


# ============================================================
# SETTINGS
# ============================================================

ROOT_PATH="$(read_control root_path)"
DOMAIN_NAME="$(read_control domain_name)"
EXPERIMENT_ID="$(read_control experiment_id)"

SUMMA_PATH="$(read_control install_path_summa)"
SUMMA_EXE="$(read_control exe_name_summa)"

SETTINGS_PATH="$(read_control settings_summa_path)"
FILEMANAGER="$(read_control settings_summa_filemanager)"

OUTPUT_PATH="$(read_control experiment_output_summa)"
LOG_PATH="$(read_control experiment_log_summa)"

DO_BACKUP="$(read_control experiment_backup_settings)"


# ============================================================
# DEFAULT PATHS
# ============================================================

if [ "$SUMMA_PATH" = "default" ]; then
    SUMMA_PATH="${ROOT_PATH}/installs/summa"
fi

if [ "$SETTINGS_PATH" = "default" ]; then
    SETTINGS_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/settings/SUMMA"
fi

if [ "$OUTPUT_PATH" = "default" ]; then
    OUTPUT_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/simulations/${EXPERIMENT_ID}/SUMMA"
fi

if [ "$LOG_PATH" = "default" ]; then
    LOG_PATH="${OUTPUT_PATH}/SUMMA_logs"
fi


SUMMA_EXEC="${SUMMA_PATH}/bin/${SUMMA_EXE}"
FILEMANAGER_PATH="${SETTINGS_PATH}/${FILEMANAGER}"


# ============================================================
# ARRAY PARAMETERS
# ============================================================

if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then

    echo
    echo "ERROR: this script must be run as a Slurm array job."

    exit 1
fi


GRUS_PER_TASK="${GRUS_PER_TASK:-10}"
TOTAL_GRUS="${TOTAL_GRUS:?TOTAL_GRUS was not supplied by submitter}"


if ! [[ "$GRUS_PER_TASK" =~ ^[1-9][0-9]*$ ]]; then

    echo
    echo "ERROR: GRUS_PER_TASK must be a positive integer."
    echo "Current value: $GRUS_PER_TASK"

    exit 1
fi


if ! [[ "$TOTAL_GRUS" =~ ^[1-9][0-9]*$ ]]; then

    echo
    echo "ERROR: TOTAL_GRUS must be a positive integer."
    echo "Current value: $TOTAL_GRUS"

    exit 1
fi


GRU_START=$(
    (
        SLURM_ARRAY_TASK_ID
        * GRUS_PER_TASK
        + 1
    )
)


GRU_COUNT="$GRUS_PER_TASK"


GRU_END=$(
    (
        GRU_START
        + GRU_COUNT
        - 1
    )
)


if [ "$GRU_END" -gt "$TOTAL_GRUS" ]; then

    GRU_COUNT=$(
        (
            TOTAL_GRUS
            - GRU_START
            + 1
        )
    )

fi


if [ "$GRU_COUNT" -le 0 ]; then

    echo
    echo "ERROR: calculated GRU_COUNT <= 0"
    echo "GRU_START: $GRU_START"
    echo "TOTAL_GRUS: $TOTAL_GRUS"

    exit 1
fi


LOG_FILE="${LOG_PATH}/summa_G${GRU_START}_${GRU_COUNT}_${SLURM_ARRAY_TASK_ID}.txt"


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base

conda activate nwam_parallel


if [ "${CONDA_DEFAULT_ENV:-}" != "nwam_parallel" ]; then

    echo
    echo "ERROR: Failed to activate nwam_parallel."
    echo "Active environment: ${CONDA_DEFAULT_ENV:-none}"

    exit 1
fi


export PATH="${CONDA_PREFIX}/bin:${PATH}"

export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"


# ============================================================
# REQUIRED FILE CHECKS
# ============================================================

if [ ! -x "$SUMMA_EXEC" ]; then

    echo
    echo "ERROR: SUMMA executable not found:"
    echo "$SUMMA_EXEC"

    exit 1
fi


if [ ! -f "$FILEMANAGER_PATH" ]; then

    echo
    echo "ERROR: SUMMA fileManager not found:"
    echo "$FILEMANAGER_PATH"

    exit 1
fi


# ============================================================
# OUTPUT DIRECTORIES
# ============================================================

mkdir -p "$OUTPUT_PATH"
mkdir -p "$LOG_PATH"


# ============================================================
# SETTINGS BACKUP
# ============================================================

if [ "$DO_BACKUP" = "yes" ] \
    && [ "$SLURM_ARRAY_TASK_ID" = "0" ]; then

    BACKUP_PATH="${OUTPUT_PATH}/run_settings"

    mkdir -p "$BACKUP_PATH"

    cp -R \
        "${SETTINGS_PATH}/." \
        "$BACKUP_PATH/"

fi


# ============================================================
# REPORT
# ============================================================

echo "============================================================"
echo "RUN SUMMA GRU SUBSET"
echo "============================================================"

echo "Domain       : $DOMAIN_NAME"
echo "Experiment   : $EXPERIMENT_ID"
echo "Environment  : $CONDA_DEFAULT_ENV"
echo "Array task   : $SLURM_ARRAY_TASK_ID"
echo "GRU start    : $GRU_START"
echo "GRU count    : $GRU_COUNT"
echo "Total GRUs   : $TOTAL_GRUS"
echo "Executable   : $SUMMA_EXEC"
echo "FileManager  : $FILEMANAGER_PATH"
echo "Output       : $OUTPUT_PATH"
echo "Log          : $LOG_FILE"
echo "Start        : $(date)"

echo "============================================================"


# ============================================================
# RUN SUMMA
# ============================================================

set +e

"$SUMMA_EXEC" \
    -g "$GRU_START" "$GRU_COUNT" \
    -m "$FILEMANAGER_PATH" \
    > "$LOG_FILE" 2>&1

STATUS=$?

set -e


# ============================================================
# VERIFY SUMMA SUCCESS
# ============================================================

MODEL_SUCCESS="no"


if grep -qi \
    "finished simulation successfully" \
    "$LOG_FILE"
then

    MODEL_SUCCESS="yes"

fi


if [ "$STATUS" -ne 0 ] \
    || [ "$MODEL_SUCCESS" != "yes" ]; then

    echo
    echo "============================================================"
    echo "SUMMA SUBSET FAILED"
    echo "============================================================"

    echo "Return code : $STATUS"
    echo "Model success message found: $MODEL_SUCCESS"

    echo
    echo "Last 40 lines of SUMMA log:"
    echo "------------------------------------------------------------"

    tail -40 "$LOG_FILE" || true

    exit 1
fi


# ============================================================
# SUCCESS
# ============================================================

echo
echo "============================================================"
echo "SUMMA SUBSET COMPLETED SUCCESSFULLY"
echo "============================================================"

echo "GRU start : $GRU_START"
echo "GRU count : $GRU_COUNT"
echo "End       : $(date)"

echo "============================================================"