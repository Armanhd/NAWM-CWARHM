#!/bin/bash
#SBATCH --job-name=lump_weights
#SBATCH --time=02:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1
#SBATCH --output=slurm_logs/lumped_weights_%A_%a.out
#SBATCH --error=slurm_logs/lumped_weights_%A_%a.err

set -euo pipefail

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
SCRIPT_DIR="${CWARHM}/4b_remapping/2_forcing"

PYTHON_SCRIPT="${SCRIPT_DIR}/1_create_lumped_forcing_remapping.py"

if [ "$#" -ne 1 ]; then
    echo "ERROR: Lumped basin task file is required."
    exit 1
fi

TASK_FILE=$(realpath "$1")

if [ ! -f "$TASK_FILE" ]; then
    echo "ERROR: Task file not found:"
    echo "$TASK_FILE"
    exit 1
fi

if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then
    echo "ERROR: Must be submitted as a Slurm array."
    exit 1
fi

LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))

CONTROL_FILE=$(sed -n "${LINE_NUMBER}p" "$TASK_FILE" | xargs)

if [ -z "$CONTROL_FILE" ] || [ ! -f "$CONTROL_FILE" ]; then
    echo "ERROR: Invalid control file for task ${SLURM_ARRAY_TASK_ID}"
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
' "$CONTROL_FILE")

module load conda/base

mkdir -p "${SCRIPT_DIR}/slurm_logs"

echo
echo "============================================================"
echo "CREATE LUMPED FORCING REMAPPING"
echo "============================================================"
echo "Job ID      : ${SLURM_JOB_ID:-unknown}"
echo "Array task  : ${SLURM_ARRAY_TASK_ID}"
echo "Domain      : ${DOMAIN}"
echo "Control     : ${CONTROL_FILE}"
echo "Start       : $(date)"
echo

conda run --no-capture-output -n nwam \
    python "$PYTHON_SCRIPT" \
    "$CONTROL_FILE"

echo
echo "PASS: ${DOMAIN}"
echo "Completed   : $(date)"
echo "============================================================"