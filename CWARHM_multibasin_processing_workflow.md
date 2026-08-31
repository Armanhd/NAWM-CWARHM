# CWARHM Multibasin Processing Workflow

## General workflow for preparing multiple hydrological domains for SUMMA and mizuRoute

**Repository branch:** `NAWM-multibasin`  
**Primary tested platform:** University of Calgary ARC  
**Software environment:** Conda environment `nwam`

---

## 1. Purpose and scope

This manual describes the multibasin CWARHM preprocessing workflow used to prepare multiple hydrological domains for SUMMA and mizuRoute. The workflow is designed so that a batch of domains can be processed concurrently using Slurm arrays rather than running each basin manually.

The workflow is intended to be **domain-generic**. A new basin can be processed when it is represented in a compatible domain inventory and the associated catchment, river-network, and river-basin shapefiles provide the attributes expected by the CWARHM control file. The workflow has been tested with selected MERIT-Basins Pfaf-3 domains and selected CENTURY/CAMELS-SPAT catchments, including both single-HRU and multi-HRU domains.

> **Validation status.** The multibasin workflow has currently been developed and tested only on the University of Calgary ARC HPC system. Execution on another HPC system, workstation, or cloud environment may require changes to module loading, Slurm directives, filesystem paths, shared-data locations, and software dependencies.

> **Conda environment.** All current testing uses the `nwam` Conda environment. The workflow assumes that Python, GDAL, GeoPandas, rasterio, xarray, netCDF4, EASYMORE, and other required dependencies are available through this environment.

This manual covers preprocessing through final SUMMA and mizuRoute input verification. It does **not** cover running SUMMA or mizuRoute simulations.

The final products include:

- monthly SUMMA forcing NetCDF files;
- SUMMA `fileManager.txt`, `forcingFileList.txt`, `coldState.nc`, `trialParams.nc`, and `attributes.nc`;
- SUMMA base-setting and parameter-table files;
- mizuRoute `topology.nc`, `mizuroute.control`, and `param.nml.default`;
- domain-level DEM, soil, and land-cover products; and
- HRU-level elevation, soil-class, and land-class intersection products.

---

## 2. Workflow overview

```text
Domain inventory CSV
        +
validated control-file template
        |
        v
generate domain-specific control files
        |
        v
generate basin and domain-month task files
        |
        v
prepare domain folders, shapefiles, and forcing grids
        |
        v
prepare monthly ERA5 and EM-Earth forcing
        |
        v
create reusable EASYMORE remapping weights
        |
        v
remap ERA5 and EM-Earth forcing to HRUs
        |
        v
combine forcing into final SUMMA forcing
        |
        v
prepare DEM, soil, and MODIS domain rasters
        |
        v
map elevation, soil, and land cover to HRUs
        |
        v
generate SUMMA and mizuRoute model-input files
        |
        v
perform final consistency checks
```

The central design principle is that **control files and generated task files define the batch**. Once those task files exist, most later Slurm commands do not need to know individual basin names.

---

## 3. Repository and directory conventions

Define the main paths once at the beginning of a session.

```bash
export REPO_ROOT="/work/comphyd_lab/users/<USER>/NWAM/CWARHM_multibasin"
export DATA_ROOT="/work/comphyd_lab/users/<USER>/NWAM/NWAM_Data"
export CONTROL_DIR="${REPO_ROOT}/0_control_files"
```

On the current ARC deployment, replace `<USER>` with your ARC username. If the repository or data directory is located elsewhere, change these variables rather than editing every command in this manual.

Each model domain is expected under:

```text
${DATA_ROOT}/domain_<DOMAIN>/
```

Important subdirectories include:

```text
forcing/1_raw_data/
forcing/3_basin_averaged_data/
forcing/4_SUMMA_input/
parameters/
settings/SUMMA/
settings/mizuRoute/
shapefiles/
```

Source domain shapefiles should be treated as read-only. The workflow creates domain-specific working copies under the corresponding `domain_<DOMAIN>` directory.

---

## 4. Before starting: required inputs

For each domain, the workflow needs a compatible inventory row that identifies the source spatial data. The existing inventory format includes fields such as:

```text
domain_name
source_directory
control_file
catchment_shp_file
river_network_shp_file
river_basin_shp_file
```

The repository currently includes example inventories for MERIT Pfaf-3 and CENTURY domains. These are examples of the expected structure; they are not the only domain groups that can be used.

Before beginning a new batch, confirm that:

- each selected domain has a unique `domain_name`;
- the source catchment and river-network shapefiles exist;
- required shapefile attributes are present and numeric where expected;
- the desired forcing period is defined in `forcing_raw_time`;
- the forcing spatial extent can be derived from the catchment;
- shared ERA5 and EM-Earth archives are accessible;
- shared MERIT-Hydro, soil-class, and MODIS data are accessible; and
- the `nwam` environment is available.

---

# STEP 0 - Activate the ARC/Conda environment

Load the Conda module and activate the tested environment.

```bash
cd "$REPO_ROOT"
module load conda/base
conda activate nwam
```

Check the active software:

```bash
which python
which gdalinfo
python --version
gdalinfo --version
```

The Python executable should normally resolve to the `nwam` environment, for example:

```text
/home/<USER>/.conda/envs/nwam/bin/python
```

If `gdalinfo` or Python cannot be found, stop here and repair the environment before running Slurm jobs.

---

# STEP 1 - Select domains and generate control files

## 1.1 Choose the inventory and batch selection

Move to the domain-preparation directory:

```bash
cd "$REPO_ROOT/00_prepare_domain_shapefiles"
```

The control generator can select a subset of domains using an inventory CSV, prefix, optional starting domain, and number of domains.

Use generic batch variables:

```bash
export INVENTORY="$CONTROL_DIR/<DOMAIN_INVENTORY>.csv"
export PREFIX="<PREFIX>"
export START_DOMAIN="<START_DOMAIN>"
export LIMIT=<NUMBER_OF_DOMAINS>
export BATCH_NAME="<BATCH_NAME>"
```

Examples of `PREFIX` values used during development include `MERIT_72` and `CAN_`, but any compatible naming scheme can be used.

## 1.2 Preview the selected domains

Always preview before overwriting controls:

```bash
python 0_generate_multibasin_control_files.py \
    --csv "$INVENTORY" \
    --prefix "$PREFIX" \
    --start-domain "$START_DOMAIN" \
    --limit "$LIMIT" \
    --dry-run
```

Confirm that the printed domains are exactly the ones you intend to process. Do not rely on `--limit` alone.

## 1.3 Generate the domain controls

```bash
python 0_generate_multibasin_control_files.py \
    --csv "$INVENTORY" \
    --prefix "$PREFIX" \
    --start-domain "$START_DOMAIN" \
    --limit "$LIMIT" \
    --overwrite
```

Expected output:

```text
0_control_files/control_<DOMAIN>.txt
```

The generator preserves shared settings from the validated template while updating domain-specific fields such as domain name, source shapefile paths/names, and forcing extent.

## 1.4 Quick verification

List the generated controls:

```bash
ls -lh "$CONTROL_DIR"/control_*.txt
```

For a specific generated control:

```bash
grep -E \
"^(domain_name|root_path|forcing_raw_space|forcing_raw_time|parameter_soil_raw_path)" \
"$CONTROL_DIR/control_<DOMAIN>.txt"
```

---

# STEP 2 - Generate basin and monthly task files

The task generator converts the selected control files into:

- one **basin task file**, with one control-file path per line; and
- one **month task file**, with one domain-month task per line.

Run:

```bash
cd "$REPO_ROOT/00_prepare_domain_shapefiles"

python 0b_generate_multibasin_month_tasks.py \
    --prefix "$PREFIX" \
    --start-domain "$START_DOMAIN" \
    --limit "$LIMIT" \
    --batch-name "$BATCH_NAME"
```

Expected files:

```text
$CONTROL_DIR/multibasin_preprocessing_<BATCH_NAME>.txt
$CONTROL_DIR/month_tasks_<BATCH_NAME>.txt
```

The total number of month tasks is calculated from the `forcing_raw_time` period in the selected controls. Therefore, **do not assume a fixed number such as 840 months** unless the configured period actually spans January 1950 through December 2019.

Check:

```bash
wc -l \
    "$CONTROL_DIR/multibasin_preprocessing_${BATCH_NAME}.txt" \
    "$CONTROL_DIR/month_tasks_${BATCH_NAME}.txt"
```

---

# STEP 2A - Define reusable batch variables

Create a small session file so that later steps use the same task files consistently.

```bash
cd "$REPO_ROOT"

cat > set_batch.sh <<BATCH_EOF
export BASIN_TASK="$CONTROL_DIR/multibasin_preprocessing_${BATCH_NAME}.txt"
export MONTH_TASK="$CONTROL_DIR/month_tasks_${BATCH_NAME}.txt"
export NBASIN=\$(wc -l < "\$BASIN_TASK")
export NMONTH=\$(wc -l < "\$MONTH_TASK")
BATCH_EOF
```

Activate it:

```bash
source "$REPO_ROOT/set_batch.sh"
```

Verify:

```bash
echo "$BASIN_TASK"
echo "$MONTH_TASK"
echo "$NBASIN"
echo "$NMONTH"
```

After reconnecting to ARC, activate the Conda environment and source this file again.

---

# STEP 3 - Prepare domain shapefiles and forcing grids

One Slurm array task processes one domain.

```bash
cd "$REPO_ROOT/00_prepare_domain_shapefiles"
source "$REPO_ROOT/set_batch.sh"
mkdir -p slurm_logs

sbatch \
    --array=0-$((NBASIN-1))%4 \
    run_multibasin_preprocessing_array.sh \
    "$BASIN_TASK"
```

The `%4` is a **concurrency throttle**, not the number of CPUs assigned to each task. Adjust it according to domain size and ARC/QOS limits.

The worker runs domain shapefile preparation and forcing-grid creation. It creates working catchment and river-network files without modifying the original source datasets.

Monitor:

```bash
squeue -u "$USER"
```

After completion, check for successful completion messages:

```bash
grep -H \
"NWAM PREPROCESSING COMPLETED SUCCESSFULLY" \
slurm_logs/preprocess_*.out
```

Check non-empty error logs:

```bash
for f in slurm_logs/preprocess_*.err; do
    [ -s "$f" ] && echo "NON-EMPTY: $f"
done
```

No output from the second command is the desired result.

---

# STEP 4 - Prepare raw ERA5 and EM-Earth forcing

Each Slurm array task processes one domain-month row from `$MONTH_TASK`.

## 4A. ERA5 preparation

```bash
cd "$REPO_ROOT/3a_forcing/0_existing_forcing"
source "$REPO_ROOT/set_batch.sh"
mkdir -p slurm_logs

sbatch \
    --array=0-$((NMONTH-1))%200 \
    run_prepare_era5_array.sh \
    "$MONTH_TASK"
```

Wait for the ERA5 preparation to finish before starting the corresponding downstream remapping step.

## 4B. EM-Earth preparation

```bash
sbatch \
    --array=0-$((NMONTH-1))%200 \
    run_prepare_emearth_array.sh \
    "$MONTH_TASK"
```

The `%200` throttle was used successfully on ARC for the tested workload, but it is not a universal limit. Reduce it for large-memory domains or if the scheduler/QOS requires a smaller concurrency.

### Very large task files

If the complete Slurm array exceeds site limits, split the index range into chunks. Choose chunk boundaries based on the actual value of `$NMONTH`; do **not** copy fixed ranges from a previous batch.

To inspect the total:

```bash
echo "$NMONTH"
```

Then submit non-overlapping ranges until the final index `$((NMONTH-1))` is covered.

## 4C. Dynamic verification for all basins

```bash
while IFS= read -r CONTROL_FILE; do
    DOMAIN=$(awk -F'|' '
        /^[[:space:]]*domain_name[[:space:]]*\|/ {
            value=$2
            sub(/#.*/, "", value)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' "$CONTROL_FILE")

    ROOT="$DATA_ROOT/domain_${DOMAIN}"

    echo
    echo "===== ${DOMAIN} ====="
    echo -n "ERA5 prepared     : "
    find "$ROOT/forcing/1_raw_data/ERA5_prepared" \
        -maxdepth 1 -type f -name "ERA5_SUMMA_*.nc" | wc -l

    echo -n "EM-Earth prepared : "
    find "$ROOT/forcing/1_raw_data/EM_Earth_prepared" \
        -maxdepth 1 -type f -name "EM_Earth_SUMMA_*.nc" | wc -l
done < "$BASIN_TASK"
```

The expected count for each domain should equal the number of months implied by its control-file forcing period.

---

# STEP 5 - Remap ERA5 and EM-Earth forcing to HRUs

The remapping stage has three parts:

1. create reusable EASYMORE spatial remapping files once per basin;
2. remap all monthly ERA5 files; and
3. remap all monthly EM-Earth files.

## 5A. Create reusable remapping files

```bash
cd "$REPO_ROOT/4b_remapping/2_forcing"
source "$REPO_ROOT/set_batch.sh"
mkdir -p slurm_logs

sbatch \
    --array=0-$((NBASIN-1))%5 \
    run_create_forcing_remapping_array.sh \
    "$BASIN_TASK"
```

Verify the spatial mappings for every domain:

```bash
while IFS= read -r CONTROL_FILE; do
    DOMAIN=$(awk -F'|' '
        /^[[:space:]]*domain_name[[:space:]]*\|/ {
            value=$2
            sub(/#.*/, "", value)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' "$CONTROL_FILE")

    echo
    echo "===== ${DOMAIN} ====="

    find "$DATA_ROOT/domain_${DOMAIN}/shapefiles/catchment_intersection/with_forcing" \
        -maxdepth 2 -type f \
        \( -name "*remap*.csv" -o -name "*remap*.nc" \) \
        | sort
done < "$BASIN_TASK"
```

At minimum, confirm that the expected ERA5 and EM-Earth remapping products exist for every domain.

## 5B. Remap ERA5 months

```bash
sbatch \
    --array=0-$((NMONTH-1))%200 \
    run_remap_ERA5_array.sh \
    "$MONTH_TASK"
```

## 5C. Remap EM-Earth months

```bash
sbatch \
    --array=0-$((NMONTH-1))%200 \
    run_remap_EM_Earth_array.sh \
    "$MONTH_TASK"
```

Wait for each array to finish and verify that no unexpected `.err` output remains.

## 5D. Dynamic count verification

```bash
while IFS= read -r CONTROL_FILE; do
    DOMAIN=$(awk -F'|' '
        /^[[:space:]]*domain_name[[:space:]]*\|/ {
            value=$2
            sub(/#.*/, "", value)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' "$CONTROL_FILE")

    ROOT="$DATA_ROOT/domain_${DOMAIN}"

    echo
    echo "===== ${DOMAIN} ====="
    echo -n "ERA5 remapped     : "
    find "$ROOT/forcing/3_basin_averaged_data/ERA5" \
        -maxdepth 1 -type f -name "*.nc" | wc -l

    echo -n "EM-Earth remapped : "
    find "$ROOT/forcing/3_basin_averaged_data/EM_Earth" \
        -maxdepth 1 -type f -name "*.nc" | wc -l
done < "$BASIN_TASK"
```

For each domain, the two counts should correspond to its expected number of monthly forcing files.

---

# STEP 6 - Create final SUMMA forcing

This stage combines the remapped products as follows:

- ERA5: `airpres`, `LWRadAtm`, `SWRadAtm`, `spechum`, `windspd`;
- EM-Earth: `pptrate`, `airtemp`.

The output naming convention retained by the workflow is:

```text
NWAM_SUMMA_forcing_YYYYMM.nc
```

Although the branch is named NAWM, the existing `NWAM_SUMMA_forcing_` filename prefix is retained for compatibility with the current scripts.

Run:

```bash
cd "$REPO_ROOT/4b_remapping/2_forcing"
source "$REPO_ROOT/set_batch.sh"
mkdir -p slurm_logs

sbatch \
    --array=0-$((NMONTH-1))%200 \
    run_combine_forcing_array.sh \
    "$MONTH_TASK"
```

## Dynamic verification

```bash
while IFS= read -r CONTROL_FILE; do
    DOMAIN=$(awk -F'|' '
        /^[[:space:]]*domain_name[[:space:]]*\|/ {
            value=$2
            sub(/#.*/, "", value)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' "$CONTROL_FILE")

    FORCING="$DATA_ROOT/domain_${DOMAIN}/forcing/4_SUMMA_input"

    N=$(find "$FORCING" -maxdepth 1 -type f \
        -name "NWAM_SUMMA_forcing_*.nc" | wc -l)

    FIRST=$(find "$FORCING" -maxdepth 1 -type f \
        -name "NWAM_SUMMA_forcing_*.nc" | sort | head -1)

    LAST=$(find "$FORCING" -maxdepth 1 -type f \
        -name "NWAM_SUMMA_forcing_*.nc" | sort | tail -1)

    echo
    echo "===== ${DOMAIN} ====="
    echo "files : $N"
    echo "first : $(basename "$FIRST")"
    echo "last  : $(basename "$LAST")"
done < "$BASIN_TASK"
```

Do not hard-code `840`, `195001`, or `201912` unless those are actually the dates configured for the current batch.

---

# STEP 7 - Prepare DEM, soil, and MODIS domain rasters

The batch worker creates three main domain parameter rasters:

```text
parameters/dem/5_elevation/elevation.tif
parameters/soilclass/2_soil_classes_domain/soil_classes.tif
parameters/landclass/7_mode_land_class/land_classes.tif
```

Run:

```bash
cd "$REPO_ROOT/3b_parameters"
source "$REPO_ROOT/set_batch.sh"
mkdir -p slurm_logs

sbatch \
    --array=0-$((NBASIN-1))%4 \
    run_multibasin_parameter_data_preprocessing_array.sh \
    "$BASIN_TASK"
```

The worker sequentially handles MERIT-Hydro DEM preprocessing, soil-class extraction, and MODIS MCD12Q1 land-cover processing for each domain.

Monitor:

```bash
squeue -u "$USER"
```

If desired, inspect accounting information after completion:

```bash
sacct -j <JOB_ID> \
    --format=JobID,JobName,State,ExitCode,Elapsed,MaxRSS
```

## Dynamic verification for all basins

```bash
while IFS= read -r CONTROL_FILE; do
    DOMAIN=$(awk -F'|' '
        /^[[:space:]]*domain_name[[:space:]]*\|/ {
            value=$2
            sub(/#.*/, "", value)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' "$CONTROL_FILE")

    ROOT="$DATA_ROOT/domain_${DOMAIN}"
    echo
    echo "===== ${DOMAIN} ====="

    for f in \
        "$ROOT/parameters/dem/5_elevation/elevation.tif" \
        "$ROOT/parameters/soilclass/2_soil_classes_domain/soil_classes.tif" \
        "$ROOT/parameters/landclass/7_mode_land_class/land_classes.tif"
    do
        if [ -s "$f" ]; then
            echo "PASS: $f"
        else
            echo "FAIL: $f"
        fi
    done
done < "$BASIN_TASK"
```

There should be no `FAIL` lines.

Before deleting logs, scan for obvious failures:

```bash
grep -ilE \
"Traceback|ERROR:|FileNotFoundError|RuntimeError|FAILED|Killed|Out Of Memory" \
slurm_logs/*.out slurm_logs/*.err 2>/dev/null
```

---

# STEP 8 - Map DEM, soil, and MODIS information to HRUs

This stage creates HRU-level parameter-intersection shapefiles.

Expected outputs are normally under:

```text
shapefiles/catchment_intersection/with_dem/
shapefiles/catchment_intersection/with_soilgrids/
shapefiles/catchment_intersection/with_modis/
```

Typical fields include:

```text
elev_mean
USGS_<class>
IGBP_<class>
```

Run:

```bash
cd "$REPO_ROOT/4b_remapping/1_topo"
source "$REPO_ROOT/set_batch.sh"
mkdir -p slurm_logs

sbatch \
    --array=0-$((NBASIN-1))%4 \
    run_multibasin_HRU_parameter_remapping_array.sh \
    "$BASIN_TASK"
```

## Dynamic verification

```bash
while IFS= read -r CONTROL_FILE; do
    DOMAIN=$(awk -F'|' '
        /^[[:space:]]*domain_name[[:space:]]*\|/ {
            value=$2
            sub(/#.*/, "", value)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' "$CONTROL_FILE")

    ROOT="$DATA_ROOT/domain_${DOMAIN}"
    echo
    echo "===== ${DOMAIN} ====="

    for f in \
        "$ROOT/shapefiles/catchment_intersection/with_dem/catchment_with_merit_dem.shp" \
        "$ROOT/shapefiles/catchment_intersection/with_soilgrids/catchment_with_soilgrids.shp" \
        "$ROOT/shapefiles/catchment_intersection/with_modis/catchment_with_modis.shp"
    do
        if [ -s "$f" ]; then
            echo "PASS: $f"
        else
            echo "FAIL: $f"
        fi
    done
done < "$BASIN_TASK"
```

Then scan Step 8 logs:

```bash
grep -ilE \
"Traceback|ERROR:|FileNotFoundError|RuntimeError|FAILED|Killed|Out Of Memory" \
slurm_logs/*.out slurm_logs/*.err 2>/dev/null
```

---

# STEP 9 - Generate SUMMA and mizuRoute model-input files

The model-input runner creates all required SUMMA and mizuRoute configuration files for one domain per array task.

Run:

```bash
cd "$REPO_ROOT/5_model_input"
source "$REPO_ROOT/set_batch.sh"
mkdir -p slurm_logs

sbatch \
    --array=0-$((NBASIN-1))%4 \
    run_multibasin_model_input_generation_array.sh \
    "$BASIN_TASK"
```

The SUMMA portion performs the following sequence:

```text
copy base settings
    -> forcingFileList.txt
    -> fileManager.txt
    -> coldState.nc
    -> trialParams.nc
    -> initialize attributes.nc
    -> insert soil class
    -> insert land class
    -> insert elevation/connectivity
```

The mizuRoute portion performs:

```text
copy base settings
    -> topology.nc
    -> optional SUMMA-to-routing remapping
    -> mizuroute.control
```

The optional remapping step is controlled by:

```text
river_basin_needs_remap | yes/no
```

For `no`, the remapping file is not required. For `yes`, confirm that the current branch's optional remapping implementation is appropriate for the domain and multibasin execution mode before running at scale.

## Completion check

```bash
grep -H \
"NWAM MODEL-INPUT GENERATION COMPLETED SUCCESSFULLY" \
slurm_logs/model_input_*.out
```

Check error files:

```bash
for f in slurm_logs/model_input_*.err; do
    [ -s "$f" ] && echo "NON-EMPTY: $f"
done
```

A stale error log from an earlier failed job can remain even after a successful rerun. When this happens, inspect the job ID and corresponding `.out` file before concluding that the current run failed.

---

# STEP 10 - Final SUMMA and mizuRoute input verification

This is the final acceptance stage before model execution.

## 10.1 Verify required files for every basin

```bash
source "$REPO_ROOT/set_batch.sh"

while IFS= read -r CONTROL_FILE; do
    DOMAIN=$(awk -F'|' '
        /^[[:space:]]*domain_name[[:space:]]*\|/ {
            value=$2
            sub(/#.*/, "", value)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' "$CONTROL_FILE")

    ROOT="$DATA_ROOT/domain_${DOMAIN}"

    echo
    echo "===== ${DOMAIN} ====="

    for f in \
        "$ROOT/settings/SUMMA/fileManager.txt" \
        "$ROOT/settings/SUMMA/forcingFileList.txt" \
        "$ROOT/settings/SUMMA/coldState.nc" \
        "$ROOT/settings/SUMMA/trialParams.nc" \
        "$ROOT/settings/SUMMA/attributes.nc" \
        "$ROOT/settings/SUMMA/modelDecisions.txt" \
        "$ROOT/settings/SUMMA/outputControl.txt" \
        "$ROOT/settings/SUMMA/localParamInfo.txt" \
        "$ROOT/settings/SUMMA/basinParamInfo.txt" \
        "$ROOT/settings/SUMMA/TBL_VEGPARM.TBL" \
        "$ROOT/settings/SUMMA/TBL_SOILPARM.TBL" \
        "$ROOT/settings/SUMMA/TBL_GENPARM.TBL" \
        "$ROOT/settings/SUMMA/TBL_MPTABLE.TBL" \
        "$ROOT/settings/mizuRoute/topology.nc" \
        "$ROOT/settings/mizuRoute/mizuroute.control" \
        "$ROOT/settings/mizuRoute/param.nml.default"
    do
        if [ -s "$f" ]; then
            echo "PASS: $(basename "$f")"
        else
            echo "FAIL: $f"
        fi
    done
done < "$BASIN_TASK"
```

Expected result: **no `FAIL` lines**.

## 10.2 Verify final forcing coverage

```bash
while IFS= read -r CONTROL_FILE; do
    DOMAIN=$(awk -F'|' '
        /^[[:space:]]*domain_name[[:space:]]*\|/ {
            value=$2
            sub(/#.*/, "", value)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            print value
            exit
        }
    ' "$CONTROL_FILE")

    FORCING="$DATA_ROOT/domain_${DOMAIN}/forcing/4_SUMMA_input"

    N=$(find "$FORCING" -maxdepth 1 -type f \
        -name "NWAM_SUMMA_forcing_*.nc" | wc -l)

    FIRST=$(find "$FORCING" -maxdepth 1 -type f \
        -name "NWAM_SUMMA_forcing_*.nc" | sort | head -1)

    LAST=$(find "$FORCING" -maxdepth 1 -type f \
        -name "NWAM_SUMMA_forcing_*.nc" | sort | tail -1)

    echo
    echo "===== ${DOMAIN} ====="
    echo "files : $N"
    echo "first : $(basename "$FIRST")"
    echo "last  : $(basename "$LAST")"
done < "$BASIN_TASK"
```

Compare these dates and file counts with `forcing_raw_time` in the domain control file.

## 10.3 Inspect forcing and SUMMA attributes for one selected basin

Choose a 1-based line index from `$BASIN_TASK`:

```bash
export BASIN_INDEX=1
export CONTROL_FILE=$(sed -n "${BASIN_INDEX}p" "$BASIN_TASK")

export DOMAIN=$(awk -F'|' '
    /^[[:space:]]*domain_name[[:space:]]*\|/ {
        value=$2
        sub(/#.*/, "", value)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        print value
        exit
    }
' "$CONTROL_FILE")
```

Then run:

```bash
python - <<'PYCODE'
from pathlib import Path
import os
import numpy as np
import pandas as pd
import xarray as xr

root = Path(os.environ["DATA_ROOT"])
domain = os.environ["DOMAIN"]
domain_root = root / f"domain_{domain}"

forcing_files = sorted(
    (domain_root / "forcing/4_SUMMA_input").glob(
        "NWAM_SUMMA_forcing_*.nc"
    )
)
attributes_file = domain_root / "settings/SUMMA/attributes.nc"

if not forcing_files:
    raise SystemExit(f"No SUMMA forcing files found for {domain}")

print(f"===== {domain}: SUMMA FORCING =====")
print("Files:", len(forcing_files))
print("First:", forcing_files[0].name)
print("Last :", forcing_files[-1].name)

with xr.open_dataset(forcing_files[0]) as ds:
    t = pd.to_datetime(ds["time"].values)
    forcing_hrus = np.asarray(ds["hruId"].values).reshape(-1).astype(np.int64)
    print("First-month time:", t[0], "to", t[-1])
    if len(t) > 1:
        print("Timestep:", t[1] - t[0])
    print("HRUs:", len(forcing_hrus))
    print("Variables:", sorted(ds.data_vars))

with xr.open_dataset(forcing_files[-1]) as ds:
    t = pd.to_datetime(ds["time"].values)
    print("Final time:", t[-1])

print()
print(f"===== {domain}: SUMMA ATTRIBUTES =====")

with xr.open_dataset(attributes_file) as ds:
    attribute_hrus = np.asarray(ds["hruId"].values).reshape(-1).astype(np.int64)
    print("HRUs:", ds.sizes["hru"])
    print("HRU order matches forcing:", np.array_equal(attribute_hrus, forcing_hrus))
    print("soilTypeIndex classes:", np.unique(ds["soilTypeIndex"].values))
    print("vegTypeIndex classes:", np.unique(ds["vegTypeIndex"].values))
    print("elevation range:", float(ds["elevation"].min()), "to", float(ds["elevation"].max()))

    for name in ["soilTypeIndex", "vegTypeIndex", "elevation"]:
        print(
            f"{name} -999 count:",
            int(np.count_nonzero(ds[name].values == -999)),
        )

    print(
        "downHRUindex non-zero:",
        int(np.count_nonzero(ds["downHRUindex"].values)),
    )
PYCODE
```

Important acceptance checks are:

- forcing HRU IDs are one-dimensional;
- forcing and `attributes.nc` HRU orders match exactly;
- no `soilTypeIndex = -999` remains;
- no `vegTypeIndex = -999` remains;
- no `elevation = -999` remains; and
- elevation values are finite.

For one-HRU-per-GRU configurations or when `settings_summa_connect_HRUs = no`, `downHRUindex` may correctly be all zero.

## 10.4 Inspect mizuRoute topology

```bash
python - <<'PYCODE'
from pathlib import Path
import os
import numpy as np
import xarray as xr

root = Path(os.environ["DATA_ROOT"])
domain = os.environ["DOMAIN"]
file = root / f"domain_{domain}" / "settings/mizuRoute/topology.nc"

print(f"===== {domain}: MIZUROUTE TOPOLOGY =====")
print("File:", file)

with xr.open_dataset(file) as ds:
    seg = np.asarray(ds["segId"].values).astype(np.int64)
    down = np.asarray(ds["downSegId"].values).astype(np.int64)
    hru = np.asarray(ds["hruId"].values).astype(np.int64)
    hru_to_seg = np.asarray(ds["hruToSegId"].values).astype(np.int64)

    segment_set = set(seg.tolist())
    invalid_down = [int(x) for x in down if x != 0 and x not in segment_set]
    invalid_hru_links = [int(x) for x in hru_to_seg if x not in segment_set]

    print("Segments:", len(seg))
    print("Routing HRUs:", len(hru))
    print("Outlet segments:", seg[down == 0])
    print("Invalid downstream IDs:", invalid_down if invalid_down else "None")
    print("Invalid HRU->segment IDs:", invalid_hru_links if invalid_hru_links else "None")
    print("Slope range:", float(np.nanmin(ds["slope"].values)), "to", float(np.nanmax(ds["slope"].values)))
    print("Length range:", float(np.nanmin(ds["length"].values)), "to", float(np.nanmax(ds["length"].values)), "m")
PYCODE
```

The desired results are:

```text
Invalid downstream IDs: None
Invalid HRU->segment IDs: None
```

---

## 11. Final acceptance checklist

Before model execution, every selected domain should satisfy the following:

| Check | Acceptance criterion |
|---|---|
| Domain control | Correct domain name, paths, forcing period, and source files |
| Prepared domain shapefiles | Exists and passed Step 3 checks |
| ERA5 monthly preparation | Expected number of files for configured period |
| EM-Earth monthly preparation | Expected number of files for configured period |
| ERA5 HRU remapping | Complete and finite |
| EM-Earth HRU remapping | Complete and finite |
| Final SUMMA forcing | Complete date coverage, correct HRU ordering |
| DEM raster | Exists and readable |
| Soil raster | Exists and readable |
| Land-cover raster | Exists and readable |
| HRU elevation | `elev_mean` available and finite |
| HRU soil histogram | `USGS_<class>` fields present |
| HRU land histogram | `IGBP_<class>` fields present |
| SUMMA attributes | Soil, vegetation, elevation fully populated |
| SUMMA HRU order | Matches forcing, coldState, and trialParams |
| mizuRoute topology | Valid downstream segment IDs |
| HRU-to-segment mapping | All links reference existing routing segments |
| Required model-input files | No missing/empty required files |
| Slurm logs | Current jobs contain no unresolved errors |

Only proceed to model execution when all required checks pass.

---

## 12. Slurm concurrency and chunking guidance

Commands in this manual use throttles such as `%4`, `%5`, or `%200`. These values are **maximum simultaneous array tasks**, not CPU allocations per task.

Each worker script contains its own resource requests, for example:

```text
#SBATCH --cpus-per-task=...
#SBATCH --mem=...
#SBATCH --time=...
```

The appropriate throttle depends on:

- current ARC/QOS limits;
- memory and runtime per basin;
- size of the domain;
- number of monthly tasks;
- filesystem load; and
- other jobs owned by the user or group.

For a large `$NMONTH`, split into chunks only when necessary. The final chunk must end at:

```bash
$((NMONTH-1))
```

and chunk ranges must not overlap or leave gaps.

---

## 13. Log handling and cleanup

Do not delete Slurm logs until output files and success messages have been verified.

A useful generic scan is:

```bash
grep -ilE \
"Traceback|ERROR:|FileNotFoundError|RuntimeError|FAILED|Killed|Out Of Memory" \
slurm_logs/*.out slurm_logs/*.err 2>/dev/null
```

After successful verification, logs can be removed from the current workflow directory with:

```bash
find slurm_logs -type f \
    \( -name "*.out" -o -name "*.err" \) \
    -delete
```

Generated Slurm logs and task-list files should normally remain excluded from Git through `.gitignore`.

---

## 14. Tested configurations versus general support

The workflow is **designed** to support arbitrary compatible basin batches, but this should not be interpreted as proof that every possible domain geometry or data configuration has been validated.

Current development testing has included:

- selected MERIT Pfaf-3 domains;
- selected CENTURY/CAMELS-SPAT basins;
- one-HRU domains;
- multi-HRU domains with more than one thousand HRUs;
- ERA5 + EM-Earth monthly forcing;
- MERIT-Hydro elevation;
- soil-class raster extraction;
- MODIS MCD12Q1 land-cover processing;
- SUMMA input generation; and
- mizuRoute topology/control generation.

The current implementation has been tested only on **ARC** using the **`nwam` Conda environment**. Porting to another system should begin with a small test batch and should verify module loading, GDAL/HDF support, data paths, Slurm directives, EASYMORE behavior, and NetCDF compatibility before scaling up.

---

## 15. Main generated model-input files

| Model | File | Purpose |
|---|---|---|
| SUMMA | `fileManager.txt` | Main SUMMA run configuration and paths |
| SUMMA | `forcingFileList.txt` | Ordered monthly forcing-file list |
| SUMMA | `coldState.nc` | Initial model states and HRU IDs |
| SUMMA | `trialParams.nc` | Trial/calibration parameters by HRU |
| SUMMA | `attributes.nc` | HRU/GRU IDs, area, location, elevation, soil, vegetation, connectivity |
| SUMMA | `modelDecisions.txt` | Hydrologic process-option choices |
| SUMMA | `outputControl.txt` | Output variables requested from SUMMA |
| SUMMA | `localParamInfo.txt` | Local/HRU parameter definitions and bounds |
| SUMMA | `basinParamInfo.txt` | Basin/GRU parameter definitions |
| SUMMA | `TBL_VEGPARM.TBL` | Vegetation parameter lookup table |
| SUMMA | `TBL_SOILPARM.TBL` | Soil parameter lookup table |
| SUMMA | `TBL_GENPARM.TBL` | General land-surface parameter table |
| SUMMA | `TBL_MPTABLE.TBL` | Noah-MP parameter table used by relevant decisions |
| mizuRoute | `topology.nc` | Routing segments, downstream IDs, HRU-to-segment mapping, slope, length, area |
| mizuRoute | `param.nml.default` | Routing parameter values |
| mizuRoute | `mizuroute.control` | Main routing run configuration |

---

## 16. Recommended workflow for a new batch

For a new set of basins, the practical sequence is:

```text
1. Add/verify domains in an inventory CSV.
2. Preview the domain selection.
3. Generate domain controls.
4. Generate basin and month task files.
5. Update/source set_batch.sh.
6. Run Step 3 and verify it.
7. Run ERA5 and EM-Earth preparation and verify counts.
8. Create EASYMORE mappings.
9. Remap ERA5 and EM-Earth forcing.
10. Combine final SUMMA forcing.
11. Prepare DEM/soil/MODIS rasters.
12. Map parameter data to HRUs.
13. Generate SUMMA + mizuRoute inputs.
14. Run final Step 10 consistency checks.
15. Only then proceed to model execution.
```

For a newly supported domain type or a new computing system, begin with **one basin and one or a few months** before submitting the complete multibasin archive.

---

## 17. Notes for repository users

This manual belongs to the `NAWM-multibasin` development branch of the NAWM-CWARHM repository. Some internal filenames and completion messages still contain the historical `NWAM` label; changing those names is separate from the functional multibasin workflow and should be done carefully to avoid breaking file discovery or compatibility.

When modifying the workflow:

- keep source datasets read-only;
- avoid shared `control_active.txt` state during concurrent jobs;
- pass domain-specific control files explicitly;
- validate HRU order whenever NetCDF files are created or combined;
- use `.reshape(-1)` rather than `.squeeze()` when a one-HRU domain must remain a one-dimensional ID array;
- preserve deterministic domain/task ordering; and
- test a single small domain before scaling to a large Slurm array.

---

## 18. Validation history

The workflow documented here was generalized from a manual that was exercised on selected MERIT Pfaf-3 and CENTURY/CAMELS-SPAT domains on ARC. Those tests demonstrated successful completion of domain preprocessing, forcing preparation and remapping, final forcing generation, geospatial parameter preparation, HRU parameter mapping, SUMMA input generation, mizuRoute input generation, and final internal consistency checks.

These validation cases demonstrate the currently tested configurations; they do not imply validation on every basin, every forcing period, or every HPC platform.
