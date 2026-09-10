#!/bin/bash
set -euo pipefail

ROOT="/work/comphyd_lab/users/arman.haddadchi/CENTURY_Basins_summa_mizuroute_exps"

TOOLDIR="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/5_model_input/SUMMA/0_coldstate_tools"

echo "============================================================"
echo "GENERATE STANDARD 3-LAYER SUMMA COLD STATES"
echo "============================================================"
echo "Root: $ROOT"
echo

python "$TOOLDIR/make_3layer_coldstate.py" \
    --root "$ROOT" \
    --activate

echo
echo "Finished."