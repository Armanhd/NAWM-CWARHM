#!/usr/bin/env python3
# coding: utf-8
"""Generate lumped control files from a distributed CWARHM basin task list.

FIR / CAMELS-SPAT-MX example (run from 00_prepare_domain_shapefiles):

    python 0_generate_lumped_multibasin_control_files.py \
        --task-file ../0_control_files/multibasin_preprocessing_CAMELS_MX_all.txt \
        --dry-run

    python 0_generate_lumped_multibasin_control_files.py \
        --task-file ../0_control_files/multibasin_preprocessing_CAMELS_MX_all.txt

Produces control_MX_<ID>_lumped.txt and
lumped_multibasin_preprocessing_CAMELS_MX_all.txt under 0_control_files.

Each output retains the original domain_name, root_path, source catchment,
source data directories, and forcing_emearth_precip. The distributed controls
are read-only. Geometry-dependent *default* output paths are redirected into
root_path/domain_<domain>/lumped/.
"""

import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM_ROOT = SCRIPT_DIR.parent
CONTROL_DIR = CWARHM_ROOT / "0_control_files"
VALID_EMEARTH_PRECIP = {"prcp", "prcp_corrected"}

# Keep consistent with the established lumped workflow. Only rewrite fields
# that have value 'default' in the distributed control.
LUMPED_PATH_SETTINGS = {
    "forcing_shape_path": "lumped/shapefiles/forcing",
    "forcing_geo_path": "lumped/forcing/0_geopotential",
    "forcing_raw_path": "lumped/forcing/1_raw_data",
    "forcing_merged_path": "lumped/forcing/2_merged_data",
    "forcing_easymore_path": "lumped/forcing/3_temp_easymore",
    "forcing_basin_avg_path": "lumped/forcing/3_basin_averaged_data",
    "forcing_summa_path": "lumped/forcing/4_SUMMA_input",
    "parameter_dem_vrt2_path": "lumped/parameters/dem/4_domain_vrt",
    "parameter_dem_tif_path": "lumped/parameters/dem/5_elevation",
    "parameter_soil_domain_path": "lumped/parameters/soilclass/2_soil_classes_domain",
    "parameter_land_vrt3_path": "lumped/parameters/landclass/4_domain_vrt_epsg_4326",
    "parameter_land_vrt4_path": "lumped/parameters/landclass/5_multiband_domain_vrt_epsg_4326",
    "parameter_land_tif_path": "lumped/parameters/landclass/6_tif_multiband",
    "parameter_land_mode_path": "lumped/parameters/landclass/7_mode_land_class",
    "intersect_dem_path": "lumped/shapefiles/catchment_intersection/with_dem",
    "intersect_soil_path": "lumped/shapefiles/catchment_intersection/with_soilgrids",
    "intersect_land_path": "lumped/shapefiles/catchment_intersection/with_modis",
    "intersect_forcing_path": "lumped/shapefiles/catchment_intersection/with_forcing",
    "settings_summa_path": "lumped/settings/SUMMA",
    "experiment_output_summa": "lumped/simulations/run1/SUMMA",
    "experiment_log_summa": "lumped/simulations/run1/SUMMA",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-file", required=True, type=Path,
                        help="Distributed basin task file (one control path per line).")
    parser.add_argument("--output-task-file", type=Path,
                        help="Default: 0_control_files/lumped_<input task filename>.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing lumped controls and task file.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and preview without writing anything.")
    return parser.parse_args()


def read_setting(lines, key):
    values = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "|" in line:
            lhs, rhs = line.split("|", 1)
            if lhs.strip() == key:
                values.append(rhs.split("#", 1)[0].strip())
    if len(values) != 1:
        raise ValueError(f"Expected exactly one '{key}' setting; found {len(values)}.")
    return values[0]


def replace_setting(lines, key, value):
    new_lines = []
    matched = 0
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "|" in line:
            lhs, rhs = line.split("|", 1)
            if lhs.strip() == key:
                matched += 1
                comment = ""
                if "#" in rhs:
                    note = rhs.split("#", 1)[1].strip()
                    if note:
                        comment = f" # {note}"
                new_lines.append(f"{key:<35} | {value}{comment}\n")
                continue
        new_lines.append(line)
    if matched != 1:
        raise ValueError(f"Expected exactly one '{key}' setting; found {matched}.")
    return new_lines


def read_task_file(path):
    if not path.is_file():
        raise FileNotFoundError(f"Distributed basin task file not found: {path}")
    controls = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        control = Path(item).expanduser()
        if not control.is_absolute():
            control = path.parent / control
        control = control.resolve()
        if not control.is_file():
            raise FileNotFoundError(f"Task line {n}: missing control file: {control}")
        controls.append(control)
    if not controls:
        raise ValueError(f"No distributed controls found in {path}")
    if len(set(controls)) != len(controls):
        raise ValueError("Duplicate distributed control paths in task file.")
    return controls


def main():
    args = parse_args()
    task_file = args.task_file.expanduser().resolve()
    source_controls = read_task_file(task_file)
    output_task = (args.output_task_file.expanduser().resolve()
                   if args.output_task_file is not None
                   else CONTROL_DIR / f"lumped_{task_file.name}")

    # Check the task-file collision BEFORE creating any lumped controls.
    if output_task.exists() and not args.overwrite and not args.dry_run:
        raise FileExistsError(
            f"Lumped task file already exists: {output_task}\n"
            "Use --overwrite to regenerate it."
        )

    planned = []
    seen_domains = set()
    print("=" * 78)
    print("GENERATE LUMPED MULTIBASIN CONTROLS")
    print("=" * 78)
    print(f"Input basin task file : {task_file}")
    print(f"Lumped basin task file: {output_task}")
    print(f"Distributed basins    : {len(source_controls)}")
    print(f"Dry run              : {args.dry_run}")
    print(f"Overwrite            : {args.overwrite}")

    # Validate every domain and assemble all outputs before writing anything.
    for source_control in source_controls:
        lines = source_control.read_text().splitlines(keepends=True)
        domain = read_setting(lines, "domain_name")
        root_path = Path(read_setting(lines, "root_path")).expanduser()
        precip = read_setting(lines, "forcing_emearth_precip")
        if not domain or domain in seen_domains:
            raise ValueError(f"Missing or duplicate domain_name: '{domain}'")
        seen_domains.add(domain)
        if precip not in VALID_EMEARTH_PRECIP:
            raise ValueError(f"Invalid forcing_emearth_precip '{precip}' in {source_control}")
        if not root_path.is_absolute():
            raise ValueError(f"root_path must be absolute for {domain}: {root_path}")

        source_catchment = (Path(read_setting(lines, "catchment_shp_path"))
                            / read_setting(lines, "catchment_shp_name"))
        if not source_catchment.is_file():
            raise FileNotFoundError(f"Source catchment for {domain} not found: {source_catchment}")

        domain_root = root_path / f"domain_{domain}"
        output_control = CONTROL_DIR / f"control_{domain}_lumped.txt"
        updated = list(lines)
        for setting, suffix in LUMPED_PATH_SETTINGS.items():
            if read_setting(updated, setting) == "default":
                updated = replace_setting(updated, setting, str(domain_root / suffix))

        if read_setting(updated, "forcing_emearth_precip") != precip:
            raise RuntimeError(f"Precipitation setting changed unexpectedly for {domain}")
        if read_setting(updated, "domain_name") != domain:
            raise RuntimeError(f"Domain name changed unexpectedly for {domain}")
        planned.append((domain, output_control, "".join(updated), precip))
        print(f"{domain:<15} {precip:<15} -> {output_control.name}")

    created = existing = 0
    if args.dry_run:
        print("\nDRY RUN: no controls or task file written.")
    else:
        CONTROL_DIR.mkdir(parents=True, exist_ok=True)
        for domain, control, content, _ in planned:
            if control.exists() and not args.overwrite:
                existing += 1
                continue
            control.write_text(content)
            if not control.is_file() or not control.stat().st_size:
                raise RuntimeError(f"Could not write lumped control for {domain}: {control}")
            created += 1
        output_task.parent.mkdir(parents=True, exist_ok=True)
        output_task.write_text("".join(f"{control.resolve()}\n" for _, control, _, _ in planned))
        if len(output_task.read_text().splitlines()) != len(planned):
            raise RuntimeError(f"Incorrect lumped task count in {output_task}")

    print("\n" + "=" * 78)
    print(f"Lumped domains  : {len(planned)}")
    print(f"Controls created: {created}")
    print(f"Controls retained: {existing}")
    print(f"Lumped task file: {output_task}")
    print("Distributed controls were not modified.")
    print("=" * 78)


if __name__ == "__main__":
    main()
