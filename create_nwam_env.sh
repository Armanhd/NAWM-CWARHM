#!/bin/bash

#SBATCH --job-name=nwam_env_create
#SBATCH --time=02:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=2
#SBATCH --output=nwam_env_create_%j.out
#SBATCH --error=nwam_env_create_%j.err

set -euo pipefail

module load conda/base

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM"

cd "$CWARHM"

echo "============================================================"
echo "CREATING NWAM CONDA ENVIRONMENT"
echo "============================================================"
echo "Start: $(date)"
echo

conda env create \
    -n nwam \
    -f environment_nwam.yml \
    --solver=libmamba

echo
echo "============================================================"
echo "VERIFYING ENVIRONMENT"
echo "============================================================"

conda run -n nwam python - <<'PY'
import numpy
import xarray
import geopandas
import rasterio
import rasterstats
import easymore

print("numpy      :", numpy.__version__)
print("xarray     :", xarray.__version__)
print("geopandas  :", geopandas.__version__)
print("rasterio   :", rasterio.__version__)
print("rasterstats:", rasterstats.__version__)
print("EASYMORE   : OK")
PY

conda run -n nwam bash -c '
echo
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
echo "netCDF-C:"
which nc-config
nc-config --version

echo
echo "netCDF-Fortran:"
which nf-config
nf-config --version
'

echo
echo "============================================================"
echo "NWAM ENVIRONMENT CREATED SUCCESSFULLY"
echo "============================================================"
echo "End: $(date)"