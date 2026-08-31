#!/bin/bash

# Crop the MERIT-Hydro DEM VRT to one CWARHM domain.
#
# Usage:
#
# bash specify_subdomain.sh /path/to/control_DOMAIN.txt
#
# Example:
#
# bash specify_subdomain.sh \
# /work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/0_control_files/control_MERIT_717.txt

set -euo pipefail


# ============================================================
# CONTROL FILE
# ============================================================

if [ "$#" -ne 1 ]; then
    echo "Usage:"
    echo "bash specify_subdomain.sh /path/to/control_DOMAIN.txt"
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
        awk -F'|' -v key="$setting" '
        /^[[:space:]]*#/ { next }
        {
            left=$1
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", left)

            if (left == key) {
                right=$2
                sub(/#.*/, "", right)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", right)
                print right
                exit
            }
        }
        ' "$CONTROL"
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

source_path=$(read_control "parameter_dem_vrt1_path")

if [ "$source_path" = "default" ]; then
    source_path="${root_path}/domain_${domain_name}/parameters/dem/3_vrt"
fi


# ============================================================
# DESTINATION PATH
# ============================================================

dest_path=$(read_control "parameter_dem_vrt2_path")

if [ "$dest_path" = "default" ]; then
    dest_path="${root_path}/domain_${domain_name}/parameters/dem/4_domain_vrt"
fi

mkdir -p "$dest_path"


# ============================================================
# DOMAIN EXTENT
# ============================================================

domain_full=$(read_control "forcing_raw_space")

IFS='/' read -r LAT_MAX LON_MIN LAT_MIN LON_MAX <<< "$domain_full"

if (
    [ -z "$LAT_MAX" ] ||
    [ -z "$LON_MIN" ] ||
    [ -z "$LAT_MIN" ] ||
    [ -z "$LON_MAX" ]
); then
    echo "ERROR: forcing_raw_space must have format:"
    echo "LAT_MAX/LON_MIN/LAT_MIN/LON_MAX"
    exit 1
fi


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
    echo "ERROR: No VRT files found in:"
    echo "$source_path"
    exit 1
fi

if [ "${#vrt_files[@]}" -gt 1 ]; then
    echo "ERROR: Expected exactly one source VRT but found:"
    printf '  %s\n' "${vrt_files[@]}"
    exit 1
fi

source_file="${vrt_files[0]}"

filename=$(basename "$source_file")

dest_file="${dest_path}/domain_${filename}"


# ============================================================
# REPORT
# ============================================================

echo
echo "======================================================================"
echo "CROP MERIT-HYDRO DEM TO DOMAIN"
echo "======================================================================"
echo
echo "Domain       : $domain_name"
echo "Control file : $CONTROL"
echo "Source VRT   : $source_file"
echo "Destination  : $dest_file"
echo
echo "Domain extent:"
echo "  latitude : $LAT_MIN to $LAT_MAX"
echo "  longitude: $LON_MIN to $LON_MAX"
echo


# ============================================================
# REMOVE STALE OUTPUT
# ============================================================

rm -f "$dest_file"


# ============================================================
# CROP DOMAIN
# ============================================================

gdal_translate \
    -of VRT \
    -projwin \
    "$LON_MIN" \
    "$LAT_MAX" \
    "$LON_MAX" \
    "$LAT_MIN" \
    "$source_file" \
    "$dest_file"


# ============================================================
# VERIFY OUTPUT
# ============================================================

if [ ! -s "$dest_file" ]; then
    echo "ERROR: Cropped domain VRT was not created:"
    echo "$dest_file"
    exit 1
fi


# ============================================================
# WORKFLOW LOG
# ============================================================

log_path="${dest_path}/_workflow_log"

mkdir -p "$log_path"

timestamp=$(date '+%Y%m%d_%H%M%S')

log_file="${log_path}/${timestamp}_specify_subdomain.txt"

this_file=$(basename "$0")

cp "$0" \
    "$log_path/$this_file"

cp "$CONTROL" \
    "$log_path/$(basename "$CONTROL")"


{
    echo "Log generated by ${this_file} on $(date '+%F %H:%M:%S')"
    echo "Domain: ${domain_name}"
    echo "Control file: ${CONTROL}"
    echo "Source VRT: ${source_file}"
    echo "Output VRT: ${dest_file}"
    echo "Latitude bounds: ${LAT_MIN} to ${LAT_MAX}"
    echo "Longitude bounds: ${LON_MIN} to ${LON_MAX}"
} > "$log_file"


# ============================================================
# SUMMARY
# ============================================================

echo
echo "======================================================================"
echo "MERIT-HYDRO DOMAIN CROPPING COMPLETED"
echo "======================================================================"
echo "Domain       : $domain_name"
echo "Output VRT   : $dest_file"
echo "Workflow log : $log_file"