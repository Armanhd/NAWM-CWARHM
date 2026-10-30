#!/usr/bin/env bash
# One-time module-first FIR Python environment setup for NAWM-CWARHM.
# Run on a FIR COMPUTE NODE (e.g., via salloc), from anywhere:
#   bash /path/to/NAWM-CWARHM-MX/setup_nwam_fir.sh
# Creates ~/virtual-envs/nwam-fir unless NWAM_FIR_VENV is set.
# Uses FIR's CVMFS modules and local Python wheelhouse; only netCDF4-python
# source is fetched from upstream GitHub if it is not already cached.
set -Eeuo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${NWAM_FIR_VENV:-$HOME/virtual-envs/nwam-fir}"
BUILD_ROOT="${NWAM_FIR_BUILD_DIR:-${SCRATCH:-$HOME/scratch}/nwam-netcdf4-build}"
SOURCE="${NWAM_FIR_NETCDF4_SOURCE:-$BUILD_ROOT/netcdf4-python}"
WHEELS="$BUILD_ROOT/wheels"

[[ -f "$ROOT/requirements_fir.in" ]] || fail "Missing $ROOT/requirements_fir.in"
type module >/dev/null 2>&1 || fail "FIR modules are not available. Run this on FIR."
case "$(hostname -s)" in
    login*) fail "Compile on a FIR compute node, not a login node. Use salloc first." ;;
esac
[[ -z "${VIRTUAL_ENV:-}" ]] || fail "Deactivate the current virtual environment before running setup."
[[ ! -e "$VENV" ]] || fail "Environment already exists: $VENV. Setup will not overwrite it."

module load StdEnv/2023 \
    python/3.12.4 \
    python-build-bundle/2026a \
    scipy-stack/2026a \
    gdal/3.9.1 \
    mpi4py/4.0.3 \
    libspatialindex/1.9.3 || fail "Could not load required FIR modules"

[[ "$(nc-config --has-parallel4)" == "no" ]] || fail "Expected serial NetCDF; nc-config reports parallel enabled"
NETCDF4_DIR="$(nc-config --prefix)"
HDF5_DIR="$(dirname "$(dirname "$(command -v h5cc)")")"
[[ -f "$NETCDF4_DIR/include/netcdf.h" ]] || fail "Missing serial NetCDF headers"
[[ -f "$HDF5_DIR/include/hdf5.h" ]] || fail "Missing serial HDF5 headers"

mkdir -p "$WHEELS"
# Work with cached source when available; do not download native libraries.
if [[ ! -d "$SOURCE/.git" ]]; then
    [[ ! -e "$SOURCE" ]] || fail "Source directory exists but is not a Git checkout: $SOURCE"
    command -v git >/dev/null || fail "Git is required for the one-time source checkout"
    echo "Fetching netCDF4-python v1.7.4rel source (one time)..."
    if ! git clone --depth 1 --branch v1.7.4rel \
        https://github.com/Unidata/netcdf4-python.git "$SOURCE"; then
        fail "Source fetch failed. If compute-node network is blocked, clone tag v1.7.4rel into $SOURCE from a login node; then rerun setup."
    fi
fi
[[ "$(git -C "$SOURCE" describe --tags --exact-match HEAD 2>/dev/null)" == "v1.7.4rel" ]] \
    || fail "Source must be checked out at netCDF4 tag v1.7.4rel: $SOURCE"

# This upstream metadata classifier was rejected by the FIR build toolchain;
# deleting the classifier does not alter the compiled extension's code.
if grep -q 'Programming Language :: Python :: 3\.14' "$SOURCE/pyproject.toml"; then
    sed -i '/Programming Language :: Python :: 3\.14/d' "$SOURCE/pyproject.toml"
fi


mkdir -p "$(dirname "$VENV")" "$WHEELS"
virtualenv --no-download --system-site-packages "$VENV"
# shellcheck disable=SC1090
source "$VENV/bin/activate"

# Build tools are installed exclusively from the Alliance wheelhouse.
python -m pip install --no-index --upgrade \
    'setuptools==80.9.0' 'setuptools-scm==9.2.2' 'wheel==0.45.1' \
    'Cython==3.2.4' 'packaging==26.3' 'cftime==1.6.5' \
    'virtualenv>=20.26.6' 'platformdirs>=4.3.6' \
    'typing-extensions>=4.14.1'

export NETCDF4_DIR HDF5_DIR
export USE_NCCONFIG=1 USE_SETUPCFG=0
(
    cd "$SOURCE"
    python -m pip wheel --no-index --no-build-isolation --no-deps \
        --no-cache-dir --wheel-dir "$WHEELS" .
)

SERIAL_WHEEL="$(find "$WHEELS" -maxdepth 1 -type f -name 'netcdf4-1.7.4-*.whl' -print -quit)"
[[ -n "$SERIAL_WHEEL" ]] || fail "Serial netCDF4 wheel was not produced"

# Install the other Python dependencies from the CVMFS wheelhouse.
# Installing the serial wheel LAST replaces any MPI-linked netCDF4 wheel
# that a transitive requirement may have pulled in.
python -m pip install --no-index -r "$ROOT/requirements_fir.in"
python -m pip install --no-index --no-deps --force-reinstall "$SERIAL_WHEEL"

NETCDF_SO="$(find "$VENV/lib" -type f -path '*/site-packages/netCDF4/_netCDF4*.so' -print -quit)"
[[ -n "$NETCDF_SO" ]] || fail "netCDF4 Python extension was not installed"
if nm -D "$NETCDF_SO" | grep -Eq 'ompi_|MPI_'; then
    fail "Built netCDF4 extension still contains MPI references"
fi
if ldd "$NETCDF_SO" | grep -Eq 'netcdf-mpi|hdf5-mpi'; then
    fail "Built netCDF4 extension still links to MPI-enabled libraries"
fi

# Run validation in a clean shell with the standard loader.
deactivate
(
    # shellcheck disable=SC1090
    source "$ROOT/load_nwam_fir.sh"
    python -m pip check
    python "$ROOT/0_tools/check_nwam_fir.py"
)

echo
echo "FIR environment setup and validation passed."
echo "To use it in a new session:"
echo "  cd '$ROOT'"
echo "  source load_nwam_fir.sh"
echo "Build cache (not committed): $BUILD_ROOT"
