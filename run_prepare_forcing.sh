#!/bin/bash
#SBATCH --job-name=nwam_prepare
#SBATCH --time=12:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2
#SBATCH --output=prepare_forcing_%j.out
#SBATCH --error=prepare_forcing_%j.err

module load conda/base
source activate nwam

cd /work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM/3a_forcing/0_existing_forcing

# echo "Preparing EM-Earth..."
# python 1_prepare_emearth_forcing.py

echo "Preparing ERA5..."
python 3_prepare_era5_forcing.py

echo "Finished."