#!/bin/bash
#SBATCH --job-name=nwam_attributes
#SBATCH --time=12:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --output=slurm_logs/attributes_%A_%a.out
#SBATCH --error=slurm_logs/attributes_%A_%a.err

set -euo pipefail

TASK_FILE="${1:?Usage: sbatch run_multibasin_attributes_array.sh TASK_FILE}"

# Resolve repository from the Slurm submission directory.
REPO_DIR="${SLURM_SUBMIT_DIR:?}"

source "$REPO_DIR/load_nwam_fir.sh"

cd "$REPO_DIR/3c_spatial_attributes"

python run_multibasin_attributes.py \
    --task-file "$TASK_FILE" \
    --index "${SLURM_ARRAY_TASK_ID:?}" \
    --execute \
    --with-worldclim