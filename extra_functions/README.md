# Extra CWARHM Functions

This directory contains optional utility scripts that are not part of the
standard CWARHM preprocessing workflow but are useful for specific NWAM
experiments and compatibility tests.

## update_lumped_coldstate_layers.py

This utility supports controlled SUMMA experiments where newly generated
lumped CWARHM inputs need to use the same vertical soil/state configuration
as an existing reference SUMMA experiment.

The issue was identified during the Exp1 versus Exp2b comparison for the
CENTURY basins. The newly generated CWARHM lumped `coldState.nc` used an
8-soil-layer configuration, whereas the reference Exp1 SUMMA simulations
used a 3-soil-layer configuration. Using the 8-layer cold state produced
substantially different SUMMA runoff even when the remaining model
configuration was intended to reproduce Exp1.

The controlled workflow therefore uses the reference 3-layer `coldState.nc`
and preserves its physical initial-state values. Because the reference and
new lumped domains can use different HRU identifiers (for example, 101 in
the reference experiment and 1 in the new CWARHM domain), the copied
cold-state HRU identifier must be updated to match the new `attributes.nc`.

The utility is intended to:

1. read the HRU ID from the new lumped `attributes.nc`;
2. copy a reference SUMMA `coldState.nc`;
3. preserve the reference vertical-layer structure and physical state values;
4. update only the copied `hruId` so it matches the new lumped domain; and
5. verify that the resulting cold state is compatible with the new one-HRU
   SUMMA setup.

For the CENTURY Exp2b test, this preserved the reference 3-soil-layer
configuration while changing the lumped HRU identifier from 101 to 1.

After correcting the cold-state configuration, the Exp1 and Exp2b SUMMA
runoff simulations for CAN_05BB001 were effectively identical
(correlation > 0.99999999), confirming that the previous discrepancy was
caused by the inconsistent cold-state/layer configuration.

This utility should only be used when reproducing or testing a reference
SUMMA configuration. It is not required for the standard CWARHM workflow,
where the newly generated cold-state configuration should normally be used.
