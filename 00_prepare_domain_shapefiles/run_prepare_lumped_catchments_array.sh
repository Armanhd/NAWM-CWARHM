#!/bin/bash
#SBATCH --job-name=lumped_cat
#SBATCH --time=01:00:00
#SBATCH --mem=2G
#SBATCH --cpus-per-task=1
#SBATCH --output=slurm_logs/lumped_cat_%A_%a.out
#SBATCH --error=slurm_logs/lumped_cat_%A_%a.err

set -euo pipefail

# ============================================================
# LUMPED CATCHMENT ARRAY WORKER
# ============================================================
#
# One Slurm array task processes one basin.
#
# Input task-file format:
#
#   /absolute/path/to/control_<DOMAIN>_lumped.txt
#
# The worker creates:
#
#   domain_<DOMAIN>/lumped/shapefiles/catchment/
#       <DOMAIN>_lumped_basin.shp
#
# Existing distributed catchments are read only.
# ============================================================

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <lumped_basin_task_file>"
    exit 1
fi

TASK_FILE="$1"

if [ ! -f "$TASK_FILE" ]; then
    echo "ERROR: task file not found:"
    echo "$TASK_FILE"
    exit 1
fi

if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then
    echo "ERROR: SLURM_ARRAY_TASK_ID is not defined."
    echo "Submit this script using sbatch --array."
    exit 1
fi

CONTROL_FILE=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "$TASK_FILE")

if [ -z "$CONTROL_FILE" ]; then
    echo "ERROR: no control file for array index ${SLURM_ARRAY_TASK_ID}"
    exit 1
fi

if [ ! -f "$CONTROL_FILE" ]; then
    echo "ERROR: control file not found:"
    echo "$CONTROL_FILE"
    exit 1
fi

SCRIPT_DIR="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/00_prepare_domain_shapefiles"

echo "============================================================"
echo "LUMPED CATCHMENT ARRAY TASK"
echo "============================================================"
echo "Job ID      : ${SLURM_JOB_ID:-unknown}"
echo "Array task  : ${SLURM_ARRAY_TASK_ID}"
echo "Control     : ${CONTROL_FILE}"
echo "Start       : $(date)"
echo

python "${SCRIPT_DIR}/2_prepare_lumped_catchment.py" \
    "$CONTROL_FILE" \
    --overwrite

echo
echo "Completed   : $(date)"
echo "PASS"
echo "============================================================"