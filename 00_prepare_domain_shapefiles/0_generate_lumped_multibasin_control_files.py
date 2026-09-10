#!/usr/bin/env python3
# coding: utf-8

"""
Generate lumped CWARHM control files from an existing multibasin task file.

Input task-file format
----------------------
One existing distributed control file per line:

    /path/to/control_CAN_01AD003.txt
    /path/to/control_CAN_01AM001.txt
    ...

Output
------
For every distributed control:

    control_CAN_01AD003.txt

create:

    control_CAN_01AD003_lumped.txt

IMPORTANT
---------
The physical CWARHM domain remains:

    domain_CAN_01AD003/

Lumped products are stored under:

    domain_CAN_01AD003/lumped/

Therefore domain_name is NOT changed.

The lumped control changes only geometry-dependent/default output paths
so distributed products are never overwritten.

The original distributed controls are READ-ONLY.

EM-Earth precipitation
----------------------
The EM-Earth precipitation selection is inherited directly from the
distributed control:

    forcing_emearth_precip | prcp

or:

    forcing_emearth_precip | prcp_corrected

The lumped workflow does NOT change this selection.

Therefore distributed and lumped forcing generated from the same control
set use the same EM-Earth precipitation source.

The downstream SUMMA forcing variable remains:

    pptrate
"""

import argparse
from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM_ROOT = SCRIPT_DIR.parent
CONTROL_DIR = CWARHM_ROOT / "0_control_files"


# ============================================================
# EM-EARTH PRECIPITATION SETTINGS
# ============================================================

VALID_EMEARTH_PRECIP = {
    "prcp",
    "prcp_corrected",
}


# ============================================================
# LUMPED PATH SETTINGS
# ============================================================

# Settings whose "default" paths need to be redirected into
# domain_<domain>/lumped/.
#
# These values are written as explicit paths in the lumped control.

LUMPED_PATH_SETTINGS = {

    # Forcing
    "forcing_shape_path":
        "lumped/shapefiles/forcing",

    "forcing_geo_path":
        "lumped/forcing/0_geopotential",

    "forcing_raw_path":
        "lumped/forcing/1_raw_data",

    "forcing_merged_path":
        "lumped/forcing/2_merged_data",

    "forcing_easymore_path":
        "lumped/forcing/3_temp_easymore",

    "forcing_basin_avg_path":
        "lumped/forcing/3_basin_averaged_data",

    "forcing_summa_path":
        "lumped/forcing/4_SUMMA_input",


    # DEM
    "parameter_dem_vrt2_path":
        "lumped/parameters/dem/4_domain_vrt",

    "parameter_dem_tif_path":
        "lumped/parameters/dem/5_elevation",


    # Soil
    "parameter_soil_domain_path":
        "lumped/parameters/soilclass/2_soil_classes_domain",


    # Land cover
    "parameter_land_vrt3_path":
        "lumped/parameters/landclass/4_domain_vrt_epsg_4326",

    "parameter_land_vrt4_path":
        "lumped/parameters/landclass/5_multiband_domain_vrt_epsg_4326",

    "parameter_land_tif_path":
        "lumped/parameters/landclass/6_tif_multiband",

    "parameter_land_mode_path":
        "lumped/parameters/landclass/7_mode_land_class",


    # Catchment intersections
    "intersect_dem_path":
        "lumped/shapefiles/catchment_intersection/with_dem",

    "intersect_soil_path":
        "lumped/shapefiles/catchment_intersection/with_soilgrids",

    "intersect_land_path":
        "lumped/shapefiles/catchment_intersection/with_modis",

    "intersect_forcing_path":
        "lumped/shapefiles/catchment_intersection/with_forcing",


    # SUMMA
    "settings_summa_path":
        "lumped/settings/SUMMA",

    "experiment_output_summa":
        "lumped/simulations/run1/SUMMA",

    "experiment_log_summa":
        "lumped/simulations/run1/SUMMA",
}


# ============================================================
# ARGUMENTS
# ============================================================

def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Generate lumped CWARHM controls from an existing "
            "multibasin preprocessing task file."
        )
    )


    parser.add_argument(
        "--task-file",
        type=Path,
        required=True,
        help=(
            "Existing distributed multibasin task file "
            "containing one absolute control-file path "
            "per line."
        ),
    )


    parser.add_argument(
        "--output-task-file",
        type=Path,
        default=None,
        help=(
            "Output lumped task file. Default: "
            "0_control_files/lumped_<input-task-name>"
        ),
    )


    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Overwrite existing lumped controls/task file."
        ),
    )


    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate and preview without writing files."
        ),
    )


    return parser.parse_args()


# ============================================================
# CONTROL FILE FUNCTIONS
# ============================================================

def read_setting(
    lines,
    setting,
):

    matches = []


    for line in lines:

        stripped = line.strip()


        if (
            not stripped
            or stripped.startswith("#")
            or "|" not in line
        ):

            continue


        left, right = line.split(
            "|",
            1
        )


        if left.strip() == setting:

            value = (
                right
                .split("#", 1)[0]
                .strip()
            )

            matches.append(
                value
            )


    if len(matches) == 0:

        raise RuntimeError(
            f"Setting '{setting}' was not found."
        )


    if len(matches) > 1:

        raise RuntimeError(
            f"Setting '{setting}' occurs more than once."
        )


    return matches[0]


def replace_setting(
    lines,
    setting,
    value,
):

    output = []
    matched = False


    for line in lines:

        stripped = line.strip()


        if (
            stripped
            and not stripped.startswith("#")
            and "|" in line
        ):

            left, right = line.split(
                "|",
                1
            )


            if left.strip() == setting:


                if matched:

                    raise RuntimeError(
                        f"Setting '{setting}' occurs "
                        "more than once."
                    )


                comment = ""


                if "#" in right:

                    comment_text = (
                        right
                        .split("#", 1)[1]
                        .strip()
                    )


                    if comment_text:

                        comment = (
                            f" # {comment_text}"
                        )


                output.append(
                    f"{setting:<35} | "
                    f"{value}{comment}\n"
                )


                matched = True

                continue


        output.append(
            line
        )


    if not matched:

        raise RuntimeError(
            f"Setting '{setting}' was not found."
        )


    return output


# ============================================================
# TASK FILE
# ============================================================

def read_task_file(
    task_file,
):

    controls = []


    with task_file.open() as contents:

        for (
            line_number,
            line,
        ) in enumerate(
            contents,
            start=1,
        ):

            value = line.strip()


            if (
                not value
                or value.startswith("#")
            ):

                continue


            control = (
                Path(value)
                .expanduser()
                .resolve()
            )


            if not control.exists():

                raise FileNotFoundError(
                    "Control file on task line "
                    f"{line_number} does not exist:\n"
                    f"{control}"
                )


            controls.append(
                control
            )


    if not controls:

        raise RuntimeError(
            "No control files found in:\n"
            f"{task_file}"
        )


    if (
        len(controls)
        != len(set(controls))
    ):

        raise RuntimeError(
            "Task file contains duplicate "
            "control files."
        )


    return controls


# ============================================================
# MAIN
# ============================================================

def main():

    args = parse_args()


    task_file = (
        args.task_file
        .expanduser()
        .resolve()
    )


    if not task_file.exists():

        raise FileNotFoundError(
            f"Task file not found:\n{task_file}"
        )


    source_controls = read_task_file(
        task_file
    )


    # --------------------------------------------------------
    # OUTPUT TASK FILE
    # --------------------------------------------------------

    if args.output_task_file is None:

        output_task_file = (
            CONTROL_DIR
            / f"lumped_{task_file.name}"
        )

    else:

        output_task_file = (
            args.output_task_file
            .expanduser()
            .resolve()
        )


    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    print()

    print("=" * 78)
    print(
        "GENERATE LUMPED MULTIBASIN CONTROLS"
    )
    print("=" * 78)

    print(
        f"Input task file  : "
        f"{task_file}"
    )

    print(
        f"Domains          : "
        f"{len(source_controls)}"
    )

    print(
        f"Output task file : "
        f"{output_task_file}"
    )

    print(
        f"Dry run          : "
        f"{args.dry_run}"
    )

    print(
        f"Overwrite        : "
        f"{args.overwrite}"
    )


    lumped_controls = []

    created = 0
    existing = 0


    # ========================================================
    # PROCESS DISTRIBUTED CONTROLS
    # ========================================================

    for source_control in source_controls:


        source_lines = (
            source_control
            .read_text()
            .splitlines(
                keepends=True
            )
        )


        # ----------------------------------------------------
        # BASIC SETTINGS
        # ----------------------------------------------------

        domain = read_setting(
            source_lines,
            "domain_name"
        )


        root_path = Path(
            read_setting(
                source_lines,
                "root_path"
            )
        )


        # ----------------------------------------------------
        # EM-EARTH PRECIPITATION
        # ----------------------------------------------------
        #
        # This must already have been written into the
        # distributed control by:
        #
        # 0_generate_multibasin_control_files.py
        #
        # We deliberately do NOT modify the selection here.
        # The lumped control inherits exactly the same value.

        emearth_precip = read_setting(
            source_lines,
            "forcing_emearth_precip"
        )


        if (
            emearth_precip
            not in VALID_EMEARTH_PRECIP
        ):

            raise RuntimeError(
                "Invalid forcing_emearth_precip "
                "in distributed control.\n"
                f"Control: {source_control}\n"
                f"Value  : {emearth_precip}\n\n"
                "Allowed values are:\n"
                "  prcp\n"
                "  prcp_corrected"
            )


        # ----------------------------------------------------
        # SOURCE CATCHMENT
        # ----------------------------------------------------

        source_catchment_path = Path(
            read_setting(
                source_lines,
                "catchment_shp_path"
            )
        )


        source_catchment_name = read_setting(
            source_lines,
            "catchment_shp_name"
        )


        source_catchment = (
            source_catchment_path
            / source_catchment_name
        )


        if not source_catchment.exists():

            raise FileNotFoundError(
                f"Source catchment not found "
                f"for {domain}:\n"
                f"{source_catchment}"
            )


        # ----------------------------------------------------
        # LUMPED DOMAIN PATHS
        # ----------------------------------------------------

        domain_root = (
            root_path
            / f"domain_{domain}"
        )


        lumped_root = (
            domain_root
            / "lumped"
        )


        lumped_catchment_dir = (
            lumped_root
            / "shapefiles"
            / "catchment"
        )


        lumped_catchment_name = (
            f"{domain}_lumped_basin.shp"
        )


        output_control = (
            CONTROL_DIR
            / f"control_{domain}_lumped.txt"
        )


        # Start with a complete copy of the distributed
        # control.
        #
        # This automatically preserves:
        #
        #   forcing_emearth_precip
        #
        # together with all other shared model settings.

        output_lines = list(
            source_lines
        )


        # ----------------------------------------------------
        # REDIRECT DEFAULT PATHS TO LUMPED TREE
        # ----------------------------------------------------
        #
        # Keep domain_name unchanged.
        #
        # catchment_shp_path remains the READ-ONLY distributed
        # source path for the lumped-catchment preparation
        # script.
        #
        # catchment_shp_name also remains the distributed
        # source name at this stage.
        #
        # All geometry-dependent default outputs are redirected
        # beneath:
        #
        # domain_<domain>/lumped/

        for (
            setting,
            relative_path,
        ) in LUMPED_PATH_SETTINGS.items():


            current_value = read_setting(
                output_lines,
                setting
            )


            # Only redirect settings currently using default.
            #
            # Explicit shared paths are intentionally retained.

            if current_value == "default":

                explicit_path = (
                    domain_root
                    / relative_path
                )


                output_lines = replace_setting(
                    output_lines,
                    setting,
                    str(
                        explicit_path
                    ),
                )


        # ----------------------------------------------------
        # VERIFY PRECIPITATION SETTING WAS PRESERVED
        # ----------------------------------------------------

        lumped_emearth_precip = read_setting(
            output_lines,
            "forcing_emearth_precip"
        )


        if (
            lumped_emearth_precip
            != emearth_precip
        ):

            raise RuntimeError(
                "EM-Earth precipitation setting changed "
                "while generating lumped control.\n"
                f"Domain      : {domain}\n"
                f"Distributed : {emearth_precip}\n"
                f"Lumped      : {lumped_emearth_precip}"
            )


        # ----------------------------------------------------
        # REPORT DOMAIN
        # ----------------------------------------------------

        print()

        print("-" * 78)

        print(
            f"Domain            : "
            f"{domain}"
        )

        print(
            f"Source control    : "
            f"{source_control}"
        )

        print(
            f"EM-Earth precip   : "
            f"{emearth_precip}"
        )

        print(
            f"Source catchment  : "
            f"{source_catchment}"
        )

        print(
            f"Lumped root       : "
            f"{lumped_root}"
        )

        print(
            f"Lumped catchment  : "
            f"{lumped_catchment_dir / lumped_catchment_name}"
        )

        print(
            f"Lumped control    : "
            f"{output_control}"
        )


        # ----------------------------------------------------
        # WRITE CONTROL
        # ----------------------------------------------------

        if (
            output_control.exists()
            and not args.overwrite
        ):

            print(
                "Control status    : "
                "EXISTS - retained"
            )

            existing += 1


        elif args.dry_run:

            print(
                "Control status    : "
                "DRY RUN"
            )


        else:

            output_control.write_text(
                "".join(
                    output_lines
                )
            )


            if (
                not output_control.exists()
                or
                output_control.stat().st_size == 0
            ):

                raise RuntimeError(
                    f"Failed to create:\n"
                    f"{output_control}"
                )


            # ------------------------------------------------
            # VERIFY WRITTEN PRECIPITATION SETTING
            # ------------------------------------------------

            written_lines = (
                output_control
                .read_text()
                .splitlines(
                    keepends=True
                )
            )


            written_emearth_precip = read_setting(
                written_lines,
                "forcing_emearth_precip"
            )


            if (
                written_emearth_precip
                != emearth_precip
            ):

                raise RuntimeError(
                    "Written lumped control has the wrong "
                    "EM-Earth precipitation source.\n"
                    f"Control : {output_control}\n"
                    f"Expected: {emearth_precip}\n"
                    f"Found   : {written_emearth_precip}"
                )


            print(
                "Control status    : CREATED"
            )

            created += 1


        lumped_controls.append(
            output_control.resolve()
        )


    # ========================================================
    # WRITE LUMPED BASIN TASK FILE
    # ========================================================

    print()

    print("-" * 78)


    if args.dry_run:

        print(
            "Task status       : "
            "DRY RUN - not written"
        )


    else:

        if (
            output_task_file.exists()
            and not args.overwrite
        ):

            raise FileExistsError(
                "Lumped task file already exists. "
                "Use --overwrite if intentional:\n"
                f"{output_task_file}"
            )


        output_task_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )


        with output_task_file.open(
            "w"
        ) as contents:

            for control in lumped_controls:

                contents.write(
                    f"{control}\n"
                )


        written = [
            line.strip()
            for line
            in output_task_file
            .read_text()
            .splitlines()
            if line.strip()
        ]


        if (
            len(written)
            != len(lumped_controls)
        ):

            raise RuntimeError(
                "Lumped task-file row-count "
                "verification failed."
            )


        print(
            "Task status       : CREATED"
        )


    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print()

    print("=" * 78)
    print(
        "LUMPED CONTROL GENERATION COMPLETE"
    )
    print("=" * 78)

    print(
        f"Domains           : "
        f"{len(source_controls)}"
    )

    print(
        f"Controls created  : "
        f"{created}"
    )

    print(
        f"Controls existing : "
        f"{existing}"
    )

    print(
        f"Lumped task file  : "
        f"{output_task_file}"
    )

    print()

    print(
        "EM-Earth precipitation selection was "
        "inherited from each distributed control."
    )

    print(
        "No EM-Earth source-variable selection "
        "was changed."
    )

    print(
        "Downstream SUMMA precipitation variable "
        "remains pptrate."
    )

    print()

    print(
        "Distributed controls were not modified."
    )

    print(
        "Distributed domain products were not modified."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()