#!/usr/bin/env python3
"""Select a control from BASIN_TASK and call the Step 11 per-basin worker."""
import argparse
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task-file', required=True, type=Path)
    p.add_argument('--index', required=True, type=int, help='Zero-based Slurm array index')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--with-worldclim', action='store_true')
    p.add_argument('--force', action='store_true')
    args = p.parse_args()
    task = args.task_file.resolve()
    rows = [r.strip() for r in task.read_text().splitlines() if r.strip() and not r.lstrip().startswith('#')]
    if not 0 <= args.index < len(rows):
        p.error(f'index {args.index} out of range [0, {len(rows)-1}]')
    control = Path(rows[args.index])
    if not control.is_absolute():
        control = task.parent / control
    cmd = [sys.executable, str(HERE/'process_basin_attributes.py'), str(control)]
    if args.execute: cmd.append('--execute')
    if args.with_worldclim: cmd.append('--with-worldclim')
    if args.force: cmd.append('--force')
    return subprocess.run(cmd).returncode

if __name__ == '__main__':
    raise SystemExit(main())
