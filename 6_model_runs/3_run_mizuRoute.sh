#!/bin/bash

#SBATCH --job-name=mizuRoute
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=2-00:00:00
#SBATCH --partition=cpu2025,cpu2023,cpu2022
#SBATCH --output=mizuRoute_%j.out
#SBATCH --error=mizuRoute_%j.err

set -euo pipefail


# ============================================================
# SAFETY
# ============================================================

# Current NWAM mizuRoute build uses serial NetCDF through PIO.
# Multi-rank runs were demonstrated to corrupt history-file
# record indices. Do not enable >1 task until mizuRoute is
# rebuilt and verified with parallel-safe PIO.
if [ "${SLURM_NTASKS:-1}" -ne 1 ]; then

    echo "ERROR:"
    echo "Current NWAM mizuRoute build is validated only with 1 MPI task."
    echo "Multi-rank PIO output corrupted NetCDF timestamps during testing."

    exit 1
fi


# ============================================================
# PATHS / CONTROL
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CWARHM="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONTROL="${CWARHM}/0_control_files/control_active.txt"


read_control() {

    local key="$1"

    awk -F'|' -v key="$key" '
        /^[[:space:]]*#/ {next}

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


ROOT_PATH="$(read_control root_path)"
DOMAIN_NAME="$(read_control domain_name)"
EXPERIMENT_ID="$(read_control experiment_id)"

MIZU_PATH="$(read_control install_path_mizuroute)"
MIZU_EXE="$(read_control exe_name_mizuroute)"

SETTINGS_PATH="$(read_control settings_mizu_path)"
CONTROL_NAME="$(read_control settings_mizu_control_file)"

OUTPUT_PATH="$(read_control experiment_output_mizuRoute)"
LOG_PATH="$(read_control experiment_log_mizuroute)"

DO_BACKUP="$(read_control experiment_backup_settings)"


if [ "$MIZU_PATH" = "default" ]; then
    MIZU_PATH="${ROOT_PATH}/installs/mizuRoute"
fi

if [ "$SETTINGS_PATH" = "default" ]; then
    SETTINGS_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/settings/mizuRoute"
fi

if [ "$OUTPUT_PATH" = "default" ]; then
    OUTPUT_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/simulations/${EXPERIMENT_ID}/mizuRoute"
fi

if [ "$LOG_PATH" = "default" ]; then
    LOG_PATH="${OUTPUT_PATH}/mizuRoute_logs"
fi


MIZU_EXEC="${MIZU_PATH}/route/bin/${MIZU_EXE}"
CONTROL_FILE="${SETTINGS_PATH}/${CONTROL_NAME}"

LOG_FILE="${LOG_PATH}/mizuRoute_log.txt"


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base
conda activate nwam

export PATH="${CONDA_PREFIX}/bin:${PATH}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"


# ============================================================
# CHECKS
# ============================================================

if [ ! -x "$MIZU_EXEC" ]; then
    echo "ERROR: mizuRoute executable not found:"
    echo "$MIZU_EXEC"
    exit 1
fi

if [ ! -f "$CONTROL_FILE" ]; then
    echo "ERROR: mizuRoute control file not found:"
    echo "$CONTROL_FILE"
    exit 1
fi


mkdir -p "$OUTPUT_PATH"
mkdir -p "$LOG_PATH"


# ============================================================
# BACKUP
# ============================================================

if [ "$DO_BACKUP" = "yes" ]; then

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
echo "RUN MIZUROUTE"
echo "============================================================"

echo "Domain      : $DOMAIN_NAME"
echo "Experiment  : $EXPERIMENT_ID"
echo "MPI tasks   : 1"
echo "Executable  : $MIZU_EXEC"
echo "Control     : $CONTROL_FILE"
echo "Output      : $OUTPUT_PATH"
echo "Log         : $LOG_FILE"
echo "Start       : $(date)"

echo "============================================================"


# ============================================================
# RUN
# ============================================================

set +e

"$MIZU_EXEC" "$CONTROL_FILE" \
    > "$LOG_FILE" 2>&1

STATUS=$?

set -e


# ============================================================
# VERIFY
# ============================================================

MODEL_SUCCESS="no"

if grep -q "SUCCESSFUL EXECUTION" "$LOG_FILE"; then
    MODEL_SUCCESS="yes"
fi


if [ "$STATUS" -ne 0 ] || [ "$MODEL_SUCCESS" != "yes" ]; then

    echo
    echo "MIZUROUTE FAILED"
    echo "Return code: $STATUS"
    echo

    tail -60 "$LOG_FILE" || true

    exit 1
fi


echo
echo "MIZUROUTE COMPLETED SUCCESSFULLY"
echo "Executable return code: $STATUS"
echo "End: $(date)"