# NAWM-CWARHM to SUMMA/mizuRoute calibration inputs

Convert basin data produced by **NAWM-CWARHM** into calibration-ready SUMMA and mizuRoute input folders in two modes:

- **Lumped:** one HRU per basin, using the CENTURY reference initialization and parameters.
- **Distributed:** preserve the existing HRUs, spatial attributes and routing topology; align HRU identifiers across SUMMA, forcing and mizuRoute.

The scripts do **not** modify the original NAWM-CWARHM datasets. They perform input conversion and data-integrity checks; successful conversion is **not** evidence that SUMMA/mizuRoute simulations run or are scientifically valid.

## Tested application

CAMELS-SPAT on University of Calgary ARC: **1,426 basins** (304 headwater, 727 meso-scale, 395 macro-scale); **32,802 distributed HRUs**. Hourly forcing spans 1950–2019 (local-time file timestamps can begin on 1949-12-31). The generated cold state uses three soil layers: **0.2, 0.3 and 0.5 m**. As of 2026-11-19, the lumped and distributed production Slurm arrays were running; do not submit duplicate arrays.

## Repository layout

| Files | Purpose |
| --- | --- |
| `01_inventory_basins.py`–`04_validate_basins.py` | Lumped inventory, preparation, conversion and validation |
| `05_inventory_distributed.py`–`08_validate_distributed_basins.py` | Distributed inventory, preparation, conversion and validation |
| `09_prepare_distributed_runtime.py` | Optional basin-specific TOML generation; not model execution |
| `10_distributed_production_task.sh`, `10_submit_distributed_conversion.sh` | Distributed Slurm production |
| `conversion_task.sh`, `submit_conversion.sh` | Lumped Slurm production |
| `config/` | Source/output/reference policies; paths must be checked before reuse |
| `env/load_model_env_arc.sh` | ARC Python/NetCDF environment |
| `doc/USER_MANUAL.md` | Detailed instructions and limitations |

The repository's `reference/`, `reports/`, `slurm_logs/` and `test_distributed/` contain local/reference/generated material and are normally excluded from Git. Reference datasets must be supplied separately.

## Quick start on ARC

```bash
export CODE=/work/comphyd_lab/users/arman.haddadchi/NWAM/NAWM_CWARHM_to_SUMMA_transfer
cd "$CODE"
source "$CODE/env/load_model_env_arc.sh"
```

Inspect and adapt `config/camels_spat_arc.toml` (lumped) or `config/camels_spat_distributed_arc.toml` (distributed). The current scripts include CAMELS-SPAT filenames and absolute ARC paths; they are **not** automatically portable to a different basin collection or cluster.

For the distributed workflow, first produce a basin inventory and a separate HRU-ID audit. The tested inventory command is:

```bash
python3 "$CODE/05_inventory_distributed.py" \
  --config "$CODE/config/camels_spat_distributed_arc.toml" \
  --inventory "$CODE/reports/camels_spat_lumped_inventory.csv" \
  --hru-audit "$CODE/reports/distributed_hru_id_audit.csv" \
  --output "$CODE/reports/camels_spat_distributed_inventory.csv"
```

Then run Steps 06–08 on a small sample before Slurm production. See the [user manual](doc/USER_MANUAL.md) for commands, validation, recovery and use with other NAWM-CWARHM basins.

## Distributed ID policy

For the **currently implemented one-HRU-per-GRU case**, the SUMMA `hruId`, `gruId`, `hru2gruId`, cold-state/trial-parameter/forcing `hruId`, and mizuRoute topology `hruId` must match in corresponding order. Original routing identifiers are retained, regardless of the delineation product used. The forcing dimension coordinate `hru` remains positional. Arbitrary HRU/GRU remapping is not supported by this converter.

## Scientific caution

Audit catchment boundaries, HRU areas, routing links, forcing, observations and reference-parameter suitability for any new basin collection. Data-integrity validation does not substitute for scientific assessment.
