#!/bin/bash
#SBATCH --job-name=nwam_domain_prep
#SBATCH --time=00:30:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=2
#SBATCH --output=domain_prep_%j.out
#SBATCH --error=domain_prep_%j.err


# ============================================================
# CHECK INPUT
# ============================================================

if [ "$#" -ne 1 ]; then
    echo "Usage:"
    echo "sbatch run_prepare_domain_shapefiles.sh CONTROL_FILE"
    exit 1
fi


CONTROL_FILE=$(realpath "$1")


if [ ! -f "$CONTROL_FILE" ]; then
    echo "ERROR: Control file not found:"
    echo "$CONTROL_FILE"
    exit 1
fi


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base


CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM"

cd "${CWARHM}/00_prepare_domain_shapefiles" || exit 1


echo "============================================================"
echo "NWAM DOMAIN SHAPEFILE PREPARATION"
echo "============================================================"

echo
echo "Control file:"
echo "$CONTROL_FILE"

echo
echo "Start time:"
date


# ============================================================
# STEP 1
# PREPARE RIVER NETWORK
# ============================================================

echo
echo "============================================================"
echo "STEP 1: PREPARE RIVER NETWORK"
echo "============================================================"

conda run -n nwam \
python 1_prepare_river_network.py \
"$CONTROL_FILE"

STATUS=$?

if [ "$STATUS" -ne 0 ]; then
    echo "ERROR: River-network preparation failed."
    exit "$STATUS"
fi


# ============================================================
# STEP 2
# PREPARE CATCHMENT
# ============================================================

echo
echo "============================================================"
echo "STEP 2: PREPARE CATCHMENT"
echo "============================================================"

conda run -n nwam \
python 2_prepare_catchment.py \
"$CONTROL_FILE"

STATUS=$?

if [ "$STATUS" -ne 0 ]; then
    echo "ERROR: Catchment preparation failed."
    exit "$STATUS"
fi


# ============================================================
# STEP 3
# REPORT CONTROL-FILE VALUES
# ============================================================

echo
echo "============================================================"
echo "STEP 3: REPORT CONTROL-FILE VALUES"
echo "============================================================"

conda run -n nwam \
python 3_report_control_values.py \
"$CONTROL_FILE"

STATUS=$?

if [ "$STATUS" -ne 0 ]; then
    echo "ERROR: Control-value report failed."
    exit "$STATUS"
fi


# ============================================================
# FINISH
# ============================================================

echo
echo "============================================================"
echo "DOMAIN PREPARATION COMPLETED SUCCESSFULLY"
echo "============================================================"

echo
echo "End time:"
date

echo
echo "======================================================================"
echo "CONTROL FILE VALUES TO COPY"
echo "======================================================================"

conda run -n nwam \
python 3_report_control_values.py \
"$CONTROL_FILE" | \
grep -E "^forcing_raw_space|^settings_mizu_make_outlet"

echo "======================================================================"