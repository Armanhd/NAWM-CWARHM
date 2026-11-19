#!/usr/bin/env bash
#SBATCH --job-name=camels_dist
#SBATCH --time=08:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=/work/comphyd_lab/users/arman.haddadchi/NWAM/NAWM_CWARHM_to_SUMMA_transfer/slurm_logs/distributed_%A_%a.out
#SBATCH --error=/work/comphyd_lab/users/arman.haddadchi/NWAM/NAWM_CWARHM_to_SUMMA_transfer/slurm_logs/distributed_%A_%a.err

set -euo pipefail

CODE="/work/comphyd_lab/users/arman.haddadchi/NWAM/NAWM_CWARHM_to_SUMMA_transfer"

bash "$CODE/10_distributed_production_task.sh" \
    "$SLURM_ARRAY_TASK_ID"
