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
INSTALL_PATH="$(read_control install_path_summa)"
EXPECTED_VERSION="$(read_control summa_version)"
EXPECTED_HASH="$(read_control summa_git_hash)"
EXE_NAME="$(read_control exe_name_summa)"

if [ "$INSTALL_PATH" = "default" ]; then
    INSTALL_PATH="${ROOT_PATH}/installs/summa"
fi


# ============================================================
# CHECK SOURCE
# ============================================================

if [ ! -d "${INSTALL_PATH}/.git" ]; then

    echo "ERROR: SUMMA source not found:"
    echo "$INSTALL_PATH"
    echo
    echo "Run 1a_clone_summa.sh first."

    exit 1
fi


cd "$INSTALL_PATH"

ACTUAL_HASH="$(git rev-parse HEAD)"
ACTUAL_VERSION="$(git describe --tags --always)"


if [ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]; then

    echo "ERROR: Wrong SUMMA source commit."
    echo "Expected: $EXPECTED_HASH"
    echo "Actual  : $ACTUAL_HASH"

    exit 1
fi


# ============================================================
# CHECK CONDA ENVIRONMENT
# ============================================================

if [ -z "${CONDA_PREFIX:-}" ]; then

    echo "ERROR: No active Conda environment detected."
    echo
    echo "Activate the NWAM environment first:"
    echo
    echo "module load conda/base"
    echo "conda activate nwam"

    exit 1
fi


# ============================================================
# FORCE CONDA COMPILERS
# ============================================================

export FC="${CONDA_PREFIX}/bin/gfortran"
export CC="${CONDA_PREFIX}/bin/gcc"

if [ ! -x "$FC" ]; then
    echo "ERROR: Conda Fortran compiler not found:"
    echo "$FC"
    exit 1
fi

if [ ! -x "$CC" ]; then
    echo "ERROR: Conda C compiler not found:"
    echo "$CC"
    exit 1
fi


# ============================================================
# CHECK BUILD TOOLS
# ============================================================

for command in cmake nc-config nf-config; do

    if ! command -v "$command" >/dev/null 2>&1; then

        echo "ERROR: Required command not found:"
        echo "$command"
        echo
        echo "Activate the nwam environment with the"
        echo "required conda-forge build dependencies."

        exit 1
    fi

done


# ============================================================
# HELP CMAKE FIND CONDA LIBRARIES
# ============================================================

export PATH="${CONDA_PREFIX}/bin:${PATH}"

export CMAKE_PREFIX_PATH="${CONDA_PREFIX}:${CMAKE_PREFIX_PATH:-}"

export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"


# ============================================================
# REPORT ENVIRONMENT
# ============================================================

echo
echo "============================================================"
echo "COMPILE SUMMA"
echo "============================================================"

echo "SUMMA version : $ACTUAL_VERSION"
echo "SUMMA commit  : $ACTUAL_HASH"
echo "Install path  : $INSTALL_PATH"

echo
echo "Conda environment:"
echo "$CONDA_PREFIX"

echo
echo "Compiler paths:"
echo "FC = $FC"
echo "CC = $CC"

echo
echo "Fortran compiler:"
"$FC" --version | head -1

echo
echo "C compiler:"
"$CC" --version | head -1

echo
echo "CMake:"
cmake --version | head -1

echo
echo "netCDF-C:"
nc-config --version

echo
echo "netCDF-Fortran:"
nf-config --version


# ============================================================
# BUILD DIRECTORY
# ============================================================

BUILD_DIR="${INSTALL_PATH}/build/cmake_build"


echo
echo "Removing previous CMake build directory:"
echo "$BUILD_DIR"

rm -rf "$BUILD_DIR"


# ============================================================
# CONFIGURE
# ============================================================

echo
echo "============================================================"
echo "CONFIGURE SUMMA"
echo "============================================================"

echo "Standard SUMMA build"
echo "SUNDIALS: disabled"

cmake \
    -S "${INSTALL_PATH}/build" \
    -B "$BUILD_DIR" \
    -DCMAKE_Fortran_COMPILER="$FC" \
    -DCMAKE_C_COMPILER="$CC" \
    -DCMAKE_PREFIX_PATH="$CONDA_PREFIX" \
    -DCMAKE_BUILD_TYPE=Release \
    -DUSE_SUNDIALS=OFF \
    -DSPECIFY_LAPACK_LINKS=OFF


# ============================================================
# VERIFY CMAKE COMPILER SELECTION
# ============================================================

CMAKE_CACHE="${BUILD_DIR}/CMakeCache.txt"

if [ ! -f "$CMAKE_CACHE" ]; then

    echo "ERROR: CMakeCache.txt was not created."

    exit 1
fi


CMAKE_FC="$(
    grep '^CMAKE_Fortran_COMPILER:' "$CMAKE_CACHE" \
    | head -1 \
    | cut -d= -f2-
)"


echo
echo "CMake selected Fortran compiler:"
echo "$CMAKE_FC"


if [ "$CMAKE_FC" != "$FC" ]; then

    echo
    echo "ERROR: CMake selected the wrong Fortran compiler."
    echo
    echo "Expected:"
    echo "$FC"
    echo
    echo "Actual:"
    echo "$CMAKE_FC"

    exit 1
fi


# ============================================================
# COMPILE
# ============================================================

echo
echo "============================================================"
echo "COMPILE"
echo "============================================================"

BUILD_JOBS="${SLURM_CPUS_PER_TASK:-4}"

echo "Parallel build jobs: $BUILD_JOBS"
echo

cmake \
    --build "$BUILD_DIR" \
    --target all \
    -j "$BUILD_JOBS"


# ============================================================
# FIND EXECUTABLE
# ============================================================

EXPECTED_EXE="${INSTALL_PATH}/bin/${EXE_NAME}"


if [ ! -x "$EXPECTED_EXE" ]; then

    echo
    echo "ERROR: Expected SUMMA executable was not created:"
    echo "$EXPECTED_EXE"

    echo
    echo "Executables found under installation:"

    find "$INSTALL_PATH" \
        -maxdepth 5 \
        -type f \
        -perm -111 \
        -name "*summa*" \
        -print

    exit 1
fi


# ============================================================
# VERIFY EXECUTABLE DEPENDENCIES
# ============================================================

echo
echo "============================================================"
echo "SUMMA COMPILED SUCCESSFULLY"
echo "============================================================"

echo
echo "Executable:"
echo "$EXPECTED_EXE"

echo
echo "Executable dependencies:"

ldd "$EXPECTED_EXE" \
    | grep -E \
    "netcdf|gfortran|quadmath|gcc|blas|lapack" \
    || true


# ============================================================
# BASIC EXECUTABLE TEST
# ============================================================

echo
echo "============================================================"
echo "SUMMA EXECUTABLE CHECK"
echo "============================================================"

set +e

"$EXPECTED_EXE" > /tmp/summa_check_${USER}_$$.txt 2>&1

SUMMA_STATUS=$?

set -e


head -30 /tmp/summa_check_${USER}_$$.txt || true

rm -f /tmp/summa_check_${USER}_$$.txt


echo
echo "SUMMA executable return code: $SUMMA_STATUS"

# SUMMA may return non-zero when called without a file manager.
# The important check here is that the executable starts and
# its shared libraries can be loaded.


# ============================================================
# LOG
# ============================================================

LOG_DIR="${INSTALL_PATH}/_workflow_log"

mkdir -p "$LOG_DIR"

LOG_FILE="${LOG_DIR}/$(date '+%Y%m%d')_compile_summa.txt"


{
    echo "SUMMA compilation"
    echo "Date: $(date)"
    echo
    echo "Version: $ACTUAL_VERSION"
    echo "Commit: $ACTUAL_HASH"
    echo
    echo "SUNDIALS: disabled"
    echo
    echo "Conda environment: $CONDA_PREFIX"
    echo
    echo "Fortran compiler: $FC"
    "$FC" --version | head -1
    echo
    echo "C compiler: $CC"
    "$CC" --version | head -1
    echo
    echo "CMake:"
    cmake --version | head -1
    echo
    echo "netCDF-C:"
    nc-config --version
    echo
    echo "netCDF-Fortran:"
    nf-config --version
    echo
    echo "Executable:"
    echo "$EXPECTED_EXE"
    echo
    echo "Executable dependencies:"
    ldd "$EXPECTED_EXE" || true

} > "$LOG_FILE"


cp "${SCRIPT_DIR}/1b_compile_summa.sh" "$LOG_DIR/"


# ============================================================
# FINAL SUMMARY
# ============================================================

echo
echo "============================================================"
echo "SUMMA INSTALLATION COMPLETE"
echo "============================================================"

echo "Version    : $ACTUAL_VERSION"
echo "Commit     : $ACTUAL_HASH"
echo "Compiler   : $FC"
echo "SUNDIALS   : disabled"
echo "Executable : $EXPECTED_EXE"
echo "Log        : $LOG_FILE"
echo "============================================================"