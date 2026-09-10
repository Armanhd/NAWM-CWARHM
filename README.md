# NAWM-CWARHM

NAWM-CWARHM is a multi-basin, high-performance-computing extension of the Community Workflows to Advance Reproducibility in Hydrologic Modeling (CWARHM) developed by Knoben et al. (2022).

The workflow provides an automated framework for generating and executing SUMMA–mizuRoute model configurations for large numbers of river basins across North America as part of the North American Water Model (NAWM) project.

NAWM-CWARHM retains the fundamental CWARHM philosophy of separating model-agnostic data preparation from model-specific configuration, while adding the domain-generation, forcing-processing, batch-management, quality-control, and HPC infrastructure required for repeated multi-basin model production.

The repository is based on the original CH-Earth/CWARHM workflow.

## Background

CWARHM was developed as a reproducible framework for configuring large-domain hydrological models. The original implementation couples:

- **SUMMA** — Structure for Unifying Multiple Modeling Alternatives (Clark et al., 2015a,b)
- **mizuRoute** — river-network routing model (Mizukami et al., 2016)

Knoben et al. (2022) demonstrated that CWARHM can be applied from local catchments to continental and global domains, including a North American configuration containing more than 500,000 sub-basins.

The purpose of NAWM-CWARHM is therefore not simply to increase the spatial scale of CWARHM. Instead, it operationalizes the CWARHM architecture for repeated model production across many North American river basins and supports both distributed and lumped representations of individual basins within the same processing framework.

Major additions include:

- automated generation of basin-specific control files from domain inventories;
- support for different domain inventories, including MERIT/Pfaf and CENTURY basins;
- automated preparation of CWARHM-compatible domain shapefiles;
- parallel generation of distributed and lumped basin configurations;
- separate distributed and lumped processing directories within each model domain;
- reusable basin-level and month-level task inventories for both configurations;
- shared continental geospatial datasets;
- combined ERA5 and EM-Earth meteorological forcing;
- control-file selection of the EM-Earth precipitation product;
- support for both standard and bias-corrected EM-Earth precipitation;
- reusable EASYMORE spatial-remapping weights;
- large Slurm-array forcing workflows;
- concatenation of monthly SUMMA forcing into continuous forcing datasets;
- UTC-to-local-standard-time (LST) conversion of forcing;
- automated DEM, soil, and land-cover preprocessing;
- automated HRU parameter extraction for distributed and lumped configurations;
- multi-basin SUMMA and mizuRoute input generation;
- LST-aware SUMMA runtime configuration;
- support for domains containing a single HRU/river segment as well as large multi-HRU domains;
- explicit handling and validation of MERIT river-network topology;
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

For EM-Earth, the precipitation field is selected from the basin control file rather than being hard-coded in the processing script. The workflow can therefore be applied using either the standard precipitation product or an alternative such as bias-corrected precipitation without modifying the forcing code.

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

## Major differences from original CWARHM

| Component | Original CWARHM | NAWM-CWARHM |
|---|---|---|
| Scientific architecture | Model-agnostic preparation followed by SUMMA/mizuRoute configuration | Retained |
| Spatial scale | Local to global | Multi-basin North American production |
| Spatial discretization | Supplied externally | Integrated domain-preparation stage |
| Spatial representations | Application dependent | Parallel distributed and lumped configurations |
| Domain configuration | Individual application controls | Inventory-driven automatic control generation |
| Control generation | Primarily application-specific | Controls generated automatically from basin lists/inventories |
| Domain inventories | Not central to workflow | MERIT/Pfaf, CENTURY, and extensible inventories |
| Batch definition | Application-oriented | Reusable distributed/lumped basin and month task files |
| Meteorological forcing | Primarily ERA5 | Combined ERA5 + EM-Earth workflow |
| Precipitation selection | Application/code dependent | Control-file selectable precipitation product |
| Bias-corrected precipitation | Not central to workflow | Alternative forcing generation using `prcp_corrected` |
| Forcing processing | Application processing | Domain-month Slurm arrays |
| Spatial forcing remapping | CWARHM remapping | Reusable EASYMORE weights + parallel monthly remapping |
| Forcing assembly | Original CWARHM structure | Dedicated monthly SUMMA assembly stage |
| Continuous forcing | Application dependent | Automated monthly forcing concatenation |
| Forcing time basis | Application dependent | UTC product plus optional local standard time product |
| DEM | MERIT-Hydro processing | Shared archive reuse + automated basin processing |
| Soil/land cover | CWARHM processing | Automated multi-basin raster + HRU extraction |
| SUMMA inputs | Generated per application | Automated distributed and lumped generation |
| HRU identifiers | Application dependent | Standardized and explicitly validated |
| Single-HRU domains | Not a primary production target | Explicitly supported through lumped workflow |
| mizuRoute topology | User-supplied network basis | Automated MERIT-style topology construction and validation |
| HPC processing | Supports scalable execution | Basin/month task architecture + Slurm arrays |
| SUMMA outputs | Standard execution | Distributed execution + dedicated merge stage |
| Verification | Workflow-dependent | Explicit checks throughout processing |
| Primary objective | General reproducible model configuration | Automated and repeatable North American model production |

## Repository organization

The main workflow directories are:

```text
00_prepare_domain_shapefiles/   Domain/control/task and lumped-domain preparation
0_control_files/                Distributed/lumped controls and task inventories
0_example/                      Example/reference configuration
0_tools/                        Shared workflow utilities
1_folder_prep/                  Domain directory creation
2_install/                      Environment and model installation
3a_forcing/                     Meteorological preparation, concatenation, and UTC→LST conversion
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

Processed domains maintain distributed and lumped model products separately within the same basin hierarchy:

```text
domain_<DOMAIN>/
├── distributed/
│   ├── forcing/
│   ├── parameters/
│   ├── shapefiles/
│   ├── settings/
│   └── simulations/
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

Detailed operational instructions should be maintained separately in the repository as the workflow manual.

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
- DEM, soil, and MODIS preparation;
- distributed and lumped HRU parameter extraction;
- SUMMA and mizuRoute input generation;
- LST-aware SUMMA runtime generation;
- optional cold-state compatibility utilities;
- final model-input verification;
- Slurm submission and monitoring examples;
- output checks and acceptance criteria.

Machine-specific ARC paths, example basin collections, test job IDs, Slurm limits, and detailed command sequences belong in the manual rather than in this README.
