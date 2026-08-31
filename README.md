# NAWM-CWARHM

**NAWM-CWARHM** is a multi-basin, high-performance-computing extension of the **Community Workflows to Advance Reproducibility in Hydrologic Modeling (CWARHM)** developed by Knoben et al. (2022).

The workflow provides an automated framework for generating and executing **SUMMA–mizuRoute** model configurations for large numbers of river basins across North America as part of the **North American Water Model (NAWM)** project.

NAWM-CWARHM retains the fundamental CWARHM philosophy of separating **model-agnostic data preparation** from **model-specific configuration**, while adding the domain-generation, forcing-processing, batch-management, quality-control, and HPC infrastructure required for repeated multi-basin model production.

The repository is based on the original [`CH-Earth/CWARHM`](https://github.com/CH-Earth/CWARHM) workflow.

---

## Background

CWARHM was developed as a reproducible framework for configuring large-domain hydrological models. The original implementation couples:

- **SUMMA** — Structure for Unifying Multiple Modeling Alternatives (Clark et al., 2015a,b)
- **mizuRoute** — river-network routing model (Mizukami et al., 2016)

Knoben et al. (2022) demonstrated that CWARHM can be applied from local catchments to continental and global domains, including a North American configuration containing more than 500,000 sub-basins.

The purpose of NAWM-CWARHM is therefore **not simply to increase the spatial scale of CWARHM**. Instead, it operationalizes the CWARHM architecture for repeated model production across many North American river basins.

Major additions include:

- automated generation of basin-specific control files;
- support for different domain inventories, including MERIT/Pfaf and CAMELS-SPAT basins;
- automated preparation of CWARHM-compatible domain shapefiles;
- reusable basin-level and month-level task inventories;
- shared continental geospatial datasets;
- combined ERA5 and EM-Earth meteorological forcing;
- reusable EASYMORE spatial-remapping weights;
- large Slurm-array forcing workflows;
- automated DEM, soil, and land-cover preprocessing;
- automated HRU parameter extraction;
- multi-basin SUMMA and mizuRoute input generation;
- support for domains containing a single HRU/river segment as well as large multi-HRU domains;
- explicit handling and validation of MERIT river-network topology;
- systematic verification between workflow stages;
- coordinated HPC execution of large collections of basins.

---

# Workflow architecture

NAWM-CWARHM organizes processing into a sequence of reproducible stages:

```text
Domain inventory
      ↓
Generate basin control files
      ↓
Generate basin + monthly task inventories
      ↓
Prepare domain shapefiles and forcing grids
      ↓
Prepare ERA5 + EM-Earth monthly forcing
      ↓
Create spatial-remapping weights
      ↓
Remap forcing to HRUs
      ↓
Assemble final SUMMA forcing
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

The important architectural change is that processing is **task-driven rather than basin-script-driven**. The same workflow scripts can therefore operate on different collections of basins without rewriting the underlying processing code.

---

# Multi-basin processing

A major extension of NAWM-CWARHM is the introduction of reusable **basin and month task files**.

For a selected collection of domains, the workflow generates:

```text
multibasin_preprocessing_<BATCH>.txt
month_tasks_<BATCH>.txt
```

The basin task file defines one model domain per task, while the monthly task file defines one **domain-month combination per task**.

For example, five basins with forcing from 1950–2019 contain:

```text
5 basins × 840 months = 4200 monthly tasks
```

These task inventories can then be supplied directly to Slurm-array runners.

A reusable `set_batch.sh` configuration exposes:

```bash
BASIN_TASK
MONTH_TASK
NBASIN
NMONTH
```

so subsequent workflow stages operate on the currently selected batch without hard-coding basin names.

This design allows the same processing infrastructure to be used for a small test collection or a much larger production set.

---

# Domain inventories and control-file generation

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

This separates:

**domain inventory → domain configuration → model processing**

and substantially reduces manual control-file editing.

---

# Domain preparation

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

This makes spatial-domain preparation part of the reproducible workflow rather than an external GIS prerequisite.

---

# Meteorological forcing

NAWM-CWARHM uses meteorological information from both **ERA5** and **EM-Earth**.

The forcing workflow is divided into three computational stages.

### 1. Source preparation

Raw ERA5 and EM-Earth archives are converted into standardized monthly files for each domain.

### 2. Spatial remapping

Reusable EASYMORE remapping weights are generated once for each basin and forcing product.

Monthly meteorological files are subsequently remapped to the model HRUs using Slurm arrays.

### 3. SUMMA forcing assembly

The remapped variables are combined into monthly SUMMA forcing files:

```text
NWAM_SUMMA_forcing_YYYYMM.nc
```

For the current 1950–2019 configuration this produces:

```text
840 monthly forcing files per basin
```

with hourly meteorological data.

The final forcing combines variables supplied by the two meteorological products into a common SUMMA-compatible dataset.

This separation of source preparation, spatial remapping, and final assembly makes large forcing workflows restartable and allows failed domain-month tasks to be rerun independently.

---

# Shared continental datasets

Processing many basins independently can create large amounts of duplicated source data.

NAWM-CWARHM therefore supports centrally maintained datasets on HPC systems.

Examples include:

- MERIT-Hydro elevation data;
- soil-class rasters;
- MODIS MCD12Q1 land cover;
- ERA5 meteorological archives;
- EM-Earth meteorological archives.

For MERIT-Hydro, existing elevation tiles can be linked from a shared archive rather than copied separately into every model domain.

This approach reduces:

- storage requirements;
- repeated downloads;
- duplicated preprocessing;
- unnecessary filesystem operations.

The specific shared-data paths used on the University of Calgary ARC system are deployment-specific and are documented in the workflow manual rather than assumed to be portable to other systems.

---

# Geospatial parameter preparation

For every basin, NAWM-CWARHM prepares three primary geospatial parameter products:

```text
parameters/dem/5_elevation/elevation.tif

parameters/soilclass/2_soil_classes_domain/soil_classes.tif

parameters/landclass/7_mode_land_class/land_classes.tif
```

These are derived from:

- **MERIT-Hydro** elevation;
- soil-class information;
- **MODIS MCD12Q1** land cover.

The domain rasters are subsequently intersected with the HRUs to derive:

- mean HRU elevation;
- HRU soil-class distributions;
- HRU land-cover distributions.

These products are written to standardized HRU-intersection shapefiles and subsequently used to populate SUMMA attributes.

---

# SUMMA configuration

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

---

# mizuRoute configuration

NAWM-CWARHM generates mizuRoute topology directly from the prepared river-network information.

The principal routing products are:

```text
topology.nc
mizuroute.control
param.nml.default
```

The topology contains information including:

```text
segId
downSegId
slope
length
hruId
hruToSegId
area
```

The revised network workflow handles MERIT-style:

```text
COMID
NextDownID
```

relationships and explicitly checks whether downstream segment identifiers remain inside the model domain.

Downstream links leaving the selected routing domain are represented as routing outlets rather than invalid internal links.

The workflow also verifies that every HRU-to-segment relationship points to a valid routing segment.

For configurations in which SUMMA HRUs already correspond directly to routing units:

```text
river_basin_needs_remap | no
```

and an additional SUMMA-to-mizuRoute remapping file is unnecessary.

---

# HPC and Slurm-array processing

NAWM-CWARHM is designed for execution on HPC systems and has been developed and tested using the University of Calgary **ARC** cluster.

Parallelization occurs at multiple levels.

### Basin-level arrays

Operations that need to run once per basin use one Slurm task per model domain.

Examples include:

- domain preparation;
- forcing-remapping-weight generation;
- DEM/soil/MODIS preparation;
- HRU parameter extraction;
- SUMMA/mizuRoute input generation.

### Domain-month arrays

Large meteorological workflows use one task per domain-month combination.

Examples include:

- ERA5 preparation;
- EM-Earth preparation;
- ERA5 HRU remapping;
- EM-Earth HRU remapping;
- final forcing assembly.

For thousands of tasks, arrays can be submitted in chunks and concurrency can be controlled with standard Slurm array throttling.

This structure makes individual failures recoverable without repeating successful work for other basins or months.

---

# Verification and quality control

Verification is treated as an explicit part of the workflow rather than an optional post-processing step.

Checks are performed between major stages to confirm that expected products exist and contain internally consistent information.

Examples include:

### Forcing

- expected monthly file count;
- correct first and last month;
- hourly timestep;
- required meteorological variables;
- correct HRU count.

### SUMMA

- required settings files exist;
- `attributes.nc`, `coldState.nc`, and `trialParams.nc` contain the expected HRUs;
- HRU ordering agrees with forcing;
- soil type is populated;
- vegetation type is populated;
- elevation is finite and populated.

### mizuRoute

- expected routing segments exist;
- downstream connectivity is valid;
- outlets are represented correctly;
- HRU-to-segment mappings are valid;
- slope and length fields are populated.

This is particularly important for automated processing because successful completion of a Slurm task alone does not guarantee that the resulting hydrological model configuration is internally consistent.

---

# Model execution

The NAWM execution architecture coordinates SUMMA and mizuRoute rather than treating them as independent model runs.

The model sequence is:

```text
SUMMA array execution
        ↓
merge SUMMA outputs
        ↓
mizuRoute
        ↓
verification
```

The Stage 6 workflow includes dedicated preparation and submission utilities and a separate SUMMA-output merge stage before routing.

This ensures that mizuRoute receives a complete runoff dataset even when SUMMA calculations have been distributed across multiple compute tasks.

---

# Major differences from original CWARHM

| Component | Original CWARHM | NAWM-CWARHM |
|---|---|---|
| Scientific architecture | Model-agnostic preparation followed by SUMMA/mizuRoute configuration | Retained |
| Spatial scale | Local to global | Multi-basin North American production |
| Spatial discretization | Supplied externally | Integrated domain-preparation stage |
| Domain configuration | Individual application controls | Inventory-driven automatic control generation |
| Domain inventories | Not central to workflow | MERIT/Pfaf, CENTURY, and extensible inventories |
| Batch definition | Application-oriented | Reusable basin and month task files |
| Meteorological forcing | Primarily ERA5 | Combined ERA5 + EM-Earth workflow |
| Forcing processing | Application processing | Domain-month Slurm arrays |
| Spatial forcing remapping | CWARHM remapping | Reusable EASYMORE weights + parallel monthly remapping |
| Forcing assembly | Original CWARHM structure | Dedicated monthly SUMMA assembly stage |
| DEM | MERIT-Hydro processing | Shared archive reuse + automated basin processing |
| Soil/land cover | CWARHM processing | Automated multi-basin raster + HRU extraction |
| SUMMA inputs | Generated per application | Automated multi-basin generation |
| HRU identifiers | Application dependent | Standardized and explicitly validated |
| Single-HRU domains | Not a primary production target | Explicitly supported |
| mizuRoute topology | User-supplied network basis | Automated MERIT-style topology construction and validation |
| HPC processing | Supports scalable execution | Basin/month task architecture + Slurm arrays |
| SUMMA outputs | Standard execution | Distributed execution + dedicated merge stage |
| Verification | Workflow-dependent | Explicit checks throughout processing |
| Primary objective | General reproducible model configuration | Automated and repeatable North American model production |

---

# Repository organization

The main workflow directories are:

```text
00_prepare_domain_shapefiles/   Domain/control/task preparation
0_control_files/                Domain controls and task inventories
0_example/                      Example/reference configuration
0_tools/                        Shared workflow utilities
1_folder_prep/                  Domain directory creation
2_install/                      Environment and model installation
3a_forcing/                     Meteorological source preparation
3b_parameters/                  DEM, soil and land-cover preparation
4a_sort_shape/                  Spatial preprocessing
4b_remapping/                   HRU parameter and forcing remapping
5_model_input/                  SUMMA and mizuRoute input generation
6_model_runs/                   SUMMA–mizuRoute execution
7_visualization/                Visualization and analysis
```

The detailed contents and exact execution sequence are described in the **NAWM-CWARHM workflow manual** included separately in this repository.

---

# Typical model-domain structure

Processed domains are maintained independently:

```text
domain_<DOMAIN>/
├── forcing/
│   ├── 1_raw_data/
│   ├── 3_basin_averaged_data/
│   └── 4_SUMMA_input/
├── parameters/
│   ├── dem/
│   ├── soilclass/
│   └── landclass/
├── shapefiles/
│   ├── catchment/
│   ├── river_network/
│   └── catchment_intersection/
├── settings/
│   ├── SUMMA/
│   └── mizuRoute/
└── simulations/
```

This standardized organization allows the same processing and execution scripts to operate across many model domains.

---

# Workflow manual

The README provides the **conceptual overview and architecture** of NAWM-CWARHM.

Detailed operational instructions should be maintained separately in the repository as the workflow manual.

The manual contains:

1. environment activation;
2. domain selection and control-file generation;
3. basin/month task generation;
4. reusable batch configuration;
5. domain and forcing-grid preparation;
6. ERA5 and EM-Earth source preparation;
7. forcing-remapping-weight generation;
8. monthly forcing remapping;
9. final SUMMA forcing assembly;
10. DEM, soil, and MODIS preparation;
11. HRU parameter extraction;
12. SUMMA and mizuRoute input generation;
13. final model-input verification;
14. Slurm submission and monitoring examples;
15. output checks and acceptance criteria.

Machine-specific ARC paths, example basin collections, test job IDs, Slurm limits, and detailed command sequences belong in the manual rather than in this README.

---

# Portability

NAWM-CWARHM has been developed for the NAWM computing environment on ARC, but the scientific workflow is not inherently restricted to that system.

To deploy elsewhere, users will generally need to modify:

- source-data paths;
- output-root paths;
- environment/module initialization;
- Slurm account and resource settings;
- locations of SUMMA and mizuRoute executables;
- shared dataset configuration.

The distinction between **workflow logic** and **deployment-specific paths/settings** is intentionally maintained to facilitate future deployment on other HPC systems.

---

# Relationship to CWARHM

NAWM-CWARHM should be viewed as an extension of CWARHM rather than a replacement for it.

**Original CWARHM**

A general, modular, reproducible framework for configuring hydrological models across local to global domains. It establishes the separation between model-agnostic data preparation and model-specific SUMMA/mizuRoute configuration.

**NAWM-CWARHM**

Retains this scientific and organizational framework while adding the infrastructure required for repeated North American model production: domain inventories, automatic control generation, MERIT-based hydrography preparation, combined ERA5/EM-Earth forcing, shared datasets, reusable remapping, multi-basin task management, Slurm-array processing, topology validation, automated model-input generation, coordinated SUMMA–mizuRoute execution, and systematic verification.

The principal contribution of NAWM-CWARHM is therefore **automation, standardization, computational scalability, robustness, and repeatability across large collections of river basins**.

---

# Citation and acknowledgement

Users of NAWM-CWARHM should cite the original CWARHM publication:

> Knoben, W. J. M., Clark, M. P., Bales, J., Bennett, A., Gharari, S., Marsh, C. B., Nijssen, B., Pietroniro, A., Spiteri, R. J., Tang, G., Tarboton, D. G., & Wood, A. W. (2022). Community Workflows to Advance Reproducibility in Hydrologic Modeling: Separating model-agnostic and model-specific configuration steps in applications of large-domain hydrologic models. *Water Resources Research*, **58**, e2021WR031753. https://doi.org/10.1029/2021WR031753

The original CWARHM repository is available at:

[`CH-Earth/CWARHM`](https://github.com/CH-Earth/CWARHM)

---

# References

Clark, M. P., Nijssen, B., Lundquist, J. D., Kavetski, D., Rupp, D. E., Woods, R. A., et al. (2015a). A unified approach for process-based hydrologic modeling: 1. Modeling concept. *Water Resources Research*, **51**, 2498–2514. https://doi.org/10.1002/2015WR017198

Clark, M. P., Nijssen, B., Lundquist, J. D., Kavetski, D., Rupp, D. E., Woods, R. A., et al. (2015b). A unified approach for process-based hydrologic modeling: 2. Model implementation and case studies. *Water Resources Research*, **51**, 2515–2542. https://doi.org/10.1002/2015WR017200

Knoben, W. J. M., Clark, M. P., Bales, J., Bennett, A., Gharari, S., Marsh, C. B., Nijssen, B., Pietroniro, A., Spiteri, R. J., Tang, G., Tarboton, D. G., & Wood, A. W. (2022). Community Workflows to Advance Reproducibility in Hydrologic Modeling: Separating model-agnostic and model-specific configuration steps in applications of large-domain hydrologic models. *Water Resources Research*, **58**, e2021WR031753. https://doi.org/10.1029/2021WR031753

Lin, P., Pan, M., Beck, H. E., Yang, Y., Yamazaki, D., Frasson, R., et al. (2019). Global reconstruction of naturalized river flows at 2.94 million reaches. *Water Resources Research*, **55**, 6499–6516. https://doi.org/10.1029/2019WR025287

Mizukami, N., Clark, M. P., Sampson, K., Nijssen, B., Mao, Y., McMillan, H., et al. (2016). mizuRoute version 1: A river network routing tool for a continental domain water resources applications. *Geoscientific Model Development*, **9**, 2223–2238. https://doi.org/10.5194/gmd-9-2223-2016

Yamazaki, D., Ikeshima, D., Sosa, J., Bates, P. D., Allen, G. H., & Pavelsky, T. M. (2019). MERIT Hydro: A high-resolution global hydrography map based on latest topography dataset. *Water Resources Research*, **55**, 5053–5073. https://doi.org/10.1029/2019WR024873
