#!/usr/bin/env bash
set -euo pipefail

CODE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONFIG="$CODE/config/camels_spat_arc.toml"
INVENTORY="$CODE/reports/camels_spat_lumped_inventory.csv"
TASK_SCRIPT="$CODE/conversion_task.sh"

LOG_DIR="$CODE/reports/slurm_logs"
mkdir -p "$LOG_DIR"

source "$CODE/env/load_model_env_arc.sh"

# This also checks that all inventory entries are READY.
read -r COUNT CANARY_INDICES < <(
python3 - "$INVENTORY" <<'PY'
import csv
import sys

with open(sys.argv[1], newline="") as f:
    rows = list(csv.DictReader(f))

if not rows:
    raise SystemExit("Inventory is empty")

if any(row["status"] != "READY" for row in rows):
    raise SystemExit("Inventory contains entries not marked READY")

if any(int(row["index"]) != i for i, row in enumerate(rows)):
    raise SystemExit("Inventory indices are not sequential")

scales = ("headwater", "meso_scale", "macro_scale")
indices = []

for scale in scales:
    matches = [r for r in rows if r["group"] == scale]
    if not matches:
        raise SystemExit(f"No basin found for {scale}")
    indices.append(int(matches[0]["index"]))

print(len(rows), ",".join(map(str, indices)))
PY
)

MODE="${1:-dry-run}"
CONCURRENCY="${CONCURRENCY:-4}"
MEMORY="${MEMORY:-16G}"
WALLTIME="${WALLTIME:-04:00:00}"

case "$MODE" in
    dry-run)
        ARRAY="0-$((COUNT - 1))%$CONCURRENCY"
        ;;
    pilot)
        ARRAY="$CANARY_INDICES"
        ;;
    production)
        ARRAY="0-$((COUNT - 1))%$CONCURRENCY"
        ;;
    *)
        echo "Usage: $0 {dry-run|pilot|production}"
        exit 2
        ;;
esac

echo "=========================================="
echo "CAMELS-SPAT LUMPED CONVERSION SUBMISSION"
echo "=========================================="
echo "Mode:        $MODE"
echo "Basins:      $COUNT"
echo "Array:       $ARRAY"
echo "CPUs/task:   1"
echo "Memory/task: $MEMORY"
echo "Time/task:   $WALLTIME"
echo "Max parallel: $CONCURRENCY"
echo "Logs:        $LOG_DIR"

if [[ "$MODE" == "dry-run" ]]; then
    echo "DRY RUN: No Slurm job submitted."
    exit 0
fi

sbatch --parsable \
    --export=ALL,CWARHM_SUMMA_CODE_ROOT="$CODE" \
    --job-name="camels_summa_${MODE}" \
    --nodes=1 \
    --ntasks=1 \
    --cpus-per-task=1 \
    --mem="$MEMORY" \
    --time="$WALLTIME" \
    --array="$ARRAY" \
    --output="$LOG_DIR/${MODE}_%A_%a.log" \
    --error="$LOG_DIR/${MODE}_%A_%a.err" \
    "$TASK_SCRIPT"
