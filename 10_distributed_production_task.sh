#!/usr/bin/env bash
set -euo pipefail

CODE="/work/comphyd_lab/users/arman.haddadchi/NWAM/NAWM_CWARHM_to_SUMMA_transfer"

CONFIG="$CODE/config/camels_spat_distributed_arc.toml"
INVENTORY="$CODE/reports/camels_spat_distributed_inventory.csv"

OUT="/work/comphyd_lab/users/arman.haddadchi/NWAM/NWAM_Data/summa_calibration/camels_spat_distributed_calibration"

INDEX="${1:?Usage: 10_distributed_production_task.sh INVENTORY_INDEX}"

source "$CODE/env/load_model_env_arc.sh"

BASIN=$(python3 - "$INVENTORY" "$INDEX" <<'PY'
import csv
import sys

with open(sys.argv[1], newline="") as f:
    rows = list(csv.DictReader(f))

i = int(sys.argv[2])

if not 0 <= i < len(rows):
    raise SystemExit(f"Invalid array index: {i}")

row = rows[i]

if row["status"] != "READY":
    raise SystemExit(f"Basin not READY: {row['basin']}")

if int(row["index"]) != i:
    raise SystemExit("Inventory index does not match row position")

print(row["basin"])
PY
)

echo "========================================================"
echo "Distributed production conversion"
echo "Index: $INDEX"
echo "Basin: $BASIN"
echo "========================================================"

TARGET="$OUT/domain/$BASIN"
AUDIT="$OUT/_audit/$BASIN.csv"
WORK="$OUT/.conversion_staging/$BASIN"

mkdir -p "$OUT/domain" "$OUT/observations/obs-daily" \
         "$OUT/observations/obs-hourly" "$OUT/_audit" \
         "$OUT/.conversion_staging"

# Existing results are skipped ONLY after independent validation.
if [[ -d "$TARGET" ]]; then
    echo "Existing basin found; checking integrity."

    python3 "$CODE/08_validate_distributed_basins.py" \
        --config "$CONFIG" \
        --inventory "$INVENTORY" \
        --destination "$OUT" \
        --basin "$BASIN" \
        --output "$AUDIT"

    echo "SKIP: Existing basin independently validated."
    exit 0
fi

# mkdir serves as an exclusive per-basin lock.
# Failed/interrupted tasks retain their staging folder for diagnosis.
if ! mkdir "$WORK"; then
    echo "ERROR: Staging directory already exists: $WORK"
    echo "Inspect the previous attempt before retrying."
    exit 1
fi

echo "STEP 06: Prepare distributed inputs"

python3 "$CODE/06_prepare_distributed_inputs.py" \
    --config "$CONFIG" \
    --inventory "$INVENTORY" \
    --basin "$BASIN" \
    --destination "$WORK/step06"

echo "STEP 07: Copy and align distributed forcing"

python3 "$CODE/07_convert_distributed_basins.py" \
    --config "$CONFIG" \
    --inventory "$INVENTORY" \
    --basin "$BASIN" \
    --step06 "$WORK/step06" \
    --destination "$WORK/step07"

echo "STEP 08: Independently validate staged result"

python3 "$CODE/08_validate_distributed_basins.py" \
    --config "$CONFIG" \
    --inventory "$INVENTORY" \
    --destination "$WORK/step07" \
    --basin "$BASIN" \
    --output "$WORK/staged_validation.csv"

echo "Publishing verified observations"

for KIND in obs-daily obs-hourly; do
    SRC_DIR="$WORK/step07/observations/$KIND"
    DEST_DIR="$OUT/observations/$KIND"

    for SRC in "$SRC_DIR"/*; do
        [[ -f "$SRC" ]] || continue

        DEST="$DEST_DIR/$(basename "$SRC")"

        if [[ -e "$DEST" ]]; then
            cmp -s "$SRC" "$DEST" || {
                echo "ERROR: Existing observation differs: $DEST"
                exit 1
            }
        else
            cp -p "$SRC" "$DEST"
            cmp -s "$SRC" "$DEST" || {
                echo "ERROR: Observation copy verification failed"
                exit 1
            }
        fi
    done
done

echo "Publishing verified distributed basin"

# Same-filesystem rename, avoiding a partially copied domain.
mv -T "$WORK/step07/domain/$BASIN" "$TARGET"

echo "Final independent validation"

python3 "$CODE/08_validate_distributed_basins.py" \
    --config "$CONFIG" \
    --inventory "$INVENTORY" \
    --destination "$OUT" \
    --basin "$BASIN" \
    --output "$AUDIT"

echo "Removing temporary work after successful validation"
rm -rf -- "$WORK"

echo "========================================================"
echo "COMPLETE: $BASIN"
echo "Output: $TARGET"
echo "Validation: $AUDIT"
echo "========================================================"
