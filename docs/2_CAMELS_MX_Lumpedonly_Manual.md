# CAMELS-MX — Lumped-only NAWM-CWARHM manual

**Branch:** `CAMELS_SPAT_MX` · **Status:** demonstration / work in progress · **Last updated:** 28 October 2026  
**Companion:** [Distributed multibasin manual](1_CAMELS_MX_Distributed_Multibasin_Manual.md) · [Repository README](../README.md)

> **Important:** Lumped controls exist for **17 available Mexican basins**, but the actual one-HRU catchment/forcing/model-input pipeline has **not yet been validated on CAMELS-MX**. This is a continuation of the original lumped workflow, adapted to the new Mexico inventory. Four of 21 demonstration basins have no CWARHM TDX-Hydro exports yet. Data sources and individual stages will be revised as the project develops. Do not alter core Python codes unless later validation shows a necessary change; first try input and control-file adjustments.

## Scope and dependencies

The lumped setup represents **one basin as one SUMMA HRU and one GRU**. It is primarily **SUMMA-only**; the distributed mizuRoute river network is **not rebuilt** here. Distributed and lumped products are separate:

```text
/work/comphyd_lab/share/Data_CAMELS_MX/
  domain_MX_1023/
    shapefiles/      # distributed, TDX-Hydro-derived working geometry
    forcing/         # distributed/raw and prepared forcing
    parameters/      # MERIT Hydro DEM, soil, MODIS products
    settings/        # distributed SUMMA and mizuRoute
    lumped/
      shapefiles/catchment/MX_1023_lumped_basin.shp
      forcing/
      shapefiles/catchment_intersection/
      settings/SUMMA/
      simulations/
```

The lumped processing **reuses distributed prepared ERA5/EM-Earth source forcing** and available DEM/soil/land-cover rasters where documented. It does **not** independently fetch these shared sources. Forcing precipitation selection is inherited from the distributed controls (`prcp`).

### Current demonstration

- **21** listed candidate CAMELS-MX basins; **17** available source shapefile directories and distributed+lumped controls.
- Missing exports: `MX_10113`, `MX_12428`, `MX_12496`, `MX_12532`.
- **Only `MX_1023` distributed Stage 00** has been validated, not lumped domain generation.
- The lumped-control generator's **17-basin dry-run passed**, and all **17 lumped control files were created and committed**.
- MERIT Hydro supplies elevation; TDX-Hydro supplies basin/river delineation. Source forcing is ERA5 plus EM-Earth `prcp` (subject to per-region availability checks).

## Pre-step — Clone and activate

For a new ARC user:

```bash
module load conda/base
conda activate nwam
mkdir -p "$HOME/NWAM"
cd "$HOME/NWAM"
git clone --branch CAMELS_SPAT_MX --single-branch \
  git@github.com:Armanhd/NAWM-CWARHM.git CWARHM_CAMELS_SPAT_MX
cd CWARHM_CAMELS_SPAT_MX
git branch --show-current
export CWARHM_ROOT="$(pwd -P)"
export CONTROL_DIR="$CWARHM_ROOT/0_control_files"
export DATA_ROOT=/work/comphyd_lab/share/Data_CAMELS_MX
```

The established setup checkout path was `/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_CAMELS_SPAT_MX`; collaborators should **use their own checkout**. Check the distributed manual's pre-step for environment, filesystem permissions, and source-data checks.

## Step 1 — Generate or verify lumped controls

The committed lumped controls were derived from the distributed task file by:

```bash
cd "$CWARHM_ROOT"
python 00_prepare_domain_shapefiles/0_generate_lumped_multibasin_control_files.py \
  --task-file 0_control_files/multibasin_preprocessing_CAMELS_MX.txt \
  --dry-run
```

Then without `--dry-run` to create only missing controls. **Do not pass `--overwrite`** unless regenerating intentionally after backing up any adjusted controls. The generator creates:

```text
0_control_files/control_MX_<ID>_lumped.txt
0_control_files/lumped_multibasin_preprocessing_CAMELS_MX.txt
```

It uses the distributed control as its template (no separate lumped template is required), retains precipitation selection, and assigns lumped output paths under `domain_MX_<ID>/lumped/`.

```bash
find "$CONTROL_DIR" -maxdepth 1 -name 'control_MX_*_lumped.txt' | wc -l
# Expected: 17
```

**After cloning into a different directory:** the committed lumped task file contains absolute paths to the original checkout. Rebuild it with local paths **without overwriting the 17 controls**:

```bash
cd "$CWARHM_ROOT"
python - <<'PY'
import csv
from pathlib import Path
cdir = Path('0_control_files').resolve()
with (cdir/'CAMELS_MX_control_file_inputs_available.csv').open(newline='') as f:
    rows=list(csv.DictReader(f))
files=[cdir/f"control_{r['domain_name']}_lumped.txt" for r in rows]
missing=[x for x in files if not x.exists()]
if missing: raise FileNotFoundError('\n'.join(map(str,missing)))
out=cdir/'lumped_multibasin_preprocessing_CAMELS_MX.txt'
out.write_text('\n'.join(map(str,files))+'\n')
print('Lumped controls:',len(files),'file:',out)
PY
```

## Step 1A — Establish shell batch variables

```bash
export BASIN_TASK="$CONTROL_DIR/multibasin_preprocessing_CAMELS_MX.txt"
export LUMPED_BASIN_TASK="$CONTROL_DIR/lumped_multibasin_preprocessing_CAMELS_MX.txt"
export NLUMPED="$(wc -l < "$LUMPED_BASIN_TASK")"
echo "$NLUMPED" # 17
```

Rebuild `BASIN_TASK` as described in the distributed manual if you cloned to a new path. Redefine these environment variables on reconnecting.

## Steps 2–3 — Create one-HRU catchments

The code generates **exactly one HRU and one GRU**, preserving original distributed shapefiles. Run only after confirming source geometry and distributed control mapping are valid.

```bash
cd "$CWARHM_ROOT/00_prepare_domain_shapefiles"
mkdir -p slurm_logs
sbatch --array=0-$((NLUMPED-1))%4 \
  run_prepare_lumped_catchments_array.sh "$LUMPED_BASIN_TASK"
squeue -u "$USER"
```

Expected shapefile for basin `MX_1023`:

```text
Data_CAMELS_MX/domain_MX_1023/lumped/shapefiles/catchment/MX_1023_lumped_basin.shp
```

Check feature count and attributes:

```bash
python - <<'PY'
import geopandas as gpd
p='/work/comphyd_lab/share/Data_CAMELS_MX/domain_MX_1023/lumped/shapefiles/catchment/MX_1023_lumped_basin.shp'
g=gpd.read_file(p)
print('Features:',len(g),'GRU:',g.GRU_ID.tolist(),'HRU:',g.HRU_ID.tolist())
assert len(g)==1 and int(g.GRU_ID.iloc[0])==1 and int(g.HRU_ID.iloc[0])==1
assert g.geometry.iloc[0].is_valid and g.HRU_area.iloc[0]>0
print('PASS')
PY
```

Also compare its total area against the prepared distributed catchment area. For `MX_1023`, the previously measured distributed total was about 1,580.912 km². Some aggregation differences may warrant investigation.

## Step 4 — Reuse prepared source ERA5 and EM-Earth

**Do not rerun source preparation just for lumped HRUs.** Reuse the distributed source grids and prepared monthly ERA5/EM-Earth under `domain_MX_<ID>/forcing/1_raw_data/`, after confirming coverage, time and units. These have **not been validated for all Mexico sites**.

## Step 4 (weights) — Create lumped forcing remapping files

```bash
cd "$CWARHM_ROOT/4b_remapping/2_forcing"
mkdir -p slurm_logs
sbatch --array=0-$((NLUMPED-1))%4 \
  run_create_lumped_forcing_remapping_array.sh "$LUMPED_BASIN_TASK"
```

Expect EASYMORE weights under `lumped/shapefiles/catchment_intersection/with_forcing/ERA5/` and `.../EM_Earth/`. Check that both are present and that the output target has one HRU.

## Step 4A — Generate lumped month tasks

The generator accepts `--task-file`; it derives the dates from `forcing_raw_time` in each lumped control:

```bash
cd "$CWARHM_ROOT/00_prepare_domain_shapefiles"
python 0b_generate_lumped_month_tasks.py \
  --task-file "$LUMPED_BASIN_TASK" --dry-run
python 0b_generate_lumped_month_tasks.py \
  --task-file "$LUMPED_BASIN_TASK"
export LUMPED_MONTH_TASK="$CONTROL_DIR/lumped_month_tasks_CAMELS_MX.txt"
export NMONTH_LUMPED="$(wc -l < "$LUMPED_MONTH_TASK")"
head -2 "$LUMPED_MONTH_TASK"
wc -l "$LUMPED_MONTH_TASK"
```

If controls specify 1950–2019, expect `17 × 840 = 14,280` basin-month tasks. Do not assume this period without checking each control. The month tasks are **not** the distributed month tasks; they must point to `control_MX_*_lumped.txt`.

## Step 5 — Remap monthly forcing to one HRU

After Step 4 weights and shared source monthly forcing have passed QA:

```bash
cd "$CWARHM_ROOT/4b_remapping/2_forcing"
CHUNK_SIZE=10
NCHUNKS=$(( (NMONTH_LUMPED + CHUNK_SIZE - 1) / CHUNK_SIZE ))
mkdir -p slurm_logs
sbatch --array=0-$((NCHUNKS-1)) \
  run_remap_ERA5_lumped_array.sh "$LUMPED_MONTH_TASK" "$CHUNK_SIZE"
sbatch --array=0-$((NCHUNKS-1)) \
  run_remap_EM_Earth_lumped_array.sh "$LUMPED_MONTH_TASK" "$CHUNK_SIZE"
```

Check monthly output directories `lumped/forcing/3_basin_averaged_data/ERA5/` and `.../EM_Earth/`; validate one HRU, `hruId = 1`, complete coverage and numerical validity.

## Step 6 — Combine final one-HRU SUMMA forcing

```bash
cd "$CWARHM_ROOT/4b_remapping/2_forcing"
CHUNK_SIZE=10
NCHUNKS=$(( (NMONTH_LUMPED + CHUNK_SIZE - 1) / CHUNK_SIZE ))
sbatch --array=0-$((NCHUNKS-1)) \
  run_combine_forcing_lumped_array.sh "$LUMPED_MONTH_TASK" "$CHUNK_SIZE"
```

Expected `domain_MX_<ID>/lumped/forcing/4_SUMMA_input/NWAM_SUMMA_forcing_YYYYMM.nc`. Each file must contain one HRU and seven variables: `airpres`, `LWRadAtm`, `SWRadAtm`, `spechum`, `windspd`, `pptrate`, `airtemp`.

### Step 6A — Concatenate one-HRU monthly forcing (UTC)

```bash
cd "$CWARHM_ROOT/3a_forcing/4_concat_summa_forcing"
mkdir -p slurm_logs
sbatch --array=0-$((NLUMPED-1))%4 \
  run_concat_summa_forcing_one_hru_array.sh "$LUMPED_BASIN_TASK"
```

Expected output: `domain_MX_<ID>/lumped/forcing/5_SUMMA_input_concat/`. The older manual indicates this runner can concatenate all available months via blank `START_YM`/`END_YM`; inspect actual runner settings before dispatch. Verify one HRU and hourly contiguous timestamps.

### Step 6B — Optional one-HRU UTC-to-LST conversion: **deferred**

Do **not** run `run_convert_concat_utc_to_lst_lumped_array.sh` unchanged for Mexico. The source workflow relies on `camels-spat-metadata.csv` and `dv_flow_obs_timezone`. Mexico-specific time zones and their mapping to `MX_*` IDs have not been established. Continue using **UTC** forcing until a Mexico-appropriate input file and conversion rule have been validated. Likewise defer LST-specific SUMMA runtime creation.

## Step 7 — Extract MERIT DEM, soil, and MODIS properties for one HRU

Reuse prepared distributed rasters (MERIT Hydro `elevation.tif`, soil `soil_classes.tif`, MODIS `land_classes.tif`); only re-map to the lumped catchment:

```bash
cd "$CWARHM_ROOT/4b_remapping/1_topo"
mkdir -p slurm_logs
sbatch --array=0-$((NLUMPED-1))%4 \
  run_lumped_HRU_parameter_remapping_array.sh "$LUMPED_BASIN_TASK"
```

Expected intersection outputs under `lumped/shapefiles/catchment_intersection/with_dem`, `with_soilgrids`, and `with_modis`. Check valid elevation, soil, and vegetation for the single HRU; do not accept all-NoData results.

## Step 8 — Generate one-HRU SUMMA inputs

```bash
cd "$CWARHM_ROOT/5_model_input"
mkdir -p slurm_logs
sbatch --array=0-$((NLUMPED-1))%4 \
  run_lumped_SUMMA_model_input_generation_array.sh "$LUMPED_BASIN_TASK"
```

Expected under `lumped/settings/SUMMA/`:

```text
fileManager.txt  forcingFileList.txt  coldState.nc  trialParams.nc
attributes.nc   modelDecisions.txt   outputControl.txt
localParamInfo.txt  basinParamInfo.txt  TBL_*.TBL
```

QA: `HRUs=1`, `GRUs=1`, `hruId=1`, `gruId=1`, `hru2gruId=1`, `downHRUindex=0`; soil, vegetation and elevation are populated. Do not generate or replace the distributed `settings/mizuRoute/topology.nc` here.

### Step 8A — Optional LST runtime: **deferred**

Use only when Step 6B is validated and Mexico-specific LST forcing exists. Otherwise `fileManager.txt` and `forcingFileList.txt` point to regular UTC forcing.

## Step 9 — Final one-HRU acceptance checks

```bash
while IFS= read -r control; do
  d=$(awk -F'|' '$1 ~ /^[[:space:]]*domain_name[[:space:]]*$/ {gsub(/[[:space:]]/,"",$2);print $2;exit}' "$control")
  r="$DATA_ROOT/domain_${d}/lumped"
  for f in settings/SUMMA/fileManager.txt settings/SUMMA/forcingFileList.txt \
           settings/SUMMA/coldState.nc settings/SUMMA/trialParams.nc \
           settings/SUMMA/attributes.nc; do
    test -s "$r/$f" || echo "MISSING: $d/$f"
  done
done < "$LUMPED_BASIN_TASK"
```

Also verify forcing `hruId` matches attributes/coldState/trialParams, model inputs contain no sentinel soil/vegetation/elevation values, and time coordinates are contiguous. LST checks are **not required** for a valid UTC-only demonstration.

## Step 10 — Optional post-processing archive (only after full QA)

The existing archival workflow packages selected distributed and lumped monthly NetCDF intermediates as `monthly_netcdf.tar` and logs as `workflow_logs.zip`, while preserving concatenated UTC/LST outputs. **This can remove original monthly files** after verification and should never be used during active debugging.

Always run dry-run first, and only after forcing/model inputs have been checked:

```bash
cd "$CWARHM_ROOT/3a_forcing/6_archive_monthly_forcing"
mkdir -p slurm_logs
sbatch --array=0-$((NLUMPED-1))%4 \
  run_archive_monthly_forcing_array.sh "$LUMPED_BASIN_TASK" --dry-run
```

After reviewing all dry-run logs, the corresponding actual command omits `--dry-run`. Confirm TAR integrity, file counts, and retention of concatenated UTC forcing **before accepting deletion of monthly source files**.

## Optional compatibility utility

`extra_functions/update_lumped_coldstate_layers.py` is for controlled tests requiring the vertical-layer structure of a trusted reference `coldState.nc`. It is **not part of the normal Mexico preparation pipeline**. Do not use it unless the planned experiment specifies a reference cold state and target layer structure.

## Handoff checklist

- [ ] Branch is `CAMELS_SPAT_MX`; clone-specific absolute task paths regenerated.
- [ ] All distributed basin shapefiles used by lumped processing have passed validation.
- [ ] 17 one-HRU catchments created and area-consistency checked.
- [ ] ERA5/EM-Earth coverage and Mexico precipitation setting (`prcp`) verified.
- [ ] Lumped EASYMORE remap weights verified.
- [ ] Lumped monthly tasks and forcing completed, checked for one HRU.
- [ ] MERIT DEM/soil/MODIS one-HRU parameters populated.
- [ ] Lumped SUMMA inputs consistent and complete.
- [ ] No CAMELS-SPAT time-zone metadata was incorrectly applied to Mexico.
- [ ] Archive step used only after verifying model inputs and preserving final forcing.

**Development note:** the project is a 21-basin demonstration, not a production benchmark. Future workflow updates may select different hydrography, precipitation, DEM, soils, vegetation or time-processing datasets per stage. Record such decisions in controls, inventories and this manual.
