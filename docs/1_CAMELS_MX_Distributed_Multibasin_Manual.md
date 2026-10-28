# CAMELS-MX — Distributed NAWM-CWARHM multibasin manual

**Branch:** `CAMELS_SPAT_MX` · **Status:** demonstration / work in progress · **Last updated:** 28 October 2026  
**Companion:** [Lumped-only manual](2_CAMELS_MX_Lumpedonly_Manual.md) · [Repository README](../README.md)

> **Scope and validation.** This branch demonstrates the NAWM-CWARHM workflow for **21 CAMELS-MX catchments**. At present, 17 have the required TDX-Hydro CWARHM-export directories and both distributed and lumped controls; four lack those exports. Only **MX_1023 distributed Stage 00** has been run successfully and checked. All later stages below are instructions to test, **not claims of completed Mexico processing**. As input data are selected, source datasets and procedures at individual stages may be revised. Do not change core Python processing scripts solely to accommodate this demonstration; prefer control settings, inventories, and input-data preparation.

## 0. What differs from the parent NAWM-CWARHM workflow?

| Item | CAMELS-MX demonstration |
|---|---|
| Source domains | TDX-Hydro upstream delineations exported as CWARHM catchment and river-network shapefiles |
| Catchment identification | `MX_<station>` (for example `MX_1023`) |
| Topographic DEM | **MERIT Hydro DEM** (retained from existing workflow); hydrofabric delineation is **TDX-Hydro** |
| Precipitation | Hourly EM-Earth `prcp` (not `prcp_corrected`) |
| Other forcing | ERA5 inputs, subject to availability/coverage verification |
| Soil and land cover | Existing soil-class and MODIS procedures, pending Mexico validation |
| Model representations | Distributed configuration plus a separate one-HRU lumped configuration |
| Model data output root | `/work/comphyd_lab/share/Data_CAMELS_MX` |
| Code branch | `CAMELS_SPAT_MX`, not `NAWM-multibasin` |
| Prepared outputs | `domain_MX_*/` for distributed; `domain_MX_*/lumped/` for lumped |

The four unavailable exports at the present snapshot are **MX_10113, MX_12428, MX_12496, and MX_12532**. They may have earlier GPKG delineation products, but are **not ready for this CWARHM input workflow**. Recheck before adding them.

### Key configuration files

```text
0_control_files/
  CAMELS_MX_control_file_inputs.csv             # inventory of 21 candidate basins
  CAMELS_MX_control_file_inputs_available.csv   # 17 basins with available source directories
  control_CAMELS_MX_template.txt                # distributed template
  control_MX_1023.txt                           # example distributed control
  control_MX_1023_lumped.txt                    # example lumped control
  multibasin_preprocessing_CAMELS_MX.txt        # 17 absolute distributed control paths
  lumped_multibasin_preprocessing_CAMELS_MX.txt # 17 absolute lumped control paths
```

**CAUTION: absolute task-file paths.** The committed `multibasin_preprocessing_CAMELS_MX.txt` and its lumped counterpart contain paths from the original ARC checkout. A collaborator cloning elsewhere must **regenerate them** (instructions below) rather than blindly using committed paths. Control files also refer to shared ARC datasets; verify permissions.

## Pre-step — Clone and select the branch

On ARC, choose a code checkout location under your own account:

```bash
module load conda/base
conda activate nwam
mkdir -p "$HOME/NWAM"
cd "$HOME/NWAM"
git clone --branch CAMELS_SPAT_MX --single-branch \
  git@github.com:Armanhd/NAWM-CWARHM.git CWARHM_CAMELS_SPAT_MX
cd CWARHM_CAMELS_SPAT_MX
git branch --show-current
# Expected: CAMELS_SPAT_MX
export CWARHM_ROOT="$(pwd -P)"
export CONTROL_DIR="$CWARHM_ROOT/0_control_files"
export DATA_ROOT=/work/comphyd_lab/share/Data_CAMELS_MX
```

The established demonstration checkout used during setup is `/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_CAMELS_SPAT_MX`. **Do not assume your own clone is at the same location.** Do not edit the separate `CWARHM_multibasin` checkout.

Check environment and data access:

```bash
which python
python -c 'import geopandas, rasterio, netCDF4; print("Python dependencies OK")'
ls -ld "$DATA_ROOT"
ls -ld /work/comphyd_lab/share/dataset_develop/camels_mx/basin_delineation/outputs
```

## Step 1 — Confirm inventory and distributed controls

The controls have already been generated for the 17 available basins in this branch; **do not overwrite** them without reason. The source inventory is `CAMELS_MX_control_file_inputs_available.csv` and the template is `control_CAMELS_MX_template.txt`.

```bash
cd "$CWARHM_ROOT/00_prepare_domain_shapefiles"
python 0_generate_multibasin_control_files.py \
  --csv ../0_control_files/CAMELS_MX_control_file_inputs_available.csv \
  --template ../0_control_files/control_CAMELS_MX_template.txt \
  --prefix MX_ --emearth-precip prcp --dry-run
```

To generate only missing controls (existing controls remain untouched), omit `--dry-run`. Do **not** use `--overwrite` once Stage 00 has updated a basin's control: its `forcing_raw_space` and `settings_mizu_make_outlet` were calculated from prepared geometry.

Expected source mappings include `GRU_ID`, `HRU_ID`, `HRU_area`, `center_lat`, `center_lon`, network `COMID`, `NextDownID`, `slope`, source `lengthkm`, output `length_m`, routing `COMID`, `area`, `hru_to_seg`, and `river_basin_needs_remap | no`. For this configuration, `river_basin_shp_name` refers to the prepared **catchment** shapefile, not the original TDX `river_basins` file.

```bash
find "$CONTROL_DIR" -maxdepth 1 -name 'control_MX_*.txt' \
  ! -name '*backup*' ! -name '*_lumped.txt' | wc -l
# Expected: 17

grep -E '^(root_path|domain_name|river_basin_shp_name|forcing_emearth_precip)' \
  "$CONTROL_DIR/control_MX_1023.txt"
```

## Step 2 — Rebuild the distributed basin task file for this checkout

**Required after cloning elsewhere.** This recreates the local absolute-path list. It does not modify the model controls.

```bash
cd "$CWARHM_ROOT"
python - <<'PY'
import csv
from pathlib import Path
root = Path.cwd().resolve()
cdir = root / '0_control_files'
inventory = cdir / 'CAMELS_MX_control_file_inputs_available.csv'
with inventory.open(newline='') as f:
    rows = list(csv.DictReader(f))
controls = [cdir / ('control_' + r['domain_name'] + '.txt') for r in rows]
missing = [p for p in controls if not p.is_file()]
if missing:
    raise FileNotFoundError('\n'.join(map(str, missing)))
out = cdir / 'multibasin_preprocessing_CAMELS_MX.txt'
out.write_text('\n'.join(map(str, controls)) + '\n')
print('Basin controls:', len(controls), '=>', out)
PY
```

The original manual's `0b_generate_multibasin_month_tasks.py` also builds month tasks. **Check its CLI before invocation** and ensure it selects precisely the 17 controls from the *available* inventory, not all 21 or unrelated Canadian controls:

```bash
python "$CWARHM_ROOT/00_prepare_domain_shapefiles/0b_generate_multibasin_month_tasks.py" --help
```

Use the generator to produce `0_control_files/month_tasks_CAMELS_MX.txt` (or adapt the batch label to the generator's supported options). Its rows must contain: `absolute_control_path<TAB>year<TAB>month`. If needed, create it unambiguously from the existing basin task with the following safe, read-only-to-controls alternative:

```bash
cd "$CWARHM_ROOT"
python - <<'PY'
from pathlib import Path
cdir = Path('0_control_files').resolve()
def setting(p, key):
    for s in p.read_text().splitlines():
        if '|' in s and s.split('|',1)[0].strip() == key:
            return s.split('|',1)[1].split('#',1)[0].strip()
    raise KeyError((p,key))
controls = [Path(x.strip()) for x in (cdir/'multibasin_preprocessing_CAMELS_MX.txt').read_text().splitlines() if x.strip()]
rows=[]
for p in controls:
    yrs=[int(x) for x in setting(p,'forcing_raw_time').split(',')]
    if len(yrs)!=2 or yrs[1]<yrs[0]: raise ValueError((p,yrs))
    for year in range(yrs[0], yrs[1]+1):
        for month in range(1,13): rows.append(f'{p}\t{year}\t{month:02d}')
out=cdir/'month_tasks_CAMELS_MX.txt'
out.write_text('\n'.join(rows)+'\n')
print(f'{len(controls)} basins; {len(rows)} basin-month tasks; {out}')
PY
```

If the controls use 1950–2019, expect **17 × 840 = 14,280** basin-month rows. Actual task count must be calculated from `forcing_raw_time` rather than assumed. Check `head`, `tail`, and `wc -l` before HPC submissions.

## Step 2A — Establish the active batch

Set these variables **in each new shell session**; use them instead of paths hardcoded into old Canadian manuals.

```bash
cd "$CWARHM_ROOT"
export BASIN_TASK="$CONTROL_DIR/multibasin_preprocessing_CAMELS_MX.txt"
export MONTH_TASK="$CONTROL_DIR/month_tasks_CAMELS_MX.txt"
export NBASIN="$(wc -l < "$BASIN_TASK")"
export NMONTH="$(wc -l < "$MONTH_TASK")"
printf 'Basins=%s\nBasin-months=%s\n' "$NBASIN" "$NMONTH"
# Expected basin count: 17
```

Optionally save **these export lines** in a local `set_batch_CAMELS_MX.sh`; source it after reconnecting. Absolute paths in Git task files are checkout-specific; do not commit another user's paths unnecessarily.

## Step 3 — Prepare distributed domain shapefiles and forcing grids

Stage 00 processes TDX-Hydro source catchment and river network into `Data_CAMELS_MX/domain_MX_*/shapefiles/` without editing the sources. `1_prepare_river_network.py` converts `lengthkm` into metres in `length_m`; `2_prepare_catchment.py` prepares one HRU per GRU and recalculates area in square metres; `3_report_control_values.py` recalculates the forcing extent and outlet settings.

**Validated MX_1023 direct run:**

```bash
cd "$CWARHM_ROOT/00_prepare_domain_shapefiles"
bash run_prepare_domain_shapefiles.sh "$CONTROL_DIR/control_MX_1023.txt"
# Expected: DOMAIN PREPARATION COMPLETED SUCCESSFULLY
```

Observed for `MX_1023`: 193 river segments, 193 GRUs/HRUs, one natural outlet, zero self-loops, 1,580.912 km² total prepared catchment area. The reporter adjusted the forcing spatial buffer from 0.25° (control generator) to **0.05°**. This behavior should be understood before preparing forcing.

For the remaining basins, use the existing Stage 00 Slurm wrapper **after confirming it resolves scripts from this checkout**:

```bash
cd "$CWARHM_ROOT/00_prepare_domain_shapefiles"
mkdir -p slurm_logs
sbatch --array=0-$((NBASIN-1))%4 \
  run_multibasin_preprocessing_array.sh "$BASIN_TASK"
squeue -u "$USER"
```

Check for the worker's `DOMAIN PREPARATION COMPLETED SUCCESSFULLY` message and inspect errors. The array runner may additionally create forcing grids. **Confirm runner requirements and log names on ARC before using broad `grep` globs.** Avoid rerunning successfully prepared domains unless intended.

```bash
for d in MX_1023 MX_11028; do
  test -s "$DATA_ROOT/domain_${d}/shapefiles/catchment/${d}_catchment.shp" && echo "$d catchment OK"
  test -s "$DATA_ROOT/domain_${d}/shapefiles/river_network/${d}_river_network.shp" && echo "$d river OK"
done
```

## Step 4 — Prepare source ERA5 and EM-Earth monthly forcing

The existing processing is month-task driven. The configured EM-Earth precipitation is **`prcp`**; the final SUMMA name is `pptrate` (kg m⁻² s⁻¹). ERA5 supplies the complementary meteorological variables. Source availability and Mexican geographic coverage must be checked before submitting thousands of tasks.

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

The original manual uses chunked arrays to reduce many short jobs. Check the current ARC QOS/partition and per-worker resource settings. Do not use node exclusions from old experiments without a current reason.

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

1. **First priority:** complete and verify Stage 00 for the other 16 available Mexican basins. Record failures individually; do not assume all pass because `MX_1023` passed.
2. Confirm source meteorological, MERIT DEM, soil, and MODIS coverage and licenses for each study region before large Slurm runs.
3. Regenerate all absolute-path task inventories on a new clone; do not overwrite modified distributed controls.
4. Run one basin-month through forcing and one basin through parameter/model-input generation before scaling.
5. Keep source TDX exports read-only. Intermediate outputs belong in `Data_CAMELS_MX/domain_MX_*/` and should not be committed to Git.
6. The original four missing basin exports can be added later; regenerate filtered inventory and new controls/task files once available.
7. LST and other inherited CAMELS-SPAT-specific logic are **not automatically applicable to Mexico**.
8. Use the [lumped-only manual](2_CAMELS_MX_Lumpedonly_Manual.md) after distributed catchments and shared source forcing/parameter rasters are ready.

### Git and collaboration

```bash
cd "$CWARHM_ROOT"
git branch --show-current
git status -sb
# To get branch updates before additional local changes:
git pull --ff-only origin CAMELS_SPAT_MX
```

The successful setup commit for the 17 controls and Stage 00 runner was `6967900`; subsequent documentation updates may add newer commits. The repository's `README.md` explains why this branch is a **demonstration** and why individual stage datasets/methods may change.
