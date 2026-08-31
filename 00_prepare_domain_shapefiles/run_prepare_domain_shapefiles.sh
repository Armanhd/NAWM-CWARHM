#!/bin/bash
#SBATCH --job-name=nwam_domain_prep
#SBATCH --time=00:30:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=2

# ============================================================
# PREPARE ONE NWAM / CWARHM MULTIBASIN DOMAIN
# ============================================================
#
# Purpose
# -------
# Prepare the Stage-00 shapefiles for one domain-specific
# control file.
#
# The script runs:
#
#   1_prepare_river_network.py
#   2_prepare_catchment.py
#   3_report_control_values.py
#
# IMPORTANT
# ---------
# This script:
#
#   - requires an explicit domain-specific control file
#   - does NOT use control_active.txt
#   - does NOT modify any control file
#   - is safe for simultaneous multibasin execution
#
# Usage
# -----
#
# Interactive test:
#
#   bash run_prepare_domain_shapefiles.sh \
#     /path/to/control_MERIT_861.txt
#
# Slurm:
#
#   sbatch run_prepare_domain_shapefiles.sh \
#     /path/to/control_MERIT_861.txt
#
# ============================================================

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

SCRIPT_DIR="${CWARHM}/00_prepare_domain_shapefiles"

RIVER_SCRIPT="${SCRIPT_DIR}/1_prepare_river_network.py"
CATCHMENT_SCRIPT="${SCRIPT_DIR}/2_prepare_catchment.py"
REPORT_SCRIPT="${SCRIPT_DIR}/3_report_control_values.py"


# ============================================================
# CHECK INPUT
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "ERROR: A domain-specific control file is required."
    echo
    echo "Usage:"
    echo "  bash run_prepare_domain_shapefiles.sh CONTROL_FILE"
    echo
    echo "or:"
    echo "  sbatch run_prepare_domain_shapefiles.sh CONTROL_FILE"

    exit 1

fi


CONTROL_FILE=$(realpath "$1")


if [ ! -f "${CONTROL_FILE}" ]; then

    echo "ERROR: Control file not found:"
    echo "${CONTROL_FILE}"

    exit 1

fi


# ============================================================
# VALIDATE WORKFLOW FILES
# ============================================================

for FILE in \
    "${RIVER_SCRIPT}" \
    "${CATCHMENT_SCRIPT}" \
    "${REPORT_SCRIPT}"
do

    if [ ! -f "${FILE}" ]; then

        echo "ERROR: Required Stage-00 script not found:"
        echo "${FILE}"

        exit 1

    fi

done


# ============================================================
# READ DOMAIN NAME
# ============================================================

DOMAIN=$(awk -F'|' '
    /^[[:space:]]*domain_name[[:space:]]*\|/ {
        value=$2
        sub(/#.*/, "", value)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        print value
        exit
    }
' "${CONTROL_FILE}")


if [ -z "${DOMAIN}" ]; then

    echo "ERROR: Could not read domain_name from:"
    echo "${CONTROL_FILE}"

    exit 1

fi


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base


cd "${SCRIPT_DIR}"


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "NWAM MULTIBASIN DOMAIN PREPARATION"
echo "======================================================================"
echo
echo "Domain       : ${DOMAIN}"
echo "Control file : ${CONTROL_FILE}"
echo "CWARHM root  : ${CWARHM}"
echo "Start time   : $(date)"
echo


# ============================================================
# STEP 1
# PREPARE RIVER NETWORK
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "STEP 1: PREPARE RIVER NETWORK"
echo "----------------------------------------------------------------------"
echo


conda run --no-capture-output -n nwam \
    python "${RIVER_SCRIPT}" \
    "${CONTROL_FILE}"


echo
echo "River-network preparation completed."


# ============================================================
# STEP 2
# PREPARE CATCHMENT
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "STEP 2: PREPARE CATCHMENT"
echo "----------------------------------------------------------------------"
echo


conda run --no-capture-output -n nwam \
    python "${CATCHMENT_SCRIPT}" \
    "${CONTROL_FILE}"


echo
echo "Catchment preparation completed."


# ============================================================
# STEP 3
# REPORT / VERIFY CONTROL VALUES
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "STEP 3: REPORT DOMAIN VALUES"
echo "----------------------------------------------------------------------"
echo


REPORT_OUTPUT=$(
    conda run --no-capture-output -n nwam \
        python "${REPORT_SCRIPT}" \
        "${CONTROL_FILE}"
)


echo "${REPORT_OUTPUT}"


# ============================================================
# EXTRACT IMPORTANT VALUES
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "IMPORTANT DOMAIN VALUES"
echo "----------------------------------------------------------------------"


IMPORTANT_VALUES=$(
    printf '%s\n' "${REPORT_OUTPUT}" |
    grep -E \
        "^forcing_raw_space|^settings_mizu_make_outlet" \
        || true
)


if [ -n "${IMPORTANT_VALUES}" ]; then

    echo "${IMPORTANT_VALUES}"

else

    echo "WARNING:"
    echo "forcing_raw_space and/or settings_mizu_make_outlet"
    echo "were not found in the Stage-00 report."

fi


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "DOMAIN PREPARATION COMPLETED SUCCESSFULLY"
echo "======================================================================"
echo
echo "Domain       : ${DOMAIN}"
echo "Control file : ${CONTROL_FILE}"
echo "End time     : $(date)"
echo
echo "No control_active.txt was used or modified."