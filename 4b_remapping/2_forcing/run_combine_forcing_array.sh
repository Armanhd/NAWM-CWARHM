#!/bin/bash
#SBATCH --job-name=combine_forcing
#SBATCH --time=01:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1
#SBATCH --array=0-839%20
#SBATCH --output=slurm_logs/combine_%A_%a.out
#SBATCH --error=slurm_logs/combine_%A_%a.err

module load conda/base

CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM"

CONTROL="${CWARHM}/0_control_files/control_active.txt"

cd "${CWARHM}/4b_remapping/2_forcing" || exit 1


# Read forcing_raw_time
YEARS=$(grep -m 1 "^forcing_raw_time" "$CONTROL")
YEARS=${YEARS#*|}
YEARS=${YEARS%%#*}
YEARS=$(echo "$YEARS" | xargs)

START_YEAR=${YEARS%,*}
END_YEAR=${YEARS#*,}


# Convert SLURM index to year/month
IDX=${SLURM_ARRAY_TASK_ID}

YEAR=$((START_YEAR + IDX / 12))
MONTH=$((IDX % 12 + 1))


# Safety check
if [ "$YEAR" -gt "$END_YEAR" ]; then
    echo "Outside forcing period. Exiting."
    exit 0
fi


echo "============================================================"
echo "COMBINE NWAM SUMMA FORCING"
echo "Year : $YEAR"
echo "Month: $MONTH"
echo "============================================================"


conda run -n nwam \
python 3_combine_forcing_for_SUMMA.py \
"$YEAR" "$MONTH"