# NAWM-CWARHM

NAWM-CWARHM is a multi-basin, high-performance-computing extension of the Community Workflows to Advance Reproducibility in Hydrologic Modeling (CWARHM) developed by Knoben et al. (2022).

The workflow provides an automated framework for generating and executing SUMMA–mizuRoute model configurations for large numbers of river basins across North America as part of the North American Water Model (NAWM) project.

NAWM-CWARHM retains the fundamental CWARHM philosophy of separating model-agnostic data preparation from model-specific configuration, while adding the domain-generation, forcing-processing, batch-management, quality-control, and HPC infrastructure required for repeated multi-basin model production.

The repository is based on the original CH-Earth/CWARHM workflow.

> [!IMPORTANT]

> **This branch: `CAMELS_SPAT_MX` — CAMELS-MX demonstration and development.**

>

> This branch provides an initial example of adapting NAWM-CWARHM to a set of **21 CAMELS-MX basins**. It is **not a completed, validated 21-basin modelling product**. The broader NAWM-CWARHM development work continues separately on `NAWM-multibasin`.

>

> The workflow, input datasets, and processing choices in this demonstration **will be reviewed and updated in future**, depending on the data selected for each stage of the workflow.

## Running on FIR and ARC

NAWM-CWARHM supports two HPC environments. **FIR and ARC require different Python environment setup procedures**; the workflow source code can be shared, but the cluster-specific paths and environment activation commands are not interchangeable.

### FIR (Alliance): recommended module-first Python setup

FIR uses Alliance software modules and a small Python virtual environment. Python, SciPy, GDAL, HDF5, NetCDF C, MPI and SpatialIndex come from FIR modules; additional Python packages are installed from the local Alliance wheelhouse. The Python `netCDF4` binding is built against **serial** NetCDF/HDF5 to remain compatible with Rasterio, using those existing native FIR libraries.

**New installation** (run once per user in an allocated FIR compute-node shell):

```bash
# From the NAWM-CWARHM-MX repository root on FIR
salloc --time=00:45:00 --cpus-per-task=2 --mem=8G
# Once placed on a compute node:
bash setup_nwam_fir.sh
```

**Existing working FIR installations:** Do **not** rerun the one-time setup. The validated `nwam-fir` virtual environment can be reused directly.

**Every new terminal or batch-job shell** (after the initial setup):

```bash
cd /path/to/NAWM-CWARHM-MX
source load_nwam_fir.sh
python 0_tools/check_nwam_fir.py   # Optional validation
```

The loader currently uses the verified modules `StdEnv/2023`, `python/3.12.4`, `python-build-bundle/2026a`, `scipy-stack/2026a`, `gdal/3.9.1`, `mpi4py/4.0.3` and `libspatialindex/1.9.3`. The default virtual environment is `~/virtual-envs/nwam-fir`. See **[FIR environment setup](docs/FIR_environment_setup.md)** for the complete setup, testing, troubleshooting and Slurm-job instructions. The setup is idempotent with respect to your existing work: it refuses to overwrite a pre-existing target environment.

For the CAMELS-MX demonstration on FIR, example data locations are `/project/rrg-mclark/datasets/CAMELS_SPAT_MX/outputs/` (TDX clipped input exports) and `/project/rrg-mclark/datasets/CAMELS_SPAT_MX_Model/` (model products). **Basin control files and task inventories may still contain absolute ARC or checkout-specific paths; update or regenerate them on FIR before processing.** Loading the Python environment alone does not make ARC datasets available on FIR.

### ARC (University of Calgary): existing Conda environment

The earlier ARC workflow uses the repository's existing Conda-based configuration and scripts. These remain available and are not replaced by the FIR setup:

| Existing ARC file | Role |
| --- | --- |
| `environment_nwam.yml` | Main Conda environment specification (`nwam`) |
| `create_nwam_env.sh` | Original ARC environment creation helper |
| `update_nwam_env.sh` | Original ARC environment update helper; inspect its configured paths before running |
| `environment_nwam_parallel.yml` | Parallel environment specification |
| `create_nwam_parallel_env.sh` | Helper for the parallel environment |

Typical ARC activation after its environment has been created:

```bash
module load conda/base
conda activate nwam
```

For a first-time ARC setup, use the appropriate existing creation script or the YAML-based Conda workflow for that installation, after checking the script's cluster paths and loaded modules. ARC data have previously been configured under `/work/comphyd_lab/` (including the CAMELS-MX example root `/work/comphyd_lab/share/Data_CAMELS_MX`); these are **ARC-specific** and should not be copied into FIR controls unchanged. Do **not** use `update_nwam_env.sh` on FIR.

### Scope of these environments

The FIR setup documented here covers **Python geospatial preprocessing, forcing processing and EASYMORE**, not compilation of SUMMA or mizuRoute. Compiled hydrological models have separate module/compiler requirements and should be installed according to the appropriate cluster's model-build instructions.

---

## CAMELS-MX demonstration (`CAMELS_SPAT_MX` branch)

### Purpose and scope

This branch is a **demonstration of how the existing NAWM-CWARHM multibasin workflow can be configured for CAMELS-MX**, using an initial inventory of 21 Mexican basins. It supports collaborator testing and iterative development; it should not be treated as a final production workflow or a fixed prescription of datasets for Mexico.

The current example uses:

- **Basin delineation and river network:** existing TDX-Hydro-derived CAMELS-MX catchment and river-network shapefiles (clipped basin exports).
- **Elevation/terrain preparation:** the existing **MERIT Hydro DEM** workflow; the TDX-derived hydrofabric does not imply that TDX elevation is used for parameter extraction.
- **Meteorological forcing configuration:** shared ERA5 and EM-Earth sources, with `forcing_emearth_precip | prcp` for this demonstration.
- **Soil and land cover:** the existing shared soil-class and MODIS MCD12Q1 configurations carried over from NAWM-CWARHM.
- **Model configurations:** both distributed and single-HRU lumped SUMMA configurations, with mizuRoute routing supported by the existing scripts.

These are **initial demonstration choices**, not permanent decisions. Forcing, DEM, land-cover, soil, hydrofabric and other model inputs may change independently as the project evaluates available datasets and requirements. Changes should be documented in the relevant controls, inventory, and workflow manuals.

### Differences from the general NAWM-CWARHM workflow

| Aspect | CAMELS-MX demonstration |
| --- | --- |
| Basin selection | `MX_` basin IDs from `CAMELS_MX_control_file_inputs.csv` (21 listed) |
| Available inputs | 17 basins currently have the expected TDX clipped shapefile exports |
| Spatial input | TDX-Hydro-derived catchment and river-network shapefiles instead of the earlier Canadian/CENTURY example sources |
| Elevation | MERIT Hydro DEM processing retained |
| Control-file template | `0_control_files/control_CAMELS_MX_template.txt` |
| Output data root on ARC | `/work/comphyd_lab/share/Data_CAMELS_MX` |
| River length mapping | `lengthkm` (km) to `length_m` (m) |
| Routing basin topology | Uses Stage-00 **prepared catchment** shapefile with `COMID`, `area` (m²), and `hru_to_seg` |
| SUMMA–mizuRoute remapping | Configured `river_basin_needs_remap | no` for the initial one-GRU-per-segment representation; verify actual ID alignment for each basin |
| Scripts | Reuse existing Python workflows; the Stage-00 shell runner was adjusted to resolve paths relative to this checkout rather than the original repository |

The original source shapefiles are treated as read-only. Stage 00 writes prepared river-network and catchment shapefiles to each domain's output directory. The topology generator subsequently reads those prepared shapefiles, rather than depending on the original TDX `river_basins` attribute schema.

### Files included in this branch

```text
0_control_files/
  CAMELS_MX_control_file_inputs.csv             # Original 21-basin inventory
  CAMELS_MX_control_file_inputs_available.csv   # 17 basins with source directories available
  control_CAMELS_MX_template.txt                # Distributed control template
  control_MX_<ID>.txt                           # 17 distributed controls
  control_MX_<ID>_lumped.txt                    # 17 lumped controls
  multibasin_preprocessing_CAMELS_MX.txt        # Distributed basin task list
  lumped_multibasin_preprocessing_CAMELS_MX.txt # Lumped basin task list
```

Lumped controls are **derived from the distributed controls** with `00_prepare_domain_shapefiles/0_generate_lumped_multibasin_control_files.py`; a separate hand-edited lumped template is not required. They inherit the distributed precipitation selection and establish paths under `domain_MX_<ID>/lumped/`.

The two committed task files contain **absolute ARC paths to the checkout used to generate them**. If the repository is cloned elsewhere, these task files must be regenerated or their paths updated before execution. Model outputs and source geospatial data are held outside Git and are not included in this repository.

### Current verification status (28 October 2026)

- **21 basins** are recorded in the full CAMELS-MX inventory.
- **17 basins** had the expected TDX clipped shapefile source directories and have distributed and lumped control files generated.
- **4 basins** do not yet have the expected `cwarhm_exports/tdx_clipped/shapefiles` directories: `MX_10113`, `MX_12428`, `MX_12496`, and `MX_12532`.
- `MX_1023` **passed distributed Stage 00**: 193 river segments and 193 catchments/GRUs were prepared, and the control was updated from the prepared domain geometry. Its source shapefiles were not modified.
- The distributed control generator was successfully applied to the 17 available basins; the lumped-control generator's 17-basin dry-run passed and the 17 lumped controls and task list were created.
- **Not yet established:** distributed Stage 00 success for the other 16 basins; lumped catchment preparation; parameter/forcing completion; topology and model-input generation across all basins; successful SUMMA–mizuRoute simulations or scientific validation.

This status intentionally distinguishes **control-file generation** from actual completion and verification of data-processing and model-execution stages.

### Continuing the demonstration

A collaborator can use the provided basin task lists and control files to continue distributed Stage 00 preparation, then prepare the lumped catchments and proceed through forcing, parameter, and model-input stages using the corresponding workflow manuals. Validate each stage before extending to further basins. In particular, confirm the routing IDs, outlet connectivity, HRU-area units, and compatibility of the source data with the selected processing scripts.

The current reporter recalculates `forcing_raw_space` with a **0.05° buffer** during Stage 00, replacing the control generator's initial **0.25° buffer**. This is an existing workflow behavior that should be considered when choosing forcing-grid coverage.

As input datasets and processing methods are decided, **update this branch and the operational manuals**. The commands and settings documented here represent a working demonstration configuration, not a guarantee that all downstream steps require no adaptation.

## Background

CWARHM was developed as a reproducible framework for configuring large-domain hydrological models. The original implementation couples:

- **SUMMA** — Structure for Unifying Multiple Modeling Alternatives (Clark et al., 2015a,b)
- **mizuRoute** — river-network routing model (Mizukami et al., 2016)

Knoben et al. (2022) demonstrated that CWARHM can be applied from local catchments to continental and global domains, including a North American configuration containing more than 500,000 sub-basins.

The purpose of NAWM-CWARHM is therefore not simply to increase the spatial scale of CWARHM. Instead, it operationalizes the CWARHM architecture for repeated model production across many North American river basins and supports both distributed and lumped representations of individual basins within the same processing framework.

Major additions include:

- automated generation of basin-specific control files from domain inventories;
- automated preparation of CWARHM-compatible domain shapefiles;
- parallel generation of distributed and lumped basin configurations;
- separate distributed and lumped processing directories within each model domain;
- reusable basin-level and month-level task inventories for both configurations;
- control-file selection of the EM-Earth precipitation product;
- support for both raw and bias-corrected EM-Earth precipitation;
- reusable EASYMORE spatial-remapping weights;
- large Slurm-array forcing workflows;
- concatenation of monthly SUMMA forcing into continuous forcing datasets;
- UTC-to-local-standard-time (LST) conversion of forcing;
- multi-basin SUMMA and mizuRoute input generation;
- LST-aware SUMMA runtime configuration;
- support for domains containing a single HRU/river segment as well as large multi-HRU domains;
- explicit handling and validation of river-network topology;
- utilities for maintaining compatible SUMMA initial-state structures in controlled experiments;
- systematic verification between workflow stages;
- coordinated HPC execution of large collections of basins.

## Workflow architecture

NAWM-CWARHM organizes processing into a sequence of reproducible stages:

```text
Domain inventory
      ↓
Generate basin control files
      ↓
Generate distributed + lumped controls
      ↓
Generate basin + monthly task inventories
      ↓
Prepare distributed + lumped domain structures
      ↓
Prepare domain shapefiles and forcing grids
      ↓
Prepare ERA5 + EM-Earth monthly forcing
      ↓
Select precipitation product
      ↓
Create spatial-remapping weights
      ↓
Remap forcing to HRUs
      ↓
Assemble monthly SUMMA forcing
      ↓
Concatenate forcing
      ↓
Convert UTC forcing to local standard time (LST)
      ↓
Prepare DEM + soil + land-cover data
      ↓
Map geospatial parameters to HRUs
      ↓
Generate SUMMA + mizuRoute inputs
      ↓
Verify model configuration
      ↓
Run SUMMA
      ↓
Merge distributed SUMMA outputs
      ↓
Run mizuRoute
      ↓
Final simulation verification
```

The important architectural change is that processing is task-driven rather than basin-script-driven. The same workflow scripts can therefore operate on different collections of basins without rewriting the underlying processing code.

A second important extension is that distributed and lumped representations are handled by the same overall workflow. This allows model structural experiments to use common source data and processing logic while maintaining separate spatial, forcing, parameter, model-input, and simulation products.

## Multi-basin processing

A major extension of NAWM-CWARHM is the introduction of reusable basin and month task files.

For a selected collection of distributed domains, the workflow generates:

```text
multibasin_preprocessing_<BATCH>.txt
month_tasks_<BATCH>.txt
```

For lumped processing, corresponding task inventories are generated:

```text
lumped_multibasin_preprocessing_<BATCH>.txt
lumped_month_tasks_<BATCH>.txt
```

The basin task files define one model domain per task, while the monthly task files define one domain-month combination per task.

For example, five basins with forcing from 1950–2019 contain:

```text
5 basins × 840 months = 4200 monthly tasks
```

These task inventories can then be supplied directly to Slurm-array runners.

A reusable `set_batch.sh` configuration exposes the currently selected task inventories and task counts so subsequent workflow stages can operate on the selected collection without hard-coding basin names.

This design allows the same processing infrastructure to be used for a small test collection or a much larger production set.

## Domain inventories and control-file generation

The original CWARHM workflow assumes that the user already has an appropriate spatial discretization and associated control file.

NAWM-CWARHM introduces a higher-level domain inventory from which basin-specific CWARHM controls can be generated automatically.

Currently supported examples include:

```text
MERIT_Pfaf3_control_file_inputs.csv
CENTURY_control_file_inputs.csv
```

These inventories contain information such as:

```text
domain_name
source_directory
catchment_shp_file
river_network_shp_file
river_basin_shp_file
```

The workflow uses these inventories together with a validated CWARHM control template to create:

```text
control_<DOMAIN>.txt
```

for each selected basin.

Domain-specific information, including the meteorological forcing extent, is generated automatically from the basin geometry.

The distributed controls can subsequently be used to generate corresponding lumped controls:

```text
control_<DOMAIN>_lumped.txt
```

The lumped controls retain the relevant forcing, source-data, and model settings from the distributed configuration while directing outputs to the lumped subdirectories of the same model domain.

This provides the configuration hierarchy:

```text
domain inventory
      ↓
distributed control
      ↓
lumped control
      ↓
distributed/lumped processing
```

and substantially reduces manual control-file editing.

Important forcing choices are also exposed through the control files rather than being hard-coded in processing scripts. In particular, the EM-Earth precipitation variable can be selected through the control configuration. This allows the same workflow to generate alternative forcing datasets using, for example:

```text
prcp
```

or:

```text
prcp_corrected
```

where the latter represents the bias-corrected precipitation product.

This is particularly useful for controlled forcing experiments because the processing workflow remains unchanged while the precipitation source is explicitly recorded in the basin configuration.

#### Known EM-Earth time gaps

The hourly EM-Earth archive contains known seven-hour gaps on **1 January 1950** and **1 January 1979** (00:00–06:00 UTC). During source preparation, NAWM-CWARHM explicitly repairs these two gaps by setting precipitation to **0.0 mm h⁻¹** and assigning the **07:00 UTC temperature from the same day** to the seven missing hours. Existing valid values are not modified, and no interpolation is performed.

This treatment applies only to these two documented gaps. Any other missing timestamps are treated as unexpected and cause the forcing-preparation task to fail.

## Domain preparation

NAWM-CWARHM adds a new:

```text
00_prepare_domain_shapefiles/
```

stage before the traditional CWARHM processing sequence.

This stage creates CWARHM-compatible catchment and river-network datasets and establishes the attributes required by SUMMA and mizuRoute.

Important attributes include:

```text
COMID
GRU_ID
HRU_ID
HRU area
NextDownID
river length
river slope
HRU-to-segment relationship
```

The source hydrography is preserved; prepared model-domain files are written to the individual NAWM domain directories.

The workflow can additionally derive a lumped representation of each basin. Distributed and lumped configurations are maintained within the same `domain_<DOMAIN>` structure but use separate subdirectories, preventing products from the two spatial representations from being mixed.

This makes spatial-domain preparation part of the reproducible workflow rather than an external GIS prerequisite and provides a consistent basis for comparing distributed and lumped model configurations.

## Meteorological forcing

NAWM-CWARHM uses meteorological information from both ERA5 and EM-Earth.

The forcing workflow is organized into source preparation, spatial remapping, SUMMA assembly, concatenation, and time conversion.

### 1. Source preparation

Raw ERA5 and EM-Earth archives are converted into standardized monthly files for each domain.

For EM-Earth, the precipitation field is selected from the basin control file rather than being hard-coded in the processing script. The workflow can therefore be applied using either the raw precipitation product or an alternative bias-corrected precipitation without modifying the forcing code.

### 2. Spatial remapping

Reusable EASYMORE remapping weights are generated for each basin and forcing product.

Monthly meteorological files are subsequently remapped to the model HRUs using Slurm arrays.

Separate remapping workflows are available for distributed and lumped configurations.

### 3. SUMMA forcing assembly

The remapped variables are combined into monthly SUMMA forcing files:

```text
NWAM_SUMMA_forcing_YYYYMM.nc
```

For the 1950–2019 configuration this produces:

```text
840 monthly forcing files per basin
```

with hourly meteorological data.

The final forcing combines variables supplied by the two meteorological products into a common SUMMA-compatible dataset.

### 4. Forcing concatenation

The monthly SUMMA forcing files can subsequently be concatenated into a continuous forcing dataset.

This provides a convenient single forcing product for long SUMMA simulations while retaining the monthly intermediate files used by the parallel processing workflow.

Separate concatenation utilities support distributed and single-HRU/lumped forcing configurations.

### 5. UTC-to-local-standard-time conversion

The forcing workflow includes an additional time-processing stage that converts the concatenated UTC forcing to local standard time (LST).

This produces an additional forcing layer while preserving the original UTC product:

```text
monthly forcing
      ↓
concatenated UTC forcing
      ↓
concatenated LST forcing
```

The local standard-time offset is obtained from basin metadata rather than manually modifying timestamps for individual domains.

SUMMA file-manager and forcing-list generation includes corresponding LST-aware workflows so simulations can explicitly use the local-time forcing product.

This separation of source preparation, remapping, assembly, concatenation, and time conversion makes the forcing workflow restartable and allows failed domain-month tasks to be rerun independently.

### 6. Post-processing archive

After the distributed and lumped forcing workflows have been completed and verified, monthly intermediate forcing files can be archived to reduce the number of individual files retained on the HPC filesystem.

For each completed basin, monthly NetCDF files from the distributed and lumped forcing-processing stages are collected into verified `monthly_netcdf.tar` archives. Workflow logs are similarly consolidated into `workflow_logs.zip`.

Original monthly files are removed only after successful archive verification. The final concatenated UTC and LST forcing products are retained unchanged.

The archive workflow uses the same active basin batch defined through `set_batch.sh` and the existing lumped basin task inventory, allowing the same procedure to operate on small test batches or large production collections without generating a separate archive task list.

## Distributed and lumped model configurations

NAWM-CWARHM supports two spatial representations of a basin within the same model-domain hierarchy:

**Distributed configuration**

Retains the multi-HRU spatial representation supplied by the prepared basin dataset.

**Lumped configuration**

Represents the basin using a single lumped HRU while retaining the corresponding basin-level forcing and parameter information required by SUMMA.

The workflow provides dedicated lumped versions of the major processing stages, including:

- control-file generation;
- catchment preparation;
- basin/month task generation;
- DEM, soil, and land-cover parameter extraction;
- ERA5 and EM-Earth remapping;
- SUMMA forcing assembly;
- UTC-to-LST conversion;
- safe post-processing archival of monthly forcing and workflow logs after distributed and lumped model preparation;
- SUMMA attributes generation;
- file-manager and forcing-list generation;
- SUMMA model-input generation.

Both configurations are stored under the same `domain_<DOMAIN>` directory but in separate subdirectories. This provides a common source-data provenance while preventing distributed and lumped products from overwriting one another.

The design is particularly useful for controlled experiments comparing the effects of spatial discretization while holding meteorological inputs, model configuration, and other experimental choices as consistent as possible.

## SUMMA configuration

NAWM-CWARHM automatically generates the model-specific files required by SUMMA.

Major outputs include:

```text
fileManager.txt
forcingFileList.txt
coldState.nc
trialParams.nc
attributes.nc
modelDecisions.txt
outputControl.txt
localParamInfo.txt
basinParamInfo.txt
```

together with the required parameter tables.

The workflow populates `attributes.nc` using the geospatial information generated during the preceding stages, including:

- HRU and GRU identifiers;
- HRU area;
- latitude and longitude;
- elevation;
- soil type;
- vegetation type;
- HRU connectivity.

The revised scripts maintain a consistent HRU ordering between forcing, attributes, initial conditions, and parameter files.

They are also designed to operate correctly for both large domains and edge cases such as a domain containing only one HRU.

Separate runtime-generation utilities are available for distributed and lumped configurations and for simulations using the LST forcing products.

Additional cold-state utilities are provided for experiments in which an existing/reference SUMMA initial state must be transferred to a newly generated configuration while preserving the physical state structure. These utilities are intended for controlled compatibility and reproducibility experiments rather than replacing the standard cold-state generation workflow.

## Repository organization

The main workflow directories are:

```text
00_prepare_domain_shapefiles/   Domain/control/task and lumped-domain preparation
0_control_files/                Distributed/lumped controls and task inventories
0_example/                      Example/reference configuration
0_tools/                        Shared workflow utilities
1_folder_prep/                  Domain directory creation
2_install/                      Environment and model installation
3a_forcing/                     Meteorological preparation, concatenation, UTC→LST conversion, and archival
3b_parameters/                  DEM, soil and land-cover preparation
4a_sort_shape/                  Spatial preprocessing
4b_remapping/                   Distributed/lumped HRU parameter and forcing remapping
5_model_input/                  Distributed/lumped SUMMA and mizuRoute input generation
6_model_runs/                   SUMMA–mizuRoute execution
7_visualization/                Visualization and analysis
extra_functions/                Optional compatibility and reproducibility utilities
```

The detailed contents and exact execution sequence are described in the NAWM-CWARHM workflow manual included separately in this repository.

## Typical model-domain structure

Processed domains maintain distributed products directly under the domain root and lumped products in a separate `lumped/` subdirectory:

```text
domain_<DOMAIN>/
├── forcing/           # Distributed products
├── parameters/        # Distributed products
├── shapefiles/        # Distributed products
├── settings/          # Distributed products
├── simulations/       # Distributed products
└── lumped/
    ├── forcing/
    ├── parameters/
    ├── shapefiles/
    ├── settings/
    └── simulations/
```

Within the forcing workflow, separate processing layers preserve intermediate and final products, including monthly forcing, concatenated UTC forcing, and local-standard-time forcing.

Conceptually:

```text
forcing/
├── monthly SUMMA forcing
├── concatenated UTC forcing
└── concatenated LST forcing
```

The exact directory names and stage numbering are documented in the workflow manual.

This standardized organization allows the same processing and execution scripts to operate across many model domains while keeping distributed and lumped configurations and UTC/LST forcing products clearly separated.

## Workflow manual

The README provides the conceptual overview and architecture of NAWM-CWARHM.

Detailed operational instructions maintained separately in the repository as the workflow manual.

The manual contains:

- environment activation;
- domain selection and inventory-driven control-file generation;
- distributed and lumped control generation;
- distributed and lumped basin/month task generation;
- reusable batch configuration;
- distributed and lumped domain preparation;
- ERA5 and EM-Earth source preparation;
- precipitation-product selection;
- forcing-remapping-weight generation;
- monthly forcing remapping;
- final SUMMA forcing assembly;
- forcing concatenation;
- UTC-to-LST conversion;
- post-processing archival of monthly forcing and workflow logs;
- DEM, soil, and MODIS preparation;
- distributed and lumped HRU parameter extraction;
- SUMMA and mizuRoute input generation;
- LST-aware SUMMA runtime generation;
- optional cold-state compatibility utilities;
- final model-input verification;
- Slurm submission and monitoring examples;
- output checks and acceptance criteria.

Machine-specific ARC paths, example basin collections, test job IDs, Slurm limits, and detailed command sequences belong in the manual rather than in this README.

## References

Clark, M. P., Nijssen, B., Lundquist, J. D., Kavetski, D., Rupp, D. E., Woods, R. A., et al. (2015a). A unified approach for process-based hydrologic modeling: 1. Modeling concept. **Water Resources Research**, **51**, 2498–2514. https://doi.org/10.1002/2015WR017198

Clark, M. P., Nijssen, B., Lundquist, J. D., Kavetski, D., Rupp, D. E., Woods, R. A., et al. (2015b). A unified approach for process-based hydrologic modeling: 2. Model implementation and case studies. **Water Resources Research**, **51**, 2515–2542. https://doi.org/10.1002/2015WR017200

Knoben, W. J. M., Clark, M. P., Bales, J., Bennett, A., Gharari, S., Marsh, C. B., Nijssen, B., Pietroniro, A., Spiteri, R. J., Tang, G., Tarboton, D. G., & Wood, A. W. (2022). Community Workflows to Advance Reproducibility in Hydrologic Modeling: Separating model-agnostic and model-specific configuration steps in applications of large-domain hydrologic models. **Water Resources Research**, **58**, e2021WR031753. https://doi.org/10.1029/2021WR031753

Lin, P., Pan, M., Beck, H. E., Yang, Y., Yamazaki, D., Frasson, R., et al. (2019). Global reconstruction of naturalized river flows at 2.94 million reaches. **Water Resources Research**, **55**, 6499–6516. https://doi.org/10.1029/2019WR025287

Mizukami, N., Clark, M. P., Sampson, K., Nijssen, B., Mao, Y., McMillan, H., et al. (2016). mizuRoute version 1: A river network routing tool for a continental domain water resources applications. **Geoscientific Model Development**, **9**, 2223–2238. https://doi.org/10.5194/gmd-9-2223-2016

Yamazaki, D., Ikeshima, D., Sosa, J., Bates, P. D., Allen, G. H., & Pavelsky, T. M. (2019). MERIT Hydro: A high-resolution global hydrography map based on latest topography dataset. **Water Resources Research**, **55**, 5053–5073. https://doi.org/10.1029/2019WR024873
