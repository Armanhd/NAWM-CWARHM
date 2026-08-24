#!/bin/bash

#SBATCH --job-name=SUMMA_merge
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --partition=cpu2025,cpu2023,cpu2022
#SBATCH --output=SUMMA_merge_%j.out
#SBATCH --error=SUMMA_merge_%j.err

set -euo pipefail

module load conda/base
conda activate nwam

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python \
    "${SCRIPT_DIR}/2_merge_summa_array_outputs.py"