#!/usr/bin/env python3
# coding: utf-8

"""
Generate monthly task files for the LUMPED CWARHM workflow.

Input
-----
lumped_multibasin_preprocessing_<BATCH>.txt

Every input row must point to:

    control_<DOMAIN>_lumped.txt

Output
------
lumped_month_tasks_<BATCH>.txt

Each output row contains:

    control_file<TAB>year<TAB>month
"""

import argparse
from pathlib import Path


# ============================================================
# CONTROL READER
# ============================================================

def read_from_control(
    file,
    setting,
):

    with file.open() as contents:

        for line in contents:

            stripped = line.strip()

            if (
                not stripped
                or stripped.startswith("#")
                or "|" not in stripped
            ):
                continue

            left, right = stripped.split(
                "|",
                1,
            )

            if left.strip() != setting:
                continue

            value = (
                right
                .split(
                    "#",
                    1,
                )[0]
                .strip()
            )

            if not value:

                raise RuntimeError(
                    f"Empty '{setting}' in:\n"
                    f"{file}"
                )

            return value

    raise RuntimeError(
        f"Setting '{setting}' not found in:\n"
        f"{file}"
    )


# ============================================================
# TASK READER
# ============================================================

def read_lumped_controls(
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
                Path(
                    value
                )
                .expanduser()
                .resolve()
            )

            if not control.exists():

                raise FileNotFoundError(
                    "Lumped control on task "
                    f"line {line_number} does "
                    "not exist:\n"
                    f"{control}"
                )

            if not control.is_file():

                raise RuntimeError(
                    "Lumped control path is "
                    "not a file:\n"
                    f"{control}"
                )

            # ------------------------------------------------
            # Strict separation from distributed workflow.
            # ------------------------------------------------

            if not control.stem.endswith(
                "_lumped"
            ):

                raise RuntimeError(
                    "Non-lumped control found in "
                    "lumped basin task file.\n"
                    f"Line    : {line_number}\n"
                    f"Control : {control}"
                )

            controls.append(
                control
            )

    if not controls:

        raise RuntimeError(
            "Lumped basin task file contains "
            "no controls."
        )

    if (
        len(controls)
        != len(
            set(
                controls
            )
        )
    ):

        raise RuntimeError(
            "Lumped basin task file contains "
            "duplicate control files."
        )

    return controls


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Generate monthly forcing tasks "
            "for lumped CWARHM controls."
        )
    )

    parser.add_argument(
        "--task-file",
        type=Path,
        required=True,
        help="Lumped basin task file.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Optional output monthly task file."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate and report without writing."
        ),
    )

    args = parser.parse_args()

    task_file = (
        args.task_file
        .expanduser()
        .resolve()
    )

    if not task_file.exists():

        raise FileNotFoundError(
            f"Lumped basin task file not found:\n"
            f"{task_file}"
        )

    controls = read_lumped_controls(
        task_file
    )

    # ========================================================
    # OUTPUT NAME
    # ========================================================

    if args.output is None:

        name = task_file.name

        prefix = (
            "lumped_multibasin_preprocessing_"
        )

        if name.startswith(
            prefix
        ):

            batch = (
                name[
                    len(
                        prefix
                    ):
                ]
                .removesuffix(
                    ".txt"
                )
            )

        else:

            batch = (
                task_file.stem
            )

        output_file = (
            task_file.parent
            / (
                "lumped_month_tasks_"
                f"{batch}.txt"
            )
        )

    else:

        output_file = (
            args.output
            .expanduser()
            .resolve()
        )

    # ========================================================
    # BUILD MONTH TASKS
    # ========================================================

    month_tasks = []
    summaries = []

    seen_domains = set()

    for control in controls:

        domain = read_from_control(
            control,
            "domain_name",
        )

        if domain in seen_domains:

            raise RuntimeError(
                "Duplicate lumped domain detected:\n"
                f"{domain}"
            )

        seen_domains.add(
            domain
        )

        forcing_raw_time = (
            read_from_control(
                control,
                "forcing_raw_time",
            )
        )

        try:

            parts = [
                value.strip()
                for value
                in forcing_raw_time.split(",")
            ]

            if len(parts) != 2:
                raise ValueError

            start_year = int(
                parts[0]
            )

            end_year = int(
                parts[1]
            )

        except Exception as exc:

            raise RuntimeError(
                "forcing_raw_time must have "
                "'START_YEAR,END_YEAR' format:\n"
                f"{control}"
            ) from exc

        if start_year > end_year:

            raise RuntimeError(
                "Invalid forcing period in:\n"
                f"{control}"
            )

        count = 0

        for year in range(
            start_year,
            end_year + 1,
        ):

            for month in range(
                1,
                13,
            ):

                month_tasks.append(
                    (
                        str(
                            control
                        ),
                        year,
                        month,
                    )
                )

                count += 1

        summaries.append(
            (
                domain,
                start_year,
                end_year,
                count,
            )
        )

    # ========================================================
    # REPORT
    # ========================================================

    print()
    print("=" * 78)
    print(
        "GENERATE LUMPED MONTHLY TASKS"
    )
    print("=" * 78)

    print(
        f"Basin task file : {task_file}"
    )

    print(
        f"Basins          : {len(controls)}"
    )

    print(
        f"Output          : {output_file}"
    )

    print(
        f"Dry run         : {args.dry_run}"
    )

    print()

    for (
        domain,
        start_year,
        end_year,
        count,
    ) in summaries:

        print(
            f"{domain:<15} "
            f"{start_year}-{end_year} "
            f"{count} months"
        )

    print()
    print(
        f"Total monthly tasks: "
        f"{len(month_tasks)}"
    )

    # ========================================================
    # DRY RUN
    # ========================================================

    if args.dry_run:

        print()
        print(
            "DRY RUN - file was not written."
        )

        return

    # ========================================================
    # WRITE
    # ========================================================

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "w"
    ) as file:

        for (
            control,
            year,
            month,
        ) in month_tasks:

            file.write(
                f"{control}\t"
                f"{year}\t"
                f"{month}\n"
            )

    # ========================================================
    # VERIFY
    # ========================================================

    written = 0

    with output_file.open() as file:

        for line in file:

            if not line.strip():
                continue

            written += 1

            control = Path(
                line.split(
                    "\t",
                    1,
                )[0]
            )

            if not control.stem.endswith(
                "_lumped"
            ):

                raise RuntimeError(
                    "Distributed control detected "
                    "in generated lumped month "
                    "task file:\n"
                    f"{control}"
                )

    if (
        written
        != len(
            month_tasks
        )
    ):

        raise RuntimeError(
            "Monthly task count verification "
            "failed.\n"
            f"Expected: {len(month_tasks)}\n"
            f"Written : {written}"
        )

    # ========================================================
    # FINISH
    # ========================================================

    print()
    print("=" * 78)
    print(
        "LUMPED MONTH TASK FILE CREATED"
    )
    print("=" * 78)

    print(
        f"Basins        : {len(controls)}"
    )

    print(
        f"Monthly tasks : {written}"
    )

    print(
        f"Output        : {output_file}"
    )

    print()
    print(
        "All task rows use _lumped controls."
    )


if __name__ == "__main__":
    main()