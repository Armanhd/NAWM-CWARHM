#!/bin/bash
set -euo pipefail

# Crop reprojected MODIS MCD12Q1 VRT files to the active modeling domain.
#
# Usage:
# bash specify_subdomain.sh /path/to/control_DOMAIN.txt
#
# The domain extent is read from:
# forcing_raw_space | LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
#
# Input:  parameters/landclass/3_vrt_epsg_4326/
# Output: parameters/landclass/4_domain_vrt_epsg_4326/

# ============================================================
# INPUT CONTROL FILE
# ============================================================

if [ "$#" -ne 1 ]; then
    echo "Usage:"
    echo "bash specify_subdomain.sh /path/to/control_DOMAIN.txt"
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

source_path=$(read_control "parameter_land_vrt2_path")

if [ "$source_path" = "default" ]; then
    source_path="${domain_path}/parameters/landclass/3_vrt_epsg_4326"
fi

if [ ! -d "$source_path" ]; then
    echo "ERROR: Reprojected MODIS VRT directory not found:"
    echo "$source_path"
    exit 1
fi

# ============================================================
# DESTINATION DIRECTORY
# ============================================================

dest_path=$(read_control "parameter_land_vrt3_path")

if [ "$dest_path" = "default" ]; then
    dest_path="${domain_path}/parameters/landclass/4_domain_vrt_epsg_4326"
fi

mkdir -p "$dest_path"

# ============================================================
# DOMAIN EXTENT
# ============================================================

domain_full=$(read_control "forcing_raw_space")

IFS='/' read -r LAT_MAX LON_MIN LAT_MIN LON_MAX <<< "$domain_full"

if (
    [ -z "${LAT_MAX:-}" ] ||
    [ -z "${LON_MIN:-}" ] ||
    [ -z "${LAT_MIN:-}" ] ||
    [ -z "${LON_MAX:-}" ]
); then
    echo "ERROR: Could not parse forcing_raw_space:"
    echo "$domain_full"
    exit 1
fi

number_regex='^-?[0-9]+([.][0-9]+)?$'

for value in "$LAT_MAX" "$LON_MIN" "$LAT_MIN" "$LON_MAX"; do
    if [[ ! "$value" =~ $number_regex ]]; then
        echo "ERROR: Non-numeric coordinate in forcing_raw_space:"
        echo "$domain_full"
        exit 1
    fi
done

if ! awk -v latmax="$LAT_MAX" -v latmin="$LAT_MIN" \
    'BEGIN { exit !(latmax > latmin) }'; then
    echo "ERROR: LAT_MAX must be greater than LAT_MIN."
    echo "forcing_raw_space: $domain_full"
    exit 1
fi

if ! awk -v lonmax="$LON_MAX" -v lonmin="$LON_MIN" \
    'BEGIN { exit !(lonmax > lonmin) }'; then
    echo "ERROR: LON_MAX must be greater than LON_MIN."
    echo "forcing_raw_space: $domain_full"
    exit 1
fi

# ============================================================
# GDAL CHECK
# ============================================================

if ! command -v gdal_translate >/dev/null 2>&1; then
    echo "ERROR: gdal_translate not found."
    echo
    echo "For the MODIS workflow on ARC, use the GDAL installed"
    echo "inside the nwam Conda environment."
    exit 1
fi

# ============================================================
# FIND INPUT VRT FILES FOR SELECTED YEARS
# ============================================================

LAND_YEARS=$(read_control "parameter_land_years")

if [[ "$LAND_YEARS" =~ ^[0-9]{4}$ ]]; then
    years=("$LAND_YEARS")
elif [[ "$LAND_YEARS" =~ ^([0-9]{4})-([0-9]{4})$ ]]; then
    START_YEAR=${BASH_REMATCH[1]}
    END_YEAR=${BASH_REMATCH[2]}

    if (( 10#$START_YEAR > 10#$END_YEAR )); then
        echo "ERROR: Invalid MODIS year range: $LAND_YEARS" >&2
        exit 1
    fi

    mapfile -t years < <(seq "$START_YEAR" "$END_YEAR")
else
    echo "ERROR: Invalid parameter_land_years: $LAND_YEARS" >&2
    echo "Expected YYYY or YYYY-YYYY" >&2
    exit 1
fi

vrt_files=()

for YEAR in "${years[@]}"; do
    VRT_FILE="${source_path}/MCD12Q1_${YEAR}.vrt"

    if [ ! -s "$VRT_FILE" ]; then
        echo "ERROR: Missing MODIS VRT: $VRT_FILE" >&2
        exit 1
    fi

    vrt_files+=("$VRT_FILE")
done

# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "CROP MODIS MCD12Q1 VRT TO DOMAIN"
echo "======================================================================"
echo
echo "Domain       : $domain_name"
echo "Control file : $CONTROL_FILE"
echo "Source       : $source_path"
echo "Destination  : $dest_path"
echo "MODIS years  : $LAND_YEARS"
echo "VRT files    : ${#vrt_files[@]}"
echo
echo "Domain extent:"
echo "  latitude : $LAT_MIN to $LAT_MAX"
echo "  longitude: $LON_MIN to $LON_MAX"
echo
echo "GDAL         : $(command -v gdal_translate)"
echo "GDAL version : $(gdal_translate --version | head -1)"
echo

# ============================================================
# CROP EACH VRT
# ============================================================

created_count=0

for FILE_SRC in "${vrt_files[@]}"; do
    FILENAME=$(basename "$FILE_SRC")
    FILE_DES="${dest_path}/domain_${FILENAME}"

    echo "----------------------------------------------------------------------"
    echo "Input : $FILE_SRC"
    echo "Output: $FILE_DES"
    echo "----------------------------------------------------------------------"

    rm -f "$FILE_DES"

    gdal_translate \
        -of VRT \
        -r nearest \
        -projwin \
        "$LON_MIN" \
        "$LAT_MAX" \
        "$LON_MAX" \
        "$LAT_MIN" \
        "$FILE_SRC" \
        "$FILE_DES"

    if [ ! -s "$FILE_DES" ]; then
        echo "ERROR: Cropped VRT was not created:"
        echo "$FILE_DES"
        exit 1
    fi

    if ! gdalinfo "$FILE_DES" >/dev/null 2>&1; then
        echo "ERROR: Cropped VRT cannot be opened by GDAL:"
        echo "$FILE_DES"
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
log_file="${log_path}/${timestamp}_crop_modis_domain_vrt.txt"
this_file=$(basename "$0")

{
    echo "Log generated by ${this_file} on $(date '+%F %H:%M:%S')"
    echo "Domain: ${domain_name}"
    echo "Control file: ${CONTROL_FILE}"
    echo "Source VRT directory: ${source_path}"
    echo "Output VRT directory: ${dest_path}"
    echo "MODIS years: ${LAND_YEARS}"
    echo "Domain latitude: ${LAT_MIN} to ${LAT_MAX}"
    echo "Domain longitude: ${LON_MIN} to ${LON_MAX}"
    echo "VRT files processed: ${#vrt_files[@]}"
    echo "VRT files created: ${created_count}"
    echo "GDAL: $(command -v gdal_translate)"
    echo "GDAL version: $(gdal_translate --version | head -1)"
} > "$log_file"

cp "$0" "$log_path/$this_file"
cp "$CONTROL_FILE" "$log_path/$(basename "$CONTROL_FILE")"

# ============================================================
# FINISH
# ============================================================

echo "======================================================================"
echo "MODIS DOMAIN VRT CROPPING COMPLETED"
echo "======================================================================"
echo "Domain       : $domain_name"
echo "Files created: $created_count"
echo "Output folder: $dest_path"
echo "Workflow log : $log_file"
