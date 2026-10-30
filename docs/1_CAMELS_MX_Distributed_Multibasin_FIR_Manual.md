# CAMELS-MX — Distributed NAWM-CWARHM multibasin manual (FIR)

**Branch:** `CAMELS_SPAT_MX` · **Platform:** Alliance FIR · **Updated:** 30 October 2026
**Companion:** [Lumped-only FIR manual](2_CAMELS_MX_Lumpedonly_FIR_Manual.md)

> **Verified on FIR:** All 21 TDX-Hydro basin shapefile sets were located (18 `tdx_clipped`, 3 `tdx_nested_preview`). All 21 distributed controls were generated and inspected; the basin task file has 21 rows and the 1950–2019 monthly task file has 17,640 rows. **Later processing stages have not been validated for all 21 basins on FIR.** Commands below for Stage 00 onward are planned runs; inspect the FIR Slurm wrappers and test a single basin/job before submitting large arrays.

## 0. FIR configuration and source datasets

| Item | Setting |
|---|---|
| Code | `CAMELS_SPAT_MX` branch of `Armanhd/NAWM-CWARHM` |
| Python | FIR modules plus `source load_nwam_fir.sh` (Python 3.12.4) |
| Inventory | `0_control_files/CAMELS_MX_control_file_inputs.csv` (21 basins) |
| Template | `0_control_files/templates/control_CAMELS_MX_template.txt` |
| TDX-Hydro exports | `/project/6079554/share/camels-mx/basin_delineation/MX_*/cwarhm_exports/` |
| Shared output root | `/project/6079554/share/camels-mx/nawm_cwarhm_output` |
| Shared soil raster | `/project/6102189/data/geospatial-data/soil_classes/soil_classes.tif` |
| EM-Earth input | `/project/rrg-alpie/data/meteorological-data/EM_Earth_v1/deterministic_hourly` |
| EM-Earth precipitation | `prcp_corrected` (SUMMA variable remains `pptrate`) |
| Time period | `1950,2019` (840 months per basin) |
| DEM / vegetation | Existing MERIT Hydro DEM and MODIS workflow, verify Mexico coverage |

**TDX source folder exception:** `MX_12428`, `MX_12496`, and `MX_12532` use `tdx_nested_preview/shapefiles`; the other 18 use `tdx_clipped/shapefiles`. The corrected inventory records their actual locations.

## Pre-step — Clone and activate on FIR

```bash
git clone --branch CAMELS_SPAT_MX --single-branch \
  https://github.com/Armanhd/NAWM-CWARHM.git NAWM-CWARHM-MX
cd NAWM-CWARHM-MX
source load_nwam_fir.sh
export CWARHM_ROOT="$(pwd -P)"
export CONTROL_DIR="$CWARHM_ROOT/0_control_files"
export DATA_ROOT=/project/6079554/share/camels-mx/nawm_cwarhm_output
python -c 'import geopandas, rasterio, netCDF4; print("FIR dependencies OK")'
```

The validated developer checkout is `/home/armanhad/projects/rrg-mclark/armanhad/NAWM-CWARHM-MX`. **Other users should use their own clone.** `load_nwam_fir.sh` activates an existing environment; first-time installation uses `setup_nwam_fir.sh` on a **compute node**, not the login node (see repo instructions). Confirm access to shared `/project/...` datasets and output permissions. Never use ARC `conda activate nwam` or ARC `/work/comphyd_lab/` paths on FIR.

## Step 1 — Generate distributed controls for all 21 basins

```bash
cd "$CWARHM_ROOT/00_prepare_domain_shapefiles"
python 0_generate_multibasin_control_files.py \
  --csv ../0_control_files/CAMELS_MX_control_file_inputs.csv \
  --template ../0_control_files/templates/control_CAMELS_MX_template.txt \
  --prefix MX_ --emearth-precip prcp_corrected --dry-run
```

After reviewing the 21 selected basins and path settings, create the controls. Omit `--overwrite` for a fresh clone; use it **only intentionally**, because later Stage 00 may change domain settings.

```bash
python 0_generate_multibasin_control_files.py \
  --csv ../0_control_files/CAMELS_MX_control_file_inputs.csv \
  --template ../0_control_files/templates/control_CAMELS_MX_template.txt \
  --prefix MX_ --emearth-precip prcp_corrected
```

If the template is still at the original path in your clone, use `../0_control_files/control_CAMELS_MX_template.txt`; moving it into `templates/` avoids the task generator mistaking its `domain_name` for an actual basin. The working FIR template was moved to that subdirectory.

```bash
find "$CONTROL_DIR" -maxdepth 1 -name 'control_MX_*.txt' ! -name '*_lumped.txt' | wc -l
# Expected: 21
for f in "$CONTROL_DIR"/control_MX_*.txt; do
  grep -E '^(root_path|domain_name|forcing_raw_time|forcing_emearth_precip|parameter_soil_raw_path)' "$f"
done
```

## Step 2 — Generate distributed basin/month task files

```bash
cd "$CWARHM_ROOT/00_prepare_domain_shapefiles"
python 0b_generate_multibasin_month_tasks.py \
  --prefix MX_ --batch-name CAMELS_MX_all
wc -l ../0_control_files/multibasin_preprocessing_CAMELS_MX_all.txt \
      ../0_control_files/month_tasks_CAMELS_MX_all.txt
# Expected: 21 basin tasks; 17,640 month tasks
```

This step was **completed and checked on FIR**. Each basin has 840 months (1950–2019). Task files contain **checkout-specific absolute control paths**. Regenerate the task files after cloning into a different location, rather than reusing paths committed by another user.

## Step 2A — Load batch variables in a shell

The working checkout has a root-level `set_batch.sh`. Verify it points to this 21-basin batch. For another clone, set the variables as follows:

```bash
cd "$CWARHM_ROOT"
export BASIN_TASK="$CONTROL_DIR/multibasin_preprocessing_CAMELS_MX_all.txt"
export MONTH_TASK="$CONTROL_DIR/month_tasks_CAMELS_MX_all.txt"
export NBASIN="$(wc -l < "$BASIN_TASK")"
export NMONTH="$(wc -l < "$MONTH_TASK")"
echo "NBASIN=$NBASIN NMONTH=$NMONTH"
# Expected: NBASIN=21 NMONTH=17640
```

To use the existing configuration in the developer checkout, run `source set_batch.sh` and verify the two counts. Source these variables again in fresh shells or job scripts as appropriate.

## Step 3 — Prepare distributed domain shapefiles and forcing grids

Stage 00 processes TDX-Hydro source catchment and river network into `nawm_cwarhm_output/domain_MX_*/shapefiles/` without editing the sources. `1_prepare_river_network.py` converts `lengthkm` into metres in `length_m`; `2_prepare_catchment.py` prepares one HRU per GRU and recalculates area in square metres; `3_report_control_values.py` recalculates the forcing extent and outlet settings.

**Historical ARC validation for MX_1023 (not a FIR validation):**

```bash
cd "$CWARHM_ROOT/00_prepare_domain_shapefiles"
bash run_prepare_domain_shapefiles.sh "$CONTROL_DIR/control_MX_1023.txt"
# Expected: DOMAIN PREPARATION COMPLETED SUCCESSFULLY
```

Previously reported for `MX_1023` on FIR: 193 river segments, 193 GRUs/HRUs, one natural outlet, zero self-loops, 1,580.912 km² total prepared catchment area. The reporter adjusted the forcing spatial buffer from 0.25° (control generator) to **0.05°**. This behavior should be understood before preparing forcing.

For the remaining basins, use the existing Stage 00 Slurm wrapper **after confirming it resolves scripts from this checkout**:

```bash
cd "$CWARHM_ROOT/00_prepare_domain_shapefiles"
mkdir -p slurm_logs
sbatch --array=0-$((NBASIN-1))%4 \
  run_multibasin_preprocessing_array.sh "$BASIN_TASK"
squeue -u "$USER"
```

Check for the worker's `DOMAIN PREPARATION COMPLETED SUCCESSFULLY` message and inspect errors. The array runner may additionally create forcing grids. **Confirm runner requirements and log names on FIR before using broad `grep` globs.** Avoid rerunning successfully prepared domains unless intended.

```bash
for d in MX_1023 MX_11028; do
  test -s "$DATA_ROOT/domain_${d}/shapefiles/catchment/${d}_catchment.shp" && echo "$d catchment OK"
  test -s "$DATA_ROOT/domain_${d}/shapefiles/river_network/${d}_river_network.shp" && echo "$d river OK"
done
```

## Step 4 — Prepare source ERA5 and EM-Earth monthly forcing

The existing processing is month-task driven. The configured EM-Earth precipitation is **`prcp_corrected`**; the final SUMMA name is `pptrate` (kg m⁻² s⁻¹). ERA5 supplies the complementary meteorological variables. Source availability and Mexican geographic coverage must be checked before submitting thousands of tasks.

```bash
cd "$CWARHM_ROOT/3a_forcing/0_existing_forcing"
mkdir -p slurm_logs
CHUNK_SIZE=10
NCHUNKS=$(( (NMONTH + CHUNK_SIZE - 1) / CHUNK_SIZE ))
# Submit only after validating one basin-month and the Slurm worker's arguments:
sbatch --array=0-$((NCHUNKS-1)) \
  run_prepare_era5_array.sh "$MONTH_TASK" "$CHUNK_SIZE"
sbatch --array=0-$((NCHUNKS-1)) \
  run_prepare_emearth_array.sh "$MONTH_TASK" "$CHUNK_SIZE"
```

The original manual uses chunked arrays to reduce many short jobs. Check the current FIR QOS/partition and per-worker resource settings. Do not use node exclusions from old experiments without a current reason.

**QA:** Each eligible basin-month should produce ERA5 and EM-Earth prepared NetCDFs under `forcing/1_raw_data/`. Check units, precipitation source metadata, missing data, month lengths, and error logs. Do not assume the old 1950–2019 period until verified against controls and archive coverage.

## Step 5 — Spatial forcing remapping to distributed HRUs

Create EASYMORE weights once per basin, then remap monthly forcing using the task inventory.

```bash
cd "$CWARHM_ROOT/4b_remapping/2_forcing"
mkdir -p slurm_logs
sbatch --array=0-$((NBASIN-1))%4 \
  run_create_forcing_remapping_array.sh "$BASIN_TASK"
# After weights pass QA:
CHUNK_SIZE=10
NCHUNKS=$(( (NMONTH + CHUNK_SIZE - 1) / CHUNK_SIZE ))
sbatch --array=0-$((NCHUNKS-1)) \
  run_remap_ERA5_array.sh "$MONTH_TASK" "$CHUNK_SIZE"
sbatch --array=0-$((NCHUNKS-1)) \
  run_remap_EM_Earth_array.sh "$MONTH_TASK" "$CHUNK_SIZE"
```

**QA:** inspect weight files in `shapefiles/catchment_intersection/with_forcing/`, verify HRU/GRU IDs and finite weights, then count monthly outputs in `forcing/3_basin_averaged_data/ERA5/` and `.../EM_Earth/`. A successful Slurm exit is not a substitute for these checks.

## Step 6 — Combine forcing into monthly SUMMA files

```bash
cd "$CWARHM_ROOT/4b_remapping/2_forcing"
CHUNK_SIZE=10
NCHUNKS=$(( (NMONTH + CHUNK_SIZE - 1) / CHUNK_SIZE ))
sbatch --array=0-$((NCHUNKS-1)) \
  run_combine_forcing_array.sh "$MONTH_TASK" "$CHUNK_SIZE"
```

Expected location: `domain_MX_<ID>/forcing/4_SUMMA_input/NWAM_SUMMA_forcing_YYYYMM.nc`. Verify all seven SUMMA variables (`airpres`, `LWRadAtm`, `SWRadAtm`, `spechum`, `windspd`, `pptrate`, `airtemp`), hourly timestamps, and correct HRU count/order.

### Step 6A — Concatenate distributed forcing (UTC)

```bash
cd "$CWARHM_ROOT/3a_forcing/4_concat_summa_forcing"
mkdir -p slurm_logs
sbatch --array=0-$((NBASIN-1))%4 \
  run_concat_summa_forcing_array.sh "$BASIN_TASK"
```

Output: `forcing/5_SUMMA_input_concat/`. The reference runner may define `START_YEAR`, `END_YEAR`, and months internally; inspect them against `forcing_raw_time` **before submitting**. Verify contiguous timestamps and HRU order.

### Step 6B — Optional UTC-to-local-standard-time (LST)

**Not validated for Mexico.** The old CAMELS-SPAT workflow reads `dv_flow_obs_timezone` from `camels-spat-metadata.csv`, which is **not a valid assumed metadata source for `MX_*` basins**. Do not run the existing LST workers or create LST runtime files until a validated CAMELS-MX time-zone source or supported longitude-based policy has been established and tested. Retain UTC forcing and use the standard UTC SUMMA runtime meanwhile. Avoid treating political time zones or DST as interchangeable with fixed LST offsets.

## Step 7 — DEM, soil and MODIS rasters

Current demonstration inputs: **MERIT Hydro DEM** (not TDX elevation), shared soil classes, and MODIS land cover. TDX-Hydro supplies the basin geometry only.

```bash
cd "$CWARHM_ROOT/3b_parameters"
mkdir -p slurm_logs
sbatch --array=0-$((NBASIN-1))%4 \
  run_multibasin_parameter_data_preprocessing_array.sh "$BASIN_TASK"
```

For each basin verify:

```bash
D=MX_1023
for f in \
  "$DATA_ROOT/domain_${D}/parameters/dem/5_elevation/elevation.tif" \
  "$DATA_ROOT/domain_${D}/parameters/soilclass/2_soil_classes_domain/soil_classes.tif" \
  "$DATA_ROOT/domain_${D}/parameters/landclass/7_mode_land_class/land_classes.tif"; do
  test -s "$f" && echo "PASS $f" || echo "MISSING $f"
done
```

Also check raster CRS, bounds, NoData, resolution, and coverage over the actual Mexico basin. The shared source data and naming conventions may require later revision as datasets are selected.

## Step 8 — Map DEM/soil/land cover to distributed HRUs

```bash
cd "$CWARHM_ROOT/4b_remapping/1_topo"
mkdir -p slurm_logs
sbatch --array=0-$((NBASIN-1))%4 \
  run_multibasin_HRU_parameter_remapping_array.sh "$BASIN_TASK"
```

Verify intersection outputs under `shapefiles/catchment_intersection/with_dem/`, `with_soilgrids/`, and `with_modis/`; check no missing elevation or all-NoData soil/vegetation classes. The MERIT intersection filename in the original workflow is `catchment_with_merit_dem.shp`.

## Step 9 — Generate distributed SUMMA and mizuRoute input files

```bash
cd "$CWARHM_ROOT/5_model_input"
mkdir -p slurm_logs
sbatch --array=0-$((NBASIN-1))%4 \
  run_multibasin_model_input_generation_array.sh "$BASIN_TASK"
```

Expected under `domain_MX_<ID>/settings/SUMMA/`: `fileManager.txt`, `forcingFileList.txt`, `coldState.nc`, `trialParams.nc`, `attributes.nc`, `modelDecisions.txt`, `outputControl.txt`, parameter tables. Under `settings/mizuRoute/`: `topology.nc`, `mizuroute.control`, `param.nml.default`.

The mizuRoute topology script reads the **prepared catchment shapefile** at `shapefiles/catchment/<river_basin_shp_name>` and the prepared river network. It uses `COMID` for routing HRU and segment IDs and `area` in **m²**. With `river_basin_needs_remap | no`, the optional remapping script exits without creating a remap file. Validate that all prepared catchment COMIDs exist in network segments before assuming mapping is appropriate. Check routing outlet, connectivity, slopes, segment lengths, and `hruToSegId`.

### Step 9A — Optional LST SUMMA runtime

**Deferred** until Mexico-specific LST data and Step 6B are validated. Do not point `fileManager_LST.txt` at nonexistent or incorrectly shifted forcing. UTC model-input generation is the primary demonstration route.

## Step 10 — Final distributed model-input acceptance checks

For each basin, verify required files and NetCDF consistency. A basic file check:

```bash
while IFS= read -r control; do
  d=$(awk -F'|' '$1 ~ /^[[:space:]]*domain_name[[:space:]]*$/ {gsub(/[[:space:]]/,"",$2); print $2; exit}' "$control")
  r="$DATA_ROOT/domain_${d}"
  for f in settings/SUMMA/fileManager.txt settings/SUMMA/attributes.nc \
           settings/SUMMA/coldState.nc settings/SUMMA/trialParams.nc \
           settings/mizuRoute/topology.nc settings/mizuRoute/mizuroute.control; do
    test -s "$r/$f" || echo "MISSING: $d/$f"
  done
done < "$BASIN_TASK"
```

Verify **each** NetCDF scientifically as well as structurally: no `-999` in elevation/soil/vegetation, consistent HRU IDs and ordering across forcing, attributes, cold state and trial parameters; connected river segment IDs; valid outlet(s); no unexpected missing forcing months; consistent UTC time axis. The current manual covers **model inputs**, not validated SUMMA or mizuRoute simulation performance.

## Handoff / operating notes

1. **First priority:** complete and verify Stage 00 for the all 21 Mexican basins. Record failures individually; do not assume all pass because `MX_1023` passed.
2. Confirm source meteorological, MERIT DEM, soil, and MODIS coverage and licenses for each study region before large Slurm runs.
3. Regenerate all absolute-path task inventories on a new clone; do not overwrite modified distributed controls.
4. Run one basin-month through forcing and one basin through parameter/model-input generation before scaling.
5. Keep source TDX exports read-only. Intermediate outputs belong in `nawm_cwarhm_output/domain_MX_*/` and should not be committed to Git.
6. The original 21 source exports are located; validate each independently before bulk processing.
7. LST and other inherited CAMELS-SPAT-specific logic are **not automatically applicable to Mexico**.
8. Use the [lumped-only manual](2_CAMELS_MX_Lumpedonly_Manual.md) after distributed catchments and shared source forcing/parameter rasters are ready.

### Git and collaboration (FIR)

Before committing, inspect `git status -sb` and `git diff --stat`. Commit reproducible scripts, the corrected inventory, template, manuals and environment setup; **do not commit** virtual environments, `slurm_logs/`, large data, credentials, cached wheels, or personal absolute-path task lists. Ensure shared-data ACLs permit collaborators to read input files and write output where required.
