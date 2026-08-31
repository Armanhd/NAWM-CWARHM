#!/usr/bin/env python3
# coding: utf-8

"""
Generate domain-specific CWARHM multibasin control files.

The script reads a domain inventory CSV and uses a validated CWARHM
control file as a template.

Default inventory:
    0_control_files/MERIT_Pfaf3_control_file_inputs.csv

Default template:
    0_control_files/control_MERIT_717.txt

Generated controls:
    control_<domain_name>.txt

Required inventory columns:
    domain_name
    source_directory
    catchment_shp_file
    river_network_shp_file
    river_basin_shp_file

The shapefile columns may contain either:

    file.shp

or relative paths such as:

    catchment/file.shp
    river_network/file.shp
    river_basins/file.shp

These are automatically separated into the corresponding CWARHM
*_shp_path and *_shp_name settings.

Optional dataset-specific control settings can also be included as
columns in the inventory CSV. If present and non-empty, they override
the corresponding value inherited from the template.

Examples
--------
MERIT_725 through MERIT_729:

    python 0_generate_multibasin_control_files.py \
        --prefix MERIT_72 \
        --start-domain MERIT_725 \
        --limit 5 \
        --dry-run

CENTURY domains:

    python 0_generate_multibasin_control_files.py \
        --csv ../0_control_files/CENTURY_control_file_inputs.csv \
        --prefix CAN_ \
        --limit 5 \
        --dry-run
"""

import argparse
import csv
import math
from pathlib import Path

import geopandas as gpd


# ============================================================
# PROJECT PATHS
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM_ROOT = SCRIPT_DIR.parent
CONTROL_DIR = CWARHM_ROOT / "0_control_files"

CSV_FILE = CONTROL_DIR / "MERIT_Pfaf3_control_file_inputs.csv"
DEFAULT_TEMPLATE = CONTROL_DIR / "control_MERIT_717.txt"

SHARED_SOIL_CLASS_DIR = Path(
    "/work/comphyd_lab/data/geospatial-data/soil_classes"
)

DEFAULT_BBOX_BUFFER = 0.25


# ============================================================
# INVENTORY COLUMNS
# ============================================================

REQUIRED_CSV_COLUMNS = [
    "domain_name",
    "source_directory",
    "catchment_shp_file",
    "river_network_shp_file",
    "river_basin_shp_file",
]


# Optional dataset-specific settings.
#
# These do not need to exist in every inventory CSV.
# If a column exists and contains a value, that value overrides
# the corresponding setting inherited from the template.

OPTIONAL_CONTROL_COLUMNS = [
    "catchment_shp_gruid",
    "catchment_shp_hruid",
    "catchment_shp_area",
    "catchment_shp_lat",
    "catchment_shp_lon",

    "river_network_shp_segid",
    "river_network_shp_downsegid",
    "river_network_shp_slope",
    "river_network_shp_length_source",
    "river_network_shp_length",

    "river_basin_shp_rm_hruid",
    "river_basin_shp_area",
    "river_basin_shp_hru_to_seg",

    "river_basin_needs_remap",
]


# ============================================================
# ARGUMENTS
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate CWARHM multibasin control files from a domain inventory."
    )

    parser.add_argument(
        "--csv",
        type=Path,
        default=CSV_FILE,
        help="Input domain inventory CSV."
    )

    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Validated CWARHM control file used as template."
    )

    parser.add_argument(
        "--prefix",
        default=None,
        help="Only include domains beginning with this prefix, e.g. MERIT_72 or CAN_."
    )

    parser.add_argument(
        "--start-domain",
        default=None,
        help="Start selection at this domain after sorting, e.g. MERIT_725."
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of selected domains."
    )

    parser.add_argument(
        "--bbox-buffer",
        type=float,
        default=DEFAULT_BBOX_BUFFER,
        help="Geographic buffer in degrees around catchment extent."
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing generated control files."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview without writing files."
    )

    return parser.parse_args()


# ============================================================
# CONTROL FILE FUNCTIONS
# ============================================================

def read_control_lines(file):
    return file.read_text().splitlines(keepends=True)


def replace_control_setting(lines, setting, value):
    found = False
    output = []

    for line in lines:
        stripped = line.strip()

        if stripped and not stripped.startswith("#") and "|" in stripped:
            left, right = line.split("|", 1)

            if left.strip() == setting:
                comment = ""

                if "#" in right:
                    _, comment_text = right.split("#", 1)
                    comment_text = comment_text.strip()

                    if comment_text:
                        comment = f" # {comment_text}"

                output.append(f"{setting:<35} | {value}{comment}\n")
                found = True
                continue

        output.append(line)

    if not found:
        raise RuntimeError(
            f"Setting '{setting}' was not found in the template control file."
        )

    return output


# ============================================================
# SOURCE SHAPEFILE PATH HANDLING
# ============================================================

def resolve_source_file(source_directory, inventory_value):
    """
    Resolve a source shapefile listed in the inventory.

    inventory_value may be either:

        file.shp

    or:

        subdirectory/file.shp

    Returns:
        full_file
        parent_directory
        filename
    """

    relative_file = Path(inventory_value)

    if relative_file.is_absolute():
        full_file = relative_file
    else:
        full_file = source_directory / relative_file

    full_file = full_file.resolve()

    return {
        "file": full_file,
        "path": full_file.parent,
        "name": full_file.name,
    }


# ============================================================
# FORCING BOUNDING BOX
# ============================================================

def calculate_forcing_bbox(catchment_file, buffer_degrees):
    gdf = gpd.read_file(catchment_file)

    if len(gdf) == 0:
        raise RuntimeError(
            f"Catchment shapefile contains no features:\n{catchment_file}"
        )

    raw_west, raw_south, raw_east, raw_north = gdf.total_bounds

    if not all(
        math.isfinite(value)
        for value in [raw_west, raw_south, raw_east, raw_north]
    ):
        raise RuntimeError(
            f"Non-finite catchment coordinates found:\n{catchment_file}"
        )

    crs_was_assumed = False

    if gdf.crs is None:
        geographic_range_ok = (
            -180.0 <= raw_west <= 180.0
            and -180.0 <= raw_east <= 180.0
            and -90.0 <= raw_south <= 90.0
            and -90.0 <= raw_north <= 90.0
            and raw_west <= raw_east
            and raw_south <= raw_north
        )

        if not geographic_range_ok:
            raise RuntimeError(
                "Catchment has no CRS and coordinates are not consistent "
                "with longitude/latitude.\n\n"
                f"File: {catchment_file}\n"
                f"W={raw_west}, S={raw_south}, E={raw_east}, N={raw_north}"
            )

        print()
        print("WARNING: Source catchment has no CRS metadata.")
        print("Coordinates are consistent with longitude/latitude.")
        print("Assuming EPSG:4326 for bounding-box calculation only.")
        print(f"Source: {catchment_file}")

        gdf = gdf.set_crs("EPSG:4326", allow_override=True)
        crs_was_assumed = True

    try:
        gdf = gdf.to_crs("EPSG:4326")
    except Exception as exc:
        raise RuntimeError(
            f"Could not convert catchment to EPSG:4326:\n"
            f"{catchment_file}\nSource CRS: {gdf.crs}"
        ) from exc

    west, south, east, north = gdf.total_bounds

    if not all(
        math.isfinite(value)
        for value in [west, south, east, north]
    ):
        raise RuntimeError(
            f"Non-finite bounding-box coordinates found:\n{catchment_file}"
        )

    if west < -180 or east > 180 or south < -90 or north > 90:
        raise RuntimeError(
            f"Invalid geographic bounds after CRS conversion:\n"
            f"{catchment_file}\nW={west}, S={south}, E={east}, N={north}"
        )

    west = max(west - buffer_degrees, -180.0)
    east = min(east + buffer_degrees, 180.0)
    south = max(south - buffer_degrees, -90.0)
    north = min(north + buffer_degrees, 90.0)

    if west >= east:
        raise RuntimeError(
            f"Invalid forcing bounding box: west >= east ({west}, {east})"
        )

    if south >= north:
        raise RuntimeError(
            f"Invalid forcing bounding box: south >= north ({south}, {north})"
        )

    forcing_raw_space = f"{north:.6f}/{west:.6f}/{south:.6f}/{east:.6f}"

    return {
        "west": west,
        "south": south,
        "east": east,
        "north": north,
        "forcing_raw_space": forcing_raw_space,
        "crs_assumed": crs_was_assumed,
        "source_crs": (
            "EPSG:4326 assumed from coordinate range"
            if crs_was_assumed
            else str(gdf.crs)
        ),
    }


# ============================================================
# DOMAIN INVENTORY
# ============================================================

def read_domain_table(csv_file):
    if not csv_file.exists():
        raise FileNotFoundError(
            f"Domain inventory CSV not found:\n{csv_file}"
        )

    with csv_file.open(newline="") as contents:
        reader = csv.DictReader(contents)

        if reader.fieldnames is None:
            raise RuntimeError("CSV file has no header.")

        fieldnames = [name.strip() for name in reader.fieldnames]

        missing_columns = [
            column
            for column in REQUIRED_CSV_COLUMNS
            if column not in fieldnames
        ]

        if missing_columns:
            raise RuntimeError(
                "Required CSV column(s) missing:\n"
                + "\n".join(f"  {column}" for column in missing_columns)
            )

        rows = []

        for raw_row in reader:
            row = {
                key.strip(): value.strip() if value else ""
                for key, value in raw_row.items()
                if key is not None
            }

            if any(row.values()):
                rows.append(row)

    return rows


# ============================================================
# VALIDATION
# ============================================================

def validate_domain_row(row):
    domain = row.get("domain_name", "")

    for column in REQUIRED_CSV_COLUMNS:
        if not row.get(column, ""):
            raise RuntimeError(
                f"Empty '{column}' value for domain '{domain}'."
            )

    source_directory = Path(row["source_directory"]).expanduser().resolve()

    if not source_directory.exists():
        raise FileNotFoundError(
            f"Source directory not found for {domain}:\n{source_directory}"
        )

    if not source_directory.is_dir():
        raise NotADirectoryError(
            f"Source path is not a directory for {domain}:\n{source_directory}"
        )

    catchment = resolve_source_file(
        source_directory,
        row["catchment_shp_file"]
    )

    river = resolve_source_file(
        source_directory,
        row["river_network_shp_file"]
    )

    basin = resolve_source_file(
        source_directory,
        row["river_basin_shp_file"]
    )

    source_files = {
        "Catchment": catchment["file"],
        "River network": river["file"],
        "Routing basin": basin["file"],
    }

    missing_files = [
        (label, file)
        for label, file in source_files.items()
        if not file.exists()
    ]

    if missing_files:
        message = "\n".join(
            f"  {label}: {file}"
            for label, file in missing_files
        )

        raise FileNotFoundError(
            f"Missing source shapefile(s) for {domain}:\n{message}"
        )

    return {
        "source_directory": source_directory,
        "catchment": catchment,
        "river": river,
        "basin": basin,
    }


def validate_shared_data():
    if not SHARED_SOIL_CLASS_DIR.is_dir():
        raise FileNotFoundError(
            f"Shared soil-class directory not found:\n"
            f"{SHARED_SOIL_CLASS_DIR}"
        )

    soil_class_file = SHARED_SOIL_CLASS_DIR / "soil_classes.tif"

    if not soil_class_file.exists():
        raise FileNotFoundError(
            f"Shared soil-class raster not found:\n"
            f"{soil_class_file}"
        )


# ============================================================
# BUILD CONTROL
# ============================================================

def build_control(template_lines, row, bbox_buffer):
    validated = validate_domain_row(row)

    bbox = calculate_forcing_bbox(
        validated["catchment"]["file"],
        bbox_buffer
    )

    updates = {
        "domain_name": row["domain_name"],

        "catchment_shp_path": str(validated["catchment"]["path"]),
        "catchment_shp_name": validated["catchment"]["name"],

        "river_network_shp_path": str(validated["river"]["path"]),
        "river_network_shp_name": validated["river"]["name"],

        "river_basin_shp_path": str(validated["basin"]["path"]),
        "river_basin_shp_name": validated["basin"]["name"],

        "forcing_raw_space": bbox["forcing_raw_space"],

        "parameter_soil_raw_path": str(SHARED_SOIL_CLASS_DIR),
        "parameter_soil_domain_path": "default",
    }

    # Apply optional dataset-specific settings from the CSV.
    for setting in OPTIONAL_CONTROL_COLUMNS:
        value = row.get(setting, "").strip()

        if value:
            updates[setting] = value

    output_lines = list(template_lines)

    for setting, value in updates.items():
        output_lines = replace_control_setting(
            output_lines,
            setting,
            value
        )

    return output_lines, bbox, validated, updates


# ============================================================
# MAIN
# ============================================================

def main():
    args = parse_args()

    csv_file = args.csv.expanduser().resolve()
    template_file = args.template.expanduser().resolve()

    if not CONTROL_DIR.exists():
        raise FileNotFoundError(
            f"Control-file directory not found:\n{CONTROL_DIR}"
        )

    if not template_file.exists():
        raise FileNotFoundError(
            f"Template control file not found:\n{template_file}"
        )

    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be greater than zero.")

    if args.bbox_buffer < 0:
        raise ValueError("--bbox-buffer cannot be negative.")

    validate_shared_data()

    rows = read_domain_table(csv_file)

    if args.prefix is not None:
        rows = [
            row
            for row in rows
            if row["domain_name"].startswith(args.prefix)
        ]

    rows = sorted(
        rows,
        key=lambda row: row["domain_name"]
    )

    if args.start_domain is not None:
        domain_names = [
            row["domain_name"]
            for row in rows
        ]

        if args.start_domain not in domain_names:
            raise RuntimeError(
                f"Requested --start-domain was not found:\n"
                f"{args.start_domain}"
            )

        start_index = domain_names.index(
            args.start_domain
        )

        rows = rows[start_index:]

    if args.limit is not None:
        rows = rows[:args.limit]

    if not rows:
        raise RuntimeError(
            "No domains matched the requested selection."
        )

    template_lines = read_control_lines(
        template_file
    )

    print()
    print("=" * 78)
    print("GENERATE MULTIBASIN CWARHM CONTROL FILES")
    print("=" * 78)
    print(f"CWARHM root      : {CWARHM_ROOT}")
    print(f"Control directory: {CONTROL_DIR}")
    print(f"Input CSV        : {csv_file}")
    print(f"Template         : {template_file}")
    print(f"Domain prefix    : {args.prefix or 'ALL'}")
    print(f"Start domain     : {args.start_domain or 'FIRST MATCH'}")
    print(f"Selected domains : {len(rows)}")
    print(f"BBox buffer      : {args.bbox_buffer} degrees")
    print(f"Soil source      : {SHARED_SOIL_CLASS_DIR}")
    print("Soil output path : default")
    print(f"Dry run          : {args.dry_run}")
    print(f"Overwrite        : {args.overwrite}")

    created = []
    skipped = []
    dry_run_files = []

    for row in rows:
        domain = row["domain_name"]
        output_file = CONTROL_DIR / f"control_{domain}.txt"

        print()
        print("-" * 78)
        print(f"Domain            : {domain}")

        output_lines, bbox, validated, updates = build_control(
            template_lines,
            row,
            args.bbox_buffer
        )

        print(f"Source directory  : {validated['source_directory']}")
        print(f"Catchment path    : {validated['catchment']['path']}")
        print(f"Catchment name    : {validated['catchment']['name']}")
        print(f"River path        : {validated['river']['path']}")
        print(f"River name        : {validated['river']['name']}")
        print(f"Basin path        : {validated['basin']['path']}")
        print(f"Basin name        : {validated['basin']['name']}")
        print(f"Source CRS        : {bbox['source_crs']}")
        print(
            f"Bounding box      : N={bbox['north']:.6f}, "
            f"W={bbox['west']:.6f}, "
            f"S={bbox['south']:.6f}, "
            f"E={bbox['east']:.6f}"
        )
        print(f"forcing_raw_space : {bbox['forcing_raw_space']}")

        optional_updates = [
            setting
            for setting in OPTIONAL_CONTROL_COLUMNS
            if setting in updates
        ]

        if optional_updates:
            print("Dataset overrides :")
            for setting in optional_updates:
                print(f"  {setting} = {updates[setting]}")
        else:
            print("Dataset overrides : none")

        print(f"Control output    : {output_file}")

        if output_file.exists() and not args.overwrite:
            print("Status            : SKIPPED - already exists")
            skipped.append(output_file)
            continue

        if args.dry_run:
            print("Status            : DRY RUN - not written")
            dry_run_files.append(output_file)
            continue

        output_file.write_text(
            "".join(output_lines)
        )

        if not output_file.exists() or output_file.stat().st_size == 0:
            raise RuntimeError(
                f"Control file was not created correctly:\n"
                f"{output_file}"
            )

        created.append(output_file)
        print("Status            : CREATED")

    print()
    print("=" * 78)
    print("CONTROL FILE GENERATION COMPLETED")
    print("=" * 78)
    print(f"Selected : {len(rows)}")
    print(f"Created  : {len(created)}")
    print(f"Skipped  : {len(skipped)}")
    print(f"Dry run  : {len(dry_run_files)}")

    if created:
        print()
        print("Created control files:")

        for file in created:
            print(f"  {file.name}")

    if skipped:
        print()
        print("Skipped existing control files:")

        for file in skipped:
            print(f"  {file.name}")

    print()
    print("Shared soil-class source:")
    print(f"  {SHARED_SOIL_CLASS_DIR / 'soil_classes.tif'}")

    print()
    print("No control_active.txt was created or modified.")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()