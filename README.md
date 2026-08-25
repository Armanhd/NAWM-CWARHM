# CWARHM for the North American Water Model (NAWM)

## Background and origin of the workflow

This repository is a modified version of the **Community Workflows to Advance Reproducibility in Hydrologic Modeling (CWARHM)** workflow developed by Knoben et al. (2022). The present repository was forked from the original [`CH-Earth/CWARHM`](https://github.com/CH-Earth/CWARHM) repository and retains the overall philosophy and structure of CWARHM while extending the workflow for application within the **North American Water Model (NAWM)** project.

CWARHM was developed as a reproducible model-configuration workflow that separates **model-agnostic data preparation** from **model-specific configuration**. The original workflow couples the **Structure for Unifying Multiple Modeling Alternatives (SUMMA)** hydrological model (Clark et al., 2015a,b) with the **mizuRoute** river-routing model (Mizukami et al., 2016).

The original CWARHM workflow was designed to be general and scalable. Knoben et al. (2022) demonstrated the workflow for local, continental, and global applications, including a North American configuration containing more than 500,000 sub-basins. The objective of the NAWM modifications is therefore not simply to increase the spatial scale of CWARHM. Instead, the revisions provide the additional **domain-generation, data-management, forcing-processing, and high-performance-computing infrastructure** required to repeatedly configure and execute SUMMA–mizuRoute simulations for many MERIT-Basins domains across North America.

The original CWARHM workflow and its scientific rationale are described in:

> Knoben, W. J. M., Clark, M. P., Bales, J., Bennett, A., Gharari, S., Marsh, C. B., Nijssen, B., Pietroniro, A., Spiteri, R. J., Tang, G., Tarboton, D. G., & Wood, A. W. (2022). Community Workflows to Advance Reproducibility in Hydrologic Modeling: Separating model-agnostic and model-specific configuration steps in applications of large-domain hydrologic models. *Water Resources Research*, **58**, e2021WR031753. https://doi.org/10.1029/2021WR031753

The original CWARHM repository should be consulted for the conceptual basis of the workflow, detailed descriptions of its original components, and the original local, continental, and global test cases.

---

# NAWM extensions to CWARHM

The NAWM version retains the fundamental CWARHM architecture and continues to use **SUMMA for hydrological simulation and mizuRoute for river-network routing**. The main modifications concern how model domains, geospatial parameters, meteorological forcing, model inputs, and simulations are prepared and executed.

The changes are designed to support repeated model configuration across MERIT-Basins domains using shared datasets and high-performance computing resources on the University of Calgary ARC cluster.

## Summary of major modifications

| CWARHM step | Original CWARHM | Revised NAWM-CWARHM | Main benefit |
|---|---|---|---|
| **0. Domain definition** | Users provide pre-existing catchment/HRU and river-network shapefiles. Spatial discretization is outside the original workflow scope. | New `00_prepare_domain_shapefiles/` stage constructs CWARHM-compatible catchment and river-network shapefiles from MERIT-Basins, creates required attributes, preserves network topology, and reports control-file values. | Enables systematic generation of many MERIT/Pfaf modelling domains with substantially less manual GIS preparation. |
| **1. Folder preparation** | Creates the CWARHM data-directory structure for a specified modelling domain. | `make_folder_structure.py` revised for the standardized NAWM domain structure and repeated processing of MERIT domains. | Provides consistent organization across large numbers of model domains. |
| **2. Software/environment** | Uses the original `environment.yml` and associated SUMMA/mizuRoute installation procedures. | Dedicated `environment_nwam.yml`, `create_nwam_env.sh`, and `update_nwam_env.sh`; SUMMA and mizuRoute clone/compile scripts revised for ARC. | Provides a reproducible HPC environment and reduces dependency and compiler inconsistencies. |
| **3. Meteorological forcing** | ERA5 is the primary meteorological forcing dataset. | Explicit ERA5 and **EM-Earth** pathways are supported, with EM-Earth used as the primary forcing source for NAWM applications. | Supports long-term EM-Earth simulations while retaining ERA5 as an alternative forcing product. |
| **3. Forcing preparation** | Downloads and prepares forcing for the selected modelling application. | Added `run_prepare_forcing.sh` and separate ERA5/EM-Earth processing pathways designed around shared forcing archives on ARC. | Reduces repeated data preparation and supports repeated processing of many domains. |
| **3b. MERIT Hydro DEM** | MERIT-Hydro elevation tiles are downloaded and processed as part of the workflow. | Added `0_link_existing_tiles.py` so existing MERIT-Hydro tiles in the shared ARC data archive can be linked and reused; VRT, subsetting, and conversion scripts were revised accordingly. | Avoids duplicate copies of large datasets and reduces both storage requirements and preprocessing time. |
| **3b. MODIS land cover** | Standard CWARHM MODIS VRT, reprojection, subsetting, and land-class processing. | MODIS processing scripts revised for the ARC/NAWM directory structure and repeated processing of large MERIT domains. | Improves robustness and repeatability of land-cover parameter extraction. |
| **4. HRU parameter extraction** | Elevation, soil, and land-cover properties are mapped to user-provided HRUs. | Elevation, soil-class, and land-class scripts substantially revised for MERIT-based HRUs, standardized identifiers, and large domain sizes. | Provides scalable and consistent HRU-level parameter generation. |
| **4b. Forcing remapping** | Original forcing-remapping workflow does not contain the new dedicated ERA5/EM-Earth Slurm-array framework. | Added separate ERA5 and EM-Earth remapping scripts together with `run_remap_ERA5_array.sh` and `run_remap_EM_Earth_array.sh`. | Allows many forcing files to be remapped concurrently on ARC. |
| **4b. Forcing assembly** | Forcing preparation and assembly follow the original CWARHM processing structure. | Added `3_combine_forcing_for_SUMMA.py` and `run_combine_forcing_array.sh` to assemble remapped forcing into SUMMA-ready files. | Separates computationally expensive remapping from final forcing assembly and facilitates restart/recovery. |
| **5. SUMMA input generation** | Generates SUMMA file manager, forcing lists, initial conditions, trial parameters, and attribute files. | SUMMA-input scripts revised to operate consistently with NAWM control files, MERIT domains, forcing products, and standardized HRU identifiers. | Allows the same input-generation procedure to be reused across many domains. |
| **5. SUMMA attributes** | Soil, vegetation, elevation, and other HRU properties are inserted into SUMMA attributes using the original CWARHM structure. | Attribute initialization and parameter-insertion scripts revised to maintain consistent HRU identifiers and parameter mappings across NAWM domains. | Reduces identifier/order mismatches and improves reproducibility. |
| **5. mizuRoute inputs** | Creates topology and control files from the river-network information supplied by the user. | Network-topology and control-file generation extensively revised for MERIT-Basins networks, including `COMID`, `NextDownID`, and HRU-to-segment relationships. | Enables systematic construction of mizuRoute networks directly from MERIT hydrography. |
| **6. SUMMA execution** | Provides SUMMA execution, including array-based execution capabilities. | `1_run_summa_as_array.sh` revised and incorporated into a coordinated Stage 6 Slurm workflow. | Enables efficient parallel execution of large MERIT domains on ARC. |
| **6. SUMMA output handling** | No equivalent dedicated merge stage in the original Stage 6 sequence. | Added `2_merge_summa_array_outputs.py` and `2_merge_summa_array_outputs.sh`. | Allows distributed SUMMA outputs to be automatically assembled before river routing. |
| **6. mizuRoute execution** | `2_run_mizuRoute.sh` follows SUMMA execution. | Routing moved to `3_run_mizuRoute.sh` after SUMMA-output merging. | Explicitly enforces the sequence SUMMA arrays → merge → mizuRoute. |
| **6. Batch orchestration** | Individual workflow/model-run scripts require more direct user execution. | Added `0_prepare_stage6.py` and `0_submit_stage6.sh` for preparation and submission of the Stage 6 workflow. | Reduces manual job management and makes large-domain simulations repeatable. |
| **6. Verification** | No dedicated final Stage 6 verification script. | Added `4_verify_stage6.py`. | Systematically detects missing, incomplete, or failed SUMMA/mizuRoute simulations. |
| **Overall processing approach** | General reproducible workflow capable of local through global model configuration, but requiring externally prepared spatial discretizations and substantial user interaction between processing stages. | MERIT-based domain generation, shared continental datasets, EM-Earth/ERA5 support, standardized inputs, Slurm-array processing, staged SUMMA–mizuRoute execution, and automated verification. | Provides an operational framework for repeatedly configuring and executing hydrological simulations across North American MERIT domains. |

---

## Domain preparation

One of the most important differences between the original and NAWM workflows occurs **before the original CWARHM processing sequence begins**.

The original CWARHM implementation deliberately excludes spatial discretization from its scope. Users are expected to provide a shapefile containing the SUMMA GRU/HRU discretization and a corresponding river-network shapefile for mizuRoute.

For NAWM, a new `00_prepare_domain_shapefiles/` stage was therefore introduced. This stage derives CWARHM-compatible catchment and river-network datasets from **MERIT-Basins** and constructs the attributes required by the subsequent CWARHM workflow, including `COMID`, `GRU_ID`, `HRU_ID`, HRU area, downstream connectivity, and HRU-to-segment relationships. It also reports spatial information required by the CWARHM control file.

**Benefit:** Domain generation becomes part of the reproducible workflow rather than an external prerequisite. This makes it practical to generate consistent configurations for many MERIT/Pfaf domains.

## Shared continental parameter datasets

The original CWARHM workflow downloads and processes the datasets required for a modelling application. This approach is convenient for independent applications but can result in unnecessary duplication when many domains are processed on the same HPC system.

The NAWM workflow therefore makes greater use of datasets maintained centrally on ARC. For example, existing MERIT-Hydro DEM tiles can be linked from the shared data archive rather than downloaded or duplicated for each modelling domain. MERIT DEM and MODIS processing scripts were revised to accommodate this shared-data structure.

**Benefit:** Large source datasets can be stored once and reused across domains, substantially reducing storage requirements, data duplication, and preprocessing time.

## HRU parameter extraction

CWARHM maps model-agnostic geospatial information to the HRUs required by SUMMA. The NAWM revision retains this concept but substantially revises the elevation, soil-class, and land-cover extraction scripts for MERIT-based HRUs, standardized identifiers, larger domains, and repeated automated execution.

**Benefit:** HRU parameter generation can be performed consistently across many domains without basin-specific modifications to the processing scripts.

## Meteorological forcing

The original CWARHM implementation uses **ERA5** meteorological forcing. The NAWM workflow adds an explicit **EM-Earth** pathway while retaining ERA5 support.

Dedicated scripts separately process ERA5 and EM-Earth forcing. Spatial remapping is also separated from final forcing-file assembly. Individual forcing files can be remapped concurrently using Slurm arrays before being combined into SUMMA-ready forcing datasets.

**Benefit:** Large numbers of meteorological files and long simulation periods can be processed efficiently on ARC. EM-Earth can serve as the standard NAWM forcing product while ERA5 remains available for alternative experiments and comparisons.

## SUMMA input generation

The underlying role of the SUMMA input-generation stage remains unchanged. CWARHM creates the file manager, forcing-file list, initial conditions, trial parameters, and attributes required by SUMMA.

The NAWM modifications adapt these scripts to the standardized NAWM directory structure, MERIT identifiers, revised forcing products, and parameter-extraction outputs.

**Benefit:** A common SUMMA configuration procedure can be applied repeatedly to different North American domains without manually rewriting paths or adapting individual scripts.

## mizuRoute network preparation

The original CWARHM workflow constructs mizuRoute inputs from a river-network shapefile supplied by the user. In the NAWM implementation, the network topology and mizuRoute control-file scripts were expanded to work systematically with MERIT-Basins hydrography.

The revised workflow handles MERIT `COMID` identifiers, `NextDownID` connectivity, and HRU-to-river-segment relationships consistently throughout domain preparation and routing-input generation.

**Benefit:** mizuRoute networks can be constructed reproducibly from a common continental hydrographic framework while preserving downstream river connectivity.

## Parallel model execution

The NAWM revision introduces a more coordinated HPC execution strategy for the SUMMA–mizuRoute model chain. SUMMA calculations are distributed using Slurm arrays, and dedicated scripts prepare and submit Stage 6 jobs.

Parallel SUMMA execution can produce multiple output components. A new merge stage therefore assembles these outputs before they are passed to mizuRoute.

The resulting model-execution sequence is:

**SUMMA array simulations → merge SUMMA outputs → mizuRoute simulation → verification**

**Benefit:** Large model domains can be distributed across ARC compute resources while ensuring that routing begins only after all required SUMMA results have been successfully assembled.

## Automated verification

The revised Stage 6 workflow concludes with an automated verification step that checks whether the expected SUMMA and mizuRoute outputs were successfully generated.

**Benefit:** Failed or incomplete jobs can be identified systematically, which is particularly important when processing large numbers of domains or Slurm-array tasks.

---

## Overall significance

The original CWARHM should not be characterized simply as a small-catchment or sequential workflow. Knoben et al. (2022) explicitly demonstrated that CWARHM could configure models from the local to global scale, including a continental North American experiment.

The distinction is instead that the **NAWM-CWARHM workflow operationalizes and extends this architecture for repeated North American model production**.

In summary:

**Original CWARHM:** A general, reproducible and modular framework for configuring SUMMA and mizuRoute across local to global domains. Spatial discretization is supplied externally, ERA5 provides meteorological forcing, and the workflow provides the model-agnostic and model-specific processing required to construct hydrological simulations.

**NAWM-CWARHM:** Retains the CWARHM scientific and organizational framework but adds reproducible MERIT-based domain generation, shared continental data management, EM-Earth forcing support, standardized MERIT identifiers, parallel forcing processing, coordinated Slurm execution, SUMMA-output merging, and automated run verification.

The NAWM modifications therefore primarily address **automation, standardization, computational scalability, and repeated production**, allowing CWARHM to serve as the model-configuration and execution framework for hydrological simulations across North American river basins.

## References

Clark, M. P., Nijssen, B., Lundquist, J. D., Kavetski, D., Rupp, D. E., Woods, R. A., et al. (2015a). A unified approach for process-based hydrologic modeling: 1. Modeling concept. *Water Resources Research*, **51**, 2498–2514. https://doi.org/10.1002/2015WR017198

Clark, M. P., Nijssen, B., Lundquist, J. D., Kavetski, D., Rupp, D. E., Woods, R. A., et al. (2015b). A unified approach for process-based hydrologic modeling: 2. Model implementation and case studies. *Water Resources Research*, **51**, 2515–2542. https://doi.org/10.1002/2015WR017200

Knoben, W. J. M., Clark, M. P., Bales, J., Bennett, A., Gharari, S., Marsh, C. B., Nijssen, B., Pietroniro, A., Spiteri, R. J., Tang, G., Tarboton, D. G., & Wood, A. W. (2022). Community Workflows to Advance Reproducibility in Hydrologic Modeling: Separating model-agnostic and model-specific configuration steps in applications of large-domain hydrologic models. *Water Resources Research*, **58**, e2021WR031753. https://doi.org/10.1029/2021WR031753

Lin, P., Pan, M., Beck, H. E., Yang, Y., Yamazaki, D., Frasson, R., et al. (2019). Global reconstruction of naturalized river flows at 2.94 million reaches. *Water Resources Research*, **55**, 6499–6516. https://doi.org/10.1029/2019WR025287

Mizukami, N., Clark, M. P., Sampson, K., Nijssen, B., Mao, Y., McMillan, H., et al. (2016). mizuRoute version 1: A river network routing tool for a continental domain water resources applications. *Geoscientific Model Development*, **9**, 2223–2238. https://doi.org/10.5194/gmd-9-2223-2016

Yamazaki, D., Ikeshima, D., Sosa, J., Bates, P. D., Allen, G. H., & Pavelsky, T. M. (2019). MERIT Hydro: A high-resolution global hydrography map based on latest topography dataset. *Water Resources Research*, **55**, 5053–5073. https://doi.org/10.1029/2019WR024873
