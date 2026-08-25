#!/bin/bash
#SBATCH --job-name=nwam_env
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --partition=cpu2025,cpu2023,cpu2022
#SBATCH --output=nwam_parallel_env_%j.out
#SBATCH --error=nwam_parallel_env_%j.err

set -euo pipefail

module load conda/base

cd /work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM

echo "============================================================"
echo "CREATE NWAM PARALLEL ENVIRONMENT"
echo "============================================================"
echo "Start: $(date)"
echo "Node : $(hostname)"
echo

conda env create \
    -f environment_nwam_parallel.yml

echo
echo "Environment created successfully."
echo "End: $(date)"
echo "============================================================"
EOF