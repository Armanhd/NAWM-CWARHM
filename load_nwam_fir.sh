#!/bin/bash
# Load the FIR Python environment for NAWM-CWARHM-MX.
# Usage: source load_nwam_fir.sh

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "ERROR: This script must be sourced:"
    echo "  source load_nwam_fir.sh"
    exit 1
fi

# Avoid loading modules over an unrelated active virtual environment.
if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    if [[ "$VIRTUAL_ENV" != "$HOME/virtual-envs/nwam-fir" ]]; then
        echo "ERROR: Deactivate the current virtual environment first."
        return 1
    fi
    deactivate
fi

# FIR software modules.
module load StdEnv/2023 \
    python/3.12.4 \
    python-build-bundle/2026a \
    scipy-stack/2026a \
    gdal/3.9.1 \
    mpi4py/4.0.3 \
    libspatialindex/1.9.3 || return 1

# Use the PROJ database compatible with pyproj 3.7.2.
export PROJ_DATA="/cvmfs/soft.computecanada.ca/easybuild/software/2023/x86-64-v3/Compiler/gcccore/proj/9.4.1/share/proj"

if [[ ! -f "$PROJ_DATA/proj.db" ]]; then
    echo "ERROR: PROJ database not found: $PROJ_DATA/proj.db"
    return 1
fi

# Activate project virtual environment.
source "$HOME/virtual-envs/nwam-fir/bin/activate" || return 1

echo "=================================================="
echo "NAWM-CWARHM-MX Python environment activated"
echo "=================================================="
echo "Python: $(python --version)"
echo "Environment: $VIRTUAL_ENV"
echo "GDAL: $(gdalinfo --version)"
echo "=================================================="
