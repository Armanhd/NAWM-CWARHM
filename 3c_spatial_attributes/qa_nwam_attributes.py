#!/usr/bin/env python3
"""Read-only NWAM attribute QA for meso_scale, macro_scale or headwater.
Usage: python qa_nwam_attributes.py --scale meso_scale
Run from NWAM root, or pass --root /absolute/path/to/NWAM.
"""
import argparse
import csv
import json
import math
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

import netCDF4

p = argparse.ArgumentParser()
p.add_argument('--scale', required=True, choices=['meso_scale','macro_scale','headwater'])
p.add_argument('--root', type=Path, default=Path.cwd())
p.add_argument('--expected', type=int, default=None)
a = p.parse_args()
base = a.root.resolve()
domains = base / 'NWAM_Data/CAMELS_SPAT_basins_prcp' / a.scale
report_root = base / '3c_spatial_attributes/reports/batch' / a.scale
qa_root = report_root / 'qa'
qa_root.mkdir(parents=True, exist_ok=True)
issues = []
missing = Counter()
missing_by_basin = Counter()
non_numeric = Counter()
row_counts = Counter()
file_counts = Counter()
reference_schema = None
reference_basin = None


def problem(basin, mode, issue, detail=''):
    issues.append(dict(basin=basin, mode=mode, issue=issue, detail=str(detail)))


def number_key(value):
    """Numerically compare ID strings, retaining fractional IDs (no int coercion)."""
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f'not numeric: {value!r}') from exc
    if not d.is_finite():
        raise ValueError(f'non-finite ID: {value!r}')
    return d


def read_summa_ids(path):
    with netCDF4.Dataset(path) as ds:
        if 'hruId' not in ds.variables:
            raise ValueError('no hruId variable')
        v = ds.variables['hruId'][:]
        if hasattr(v, 'filled'):
            v = v.filled(float('nan'))
        return [number_key(str(x)) for x in v.tolist()]


basins = sorted(domains.glob('domain_*'))
print('Scale:', a.scale)
print('Domains found:', len(basins))
if a.expected is not None and len(basins) != a.expected:
    problem('*', '*', 'domain_count', f'{len(basins)} != {a.expected}')

for domain in basins:
    basin = domain.name.removeprefix('domain_')
    status_path = report_root / 'basins' / f'{basin}.json'
    if a.scale == 'meso_scale' or status_path.exists():
        if not status_path.exists():
            problem(basin, '*', 'missing_batch_report')
        else:
            try:
                status = json.loads(status_path.read_text())
                if status.get('status') != 'complete_or_partial_data':
                    problem(basin, '*', 'batch_not_complete', status.get('status'))
            except Exception as ex:
                problem(basin, '*', 'bad_batch_report', ex)
    for mode, csvpath, ncpath in (
        ('distributed', domain/'attributes'/f'{basin}_attributes.csv', domain/'settings/SUMMA/attributes.nc'),
        ('lumped', domain/'lumped/attributes'/f'{basin}_lumped_attributes.csv', domain/'lumped/settings/SUMMA/attributes.nc'),
    ):
        if not csvpath.is_file():
            problem(basin, mode, 'missing_csv', csvpath)
            continue
        try:
            with csvpath.open(newline='') as f:
                reader = csv.reader(f)
                header = next(reader)
                records = list(reader)
        except Exception as ex:
            problem(basin, mode, 'unreadable_csv', ex)
            continue
        file_counts[mode] += 1
        row_counts[(mode,len(records))] += 1
        if len(records) != 468:
            problem(basin, mode, 'attribute_row_count', len(records))
        if header[:4] != ['Category','Attribute','Unit','Source']:
            problem(basin, mode, 'bad_metadata_columns', header[:4])
        if len(header) < 5:
            problem(basin, mode, 'no_hru_columns')
            continue
        if len(header) != len(set(header)):
            problem(basin, mode, 'duplicate_csv_column')
        if any(len(r) != len(header) for r in records):
            problem(basin, mode, 'ragged_csv_rows')
            continue
        schema = [tuple(r[:4]) for r in records]
        if len({(r[0],r[1]) for r in records}) != len(records):
            problem(basin, mode, 'duplicate_category_attribute_pair')
        if reference_schema is None:
            reference_schema = schema
            reference_basin = (basin,mode)
        elif schema != reference_schema:
            problem(basin, mode, 'metadata_schema_mismatch', f'reference={reference_basin}')
        try:
            csv_ids = [number_key(c) for c in header[4:]]
            if len(csv_ids) != len(set(csv_ids)):
                problem(basin, mode, 'duplicate_hru_ids')
            nc_ids = read_summa_ids(ncpath)
            if len(csv_ids) != len(nc_ids) or set(csv_ids) != set(nc_ids):
                problem(basin, mode, 'summa_hru_id_mismatch', f'CSV={len(csv_ids)} SUMMA={len(nc_ids)}')
        except Exception as ex:
            problem(basin, mode, 'hru_id_read_or_parse_error', ex)
        for rec in records:
            key = (mode,rec[0],rec[1])
            for cell in rec[4:]:
                v = cell.strip()
                if not v or v.lower() in ('nan','na','n/a','null','none'):
                    missing[key] += 1
                    missing_by_basin[(basin,mode)] += 1
                    continue
                try:
                    num = float(v)
                    if not math.isfinite(num):
                        missing[key] += 1
                        missing_by_basin[(basin,mode)] += 1
                except ValueError:
                    non_numeric[key] += 1
        # Spatial layers are preserved, but completeness of source-specific layers
        # must be reviewed separately using module coverage reports.
        if not (domain/'parameters').is_dir():
            problem(basin, mode, 'parameters_directory_missing')

# Read-only geometry repair audit for three known invalid meso-scale catchments.
if a.scale == 'meso_scale':
    try:
        import geopandas as gpd
        for basin in ('CAN_07GE007','USA_03078000','USA_14166500'):
            shp = domains/f'domain_{basin}'/'shapefiles/catchment'/f'{basin}_distributed_basin.shp'
            original = gpd.read_file(shp).to_crs('EPSG:6933')
            repaired = original.geometry.make_valid()
            if repaired.is_empty.any() or not repaired.is_valid.all():
                problem(basin,'distributed','geometry_repair_invalid')
                continue
            a0 = original.geometry.area.to_numpy()
            a1 = repaired.area.to_numpy()
            relative = abs(a1.sum()-a0.sum())/max(abs(a0.sum()),1.0)
            maximum = max((abs(x-y)/max(abs(x),1.0) for x,y in zip(a0,a1)),default=0)
            print(f'GEOMETRY {basin}: HRUs={len(original)} max_relative_area_change={maximum:.6%} total_relative_area_change={relative:.6%}')
            if maximum > 0.001 or relative > 0.001:
                problem(basin,'distributed','geometry_area_change_review',f'max={maximum:.6%};total={relative:.6%}')
    except Exception as ex:
        problem('*','distributed','geometry_audit_failed',ex)

out_issues = qa_root/'attribute_qa_issues.csv'
with out_issues.open('w',newline='') as f:
    w = csv.DictWriter(f,fieldnames=['basin','mode','issue','detail'])
    w.writeheader(); w.writerows(issues)
out_missing = qa_root/'missing_by_attribute.csv'
with out_missing.open('w',newline='') as f:
    w = csv.writer(f)
    w.writerow(['mode','category','attribute','missing_cells','non_numeric_cells'])
    for k in sorted(set(missing)|set(non_numeric)):
        w.writerow([*k,missing[k],non_numeric[k]])
out_basin = qa_root/'missing_by_basin.csv'
with out_basin.open('w',newline='') as f:
    w = csv.writer(f); w.writerow(['basin','mode','missing_cells'])
    for (basin,mode),n in sorted(missing_by_basin.items()):
        w.writerow([basin,mode,n])
print('CSV files:',dict(file_counts))
print('Row counts:',dict((f'{mode}:{n}',v) for (mode,n),v in sorted(row_counts.items())))
print('Structural/ID issues:',len(issues))
print('Missing numeric cells (all basins):',sum(missing.values()))
print('Non-numeric data cells:',sum(non_numeric.values()))
print('Top missing attributes:',missing.most_common(12))
print('Issues file:',out_issues)
print('Missing attribute report:',out_missing)
print('Missing basin report:',out_basin)
for item in issues[:20]:
    print('ISSUE:',item)
if issues or non_numeric:
    raise SystemExit(1)
print('PASS: structural, schema and SUMMA ID QA; missing-value reports retained for scientific review.')
