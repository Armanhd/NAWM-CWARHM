#!/bin/bash
#SBATCH --job-name=nwam_remap
#SBATCH --time=24:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=2
#SBATCH --output=remap_forcing_%j.out
#SBATCH --error=remap_forcing_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=arman.haddadchi@ucalgary.ca

set -e

module load conda/base


cd /work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM/4b_remapping/2_forcing


echo "Remapping ERA5..."
conda run -n nwam python 2a_remap_all_ERA5.py


echo "Remapping EM-Earth..."
conda run -n nwam python 2b_remap_all_EM_Earth.py


echo "Finished remapping both forcing datasets."