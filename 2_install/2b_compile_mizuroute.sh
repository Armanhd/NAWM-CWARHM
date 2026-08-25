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

EXPECTED_EXE="${F_MASTER}bin/${EXE_NAME}"


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
    echo "conda activate nwam_parallel"

    exit 1

fi


ENV_NAME="$(basename "$CONDA_PREFIX")"


if [ "$ENV_NAME" != "nwam_parallel" ]; then

    echo "ERROR: Parallel mizuRoute must currently be compiled"
    echo "inside the validated nwam_parallel environment."
    echo
    echo "Active environment:"
    echo "  $ENV_NAME"
    echo
    echo "Run:"
    echo "  conda activate nwam_parallel"

    exit 1

fi


# ============================================================
# FORCE CONDA / MPI TOOLCHAIN
# ============================================================

export PATH="${CONDA_PREFIX}/bin:${PATH}"

export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"


MPICC="${CONDA_PREFIX}/bin/mpicc"
MPICXX="${CONDA_PREFIX}/bin/mpicxx"
MPIF90="${CONDA_PREFIX}/bin/mpif90"
MPIFORT="${CONDA_PREFIX}/bin/mpifort"


export CC="$MPICC"

if [ -x "$MPICXX" ]; then
    export CXX="$MPICXX"
fi


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
    nf-config \
    pnetcdf-config
do

    if ! command -v "$command" >/dev/null 2>&1; then

        echo "ERROR: Required command not found:"
        echo "$command"

        exit 1

    fi

done


# ============================================================
# VERIFY PARALLEL NETCDF STACK
# ============================================================

echo
echo "============================================================"
echo "VERIFY PARALLEL NETCDF STACK"
echo "============================================================"


NETCDF_PARALLEL="$(
    nc-config --has-parallel 2>/dev/null || echo no
)"

NETCDF_PARALLEL4="$(
    nc-config --has-parallel4 2>/dev/null || echo no
)"

NETCDF_PNETCDF="$(
    nc-config --has-pnetcdf 2>/dev/null || echo no
)"


echo "NetCDF parallel    : $NETCDF_PARALLEL"
echo "NetCDF parallel4   : $NETCDF_PARALLEL4"
echo "NetCDF PnetCDF     : $NETCDF_PNETCDF"
echo "PnetCDF version    : $(pnetcdf-config --version)"


if [ "$NETCDF_PARALLEL" != "yes" ]; then

    echo
    echo "ERROR: NetCDF-C does not have parallel support."

    exit 1

fi


if [ "$NETCDF_PARALLEL4" != "yes" ]; then

    echo
    echo "ERROR: NetCDF-C does not have parallel NetCDF-4 support."

    exit 1

fi


if [ "$NETCDF_PNETCDF" != "yes" ]; then

    echo
    echo "ERROR: NetCDF-C does not report PnetCDF support."

    exit 1

fi


if [ ! -f "${CONDA_PREFIX}/lib/libpnetcdf.so" ] && \
   [ ! -f "${CONDA_PREFIX}/lib/libpnetcdf.a" ]; then

    echo
    echo "ERROR: PnetCDF library was not found under:"
    echo "${CONDA_PREFIX}/lib"

    exit 1

fi


# ============================================================
# BUILD SETTINGS
# ============================================================

# Compiler family expected by mizuRoute Makefile.
FC="gnu"

# Actual Fortran compiler must be MPI-enabled.
FC_EXE="$MPIF90"

MODE="fast"

# Stand-alone NWAM configuration.
IS_OPENMP="no"

# ParallelIO is required.
IS_PIO="yes"

# GPTL timing library.
IS_GPTL="yes"

# Both NetCDF and PnetCDF are supplied by nwam_parallel.
NCDF_PATH="${CONDA_PREFIX}"
PNETCDF_PATH="${CONDA_PREFIX}"


# ============================================================
# REPORT ENVIRONMENT
# ============================================================

echo
echo "============================================================"
echo "COMPILE PARALLEL-CAPABLE MIZUROUTE"
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
echo "MPI runtime:"
mpirun --version | head -2

echo
echo "netCDF-C:"
nc-config --version
echo "Parallel    : $(nc-config --has-parallel)"
echo "Parallel4   : $(nc-config --has-parallel4)"
echo "PnetCDF     : $(nc-config --has-pnetcdf)"

echo
echo "netCDF-Fortran:"
nf-config --version

echo
echo "PnetCDF:"
pnetcdf-config --version

echo
echo "Build settings:"
echo "MODE          = $MODE"
echo "OpenMP        = $IS_OPENMP"
echo "PIO           = $IS_PIO"
echo "GPTL          = $IS_GPTL"
echo "NCDF_PATH     = $NCDF_PATH"
echo "PNETCDF_PATH  = $PNETCDF_PATH"
echo "Executable    = $EXE_NAME"


# ============================================================
# BACK UP CURRENT WORKING EXECUTABLE
# ============================================================

if [ -x "$EXPECTED_EXE" ]; then

    BACKUP_EXE="${F_MASTER}bin/mizuroute_serial_backup.exe"

    if [ ! -e "$BACKUP_EXE" ]; then

        echo
        echo "Backing up existing working mizuRoute executable:"
        echo "$EXPECTED_EXE"
        echo "->"
        echo "$BACKUP_EXE"

        cp -p \
            "$EXPECTED_EXE" \
            "$BACKUP_EXE"

    else

        echo
        echo "Existing serial backup retained:"
        echo "$BACKUP_EXE"

    fi

fi


# ============================================================
# CLEAN PREVIOUS BUILD
# ============================================================

echo
echo "============================================================"
echo "CLEAN PREVIOUS BUILD"
echo "============================================================"


echo "Cleaning mizuRoute objects..."

make \
    -C "$F_MASTER" \
    -f build/Makefile \
    F_MASTER="$F_MASTER" \
    clean \
    >/dev/null 2>&1 || true


echo "Cleaning ParallelIO through mizuRoute Makefile..."

make \
    -C "$F_MASTER" \
    -f build/Makefile \
    F_MASTER="$F_MASTER" \
    cleanlibs \
    >/dev/null 2>&1 || true


# ------------------------------------------------------------
# Critical:
# Remove old PIO CMake cache/configuration.
#
# Otherwise CMake can reuse the old serial-NetCDF detection.
# Keep the piolib directory itself because the mizuRoute
# Makefile expects it to exist.
# ------------------------------------------------------------

PIOLIB_DIR="${F_MASTER}build/lib/piolib"

mkdir -p "$PIOLIB_DIR"


echo "Removing old ParallelIO CMake configuration..."

rm -rf \
    "${PIOLIB_DIR}/CMakeCache.txt" \
    "${PIOLIB_DIR}/CMakeFiles" \
    "${PIOLIB_DIR}/cmake_install.cmake" \
    "${PIOLIB_DIR}/Makefile" \
    "${PIOLIB_DIR}/lib" \
    "${PIOLIB_DIR}/include"


mkdir -p \
    "${PIOLIB_DIR}/lib" \
    "${PIOLIB_DIR}/include"


# Remove current executable only after backup.
rm -f "$EXPECTED_EXE"


# ============================================================
# BUILD
# ============================================================

echo
echo "============================================================"
echo "BUILD MIZUROUTE + PARALLELIO"
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
    F_MASTER="$F_MASTER" \
    NCDF_PATH="$NCDF_PATH" \
    PNETCDF_PATH="$PNETCDF_PATH"


# ============================================================
# VERIFY EXECUTABLE EXISTS
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
# VERIFY PIO CONFIGURATION
# ============================================================

PIO_CACHE="${PIOLIB_DIR}/CMakeCache.txt"


echo
echo "============================================================"
echo "VERIFY PARALLELIO CONFIGURATION"
echo "============================================================"


if [ ! -f "$PIO_CACHE" ]; then

    echo "ERROR: ParallelIO CMakeCache.txt was not created:"
    echo "$PIO_CACHE"

    exit 1

fi


echo
echo "Relevant PIO CMake settings:"

grep -Ei \
    "pnetcdf|netcdf.*parallel|mpiio|with_pnetcdf|netcdf_path" \
    "$PIO_CACHE" \
    || true


echo
echo "Looking for PnetCDF configuration..."

if ! grep -qi "pnetcdf" "$PIO_CACHE"; then

    echo
    echo "ERROR: PnetCDF does not appear in the PIO CMake cache."

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
echo "Relevant executable dependencies:"

ldd "$EXPECTED_EXE" | \
grep -Ei \
"mpi|netcdf|hdf5|pnetcdf|gfortran|quadmath|gcc" \
|| true


# ============================================================
# CONFIRM ENVIRONMENT PATHS IN EXECUTABLE
# ============================================================

echo
echo "Checking that executable resolves libraries from:"
echo "$CONDA_PREFIX"

if ldd "$EXPECTED_EXE" | grep -E \
    "libmpi|libnetcdf|libnetcdff" | \
    grep -v "$CONDA_PREFIX" >/dev/null
then

    echo
    echo "WARNING:"
    echo "One or more core libraries are not resolving from"
    echo "the active nwam_parallel environment."

    ldd "$EXPECTED_EXE" | \
        grep -E "libmpi|libnetcdf|libnetcdff"

else

    echo "Core MPI/NetCDF libraries resolve from nwam_parallel: PASS"

fi


# ============================================================
# BASIC EXECUTABLE START CHECK
# ============================================================

echo
echo "============================================================"
echo "MIZUROUTE EXECUTABLE START CHECK"
echo "============================================================"


CHECK_FILE="/tmp/mizuroute_check_${USER}_$$.txt"


set +e

"$EXPECTED_EXE" > "$CHECK_FILE" 2>&1

MIZU_STATUS=$?

set -e


head -40 "$CHECK_FILE" || true

rm -f "$CHECK_FILE"


echo
echo "mizuRoute no-argument return code: $MIZU_STATUS"

echo
echo "A non-zero return code here can be normal because no"
echo "mizuRoute control file was supplied."


# ============================================================
# LOGGING
# ============================================================

LOG_DIR="${INSTALL_PATH}/_workflow_log"

mkdir -p "$LOG_DIR"


LOG_FILE="${LOG_DIR}/$(date '+%Y%m%d')_compile_mizuroute_parallel.txt"


{
    echo "Parallel-capable mizuRoute compilation"
    echo "Date: $(date)"

    echo
    echo "Version: $ACTUAL_VERSION"
    echo "Commit: $ACTUAL_HASH"

    echo
    echo "Conda environment:"
    echo "$CONDA_PREFIX"

    echo
    echo "Compiler family: $FC"
    echo "MPI Fortran compiler: $FC_EXE"
    "$FC_EXE" --version | head -1

    echo
    echo "MPI:"
    mpirun --version | head -2

    echo
    echo "netCDF-C:"
    nc-config --version
    echo "parallel: $(nc-config --has-parallel)"
    echo "parallel4: $(nc-config --has-parallel4)"
    echo "pnetcdf: $(nc-config --has-pnetcdf)"

    echo
    echo "netCDF-Fortran:"
    nf-config --version

    echo
    echo "PnetCDF:"
    pnetcdf-config --version

    echo
    echo "MODE: $MODE"
    echo "OpenMP: $IS_OPENMP"
    echo "PIO: $IS_PIO"
    echo "GPTL: $IS_GPTL"
    echo "NCDF_PATH: $NCDF_PATH"
    echo "PNETCDF_PATH: $PNETCDF_PATH"

    echo
    echo "Executable:"
    echo "$EXPECTED_EXE"

    echo
    echo "Dependencies:"
    ldd "$EXPECTED_EXE" || true

    echo
    echo "ParallelIO CMake settings:"
    grep -Ei \
        "pnetcdf|netcdf.*parallel|mpiio|with_pnetcdf|netcdf_path" \
        "$PIO_CACHE" \
        || true

} > "$LOG_FILE"


cp \
    "${SCRIPT_DIR}/2b_compile_mizuroute.sh" \
    "$LOG_DIR/"


# ============================================================
# FINAL SUMMARY
# ============================================================

echo
echo "============================================================"
echo "PARALLEL-CAPABLE MIZUROUTE INSTALLATION COMPLETE"
echo "============================================================"

echo "Version       : $ACTUAL_VERSION"
echo "Commit        : $ACTUAL_HASH"
echo "Environment   : $ENV_NAME"
echo "Compiler      : $FC_EXE"
echo "Mode          : $MODE"
echo "OpenMP        : $IS_OPENMP"
echo "PIO           : $IS_PIO"
echo "GPTL          : $IS_GPTL"
echo "NetCDF MPI    : $NETCDF_PARALLEL"
echo "NetCDF-4 MPI  : $NETCDF_PARALLEL4"
echo "PnetCDF       : $NETCDF_PNETCDF"
echo "Executable    : $EXPECTED_EXE"
echo "Serial backup : ${F_MASTER}bin/mizuroute_serial_backup.exe"
echo "Log           : $LOG_FILE"

echo
echo "IMPORTANT:"
echo "Compilation success does NOT yet prove correct multi-rank"
echo "mizuRoute output. Next test with 1, 2, and 4 MPI ranks and"
echo "run the strict yearly NetCDF QA before changing Stage 6."

echo "============================================================"