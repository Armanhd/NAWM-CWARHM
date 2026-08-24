#!/bin/bash

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CWARHM="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONTROL="${CWARHM}/0_control_files/control_active.txt"


# ============================================================
# CONTROL READER
# ============================================================

read_control() {

    local key="$1"

    awk -F'|' -v key="$key" '
        /^[[:space:]]*#/ {next}
        NF >= 2 {
            left=$1
            gsub(/^[ \t]+|[ \t]+$/, "", left)

            if (left == key) {
                right=$2
                sub(/#.*/, "", right)
                gsub(/^[ \t]+|[ \t]+$/, "", right)
                print right
                exit
            }
        }
    ' "$CONTROL"
}


# ============================================================
# SETTINGS
# ============================================================

ROOT_PATH="$(read_control root_path)"
GITHUB_URL="$(read_control github_mizuroute)"
INSTALL_PATH="$(read_control install_path_mizuroute)"
VERSION="$(read_control mizuroute_version)"
EXPECTED_HASH="$(read_control mizuroute_git_hash)"

if [ "$INSTALL_PATH" = "default" ]; then
    INSTALL_PATH="${ROOT_PATH}/installs/mizuRoute"
fi


# ============================================================
# CHECK EXISTING INSTALLATION
# ============================================================

if [ -e "$INSTALL_PATH" ]; then

    echo "ERROR: mizuRoute installation path already exists:"
    echo "$INSTALL_PATH"
    echo
    echo "Remove or rename it before cloning."

    exit 1
fi


# ============================================================
# CLONE
# ============================================================

echo
echo "============================================================"
echo "CLONE MIZUROUTE"
echo "============================================================"
echo "Repository : $GITHUB_URL"
echo "Version    : $VERSION"
echo "Expected   : $EXPECTED_HASH"
echo "Install    : $INSTALL_PATH"
echo


git clone \
    --branch "$VERSION" \
    --single-branch \
    "$GITHUB_URL" \
    "$INSTALL_PATH"


cd "$INSTALL_PATH"


# ============================================================
# VERIFY VERSION
# ============================================================

ACTUAL_HASH="$(git rev-parse HEAD)"
ACTUAL_VERSION="$(git describe --tags --always)"


echo
echo "Checked out version : $ACTUAL_VERSION"
echo "Checked out commit  : $ACTUAL_HASH"


if [ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]; then

    echo
    echo "ERROR: mizuRoute commit does not match expected commit."
    echo "Expected: $EXPECTED_HASH"
    echo "Actual  : $ACTUAL_HASH"

    exit 1
fi


# ============================================================
# LOGGING
# ============================================================

LOG_DIR="${INSTALL_PATH}/_workflow_log"

mkdir -p "$LOG_DIR"

LOG_FILE="${LOG_DIR}/$(date '+%Y%m%d')_clone_mizuroute.txt"


{
    echo "mizuRoute clone"
    echo "Date: $(date)"
    echo "Repository: $GITHUB_URL"
    echo "Version: $ACTUAL_VERSION"
    echo "Commit: $ACTUAL_HASH"
    echo "Install: $INSTALL_PATH"
} > "$LOG_FILE"


cp "${SCRIPT_DIR}/2a_clone_mizuroute.sh" "$LOG_DIR/"


# ============================================================
# SUMMARY
# ============================================================

echo
echo "============================================================"
echo "MIZUROUTE SOURCE INSTALLED"
echo "============================================================"
echo "Version : $ACTUAL_VERSION"
echo "Commit  : $ACTUAL_HASH"
echo "Path    : $INSTALL_PATH"
echo "============================================================"