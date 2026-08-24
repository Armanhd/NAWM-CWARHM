#!/bin/bash
#SBATCH --job-name=era5_remap
#SBATCH --time=02:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --array=0-839%20
#SBATCH --output=slurm_logs/era5_remap_%A_%a.out
#SBATCH --error=slurm_logs/era5_remap_%A_%a.err

module load conda/base

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM"

CONTROL="${CWARHM}/0_control_files/control_active.txt"

cd "${CWARHM}/4b_remapping/2_forcing" || exit 1


# ------------------------------------------------------------
# Read forcing period
# ------------------------------------------------------------

YEARS=$(grep -m 1 "^forcing_raw_time" "$CONTROL")
YEARS=${YEARS#*|}
YEARS=${YEARS%%#*}
YEARS=$(echo "$YEARS" | xargs)

START_YEAR=${YEARS%,*}
END_YEAR=${YEARS#*,}


# ------------------------------------------------------------
# Convert SLURM index to year/month
# ------------------------------------------------------------

IDX=${SLURM_ARRAY_TASK_ID}

YEAR=$((START_YEAR + IDX / 12))
MONTH=$((IDX % 12 + 1))


# ------------------------------------------------------------
# Safety check
# ------------------------------------------------------------

if [ "$YEAR" -gt "$END_YEAR" ]; then
    echo "Outside forcing period. Exiting."
    exit 0
fi


echo "============================================================"
echo "ERA5 HRU REMAPPING"
echo "Year : $YEAR"
echo "Month: $MONTH"
echo "============================================================"


conda run -n nwam \
python 2a_remap_all_ERA5.py \
"$YEAR" "$MONTH"