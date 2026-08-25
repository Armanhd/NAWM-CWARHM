#!/bin/bash

#SBATCH --job-name=mizuRoute
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=2-00:00:00
#SBATCH --partition=cpu2025,cpu2023,cpu2022
#SBATCH --output=mizuRoute_%j.out
#SBATCH --error=mizuRoute_%j.err

set -euo pipefail


# ============================================================
# PATHS / CONTROL
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

MIZU_PATH="$(read_control install_path_mizuroute)"
MIZU_EXE="$(read_control exe_name_mizuroute)"

SETTINGS_PATH="$(read_control settings_mizu_path)"
CONTROL_NAME="$(read_control settings_mizu_control_file)"

OUTPUT_PATH="$(read_control experiment_output_mizuRoute)"
LOG_PATH="$(read_control experiment_log_mizuroute)"

DO_BACKUP="$(read_control experiment_backup_settings)"


# ============================================================
# DEFAULT PATHS
# ============================================================

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
# MPI SETTINGS
# ============================================================

MPI_TASKS="${SLURM_NTASKS:-1}"


if ! [[ "$MPI_TASKS" =~ ^[1-9][0-9]*$ ]]; then

    echo
    echo "ERROR: Invalid MPI task count:"
    echo "$MPI_TASKS"

    exit 1
fi


# Current validated production default is 4 MPI ranks.
# Other task counts may be tested later for larger domains,
# but should not be assumed equivalent until validated.

if [ "$MPI_TASKS" -lt 1 ]; then

    echo
    echo "ERROR: MPI task count must be >= 1."

    exit 1
fi


# ============================================================
# REQUIRED FILE / EXECUTABLE CHECKS
# ============================================================

if [ ! -x "$MIZU_EXEC" ]; then

    echo
    echo "ERROR: mizuRoute executable not found:"
    echo "$MIZU_EXEC"

    exit 1
fi


if [ ! -f "$CONTROL_FILE" ]; then

    echo
    echo "ERROR: mizuRoute control file not found:"
    echo "$CONTROL_FILE"

    exit 1
fi


# ============================================================
# VERIFY PARALLEL LIBRARY LINKAGE
# ============================================================

LDD_OUTPUT="$(
    ldd "$MIZU_EXEC"
)"


for required_lib in \
    libmpi \
    libnetcdf \
    libpnetcdf

do

    if ! grep -q "$required_lib" <<< "$LDD_OUTPUT"; then

        echo
        echo "ERROR:"
        echo "mizuRoute executable is not linked against:"
        echo "$required_lib"

        echo
        echo "Executable:"
        echo "$MIZU_EXEC"

        echo
        echo "Recompile mizuRoute with nwam_parallel."

        exit 1
    fi

done


if grep -q "not found" <<< "$LDD_OUTPUT"; then

    echo
    echo "ERROR: unresolved mizuRoute shared libraries:"
    echo

    grep "not found" <<< "$LDD_OUTPUT"

    exit 1
fi


# ============================================================
# VERIFY CONTROL FILE PARALLEL I/O SETTINGS
# ============================================================

if ! grep -Eq \
    '^<pio_netcdf_type>[[:space:]]+pnetcdf[[:space:]]+!' \
    "$CONTROL_FILE"
then

    echo
    echo "ERROR:"
    echo "mizuRoute control file is not configured for PnetCDF."
    echo
    echo "Expected:"
    echo "<pio_netcdf_type> pnetcdf !"
    echo
    echo "Control file:"
    echo "$CONTROL_FILE"

    exit 1
fi


if ! grep -Eq \
    '^<pio_netcdf_format>[[:space:]]+64bit_offset[[:space:]]+!' \
    "$CONTROL_FILE"
then

    echo
    echo "ERROR:"
    echo "mizuRoute control file does not use 64bit_offset."

    echo
    echo "Expected:"
    echo "<pio_netcdf_format> 64bit_offset !"

    exit 1
fi


if ! grep -Eq \
    '^<seg_outlet>[[:space:]]+-9999[[:space:]]+!' \
    "$CONTROL_FILE"
then

    echo
    echo "ERROR:"
    echo "mizuRoute control file does not route the complete network."

    echo
    echo "Expected:"
    echo "<seg_outlet> -9999 !"

    exit 1
fi


if ! grep -Eq \
    '^<ro_calendar>[[:space:]]+standard[[:space:]]+!' \
    "$CONTROL_FILE"
then

    echo
    echo "ERROR:"
    echo "mizuRoute control file does not contain:"
    echo "<ro_calendar> standard !"

    exit 1
fi


# ============================================================
# OUTPUT DIRECTORIES
# ============================================================

mkdir -p "$OUTPUT_PATH"

mkdir -p "$LOG_PATH"


# ============================================================
# REMOVE STALE MIZUROUTE HISTORY OUTPUTS
# ============================================================

# A rerun must not mix newly generated history files with
# history files left from an older simulation.

OLD_HISTORY_COUNT="$(
    find "$OUTPUT_PATH" \
        -maxdepth 1 \
        -type f \
        -name "${EXPERIMENT_ID}.h.*.nc" \
        | wc -l
)"


if [ "$OLD_HISTORY_COUNT" -gt 0 ]; then

    echo
    echo "Removing $OLD_HISTORY_COUNT existing mizuRoute history files:"
    echo "$OUTPUT_PATH"

    find "$OUTPUT_PATH" \
        -maxdepth 1 \
        -type f \
        -name "${EXPERIMENT_ID}.h.*.nc" \
        -delete

fi


# Remove stale cleanup backups from an earlier run.

find "$OUTPUT_PATH" \
    -maxdepth 1 \
    -type f \
    -name "*.pre_duplicate_cleanup" \
    -delete


# Remove previous run log.

rm -f "$LOG_FILE"


# ============================================================
# SETTINGS BACKUP
# ============================================================

if [ "$DO_BACKUP" = "yes" ]; then

    BACKUP_PATH="${OUTPUT_PATH}/run_settings"

    rm -rf "$BACKUP_PATH"

    mkdir -p "$BACKUP_PATH"

    cp -R \
        "${SETTINGS_PATH}/." \
        "$BACKUP_PATH/"

fi


# ============================================================
# REPORT
# ============================================================

echo
echo "============================================================"
echo "RUN MIZUROUTE"
echo "============================================================"

echo "Domain       : $DOMAIN_NAME"
echo "Experiment   : $EXPERIMENT_ID"
echo "Environment  : $CONDA_DEFAULT_ENV"

echo
echo "MPI tasks    : $MPI_TASKS"
echo "PIO backend  : pnetcdf"
echo "PIO format   : 64bit_offset"

echo
echo "Executable   : $MIZU_EXEC"
echo "Control      : $CONTROL_FILE"
echo "Output       : $OUTPUT_PATH"
echo "Log          : $LOG_FILE"

echo
echo "Start        : $(date)"

echo "============================================================"
echo


# ============================================================
# RUN MIZUROUTE
# ============================================================

set +e

if [ -n "${SLURM_JOB_ID:-}" ]; then

    srun \
        --ntasks="$MPI_TASKS" \
        "$MIZU_EXEC" \
        "$CONTROL_FILE" \
        > "$LOG_FILE" 2>&1

else

    # Primarily useful for a 1-rank diagnostic outside Slurm.
    # Production Stage 6 should normally run through Slurm.

    if [ "$MPI_TASKS" -ne 1 ]; then

        echo
        echo "ERROR:"
        echo "Multi-rank mizuRoute must be launched through Slurm/srun."

        exit 1
    fi

    "$MIZU_EXEC" \
        "$CONTROL_FILE" \
        > "$LOG_FILE" 2>&1

fi


STATUS=$?

set -e


# ============================================================
# VERIFY MIZUROUTE SUCCESS
# ============================================================

MODEL_SUCCESS="no"


if grep -q \
    "SUCCESSFUL EXECUTION" \
    "$LOG_FILE"
then

    MODEL_SUCCESS="yes"

fi


if [ "$STATUS" -ne 0 ] \
    || [ "$MODEL_SUCCESS" != "yes" ]; then

    echo
    echo "============================================================"
    echo "MIZUROUTE FAILED"
    echo "============================================================"

    echo "Executable return code : $STATUS"
    echo "Success marker found   : $MODEL_SUCCESS"

    echo
    echo "Last 60 lines of mizuRoute log:"
    echo "------------------------------------------------------------"

    tail -60 "$LOG_FILE" || true

    exit 1
fi


# ============================================================
# BASIC OUTPUT PRESENCE CHECK
# ============================================================

HISTORY_COUNT="$(
    find "$OUTPUT_PATH" \
        -maxdepth 1 \
        -type f \
        -name "${EXPERIMENT_ID}.h.*.nc" \
        | wc -l
)"


if [ "$HISTORY_COUNT" -eq 0 ]; then

    echo
    echo "ERROR:"
    echo "mizuRoute reported successful execution but no yearly"
    echo "history NetCDF files were produced."

    exit 1
fi


# ============================================================
# PROVENANCE
# ============================================================

WORKFLOW_LOG="${OUTPUT_PATH}/_workflow_log"

mkdir -p "$WORKFLOW_LOG"


RUN_LOG="$(
    printf \
        "%s/%s_mizuroute_run.txt" \
        "$WORKFLOW_LOG" \
        "$(date '+%Y%m%d_%H%M%S')"
)"


{
    echo "mizuRoute Stage 6 run"
    echo "Date: $(date)"
    echo
    echo "Domain: $DOMAIN_NAME"
    echo "Experiment: $EXPERIMENT_ID"
    echo
    echo "Environment: $CONDA_DEFAULT_ENV"
    echo "Conda prefix: $CONDA_PREFIX"
    echo
    echo "MPI tasks: $MPI_TASKS"
    echo "PIO backend: pnetcdf"
    echo "PIO format: 64bit_offset"
    echo
    echo "Executable: $MIZU_EXEC"
    echo "Control file: $CONTROL_FILE"
    echo
    echo "History files produced: $HISTORY_COUNT"
    echo "Executable return code: $STATUS"
    echo "mizuRoute success marker: $MODEL_SUCCESS"

} > "$RUN_LOG"


cp \
    "$CONTROL_FILE" \
    "$WORKFLOW_LOG/mizuroute.control"


cp \
    "${SCRIPT_DIR}/3_run_mizuRoute.sh" \
    "$WORKFLOW_LOG/3_run_mizuRoute.sh"


# ============================================================
# SUCCESS
# ============================================================

echo
echo "============================================================"
echo "MIZUROUTE COMPLETED SUCCESSFULLY"
echo "============================================================"

echo "MPI tasks      : $MPI_TASKS"
echo "History files  : $HISTORY_COUNT"
echo "Return code    : $STATUS"
echo "Log            : $LOG_FILE"
echo "Workflow log   : $RUN_LOG"
echo "End            : $(date)"

echo
echo "NOTE:"
echo "Parallel mizuRoute output is not considered final until"
echo "4_clean_mizuroute_outputs.py and 5_verify_stage6.py pass."

echo "============================================================"