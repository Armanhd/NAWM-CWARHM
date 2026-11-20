# CAMELS-MX preprocessing on Alliance Fir - code change record

November 2026  
Repository: `Armanhd/NAWM-CWARHM`  
Branch: `CAMELS_SPAT_MX`
Reproduced by: Xiajing (Dorothy) Lin

## Purpose and review basis

I ran the CAMELS-MX preprocessing workflow on Alliance Fir and made changes needed for the available software, forcing files and output directories. This document records the actual changes visible in the working-tree patches.

The recorded `git diff` contains **16 modified scripts, 42 modified basin control files, and the removal of one template from its old location** (59 tracked changes in total). The template exists as an untracked file under `0_control_files/templates/`; This move will treated as a rename only once the new location is staged.

Each diff below is reproduced from the saved Fir terminal output. Lines starting with `-` were removed and lines starting with `+` were added. Unchanged nearby lines are shown for context. The full Git diff remains the authoritative record at PR review time.

## Some notes

- Moving `control_CAMELS_MX_template.txt` into `0_control_files/templates/` resolved the duplicate distributed control for `MX_1023`; the task generator then identified 21 basins and 17,640 basin-month tasks.
- Python 3.12.4 and GDAL 3.9.1.
- In the recorded inventory for `MX_1023`, `MX_10113` and `MX_30181`, ERA5 and EM-Earth each had 840 monthly prepared files for 1950–2019.
- The inspected EM-Earth January 1950 file had missing precipitation values in the first seven hours. 

## 1. Changes in processing scripts — complete working-tree diffs

### 1.1 `00_prepare_domain_shapefiles/run_multibasin_preprocessing_array.sh`

**Fir launch path and Python environment.** Switch the repository root and Python invocation to the tested Fir installation. The commented legacy commands are still present and should be cleaned up before merge. This is execution setup, not a change to the domain processing method.

```diff
diff --git a/00_prepare_domain_shapefiles/run_multibasin_preprocessing_array.sh b/00_prepare_domain_shapefiles/run_multibasin_preprocessing_array.sh
index be231dd..dd85091 100755
--- a/00_prepare_domain_shapefiles/run_multibasin_preprocessing_array.sh
+++ b/00_prepare_domain_shapefiles/run_multibasin_preprocessing_array.sh
@@ -65,7 +65,8 @@ set -euo pipefail
 # PATHS
 # ============================================================
-CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+#CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+CWARHM="/project/6102189/dorolin/Github/NAWM-CWARHM-MX/"
 PREP_DIR="${CWARHM}/00_prepare_domain_shapefiles"
@@ -249,10 +250,13 @@ done
 # ENVIRONMENT / LOG DIRECTORY
 # ============================================================
-module load conda/base
+#module load conda/base
+#mkdir -p "${PREP_DIR}/slurm_logs"
+source /project/6102189/dorolin/Github/NAWM-CWARHM-MX/load_nwam_fir.sh
+which python
+python --version
-mkdir -p "${PREP_DIR}/slurm_logs"
 # ============================================================
@@ -328,8 +332,8 @@ echo
 cd "${FORCING_PREP_DIR}"
-conda run --no-capture-output -n nwam \
-    python "${GRID_SCRIPT}" \
+#conda run --no-capture-output -n nwam \
+python "${GRID_SCRIPT}" \
     "${CONTROL_FILE}"
@@ -456,4 +460,4 @@ echo "Next workflow stage:"
 echo "  Prepare monthly ERA5 and EM-Earth forcing files."
 echo
 echo "No control_active.txt was used or modified."
-echo
\ No newline at end of file
+echo
```

### 1.2 `00_prepare_domain_shapefiles/run_prepare_domain_shapefiles.sh`

**Domain shapefile worker environment.** Replace the Conda calls for river-network, catchment and reporting workers with the Fir Python environment. The processing sequence is unchanged; checkout-specific paths need review.

```diff
diff --git a/00_prepare_domain_shapefiles/run_prepare_domain_shapefiles.sh b/00_prepare_domain_shapefiles/run_prepare_domain_shapefiles.sh
index 612d5c7..175dbc5 100755
--- a/00_prepare_domain_shapefiles/run_prepare_domain_shapefiles.sh
+++ b/00_prepare_domain_shapefiles/run_prepare_domain_shapefiles.sh
@@ -141,10 +141,11 @@ fi
 # ENVIRONMENT
 # ============================================================
-module load conda/base
-
-
-cd "${SCRIPT_DIR}"
+#module load conda/base
+#cd "${SCRIPT_DIR}"
+source /project/6102189/dorolin/Github/NAWM-CWARHM-MX/load_nwam_fir.sh
+which python
+python --version
 # ============================================================
@@ -175,8 +176,8 @@ echo "----------------------------------------------------------------------"
 echo
-conda run --no-capture-output -n nwam \
-    python "${RIVER_SCRIPT}" \
+#conda run --no-capture-output -n nwam \
+python "${RIVER_SCRIPT}" \
     "${CONTROL_FILE}"
@@ -196,8 +197,8 @@ echo "----------------------------------------------------------------------"
 echo
-conda run --no-capture-output -n nwam \
-    python "${CATCHMENT_SCRIPT}" \
+#conda run --no-capture-output -n nwam \
+python "${CATCHMENT_SCRIPT}" \
     "${CONTROL_FILE}"
@@ -218,7 +219,7 @@ echo
 REPORT_OUTPUT=$(
-    conda run --no-capture-output -n nwam \
+    #conda run --no-capture-output -n nwam \
         python "${REPORT_SCRIPT}" \
         "${CONTROL_FILE}"
 )
@@ -271,4 +272,4 @@ echo "Domain       : ${DOMAIN}"
 echo "Control file : ${CONTROL_FILE}"
 echo "End time     : $(date)"
 echo
-echo "No control_active.txt was used or modified."
\ No newline at end of file
+echo "No control_active.txt was used or modified."
```

### 1.3 `3a_forcing/0_existing_forcing/run_prepare_emearth_array.sh`

**EM-Earth monthly preparation job.** Use Fir environment and checkout. Change Slurm memory from 4G to 64G and walltime from 8h to 2h in the test. These are runtime requests and have not been established as optimal. No archive-gap repair code appears in this file diff.

```diff
diff --git a/3a_forcing/0_existing_forcing/run_prepare_emearth_array.sh b/3a_forcing/0_existing_forcing/run_prepare_emearth_array.sh
index f4500d4..5a47d40 100755
--- a/3a_forcing/0_existing_forcing/run_prepare_emearth_array.sh
+++ b/3a_forcing/0_existing_forcing/run_prepare_emearth_array.sh
@@ -1,7 +1,7 @@
 #!/bin/bash
 #SBATCH --job-name=emearth_prep
-#SBATCH --time=08:00:00
-#SBATCH --mem=4G
+#SBATCH --time=02:00:00
+#SBATCH --mem=64G
 #SBATCH --cpus-per-task=1
 #SBATCH --output=slurm_logs/emearth_prep_%A_%a.out
 #SBATCH --error=slurm_logs/emearth_prep_%A_%a.err
@@ -46,7 +46,8 @@ set -euo pipefail
 # PATHS
 # ============================================================
-CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+#CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+CWARHM="/project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/"
 WORKDIR="${CWARHM}/3a_forcing/0_existing_forcing"
@@ -158,10 +159,12 @@ TASK_COUNT=$((END_INDEX - START_INDEX + 1))
 # ENVIRONMENT
 # ============================================================
-module load conda/base
-
-cd "${WORKDIR}"
+#module load conda/base
+#cd "${WORKDIR}"
+source /project/6102189/dorolin/Github/NAWM-CWARHM-MX/load_nwam_fir.sh
+which python
+python --version
 # ============================================================
 # REPORT
@@ -344,7 +347,7 @@ for TASK_INDEX in $(seq "${START_INDEX}" "${END_INDEX}"); do
     # RUN EXISTING PYTHON WORKER
     # --------------------------------------------------------
-    if conda run --no-capture-output -n nwam \
+    if #conda run --no-capture-output -n nwam \
         python "${PYTHON_SCRIPT}" \
         "${CONTROL_FILE}" \
         "${YEAR}" \
@@ -394,4 +397,4 @@ if [ "${FAILED}" -gt 0 ]; then
     exit 1
-fi
\ No newline at end of file
+fi
```

### 1.4 `3a_forcing/0_existing_forcing/run_prepare_era5_array.sh`

**ERA5 monthly preparation job.** Use Fir environment and checkout instead of original Conda launch. Existing forcing extraction logic remains in its Python worker.

```diff
diff --git a/3a_forcing/0_existing_forcing/run_prepare_era5_array.sh b/3a_forcing/0_existing_forcing/run_prepare_era5_array.sh
index 3246fcf..979c21e 100755
--- a/3a_forcing/0_existing_forcing/run_prepare_era5_array.sh
+++ b/3a_forcing/0_existing_forcing/run_prepare_era5_array.sh
@@ -46,7 +46,8 @@ set -euo pipefail
 # PATHS
 # ============================================================
-CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+#CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+CWARHM="/project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/"
 WORKDIR="${CWARHM}/3a_forcing/0_existing_forcing"
@@ -165,9 +166,11 @@ TASK_COUNT=$((END_INDEX - START_INDEX + 1))
 # ENVIRONMENT
 # ============================================================
-module load conda/base
-
-cd "${WORKDIR}"
+#module load conda/base
+#cd "${WORKDIR}"
+source /project/6102189/dorolin/Github/NAWM-CWARHM-MX/load_nwam_fir.sh
+which python
+python --version
 # ============================================================
@@ -342,7 +345,7 @@ for TASK_INDEX in $(seq "${START_INDEX}" "${END_INDEX}"); do
     # RUN EXISTING PYTHON WORKER
     # --------------------------------------------------------
-    if conda run --no-capture-output -n nwam \
+    if #conda run --no-capture-output -n nwam \
         python "${PYTHON_SCRIPT}" \
         "${CONTROL_FILE}" \
         "${YEAR}" \
@@ -389,4 +392,4 @@ echo
 if [ "${FAILED}" -gt 0 ]; then
     echo "ERROR: ${FAILED} task(s) failed in this chunk."
     exit 1
-fi
\ No newline at end of file
+fi
```

### 1.5 `3a_forcing/4_concat_summa_forcing/run_concat_summa_forcing_array.sh`

**Monthly forcing concatenation.** Replace Conda setup and old absolute script directory with Fir paths. The node exclusion directive is also commented out; the effect on scheduling should be reviewed separately.

```diff
diff --git a/3a_forcing/4_concat_summa_forcing/run_concat_summa_forcing_array.sh b/3a_forcing/4_concat_summa_forcing/run_concat_summa_forcing_array.sh
index ecf5a0e..570c4cd 100755
--- a/3a_forcing/4_concat_summa_forcing/run_concat_summa_forcing_array.sh
+++ b/3a_forcing/4_concat_summa_forcing/run_concat_summa_forcing_array.sh
@@ -4,7 +4,7 @@
 #SBATCH --time=02:00:00
 #SBATCH --mem=4G
 #SBATCH --cpus-per-task=1
-#SBATCH --exclude=fc1
+#    SBATCH --exclude=fc1 when I submit the job, fir could not find this fc1 to be excluded. So I just make this line invisible
 #SBATCH --output=slurm_logs/summa_concat_%A_%a.out
 #SBATCH --error=slurm_logs/summa_concat_%A_%a.err
@@ -15,8 +15,8 @@ set -eo pipefail
 # PATHS
 # ============================================================
-SCRIPT_DIR="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin/3a_forcing/4_concat_summa_forcing"
-
+#SCRIPT_DIR="/project/6102189/dorolin/Github/NAWM-CWARHM-MX/3a_forcing/4_concat_summa_forcing"
+SCRIPT_DIR="/project/6102189/dorolin/Github/NAWM-CWARHM-MX/3a_forcing/4_concat_summa_forcing"
 # ============================================================
 # INPUT BASIN TASK FILE
@@ -127,9 +127,8 @@ echo "============================================================"
 # ENVIRONMENT
 # ============================================================
-module load conda/base
+source "/project/6102189/dorolin/Github/NAWM-CWARHM-MX/load_nwam_fir.sh"
-conda activate nwam
 set -u
@@ -155,4 +154,4 @@ python "${SCRIPT_DIR}/concat_summa_forcing.py" \
 echo
 echo "============================================================"
 echo "DONE: ${DOMAIN}"
-echo "============================================================"
\ No newline at end of file
+echo "============================================================"
```

### 1.6 `3b_parameters/SOILGRIDS/2_extract_domain/extract_domain.py`

**Soil input selection** Change the search from all TIFFs to the single usda_mode_soilclass_250m_ll.tif raster. I use Gdal to check this two files, they seems the same, so I select the usda one.

```diff
diff --git a/3b_parameters/SOILGRIDS/2_extract_domain/extract_domain.py b/3b_parameters/SOILGRIDS/2_extract_domain/extract_domain.py
index f0ec0a0..d31cb58 100644
--- a/3b_parameters/SOILGRIDS/2_extract_domain/extract_domain.py
+++ b/3b_parameters/SOILGRIDS/2_extract_domain/extract_domain.py
@@ -219,7 +219,7 @@ output_file = (
 source_files = sorted(
     soil_raw_path.glob(
-        "*.tif"
+        "usda_mode_soilclass_250m_ll.tif"
     )
 )
```

### 1.7 `3b_parameters/run_multibasin_parameter_data_preprocessing_array.sh`

**Parameter preprocessing and GDAL/HDF4.** Stage the packed nwam-fir environment under SLURM_TMPDIR and check the GDAL/HDF4 installation. Replace xargs whitespace handling with sed in task/control reading. The environment archive path is personal and should be supplied by configuration, not committed as a universal default.

```diff
diff --git a/3b_parameters/run_multibasin_parameter_data_preprocessing_array.sh b/3b_parameters/run_multibasin_parameter_data_preprocessing_array.sh
index d8f3aa5..30eac56 100755
--- a/3b_parameters/run_multibasin_parameter_data_preprocessing_array.sh
+++ b/3b_parameters/run_multibasin_parameter_data_preprocessing_array.sh
@@ -75,7 +75,9 @@ set -euo pipefail
 # CWARHM ROOT
 # ============================================================
-CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+#CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+CWARHM="/project/6102189/dorolin/Github/NAWM-CWARHM-MX"
+
 PARAM_DIR="${CWARHM}/3b_parameters"
@@ -169,7 +171,7 @@ LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))
 CONTROL_FILE=$(
     sed -n "${LINE_NUMBER}p" "${TASK_FILE}" \
-    | xargs
+        | sed "s/^[[:space:]]*//;s/[[:space:]]*$//"
 )
@@ -207,7 +209,7 @@ read_control() {
         grep -m 1 "^[[:space:]]*${setting}[[:space:]]*|" "${CONTROL_FILE}" \
         | cut -d'|' -f2- \
         | cut -d'#' -f1 \
-        | xargs
+        | sed "s/^[[:space:]]*//;s/[[:space:]]*$//"
     )
     if [ -z "${value}" ]; then
@@ -273,18 +275,31 @@ done
 # ENVIRONMENT
 # ============================================================
-module load conda/base
+#module load conda/base
+
+# Use the packed Python/GDAL environment on node-local storage.
+ENV_TAR=/project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/nwam-fir.tar.gz
+tar -xzf "$ENV_TAR" -C "$SLURM_TMPDIR"
+export VIRTUAL_ENV="$SLURM_TMPDIR/nwam-fir"
+export PATH="$VIRTUAL_ENV/bin:$PATH"
+export TMPDIR="$SLURM_TMPDIR"
+unset GDAL_DATA PROJ_DATA PROJ_LIB
+
+python -c 'import sys, os, rasterio; print(sys.executable, sys.prefix); assert sys.prefix == os.environ["VIRTUAL_ENV"]'
+gdalinfo --version
+gdalinfo --formats | grep -i HDF4
+
 # Activate nwam so all shell scripts use the GDAL installation
 # from the nwam environment. This is particularly important
 # for MODIS HDF4 support.
-CONDA_BASE=$(conda info --base)
+#CONDA_BASE=$(conda info --base)
-source "${CONDA_BASE}/etc/profile.d/conda.sh"
+#source "${CONDA_BASE}/etc/profile.d/conda.sh"
-conda activate nwam
+#conda activate nwam
 # ============================================================
@@ -742,4 +757,4 @@ echo "Next workflow stage:"
 echo "  Map DEM, soil class and land class to individual HRUs."
 echo
 echo "No control_active.txt was used or modified."
-echo
\ No newline at end of file
+echo
```

### 1.8 `4b_remapping/1_topo/run_multibasin_HRU_parameter_remapping_array.sh`

**Topographic, soil and land-cover HRU remapping.** Stage Python on node-local storage, use Fir PROJ database for geospatial scripts and QA, and replace xargs trimming. The fixed PROJ 9.4 location and archive path are installation-specific.

```diff
diff --git a/4b_remapping/1_topo/run_multibasin_HRU_parameter_remapping_array.sh b/4b_remapping/1_topo/run_multibasin_HRU_parameter_remapping_array.sh
index 0f746be..43e5783 100755
--- a/4b_remapping/1_topo/run_multibasin_HRU_parameter_remapping_array.sh
+++ b/4b_remapping/1_topo/run_multibasin_HRU_parameter_remapping_array.sh
@@ -62,7 +62,7 @@ set -euo pipefail
 # PATHS
 # ============================================================
-CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+CWARHM="/project/6102189/dorolin/Github/NAWM-CWARHM-MX"
 SCRIPT_DIR="${CWARHM}/4b_remapping/1_topo"
@@ -123,7 +123,7 @@ LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))
 CONTROL_FILE=$(
     sed -n "${LINE_NUMBER}p" "${TASK_FILE}" \
-    | xargs
+    | sed "s/^[[:space:]]*//;s/[[:space:]]*$//"
 )
@@ -180,7 +180,7 @@ read_control() {
     value="${value%%#*}"
     value=$(
-        echo "${value}" | xargs
+        echo "${value}" | sed "s/^[[:space:]]*//;s/[[:space:]]*$//"
     )
     if [ -z "${value}" ]; then
@@ -234,7 +234,16 @@ done
 # ENVIRONMENT
 # ============================================================
-module load conda/base
+# Use nwam-fir Python on node-local storage. GDAL/PROJ come from Fir.
+ENV_TAR=/project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/nwam-fir.tar.gz
+tar -xzf "$ENV_TAR" -C "$SLURM_TMPDIR"
+export VIRTUAL_ENV="$SLURM_TMPDIR/nwam-fir"
+export PATH="$VIRTUAL_ENV/bin:$PATH"
+export TMPDIR="$SLURM_TMPDIR"
+unset GDAL_DATA PROJ_DATA PROJ_LIB
+
+python -c 'import sys, os, numpy, geopandas, rasterio, fiona; print(sys.executable, numpy.__version__); assert sys.prefix == os.environ["VIRTUAL_ENV"]'
+PROJ_DATA="/cvmfs/soft.computecanada.ca/easybuild/software/2023/x86-64-v4/Compiler/gcccore/proj/9.4.1/share/proj" python -c 'import pyproj; from pyproj import CRS; print("PROJ data:", pyproj.datadir.get_data_dir()); print("CRS:", CRS.from_epsg(4326))'
 mkdir -p "${SCRIPT_DIR}/slurm_logs"
@@ -353,8 +362,7 @@ echo "----------------------------------------------------------------------"
 echo
-conda run --no-capture-output -n nwam \
-    python "${ELEVATION_SCRIPT}" \
+    PROJ_DATA="/cvmfs/soft.computecanada.ca/easybuild/software/2023/x86-64-v4/Compiler/gcccore/proj/9.4.1/share/proj" python "${ELEVATION_SCRIPT}" \
     "${CONTROL_FILE}"
@@ -374,8 +382,7 @@ echo "----------------------------------------------------------------------"
 echo
-conda run --no-capture-output -n nwam \
-    python "${SOIL_SCRIPT}" \
+    PROJ_DATA="/cvmfs/soft.computecanada.ca/easybuild/software/2023/x86-64-v4/Compiler/gcccore/proj/9.4.1/share/proj" python "${SOIL_SCRIPT}" \
     "${CONTROL_FILE}"
@@ -395,8 +402,7 @@ echo "----------------------------------------------------------------------"
 echo
-conda run --no-capture-output -n nwam \
-    python "${LAND_SCRIPT}" \
+    PROJ_DATA="/cvmfs/soft.computecanada.ca/easybuild/software/2023/x86-64-v4/Compiler/gcccore/proj/9.4.1/share/proj" python "${LAND_SCRIPT}" \
     "${CONTROL_FILE}"
@@ -509,8 +515,7 @@ echo
 # BASIC ATTRIBUTE VERIFICATION
 # ============================================================
-conda run --no-capture-output -n nwam \
-python - \
+PROJ_DATA="/cvmfs/soft.computecanada.ca/easybuild/software/2023/x86-64-v4/Compiler/gcccore/proj/9.4.1/share/proj" python - \
 "${DEM_OUTPUT}" \
 "${SOIL_OUTPUT}" \
 "${LAND_OUTPUT}" <<'PY'
```

### 1.9 `4b_remapping/2_forcing/2b_remap_all_EM_Earth.py`

**EM-Earth EASYMORE remapping weight lookup.** Change the temporary remap directory and later reassign remap_dir to catchment-intersection weights. Both assignments exist in the diff. Confirm which directory contains the generated CSV before accepting this change; the original and final paths should not be described as interchangeable.

```diff
diff --git a/4b_remapping/2_forcing/2b_remap_all_EM_Earth.py b/4b_remapping/2_forcing/2b_remap_all_EM_Earth.py
index 7ee2b35..5fd0202 100644
--- a/4b_remapping/2_forcing/2b_remap_all_EM_Earth.py
+++ b/4b_remapping/2_forcing/2b_remap_all_EM_Earth.py
@@ -214,12 +214,15 @@ output_dir = make_default_path(
 )
+# remap_dir = make_default_path(
+#     "shapefiles/catchment_intersection/"
+#     "with_forcing/EM_Earth"
+# )
+
 remap_dir = make_default_path(
-    "shapefiles/catchment_intersection/"
-    "with_forcing/EM_Earth"
+    "forcing/3_temp_easymore/EM_Earth"
 )
-
 temp_root = make_default_path(
     "forcing/3_temp_easymore/EM_Earth"
 )
@@ -517,6 +520,11 @@ case_name = (
 )
+remap_dir = (
+    remap_dir.parents[2]
+    / "shapefiles/catchment_intersection/with_forcing/EM_Earth"
+)
+
 remap_files = sorted(
     remap_dir.glob(
         f"{case_name}_remapping.csv"
@@ -1352,4 +1360,4 @@ print(f"Remap CSV    : {remap_csv}")
 print()
 print(
     "No control_active.txt was created or modified."
-)
\ No newline at end of file
+)
```

### 1.10 `4b_remapping/2_forcing/3_combine_forcing_for_SUMMA.py`

**Monthly EASYMORE output filename matching.** Replace older ERA5_SUMMA/EM_Earth_SUMMA monthly filename assumptions with the actual date-stamped remapped filenames. This changes file discovery, not the numerical combination formula.

```diff
diff --git a/4b_remapping/2_forcing/3_combine_forcing_for_SUMMA.py b/4b_remapping/2_forcing/3_combine_forcing_for_SUMMA.py
index 5537226..a1f2e6c 100644
--- a/4b_remapping/2_forcing/3_combine_forcing_for_SUMMA.py
+++ b/4b_remapping/2_forcing/3_combine_forcing_for_SUMMA.py
@@ -319,7 +319,7 @@ def get_month_files(year, month):
         era5_dir
         / (
             f"{era5_case}_remapped_"
-            f"ERA5_SUMMA_{ym}.nc"
+            f"{ym[:4]}-{ym[4:]}-01-00-00-00.nc"
         )
     )
@@ -328,7 +328,7 @@ def get_month_files(year, month):
         emearth_dir
         / (
             f"{emearth_case}_remapped_"
-            f"EM_Earth_SUMMA_{ym}.nc"
+            f"{ym[:4]}-{ym[4:]}-01-00-00-00.nc"
         )
     )
@@ -1346,4 +1346,4 @@ elif len(sys.argv) == 2:
 print()
 print(
     "No control_active.txt was created or modified."
-)
\ No newline at end of file
+)
```

### 1.11 `4b_remapping/2_forcing/run_combine_forcing_array.sh`

**Forcing combination job environment.** Change 4G to 16G memory, stage the packed environment to node-local storage, and call Python directly. The job setup currently activates the shared environment before unpacking the local copy; simplify after checking that local Python is the actual interpreter.

```diff
diff --git a/4b_remapping/2_forcing/run_combine_forcing_array.sh b/4b_remapping/2_forcing/run_combine_forcing_array.sh
index 6aa39b9..927ccbd 100755
--- a/4b_remapping/2_forcing/run_combine_forcing_array.sh
+++ b/4b_remapping/2_forcing/run_combine_forcing_array.sh
@@ -1,7 +1,8 @@
 #!/bin/bash
 #SBATCH --job-name=combine_forcing
 #SBATCH --time=08:00:00
-#SBATCH --mem=4G
+#SBATCH --mem=16G
+# SBATCH --mem=4G
 #SBATCH --cpus-per-task=1
 #SBATCH --output=slurm_logs/combine_forcing_%A_%a.out
 #SBATCH --error=slurm_logs/combine_forcing_%A_%a.err
@@ -66,12 +67,23 @@ set -euo pipefail
 # PATHS
 # ============================================================
-CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+#CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+CWARHM="/project/6102189/dorolin/Github/NAWM-CWARHM-MX/"
 SCRIPT_DIR="${CWARHM}/4b_remapping/2_forcing"
 PYTHON_SCRIPT="${SCRIPT_DIR}/3_combine_forcing_for_SUMMA.py"
+# Use a local copy to reduce small-file reads from shared storage.
+ENV_TAR=/project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/nwam-fir.tar.gz
+
+source /project/6102189/dorolin/Github/NAWM-CWARHM-MX/load_nwam_fir.sh
+tar -xzf "$ENV_TAR" -C "$SLURM_TMPDIR"
+export PATH="$SLURM_TMPDIR/nwam-fir/bin:$PATH"
+export TMPDIR="$SLURM_TMPDIR"
+
+python -c "import sys, xarray, netCDF4, easymore; print(sys.executable, sys.prefix)"
+python -c 'import sys, os; assert sys.prefix == os.environ["SLURM_TMPDIR"] + "/nwam-fir", sys.prefix'
 # ============================================================
 # ARGUMENTS
@@ -179,10 +191,12 @@ TASK_COUNT=$((END_INDEX - START_INDEX + 1))
 # ENVIRONMENT
 # ============================================================
-module load conda/base
+#module load conda/base
-cd "${SCRIPT_DIR}"
+#cd "${SCRIPT_DIR}"
+which python
+python --version
 # ============================================================
 # REPORT
@@ -358,7 +372,7 @@ for TASK_INDEX in $(seq "${START_INDEX}" "${END_INDEX}"); do
     # COMBINE ERA5 + EM-EARTH FOR SUMMA
     # --------------------------------------------------------
-    if conda run --no-capture-output -n nwam \
+    if
         python "${PYTHON_SCRIPT}" \
         "${CONTROL_FILE}" \
         "${YEAR}" \
@@ -408,4 +422,4 @@ if [ "${FAILED}" -gt 0 ]; then
     exit 1
-fi
\ No newline at end of file
+fi
```

### 1.12 `4b_remapping/2_forcing/run_create_forcing_remapping_array.sh`

**Create forcing remapping job.** Replace the original developer checkout path with the Fir checkout. This is a local execution path change.

```diff
diff --git a/4b_remapping/2_forcing/run_create_forcing_remapping_array.sh b/4b_remapping/2_forcing/run_create_forcing_remapping_array.sh
index ede17a2..61e59d5 100755
--- a/4b_remapping/2_forcing/run_create_forcing_remapping_array.sh
+++ b/4b_remapping/2_forcing/run_create_forcing_remapping_array.sh
@@ -8,7 +8,8 @@
 set -euo pipefail
-CWARHM="/home/armanhad/projects/rrg-mclark/armanhad/NAWM-CWARHM-MX"
+#CWARHM="/home/armanhad/projects/rrg-mclark/armanhad/NAWM-CWARHM-MX"
+CWARHM="/project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/"
 SCRIPT_DIR="${CWARHM}/4b_remapping/2_forcing"
 ERA5_SCRIPT="${SCRIPT_DIR}/1a_remap_ERA5.py"
```

### 1.13 `4b_remapping/2_forcing/run_remap_EM_Earth_array.sh`

**EM-Earth monthly remapping launcher.** Replace original developer checkout path with the Fir checkout. 

```diff
diff --git a/4b_remapping/2_forcing/run_remap_EM_Earth_array.sh b/4b_remapping/2_forcing/run_remap_EM_Earth_array.sh
index b799982..0a666c7 100755
--- a/4b_remapping/2_forcing/run_remap_EM_Earth_array.sh
+++ b/4b_remapping/2_forcing/run_remap_EM_Earth_array.sh
@@ -49,7 +49,8 @@ set -euo pipefail
 # PATHS
 # ============================================================
-CWARHM="/home/armanhad/projects/rrg-mclark/armanhad/NAWM-CWARHM-MX"
+#CWARHM="/home/armanhad/projects/rrg-mclark/armanhad/NAWM-CWARHM-MX"
+CWARHM="/project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/"
 SCRIPT_DIR="${CWARHM}/4b_remapping/2_forcing"
@@ -389,4 +390,4 @@ if [ "${FAILED}" -gt 0 ]; then
     exit 1
-fi
\ No newline at end of file
+fi
```

### 1.14 `4b_remapping/2_forcing/run_remap_ERA5_array.sh`

**ERA5 monthly remapping launcher.** Replace original developer checkout path with the Fir checkout. 

```diff
diff --git a/4b_remapping/2_forcing/run_remap_ERA5_array.sh b/4b_remapping/2_forcing/run_remap_ERA5_array.sh
index 97b51b6..369d01c 100755
--- a/4b_remapping/2_forcing/run_remap_ERA5_array.sh
+++ b/4b_remapping/2_forcing/run_remap_ERA5_array.sh
@@ -49,7 +49,8 @@ set -euo pipefail
 # PATHS
 # ============================================================
-CWARHM="/home/armanhad/projects/rrg-mclark/armanhad/NAWM-CWARHM-MX"
+#CWARHM="/home/armanhad/projects/rrg-mclark/armanhad/NAWM-CWARHM-MX"
+CWARHM="/project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/"
 SCRIPT_DIR="${CWARHM}/4b_remapping/2_forcing"
@@ -389,4 +390,4 @@ if [ "${FAILED}" -gt 0 ]; then
     exit 1
-fi
\ No newline at end of file
+fi
```

### 1.15 `5_model_input/mizuRoute/1b_network_topology_file/1_create_network_topology_file.py`

**Routing-basin input selection** Change control setting river_basin_shp_name to catchment_shp_name. This changes the selected shapefile name, not just a path. Confirm the geometry and expected mizuRoute routing-basin fields before merging.

```diff
diff --git a/5_model_input/mizuRoute/1b_network_topology_file/1_create_network_topology_file.py b/5_model_input/mizuRoute/1b_network_topology_file/1_create_network_topology_file.py
index f35409d..3939231 100644
--- a/5_model_input/mizuRoute/1b_network_topology_file/1_create_network_topology_file.py
+++ b/5_model_input/mizuRoute/1b_network_topology_file/1_create_network_topology_file.py
@@ -463,7 +463,7 @@ river_length = read_from_control(
 river_basin_name = read_from_control(
     CONTROL_FILE,
-    "river_basin_shp_name"
+    "catchment_shp_name"
 )
```

### 1.16 `5_model_input/run_multibasin_model_input_generation_array.sh`

**SUMMA/mizuRoute input generation.** Use node-local Python and Fir PROJ for workers and NetCDF QA; replace xargs trimming with sed. Check the hardcoded environment/proj paths and preserve existing model-input formulas.

```diff
diff --git a/5_model_input/run_multibasin_model_input_generation_array.sh b/5_model_input/run_multibasin_model_input_generation_array.sh
index cf17805..2a0d62c 100755
--- a/5_model_input/run_multibasin_model_input_generation_array.sh
+++ b/5_model_input/run_multibasin_model_input_generation_array.sh
@@ -54,7 +54,7 @@ set -euo pipefail
 # PATHS
 # ============================================================
-CWARHM="/work/comphyd_lab/users/arman.haddadchi/NWAM/CWARHM_multibasin"
+CWARHM="/project/6102189/dorolin/Github/NAWM-CWARHM-MX"
 MODEL_INPUT="${CWARHM}/5_model_input"
@@ -111,7 +111,7 @@ fi
 LINE_NUMBER=$((SLURM_ARRAY_TASK_ID + 1))
-CONTROL_FILE=$(sed -n "${LINE_NUMBER}p" "${TASK_FILE}" | xargs)
+CONTROL_FILE=$(sed -n "${LINE_NUMBER}p" "${TASK_FILE}" | sed "s/^[[:space:]]*//;s/[[:space:]]*$//")
 if [ -z "${CONTROL_FILE}" ]; then
@@ -147,7 +147,7 @@ read_control() {
         grep -m 1 "^${setting}[[:space:]]*|" "${CONTROL_FILE}" \
         | cut -d'|' -f2- \
         | cut -d'#' -f1 \
-        | xargs
+        | sed "s/^[[:space:]]*//;s/[[:space:]]*$//"
     )
     if [ -z "${value}" ]; then
@@ -180,9 +180,19 @@ DOMAIN_ROOT="${ROOT_PATH}/domain_${DOMAIN}"
 # ENVIRONMENT
 # ============================================================
-module load conda/base
+# Python runs from node-local storage. GDAL/PROJ come from Fir.
+ENV_TAR=/project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/nwam-fir.tar.gz
+tar -xzf "$ENV_TAR" -C "$SLURM_TMPDIR"
+export VIRTUAL_ENV="$SLURM_TMPDIR/nwam-fir"
+export PATH="$VIRTUAL_ENV/bin:$PATH"
+export TMPDIR="$SLURM_TMPDIR"
+unset GDAL_DATA PROJ_DATA PROJ_LIB
-PYTHON=$(conda run -n nwam which python)
+PYTHON="$VIRTUAL_ENV/bin/python"
+PROJ94=/cvmfs/soft.computecanada.ca/easybuild/software/2023/x86-64-v4/Compiler/gcccore/proj/9.4.1/share/proj
+
+test -s "$PROJ94/proj.db"
+PROJ_DATA="$PROJ94" "$PYTHON" -c 'from pyproj import CRS; print("EPSG:", CRS.from_epsg(4326).to_epsg())'
 if [ ! -x "${PYTHON}" ]; then
@@ -240,7 +250,7 @@ run_python_step() {
     fi
-    "${PYTHON}" \
+    PROJ_DATA="$PROJ94" "${PYTHON}" \
         "${script}" \
         "${CONTROL_FILE}"
@@ -569,7 +579,7 @@ done
 # NETCDF QA
 # ============================================================
-"${PYTHON}" - \
+PROJ_DATA="$PROJ94" "${PYTHON}" - \
     "${SUMMA_SETTINGS}/${SUMMA_COLDSTATE}" \
     "${SUMMA_SETTINGS}/${SUMMA_TRIALPARAMS}" \
     "${SUMMA_SETTINGS}/${SUMMA_ATTRIBUTES}" \
```

## 2. Control template location

**Before**

```text
0_control_files/control_CAMELS_MX_template.txt
0_control_files/control_MX_1023.txt
```

**After**

```text
0_control_files/templates/control_CAMELS_MX_template.txt
0_control_files/control_MX_1023.txt
```

When I run script to generate the control files, sometimes the task generator would report `RuntimeError: Duplicate DISTRIBUTED controls found for domain 'MX_1023'` (for example). 
The template contains `domain_name | MX_1023` and was scanned with the active controls. 
My solution was moving it under `templates/` to prevent it from being treated as another active basin control. 

## 3. Basin controls — all 42 individual working-tree diffs

For the 21 distributed control files, `root_path` moves outputs from the shared hackathon directory to the test checkout and `forcing_raw_space` changes the requested geographic subset. The latter changes which forcing grid cells are read and requires spatial review. The `settings_mizu_make_outlet | n/a` change only alters whitespace. For the 21 lumped control files, the recorded change is the output root. These paths describe the test setup; they should not be merged as general defaults without a portable output-root design.

The affected basin IDs are: MX_1023, MX_3008, MX_10113, MX_11028, MX_11042, MX_12428, MX_12496, MX_12532, MX_18323, MX_20037, MX_22008, MX_22026, MX_23003, MX_25037, MX_25043, MX_26151, MX_26282, MX_26337, MX_27006, MX_30066, MX_30181.

### 3.2 `0_control_files/control_MX_10113.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.
Note: When I rerun the script to generate the control files, the forcing boundary will change a little bit in comparison to those orginally provided.

```diff
diff --git a/0_control_files/control_MX_10113.txt b/0_control_files/control_MX_10113.txt
index fe8799a..d0a9dd7 100644
--- a/0_control_files/control_MX_10113.txt
+++ b/0_control_files/control_MX_10113.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_10113
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 26.280389/-107.183167/24.738056/-105.570167
+forcing_raw_space            | 26.080389/-106.983167/24.938056/-105.770167
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.3 `0_control_files/control_MX_10113_lumped.txt`

For lumped, I just ran the control targeting to my own directory.
Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_10113_lumped.txt b/0_control_files/control_MX_10113_lumped.txt
index 8cf7999..ce2ab20 100644
--- a/0_control_files/control_MX_10113_lumped.txt
+++ b/0_control_files/control_MX_10113_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_10113
```

### 3.4 `0_control_files/control_MX_1023.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_1023.txt b/0_control_files/control_MX_1023.txt
index d3d639d..f848c53 100644
--- a/0_control_files/control_MX_1023.txt
+++ b/0_control_files/control_MX_1023.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_1023
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 32.506500/-116.744389/31.592722/-115.614278
+forcing_raw_space            | 32.306500/-116.544389/31.792722/-115.814278
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.5 `0_control_files/control_MX_1023_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_1023_lumped.txt b/0_control_files/control_MX_1023_lumped.txt
index 4280aa9..3b06a9b 100644
--- a/0_control_files/control_MX_1023_lumped.txt
+++ b/0_control_files/control_MX_1023_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_1023
```

### 3.6 `0_control_files/control_MX_11028.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_11028.txt b/0_control_files/control_MX_11028.txt
index 6964a43..338fc16 100644
--- a/0_control_files/control_MX_11028.txt
+++ b/0_control_files/control_MX_11028.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_11028
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 24.440056/-104.227167/23.390500/-103.230833
+forcing_raw_space            | 24.240056/-104.027167/23.590500/-103.430833
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.7 `0_control_files/control_MX_11028_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_11028_lumped.txt b/0_control_files/control_MX_11028_lumped.txt
index 430c863..8d9c5a0 100644
--- a/0_control_files/control_MX_11028_lumped.txt
+++ b/0_control_files/control_MX_11028_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_11028
```

### 3.8 `0_control_files/control_MX_11042.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_11042.txt b/0_control_files/control_MX_11042.txt
index a788cab..cd4b655 100644
--- a/0_control_files/control_MX_11042.txt
+++ b/0_control_files/control_MX_11042.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_11042
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 24.920611/-105.290611/24.351056/-104.611528
+forcing_raw_space            | 24.720611/-105.090611/24.551056/-104.811528
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.9 `0_control_files/control_MX_11042_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_11042_lumped.txt b/0_control_files/control_MX_11042_lumped.txt
index ce654c3..ae5d93f 100644
--- a/0_control_files/control_MX_11042_lumped.txt
+++ b/0_control_files/control_MX_11042_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_11042
```

### 3.10 `0_control_files/control_MX_12428.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_12428.txt b/0_control_files/control_MX_12428.txt
index 0b26cc1..b584506 100644
--- a/0_control_files/control_MX_12428.txt
+++ b/0_control_files/control_MX_12428.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_12428
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 23.355389/-104.156278/21.099722/-102.522167
+forcing_raw_space            | 23.155389/-103.956278/21.299722/-102.722167
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.11 `0_control_files/control_MX_12428_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_12428_lumped.txt b/0_control_files/control_MX_12428_lumped.txt
index cd198f7..767c57b 100644
--- a/0_control_files/control_MX_12428_lumped.txt
+++ b/0_control_files/control_MX_12428_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_12428
```

### 3.12 `0_control_files/control_MX_12496.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_12496.txt b/0_control_files/control_MX_12496.txt
index ffde0fb..27cd897 100644
--- a/0_control_files/control_MX_12496.txt
+++ b/0_control_files/control_MX_12496.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_12496
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 23.667833/-105.400611/18.808056/-99.052833
+forcing_raw_space            | 23.467833/-105.200611/19.008056/-99.252833
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.13 `0_control_files/control_MX_12496_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_12496_lumped.txt b/0_control_files/control_MX_12496_lumped.txt
index 3484758..9c18dfc 100644
--- a/0_control_files/control_MX_12496_lumped.txt
+++ b/0_control_files/control_MX_12496_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_12496
```

### 3.14 `0_control_files/control_MX_12532.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_12532.txt b/0_control_files/control_MX_12532.txt
index 46f4938..a0793f6 100644
--- a/0_control_files/control_MX_12532.txt
+++ b/0_control_files/control_MX_12532.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_12532
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 22.974389/-103.819056/18.808056/-99.052833
+forcing_raw_space            | 22.774389/-103.619056/19.008056/-99.252833
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.15 `0_control_files/control_MX_12532_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_12532_lumped.txt b/0_control_files/control_MX_12532_lumped.txt
index 10bb154..65155a4 100644
--- a/0_control_files/control_MX_12532_lumped.txt
+++ b/0_control_files/control_MX_12532_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_12532
```

### 3.16 `0_control_files/control_MX_18323.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_18323.txt b/0_control_files/control_MX_18323.txt
index 8af9da6..e6ccffa 100644
--- a/0_control_files/control_MX_18323.txt
+++ b/0_control_files/control_MX_18323.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_18323
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 19.233722/-99.589278/18.579028/-99.004056
+forcing_raw_space            | 19.033722/-99.389278/18.779028/-99.204056
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.17 `0_control_files/control_MX_18323_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_18323_lumped.txt b/0_control_files/control_MX_18323_lumped.txt
index b9acbdb..aa77659 100644
--- a/0_control_files/control_MX_18323_lumped.txt
+++ b/0_control_files/control_MX_18323_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_18323
```

### 3.18 `0_control_files/control_MX_20037.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_20037.txt b/0_control_files/control_MX_20037.txt
index 8ab38fc..02777fe 100644
--- a/0_control_files/control_MX_20037.txt
+++ b/0_control_files/control_MX_20037.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_20037
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 17.875389/-99.991056/16.735389/-98.374611
+forcing_raw_space            | 17.675389/-99.791056/16.935389/-98.574611
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.19 `0_control_files/control_MX_20037_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_20037_lumped.txt b/0_control_files/control_MX_20037_lumped.txt
index c9c555a..635d3ae 100644
--- a/0_control_files/control_MX_20037_lumped.txt
+++ b/0_control_files/control_MX_20037_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_20037
```

### 3.20 `0_control_files/control_MX_22008.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_22008.txt b/0_control_files/control_MX_22008.txt
index 35129dc..d7d2852 100644
--- a/0_control_files/control_MX_22008.txt
+++ b/0_control_files/control_MX_22008.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_22008
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 17.280611/-96.918944/15.927278/-95.551611
+forcing_raw_space            | 17.080611/-96.718944/16.127278/-95.751611
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.21 `0_control_files/control_MX_22008_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_22008_lumped.txt b/0_control_files/control_MX_22008_lumped.txt
index 92260a5..26bdb7c 100644
--- a/0_control_files/control_MX_22008_lumped.txt
+++ b/0_control_files/control_MX_22008_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_22008
```

### 3.22 `0_control_files/control_MX_22026.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_22026.txt b/0_control_files/control_MX_22026.txt
index 703624a..43d5615 100644
--- a/0_control_files/control_MX_22026.txt
+++ b/0_control_files/control_MX_22026.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_22026
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 16.972389/-94.612917/16.230694/-93.955500
+forcing_raw_space            | 16.772389/-94.412917/16.430694/-94.155500
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.23 `0_control_files/control_MX_22026_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_22026_lumped.txt b/0_control_files/control_MX_22026_lumped.txt
index cfdba5c..48de0c0 100644
--- a/0_control_files/control_MX_22026_lumped.txt
+++ b/0_control_files/control_MX_22026_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_22026
```

### 3.24 `0_control_files/control_MX_23003.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_23003.txt b/0_control_files/control_MX_23003.txt
index 4443e02..7db9cba 100644
--- a/0_control_files/control_MX_23003.txt
+++ b/0_control_files/control_MX_23003.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_23003
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 15.380722/-92.522639/14.469306/-91.870611
+forcing_raw_space            | 15.180722/-92.322639/14.669306/-92.070611
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.25 `0_control_files/control_MX_23003_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_23003_lumped.txt b/0_control_files/control_MX_23003_lumped.txt
index aaab8ac..372409e 100644
--- a/0_control_files/control_MX_23003_lumped.txt
+++ b/0_control_files/control_MX_23003_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_23003
```

### 3.26 `0_control_files/control_MX_25037.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_25037.txt b/0_control_files/control_MX_25037.txt
index cd1451e..4f0bd48 100644
--- a/0_control_files/control_MX_25037.txt
+++ b/0_control_files/control_MX_25037.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_25037
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 23.658611/-98.648167/22.799389/-97.669056
+forcing_raw_space            | 23.458611/-98.448167/22.999389/-97.869056
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.27 `0_control_files/control_MX_25037_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_25037_lumped.txt b/0_control_files/control_MX_25037_lumped.txt
index fc0f252..23a59af 100644
--- a/0_control_files/control_MX_25037_lumped.txt
+++ b/0_control_files/control_MX_25037_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_25037
```

### 3.28 `0_control_files/control_MX_25043.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_25043.txt b/0_control_files/control_MX_25043.txt
index 8c5e09d..9043cc3 100644
--- a/0_control_files/control_MX_25043.txt
+++ b/0_control_files/control_MX_25043.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_25043
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 24.734389/-100.038944/24.002083/-99.182389
+forcing_raw_space            | 24.534389/-99.838944/24.202083/-99.382389
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.29 `0_control_files/control_MX_25043_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_25043_lumped.txt b/0_control_files/control_MX_25043_lumped.txt
index 0d9fa5f..70470e4 100644
--- a/0_control_files/control_MX_25043_lumped.txt
+++ b/0_control_files/control_MX_25043_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_25043
```

### 3.30 `0_control_files/control_MX_26151.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_26151.txt b/0_control_files/control_MX_26151.txt
index 8d10150..6340b7e 100644
--- a/0_control_files/control_MX_26151.txt
+++ b/0_control_files/control_MX_26151.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_26151
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 20.915833/-100.540944/19.580389/-99.367278
+forcing_raw_space            | 20.715833/-100.340944/19.780389/-99.567278
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.31 `0_control_files/control_MX_26151_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_26151_lumped.txt b/0_control_files/control_MX_26151_lumped.txt
index 3dd18e2..1c07b6e 100644
--- a/0_control_files/control_MX_26151_lumped.txt
+++ b/0_control_files/control_MX_26151_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_26151
```

### 3.32 `0_control_files/control_MX_26282.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_26282.txt b/0_control_files/control_MX_26282.txt
index d73d866..b7d2a34 100644
--- a/0_control_files/control_MX_26282.txt
+++ b/0_control_files/control_MX_26282.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_26282
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 20.802278/-98.879583/20.066500/-98.196056
+forcing_raw_space            | 20.602278/-98.679583/20.266500/-98.396056
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.33 `0_control_files/control_MX_26282_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_26282_lumped.txt b/0_control_files/control_MX_26282_lumped.txt
index 091db78..7f5492f 100644
--- a/0_control_files/control_MX_26282_lumped.txt
+++ b/0_control_files/control_MX_26282_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_26282
```

### 3.34 `0_control_files/control_MX_26337.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_26337.txt b/0_control_files/control_MX_26337.txt
index 502355f..85e1595 100644
--- a/0_control_files/control_MX_26337.txt
+++ b/0_control_files/control_MX_26337.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_26337
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 22.622500/-101.000611/21.618278/-99.912083
+forcing_raw_space            | 22.422500/-100.800611/21.818278/-100.112083
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.35 `0_control_files/control_MX_26337_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_26337_lumped.txt b/0_control_files/control_MX_26337_lumped.txt
index 3a9a45c..e668f24 100644
--- a/0_control_files/control_MX_26337_lumped.txt
+++ b/0_control_files/control_MX_26337_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_26337
```

### 3.36 `0_control_files/control_MX_27006.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_27006.txt b/0_control_files/control_MX_27006.txt
index 1ac3788..707d2a8 100644
--- a/0_control_files/control_MX_27006.txt
+++ b/0_control_files/control_MX_27006.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_27006
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 20.407639/-97.244500/19.476500/-96.467361
+forcing_raw_space            | 20.207639/-97.044500/19.676500/-96.667361
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.37 `0_control_files/control_MX_27006_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_27006_lumped.txt b/0_control_files/control_MX_27006_lumped.txt
index c98a3f5..2b84956 100644
--- a/0_control_files/control_MX_27006_lumped.txt
+++ b/0_control_files/control_MX_27006_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_27006
```

### 3.38 `0_control_files/control_MX_30066.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_30066.txt b/0_control_files/control_MX_30066.txt
index b6cbb3c..5787e15 100644
--- a/0_control_files/control_MX_30066.txt
+++ b/0_control_files/control_MX_30066.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_30066
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 17.548472/-93.766806/16.930611/-92.865278
+forcing_raw_space            | 17.348472/-93.566806/17.130611/-93.065278
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.39 `0_control_files/control_MX_30066_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_30066_lumped.txt b/0_control_files/control_MX_30066_lumped.txt
index 5175fe8..b01f133 100644
--- a/0_control_files/control_MX_30066_lumped.txt
+++ b/0_control_files/control_MX_30066_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_30066
```

### 3.40 `0_control_files/control_MX_3008.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_3008.txt b/0_control_files/control_MX_3008.txt
index d4112bc..a843e36 100644
--- a/0_control_files/control_MX_3008.txt
+++ b/0_control_files/control_MX_3008.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_3008
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 26.270278/-111.901167/25.315944/-111.116611
+forcing_raw_space            | 26.070278/-111.701167/25.515944/-111.316611
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.41 `0_control_files/control_MX_3008_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_3008_lumped.txt b/0_control_files/control_MX_3008_lumped.txt
index d2c7d43..3d1c2ff 100644
--- a/0_control_files/control_MX_3008_lumped.txt
+++ b/0_control_files/control_MX_3008_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_3008
```

### 3.42 `0_control_files/control_MX_30181.txt`

Distributed control: output root, forcing bounds and outlet-setting whitespace.

```diff
diff --git a/0_control_files/control_MX_30181.txt b/0_control_files/control_MX_30181.txt
index 8c9b947..3551c16 100644
--- a/0_control_files/control_MX_30181.txt
+++ b/0_control_files/control_MX_30181.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_30181
@@ -83,7 +83,7 @@ exe_name_mizuroute          | mizuroute.exe
 forcing_raw_time            | 1950,2019
 # LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
-forcing_raw_space                   | 18.897500/-91.367167/17.358500/-89.329833
+forcing_raw_space            | 18.697500/-91.167167/17.558500/-89.529833
 forcing_time_step_size      | 3600
 forcing_measurement_height  | 3
@@ -247,7 +247,7 @@ settings_mizu_within_basin  | 0
 # IMPORTANT:
 # Replace this placeholder with the actual outlet COMID reported by
 # 00_prepare_domain_shapefiles/3_report_control_values.py.
-settings_mizu_make_outlet           | n/a
+settings_mizu_make_outlet    | n/a
 # =====================================================================
```

### 3.43 `0_control_files/control_MX_30181_lumped.txt`

Lumped control: output root.

```diff
diff --git a/0_control_files/control_MX_30181_lumped.txt b/0_control_files/control_MX_30181_lumped.txt
index f670b6d..60a3db7 100644
--- a/0_control_files/control_MX_30181_lumped.txt
+++ b/0_control_files/control_MX_30181_lumped.txt
@@ -6,7 +6,7 @@
 # Modeling domain settings
 # =====================================================================
-root_path                           | /project/6079554/share/camels-mx/nawm_cwarhm_output
+root_path | /project/rrg-alpie/dorolin/Github/NAWM-CWARHM-MX/outputs
 domain_name                         | MX_30181
```


## EASYMORE compatibility and forcing remapping fixes

During the CAMELS-MX preprocessing tests on Alliance Fir, I encountered several issues related to the EASYMORE installation, remapping file paths, and the interaction between EASYMORE and the installed Python packages.

The Fir environment used for these tests contains:

| Package | Version |
|---|---|
| Python | 3.12.4 |
| NumPy | 2.4.2 |
| pandas | 3.0.0 |
| GDAL | 3.9.1 |
| EASYMORE | 1.0.0+computecanada |

The installed EASYMORE version matches `requirements_fir.txt`. The original `requirements.txt` specifies EASYMORE 0.0.3, while `environment_nwam.yml` does not specify an exact version. EASYMORE 2.0 has not been tested in this reproduction.

### 1. Existing EASYMORE changes in Arman's branch

Commit `988ed7f` (November 3, 2026) already addressed three EASYMORE compatibility issues:

- Changed `easymore.Easymore()` to `easymore.easymore()`.
- Changed the remapping CSV filename pattern from `*_remapping_file_*.csv` to `*_remapping.csv`.
- Changed the expected remapped NetCDF filename to use the first timestamp in the source forcing file.

These changes were already part of the branch before my additional tests. I used the updated scripts and did not need to repeat these changes.

### 2. EM-Earth remapping CSV path

**File:** `4b_remapping/2_forcing/2b_remap_all_EM_Earth.py`

The initial implementation located the remapping CSV under the catchment intersection directory.

Original:

```python
remap_dir = make_default_path(
    "shapefiles/catchment_intersection/"
    "with_forcing/EM_Earth"
)
```

During the Fir tests, I changed the initial path to the temporary EASYMORE directory:

```python
remap_dir = make_default_path(
    "forcing/3_temp_easymore/EM_Earth"
)
```

Later in the script, the path was changed back to the catchment intersection directory relative to this location:

```python
remap_dir = (
    remap_dir.parents[2]
    / "shapefiles/catchment_intersection/with_forcing/EM_Earth"
)
```

The intention was to make the monthly remapping step locate the existing EM-Earth remapping weights.

The current implementation uses `parents[2]`, which depends on the directory structure. This part should be checked before merging. In particular, the final path should point to the CSV produced by the preceding remapping-weight generation step.

### 3. pandas compatibility in the installed EASYMORE package

**File:** `site-packages/easymore/easymore.py`

**Current location:** Line 1368.

The earlier implementation used an inplace operation on a pandas column:

```python
df_temp['values_w'].fillna(fill_value, inplace=True)
```

The installed Fir version contains:

```python
df_temp['values_w'] = df_temp['values_w'].fillna(float(fill_value))
```

This change addresses compatibility with the newer pandas version. It avoids chained inplace assignment and explicitly converts the missing-value replacement to a floating-point value.

The change preserves the original missing-value filling operation and does not modify the spatial remapping weights.

I confirmed that this line is present in the installed EASYMORE package. It is a local package-level change, not an uncommitted modification to the NAWM-CWARHM repository.

### 4. Short coordinate arrays in EASYMORE

**File:** `site-packages/easymore/easymore.py`

**Current location:** Lines 714–721.

The original coordinate-spacing check used the maximum absolute second difference:

```python
max_lat_temp_diff_2 = max(abs(np.diff(np.diff(lat_temp))))
max_lon_temp_diff_2 = max(abs(np.diff(np.diff(lon_temp))))
```

This fails when a coordinate array contains only two points because the second difference is empty.

The installed Fir version contains:

```python
lat_temp_diff = np.diff(lat_temp)
lat_temp_diff_2 = np.diff(lat_temp_diff)
max_lat_temp_diff_2 = np.max(np.abs(lat_temp_diff_2)) if lat_temp_diff_2.size else 0.0

lon_temp_diff = np.diff(lon_temp)
lon_temp_diff_2 = np.diff(lon_temp_diff)
max_lon_temp_diff_2 = np.max(np.abs(lon_temp_diff_2)) if lon_temp_diff_2.size else 0.0
```
 
This helps a two-point dimension to pass the spacing check. Returning `0.0` here means no non-uniform second difference was observed; it is not a change in coordinate rounding, decimal precision or the remapping weights. This inspection confirms the patch is present, but it is not a separate rerun or validation of the forcing output.

### 5. Python and GDAL compatibility

The Fir environment uses NumPy 2.4.2 and GDAL 3.9.1. During environment setup, I encountered a NumPy/GDAL compatibility issue involving the GDAL Python bindings.

The final environment was checked using:

```python
import numpy
import osgeo.gdal
import rasterio
import geopandas
import pyproj
```

All imports completed successfully. The required geospatial Python modules can be imported in the current environment. It does not constitute a numerical comparison between different NumPy or GDAL versions.

### 6. Reproduction notes and remaining work

The current EASYMORE setup was used during the Fir preprocessing work. The following points are important for reproducing the workflow in another environment:

1. The installed package is EASYMORE `1.0.0+computecanada`, not EASYMORE 2.0.
2. The installed package contains the pandas missing-value and short-coordinate-array changes described above.
3. These package-level changes are not included automatically when the NAWM-CWARHM repository is cloned.
4. The EM-Earth remapping CSV path change remains part of the local repository modifications and needs a final path check before merging.
5. Compatibility with EASYMORE 2.0, including remapping filenames and numerical outputs, remains to be tested separately.

A future test should compare the remapping weights and resulting forcing files between the current working environment and the version requested for the main workflow before changing the production environment.

## 7. Review needed before the PR is merged

The scientifically relevant changes are the forcing extraction bounds, the selected USDA soil raster, the routing-basin versus catchment shapefile key, and any EM-Earth time-gap repair. They need input and output verification. The EASYMORE EM-Earth remapping CSV path also needs a direct existence/read test. Current job scripts contain absolute personal paths and some commented previous commands, which is completely OK; if these can be made portable before they become shared production defaults that would be wonderful. But currently these workflow is general good and reproducible.

Next steps after reproduction review: validate representative combined forcing files (timestamps, units, NaNs and completeness); compare soil and routing geometries; run representative SUMMA and mizuRoute model inputs through a full test; measure memory, disk I/O and walltime with Slurm accounting before larger arrays.
