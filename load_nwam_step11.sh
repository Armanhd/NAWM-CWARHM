#!/bin/bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "ERROR: Source this script."
    exit 1
fi

module load StdEnv/2023 \
    python/3.12.4 \
    scipy-stack/2026a \
    gdal/3.9.1 \
    mpi4py/4.0.3 || return 1

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    deactivate
fi

source "$HOME/virtual-envs/nwam-fir-step11/bin/activate" || return 1

export PROJ_DATA="/cvmfs/soft.computecanada.ca/easybuild/software/2023/x86-64-v3/Compiler/gcccore/proj/9.4.1/share/proj"

MPI_LIB=$(LD_PRELOAD= ldd "$VIRTUAL_ENV/lib/python3.12/site-packages/netCDF4/"_netCDF4*.so |
    awk '/libmpi.so.40/ {print $3; exit}')

[[ -f "$MPI_LIB" ]] || { echo "ERROR: MPI library missing"; return 1; }

export NWAM_STEP11_MPI_LIB="$MPI_LIB"

LD_PRELOAD="$MPI_LIB" python -c 'import numpy, geopandas, netCDF4; from osgeo import gdal_array' || return 1

echo "STEP 11 ENVIRONMENT: PASS"
