#!/bin/bash

# Convert the cropped MERIT-Hydro domain VRT to GeoTIFF.
#
# Usage:
#
# bash convert_vrt_to_tif.sh /path/to/control_DOMAIN.txt
#
# Example:
#
# bash convert_vrt_to_tif.sh \
# /work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/control_MERIT_717.txt

set -euo pipefail


# ============================================================
# CONTROL FILE
# ============================================================

if [ "$#" -ne 1 ]; then
    echo "Usage:"
    echo "bash convert_vrt_to_tif.sh /path/to/control_DOMAIN.txt"
    exit 1
fi

CONTROL=$(realpath "$1")

if [ ! -f "$CONTROL" ]; then
    echo "ERROR: Control file not found:"
    echo "$CONTROL"
    exit 1
fi


# ============================================================
# CONTROL-FILE FUNCTION
# ============================================================

read_control() {

    local setting="$1"
    local value

    value=$(
        grep -m 1 "^${setting}[[:space:]]*|" "$CONTROL" \
        | cut -d'|' -f2- \
        | cut -d'#' -f1 \
        | xargs
    )

    if [ -z "$value" ]; then
        echo "ERROR: Setting not found or empty: $setting" >&2
        exit 1
    fi

    printf '%s\n' "$value"
}


# ============================================================
# DOMAIN SETTINGS
# ============================================================

root_path=$(read_control "root_path")
domain_name=$(read_control "domain_name")


# ============================================================
# SOURCE VRT PATH
# ============================================================

source_path=$(read_control "parameter_dem_vrt2_path")

if [ "$source_path" = "default" ]; then

    source_path="${root_path}/domain_${domain_name}/parameters/dem/4_domain_vrt"

fi


# ============================================================
# DESTINATION PATH
# ============================================================

dest_path=$(read_control "parameter_dem_tif_path")

if [ "$dest_path" = "default" ]; then

    dest_path="${root_path}/domain_${domain_name}/parameters/dem/5_elevation"

fi

mkdir -p "$dest_path"


# ============================================================
# OUTPUT FILENAME
# ============================================================

dest_name=$(read_control "parameter_dem_tif_name")

if [ -z "$dest_name" ]; then
    echo "ERROR: parameter_dem_tif_name is empty."
    exit 1
fi

tif_file="${dest_path}/${dest_name}"


# ============================================================
# FIND SOURCE VRT
# ============================================================

if [ ! -d "$source_path" ]; then
    echo "ERROR: Source VRT directory not found:"
    echo "$source_path"
    exit 1
fi

mapfile -t vrt_files < <(
    find "$source_path" \
        -maxdepth 1 \
        -type f \
        -name "*.vrt" \
        | sort
)

if [ "${#vrt_files[@]}" -eq 0 ]; then

    echo "ERROR: No VRT file found in:"
    echo "$source_path"
    exit 1

fi

if [ "${#vrt_files[@]}" -gt 1 ]; then

    echo "ERROR: Expected exactly one domain VRT but found:"
    printf '  %s\n' "${vrt_files[@]}"
    exit 1

fi

vrt_file="${vrt_files[0]}"


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "CONVERT MERIT-HYDRO DOMAIN VRT TO GEOTIFF"
echo "======================================================================"
echo
echo "Domain       : $domain_name"
echo "Control file : $CONTROL"
echo "Source VRT   : $vrt_file"
echo "Destination  : $tif_file"
echo


# ============================================================
# REMOVE STALE OUTPUT
# ============================================================

if [ -e "$tif_file" ]; then

    echo "Removing existing output:"
    echo "  $tif_file"

    rm -f "$tif_file"

fi


# ============================================================
# CREATE GEOTIFF
# ============================================================

gdal_translate \
    -of GTiff \
    -co COMPRESS=DEFLATE \
    -co TILED=YES \
    -co BIGTIFF=IF_SAFER \
    "$vrt_file" \
    "$tif_file"


# ============================================================
# VERIFY OUTPUT EXISTS
# ============================================================

if [ ! -s "$tif_file" ]; then

    echo "ERROR: Output GeoTIFF was not created:"
    echo "$tif_file"
    exit 1

fi


# ============================================================
# BASIC GDAL VALIDATION
# ============================================================

if ! gdalinfo "$tif_file" >/dev/null 2>&1; then

    echo "ERROR: gdalinfo could not read:"
    echo "$tif_file"
    exit 1

fi


# ============================================================
# WORKFLOW LOG
# ============================================================

log_path="${dest_path}/_workflow_log"

mkdir -p "$log_path"

timestamp=$(date '+%Y%m%d_%H%M%S')

log_file="${log_path}/${timestamp}_convert_merit_vrt_to_tif.txt"

this_file=$(basename "$0")


cp "$0" \
    "$log_path/$this_file"

cp "$CONTROL" \
    "$log_path/$(basename "$CONTROL")"


{
    echo "Log generated by ${this_file} on $(date '+%F %H:%M:%S')"
    echo "Domain: ${domain_name}"
    echo "Control file: ${CONTROL}"
    echo "Source VRT: ${vrt_file}"
    echo "Output GeoTIFF: ${tif_file}"
    echo "Compression: DEFLATE"
    echo "Tiled: YES"
    echo "BIGTIFF: IF_SAFER"
} > "$log_file"


# ============================================================
# SUMMARY
# ============================================================

echo
echo "======================================================================"
echo "MERIT-HYDRO GEOTIFF CREATION COMPLETED"
echo "======================================================================"
echo "Domain       : $domain_name"
echo "Output TIFF  : $tif_file"
echo "Workflow log : $log_file"