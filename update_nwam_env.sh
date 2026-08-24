#!/bin/bash

#SBATCH --job-name=nwam_env_update
#SBATCH --time=02:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=2
#SBATCH --output=nwam_env_update_%j.out
#SBATCH --error=nwam_env_update_%j.err

set -euo pipefail

module load conda/base

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM"

cd "$CWARHM"

echo "============================================================"
echo "UPDATING NWAM CONDA ENVIRONMENT"
echo "============================================================"
echo "Start: $(date)"
echo

conda env update \
    -n nwam \
    -f environment_nwam.yml \
    --prune \
    --solver=libmamba

echo
echo "============================================================"
echo "VERIFYING PYTHON ENVIRONMENT"
echo "============================================================"

conda run -n nwam python - <<'PY'
import numpy
import xarray
import geopandas
import rasterio
import rasterstats
import easymore
import mpi4py
import git

print("numpy      :", numpy.__version__)
print("xarray     :", xarray.__version__)
print("geopandas  :", geopandas.__version__)
print("rasterio   :", rasterio.__version__)
print("rasterstats:", rasterstats.__version__)
print("mpi4py     :", mpi4py.__version__)
print("GitPython  :", git.__version__)
print("EASYMORE   : OK")
PY

echo
echo "============================================================"
echo "VERIFYING COMPILER / NETCDF / MPI TOOLS"
echo "============================================================"

conda run -n nwam bash -c '
echo "gcc:"
which gcc
gcc --version | head -1

echo
echo "gfortran:"
which gfortran
gfortran --version | head -1

echo
echo "cmake:"
which cmake
cmake --version | head -1

echo
echo "nc-config:"
which nc-config
nc-config --version

echo
echo "nf-config:"
which nf-config
nf-config --version

echo
echo "mpicc:"
which mpicc
mpicc --version | head -1

echo
echo "mpifort:"
which mpifort
mpifort --version | head -1

echo
echo "mpif90:"
which mpif90
mpif90 --version | head -1

echo
echo "mpirun:"
which mpirun
mpirun --version | head -2
'

echo
echo "============================================================"
echo "NWAM ENVIRONMENT UPDATE COMPLETE"
echo "============================================================"
echo "End: $(date)"