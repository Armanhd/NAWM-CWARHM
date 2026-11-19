#!/bin/bash -l
set -euo pipefail

# Step 05: Convert one CAMELS-SPAT lumped basin.
# SLURM_ARRAY_TASK_ID selects one row of the inventory.
# All source/destination paths are configured in TOML.

CODE="${CWARHM_SUMMA_CODE_ROOT:?Missing CWARHM_SUMMA_CODE_ROOT}"

CONFIG="$CODE/config/camels_spat_arc.toml"
INVENTORY="$CODE/reports/camels_spat_lumped_inventory.csv"

source "$CODE/env/load_model_env_arc.sh"

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

TASK="${SLURM_ARRAY_TASK_ID:?Missing Slurm array task ID}"

echo "================================================"
echo "CAMELS-SPAT TO SUMMA CONVERSION"
echo "================================================"
echo "Job ID:        ${SLURM_JOB_ID:-unknown}"
echo "Array task:    $TASK"
echo "Host:          $(hostname)"
echo "Start:         $(date -Is)"
echo "Configuration: $CONFIG"
echo "Inventory:     $INVENTORY"

python3 "$CODE/03_convert_basins.py" \
    --config "$CONFIG" \
    --inventory "$INVENTORY" \
    --index "$TASK"

echo
echo "CONVERSION TASK: SUCCESS"
echo "End: $(date -Is)"
