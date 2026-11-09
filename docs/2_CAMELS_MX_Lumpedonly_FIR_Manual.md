# CAMELS-MX — Lumped-only NAWM-CWARHM manual (FIR)

**Branch:** `CAMELS_SPAT_MX` · **Platform:** Alliance FIR · **Updated:** 30 October 2026

**Companion:** [Distributed FIR manual](1_CAMELS_MX_Distributed_Multibasin_FIR_Manual.md)

> **Current status:** All **21 distributed controls**, **21 lumped controls**, and the **21-basin / 17,640-month distributed task files** exist on FIR. The MX template and all 42 basin controls include Step 11 spatial-attribute settings. Distributed controls select `distributed`; lumped controls select `lumped`. New spatial-attribute scripts and seven updated lumped shell runners have been copied into the MX checkout. The one-HRU forcing/model-input stages and spatial-attribute processing **have not been confirmed for all 21 Mexico basins**. Treat subsequent steps as instructions to test, not completed results.

## 0. Scope, shared data and directory layout

The lumped configuration represents each Mexican basin with **one HRU and one GRU** for SUMMA. It inherits `prcp_corrected` and the other shared settings from its distributed control. Distributed products are not overwritten; lumped products are written under `domain_MX_<ID>/lumped/`. Lumped processing reuses available distributed prepared meteorological sources and parameter rasters after those pass QA. It does not independently recreate the distributed mizuRoute river network.

```text
/project/6079554/share/camels-mx/nawm_cwarhm_output/
  domain_MX_1023/
    shapefiles/             # distributed geometry
    forcing/                # distributed source forcing
    parameters/             # shared DEM, soil, MODIS products
    settings/               # distributed SUMMA/mizuRoute
    lumped/
      shapefiles/catchment/MX_1023_lumped_basin.shp
      forcing/
      shapefiles/catchment_intersection/
      settings/SUMMA/
      simulations/
```

Step 11 adds distributed and lumped attribute outputs under `attributes/` and `lumped/attributes/`, respectively.

## Pre-step — Clone and activate FIR

```bash
git clone --branch CAMELS_SPAT_MX --single-branch \
  https://github.com/Armanhd/NAWM-CWARHM.git NAWM-CWARHM-MX

cd NAWM-CWARHM-MX
source load_nwam_fir.sh

export CWARHM_ROOT="$(pwd -P)"
export CONTROL_DIR="$CWARHM_ROOT/0_control_files"
export DATA_ROOT=/project/6079554/share/camels-mx/nawm_cwarhm_output
```

For first-time FIR environment creation, use `setup_nwam_fir.sh` on a compute node (it refuses to overwrite an existing `nwam-fir` virtual environment). Verify access to project input and output directories; do not reuse ARC paths or ARC Conda instructions.

### Check copied runner paths before submission

The seven updated lumped shell runners load the FIR environment, but their copied absolute repository paths still need to point to `NAWM-CWARHM-MX` before independent MX execution.

Before submitting a runner, confirm that its script and control paths resolve within the intended MX checkout. Do not assume that copying a runner changes paths inside its contents.

The existing root `set_batch.sh` must also be inspected before sourcing it. The explicit MX batch variables below avoid selecting an unrelated batch.

FIR environment compatibility does not make the inherited CAMELS-SPAT LST logic valid for Mexico.

## Step 1 — Generate 21 lumped controls from distributed controls

First complete **Steps 1–2** in the [distributed FIR manual](1_CAMELS_MX_Distributed_Multibasin_FIR_Manual.md). Then:

```bash
cd "$CWARHM_ROOT/00_prepare_domain_shapefiles"

python 0_generate_lumped_multibasin_control_files.py \
  --task-file ../0_control_files/multibasin_preprocessing_CAMELS_MX_all.txt \
  --dry-run
```

After inspecting the 21-domain preview, run **without** `--dry-run`:

```bash
python 0_generate_lumped_multibasin_control_files.py \
  --task-file ../0_control_files/multibasin_preprocessing_CAMELS_MX_all.txt
```

Expected outputs:

```text
0_control_files/control_MX_<ID>_lumped.txt       # 21 controls
0_control_files/lumped_multibasin_preprocessing_CAMELS_MX_all.txt
```

If intentionally replacing existing lumped controls, add `--overwrite`; this should not be used casually after any manual control edits. The script preserves the distributed `domain_name`, inherits `forcing_emearth_precip | prcp_corrected`, and routes lumped geometry-dependent outputs to `domain_MX_<ID>/lumped/`.

```bash
find "$CONTROL_DIR" -maxdepth 1 -name 'control_MX_*_lumped.txt' | wc -l
wc -l "$CONTROL_DIR/lumped_multibasin_preprocessing_CAMELS_MX_all.txt"
# Expected 21 and 21 after successful generation
```

**Checkout-specific absolute paths:** The lumped task file must be regenerated when moving to another clone; do not reuse another developer's absolute control paths.

**Step 11 setting after regeneration:** The current generator inherits `attribute_processing_mode` from the distributed control. If lumped controls are regenerated, verify that their mode is set to `lumped`. Preserve their existing forcing, DEM, intersection, and SUMMA paths. The current 21 lumped controls have already been updated with this mode.

## Step 1A — Set lumped batch variables

```bash
export LUMPED_BASIN_TASK="$CONTROL_DIR/lumped_multibasin_preprocessing_CAMELS_MX_all.txt"
export NLUMPED="$(wc -l < "$LUMPED_BASIN_TASK")"

echo "NLUMPED=$NLUMPED"
# Expected: 21
```

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
nawm_cwarhm_output/domain_MX_1023/lumped/shapefiles/catchment/MX_1023_lumped_basin.shp
```

Check feature count and attributes:

```bash
python - <<'PY'
import geopandas as gpd

p = (
    "/project/6079554/share/camels-mx/nawm_cwarhm_output/"
    "domain_MX_1023/lumped/shapefiles/catchment/"
    "MX_1023_lumped_basin.shp"
)

g = gpd.read_file(p)

print(
    "Features:", len(g),
    "GRU:", g.GRU_ID.tolist(),
    "HRU:", g.HRU_ID.tolist(),
)

assert len(g) == 1
assert int(g.GRU_ID.iloc[0]) == 1
assert int(g.HRU_ID.iloc[0]) == 1
assert g.geometry.iloc[0].is_valid
assert g.HRU_area.iloc[0] > 0

print("PASS")
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

export LUMPED_MONTH_TASK="$CONTROL_DIR/lumped_month_tasks_CAMELS_MX_all.txt"
export NMONTH_LUMPED="$(wc -l < "$LUMPED_MONTH_TASK")"

head -2 "$LUMPED_MONTH_TASK"
wc -l "$LUMPED_MONTH_TASK"
```

If controls specify 1950–2019, expect `21 × 840 = 17,640` basin-month tasks. Do not assume this period without checking each control. The month tasks are **not** the distributed month tasks; they must point to `control_MX_*_lumped.txt`.

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

Expected output: `domain_MX_<ID>/lumped/forcing/5_SUMMA_input_concat/`. The updated runner retains blank `START_YM`/`END_YM` filters to concatenate all available months. Inspect the actual settings before dispatch. Verify one HRU and hourly contiguous timestamps.

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

The existing MX model-input land-cover configuration remains MODIS 2022. Adding Step 11 attributes does not change this selection.

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

The existing monthly-forcing archive runner still requires a FIR/MX compatibility review. Do not submit it unchanged. Once its repository paths, environment setup, arguments, and retention behavior have been verified, run its dry-run mode first.

Confirm TAR integrity, file counts, and retention of concatenated UTC forcing **before accepting deletion of monthly source files**.

Spatial-attribute archiving is separate and is described in Step 11F.

## Step 11 — Extract, consolidate, and validate spatial attributes

### Purpose

Generate spatial attributes for individual distributed HRUs and the corresponding lumped HRU, then consolidate the results into two final CSV files per basin.

Run after distributed and lumped catchments and SUMMA `attributes.nc` files have passed verification. Existing DEM products and accessible shared geospatial sources are also required.

Step 11 is independent of forcing preparation and does not modify existing SUMMA or mizuRoute model inputs.

### Main codes

Dataset-specific extractors are located in `3b_parameters/`.

| Code under `3c_spatial_attributes/` | Purpose |
|---|---|
| `module_registry.py` | Defines datasets, extractor scripts, and output conventions. |
| `process_basin_attributes.py` | Runs modules and consolidation for one basin. |
| `run_multibasin_attributes.py` | Selects a control from a basin task file. |
| `run_multibasin_attributes_array.sh` | Executes basin processing through Slurm arrays. |
| `inspect_source_configuration.py` | Checks configured sources and extractor interfaces. |
| `consolidate_nwam_attributes.py` | Combines module outputs into final attribute CSVs. |
| `attribute_metadata.csv` | Defines the central attribute schema, units, categories, and sources. |
| `validate_attributes.py` | Checks output structure, schema, and SUMMA HRU identifiers. |
| `run_terrain_correction.sh` | Executes terrain processing. |
| `archive_spatial_attribute_modules.py` | Optionally archives intermediate attribute outputs. |

The separate `qa_nwam_attributes.py` utility assumes CAMELS-SPAT collection paths. Use `validate_attributes.py` for the MX batch.

### Inputs

Required inputs include:

- Prepared distributed catchment shapefiles.
- `domain_<DOMAIN>/settings/SUMMA/attributes.nc`.
- `domain_<DOMAIN>/lumped/shapefiles/catchment/<DOMAIN>_lumped_basin.shp`.
- `domain_<DOMAIN>/lumped/settings/SUMMA/attributes.nc`.
- Existing MERIT Hydro DEM.
- Explicit geospatial source settings in the controls.

The supported datasets are terrain, SoilGrids, Pelletier, GLHYMPS, HydroLAKES, forest height, GLCLU2019, LGRIP30, MODIS LAI, and optional WorldClim.

The current Slurm wrapper explicitly includes WorldClim. Changing a control flag alone does not remove that command-line option.

**MX catchment naming check:** The current terrain generator requires the prepared distributed catchment filename `<DOMAIN>_distributed_basin.shp`. MX preparation may instead produce `<DOMAIN>_catchment.shp`. Confirm the expected prepared file exists before running. If necessary, adapt the terrain extractor to the actual prepared MX filename before submission; do not rename or modify original TDX source exports.

### Outputs

| Configuration | Final output |
|---|---|
| Distributed | `domain_<DOMAIN>/attributes/<DOMAIN>_attributes.csv` |
| Lumped | `domain_<DOMAIN>/lumped/attributes/<DOMAIN>_lumped_attributes.csv` |

Each CSV begins with `Category, Attribute, Unit, Source`, followed by value columns identified by HRU IDs. The distributed CSV has one column per HRU; the lumped CSV has one HRU column.

The current full schema, including WorldClim, contains 468 attribute rows. Module-specific outputs remain under `attributes/<module>/` and `lumped/attributes/<module>/` until optionally archived.

The extractors may also create clipped or derived products under `parameters/`. Original catchments, shared geospatial sources, and SUMMA files are not intentionally modified.

### 11A — Prepare a combined Step 11 batch

The main MX controls select separate `distributed` and `lumped` modes. For a combined run, create separate Step 11 control copies with mode `both`, using the distributed controls as the base.

This preserves the original controls and uses the distributed DEM for both configurations. It avoids depending on the lumped DEM paths recorded in the standard lumped controls.

Run from the MX repository root:

```bash
cd /home/armanhad/projects/rrg-mclark/armanhad/NAWM-CWARHM-MX
source load_nwam_fir.sh

export CWARHM_ROOT="$(pwd -P)"
export CONTROL_DIR="$CWARHM_ROOT/0_control_files"
export DATA_ROOT=/project/6079554/share/camels-mx/nawm_cwarhm_output

python - <<'PY'
from pathlib import Path
import re

repo = Path.cwd()
controls = repo / "0_control_files"
work = repo / "3c_spatial_attributes/reports/MX_step11"
copies = work / "controls"

sources = sorted(
    p for p in controls.glob("control_MX_*.txt")
    if re.fullmatch(r"control_MX_\d+\.txt", p.name)
)

if len(sources) != 21:
    raise SystemExit(
        f"Expected 21 distributed controls; found {len(sources)}"
    )

pattern = re.compile(
    r"(?m)^attribute_processing_mode[ \t]*\|[^\n]*$"
)

plans = []
for source in sources:
    text, count = pattern.subn(
        "attribute_processing_mode | both",
        source.read_text(),
    )
    if count != 1:
        raise SystemExit(
            f"Expected one processing-mode setting: {source}"
        )
    plans.append((copies / source.name, text))

pilot_control = copies / "control_MX_1023.txt"
if pilot_control not in [p for p, _ in plans]:
    raise SystemExit("MX_1023 pilot control missing")

copies.mkdir(parents=True, exist_ok=True)

for output, text in plans:
    output.write_text(text)

task = work / "MX_step11_tasks.txt"
task.write_text(
    "".join(f"{p.resolve()}\n" for p, _ in plans)
)

pilot_task = work / "MX_step11_pilot.txt"
pilot_task.write_text(f"{pilot_control.resolve()}\n")

print(f"Combined Step 11 controls: {len(plans)}")
print(f"Task file: {task}")
print(f"Pilot task file: {pilot_task}")
print("Original controls unchanged.")
PY

export STEP11_TASK="$CWARHM_ROOT/3c_spatial_attributes/reports/MX_step11/MX_step11_tasks.txt"
export STEP11_PILOT="$CWARHM_ROOT/3c_spatial_attributes/reports/MX_step11/MX_step11_pilot.txt"
export NSTEP11="$(wc -l < "$STEP11_TASK")"

echo "NSTEP11=$NSTEP11"
# Expected: 21
```

These control copies and absolute-path task files are local run products. Do not commit them to Git.

### 11B — Verify sources and preview one basin

```bash
cd "$CWARHM_ROOT"

STEP11_CONTROL="$CWARHM_ROOT/3c_spatial_attributes/reports/MX_step11/controls/control_MX_1023.txt"

python 3c_spatial_attributes/inspect_source_configuration.py \
  "$STEP11_CONTROL"

python 3c_spatial_attributes/run_multibasin_attributes.py \
  --task-file "$STEP11_PILOT" \
  --index 0 \
  --with-worldclim \
  --force
```

Expected source preflight result: `Preflight issues: 0`.

The second command displays the processing sequence without executing extraction. Here, `--force` ensures that commands are displayed even when intermediate outputs already exist.

The source preflight does not guarantee complete basin inputs or source coverage. Independently check the prepared shapefile naming, SUMMA files, DEM, and geographic coverage over Mexico before submitting the pilot.

### 11C — Submit one pilot basin

Submit from the **MX repository root**, because the current wrapper resolves the repository through `SLURM_SUBMIT_DIR`.

```bash
cd "$CWARHM_ROOT"
mkdir -p 3c_spatial_attributes/slurm_logs

sbatch \
  --job-name=mx_attributes_pilot \
  --array=0 \
  --output="$CWARHM_ROOT/3c_spatial_attributes/slurm_logs/attributes_%A_%a.out" \
  --error="$CWARHM_ROOT/3c_spatial_attributes/slurm_logs/attributes_%A_%a.err" \
  3c_spatial_attributes/run_multibasin_attributes_array.sh \
  "$STEP11_PILOT"
```

The pilot processes MX_1023 in both configurations. Check that it generates both final CSVs and that the selected modules and consolidation succeed.

### 11D — Submit the complete basin batch

After the pilot passes and the remaining basins meet the input requirements:

```bash
cd "$CWARHM_ROOT"

sbatch \
  --job-name=mx_spatial_attributes \
  --array=0-$((NSTEP11-1))%2 \
  --cpus-per-task=4 \
  --mem=64G \
  --time=12:00:00 \
  --output="$CWARHM_ROOT/3c_spatial_attributes/slurm_logs/attributes_%A_%a.out" \
  --error="$CWARHM_ROOT/3c_spatial_attributes/slurm_logs/attributes_%A_%a.err" \
  3c_spatial_attributes/run_multibasin_attributes_array.sh \
  "$STEP11_TASK"
```

The `%2` limit is an initial concurrency choice. Adjust memory, walltime, and concurrency using pilot measurements.

The worker may reuse existing intermediate module CSVs when they pass basic output checks. Those checks do not establish scientific validity or confirm that earlier outputs used identical source data and settings.

Monitor running jobs:

```bash
squeue -u "$USER"
```

Inspect completion:

```bash
sacct -j JOBID \
  --format=JobID,State,Elapsed,MaxRSS,ExitCode
```

Slurm logs are written under `3c_spatial_attributes/slurm_logs/`.

Each processed basin also receives:

`domain_<DOMAIN>/_workflow_log/step11_attributes/status.json`

Review individual module results and consolidation status; do not rely solely on the Slurm exit state.

### 11E — Validate the final CSV files and review coverage

Validate the pilot before scaling:

```bash
cd "$CWARHM_ROOT"

python 3c_spatial_attributes/validate_attributes.py \
  --task-file "$STEP11_PILOT" \
  --expected-rows 468 \
  --report-dir 3c_spatial_attributes/reports/MX_step11/qa_pilot
```

After the complete batch:

```bash
python 3c_spatial_attributes/validate_attributes.py \
  --task-file "$STEP11_TASK" \
  --expected-rows 468 \
  --report-dir 3c_spatial_attributes/reports/MX_step11/qa
```

The QA checks:

- Presence of distributed and lumped consolidated CSVs.
- Required metadata columns and expected attribute count.
- Consistent attribute definitions and schema across basins.
- Duplicate attribute definitions.
- Agreement between CSV HRU identifiers and SUMMA `attributes.nc`.
- Unexpected non-numeric values and missing scientific values.

Review `attribute_qa_issues.csv`, `missing_by_attribute.csv`, and the module and consolidation reports.

The expected 468 rows apply to the current full schema with WorldClim. Recheck the expected count if the schema changes.

Missing or nonfinite scientific values may remain blank or NaN. Do not interpret them automatically as zero. Review source coverage and missingness by basin and attribute before using the outputs in modelling or statistical analysis.

Structural QA does not establish complete geographic coverage or scientific validity.

### 11F — Optional intermediate spatial-attribute archiving

After both configurations pass QA and significant coverage limitations have been reviewed, preview archiving for one basin:

```bash
cd "$CWARHM_ROOT"

python 3c_spatial_attributes/archive_spatial_attribute_modules.py \
  --domains-root "$DATA_ROOT" \
  --basin MX_1023 \
  --expected-rows 468
```

The default operation is a preview. Create and verify the archives while retaining the original module directories:

```bash
python 3c_spatial_attributes/archive_spatial_attribute_modules.py \
  --domains-root "$DATA_ROOT" \
  --basin MX_1023 \
  --expected-rows 468 \
  --execute
```

For all 21 basins, omit `--basin` and use `--expected-domains 21`, provided the selected data root contains exactly those 21 domain directories.

Each basin receives separate archives:

| Configuration | Archive |
|---|---|
| Distributed | `domain_<DOMAIN>/attributes/attribute_modules.zip` |
| Lumped | `domain_<DOMAIN>/lumped/attributes/attribute_modules.zip` |

The consolidated CSVs remain directly accessible. The basin's parameter products, SUMMA files, catchment shapefiles, forcing data, and shared sources are not archived by this utility.

Original module directories are removed only when `--delete-originals` is explicitly added and both archives have passed verification.

If intermediates have been removed, restore them before reconsolidation or other processing that depends on module CSVs:

```bash
DOMAIN="$DATA_ROOT/domain_MX_1023"

unzip "$DOMAIN/attributes/attribute_modules.zip" \
  -d "$DOMAIN/attributes"

unzip "$DOMAIN/lumped/attributes/attribute_modules.zip" \
  -d "$DOMAIN/lumped/attributes"
```

The processing scripts do not automatically extract archived intermediates.

Step 11 is complete when extraction and consolidation have passed structural and identifier QA and significant source-coverage limitations have been reviewed. Archiving is optional.

## Optional compatibility utility

`extra_functions/update_lumped_coldstate_layers.py` is for controlled tests requiring the vertical-layer structure of a trusted reference `coldState.nc`. It is **not part of the normal Mexico preparation pipeline**. Do not use it unless the planned experiment specifies a reference cold state and target layer structure.

## Handoff checklist

- [ ] Branch is `CAMELS_SPAT_MX`; clone-specific absolute task paths regenerated.
- [ ] Copied runners resolve scripts and controls from the MX checkout.
- [ ] All distributed basin shapefiles used by lumped processing have passed validation.
- [ ] 21 one-HRU catchments created and area-consistency checked.
- [ ] ERA5/EM-Earth coverage and Mexico precipitation setting (`prcp_corrected`) verified.
- [ ] Lumped EASYMORE remap weights verified.
- [ ] Lumped monthly tasks and forcing completed, checked for one HRU.
- [ ] MERIT DEM/soil/MODIS one-HRU parameters populated.
- [ ] Lumped SUMMA inputs consistent and complete.
- [ ] No CAMELS-SPAT time-zone metadata was incorrectly applied to Mexico.
- [ ] Monthly-forcing archive runner reviewed for FIR/MX compatibility before use.
- [ ] Archive step used only after verifying model inputs and preserving final forcing.
- [ ] Step 11 prepared catchment naming, source paths, DEM, and SUMMA inputs checked.
- [ ] Distributed and lumped consolidated attribute CSVs generated and validated.
- [ ] Missing attribute values and source coverage over Mexico reviewed.
- [ ] Spatial-attribute archiving performed only if requested and after QA.

**Development note:** the project is a 21-basin demonstration, not a production benchmark. Future workflow updates may select different hydrography, precipitation, DEM, soils, vegetation or time-processing datasets per stage. Record such decisions in controls, inventories and this manual.