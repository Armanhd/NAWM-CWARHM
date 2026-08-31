#!/bin/bash
#SBATCH --job-name=nwam_param_data
#SBATCH --time=06:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2
#SBATCH --output=slurm_logs/parameter_data_%A_%a.out
#SBATCH --error=slurm_logs/parameter_data_%A_%a.err

# ============================================================
# NWAM MULTIBASIN PARAMETER-DATA PREPROCESSING WORKER
# ============================================================
#
# One Slurm array task processes one domain.
#
# Workflow
# --------
#
# MERIT-Hydro DEM
#   1. Link existing MERIT-Hydro elevation archives
#   2. Unpack required archives
#   3. Create MERIT-Hydro VRT
#   4. Crop VRT to domain
#   5. Convert domain VRT to elevation.tif
#
# SoilGrids
#   6. Crop existing global soil-class raster to domain
#
# MODIS MCD12Q1
#   7. Create yearly MODIS VRT
#   8. Reproject MODIS VRT to EPSG:4326
#   9. Crop MODIS VRT to domain
#  10. Create multiband domain VRT
#  11. Convert multiband VRT to GeoTIFF
#  12. Create representative/modal land-class raster
#
# IMPORTANT
# ---------
#
# - One array task = one basin/domain.
# - Failure in one basin does NOT stop other array tasks.
# - Within one basin, steps run sequentially.
# - set -euo pipefail causes that basin to stop immediately
#   if any required step fails.
# - No control_active.txt is used or modified.
#
# Task-file format
# ----------------
#
# One absolute control-file path per line:
#
# /work/.../control_MERIT_861.txt
# /work/.../control_MERIT_862.txt
# /work/.../control_MERIT_863.txt
#
# Example test for MERIT_863 (third line):
#
# sbatch \
#     --array=2-2 \
#     run_multibasin_parameter_data_preprocessing_array.sh \
#     /work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/multibasin_preprocessing_MERIT_86.txt
#
# Example six-basin run:
#
# sbatch \
#     --array=0-5%3 \
#     run_multibasin_parameter_data_preprocessing_array.sh \
#     /work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/multibasin_preprocessing_MERIT_86.txt
#
# ============================================================

set -euo pipefail


# ============================================================
# CWARHM ROOT
# ============================================================

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"

PARAM_DIR="${CWARHM}/3b_parameters"


# ============================================================
# WORKFLOW SCRIPTS
# ============================================================

# MERIT-Hydro

DEM_LINK="${PARAM_DIR}/MERIT_Hydro_DEM/0_link_existing_tiles.py"

DEM_UNPACK="${PARAM_DIR}/MERIT_Hydro_DEM/2_unpack/unpack_merit_hydro_dem.sh"

DEM_VRT="${PARAM_DIR}/MERIT_Hydro_DEM/3_create_vrt/make_merit_dem_vrt.sh"

DEM_CROP="${PARAM_DIR}/MERIT_Hydro_DEM/4_specify_subdomain/specify_subdomain.sh"

DEM_TIF="${PARAM_DIR}/MERIT_Hydro_DEM/5_convert_to_tif/convert_vrt_to_tif.sh"


# SoilGrids

SOIL_EXTRACT="${PARAM_DIR}/SOILGRIDS/2_extract_domain/extract_domain.py"


# MODIS

MODIS_VRT="${PARAM_DIR}/MODIS_MCD12Q1_V6/2_create_vrt/make_vrt_per_year.sh"

MODIS_REPROJECT="${PARAM_DIR}/MODIS_MCD12Q1_V6/3_reproject_vrt/reproject_vrt.sh"

MODIS_CROP="${PARAM_DIR}/MODIS_MCD12Q1_V6/4_specify_subdomain/specify_subdomain.sh"

MODIS_MULTIBAND="${PARAM_DIR}/MODIS_MCD12Q1_V6/5_multiband_vrt/create_multiband_vrt.sh"

MODIS_TIF="${PARAM_DIR}/MODIS_MCD12Q1_V6/6_convert_to_tif/convert_vrt_to_tif.sh"

MODIS_MODE="${PARAM_DIR}/MODIS_MCD12Q1_V6/7_find_mode_land_class/find_mode_landclass.py"


# ============================================================
# INPUT TASK FILE
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "ERROR: One preprocessing task file must be supplied."
    echo
    echo "Usage:"
    echo
    echo "sbatch --array=0-N \\"
    echo "    run_multibasin_parameter_data_preprocessing_array.sh \\"
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
# CHECK SLURM ARRAY ID
# ============================================================

if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then

    echo "ERROR: SLURM_ARRAY_TASK_ID is not defined."
    echo "Submit this script as a Slurm array."

    exit 1
fi


# ============================================================
# SELECT CONTROL FILE
# ============================================================

LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))


CONTROL_FILE=$(
    sed -n "${LINE_NUMBER}p" "${TASK_FILE}" \
    | xargs
)


if [ -z "${CONTROL_FILE}" ]; then

    echo "ERROR: No control file found for array task:"
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
    local value

    value=$(
        grep -m 1 "^[[:space:]]*${setting}[[:space:]]*|" "${CONTROL_FILE}" \
        | cut -d'|' -f2- \
        | cut -d'#' -f1 \
        | xargs
    )

    if [ -z "${value}" ]; then

        echo "ERROR: Setting not found or empty:"
        echo "${setting}"
        echo
        echo "Control file:"
        echo "${CONTROL_FILE}"

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
# VALIDATE REQUIRED WORKFLOW FILES
# ============================================================

REQUIRED_FILES=(
    "${DEM_LINK}"
    "${DEM_UNPACK}"
    "${DEM_VRT}"
    "${DEM_CROP}"
    "${DEM_TIF}"
    "${SOIL_EXTRACT}"
    "${MODIS_VRT}"
    "${MODIS_REPROJECT}"
    "${MODIS_CROP}"
    "${MODIS_MULTIBAND}"
    "${MODIS_TIF}"
    "${MODIS_MODE}"
)


for FILE in "${REQUIRED_FILES[@]}"; do

    if [ ! -f "${FILE}" ]; then

        echo "ERROR: Required workflow file not found:"
        echo "${FILE}"

        exit 1
    fi

done


# ============================================================
# ENVIRONMENT
# ============================================================

module load conda/base


# Activate nwam so all shell scripts use the GDAL installation
# from the nwam environment. This is particularly important
# for MODIS HDF4 support.

CONDA_BASE=$(conda info --base)

source "${CONDA_BASE}/etc/profile.d/conda.sh"

conda activate nwam


# ============================================================
# LOG DIRECTORY
# ============================================================

mkdir -p "${PARAM_DIR}/slurm_logs"


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "NWAM MULTIBASIN PARAMETER-DATA PREPROCESSING"
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
echo "Python         : $(command -v python)"
echo "GDAL           : $(command -v gdalinfo || true)"
echo "Start time     : $(date)"
echo


# ============================================================
# MERIT-HYDRO DEM
# ============================================================

echo
echo "======================================================================"
echo "PART A: MERIT-HYDRO DEM"
echo "======================================================================"


# ------------------------------------------------------------
# STEP 1
# LINK REQUIRED MERIT-HYDRO ARCHIVES
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 1: LINK MERIT-HYDRO TILES"
echo "----------------------------------------------------------------------"
echo


python "${DEM_LINK}" \
    "${CONTROL_FILE}"


echo
echo "MERIT-Hydro tile linking passed."


# ------------------------------------------------------------
# STEP 2
# UNPACK MERIT-HYDRO ARCHIVES
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 2: UNPACK MERIT-HYDRO TILES"
echo "----------------------------------------------------------------------"
echo


bash "${DEM_UNPACK}" \
    "${CONTROL_FILE}"


echo
echo "MERIT-Hydro unpacking passed."


# ------------------------------------------------------------
# STEP 3
# CREATE MERIT-HYDRO VRT
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 3: CREATE MERIT-HYDRO VRT"
echo "----------------------------------------------------------------------"
echo


bash "${DEM_VRT}" \
    "${CONTROL_FILE}"


echo
echo "MERIT-Hydro VRT creation passed."


# ------------------------------------------------------------
# STEP 4
# CROP MERIT-HYDRO VRT
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 4: CROP MERIT-HYDRO DEM TO DOMAIN"
echo "----------------------------------------------------------------------"
echo


bash "${DEM_CROP}" \
    "${CONTROL_FILE}"


echo
echo "MERIT-Hydro domain cropping passed."


# ------------------------------------------------------------
# STEP 5
# CREATE FINAL DEM TIFF
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 5: CREATE DOMAIN ELEVATION GEOTIFF"
echo "----------------------------------------------------------------------"
echo


bash "${DEM_TIF}" \
    "${CONTROL_FILE}"


echo
echo "MERIT-Hydro GeoTIFF creation passed."


# ============================================================
# SOILGRIDS
# ============================================================

echo
echo "======================================================================"
echo "PART B: SOILGRIDS"
echo "======================================================================"


# ------------------------------------------------------------
# STEP 6
# EXTRACT DOMAIN SOIL CLASS
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 6: EXTRACT SOILGRIDS DOMAIN"
echo "----------------------------------------------------------------------"
echo


python "${SOIL_EXTRACT}" \
    "${CONTROL_FILE}"


echo
echo "SoilGrids domain extraction passed."


# ============================================================
# MODIS
# ============================================================

echo
echo "======================================================================"
echo "PART C: MODIS MCD12Q1"
echo "======================================================================"


# ------------------------------------------------------------
# STEP 7
# CREATE YEARLY MODIS VRT
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 7: CREATE MODIS YEARLY VRT"
echo "----------------------------------------------------------------------"
echo


bash "${MODIS_VRT}" \
    "${CONTROL_FILE}"


echo
echo "MODIS yearly VRT creation passed."


# ------------------------------------------------------------
# STEP 8
# REPROJECT MODIS VRT
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 8: REPROJECT MODIS VRT TO EPSG:4326"
echo "----------------------------------------------------------------------"
echo


bash "${MODIS_REPROJECT}" \
    "${CONTROL_FILE}"


echo
echo "MODIS reprojection passed."


# ------------------------------------------------------------
# STEP 9
# CROP MODIS TO DOMAIN
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 9: CROP MODIS TO DOMAIN"
echo "----------------------------------------------------------------------"
echo


bash "${MODIS_CROP}" \
    "${CONTROL_FILE}"


echo
echo "MODIS domain cropping passed."


# ------------------------------------------------------------
# STEP 10
# CREATE MULTIBAND VRT
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 10: CREATE MODIS MULTIBAND VRT"
echo "----------------------------------------------------------------------"
echo


bash "${MODIS_MULTIBAND}" \
    "${CONTROL_FILE}"


echo
echo "MODIS multiband VRT creation passed."


# ------------------------------------------------------------
# STEP 11
# CONVERT MODIS VRT TO TIFF
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 11: CONVERT MODIS VRT TO GEOTIFF"
echo "----------------------------------------------------------------------"
echo


bash "${MODIS_TIF}" \
    "${CONTROL_FILE}"


echo
echo "MODIS GeoTIFF creation passed."


# ------------------------------------------------------------
# STEP 12
# REPRESENTATIVE / MODE LAND CLASS
# ------------------------------------------------------------

echo
echo "----------------------------------------------------------------------"
echo "STEP 12: CREATE REPRESENTATIVE MODIS LAND CLASS"
echo "----------------------------------------------------------------------"
echo


python "${MODIS_MODE}" \
    "${CONTROL_FILE}"


echo
echo "MODIS representative land-class creation passed."


# ============================================================
# VERIFY FINAL OUTPUTS
# ============================================================

echo
echo "======================================================================"
echo "VERIFY FINAL PARAMETER DATA"
echo "======================================================================"
echo


# ------------------------------------------------------------
# DEM
# ------------------------------------------------------------

DEM_FINAL="${DOMAIN_ROOT}/parameters/dem/5_elevation/elevation.tif"


if [ ! -s "${DEM_FINAL}" ]; then

    echo "ERROR: Final DEM not found or empty:"
    echo "${DEM_FINAL}"

    exit 1
fi


echo "DEM:"
echo "  PASS"
echo "  ${DEM_FINAL}"


# ------------------------------------------------------------
# SOIL
# ------------------------------------------------------------

SOIL_DOMAIN_PATH=$(read_control "parameter_soil_domain_path")


if [ "${SOIL_DOMAIN_PATH}" = "default" ]; then

    SOIL_DOMAIN_PATH="${DOMAIN_ROOT}/parameters/soilclass/2_soil_classes_domain"

fi


SOIL_TIF_NAME=$(read_control "parameter_soil_tif_name")

SOIL_FINAL="${SOIL_DOMAIN_PATH}/${SOIL_TIF_NAME}"


if [ ! -s "${SOIL_FINAL}" ]; then

    echo "ERROR: Final soil-class raster not found or empty:"
    echo "${SOIL_FINAL}"

    exit 1
fi


echo
echo "Soil class:"
echo "  PASS"
echo "  ${SOIL_FINAL}"


# ------------------------------------------------------------
# MODIS REPRESENTATIVE LAND CLASS
# ------------------------------------------------------------

LAND_MODE_PATH=$(read_control "parameter_land_mode_path")


if [ "${LAND_MODE_PATH}" = "default" ]; then

    LAND_MODE_PATH="${DOMAIN_ROOT}/parameters/landclass/7_mode_land_class"

fi


LAND_TIF_NAME=$(read_control "parameter_land_tif_name")

LAND_FINAL="${LAND_MODE_PATH}/${LAND_TIF_NAME}"


if [ ! -s "${LAND_FINAL}" ]; then

    echo "ERROR: Final MODIS land-class raster not found or empty:"
    echo "${LAND_FINAL}"

    exit 1
fi


echo
echo "MODIS land class:"
echo "  PASS"
echo "  ${LAND_FINAL}"


# ============================================================
# GDAL FINAL VALIDATION
# ============================================================

for RASTER in \
    "${DEM_FINAL}" \
    "${SOIL_FINAL}" \
    "${LAND_FINAL}"
do

    if ! gdalinfo "${RASTER}" >/dev/null 2>&1; then

        echo
        echo "ERROR: GDAL cannot open final raster:"
        echo "${RASTER}"

        exit 1
    fi

done


echo
echo "GDAL readability:"
echo "  PASS"


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "NWAM PARAMETER-DATA PREPROCESSING COMPLETED SUCCESSFULLY"
echo "======================================================================"
echo
echo "Domain       : ${DOMAIN}"
echo "Control file : ${CONTROL_FILE}"
echo
echo "Final DEM:"
echo "  ${DEM_FINAL}"
echo
echo "Final soil class:"
echo "  ${SOIL_FINAL}"
echo
echo "Final land class:"
echo "  ${LAND_FINAL}"
echo
echo "End time     : $(date)"
echo
echo "Next workflow stage:"
echo "  Map DEM, soil class and land class to individual HRUs."
echo
echo "No control_active.txt was used or modified."
echo