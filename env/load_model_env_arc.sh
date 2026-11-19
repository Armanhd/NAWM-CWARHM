#!/usr/bin/env bash

# NAWM-CWARHM to SUMMA conversion environment on ARC.
# Source this file; do not execute it in a separate shell.

module load python/3.12.5
module load lib/netcdf/4.9.2

CODE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export PYTHONPATH="$CODE_ROOT/python_packages${PYTHONPATH:+:$PYTHONPATH}"

python3 -c "import numpy, netCDF4, cftime" || return 1

echo "ARC SUMMA conversion environment loaded."
python3 --version
