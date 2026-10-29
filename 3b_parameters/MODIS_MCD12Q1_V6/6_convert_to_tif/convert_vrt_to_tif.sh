#!/bin/bash
set -euo pipefail

# Convert the selected MODIS MCD12Q1 domain VRT to GeoTIFF.
# Supports parameter_land_years | YYYY or YYYY-YYYY.
#
# Usage:
#   bash convert_vrt_to_tif.sh /path/to/control_DOMAIN.txt
#
# Input:
#   parameters/landclass/5_multiband_domain_vrt_epsg_4326/
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
# SELECT SOURCE VRT USING CONTROL-FILE YEARS
# ============================================================

LAND_YEARS=$(read_control "parameter_land_years")

if [[ "$LAND_YEARS" =~ ^[0-9]{4}$ ]]; then
    first_year="$LAND_YEARS"
    last_year="$LAND_YEARS"
    expected_bands=1
    vrt_name="domain_MCD12Q1_${first_year}.vrt"

elif [[ "$LAND_YEARS" =~ ^([0-9]{4})-([0-9]{4})$ ]]; then
    first_year="${BASH_REMATCH[1]}"
    last_year="${BASH_REMATCH[2]}"

    if (( 10#$first_year > 10#$last_year )); then
        echo "ERROR: Invalid MODIS year range: $LAND_YEARS" >&2
        exit 1
    fi

    expected_bands=$((10#$last_year - 10#$first_year + 1))

    if [ "$expected_bands" -eq 1 ]; then
        vrt_name="domain_MCD12Q1_${first_year}.vrt"
    else
        vrt_name="domain_MCD12Q1_${first_year}-${last_year}.vrt"
    fi

else
    echo "ERROR: Invalid parameter_land_years: $LAND_YEARS" >&2
    echo "Expected YYYY or YYYY-YYYY" >&2
    exit 1
fi

vrt_file="${source_path}/${vrt_name}"

if [ ! -s "$vrt_file" ]; then
    echo "ERROR: Required MODIS VRT not found:"
    echo "$vrt_file"
    exit 1
fi

# ============================================================
# OUTPUT FILE
# ============================================================

base_name=$(basename "$vrt_file" .vrt)
tif_file="${dest_path}/${base_name}.tif"

# ============================================================
# VERIFY SOURCE BAND COUNT BEFORE CONVERSION
# ============================================================

if ! gdalinfo "$vrt_file" >/dev/null 2>&1; then
    echo "ERROR: GDAL cannot open input VRT:"
    echo "$vrt_file"
    exit 1
fi

input_band_count=$(
    gdalinfo "$vrt_file" | grep -c '^Band '
)

if [ "$input_band_count" -ne "$expected_bands" ]; then
    echo "ERROR: Input VRT band count does not match selected years."
    echo "Selected years : $LAND_YEARS"
    echo "Expected bands : $expected_bands"
    echo "Actual bands   : $input_band_count"
    exit 1
fi

# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "CONVERT MODIS MULTIBAND VRT TO GEOTIFF"
echo "======================================================================"
echo
echo "Domain         : $domain_name"
echo "Control file   : $CONTROL_FILE"
echo "Selected years : $LAND_YEARS"
echo "Expected bands : $expected_bands"
echo "Input VRT      : $vrt_file"
echo "Output TIFF    : $tif_file"
echo "GDAL           : $(command -v gdal_translate)"
echo "GDAL version   : $(gdal_translate --version | head -1)"
echo

# ============================================================
# CONVERT VRT TO GEOTIFF
# ============================================================

# Write a temporary file so a failed conversion does not destroy
# a previously successful TIFF. Move it into place after validation.
tmp_tif="${dest_path}/.${base_name}.$$.tmp.tif"
trap 'rm -f "$tmp_tif"' EXIT

gdal_translate \
    -co COMPRESS=DEFLATE \
    -co TILED=YES \
    -co BIGTIFF=IF_SAFER \
    "$vrt_file" \
    "$tmp_tif"

# ============================================================
# VERIFY OUTPUT EXISTS AND GDAL CAN OPEN IT
# ============================================================

if [ ! -s "$tmp_tif" ]; then
    echo "ERROR: GeoTIFF was not created:"
    echo "$tmp_tif"
    exit 1
fi

if ! gdalinfo "$tmp_tif" >/dev/null 2>&1; then
    echo "ERROR: Created GeoTIFF cannot be opened by GDAL:"
    echo "$tmp_tif"
    exit 1
fi

# ============================================================
# VERIFY BAND COUNT
# ============================================================

output_band_count=$(
    gdalinfo "$tmp_tif" | grep -c '^Band '
)

if [ "$input_band_count" -ne "$output_band_count" ]; then
    echo "ERROR: Band count changed during conversion."
    echo "Input bands : $input_band_count"
    echo "Output bands: $output_band_count"
    exit 1
fi

if [ "$output_band_count" -ne "$expected_bands" ]; then
    echo "ERROR: MODIS band count does not match selected years."
    echo "Selected years : $LAND_YEARS"
    echo "Expected bands : $expected_bands"
    echo "Actual bands   : $output_band_count"
    exit 1
fi

# ============================================================
# VERIFY RASTER SIZE
# ============================================================

input_size=$(
    gdalinfo "$vrt_file" | grep '^Size is ' | head -1
)

output_size=$(
    gdalinfo "$tmp_tif" | grep '^Size is ' | head -1
)

if [ "$input_size" != "$output_size" ]; then
    echo "ERROR: Raster dimensions changed during conversion."
    echo "Input : $input_size"
    echo "Output: $output_size"
    exit 1
fi

# ============================================================
# FINALIZE OUTPUT AND REMOVE OBSOLETE MODIS TIFFS
# ============================================================

mv -f "$tmp_tif" "$tif_file"

# Step 7 expects exactly one domain_MCD12Q1_*.tif input.
# Only matching obsolete intermediate TIFFs in this directory are removed.
find "$dest_path" \
    -maxdepth 1 \
    -type f \
    -name 'domain_MCD12Q1_*.tif' \
    ! -name "$(basename "$tif_file")" \
    -print \
    -delete

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
    echo "Selected years: ${LAND_YEARS}"
    echo "Expected bands: ${expected_bands}"
    echo "Input VRT: ${vrt_file}"
    echo "Output TIFF: ${tif_file}"
    echo "Bands: ${output_band_count}"
    echo "Raster size: ${output_size}"
    echo "GDAL: $(command -v gdal_translate)"
    echo "GDAL version: $(gdal_translate --version | head -1)"
} > "$log_file"

cp "$0" "$log_path/$this_file"
cp "$CONTROL_FILE" "$log_path/$(basename "$CONTROL_FILE")"

# ============================================================
# FINISH
# ============================================================

echo
echo "======================================================================"
echo "MODIS GEOTIFF CREATION COMPLETED"
echo "======================================================================"
echo "Domain         : $domain_name"
echo "Selected years : $LAND_YEARS"
echo "Bands          : $output_band_count"
echo "Raster size    : $output_size"
echo "Output TIFF    : $tif_file"
echo "Workflow log   : $log_file"
