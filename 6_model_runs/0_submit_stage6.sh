#!/bin/bash

set -euo pipefail


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
SETTINGS_PATH="$(read_control settings_summa_path)"
ATTRIBUTES_NAME="$(read_control settings_summa_attributes)"


if [ "$SETTINGS_PATH" = "default" ]; then

    SETTINGS_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/settings/SUMMA"
fi


ATTRIBUTES="${SETTINGS_PATH}/${ATTRIBUTES_NAME}"


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base
conda activate nwam


# ============================================================
# PREPARE
# ============================================================

python \
    "${SCRIPT_DIR}/0_prepare_stage6.py"


# ============================================================
# NUMBER OF GRUS
# ============================================================

TOTAL_GRUS="$(
python - "$ATTRIBUTES" <<'PY'
import sys
import netCDF4 as nc

with nc.Dataset(sys.argv[1]) as ds:
    print(len(ds.dimensions["gru"]))
PY
)"


# Tunable without editing scripts:
#
# GRUS_PER_TASK=20 MAX_CONCURRENT=24 ./0_submit_stage6.sh

GRUS_PER_TASK="${GRUS_PER_TASK:-10}"
MAX_CONCURRENT="${MAX_CONCURRENT:-32}"


N_TASKS=$(
    (
        TOTAL_GRUS
        + GRUS_PER_TASK
        - 1
    )
    / GRUS_PER_TASK
)

LAST_TASK=$((N_TASKS - 1))


echo
echo "============================================================"
echo "SUBMIT NWAM STAGE 6"
echo "============================================================"

echo "Domain          : $DOMAIN_NAME"
echo "Experiment      : $EXPERIMENT_ID"
echo "Total GRUs      : $TOTAL_GRUS"
echo "GRUs/task       : $GRUS_PER_TASK"
echo "SUMMA tasks     : $N_TASKS"
echo "Max concurrent  : $MAX_CONCURRENT"
echo "mizuRoute tasks : 1"

echo "============================================================"
echo


# ============================================================
# SUMMA ARRAY
# ============================================================

SUMMA_JOB=$(
    sbatch \
        --parsable \
        --job-name="SUMMA_${DOMAIN_NAME}" \
        --array="0-${LAST_TASK}%${MAX_CONCURRENT}" \
        --export="ALL,TOTAL_GRUS=${TOTAL_GRUS},GRUS_PER_TASK=${GRUS_PER_TASK}" \
        "${SCRIPT_DIR}/1_run_summa_as_array.sh"
)


echo "SUMMA array job : $SUMMA_JOB"


# ============================================================
# MERGE
# ============================================================

MERGE_JOB=$(
    sbatch \
        --parsable \
        --job-name="merge_${DOMAIN_NAME}" \
        --dependency="afterok:${SUMMA_JOB}" \
        "${SCRIPT_DIR}/2_merge_summa_array_outputs.sh"
)


echo "SUMMA merge job : $MERGE_JOB"


# ============================================================
# MIZUROUTE
# ============================================================

MIZU_JOB=$(
    sbatch \
        --parsable \
        --job-name="mizu_${DOMAIN_NAME}" \
        --dependency="afterok:${MERGE_JOB}" \
        "${SCRIPT_DIR}/3_run_mizuRoute.sh"
)


echo "mizuRoute job   : $MIZU_JOB"


# ============================================================
# FINAL QA
# ============================================================

QA_JOB=$(
    sbatch \
        --parsable \
        --job-name="QA_${DOMAIN_NAME}" \
        --dependency="afterok:${MIZU_JOB}" \
        "${SCRIPT_DIR}/4_verify_stage6.sh"
)


echo "Final QA job    : $QA_JOB"


echo
echo "============================================================"
echo "STAGE 6 WORKFLOW SUBMITTED"
echo "============================================================"

echo
echo "Dependency chain:"
echo
echo "SUMMA array"
echo "    -> SUMMA merge"
echo "        -> mizuRoute"
echo "            -> final QA"
echo

echo "Monitor with:"
echo "squeue -u \$USER"

echo "============================================================"