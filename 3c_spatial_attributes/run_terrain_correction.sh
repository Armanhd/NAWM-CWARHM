#!/usr/bin/env bash

# Step 11 terrain processing.
# Supports distributed, lumped, and both modes.
# Uses the active Python environment (ARC or FIR).
# Does not rerun DEM, MODIS, or soil-class preprocessing.

set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: bash $0 CONTROL_FILE [both|distributed|lumped]" >&2
    exit 2
fi

CONTROL="$(realpath "$1")"
MODE="${2:-both}"

case "$MODE" in
    both|distributed|lumped)
        ;;
    *)
        echo "ERROR: Invalid processing mode: $MODE" >&2
        exit 2
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CWARHM="$(cd "$SCRIPT_DIR/.." && pwd)"

TERRAIN="$CWARHM/3b_parameters/TERRAIN_ATTRIBUTES"

# Generate slope/aspect from the existing distributed DEM.
python "$TERRAIN/1_generate_slope_aspect.py" \
    "$CONTROL"

# Calculate only the requested HRU configuration(s).
python "$TERRAIN/2_calculate_terrain_attributes.py" \
    "$CONTROL" \
    --mode "$MODE"