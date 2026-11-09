"""Step 11 spatial attribute module registry.

All external dataset paths are supplied explicitly through control files.
Supports distributed, lumped, or both configurations.
Terrain uses the existing domain DEM; Pelletier uses explicit raster layers.
"""
from pathlib import Path

MODULES = (
    ("terrain", None),
    ("soilgrids", "SOILGRIDS/1_process_soilgrids.py"),
    ("pelletier", "PELLETIER/1_process_pelletier.py"),
    ("glhymps", "GLHYMPS/1_process_glhymps.py"),
    ("hydrolakes", "HYDROLAKES/1_process_hydrolakes.py"),
    ("forest_height", "FOREST_HEIGHT/1_process_forest_height.py"),
    ("glclu2019", "GLCLU2019/1_process_glclu2019.py"),
    ("lgrip30", "LGRIP30/1_process_lgrip30.py"),
    ("lai", "LAI/1_process_lai.py"),
    ("worldclim", "WORLDCLIM/1_process_worldclim.py"),
)

# Pelletier accepts --layer NAME=PATH for each source raster.
# All extractors now support --mode distributed|lumped|both.
PELLETIER_LAYERS = {
    "soil_thickness": "upland_hill-slope_soil_thickness.tif",
    "regolith_thickness": "upland_hill-slope_regolith_thickness.tif",
    "sedimentary_deposit_thickness": "upland_valley-bottom_and_lowland_sedimentary_deposit_thickness.tif",
    "average_soil_and_sedimentary_deposit_thickness": "average_soil_and_sedimentary-deposit_thickness.tif",
}

def output_paths(domain_root: Path, name: str):
    return (
        domain_root / "attributes" / name / f"hru_{name}_attributes.csv",
        domain_root / "lumped/attributes" / name / f"lumped_{name}_attributes.csv",
    )
