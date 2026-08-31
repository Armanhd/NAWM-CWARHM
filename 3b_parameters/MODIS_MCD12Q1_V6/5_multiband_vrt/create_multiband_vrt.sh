#!/bin/bash
set -euo pipefail

# Create a multiband MODIS MCD12Q1 VRT.
#
# Each cropped annual MODIS VRT becomes one band.
#
# Usage:
#
# bash create_multiband_vrt.sh \
# /path/to/control_DOMAIN.txt
#
# Input:
#   parameters/landclass/4_domain_vrt_epsg_4326/
#
# Output:
#   parameters/landclass/5_multiband_domain_vrt_epsg_4326/

# ============================================================
# INPUT CONTROL FILE
# ============================================================

if [ "$#" -ne 1 ]; then
    echo "Usage:"
    echo "bash create_multiband_vrt.sh /path/to/control_DOMAIN.txt"
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
# SOURCE DIRECTORY
# ============================================================

source_path=$(read_control "parameter_land_vrt3_path")

if [ "$source_path" = "default" ]; then
    source_path="${domain_path}/parameters/landclass/4_domain_vrt_epsg_4326"
fi

if [ ! -d "$source_path" ]; then
    echo "ERROR: Cropped MODIS VRT directory not found:"
    echo "$source_path"
    exit 1
fi


# ============================================================
# DESTINATION DIRECTORY
# ============================================================

dest_path=$(read_control "parameter_land_vrt4_path")

if [ "$dest_path" = "default" ]; then
    dest_path="${domain_path}/parameters/landclass/5_multiband_domain_vrt_epsg_4326"
fi

mkdir -p "$dest_path"


# ============================================================
# GDAL CHECK
# ============================================================

if ! command -v gdalbuildvrt >/dev/null 2>&1; then
    echo "ERROR: gdalbuildvrt not found."
    echo
    echo "For the MODIS workflow on ARC, use GDAL from the nwam"
    echo "Conda environment."
    exit 1
fi

if ! command -v gdalinfo >/dev/null 2>&1; then
    echo "ERROR: gdalinfo not found."
    exit 1
fi


# ============================================================
# FIND CROPPED MODIS VRT FILES
# ============================================================

mapfile -t vrt_files < <(
    find "$source_path" \
        -maxdepth 1 \
        -type f \
        -name "domain_MCD12Q1_*.vrt" \
        | sort
)

if [ "${#vrt_files[@]}" -eq 0 ]; then
    echo "ERROR: No cropped MODIS VRT files found in:"
    echo "$source_path"
    exit 1
fi


# ============================================================
# DETERMINE OUTPUT NAME
# ============================================================

# For the current NWAM workflow only 2022 is used, therefore
# this normally produces:
#
# domain_MCD12Q1_2022.vrt
#
# If multiple years are added later, use a year-range name.

years=()

for vrt_file in "${vrt_files[@]}"; do

    filename=$(basename "$vrt_file")

    year=$(
        echo "$filename" \
        | sed -n 's/^domain_MCD12Q1_\([0-9][0-9][0-9][0-9]\)\.vrt$/\1/p'
    )

    if [ -z "$year" ]; then
        echo "ERROR: Could not determine MODIS year from:"
        echo "$filename"
        exit 1
    fi

    years+=("$year")

done

first_year="${years[0]}"
last_year="${years[$((${#years[@]} - 1))]}"

if [ "${#years[@]}" -eq 1 ]; then
    output_name="domain_MCD12Q1_${first_year}.vrt"
else
    output_name="domain_MCD12Q1_${first_year}-${last_year}.vrt"
fi

output_file="${dest_path}/${output_name}"


# ============================================================
# CREATE INPUT FILE LIST
# ============================================================

filelist="${dest_path}/MCD12Q1_multiband_filelist.txt"

printf "%s\n" "${vrt_files[@]}" > "$filelist"


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "CREATE MODIS MCD12Q1 MULTIBAND VRT"
echo "======================================================================"
echo
echo "Domain       : $domain_name"
echo "Control file : $CONTROL_FILE"
echo "Source       : $source_path"
echo "Destination  : $dest_path"
echo "Input VRTs   : ${#vrt_files[@]}"
echo "MODIS years  : ${years[*]}"
echo "Output VRT   : $output_file"
echo "GDAL         : $(command -v gdalbuildvrt)"
echo "GDAL version : $(gdalbuildvrt --version | head -1)"
echo

echo "Input files:"
for vrt_file in "${vrt_files[@]}"; do
    echo "  $vrt_file"
done

echo


# ============================================================
# REMOVE OLD OUTPUT
# ============================================================

rm -f "$output_file"


# ============================================================
# BUILD MULTIBAND VRT
# ============================================================

gdalbuildvrt \
    -separate \
    -input_file_list "$filelist" \
    -resolution highest \
    "$output_file"


# ============================================================
# VERIFY OUTPUT
# ============================================================

if [ ! -s "$output_file" ]; then
    echo "ERROR: Multiband VRT was not created:"
    echo "$output_file"
    exit 1
fi

if ! gdalinfo "$output_file" >/dev/null 2>&1; then
    echo "ERROR: Created VRT cannot be opened by GDAL:"
    echo "$output_file"
    exit 1
fi


# ============================================================
# VERIFY BAND COUNT
# ============================================================

band_count=$(
    gdalinfo "$output_file" \
    | grep -c '^Band '
)

expected_bands="${#vrt_files[@]}"

if [ "$band_count" -ne "$expected_bands" ]; then
    echo "ERROR: Unexpected number of bands."
    echo "Expected: $expected_bands"
    echo "Found   : $band_count"
    exit 1
fi


# ============================================================
# WORKFLOW LOG
# ============================================================

log_path="${dest_path}/_workflow_log"

mkdir -p "$log_path"

timestamp=$(date '+%Y%m%d_%H%M%S')

log_file="${log_path}/${timestamp}_create_modis_multiband_vrt.txt"

this_file=$(basename "$0")

{
    echo "Log generated by ${this_file} on $(date '+%F %H:%M:%S')"
    echo "Domain: ${domain_name}"
    echo "Control file: ${CONTROL_FILE}"
    echo "Source directory: ${source_path}"
    echo "Output directory: ${dest_path}"
    echo "Input VRT files: ${#vrt_files[@]}"
    echo "MODIS years: ${years[*]}"
    echo "Output VRT: ${output_file}"
    echo "Bands created: ${band_count}"
    echo "GDAL: $(command -v gdalbuildvrt)"
    echo "GDAL version: $(gdalbuildvrt --version | head -1)"
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
echo "MODIS MULTIBAND VRT CREATION COMPLETED"
echo "======================================================================"
echo "Domain       : $domain_name"
echo "Input VRTs   : ${#vrt_files[@]}"
echo "Bands        : $band_count"
echo "MODIS years  : ${years[*]}"
echo "Output VRT   : $output_file"
echo "Workflow log : $log_file"