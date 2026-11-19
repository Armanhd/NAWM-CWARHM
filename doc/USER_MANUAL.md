# User manual — NAWM-CWARHM to SUMMA/mizuRoute transfer

## 1. Purpose and scope

The repository converts existing NAWM-CWARHM basin outputs to a consistent calibration input layout for **lumped** (one HRU per basin) or **distributed** (original HRUs and topology) SUMMA/mizuRoute workflows. It copies forcing and observations, prepares reference-based parameter and cold-state inputs, and validates data preservation. **It does not run SUMMA or mizuRoute.**

The scripts were piloted on University of Calgary **ARC** with CAMELS-SPAT: 1,426 basins, 32,802 distributed HRUs, hourly forcing covering 1950–2019. A different basin collection may require adaptation of folder names, observation patterns, scripts and reference files.

## 2. Requirements and initial setup

- ARC environment: Python 3.12.5, NumPy, netCDF4/cftime, standard-library `tomllib`; Bash and Slurm for batch runs.
- Accessible, **read-only** NAWM-CWARHM source dataset.
- CENTURY-style reference inputs specified by `reference_basin` in the TOML, including `summa_state/coldState.nc`, `summa_inputs/trialParams.priori.nc`, and `mizuroute_inputs/mizuroute.param`.
- Sufficient space/quota for copied forcing files and temporary staging.

```bash
export CODE=/work/comphyd_lab/users/arman.haddadchi/NWAM/NAWM_CWARHM_to_SUMMA_transfer
source "$CODE/env/load_model_env_arc.sh"
```

Edit/check `config/camels_spat_arc.toml` for lumped or `config/camels_spat_distributed_arc.toml` for distributed. **Also inspect hard-coded paths in the production `.sh` scripts.** Do not edit scripts or configurations while their jobs are running.

### Expected source structure (distributed)

```text
<source>/<scale>/domain_<BASIN>/
  settings/SUMMA/{attributes.nc,coldState.nc,trialParams.nc,forcingFileList_LST.txt,...}
  settings/mizuRoute/topology.nc
  forcing/6_SUMMA_input_LST/*.nc
  observations/<daily-and-hourly-files>
```

The tested source collection has `headwater`, `meso_scale` and `macro_scale` groups. Distributed source attributes must contain `hruId`, `gruId` and `hru2gruId`; routing topology must contain `hruId` and its segment/network variables. The scripts require one HRU per GRU, identical GRU/routing order and matching original forcing IDs. IDs need **not** come from MERIT; any delineation is acceptable if these structural conditions hold.

## 3. Lumped workflow (Steps 01–04)

1. `01_inventory_basins.py`: inventory basin paths, forcing and observations.
2. `02_prepare_cold_state.py`: prepare reference initial conditions.
3. `03_convert_basins.py`: convert a basin using one HRU; select `--basin` or `--index`.
4. `04_validate_basins.py`: independently check output.

Check available options with `python3 "$CODE/<script>.py" --help`. Example conversion:

```bash
python3 "$CODE/03_convert_basins.py" \
  --config "$CODE/config/camels_spat_arc.toml" \
  --inventory "$CODE/reports/camels_spat_lumped_inventory.csv" \
  --basin CAN_01AF007
```

For an ARC batch, inspect `conversion_task.sh` and `submit_conversion.sh` and their existing options before submission; do not create a duplicate active array.

## 4. Distributed workflow (Steps 05–08)

**Preflight:** Before Step 05, generate a basin inventory and an independent HRU-ID audit. `05_inventory_distributed.py` consumes these existing CSV files; it does not create the upstream audit. For the tested collection, the audit found direct one-to-one correspondence across all 1,426 basins.

```bash
python3 "$CODE/05_inventory_distributed.py" \
  --config "$CODE/config/camels_spat_distributed_arc.toml" \
  --inventory "$CODE/reports/camels_spat_lumped_inventory.csv" \
  --hru-audit "$CODE/reports/distributed_hru_id_audit.csv" \
  --output "$CODE/reports/camels_spat_distributed_inventory.csv"
```

**Step 06:** Prepare distributed `attributes.nc`, cold state (three layers of 0.2, 0.3, 0.5 m), trial parameters and unchanged routing topology. Existing routing IDs become the corresponding SUMMA HRU IDs. The configured CENTURY contour-length policy is applied; other distributed spatial attributes remain unchanged.

```bash
TEST06="$CODE/reports/distributed_tests"
python3 "$CODE/06_prepare_distributed_inputs.py" \
  --config "$CODE/config/camels_spat_distributed_arc.toml" \
  --inventory "$CODE/reports/camels_spat_distributed_inventory.csv" \
  --basin CAN_01AF007 --destination "$TEST06"
```

**Step 07:** Copy original LST forcing and observations and update only forcing `hruId` values (no HRU reordering, no meteorological transformations). It does not create `lumped_to_hru.nc`.

```bash
TEST07="$CODE/reports/distributed_full_tests"
python3 "$CODE/07_convert_distributed_basins.py" \
  --config "$CODE/config/camels_spat_distributed_arc.toml" \
  --inventory "$CODE/reports/camels_spat_distributed_inventory.csv" \
  --basin CAN_01AF007 --step06 "$TEST06" --destination "$TEST07"
```

**Step 08:** Independently validate HRU/GRU/topology IDs, spatial attributes, expanded reference variables, routing topology, observations and **all non-ID forcing variables and time coordinates** (chunked comparison). Check distributed model decisions and absence of lumped remapping.

```bash
python3 "$CODE/08_validate_distributed_basins.py" \
  --config "$CODE/config/camels_spat_distributed_arc.toml" \
  --inventory "$CODE/reports/camels_spat_distributed_inventory.csv" \
  --destination "$TEST07" --basin CAN_01AF007 \
  --output "$CODE/reports/step08_distributed_validation.csv"
```

These scripts refuse to overwrite an existing test basin. Use a new destination for repeat tests rather than deleting active outputs.

## 5. Optional runtime TOML (Step 09)

`09_prepare_distributed_runtime.py` produces basin-specific TOMLs from `test_distributed/exp56_distributed/settings/summa_config_template.toml`. It reads **actual full forcing timestamps**, and sets nominal calibration dates from the intersection of forcing and daily observation time ranges. It retains direct `[hydrofabric]` routing and has no `[remapping]` section.

```bash
python3 "$CODE/09_prepare_distributed_runtime.py" \
  --config "$CODE/config/camels_spat_distributed_arc.toml" \
  --inventory "$CODE/reports/camels_spat_distributed_inventory.csv" \
  --converted-root "$TEST07" \
  --output-root "$CODE/reports/distributed_runtime_tests" \
  --template "$CODE/test_distributed/exp56_distributed/settings/summa_config_template.toml" \
  --basin CAN_01AF007
```

For the pilot, forcing timestamps ran `1949-12-31 20:00` to `2019-12-31 19:00` (613,608 hourly steps). **Do not impose the exp56 example's 2016–2024 window.** The generated TOMLs have **not** been tested by running SUMMA/mizuRoute; observation completeness and final-day runtime behavior were not verified.

## 6. Production on ARC (Step 10)

`10_distributed_production_task.sh` orchestrates Steps 06–08 per inventory row: stage, validate, copy observations, publish domain, final validate, clean successful staging. `10_submit_distributed_conversion.sh` wraps it for Slurm. Both currently include ARC- and CAMELS-SPAT-specific paths.

```bash
bash -n "$CODE/10_distributed_production_task.sh"
bash -n "$CODE/10_submit_distributed_conversion.sh"
mkdir -p "$CODE/slurm_logs"
```

A successful two-basin Slurm pilot used array `0,1%2` (job 51429361). The full distributed CAMELS-SPAT production array **51429743** was submitted as `0-1425%2`; the separate lumped array **51426027** was also running as of 2026-11-19. **Do not resubmit either while active.** For a new dataset, use its actual inventory length, validate a small pilot, and reassess memory, walltime, I/O and disk quota.

```bash
squeue -u "$USER"
sacct -j <JOB_ID> --format=JobID,State,Elapsed,MaxRSS,ReqMem,ExitCode
```

Completed tasks are skipped **only after revalidation**. Failed tasks can leave `<output>/.conversion_staging/<BASIN>/`; inspect the logs and staged files before carefully cleaning or retrying. Never remove staging belonging to active jobs.

## 7. Output layout

```text
<output>/
  domain/<BASIN>/
    summa_inputs/{attributes.nc,trialParams.nc,trialParams.priori.nc,...}
    summa_state/coldState.nc
    summa_forcing/*.nc
    mizuroute_inputs/{topology.nc,mizuroute.param}
  observations/{obs-daily,obs-hourly}/*.nc
  _audit/<BASIN>.csv
  .conversion_staging/                  # temporary; not model input
```

Run `08_validate_distributed_basins.py` against published output and check each audit CSV for `PASS`. The test outputs and staging should not be tracked in Git.

## 8. Reusing with another NAWM-CWARHM dataset

1. Inspect and adapt source naming, basin inventory, observation patterns and config paths.
2. Supply/check the CENTURY reference inputs; confirm their units and suitability.
3. Verify one-to-one HRU/GRU/routing matching and forcing IDs for **every basin**.
4. Run Steps 05–08 on representative small and large basins; inspect reports.
5. Modify production shell paths, output directory and Slurm array bounds/resources.
6. Pilot Slurm conversion before launching the rest. Validation is data-level only; no model run is required by this transfer workflow.

## 9. Scientific and operational cautions

- Check delineation, areas, routing topology, meteorology and observation quality independently.
- The distributed converter does **not** support arbitrary many-to-one HRU/GRU mappings.
- The current `fileManager.txt`/`fileManager_LST.txt` copied into test outputs may retain original CWARHM paths; use verified runtime configuration before any later model run.
- Some reference/example data are intentionally excluded from Git; a new installation needs them provisioned separately.
- Avoid editing/removing scripts, reference data or staging used by active Slurm jobs.
