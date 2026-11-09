#!/usr/bin/env python3
"""Archive per-module spatial attributes, preserving consolidated CSVs.

Default: inspect only. --execute creates ZIPs without deleting sources.
--delete-originals requires --execute and removes module directories only after
both distributed and lumped ZIPs have been fully verified.

Run ONLY after the target basin collection has finished processing and passed QA.
Archived modules must be extracted again before rerunning extractors or consolidation.
"""
import argparse
import csv
import os
import shutil
import sys
import zlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

MODULES = frozenset({
    'terrain', 'soilgrids', 'pelletier', 'glhymps', 'hydrolakes',
    'forest_height', 'glclu2019', 'lgrip30', 'lai', 'worldclim',
})


def valid_final_csv(path, expected_rows):
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f'missing/empty consolidated CSV: {path}')
    with path.open(newline='') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header or header[:4] != ['Category', 'Attribute', 'Unit', 'Source']:
            raise ValueError(f'invalid consolidated CSV header: {path}')
        n = sum(1 for _ in reader)
    if expected_rows is not None and n != expected_rows:
        raise ValueError(f'expected {expected_rows} rows, got {n}: {path}')


def source_inventory(base):
    folders = sorted(p for p in base.iterdir() if p.is_dir() and p.name in MODULES)
    files = sorted((p for folder in folders for p in folder.rglob('*') if p.is_file()))
    return folders, files


def crc_file(path):
    crc = 0
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            crc = zlib.crc32(chunk, crc)
    return crc & 0xffffffff


def validate_archive(archive, base, files):
    expected = {p.relative_to(base).as_posix(): p for p in files}
    with ZipFile(archive) as z:
        if z.testzip() is not None:
            raise RuntimeError(f'CRC verification failed: {archive}')
        names = z.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise RuntimeError(f'archive file listing mismatch: {archive}')
        for info in z.infolist():
            src = expected[info.filename]
            if info.file_size != src.stat().st_size or info.CRC != crc_file(src):
                raise RuntimeError(f'archived contents differ from source: {src}')


def make_archive(base, files):
    target = base / 'attribute_modules.zip'
    if target.exists():
        validate_archive(target, base, files)
        return 'verified-existing'
    temp = base / 'attribute_modules.zip.tmp'
    if temp.exists():
        raise RuntimeError(f'temporary ZIP already exists; inspect before retry: {temp}')
    try:
        with ZipFile(temp, 'w', compression=ZIP_DEFLATED, compresslevel=4, allowZip64=True) as z:
            for src in files:
                z.write(src, src.relative_to(base).as_posix())
        validate_archive(temp, base, files)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return 'created'


def handle_domain(domain, args):
    basin = domain.name.removeprefix('domain_')
    parts = (
        (domain / 'attributes', f'{basin}_attributes.csv'),
        (domain / 'lumped' / 'attributes', f'{basin}_lumped_attributes.csv'),
    )
    for base, filename in parts:
        valid_final_csv(base / filename, args.expected_rows)
    inventories = [(base, *source_inventory(base)) for base, _ in parts]
    total_files = sum(len(files) for _, _, files in inventories)
    if not total_files:
        if all((base / 'attribute_modules.zip').is_file() for base, _ in parts):
            return 'already-archived', 0
        raise RuntimeError('no module files found and one or more archives missing')
    if any(not files for _, _, files in inventories):
        raise RuntimeError('partial module output; expected both distributed and lumped')
    if not args.execute:
        return 'would-archive', total_files
    for base, _, files in inventories:
        make_archive(base, files)
    # Both ZIPs must be verified before deleting either side.
    for base, _, files in inventories:
        validate_archive(base / 'attribute_modules.zip', base, files)
    if args.delete_originals:
        for _, folders, _ in inventories:
            for folder in folders:
                shutil.rmtree(folder)
        return 'archived-and-removed', total_files
    return 'archived-kept-originals', total_files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--domains-root', type=Path, required=True,
                   help='Parent directory of domain_* folders')
    p.add_argument('--expected-domains', type=int)
    p.add_argument('--expected-rows', type=int, default=468)
    p.add_argument('--execute', action='store_true',
                   help='Create or verify archives (otherwise read-only)')
    p.add_argument('--delete-originals', action='store_true',
                   help='After verifying BOTH ZIPs, delete module directories')
    p.add_argument('--basin', help='Process one domain only, e.g. CAN_01AD003')
    args = p.parse_args()
    if args.delete_originals and not args.execute:
        p.error('--delete-originals requires --execute')
    root = args.domains_root.resolve()
    if not root.is_dir():
        p.error(f'not a directory: {root}')
    domains = sorted(root.glob('domain_*'))
    if args.basin:
        domains = [root / f'domain_{args.basin}']
        if not domains[0].is_dir():
            p.error(f'basin directory not found: {domains[0]}')
    if args.expected_domains is not None and len(domains) != args.expected_domains:
        p.error(f'found {len(domains)} domains, expected {args.expected_domains}')
    failures = []
    for domain in domains:
        try:
            status, count = handle_domain(domain, args)
            print(f'{domain.name}: {status} ({count} module files)', flush=True)
        except Exception as exc:
            failures.append((domain.name, str(exc)))
            print(f'{domain.name}: ERROR {exc}', file=sys.stderr, flush=True)
    print(f'Finished: {len(domains) - len(failures)}/{len(domains)} basins without errors; '
          f'{len(failures)} errors', flush=True)
    if failures:
        sys.exit(1)


if __name__ == '__main__':
    main()
