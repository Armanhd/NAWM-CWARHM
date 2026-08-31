#!/bin/bash
#SBATCH --job-name=nwam_hru_param
#SBATCH --time=04:00:00
#SBATCH --mem=12G
#SBATCH --cpus-per-task=2
#SBATCH --output=slurm_logs/hru_parameter_%A_%a.out
#SBATCH --error=slurm_logs/hru_parameter_%A_%a.err

# ============================================================
# NWAM MULTIBASIN HRU PARAMETER REMAPPING WORKER
# ============================================================
#
# One Slurm array task processes one basin/domain.
#
# Workflow
# --------
#
#   1. Map MERIT-Hydro elevation to HRUs
#   2. Map SoilGrids soil classes to HRUs
#   3. Map MODIS/IGBP land classes to HRUs
#
# Input task file
# ---------------
#
# One absolute control-file path per line:
#
#   /work/.../control_MERIT_861.txt
#   /work/.../control_MERIT_862.txt
#   /work/.../control_MERIT_863.txt
#
# IMPORTANT
# ---------
#
# This worker:
#
#   - does NOT use control_active.txt
#   - does NOT modify control files
#   - processes one basin per array task
#   - stops the current basin if one step fails
#   - does not stop independent array tasks for other basins
#
# Example
# -------
#
# TASK_FILE="/work/comphyd_lab/users/arman.haddadchi/NWAM/\
# CWARHM_multibasin/0_control_files/\
# multibasin_preprocessing_MERIT_86.txt"
#
# N=$(wc -l < "${TASK_FILE}")
#
# sbatch \
#     --array=0-$((N-1))%6 \
#     run_multibasin_HRU_parameter_remapping_array.sh \
#     "${TASK_FILE}"
#
# ============================================================

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

SCRIPT_DIR="${CWARHM}/4b_remapping/1_topo"

ELEVATION_SCRIPT="${SCRIPT_DIR}/1_find_HRU_elevation.py"

SOIL_SCRIPT="${SCRIPT_DIR}/2_find_HRU_soil_classes.py"

LAND_SCRIPT="${SCRIPT_DIR}/3_find_HRU_land_classes.py"


# ============================================================
# INPUT TASK FILE
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "ERROR: A multibasin task file must be supplied."
    echo
    echo "Usage:"
    echo "  sbatch --array=0-N%6 \\"
    echo "    run_multibasin_HRU_parameter_remapping_array.sh \\"
    echo "    /path/to/multibasin_preprocessing.txt"

    exit 1

fi


TASK_FILE=$(realpath "$1")


if [ ! -f "${TASK_FILE}" ]; then

    echo "ERROR: Task file not found:"
    echo "${TASK_FILE}"

    exit 1

fi


# ============================================================
# SLURM ARRAY TASK
# ============================================================

if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then

    echo "ERROR: SLURM_ARRAY_TASK_ID is not defined."
    echo "Submit this script as a Slurm array."

    exit 1

fi


LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))


CONTROL_FILE=$(
    sed -n "${LINE_NUMBER}p" "${TASK_FILE}" \
    | xargs
)


if [ -z "${CONTROL_FILE}" ]; then

    echo "ERROR: No control file found for array index:"
    echo "${SLURM_ARRAY_TASK_ID}"

    exit 1

fi


CONTROL_FILE=$(realpath "${CONTROL_FILE}")


if [ ! -f "${CONTROL_FILE}" ]; then

    echo "ERROR: Control file not found:"
    echo "${CONTROL_FILE}"

    exit 1

fi


# ============================================================
# CONTROL-FILE READER
# ============================================================
read_control() {

    local setting="$1"
    local line
    local value

    line=$(
        grep -m 1 "^[[:space:]]*${setting}[[:space:]]*|" \
        "${CONTROL_FILE}" \
        || true
    )

    if [ -z "${line}" ]; then

        echo "ERROR: Setting not found or empty:" >&2
        echo "${setting}" >&2
        echo "Control file:" >&2
        echo "${CONTROL_FILE}" >&2

        exit 1

    fi

    value="${line#*|}"
    value="${value%%#*}"

    value=$(
        echo "${value}" | xargs
    )

    if [ -z "${value}" ]; then

        echo "ERROR: Setting found but value is empty:" >&2
        echo "${setting}" >&2
        echo "Control file:" >&2
        echo "${CONTROL_FILE}" >&2

        exit 1

    fi

    echo "${value}"
}

# ============================================================
# DOMAIN INFORMATION
# ============================================================

DOMAIN=$(read_control "domain_name")

ROOT_PATH=$(read_control "root_path")

DOMAIN_ROOT="${ROOT_PATH}/domain_${DOMAIN}"


# ============================================================
# VALIDATE WORKFLOW SCRIPTS
# ============================================================

for FILE in \
    "${ELEVATION_SCRIPT}" \
    "${SOIL_SCRIPT}" \
    "${LAND_SCRIPT}"
do

    if [ ! -f "${FILE}" ]; then

        echo "ERROR: Required workflow script not found:"
        echo "${FILE}"

        exit 1

    fi

done


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base


mkdir -p "${SCRIPT_DIR}/slurm_logs"


cd "${SCRIPT_DIR}"


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "NWAM MULTIBASIN HRU PARAMETER REMAPPING"
echo "======================================================================"
echo
echo "Slurm job ID   : ${SLURM_JOB_ID:-unknown}"
echo "Array task ID  : ${SLURM_ARRAY_TASK_ID}"
echo "Task-file line : ${LINE_NUMBER}"
echo
echo "Domain         : ${DOMAIN}"
echo "Control file   : ${CONTROL_FILE}"
echo "Domain root    : ${DOMAIN_ROOT}"
echo "Task file      : ${TASK_FILE}"
echo
echo "Start time     : $(date)"
echo


# ============================================================
# INPUT PARAMETER DATA
# ============================================================

DEM_PATH=$(read_control "parameter_dem_tif_path")
DEM_NAME=$(read_control "parameter_dem_tif_name")

SOIL_PATH=$(read_control "parameter_soil_domain_path")
SOIL_NAME=$(read_control "parameter_soil_tif_name")

LAND_PATH=$(read_control "parameter_land_mode_path")
LAND_NAME=$(read_control "parameter_land_tif_name")


if [ "${DEM_PATH}" = "default" ]; then

    DEM_PATH="${DOMAIN_ROOT}/parameters/dem/5_elevation"

fi


if [ "${SOIL_PATH}" = "default" ]; then

    SOIL_PATH="${DOMAIN_ROOT}/parameters/soilclass/2_soil_classes_domain"

fi


if [ "${LAND_PATH}" = "default" ]; then

    LAND_PATH="${DOMAIN_ROOT}/parameters/landclass/7_mode_land_class"

fi


DEM_FILE="${DEM_PATH}/${DEM_NAME}"

SOIL_FILE="${SOIL_PATH}/${SOIL_NAME}"

LAND_FILE="${LAND_PATH}/${LAND_NAME}"


echo "Input parameter rasters"
echo "----------------------------------------------------------------------"
echo
echo "DEM        : ${DEM_FILE}"
echo "Soil class : ${SOIL_FILE}"
echo "Land class : ${LAND_FILE}"
echo


# ============================================================
# VERIFY INPUT PARAMETER DATA
# ============================================================

for FILE in \
    "${DEM_FILE}" \
    "${SOIL_FILE}" \
    "${LAND_FILE}"
do

    if [ ! -s "${FILE}" ]; then

        echo "ERROR: Required parameter raster not found or empty:"
        echo "${FILE}"

        exit 1

    fi

done


echo "Parameter raster inputs: PASS"


# ============================================================
# STEP 1
# HRU ELEVATION
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "STEP 1: MAP MERIT-HYDRO ELEVATION TO HRUS"
echo "----------------------------------------------------------------------"
echo


conda run --no-capture-output -n nwam \
    python "${ELEVATION_SCRIPT}" \
    "${CONTROL_FILE}"


echo
echo "HRU elevation mapping passed."


# ============================================================
# STEP 2
# HRU SOIL CLASSES
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "STEP 2: MAP SOIL CLASSES TO HRUS"
echo "----------------------------------------------------------------------"
echo


conda run --no-capture-output -n nwam \
    python "${SOIL_SCRIPT}" \
    "${CONTROL_FILE}"


echo
echo "HRU soil-class mapping passed."


# ============================================================
# STEP 3
# HRU LAND CLASSES
# ============================================================

echo
echo "----------------------------------------------------------------------"
echo "STEP 3: MAP MODIS LAND CLASSES TO HRUS"
echo "----------------------------------------------------------------------"
echo


conda run --no-capture-output -n nwam \
    python "${LAND_SCRIPT}" \
    "${CONTROL_FILE}"


echo
echo "HRU land-class mapping passed."


# ============================================================
# RESOLVE EXPECTED OUTPUTS
# ============================================================

DEM_INTERSECT_PATH=$(read_control "intersect_dem_path")
DEM_INTERSECT_NAME=$(read_control "intersect_dem_name")

SOIL_INTERSECT_PATH=$(read_control "intersect_soil_path")
SOIL_INTERSECT_NAME=$(read_control "intersect_soil_name")

LAND_INTERSECT_PATH=$(read_control "intersect_land_path")
LAND_INTERSECT_NAME=$(read_control "intersect_land_name")


if [ "${DEM_INTERSECT_PATH}" = "default" ]; then

    DEM_INTERSECT_PATH="${DOMAIN_ROOT}/shapefiles/catchment_intersection/with_dem"

fi


if [ "${SOIL_INTERSECT_PATH}" = "default" ]; then

    SOIL_INTERSECT_PATH="${DOMAIN_ROOT}/shapefiles/catchment_intersection/with_soilgrids"

fi


if [ "${LAND_INTERSECT_PATH}" = "default" ]; then

    LAND_INTERSECT_PATH="${DOMAIN_ROOT}/shapefiles/catchment_intersection/with_modis"

fi


DEM_OUTPUT="${DEM_INTERSECT_PATH}/${DEM_INTERSECT_NAME}"

SOIL_OUTPUT="${SOIL_INTERSECT_PATH}/${SOIL_INTERSECT_NAME}"

LAND_OUTPUT="${LAND_INTERSECT_PATH}/${LAND_INTERSECT_NAME}"


# ============================================================
# VERIFY OUTPUT FILES
# ============================================================

echo
echo "======================================================================"
echo "VERIFY HRU PARAMETER OUTPUTS"
echo "======================================================================"
echo


if [ ! -s "${DEM_OUTPUT}" ]; then

    echo "ERROR: HRU elevation shapefile not found:"
    echo "${DEM_OUTPUT}"

    exit 1

fi


echo "HRU elevation:"
echo "  PASS"
echo "  ${DEM_OUTPUT}"
echo


if [ ! -s "${SOIL_OUTPUT}" ]; then

    echo "ERROR: HRU soil-class shapefile not found:"
    echo "${SOIL_OUTPUT}"

    exit 1

fi


echo "HRU soil class:"
echo "  PASS"
echo "  ${SOIL_OUTPUT}"
echo


if [ ! -s "${LAND_OUTPUT}" ]; then

    echo "ERROR: HRU land-class shapefile not found:"
    echo "${LAND_OUTPUT}"

    exit 1

fi


echo "HRU land class:"
echo "  PASS"
echo "  ${LAND_OUTPUT}"
echo


# ============================================================
# BASIC ATTRIBUTE VERIFICATION
# ============================================================

conda run --no-capture-output -n nwam \
python - \
"${DEM_OUTPUT}" \
"${SOIL_OUTPUT}" \
"${LAND_OUTPUT}" <<'PY'

import sys

import geopandas as gpd
import numpy as np


dem_file = sys.argv[1]
soil_file = sys.argv[2]
land_file = sys.argv[3]


dem = gpd.read_file(
    dem_file,
    engine="fiona"
)

soil = gpd.read_file(
    soil_file,
    engine="fiona"
)

land = gpd.read_file(
    land_file,
    engine="fiona"
)


counts = {
    "DEM": len(dem),
    "Soil": len(soil),
    "Land": len(land),
}


if len(set(counts.values())) != 1:

    raise RuntimeError(
        "HRU counts differ between parameter outputs:\n"
        + "\n".join(
            f"  {name}: {count}"
            for name, count in counts.items()
        )
    )


if "elev_mean" not in dem.columns:

    raise RuntimeError(
        "elev_mean missing from DEM intersection."
    )


if not np.all(
    np.isfinite(
        dem["elev_mean"].astype(float)
    )
):

    raise RuntimeError(
        "DEM intersection contains invalid elev_mean values."
    )


soil_fields = [
    name
    for name in soil.columns
    if name.startswith("USGS_")
]


if not soil_fields:

    raise RuntimeError(
        "No USGS soil-class fields found."
    )


land_fields = [
    name
    for name in land.columns
    if name.startswith("IGBP_")
]


if not land_fields:

    raise RuntimeError(
        "No IGBP land-class fields found."
    )


print()
print("Attribute verification:")
print("  PASS")
print()
print(f"HRUs             : {len(dem)}")
print(f"Soil class fields: {len(soil_fields)}")
print(f"Land class fields: {len(land_fields)}")

PY


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "NWAM HRU PARAMETER REMAPPING COMPLETED SUCCESSFULLY"
echo "======================================================================"
echo
echo "Domain       : ${DOMAIN}"
echo "Control file : ${CONTROL_FILE}"
echo
echo "HRU elevation:"
echo "  ${DEM_OUTPUT}"
echo
echo "HRU soil class:"
echo "  ${SOIL_OUTPUT}"
echo
echo "HRU land class:"
echo "  ${LAND_OUTPUT}"
echo
echo "End time     : $(date)"
echo
echo "Next workflow stage:"
echo "  Generate SUMMA and mizuRoute model-input files."
echo
echo "No control_active.txt was used or modified."