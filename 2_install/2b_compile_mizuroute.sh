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
INSTALL_PATH="$(read_control install_path_mizuroute)"
EXPECTED_VERSION="$(read_control mizuroute_version)"
EXPECTED_HASH="$(read_control mizuroute_git_hash)"
EXE_NAME="$(read_control exe_name_mizuroute)"


if [ "$INSTALL_PATH" = "default" ]; then
    INSTALL_PATH="${ROOT_PATH}/installs/mizuRoute"
fi


F_MASTER="${INSTALL_PATH}/route/"


# ============================================================
# CHECK SOURCE
# ============================================================

if [ ! -d "${INSTALL_PATH}/.git" ]; then

    echo "ERROR: mizuRoute source not found:"
    echo "$INSTALL_PATH"
    echo
    echo "Run 2a_clone_mizuroute.sh first."

    exit 1
fi


if [ ! -f "${F_MASTER}/build/Makefile" ]; then

    echo "ERROR: mizuRoute Makefile not found:"
    echo "${F_MASTER}/build/Makefile"

    exit 1
fi


cd "$INSTALL_PATH"

ACTUAL_HASH="$(git rev-parse HEAD)"
ACTUAL_VERSION="$(git describe --tags --always)"


if [ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]; then

    echo "ERROR: Wrong mizuRoute source commit."
    echo "Expected: $EXPECTED_HASH"
    echo "Actual  : $ACTUAL_HASH"

    exit 1
fi


# ============================================================
# CHECK PARALLELIO EXTERNAL
# ============================================================

echo
echo "Checking ParallelIO external..."

PARALLELIO="${INSTALL_PATH}/libraries/parallelio"

if [ ! -f "${PARALLELIO}/CMakeLists.txt" ]; then

    echo "ERROR: ParallelIO external not found:"
    echo "$PARALLELIO"
    echo
    echo "Run:"
    echo "  cd ${INSTALL_PATH}"
    echo "  mkdir -p libraries/parallelio"
    echo "  ./bin/git-fleximod update"

    exit 1
fi

PIO_VERSION="$(
    git -C "$PARALLELIO" describe --tags --always
)"

PIO_HASH="$(
    git -C "$PARALLELIO" rev-parse HEAD
)"

echo "ParallelIO version: $PIO_VERSION"
echo "ParallelIO commit : $PIO_HASH"


# ============================================================
# CHECK CONDA ENVIRONMENT
# ============================================================

if [ -z "${CONDA_PREFIX:-}" ]; then

    echo "ERROR: No active Conda environment detected."
    echo
    echo "Run:"
    echo "module load conda/base"
    echo "conda activate nwam"

    exit 1
fi


# ============================================================
# FORCE CONDA / MPI TOOLCHAIN
# ============================================================

export PATH="${CONDA_PREFIX}/bin:${PATH}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"

MPIF90="${CONDA_PREFIX}/bin/mpif90"
MPIFORT="${CONDA_PREFIX}/bin/mpifort"
MPICC="${CONDA_PREFIX}/bin/mpicc"


# ============================================================
# CHECK REQUIRED TOOLS
# ============================================================

for command in \
    make \
    cmake \
    gcc \
    gfortran \
    mpicc \
    mpif90 \
    mpifort \
    nc-config \
    nf-config
do

    if ! command -v "$command" >/dev/null 2>&1; then

        echo "ERROR: Required command not found:"
        echo "$command"
        echo
        echo "Update/activate the nwam Conda environment first."

        exit 1
    fi

done


if [ ! -x "$MPIF90" ]; then

    echo "ERROR: Conda MPI Fortran compiler not found:"
    echo "$MPIF90"

    exit 1
fi


# Help PIO's CMake build use the same Conda MPI installation.
export CC="${CONDA_PREFIX}/bin/mpicc"

if [ -x "${CONDA_PREFIX}/bin/mpicxx" ]; then
    export CXX="${CONDA_PREFIX}/bin/mpicxx"
fi


# ============================================================
# BUILD SETTINGS
# ============================================================

# Compiler family expected by mizuRoute Makefile.
FC="gnu"

# Actual compiler must be MPI-enabled because mizuRoute
# v3.1.1 directly uses MPI modules.
FC_EXE="$MPIF90"

MODE="fast"

# Stand-alone NWAM configuration.
IS_OPENMP="no"

# Required for mizuRoute v3.1.1 source structure.
IS_PIO="yes"

# Timing library is not required.
IS_GPTL="yes"

NCDF_PATH="${CONDA_PREFIX}"

EXPECTED_EXE="${F_MASTER}bin/${EXE_NAME}"


# ============================================================
# REPORT ENVIRONMENT
# ============================================================

echo
echo "============================================================"
echo "COMPILE MIZUROUTE"
echo "============================================================"

echo "mizuRoute version : $ACTUAL_VERSION"
echo "mizuRoute commit  : $ACTUAL_HASH"
echo "Install path      : $INSTALL_PATH"
echo "Build root        : $F_MASTER"

echo
echo "Conda environment:"
echo "$CONDA_PREFIX"

echo
echo "MPI Fortran compiler:"
echo "$FC_EXE"
"$FC_EXE" --version | head -1

echo
echo "MPI C compiler:"
echo "$MPICC"
"$MPICC" --version | head -1

echo
echo "GNU Fortran:"
gfortran --version | head -1

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
echo "Build settings:"
echo "MODE       = $MODE"
echo "OpenMP     = $IS_OPENMP"
echo "PIO        = $IS_PIO"
echo "GPTL       = $IS_GPTL"
echo "Executable = $EXE_NAME"


# ============================================================
# REMOVE PREVIOUS EXECUTABLE
# ============================================================

if [ -e "$EXPECTED_EXE" ]; then

    echo
    echo "Removing previous executable:"
    echo "$EXPECTED_EXE"

    rm -f "$EXPECTED_EXE"
fi


# ============================================================
# CLEAN PREVIOUS FAILED BUILD
# ============================================================

echo
echo "Cleaning previous mizuRoute build products..."

make \
    -C "$F_MASTER" \
    -f build/Makefile \
    F_MASTER="$F_MASTER" \
    clean \
    >/dev/null 2>&1 || true


echo "Cleaning previous ParallelIO build products..."

make \
    -C "$F_MASTER" \
    -f build/Makefile \
    F_MASTER="$F_MASTER" \
    cleanlibs \
    >/dev/null 2>&1 || true


# ============================================================
# COMPILE
# ============================================================

echo
echo "============================================================"
echo "BUILD MIZUROUTE"
echo "============================================================"

make \
    -C "$F_MASTER" \
    -f build/Makefile \
    FC="$FC" \
    FC_EXE="$FC_EXE" \
    EXE="$EXE_NAME" \
    MODE="$MODE" \
    isOpenMP="$IS_OPENMP" \
    isPIO="$IS_PIO" \
    isGPTL="$IS_GPTL" \
    PIO_FILESYSTEM_HINTS= \
    F_MASTER="$F_MASTER" \
    NCDF_PATH="$NCDF_PATH"


# ============================================================
# VERIFY EXECUTABLE
# ============================================================

if [ ! -x "$EXPECTED_EXE" ]; then

    echo
    echo "ERROR: Expected mizuRoute executable was not created:"
    echo "$EXPECTED_EXE"

    echo
    echo "Potential executables found:"

    find "$INSTALL_PATH" \
        -maxdepth 5 \
        -type f \
        -perm -111 \
        -name "*route*" \
        -print

    exit 1
fi


# ============================================================
# DEPENDENCY CHECK
# ============================================================

echo
echo "============================================================"
echo "MIZUROUTE COMPILED SUCCESSFULLY"
echo "============================================================"

echo
echo "Executable:"
echo "$EXPECTED_EXE"

echo
echo "Executable dependencies:"

ldd "$EXPECTED_EXE" | grep -E \
    "mpi|pio|netcdf|gfortran|quadmath|gcc" || true


# ============================================================
# BASIC EXECUTABLE CHECK
# ============================================================

echo
echo "============================================================"
echo "MIZUROUTE EXECUTABLE CHECK"
echo "============================================================"

CHECK_FILE="/tmp/mizuroute_check_${USER}_$$.txt"

set +e

"$EXPECTED_EXE" > "$CHECK_FILE" 2>&1

MIZU_STATUS=$?

set -e


head -40 "$CHECK_FILE" || true

rm -f "$CHECK_FILE"


echo
echo "mizuRoute executable return code: $MIZU_STATUS"

# A non-zero code without a control-file argument can be normal.
# This check primarily confirms that the executable starts and
# that shared-library dependencies are resolved.


# ============================================================
# LOGGING
# ============================================================

LOG_DIR="${INSTALL_PATH}/_workflow_log"

mkdir -p "$LOG_DIR"

LOG_FILE="${LOG_DIR}/$(date '+%Y%m%d')_compile_mizuroute.txt"


{
    echo "mizuRoute compilation"
    echo "Date: $(date)"
    echo
    echo "Version: $ACTUAL_VERSION"
    echo "Commit: $ACTUAL_HASH"
    echo
    echo "Compiler family: $FC"
    echo "MPI Fortran compiler: $FC_EXE"
    "$FC_EXE" --version | head -1
    echo
    echo "netCDF-C:"
    nc-config --version
    echo
    echo "netCDF-Fortran:"
    nf-config --version
    echo
    echo "MODE: $MODE"
    echo "OpenMP: $IS_OPENMP"
    echo "PIO: $IS_PIO"
    echo "GPTL: $IS_GPTL"
    echo
    echo "Executable:"
    echo "$EXPECTED_EXE"
    echo
    echo "Dependencies:"
    ldd "$EXPECTED_EXE" || true

} > "$LOG_FILE"


cp "${SCRIPT_DIR}/2b_compile_mizuroute.sh" "$LOG_DIR/"


# ============================================================
# FINAL SUMMARY
# ============================================================

echo
echo "============================================================"
echo "MIZUROUTE INSTALLATION COMPLETE"
echo "============================================================"

echo "Version    : $ACTUAL_VERSION"
echo "Commit     : $ACTUAL_HASH"
echo "Compiler   : $FC_EXE"
echo "Mode       : $MODE"
echo "OpenMP     : $IS_OPENMP"
echo "PIO        : $IS_PIO"
echo "GPTL       : $IS_GPTL"
echo "Executable : $EXPECTED_EXE"
echo "Log        : $LOG_FILE"

echo "============================================================"