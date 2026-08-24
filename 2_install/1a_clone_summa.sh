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
GITHUB_URL="$(read_control github_summa)"
VERSION="$(read_control summa_version)"
EXPECTED_HASH="$(read_control summa_git_hash)"
INSTALL_PATH="$(read_control install_path_summa)"

if [ "$INSTALL_PATH" = "default" ]; then
    INSTALL_PATH="${ROOT_PATH}/installs/summa"
fi


# ============================================================
# REPORT
# ============================================================

echo
echo "============================================================"
echo "CLONE SUMMA"
echo "============================================================"
echo "Repository : $GITHUB_URL"
echo "Version    : $VERSION"
echo "Expected   : $EXPECTED_HASH"
echo "Install    : $INSTALL_PATH"
echo


# ============================================================
# CLONE / VERIFY
# ============================================================

if [ -d "${INSTALL_PATH}/.git" ]; then

    echo "SUMMA repository already exists."
    echo "Checking existing installation..."

    cd "$INSTALL_PATH"

    git fetch --tags origin

    git checkout --detach "$VERSION"

else

    mkdir -p "$(dirname "$INSTALL_PATH")"

    git clone \
        --branch "$VERSION" \
        --single-branch \
        "$GITHUB_URL" \
        "$INSTALL_PATH"

    cd "$INSTALL_PATH"

fi


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
    echo "ERROR: SUMMA commit does not match expected commit."
    echo "Expected: $EXPECTED_HASH"
    echo "Actual  : $ACTUAL_HASH"

    exit 1
fi


# ============================================================
# LOG
# ============================================================

LOG_DIR="${INSTALL_PATH}/_workflow_log"

mkdir -p "$LOG_DIR"

LOG_FILE="${LOG_DIR}/$(date '+%Y%m%d')_clone_summa.txt"

{
    echo "SUMMA clone/checkout"
    echo "Date: $(date)"
    echo "Repository: $GITHUB_URL"
    echo "Version: $ACTUAL_VERSION"
    echo "Commit: $ACTUAL_HASH"
} > "$LOG_FILE"

cp "$0" "$LOG_DIR/"


echo
echo "============================================================"
echo "SUMMA SOURCE READY"
echo "============================================================"
echo "Version : $ACTUAL_VERSION"
echo "Commit  : $ACTUAL_HASH"
echo "Location: $INSTALL_PATH"