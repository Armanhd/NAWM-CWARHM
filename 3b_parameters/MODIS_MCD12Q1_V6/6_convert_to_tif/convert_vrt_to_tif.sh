#!/bin/bash
set -euo pipefail

# Convert the MODIS multiband domain VRT to GeoTIFF.
#
# Usage:
#
# bash convert_vrt_to_tif.sh \
# /path/to/control_DOMAIN.txt
#
# Input:
#   parameters/landclass/5_multiband_domain_vrt_epsg_4326/
#
# Output:
#   parameters/landclass/6_tif_multiband/

# ============================================================
# INPUT CONTROL FILE
# ============================================================

if [ "$#" -ne 1 ]; then
    echo "Usage:"
    echo "bash convert_vrt_to_tif.sh /path/to/control_DOMAIN.txt"
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

source_path=$(read_control "parameter_land_vrt4_path")

if [ "$source_path" = "default" ]; then
    source_path="${domain_path}/parameters/landclass/5_multiband_domain_vrt_epsg_4326"
fi

if [ ! -d "$source_path" ]; then
    echo "ERROR: MODIS multiband VRT directory not found:"
    echo "$source_path"
    exit 1
fi


# ============================================================
# DESTINATION DIRECTORY
# ============================================================

dest_path=$(read_control "parameter_land_tif_path")

if [ "$dest_path" = "default" ]; then
    dest_path="${domain_path}/parameters/landclass/6_tif_multiband"
fi

mkdir -p "$dest_path"


# ============================================================
# GDAL CHECK
# ============================================================

if ! command -v gdal_translate >/dev/null 2>&1; then
    echo "ERROR: gdal_translate not found."
    echo
    echo "For the MODIS workflow on ARC, use GDAL from the"
    echo "nwam Conda environment."
    exit 1
fi

if ! command -v gdalinfo >/dev/null 2>&1; then
    echo "ERROR: gdalinfo not found."
    exit 1
fi


# ============================================================
# FIND SOURCE VRT
# ============================================================

mapfile -t vrt_files < <(
    find "$source_path" \
        -maxdepth 1 \
        -type f \
        -name "domain_MCD12Q1_*.vrt" \
        | sort
)

if [ "${#vrt_files[@]}" -eq 0 ]; then
    echo "ERROR: No MODIS multiband VRT found in:"
    echo "$source_path"
    exit 1
fi

if [ "${#vrt_files[@]}" -gt 1 ]; then
    echo "ERROR: More than one MODIS multiband VRT found:"
    for file in "${vrt_files[@]}"; do
        echo "  $file"
    done
    echo
    echo "Expected exactly one multiband VRT."
    exit 1
fi

vrt_file="${vrt_files[0]}"


# ============================================================
# OUTPUT FILE
# ============================================================

base_name=$(basename "$vrt_file" .vrt)

tif_file="${dest_path}/${base_name}.tif"


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "CONVERT MODIS MULTIBAND VRT TO GEOTIFF"
echo "======================================================================"
echo
echo "Domain       : $domain_name"
echo "Control file : $CONTROL_FILE"
echo "Input VRT    : $vrt_file"
echo "Output TIFF  : $tif_file"
echo "GDAL         : $(command -v gdal_translate)"
echo "GDAL version : $(gdal_translate --version | head -1)"
echo


# ============================================================
# REMOVE OLD OUTPUT
# ============================================================

rm -f "$tif_file"


# ============================================================
# CONVERT VRT TO GEOTIFF
# ============================================================

gdal_translate \
    -co COMPRESS=DEFLATE \
    -co TILED=YES \
    -co BIGTIFF=IF_SAFER \
    "$vrt_file" \
    "$tif_file"


# ============================================================
# VERIFY OUTPUT EXISTS
# ============================================================

if [ ! -s "$tif_file" ]; then
    echo "ERROR: GeoTIFF was not created:"
    echo "$tif_file"
    exit 1
fi


# ============================================================
# VERIFY GDAL CAN OPEN OUTPUT
# ============================================================

if ! gdalinfo "$tif_file" >/dev/null 2>&1; then
    echo "ERROR: Created GeoTIFF cannot be opened by GDAL:"
    echo "$tif_file"
    exit 1
fi


# ============================================================
# VERIFY BAND COUNT
# ============================================================

input_band_count=$(
    gdalinfo "$vrt_file" \
    | grep -c '^Band '
)

output_band_count=$(
    gdalinfo "$tif_file" \
    | grep -c '^Band '
)

if [ "$input_band_count" -ne "$output_band_count" ]; then
    echo "ERROR: Band count changed during conversion."
    echo "Input bands : $input_band_count"
    echo "Output bands: $output_band_count"
    exit 1
fi


# ============================================================
# VERIFY RASTER SIZE
# ============================================================

input_size=$(
    gdalinfo "$vrt_file" \
    | grep '^Size is ' \
    | head -1
)

output_size=$(
    gdalinfo "$tif_file" \
    | grep '^Size is ' \
    | head -1
)

if [ "$input_size" != "$output_size" ]; then
    echo "ERROR: Raster dimensions changed during conversion."
    echo "Input : $input_size"
    echo "Output: $output_size"
    exit 1
fi


# ============================================================
# WORKFLOW LOG
# ============================================================

log_path="${dest_path}/_workflow_log"

mkdir -p "$log_path"

timestamp=$(date '+%Y%m%d_%H%M%S')

log_file="${log_path}/${timestamp}_convert_modis_vrt_to_tif.txt"

this_file=$(basename "$0")

{
    echo "Log generated by ${this_file} on $(date '+%F %H:%M:%S')"
    echo "Domain: ${domain_name}"
    echo "Control file: ${CONTROL_FILE}"
    echo "Input VRT: ${vrt_file}"
    echo "Output TIFF: ${tif_file}"
    echo "Bands: ${output_band_count}"
    echo "Raster size: ${output_size}"
    echo "GDAL: $(command -v gdal_translate)"
    echo "GDAL version: $(gdal_translate --version | head -1)"
} > "$log_file"

cp \
    "$0" \
    "$log_path/$this_file"

cp \
    "$CONTROL_FILE" \
    "$log_path/$(basename "$CONTROL_FILE")"


# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "MODIS GEOTIFF CREATION COMPLETED"
echo "======================================================================"
echo "Domain       : $domain_name"
echo "Bands        : $output_band_count"
echo "Raster size  : $output_size"
echo "Output TIFF  : $tif_file"
echo "Workflow log : $log_file"