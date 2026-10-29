#!/bin/bash
set -euo pipefail

# Reproject selected MODIS MCD12Q1 annual VRT files to EPSG:4326.
# Usage: bash reproject_vrt.sh /path/to/control_DOMAIN.txt
# The selected year or inclusive year range is read from
# parameter_land_years (e.g. 2022 or 2001-2018).

# ============================================================
# INPUT CONTROL FILE
# ============================================================
if [ "$#" -ne 1 ]; then
    echo "Usage: bash reproject_vrt.sh /path/to/control_DOMAIN.txt" >&2
    exit 1
fi

CONTROL_FILE=$(realpath "$1")
if [ ! -f "$CONTROL_FILE" ]; then
    echo "ERROR: Control file not found: $CONTROL_FILE" >&2
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
    echo "ERROR: Source MODIS VRT directory not found: $source_path" >&2
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
for program in gdalwarp gdalinfo gdalsrsinfo; do
    if ! command -v "$program" >/dev/null 2>&1; then
        echo "ERROR: $program was not found in PATH." >&2
        exit 1
    fi
done

# ============================================================
# SELECT YEARS FROM CONTROL FILE
# ============================================================
LAND_YEARS=$(read_control "parameter_land_years")
if [[ "$LAND_YEARS" =~ ^[0-9]{4}$ ]]; then
    years=("$LAND_YEARS")
elif [[ "$LAND_YEARS" =~ ^([0-9]{4})-([0-9]{4})$ ]]; then
    start_year="${BASH_REMATCH[1]}"
    end_year="${BASH_REMATCH[2]}"
    if (( 10#$start_year > 10#$end_year )); then
        echo "ERROR: Invalid MODIS year range: $LAND_YEARS" >&2
        exit 1
    fi
    mapfile -t years < <(seq "$start_year" "$end_year")
else
    echo "ERROR: Invalid parameter_land_years: $LAND_YEARS" >&2
    echo "Expected YYYY or YYYY-YYYY" >&2
    exit 1
fi

# Require precisely the requested annual source VRTs.
source_files=()
for YEAR in "${years[@]}"; do
    source_file="${source_path}/MCD12Q1_${YEAR}.vrt"
    if [ ! -s "$source_file" ]; then
        echo "ERROR: Required MODIS VRT missing: $source_file" >&2
        exit 1
    fi
    source_files+=("$source_file")
done

# ============================================================
# REPORT
# ============================================================
TARGET_CRS="EPSG:4326"
echo
echo "======================================================================"
echo "REPROJECT MODIS MCD12Q1 VRT TO EPSG:4326"
echo "======================================================================"
echo "Domain       : $domain_name"
echo "Control file : $CONTROL_FILE"
echo "Source       : $source_path"
echo "Destination  : $dest_path"
echo "MODIS years  : ${years[*]}"
echo "VRT files    : ${#source_files[@]}"
echo "Target CRS   : $TARGET_CRS"
echo "Resampling   : nearest neighbour (categorical classes)"
echo "GDAL         : $(command -v gdalwarp)"
echo "GDAL version : $(gdalinfo --version)"
echo

# ============================================================
# REPROJECT SELECTED VRT FILES
# ============================================================
created_count=0
for FILE_SRC in "${source_files[@]}"; do
    FILENAME=$(basename "$FILE_SRC")
    FILE_DES="${dest_path}/${FILENAME}"
    echo "----------------------------------------------------------------------"
    echo "Input : $FILE_SRC"
    echo "Output: $FILE_DES"
    echo "----------------------------------------------------------------------"

    # Use a temporary file to avoid deleting a valid prior result
    # if the new warp fails. Keep it in the destination directory.
    FILE_TMP="${dest_path}/.${FILENAME}.tmp.$$.vrt"
    rm -f "$FILE_TMP"
    if ! gdalwarp \
        -of VRT \
        -t_srs "$TARGET_CRS" \
        -r near \
        "$FILE_SRC" \
        "$FILE_TMP"; then
        rm -f "$FILE_TMP"
        echo "ERROR: Reprojection failed for $FILE_SRC" >&2
        exit 1
    fi
    if [ ! -s "$FILE_TMP" ] || ! gdalinfo "$FILE_TMP" >/dev/null 2>&1; then
        rm -f "$FILE_TMP"
        echo "ERROR: Reprojected VRT missing or unreadable: $FILE_TMP" >&2
        exit 1
    fi

    output_epsg=$(
        gdalsrsinfo -o epsg "$FILE_TMP" 2>/dev/null \
        | grep -o 'EPSG:[0-9]*' \
        | head -1 || true
    )
    if [ "$output_epsg" != "$TARGET_CRS" ]; then
        rm -f "$FILE_TMP"
        echo "ERROR: Unexpected output CRS: ${output_epsg:-unknown}" >&2
        exit 1
    fi

    mv -f "$FILE_TMP" "$FILE_DES"
    created_count=$((created_count + 1))
    echo "Created successfully: $FILE_DES"
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
    echo "Selected MODIS years: ${LAND_YEARS}"
    echo "Target CRS: ${TARGET_CRS}"
    echo "Resampling: near"
    echo "VRT files processed: ${created_count}"
    echo "GDAL: $(command -v gdalwarp)"
    echo "GDAL version: $(gdalinfo --version)"
} > "$log_file"
cp "$0" "$log_path/$this_file"
cp "$CONTROL_FILE" "$log_path/$(basename "$CONTROL_FILE")"

echo "======================================================================"
echo "MODIS VRT REPROJECTION COMPLETED"
echo "======================================================================"
echo "Domain       : $domain_name"
echo "Years        : $LAND_YEARS"
echo "Files created: $created_count"
echo "Target CRS   : $TARGET_CRS"
echo "Output folder: $dest_path"
echo "Workflow log : $log_file"
