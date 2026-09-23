#!/bin/bash
#SBATCH --job-name=archive_forcing
#SBATCH --time=08:00:00
#SBATCH --mem=2G
#SBATCH --cpus-per-task=1
#SBATCH --output=slurm_logs/archive_forcing_%A_%a.out
#SBATCH --error=slurm_logs/archive_forcing_%A_%a.err

# ============================================================
# CWARHM MONTHLY-FORCING ARCHIVE WORKER
# ============================================================
#
# One Slurm array task processes ONE completed basin.
#
# The task file is the existing lumped basin task file:
#
#   lumped_multibasin_preprocessing_<BATCH>.txt
#
# Each row contains:
#
#   /absolute/path/to/control_<DOMAIN>_lumped.txt
#
# The worker reads:
#
#   root_path
#   domain_name
#
# from the lumped control file and reconstructs:
#
#   <root_path>/domain_<DOMAIN>
#
# The Python archive script then archives BOTH distributed and
# lumped monthly forcing for that basin.
#
# Dry run:
#
#   sbatch --array=0-N \
#       run_archive_monthly_forcing_array.sh \
#       lumped_multibasin_preprocessing_<BATCH>.txt \
#       --dry-run
#
# Archive:
#
#   sbatch --array=0-N \
#       run_archive_monthly_forcing_array.sh \
#       lumped_multibasin_preprocessing_<BATCH>.txt
#
# ============================================================

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
WORKDIR="${CWARHM}/3a_forcing/6_archive_monthly_forcing"
PYTHON_SCRIPT="${WORKDIR}/archive_monthly_forcing.py"


# ============================================================
# ARGUMENTS
# ============================================================

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "ERROR: Invalid number of arguments."
    echo
    echo "Usage:"
    echo "  run_archive_monthly_forcing_array.sh TASK_FILE [--dry-run]"
    exit 1
fi

TASK_FILE=$(realpath "$1")
MODE="${2:-}"

if [ ! -f "$TASK_FILE" ]; then
    echo "ERROR: Task file not found:"
    echo "$TASK_FILE"
    exit 1
fi

if [ -n "$MODE" ] && [ "$MODE" != "--dry-run" ]; then
    echo "ERROR: Optional second argument must be --dry-run."
    exit 1
fi

if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then
    echo "ERROR: SLURM_ARRAY_TASK_ID is not defined."
    echo "Submit this script as a Slurm array."
    exit 1
fi

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "ERROR: Python script not found:"
    echo "$PYTHON_SCRIPT"
    exit 1
fi


# ============================================================
# SELECT CONTROL FILE
# ============================================================

TOTAL_TASKS=$(wc -l < "$TASK_FILE")
LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))

if [ "$LINE_NUMBER" -gt "$TOTAL_TASKS" ]; then
    echo "ERROR: Array index exceeds task-file length."
    echo "Array ID   : $SLURM_ARRAY_TASK_ID"
    echo "Task count : $TOTAL_TASKS"
    exit 1
fi

CONTROL_FILE=$(sed -n "${LINE_NUMBER}p" "$TASK_FILE" | xargs)

if [ -z "$CONTROL_FILE" ]; then
    echo "ERROR: Empty task at line $LINE_NUMBER"
    exit 1
fi

CONTROL_FILE=$(realpath "$CONTROL_FILE")

if [ ! -f "$CONTROL_FILE" ]; then
    echo "ERROR: Control file not found:"
    echo "$CONTROL_FILE"
    exit 1
fi


# ============================================================
# READ CONTROL SETTINGS
# ============================================================

DOMAIN=$(awk -F'|' '
    /^[[:space:]]*domain_name[[:space:]]*\|/ {
        value=$2
        sub(/#.*/, "", value)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        print value
        exit
    }
' "$CONTROL_FILE")

ROOT_PATH=$(awk -F'|' '
    /^[[:space:]]*root_path[[:space:]]*\|/ {
        value=$2
        sub(/#.*/, "", value)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        print value
        exit
    }
' "$CONTROL_FILE")

if [ -z "$DOMAIN" ]; then
    echo "ERROR: Could not read domain_name from:"
    echo "$CONTROL_FILE"
    exit 1
fi

if [ -z "$ROOT_PATH" ]; then
    echo "ERROR: Could not read root_path from:"
    echo "$CONTROL_FILE"
    exit 1
fi


# ============================================================
# DOMAIN ROOT
# ============================================================

DOMAIN_ROOT="${ROOT_PATH}/domain_${DOMAIN}"

if [ ! -d "$DOMAIN_ROOT" ]; then
    echo "ERROR: Domain directory not found:"
    echo "$DOMAIN_ROOT"
    exit 1
fi

DOMAIN_ROOT=$(realpath "$DOMAIN_ROOT")


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base

cd "$WORKDIR"

mkdir -p slurm_logs


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "CWARHM MONTHLY-FORCING ARCHIVE"
echo "======================================================================"
echo
echo "Slurm job ID  : ${SLURM_JOB_ID:-unknown}"
echo "Array task ID : ${SLURM_ARRAY_TASK_ID}"
echo "Task line     : ${LINE_NUMBER}"
echo "Task file     : ${TASK_FILE}"
echo "Control file  : ${CONTROL_FILE}"
echo "Domain        : ${DOMAIN}"
echo "Root path     : ${ROOT_PATH}"
echo "Domain root   : ${DOMAIN_ROOT}"
echo "Mode          : ${MODE:-archive}"
echo "Start time    : $(date)"
echo


# ============================================================
# RUN
# ============================================================

COMMAND=(
    conda run
    --no-capture-output
    -n nwam
    python
    "$PYTHON_SCRIPT"
    --domain-root
    "$DOMAIN_ROOT"
)

if [ "$MODE" = "--dry-run" ]; then
    COMMAND+=(--dry-run)
fi

"${COMMAND[@]}"


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "PASS: CWARHM MONTHLY-FORCING ARCHIVE"
echo "======================================================================"
echo
echo "Domain   : ${DOMAIN}"
echo "End time : $(date)"
echo