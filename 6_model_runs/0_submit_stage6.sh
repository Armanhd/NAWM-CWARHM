#!/bin/bash

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

            gsub(
                /^[ \t]+|[ \t]+$/,
                "",
                left
            )

            if (left == key) {

                right=$2

                sub(
                    /#.*/,
                    "",
                    right
                )

                gsub(
                    /^[ \t]+|[ \t]+$/,
                    "",
                    right
                )

                print right

                exit
            }
        }

    ' "$CONTROL"
}


# ============================================================
# CONTROL SETTINGS
# ============================================================

ROOT_PATH="$(
    read_control root_path
)"

DOMAIN_NAME="$(
    read_control domain_name
)"

EXPERIMENT_ID="$(
    read_control experiment_id
)"

SETTINGS_PATH="$(
    read_control settings_summa_path
)"

ATTRIBUTES_NAME="$(
    read_control settings_summa_attributes
)"

MIZU_OUTPUT="$(
    read_control experiment_output_mizuRoute
)"


# ============================================================
# DEFAULT PATHS
# ============================================================

if [ "$SETTINGS_PATH" = "default" ]; then

    SETTINGS_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/settings/SUMMA"

fi


if [ "$MIZU_OUTPUT" = "default" ]; then

    MIZU_OUTPUT="${ROOT_PATH}/domain_${DOMAIN_NAME}/simulations/${EXPERIMENT_ID}/mizuRoute"

fi


ATTRIBUTES="${SETTINGS_PATH}/${ATTRIBUTES_NAME}"


# ============================================================
# REQUIRED FILES
# ============================================================

required_files=(

    "$CONTROL"

    "${SCRIPT_DIR}/0_prepare_stage6.py"

    "${SCRIPT_DIR}/1_run_summa_as_array.sh"

    "${SCRIPT_DIR}/2_merge_summa_array_outputs.sh"

    "${SCRIPT_DIR}/3_run_mizuRoute.sh"

    "${SCRIPT_DIR}/4_clean_mizuroute_outputs.py"

    "${SCRIPT_DIR}/5_verify_stage6.py"

    "$ATTRIBUTES"
)


for file in "${required_files[@]}"; do

    if [ ! -f "$file" ]; then

        echo
        echo "ERROR: Required Stage 6 file not found:"
        echo "$file"

        exit 1

    fi

done


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base

conda activate nwam_parallel


if [ "${CONDA_DEFAULT_ENV:-}" != "nwam_parallel" ]; then

    echo
    echo "ERROR: Failed to activate nwam_parallel."
    echo
    echo "Active environment:"
    echo "${CONDA_DEFAULT_ENV:-none}"

    exit 1

fi


PYTHON_EXE="${CONDA_PREFIX}/bin/python"


if [ ! -x "$PYTHON_EXE" ]; then

    echo
    echo "ERROR: Python executable not found:"
    echo "$PYTHON_EXE"

    exit 1

fi


# ============================================================
# USER-TUNABLE PARALLEL SETTINGS
# ============================================================

# These may be changed without editing this script:
#
# GRUS_PER_TASK=20 \
# MAX_CONCURRENT=24 \
# MIZU_TASKS=8 \
# ./0_submit_stage6.sh
#
# The current validated default for mizuRoute is 4 MPI ranks.

GRUS_PER_TASK="${GRUS_PER_TASK:-10}"

MAX_CONCURRENT="${MAX_CONCURRENT:-32}"

MIZU_TASKS="${MIZU_TASKS:-4}"


# ============================================================
# RESOURCE SETTINGS
# ============================================================

SUMMA_MEMORY="${SUMMA_MEMORY:-8G}"

SUMMA_TIME="${SUMMA_TIME:-2-00:00:00}"

MERGE_MEMORY="${MERGE_MEMORY:-8G}"

MERGE_TIME="${MERGE_TIME:-12:00:00}"

MIZU_MEMORY="${MIZU_MEMORY:-8G}"

MIZU_TIME="${MIZU_TIME:-2-00:00:00}"

CLEAN_MEMORY="${CLEAN_MEMORY:-4G}"

CLEAN_TIME="${CLEAN_TIME:-04:00:00}"

QA_MEMORY="${QA_MEMORY:-4G}"

QA_TIME="${QA_TIME:-04:00:00}"


PARTITIONS="${PARTITIONS:-cpu2025,cpu2023,cpu2022}"


# ============================================================
# VALIDATE NUMERIC SETTINGS
# ============================================================

for value_name in \
    GRUS_PER_TASK \
    MAX_CONCURRENT \
    MIZU_TASKS

do

    value="${!value_name}"

    if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then

        echo
        echo "ERROR: $value_name must be a positive integer."
        echo "Current value: $value"

        exit 1

    fi

done


# ============================================================
# PREPARE STAGE 6
# ============================================================

echo
echo "============================================================"
echo "PREPARE STAGE 6"
echo "============================================================"

"$PYTHON_EXE" \
    "${SCRIPT_DIR}/0_prepare_stage6.py"


# ============================================================
# DETERMINE NUMBER OF SUMMA GRUS
# ============================================================

TOTAL_GRUS="$(
    "$PYTHON_EXE" \
    - "$ATTRIBUTES" <<'PY'

import sys
import netCDF4 as nc

attributes = sys.argv[1]

with nc.Dataset(attributes) as ds:

    if "gru" not in ds.dimensions:

        raise RuntimeError(
            "attributes.nc does not contain the 'gru' dimension."
        )

    print(
        len(
            ds.dimensions["gru"]
        )
    )

PY
)"


if ! [[ "$TOTAL_GRUS" =~ ^[1-9][0-9]*$ ]]; then

    echo
    echo "ERROR: Invalid GRU count:"
    echo "$TOTAL_GRUS"

    exit 1

fi


N_TASKS=$(
    (
        TOTAL_GRUS
        + GRUS_PER_TASK
        - 1
    )
    / GRUS_PER_TASK
)


LAST_TASK=$(
    (
        N_TASKS
        - 1
    )
)


# ============================================================
# REPORT
# ============================================================

echo
echo "============================================================"
echo "SUBMIT NWAM STAGE 6"
echo "============================================================"

echo "Domain             : $DOMAIN_NAME"
echo "Experiment         : $EXPERIMENT_ID"

echo
echo "Total GRUs         : $TOTAL_GRUS"
echo "GRUs/SUMMA task    : $GRUS_PER_TASK"
echo "SUMMA array tasks  : $N_TASKS"
echo "Max concurrent     : $MAX_CONCURRENT"

echo
echo "mizuRoute MPI tasks: $MIZU_TASKS"
echo "mizuRoute PIO      : pnetcdf"
echo "mizuRoute format   : 64bit_offset"

echo
echo "Environment        : $CONDA_DEFAULT_ENV"
echo "Python             : $PYTHON_EXE"

echo
echo "Final mizu output  : $MIZU_OUTPUT"

echo "============================================================"
echo


# ============================================================
# SUMMA ARRAY
# ============================================================

SUMMA_JOB="$(
    sbatch \
        --parsable \
        --job-name="SUMMA_${DOMAIN_NAME}" \
        --array="0-${LAST_TASK}%${MAX_CONCURRENT}" \
        --nodes=1 \
        --ntasks=1 \
        --cpus-per-task=1 \
        --mem="$SUMMA_MEMORY" \
        --time="$SUMMA_TIME" \
        --partition="$PARTITIONS" \
        --export="ALL,TOTAL_GRUS=${TOTAL_GRUS},GRUS_PER_TASK=${GRUS_PER_TASK}" \
        --output="${SCRIPT_DIR}/SUMMA_${DOMAIN_NAME}_%A_%a.out" \
        --error="${SCRIPT_DIR}/SUMMA_${DOMAIN_NAME}_%A_%a.err" \
        "${SCRIPT_DIR}/1_run_summa_as_array.sh"
)"


echo "SUMMA array job     : $SUMMA_JOB"


# ============================================================
# MERGE SUMMA ARRAY OUTPUTS
# ============================================================

MERGE_JOB="$(
    sbatch \
        --parsable \
        --job-name="merge_${DOMAIN_NAME}" \
        --dependency="afterok:${SUMMA_JOB}" \
        --nodes=1 \
        --ntasks=1 \
        --cpus-per-task=1 \
        --mem="$MERGE_MEMORY" \
        --time="$MERGE_TIME" \
        --partition="$PARTITIONS" \
        --output="${SCRIPT_DIR}/merge_${DOMAIN_NAME}_%j.out" \
        --error="${SCRIPT_DIR}/merge_${DOMAIN_NAME}_%j.err" \
        "${SCRIPT_DIR}/2_merge_summa_array_outputs.sh"
)"


echo "SUMMA merge job     : $MERGE_JOB"


# ============================================================
# MIZUROUTE PARALLEL RUN
# ============================================================

MIZU_JOB="$(
    sbatch \
        --parsable \
        --job-name="mizu_${DOMAIN_NAME}" \
        --dependency="afterok:${MERGE_JOB}" \
        --nodes=1 \
        --ntasks="$MIZU_TASKS" \
        --cpus-per-task=1 \
        --mem="$MIZU_MEMORY" \
        --time="$MIZU_TIME" \
        --partition="$PARTITIONS" \
        --output="${SCRIPT_DIR}/mizu_${DOMAIN_NAME}_%j.out" \
        --error="${SCRIPT_DIR}/mizu_${DOMAIN_NAME}_%j.err" \
        "${SCRIPT_DIR}/3_run_mizuRoute.sh"
)"


echo "mizuRoute job       : $MIZU_JOB"


# ============================================================
# CLEAN / VALIDATE MIZUROUTE DUPLICATE TIMES
# ============================================================

CLEAN_JOB="$(
    sbatch \
        --parsable \
        --job-name="clean_${DOMAIN_NAME}" \
        --dependency="afterok:${MIZU_JOB}" \
        --nodes=1 \
        --ntasks=1 \
        --cpus-per-task=1 \
        --mem="$CLEAN_MEMORY" \
        --time="$CLEAN_TIME" \
        --partition="$PARTITIONS" \
        --output="${SCRIPT_DIR}/clean_${DOMAIN_NAME}_%j.out" \
        --error="${SCRIPT_DIR}/clean_${DOMAIN_NAME}_%j.err" \
        --wrap="${PYTHON_EXE} '${SCRIPT_DIR}/4_clean_mizuroute_outputs.py'"
)"


echo "mizuRoute cleanup   : $CLEAN_JOB"


# ============================================================
# FINAL STAGE 6 QA
# ============================================================

QA_JOB="$(
    sbatch \
        --parsable \
        --job-name="QA_${DOMAIN_NAME}" \
        --dependency="afterok:${CLEAN_JOB}" \
        --nodes=1 \
        --ntasks=1 \
        --cpus-per-task=1 \
        --mem="$QA_MEMORY" \
        --time="$QA_TIME" \
        --partition="$PARTITIONS" \
        --output="${SCRIPT_DIR}/QA_${DOMAIN_NAME}_%j.out" \
        --error="${SCRIPT_DIR}/QA_${DOMAIN_NAME}_%j.err" \
        --wrap="${PYTHON_EXE} '${SCRIPT_DIR}/5_verify_stage6.py'"
)"


echo "Final QA job        : $QA_JOB"


# ============================================================
# SUBMISSION SUMMARY
# ============================================================

echo
echo "============================================================"
echo "STAGE 6 WORKFLOW SUBMITTED"
echo "============================================================"

echo
echo "Dependency chain:"
echo
echo "SUMMA array"
echo "    -> merge SUMMA outputs"
echo "        -> mizuRoute (${MIZU_TASKS} MPI ranks)"
echo "            -> clean/validate duplicate timestamps"
echo "                -> final Stage 6 QA"

echo
echo "Job IDs:"
echo "  SUMMA : $SUMMA_JOB"
echo "  Merge : $MERGE_JOB"
echo "  mizu  : $MIZU_JOB"
echo "  Clean : $CLEAN_JOB"
echo "  QA    : $QA_JOB"

echo
echo "Monitor with:"
echo "  squeue -u \$USER"

echo
echo "Inspect dependencies with:"
echo "  squeue -j ${SUMMA_JOB},${MERGE_JOB},${MIZU_JOB},${CLEAN_JOB},${QA_JOB}"

echo
echo "Stage 6 is complete only when the final QA job"
echo "finishes successfully."

echo "============================================================"