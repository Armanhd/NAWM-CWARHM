#!/bin/bash
set -euo pipefail

# Create one MODIS MCD12Q1 VRT for each configured year.
#
# Usage:
#
# bash make_vrt_per_year.sh \
# /path/to/control_DOMAIN.txt
#
# IMPORTANT
# ---------
# This multibasin version does NOT use control_active.txt.
# The domain-specific control file must be passed explicitly.
#
# MODIS MCD12Q1 is stored as HDF4. Therefore this script must
# be run with a GDAL installation that supports HDF4.
#
# On ARC, the NWAM Conda environment provides the required
# GDAL/HDF4 support. Do not load the ARC lib/gdal module for
# this step if it overrides the Conda GDAL installation.


# ============================================================
# INPUT CONTROL FILE
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "Usage:"
    echo
    echo "bash make_vrt_per_year.sh /path/to/control_DOMAIN.txt"
    echo
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
# SOURCE MODIS DATA
# ============================================================

source_path=$(read_control "parameter_land_raw_path")


if [ "$source_path" = "default" ]; then

    source_path="${domain_path}/parameters/landclass/1_MODIS_raw_data"

fi


if [ ! -d "$source_path" ]; then

    echo "ERROR: MODIS raw-data directory not found:"
    echo "$source_path"

    exit 1

fi


# ============================================================
# OUTPUT VRT DIRECTORY
# ============================================================

dest_path=$(read_control "parameter_land_vrt1_path")


if [ "$dest_path" = "default" ]; then

    dest_path="${domain_path}/parameters/landclass/2_vrt_native_crs"

fi


mkdir -p "${dest_path}/filelists"


# ============================================================
# CHECK GDAL
# ============================================================

if ! command -v gdalinfo >/dev/null 2>&1; then

    echo "ERROR: gdalinfo not found."
    echo
    echo "Activate the NWAM Conda environment before running this script:"
    echo
    echo "    conda activate nwam"
    echo

    exit 1

fi


if ! command -v gdalbuildvrt >/dev/null 2>&1; then

    echo "ERROR: gdalbuildvrt not found."
    echo
    echo "Activate the NWAM Conda environment before running this script:"
    echo
    echo "    conda activate nwam"
    echo

    exit 1

fi


# ============================================================
# CHECK HDF4 SUPPORT
# ============================================================

# Capture the complete format list first.
# Do not pipe gdalinfo directly into grep -q while pipefail is active,
# because grep -q can terminate early and cause gdalinfo to receive
# SIGPIPE, making the pipeline appear to fail.

GDAL_FORMATS=$(gdalinfo --formats 2>/dev/null)

if ! grep -q "HDF4" <<< "$GDAL_FORMATS"; then

    echo
    echo "ERROR: The active GDAL installation does not support HDF4."
    echo
    echo "Current gdalinfo:"
    command -v gdalinfo || true
    echo
    echo "GDAL version:"
    gdalinfo --version || true
    echo
    echo "MODIS MCD12Q1 requires HDF4 support."
    echo

    exit 1

fi


# ============================================================
# MODIS YEARS
# ============================================================

# Current NWAM workflow uses the 2022 MCD12Q1 land-cover map.
#
# Keep this as an explicit data/model assumption for now.
#
# If additional years are needed later, add them here, for example:
#
# MODIS_YEARS=(2020 2021 2022)

MODIS_YEARS=(2022)


# ============================================================
# REPORT
# ============================================================

echo

echo "======================================================================"
echo "CREATE MODIS MCD12Q1 YEARLY VRT"
echo "======================================================================"

echo

echo "Domain       : $domain_name"
echo "Control file : $CONTROL_FILE"

echo "Source       : $source_path"

echo "Destination  : $dest_path"

echo "MODIS years  : ${MODIS_YEARS[*]}"

echo "GDAL         : $(command -v gdalinfo)"

echo "GDAL version : $(gdalinfo --version)"

echo

echo "HDF4 support : available"

echo


# ============================================================
# CREATE YEARLY VRT FILES
# ============================================================

created_count=0


for YEAR in "${MODIS_YEARS[@]}"; do

    OUTTXT="${dest_path}/filelists/MCD12Q1_filelist_${YEAR}.txt"

    OUTVRT="${dest_path}/MCD12Q1_${YEAR}.vrt"


    # --------------------------------------------------------
    # FIND HDF FILES
    # --------------------------------------------------------

    find "$source_path" \
        -maxdepth 1 \
        -type f \
        -name "MCD12Q1.A${YEAR}*.hdf" \
        | sort \
        > "$OUTTXT"


    FILE_COUNT=$(wc -l < "$OUTTXT")

    FILE_COUNT=$(echo "$FILE_COUNT" | xargs)


    if [ "$FILE_COUNT" -eq 0 ]; then

        echo "ERROR: No MODIS HDF files found for ${YEAR}:"

        echo "$source_path"

        exit 1

    fi


    echo "----------------------------------------------------------------------"

    echo "Year ${YEAR}"

    echo "----------------------------------------------------------------------"

    echo "HDF files : $FILE_COUNT"

    echo "File list : $OUTTXT"

    echo "Output VRT: $OUTVRT"

    echo


    # --------------------------------------------------------
    # REMOVE OLD OUTPUT
    # --------------------------------------------------------

    if [ -e "$OUTVRT" ]; then

        echo "Removing existing VRT:"

        echo "$OUTVRT"

        rm -f "$OUTVRT"

        echo

    fi


    # --------------------------------------------------------
    # BUILD VRT
    #
    # MCD12Q1 LC_Type1 is subdataset 1 in the current files.
    # --------------------------------------------------------

    gdalbuildvrt \
        "$OUTVRT" \
        -input_file_list "$OUTTXT" \
        -sd 1 \
        -resolution highest


    # --------------------------------------------------------
    # VERIFY OUTPUT
    # --------------------------------------------------------

    if [ ! -s "$OUTVRT" ]; then

        echo "ERROR: VRT was not created:"

        echo "$OUTVRT"

        exit 1

    fi


    if ! gdalinfo "$OUTVRT" >/dev/null 2>&1; then

        echo "ERROR: GDAL cannot read the generated VRT:"

        echo "$OUTVRT"

        exit 1

    fi


    created_count=$((created_count + 1))


    echo

    echo "Created successfully:"

    echo "$OUTVRT"

    echo

done


# ============================================================
# WORKFLOW LOG
# ============================================================

log_path="${dest_path}/_workflow_log"

mkdir -p "$log_path"


timestamp=$(date '+%Y%m%d_%H%M%S')


log_file="${log_path}/${timestamp}_create_modis_yearly_vrt.txt"


this_file=$(basename "$0")


{
    echo "Log generated by ${this_file} on $(date '+%F %H:%M:%S')"

    echo "Domain: ${domain_name}"

    echo "Control file: ${CONTROL_FILE}"

    echo "Source MODIS directory: ${source_path}"

    echo "Output VRT directory: ${dest_path}"

    echo "MODIS years: ${MODIS_YEARS[*]}"

    echo "GDAL executable: $(command -v gdalinfo)"

    echo "GDAL version: $(gdalinfo --version)"

    echo "HDF4 support: yes"

    echo "VRT files created: ${created_count}"

} > "$log_file"


cp "$0" "$log_path/$this_file"


# ============================================================
# FINISH
# ============================================================

echo "======================================================================"
echo "MODIS YEARLY VRT CREATION COMPLETED"
echo "======================================================================"

echo "Domain       : $domain_name"

echo "VRTs created : $created_count"

echo "Output folder: $dest_path"

echo "Workflow log : $log_file"

echo