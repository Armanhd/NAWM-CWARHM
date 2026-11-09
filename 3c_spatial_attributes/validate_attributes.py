#!/usr/bin/env python3
"""Generic Step 11 QA for any CWARHM BASIN_TASK (distributed + lumped).

Structural and ID QA only; missing numeric cells are reported, not fatal.
"""
import argparse
import csv
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
import math
import netCDF4
from process_basin_attributes import read_control


def numid(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite(): raise ValueError(value)
        return n
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'Bad HRU ID: {value!r}') from exc


def qa(path, ncpath, expected_rows, issues, missing, basin, mode, schema_ref):
    if not path.is_file():
        issues.append((basin, mode, 'missing_csv', str(path)))
        return
    try:
        with path.open(newline='') as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
        if header[:4] != ['Category','Attribute','Unit','Source']:
            issues.append((basin, mode, 'invalid_header', str(header[:4])))
        if len(header) < 5 or any(len(row) != len(header) for row in rows):
            issues.append((basin, mode, 'ragged_rows_or_no_hru', str(path)))
            return
        if expected_rows is not None and len(rows) != expected_rows:
            issues.append((basin, mode, 'wrong_row_count', len(rows)))
        if len(set((r[0],r[1]) for r in rows)) != len(rows):
            issues.append((basin, mode, 'duplicate_attributes', ''))
        schema = tuple(tuple(row[:4]) for row in rows)
        if schema_ref[0] is None: schema_ref[0] = schema
        elif schema != schema_ref[0]:
            issues.append((basin, mode, 'schema_mismatch', ''))
        csv_ids = list(map(numid, header[4:]))
        with netCDF4.Dataset(ncpath) as ds:
            var = ds.variables['hruId'][:]
            if hasattr(var, 'filled'): var = var.filled(float('nan'))
            nc_ids = [numid(str(v)) for v in var.tolist()]
        if len(csv_ids) != len(nc_ids) or len(set(csv_ids)) != len(csv_ids) or set(csv_ids) != set(nc_ids):
            issues.append((basin, mode, 'hru_ids_mismatch', f'{len(csv_ids)} CSV vs {len(nc_ids)} SUMMA'))
        for row in rows:
            for cell in row[4:]:
                if not cell.strip() or cell.strip().lower() in ('nan','na','n/a','null','none'):
                    missing[(mode,row[0],row[1])] += 1
                else:
                    try:
                        if not math.isfinite(float(cell)): missing[(mode,row[0],row[1])] += 1
                    except ValueError:
                        issues.append((basin, mode, 'non_numeric_cell', row[1]))
    except Exception as exc:
        issues.append((basin, mode, 'qa_exception', str(exc)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task-file', type=Path, required=True)
    p.add_argument('--expected-rows', type=int, default=468)
    p.add_argument('--report-dir', type=Path, default=Path('reports/qa'))
    args = p.parse_args()
    task = args.task_file.resolve()
    controls = []
    for line in task.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        control = Path(line)
        if not control.is_absolute(): control = task.parent / control
        controls.append(control)
    issues = []
    missing = Counter()
    schema_ref = [None]
    for control in controls:
        try:
            cfg = read_control(control)
            basin = cfg['domain_name']
            dom = Path(cfg['root_path']) / f'domain_{basin}'
        except Exception as exc:
            issues.append((str(control), '*', 'control_error', str(exc)))
            continue
        for mode, csv_path, nc in (
            ('distributed', dom/'attributes'/f'{basin}_attributes.csv', dom/'settings/SUMMA/attributes.nc'),
            ('lumped', dom/'lumped/attributes'/f'{basin}_lumped_attributes.csv', dom/'lumped/settings/SUMMA/attributes.nc'),
        ):
            qa(csv_path,nc,args.expected_rows,issues,missing,basin,mode,schema_ref)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    with (args.report_dir/'attribute_qa_issues.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['basin','mode','issue','detail']);w.writerows(issues)
    with (args.report_dir/'missing_by_attribute.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['mode','category','attribute','missing_cells'])
        for (mode, cat, att), count in sorted(missing.items()): w.writerow([mode,cat,att,count])
    print('Controls:', len(controls))
    print('QA issues:', len(issues))
    print('Missing numeric cells:', sum(missing.values()))
    print('Reports:', args.report_dir.resolve())
    for problem in issues[:20]: print('ISSUE:', problem)
    return 1 if issues else 0

if __name__ == '__main__': raise SystemExit(main())
