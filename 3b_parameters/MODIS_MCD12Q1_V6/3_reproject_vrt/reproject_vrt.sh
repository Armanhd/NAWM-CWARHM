#!/bin/bash
set -euo pipefail

# Reproject MODIS MCD12Q1 VRT files to EPSG:4326.
#
# Usage:
#
# bash reproject_vrt.sh \
# /path/to/control_DOMAIN.txt
#
# This script is multibasin-safe:
#   - it does NOT use control_active.txt
#   - it receives the domain-specific control file explicitly
#   - all paths are resolved from that control file

# ============================================================
# INPUT CONTROL FILE
# ============================================================

if [ "$#" -ne 1 ]; then
    echo "Usage:"
    echo "bash reproject_vrt.sh /path/to/control_DOMAIN.txt"
    exit 1
fi

CONTROL_FILE=$(realpath "$1")

if [ ! -f "$CONTROL_FILE" ]; then
    echo "ERROR: Control file not found:"
    echo "$CONTROL_FILE"
    exit 1
fi


# ============================================================
# CONTROL-FILE READER
# ============================================================

read_control() {

    local setting="$1"
    local value

    value=$(
        grep -m 1 "^${setting}[[:space:]]*|" "$CONTROL_FILE" \
        | cut -d'|' -f2- \
        | cut -d'#' -f1 \
        | xargs
    )

    if [ -z "$value" ]; then
        echo "ERROR: Setting not found or empty: $setting" >&2
        exit 1
    fi

    echo "$value"
}


# ============================================================
# DOMAIN SETTINGS
# ============================================================

root_path=$(read_control "root_path")
domain_name=$(read_control "domain_name")

domain_path="${root_path}/domain_${domain_name}"


# ============================================================
# SOURCE VRT DIRECTORY
# ============================================================

source_path=$(read_control "parameter_land_vrt1_path")

if [ "$source_path" = "default" ]; then
    source_path="${domain_path}/parameters/landclass/2_vrt_native_crs"
fi

if [ ! -d "$source_path" ]; then
    echo "ERROR: Source MODIS VRT directory not found:"
    echo "$source_path"
    exit 1
fi


# ============================================================
# DESTINATION DIRECTORY
# ============================================================

dest_path=$(read_control "parameter_land_vrt2_path")

if [ "$dest_path" = "default" ]; then
    dest_path="${domain_path}/parameters/landclass/3_vrt_epsg_4326"
fi

mkdir -p "$dest_path"


# ============================================================
# GDAL CHECK
# ============================================================

if ! command -v gdalwarp >/dev/null 2>&1; then
    echo "ERROR: gdalwarp was not found in PATH."
    echo
    echo "Current PATH:"
    echo "$PATH"
    exit 1
fi

if ! command -v gdalinfo >/dev/null 2>&1; then
    echo "ERROR: gdalinfo was not found in PATH."
    exit 1
fi


# ============================================================
# TARGET CRS
# ============================================================

TARGET_CRS="EPSG:4326"


# ============================================================
# FIND SOURCE VRT FILES
# ============================================================

mapfile -t source_files < <(
    find "$source_path" \
        -maxdepth 1 \
        -type f \
        -name "MCD12Q1_*.vrt" \
        | sort
)

if [ "${#source_files[@]}" -eq 0 ]; then
    echo "ERROR: No MODIS MCD12Q1 VRT files found in:"
    echo "$source_path"
    echo
    echo "Expected something like:"
    echo "MCD12Q1_2022.vrt"
    exit 1
fi


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "REPROJECT MODIS MCD12Q1 VRT TO EPSG:4326"
echo "======================================================================"
echo
echo "Domain       : $domain_name"
echo "Control file : $CONTROL_FILE"
echo "Source       : $source_path"
echo "Destination  : $dest_path"
echo "Target CRS   : $TARGET_CRS"
echo "VRT files    : ${#source_files[@]}"
echo "GDAL         : $(command -v gdalwarp)"
echo "GDAL version : $(gdalinfo --version)"
echo


# ============================================================
# REPROJECT VRT FILES
# ============================================================

created_count=0

for FILE_SRC in "${source_files[@]}"; do

    FILENAME=$(basename "$FILE_SRC")

    FILE_DES="${dest_path}/${FILENAME}"

    echo "----------------------------------------------------------------------"
    echo "Input : $FILE_SRC"
    echo "Output: $FILE_DES"
    echo "----------------------------------------------------------------------"

    rm -f "$FILE_DES"

    gdalwarp \
        -of VRT \
        -t_srs "$TARGET_CRS" \
        "$FILE_SRC" \
        "$FILE_DES"

    if [ ! -s "$FILE_DES" ]; then
        echo "ERROR: Reprojected VRT was not created:"
        echo "$FILE_DES"
        exit 1
    fi

    # Verify CRS
    output_epsg=$(
        gdalsrsinfo \
            -o epsg \
            "$FILE_DES" \
            2>/dev/null \
        | grep -o 'EPSG:[0-9]*' \
        | head -1 \
        || true
    )

    if [ "$output_epsg" != "EPSG:4326" ]; then
        echo "ERROR: Unexpected output CRS."
        echo "Expected: EPSG:4326"
        echo "Found   : ${output_epsg:-unknown}"
        echo "File    : $FILE_DES"
        exit 1
    fi

    created_count=$((created_count + 1))

    echo
    echo "Created successfully:"
    echo "$FILE_DES"
    echo
done


# ============================================================
# WORKFLOW LOG
# ============================================================

log_path="${dest_path}/_workflow_log"

mkdir -p "$log_path"

timestamp=$(date '+%Y%m%d_%H%M%S')

log_file="${log_path}/${timestamp}_reproject_modis_vrt.txt"

this_file=$(basename "$0")

{
    echo "Log generated by ${this_file} on $(date '+%F %H:%M:%S')"
    echo "Domain: ${domain_name}"
    echo "Control file: ${CONTROL_FILE}"
    echo "Source directory: ${source_path}"
    echo "Destination directory: ${dest_path}"
    echo "Target CRS: ${TARGET_CRS}"
    echo "VRT files processed: ${created_count}"
    echo "GDAL: $(command -v gdalwarp)"
    echo "GDAL version: $(gdalinfo --version)"
} > "$log_file"

cp "$0" "$log_path/$this_file"


# ============================================================
# FINISH
# ============================================================

echo "======================================================================"
echo "MODIS VRT REPROJECTION COMPLETED"
echo "======================================================================"
echo "Domain       : $domain_name"
echo "Files created: $created_count"
echo "Target CRS   : $TARGET_CRS"
echo "Output folder: $dest_path"
echo "Workflow log : $log_file"