#!/usr/bin/env python3
# coding: utf-8

"""
Generate multibasin preprocessing and monthly forcing task files.

Outputs
-------
1. Basin preprocessing task file:

    multibasin_preprocessing_<BATCH>.txt

Each row contains:

    control_file

2. Monthly forcing task file:

    month_tasks_<BATCH>.txt

Each row contains:

    control_file<TAB>year<TAB>month

The forcing period for each basin is read from forcing_raw_time
in its domain-specific control file.

Examples
--------
MERIT_721 through MERIT_724:

    python 0b_generate_multibasin_month_tasks.py \
        --prefix MERIT_72 \
        --start-domain MERIT_721 \
        --limit 4 \
        --batch-name MERIT_721_724

MERIT_725 through MERIT_729:

    python 0b_generate_multibasin_month_tasks.py \
        --prefix MERIT_72 \
        --start-domain MERIT_725 \
        --limit 5 \
        --batch-name MERIT_725_729

Dry run:

    python 0b_generate_multibasin_month_tasks.py \
        --prefix MERIT_72 \
        --start-domain MERIT_725 \
        --limit 5 \
        --batch-name MERIT_725_729 \
        --dry-run
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
# ARGUMENTS
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate basin and monthly task files for multibasin CWARHM Slurm arrays."
    )

    parser.add_argument(
        "--prefix",
        default=None,
        help="Only include domains beginning with this prefix, e.g. MERIT_72."
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
        help="Maximum number of selected control files."
    )

    parser.add_argument(
        "--batch-name",
        default=None,
        help="Name used for output task files, e.g. MERIT_725_729."
    )

    parser.add_argument(
        "--basin-output",
        type=Path,
        default=None,
        help="Optional explicit basin preprocessing task-file path."
    )

    parser.add_argument(
        "--month-output",
        type=Path,
        default=None,
        help="Optional explicit monthly forcing task-file path."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report tasks without writing files."
    )

    return parser.parse_args()


# ============================================================
# CONTROL READER
# ============================================================

def read_from_control(file, setting):
    with file.open() as contents:
        for line in contents:
            stripped = line.strip()

            if not stripped or stripped.startswith("#") or "|" not in stripped:
                continue

            left, right = stripped.split("|", 1)

            if left.strip() != setting:
                continue

            value = right.split("#", 1)[0].strip()

            if not value:
                raise ValueError(
                    f"Setting '{setting}' is empty in:\n{file}"
                )

            return value

    raise ValueError(
        f"Setting '{setting}' not found in:\n{file}"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    args = parse_args()

    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be greater than zero.")

    # --------------------------------------------------------
    # FIND DOMAIN CONTROL FILES
    # --------------------------------------------------------

    control_files = sorted(CONTROL_DIR.glob("control_*.txt"))

    selected = []

    for control_file in control_files:
        domain = read_from_control(control_file, "domain_name")

        if args.prefix is not None and not domain.startswith(args.prefix):
            continue

        selected.append((domain, control_file.resolve()))

    selected = sorted(selected, key=lambda item: item[0])

    # --------------------------------------------------------
    # START AT REQUESTED DOMAIN
    # --------------------------------------------------------

    if args.start_domain is not None:
        domain_names = [domain for domain, _ in selected]

        if args.start_domain not in domain_names:
            raise RuntimeError(
                f"Requested --start-domain was not found:\n{args.start_domain}"
            )

        start_index = domain_names.index(args.start_domain)
        selected = selected[start_index:]

    # --------------------------------------------------------
    # APPLY LIMIT
    # --------------------------------------------------------

    if args.limit is not None:
        selected = selected[:args.limit]

    if not selected:
        raise RuntimeError("No matching domain control files found.")

    # --------------------------------------------------------
    # DETERMINE OUTPUT NAME
    # --------------------------------------------------------

    if args.batch_name:
        batch_name = args.batch_name.replace("/", "_")

    elif args.prefix:
        batch_name = args.prefix.replace("/", "_")

    else:
        batch_name = "ALL"

    if args.basin_output is not None:
        basin_output = args.basin_output.expanduser().resolve()
    else:
        basin_output = CONTROL_DIR / f"multibasin_preprocessing_{batch_name}.txt"

    if args.month_output is not None:
        month_output = args.month_output.expanduser().resolve()
    else:
        month_output = CONTROL_DIR / f"month_tasks_{batch_name}.txt"

    # --------------------------------------------------------
    # BUILD BASIN TASKS
    # --------------------------------------------------------

    basin_tasks = [
        str(control_file)
        for domain, control_file in selected
    ]

    # --------------------------------------------------------
    # BUILD MONTH TASKS
    # --------------------------------------------------------

    month_tasks = []
    domain_summary = []

    for domain, control_file in selected:
        forcing_raw_time = read_from_control(control_file, "forcing_raw_time")

        try:
            parts = [value.strip() for value in forcing_raw_time.split(",")]

            if len(parts) != 2:
                raise ValueError

            start_year = int(parts[0])
            end_year = int(parts[1])

        except Exception as exc:
            raise ValueError(
                "forcing_raw_time must use 'START_YEAR,END_YEAR' format in:\n"
                f"{control_file}"
            ) from exc

        if start_year > end_year:
            raise ValueError(
                f"Invalid forcing_raw_time in {control_file}:\n"
                f"{start_year},{end_year}"
            )

        domain_task_count = 0

        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                month_tasks.append((str(control_file), year, month))
                domain_task_count += 1

        domain_summary.append(
            (domain, start_year, end_year, domain_task_count)
        )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print("GENERATE MULTIBASIN TASK FILES")
    print("=" * 78)

    print(f"CWARHM root       : {CWARHM_ROOT}")
    print(f"Control directory : {CONTROL_DIR}")
    print(f"Domain prefix     : {args.prefix or 'ALL'}")
    print(f"Start domain      : {args.start_domain or 'FIRST MATCH'}")
    print(f"Batch name        : {batch_name}")
    print(f"Selected domains  : {len(selected)}")
    print(f"Basin tasks       : {len(basin_tasks)}")
    print(f"Monthly tasks     : {len(month_tasks)}")
    print(f"Basin task file   : {basin_output}")
    print(f"Month task file   : {month_output}")
    print(f"Dry run           : {args.dry_run}")

    print()

    for domain, start_year, end_year, task_count in domain_summary:
        print(
            f"{domain:<12} "
            f"{start_year}-{end_year}  "
            f"{task_count} monthly tasks"
        )

    # --------------------------------------------------------
    # DRY RUN
    # --------------------------------------------------------

    if args.dry_run:
        print()
        print("DRY RUN - task files were not written.")
        return

    # --------------------------------------------------------
    # WRITE BASIN TASK FILE
    # --------------------------------------------------------

    basin_output.parent.mkdir(parents=True, exist_ok=True)

    with basin_output.open("w") as file:
        for control_file in basin_tasks:
            file.write(f"{control_file}\n")

    # --------------------------------------------------------
    # WRITE MONTH TASK FILE
    # --------------------------------------------------------

    month_output.parent.mkdir(parents=True, exist_ok=True)

    with month_output.open("w") as file:
        for control_file, year, month in month_tasks:
            file.write(f"{control_file}\t{year}\t{month}\n")

    # --------------------------------------------------------
    # VERIFY BASIN TASK FILE
    # --------------------------------------------------------

    if not basin_output.exists():
        raise RuntimeError("Basin task file was not created.")

    with basin_output.open() as file:
        written_basin_tasks = [
            line.strip()
            for line in file
            if line.strip()
        ]

    if len(written_basin_tasks) != len(basin_tasks):
        raise RuntimeError(
            "Basin task-file row-count verification failed.\n"
            f"Expected: {len(basin_tasks)}\n"
            f"Written : {len(written_basin_tasks)}"
        )

    if written_basin_tasks != basin_tasks:
        raise RuntimeError(
            "Basin task-file contents do not match selected controls."
        )

    # --------------------------------------------------------
    # VERIFY MONTH TASK FILE
    # --------------------------------------------------------

    if not month_output.exists():
        raise RuntimeError("Month task file was not created.")

    with month_output.open() as file:
        written_month_count = sum(
            1 for line in file if line.strip()
        )

    if written_month_count != len(month_tasks):
        raise RuntimeError(
            "Month task-file row-count verification failed.\n"
            f"Expected: {len(month_tasks)}\n"
            f"Written : {written_month_count}"
        )

    # --------------------------------------------------------
    # FINISH
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print("MULTIBASIN TASK FILES CREATED")
    print("=" * 78)

    print(f"Domains       : {len(selected)}")
    print(f"Basin tasks   : {len(basin_tasks)}")
    print(f"Monthly tasks : {len(month_tasks)}")
    print(f"Basin file    : {basin_output}")
    print(f"Month file    : {month_output}")

    print()
    print("No control_active.txt was used or modified.")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()