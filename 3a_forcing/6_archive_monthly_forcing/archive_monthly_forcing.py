#!/usr/bin/env python3
# coding: utf-8

"""
Archive monthly forcing files after a completed CWARHM workflow.

The script processes ONE completed domain directory, for example:

    /work/.../CENTURY_basins_prcp/domain_CAN_01AD003

It automatically archives monthly NetCDF files from:

DISTRIBUTED
-----------
forcing/1_raw_data/EM_Earth_prepared/
forcing/1_raw_data/ERA5_prepared/
forcing/3_basin_averaged_data/EM_Earth/
forcing/3_basin_averaged_data/ERA5/
forcing/4_SUMMA_input/

LUMPED
------
lumped/forcing/3_basin_averaged_data/EM_Earth/
lumped/forcing/3_basin_averaged_data/ERA5/
lumped/forcing/4_SUMMA_input/

For every target directory:

    monthly *.nc files
        -> monthly_netcdf.tar

If _workflow_log exists:

    _workflow_log/* files
        -> _workflow_log/workflow_logs.zip

Original files are deleted ONLY after the corresponding archive has
been successfully created and verified.

The following are NOT modified:

    forcing/5_SUMMA_input_concat/
    forcing/6_SUMMA_input_LST/
    lumped/forcing/5_SUMMA_input_concat/
    lumped/forcing/6_SUMMA_input_LST/

Usage
-----
Dry run:

    python archive_monthly_forcing.py \
        --domain-root /path/to/domain_CAN_01AD003 \
        --dry-run

Archive:

    python archive_monthly_forcing.py \
        --domain-root /path/to/domain_CAN_01AD003
"""

from pathlib import Path
import argparse
import os
import re
import tarfile
import zipfile


# =====================================================================
# MONTHLY FILE PATTERNS
# =====================================================================

TARGETS = [
    {
        "label": "distributed prepared EM-Earth",
        "relative_dir": "forcing/1_raw_data/EM_Earth_prepared",
        "pattern": re.compile(r"^EM_Earth_SUMMA_(\d{6})\.nc$"),
    },
    {
        "label": "distributed prepared ERA5",
        "relative_dir": "forcing/1_raw_data/ERA5_prepared",
        "pattern": re.compile(r"^ERA5_SUMMA_(\d{6})\.nc$"),
    },
    {
        "label": "distributed remapped EM-Earth",
        "relative_dir": "forcing/3_basin_averaged_data/EM_Earth",
        "pattern": re.compile(r".*_EM_Earth_remapped_EM_Earth_SUMMA_(\d{6})\.nc$"),
    },
    {
        "label": "distributed remapped ERA5",
        "relative_dir": "forcing/3_basin_averaged_data/ERA5",
        "pattern": re.compile(r".*_ERA5_remapped_ERA5_SUMMA_(\d{6})\.nc$"),
    },
    {
        "label": "distributed monthly SUMMA forcing",
        "relative_dir": "forcing/4_SUMMA_input",
        "pattern": re.compile(r"^NWAM_SUMMA_forcing_(\d{6})\.nc$"),
    },
    {
        "label": "lumped remapped EM-Earth",
        "relative_dir": "lumped/forcing/3_basin_averaged_data/EM_Earth",
        "pattern": re.compile(r".*_lumped_EM_Earth_remapped_EM_Earth_SUMMA_(\d{6})\.nc$"),
    },
    {
        "label": "lumped remapped ERA5",
        "relative_dir": "lumped/forcing/3_basin_averaged_data/ERA5",
        "pattern": re.compile(r".*_lumped_ERA5_remapped_ERA5_SUMMA_(\d{6})\.nc$"),
    },
    {
        "label": "lumped monthly SUMMA forcing",
        "relative_dir": "lumped/forcing/4_SUMMA_input",
        "pattern": re.compile(r"^NWAM_SUMMA_forcing_(\d{6})\.nc$"),
    },
]


# =====================================================================
# MONTH CHECKS
# =====================================================================

def get_monthly_files(directory, pattern):
    matches = []

    for path in directory.iterdir():
        if not path.is_file():
            continue

        match = pattern.match(path.name)

        if match:
            matches.append((match.group(1), path))

    return sorted(matches, key=lambda item: item[0])


def next_month(ym):
    year = int(ym[:4])
    month = int(ym[4:])

    if month == 12:
        return f"{year + 1:04d}01"

    return f"{year:04d}{month + 1:02d}"


def validate_month_sequence(monthly_files):
    months = [ym for ym, _ in monthly_files]

    if not months:
        return

    if len(months) != len(set(months)):
        raise RuntimeError("Duplicate monthly files detected.")

    for current, following in zip(months[:-1], months[1:]):
        expected = next_month(current)

        if following != expected:
            raise RuntimeError(
                "Monthly files are not continuous.\n"
                f"Current : {current}\n"
                f"Expected: {expected}\n"
                f"Found   : {following}"
            )


# =====================================================================
# TAR
# =====================================================================

def get_tar_files(tar_path):
    with tarfile.open(tar_path, "r") as archive:
        return sorted(
            member.name
            for member in archive.getmembers()
            if member.isfile()
        )


def verify_tar(tar_path, expected_names):
    if not tar_path.is_file() or tar_path.stat().st_size == 0:
        raise RuntimeError(f"Invalid TAR archive:\n{tar_path}")

    saved = get_tar_files(tar_path)
    expected = sorted(expected_names)

    if saved != expected:
        raise RuntimeError(
            "TAR verification failed.\n"
            f"Archive : {tar_path}\n"
            f"Expected: {len(expected)} files\n"
            f"Found   : {len(saved)} files"
        )


def archive_netcdf(directory, pattern, dry_run):
    monthly_files = get_monthly_files(directory, pattern)
    archive_path = directory / "monthly_netcdf.tar"

    # Already archived
    if not monthly_files:
        if archive_path.is_file():
            print("NetCDF archive : ALREADY ARCHIVED")
            return "already_archived"

        print("NetCDF archive : SKIP - no matching monthly files")
        return "skip"

    validate_month_sequence(monthly_files)

    source_paths = [path for _, path in monthly_files]
    source_names = [path.name for path in source_paths]

    first_month = monthly_files[0][0]
    last_month = monthly_files[-1][0]

    print(f"Monthly files  : {len(source_paths)}")
    print(f"First month    : {first_month}")
    print(f"Last month     : {last_month}")
    print(f"Archive        : {archive_path}")

    if archive_path.exists():
        verify_tar(archive_path, source_names)

        if dry_run:
            print("DRY RUN        : existing TAR verified; originals would be deleted")
            return "dry_run"

        for path in source_paths:
            path.unlink()

        print(f"Deleted        : {len(source_paths)} monthly NetCDF files")
        return "archived"

    if dry_run:
        print(f"DRY RUN        : would TAR {len(source_paths)} NetCDF files")
        print(f"DRY RUN        : would delete {len(source_paths)} originals after verification")
        return "dry_run"

    temp_archive = directory / "monthly_netcdf.tar.tmp"

    if temp_archive.exists():
        temp_archive.unlink()

    try:
        with tarfile.open(temp_archive, "w") as archive:
            for path in source_paths:
                archive.add(path, arcname=path.name, recursive=False)

        verify_tar(temp_archive, source_names)

        os.replace(temp_archive, archive_path)

        verify_tar(archive_path, source_names)

    except Exception:
        if temp_archive.exists():
            temp_archive.unlink()
        raise

    for path in source_paths:
        path.unlink()

    print(f"TAR size       : {archive_path.stat().st_size / (1024**3):.3f} GB")
    print(f"Deleted        : {len(source_paths)} monthly NetCDF files")
    print("NetCDF archive : PASS")

    return "archived"


# =====================================================================
# WORKFLOW LOG ZIP
# =====================================================================

def collect_log_files(log_dir):
    if not log_dir.is_dir():
        return []

    return sorted(
        path
        for path in log_dir.rglob("*")
        if path.is_file()
        and path.name not in {
            "workflow_logs.zip",
            "workflow_logs.zip.tmp",
        }
    )


def verify_zip(zip_path, expected_names=None):
    if not zip_path.is_file() or zip_path.stat().st_size == 0:
        raise RuntimeError(f"Invalid ZIP archive:\n{zip_path}")

    with zipfile.ZipFile(zip_path, "r") as archive:
        bad = archive.testzip()

        if bad is not None:
            raise RuntimeError(
                f"Corrupt file inside ZIP: {bad}\n{zip_path}"
            )

        names = sorted(archive.namelist())

    if expected_names is not None and names != sorted(expected_names):
        raise RuntimeError(
            "Workflow-log ZIP verification failed.\n"
            f"Archive : {zip_path}\n"
            f"Expected: {len(expected_names)} files\n"
            f"Found   : {len(names)} files"
        )


def remove_empty_directories(log_dir):
    directories = sorted(
        [path for path in log_dir.rglob("*") if path.is_dir()],
        key=lambda path: len(path.parts),
        reverse=True,
    )

    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            pass


def archive_logs(directory, dry_run):
    log_dir = directory / "_workflow_log"

    if not log_dir.is_dir():
        print("Workflow logs  : SKIP - no _workflow_log")
        return "skip"

    source_files = collect_log_files(log_dir)
    zip_path = log_dir / "workflow_logs.zip"

    if not source_files:
        if zip_path.is_file():
            verify_zip(zip_path)
            print("Workflow logs  : ALREADY ARCHIVED")
            return "already_archived"

        print("Workflow logs  : SKIP - empty")
        return "skip"

    source_names = [
        path.relative_to(log_dir).as_posix()
        for path in source_files
    ]

    print(f"Log files      : {len(source_files)}")
    print(f"ZIP archive    : {zip_path}")

    if zip_path.exists():
        verify_zip(zip_path, source_names)

        if dry_run:
            print("DRY RUN        : existing ZIP verified; originals would be deleted")
            return "dry_run"

        for path in source_files:
            path.unlink()

        remove_empty_directories(log_dir)

        print(f"Deleted logs   : {len(source_files)}")
        return "archived"

    if dry_run:
        print(f"DRY RUN        : would ZIP {len(source_files)} log files")
        print(f"DRY RUN        : would delete {len(source_files)} originals after verification")
        return "dry_run"

    temp_zip = log_dir / "workflow_logs.zip.tmp"

    if temp_zip.exists():
        temp_zip.unlink()

    try:
        with zipfile.ZipFile(
            temp_zip,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:

            for path, name in zip(source_files, source_names):
                archive.write(path, arcname=name)

        verify_zip(temp_zip, source_names)

        os.replace(temp_zip, zip_path)

        verify_zip(zip_path, source_names)

    except Exception:
        if temp_zip.exists():
            temp_zip.unlink()
        raise

    for path in source_files:
        path.unlink()

    remove_empty_directories(log_dir)

    print(f"ZIP size       : {zip_path.stat().st_size / (1024**2):.2f} MB")
    print(f"Deleted logs   : {len(source_files)}")
    print("Workflow logs  : PASS")

    return "archived"


# =====================================================================
# MAIN
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Archive monthly CWARHM forcing for one completed domain."
    )

    parser.add_argument(
        "--domain-root",
        required=True,
        type=Path,
        help="Completed domain_<DOMAIN> directory.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without writing archives or deleting files.",
    )

    args = parser.parse_args()

    domain_root = args.domain_root.expanduser().resolve()

    if not domain_root.is_dir():
        raise FileNotFoundError(
            f"Domain directory not found:\n{domain_root}"
        )

    if not domain_root.name.startswith("domain_"):
        raise RuntimeError(
            "Expected directory name beginning with 'domain_'.\n"
            f"Found: {domain_root.name}"
        )

    domain = domain_root.name[len("domain_"):]

    print()
    print("=" * 80)
    print("ARCHIVE MONTHLY CWARHM FORCING")
    print("=" * 80)
    print(f"Domain      : {domain}")
    print(f"Domain root : {domain_root}")
    print(f"Dry run     : {args.dry_run}")
    print(f"Targets     : {len(TARGETS)}")
    print("=" * 80)

    results = []

    for index, target in enumerate(TARGETS, start=1):
        directory = domain_root / target["relative_dir"]

        print()
        print("=" * 80)
        print(f"[{index}/{len(TARGETS)}] {target['label']}")
        print("=" * 80)
        print(f"Directory      : {directory}")

        if not directory.is_dir():
            print("Status         : SKIP - directory not present")
            results.append((target["label"], "skip", "skip"))
            continue

        nc_status = archive_netcdf(
            directory,
            target["pattern"],
            args.dry_run,
        )

        log_status = archive_logs(
            directory,
            args.dry_run,
        )

        results.append(
            (target["label"], nc_status, log_status)
        )

    print()
    print("=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)

    for label, nc_status, log_status in results:
        print(
            f"{label:<38} "
            f"NetCDF={nc_status:<18} "
            f"logs={log_status}"
        )

    print()
    print(f"Domain : {domain}")

    if args.dry_run:
        print("RESULT : DRY RUN PASS - no files changed")
    else:
        print("RESULT : PASS")

    print("=" * 80)


if __name__ == "__main__":
    main()