#!/usr/bin/env python3
"""Consolidate existing NWAM per-module attribute CSVs into CAMELS-SPAT-style tables.

This does NOT run modules, alter parameters/, remove sources, or modify SUMMA.
Missing or nonfinite scientific values become blanks; schema & QA are logged centrally.
A prebuilt schema is recommended for reproducible batch outputs.
"""
import argparse
import csv
import json
import math
import os
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

CORE = ('terrain', 'soilgrids', 'pelletier', 'glhymps', 'hydrolakes',
        'forest_height', 'glclu2019', 'lgrip30', 'lai')
OPTIONAL = 'worldclim'
SOURCES = {'terrain': ('Topography', 'Terrain / MERIT Hydro'),
           'soilgrids': ('Soil', 'SoilGrids'),
           'pelletier': ('Soil', 'Pelletier'),
           'glhymps': ('Geology', 'GLHYMPS'),
           'hydrolakes': ('Open water', 'HydroLAKES'),
           'forest_height': ('Land cover', 'Forest height'),
           'glclu2019': ('Land cover', 'GLCLU2019'),
           'lgrip30': ('Land cover', 'LGRIP30'),
           'lai': ('Land cover', 'MODIS LAI (2013-2023)'),
           'worldclim': ('Climate', 'WorldClim')}
ID_COLS = {'hruId', 'gruId', 'HRUarea_m2'}


def unit_for(module, name):
    n = name.lower()
    if module == 'worldclim':
        return {'mean_annual_precipitation': 'mm/year',
                'mean_annual_temperature': 'deg C',
                'mean_annual_pet': 'mm/year',
                'temperature_annual_range': 'deg C'}.get(name, '-')
    if module == 'pelletier':
        return 'm'
    if module == 'glhymps':
        return '-' if 'porosity' in n else 'log10(m2) (verify source convention)'
    if module == 'hydrolakes':
        if 'number' in n or n == 'known_reservoirs': return 'count'
        if 'volume' in n: return 'million m3'
        if 'area' in n: return 'km2'
    if module in ('glclu2019','lgrip30'): return 'fraction'
    if module == 'lai': return 'm2/m2'
    if module == 'forest_height': return 'm'
    if module == 'terrain':
        if 'slope' in n or 'aspect' in n: return 'degrees'
        if 'elev' in n or 'dem' in n: return 'm'
    # SoilGrids includes mixed depth-dependent units and derived variables.
    # Do not guess scientific units; annotate from a verified catalog later.
    return 'VERIFY'


def atomic_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.stem + '_', suffix='.tmp', dir=path.parent)
    os.close(fd)
    try:
        with open(temp, 'w', newline='', encoding='utf-8') as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def atomic_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.stem + '_', suffix='.tmp', dir=path.parent)
    os.close(fd)
    try:
        with open(temp, 'w', encoding='utf-8') as fp: json.dump(content, fp, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def find_module_file(domain_path, mode, module):
    root = domain_path / ('attributes' if mode == 'distributed' else 'lumped/attributes') / module
    if not root.is_dir(): return None
    prefix = 'hru_' if mode == 'distributed' else 'lumped_'
    candidates = sorted(root.glob(prefix + '*_attributes.csv'))
    if len(candidates) > 1:
        raise ValueError(f'Ambiguous {mode} {module} attribute files: {candidates}')
    return candidates[0] if candidates else None


def id_key(value):
    """Canonical, lossless decimal ID representation, e.g. 7.0 -> '7'."""
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f'Invalid identifier: {value!r}') from exc
    if not d.is_finite():
        raise ValueError(f'Nonfinite identifier: {value!r}')
    return format(d.normalize(), 'f')


def id_label(key):
    """CAMELS-SPAT style: 72048346.0 or 72048346.5."""
    return key if '.' in key else key + '.0'


def get_hru_ids(domain, mode):
    p = domain / ('settings/SUMMA/attributes.nc' if mode == 'distributed' else 'lumped/settings/SUMMA/attributes.nc')
    with xr.open_dataset(p, decode_cf=False) as ds:
        ids = [id_key(x.item() if hasattr(x, 'item') else x)
               for x in np.asarray(ds['hruId'].values).ravel()]
        grus = [id_key(x.item() if hasattr(x, 'item') else x)
                for x in np.asarray(ds['hru2gruId'].values).ravel()]
    if len(ids) != len(set(ids)) or len(ids) != len(grus):
        raise ValueError(f'Duplicate or invalid SUMMA IDs: {p}')
    return ids, dict(zip(ids, grus))


def read_module(path, expected_ids, grus):
    df = pd.read_csv(path, low_memory=False, dtype={'hruId': 'string', 'gruId': 'string'})
    if not ID_COLS.issubset(df.columns):
        raise ValueError(f'Missing identifiers in {path}')
    if df['hruId'].isna().any() or df['gruId'].isna().any():
        raise ValueError(f'Null HRU/GRU identifiers in {path}')
    df['hruId'] = [id_key(x) for x in df['hruId']]
    df['gruId'] = [id_key(x) for x in df['gruId']]
    if df['hruId'].duplicated().any() or set(df.hruId) != set(expected_ids):
        raise ValueError(f'HRU ID mismatch in {path}: check fractional IDs and original source')
    df = df.set_index('hruId').loc[expected_ids]
    for hru in expected_ids:
        if df.loc[hru, 'gruId'] != grus[hru]:
            raise ValueError(f'GRU mismatch for HRU {hru} in {path}')
    columns = [c for c in df.columns if c not in ID_COLS and not c.endswith('_valid_pixels')]
    if len(columns) != len(set(columns)):
        raise ValueError(f'Duplicate attribute names in {path}')
    return df, columns


def build_rows(domain, mode, modules, schema):
    ids, grus = get_hru_ids(domain, mode)
    state = {}
    values = {}
    areas = {}
    found = {}
    for module in modules:
        p = find_module_file(domain, mode, module)
        if p is None:
            state[module] = 'missing_module_csv'
            continue
        df, columns = read_module(p, ids, grus)
        found[module] = columns
        state[module] = 'read'
        for hru in ids:
            area = pd.to_numeric(pd.Series([df.loc[hru, 'HRUarea_m2']]), errors='coerce').iloc[0]
            if np.isfinite(area):
                if hru in areas and not np.isclose(areas[hru], area, rtol=1e-5, atol=1):
                    raise ValueError(f'Inconsistent HRUarea_m2 for HRU {hru} ({module})')
                areas[hru] = float(area)
        for col in columns:
            values[module, col] = pd.to_numeric(df[col], errors='coerce').replace([np.inf, -np.inf], np.nan)
    if not found:
        raise ValueError(f'No attribute module CSVs found for {domain.name} {mode}')
    if schema is not None:
        schema_modules = {x['module'] for x in schema}
        absent = set(modules) - schema_modules
        if absent:
            raise ValueError(f'Modules missing from schema: {sorted(absent)}')

    if schema is None:
        catalog = [(m, c, *SOURCES[m], unit_for(m, c)) for m in modules for c in found.get(m, [])]
    else:
        catalog = [(x['module'], x['attribute'], x['category'], x['source'], x['unit'])
                   for x in schema if x['module'] in modules]

    rows = []
    missing_cells = 0
    for name, unit, source, getter in (
        ('gruId', '-', 'SUMMA attributes.nc', lambda h: grus[h]),
        ('HRUarea_m2', 'm2', 'CWARHM shapefile', lambda h: areas.get(h, math.nan)),
    ):
        row = {'Category': 'Basin', 'Attribute': name, 'Unit': unit, 'Source': source}
        for hru in ids:
            val = getter(hru)
            if pd.isna(val): missing_cells += 1
            row[id_label(hru)] = '' if pd.isna(val) else (id_label(val) if name == 'gruId' else val)
        rows.append(row)

    unavailable = []
    for module, col, category, source, unit in catalog:
        row = {'Category': category, 'Attribute': col, 'Unit': unit, 'Source': source}
        v = values.get((module, col))
        if v is None: unavailable.append(f'{module}:{col}')
        for hru in ids:
            value = (v.loc[hru] if v is not None else math.nan)
            if not np.isfinite(value):
                row[id_label(hru)] = ''
                missing_cells += 1
            else:
                row[id_label(hru)] = float(value)
        rows.append(row)
    status = {
        'domain': domain.name, 'configuration': mode,
        'num_hrus': len(ids), 'attribute_rows': len(rows),
        'missing_cells': missing_cells, 'modules': state,
        'unavailable_attribute_columns': unavailable[:100],
        'unavailable_attribute_count': len(unavailable),
        'result': ('complete' if missing_cells == 0 and all(m in found for m in modules)
                   else 'partial_missing_data'),
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
    }
    return ids, rows, status, catalog


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('control_file', type=Path)
    p.add_argument('--mode', choices=['both', 'distributed', 'lumped'], default='both')
    p.add_argument('--with-worldclim', action='store_true')
    p.add_argument('--schema', type=Path, help='Central schema CSV; generate if absent with --init-schema')
    p.add_argument('--init-schema', action='store_true', help='Write schema from this pilot, without overwriting existing schema')
    p.add_argument('--reports', type=Path, default=Path('3c_spatial_attributes/reports'))
    args = p.parse_args()
    text = args.control_file.read_text()
    cfg = {}
    for line in text.splitlines():
        if '|' in line and not line.lstrip().startswith('#'):
            k, v = line.split('|', 1)
            cfg[k.strip()] = v.split('#', 1)[0].strip()
    if 'root_path' not in cfg or 'domain_name' not in cfg:
        raise ValueError('Control missing root_path or domain_name')
    domain = Path(cfg['root_path']) / f"domain_{cfg['domain_name']}"
    modules = CORE + ((OPTIONAL,) if args.with_worldclim else ())
    modes = ['distributed', 'lumped'] if args.mode == 'both' else [args.mode]
    schema = None
    if args.schema and args.schema.exists():
        with args.schema.open(newline='') as fp: schema = list(csv.DictReader(fp))
        if not schema: raise ValueError('Schema is empty')
    elif args.schema and not args.init_schema:
        raise FileNotFoundError(f'Schema not found: {args.schema}; initialize with --init-schema')
    if args.init_schema and args.schema and args.schema.exists():
        raise FileExistsError(f'Will not replace schema: {args.schema}')
    all_results = []
    initial_catalog = None
    # Compute and validate both configurations before writing either final result.
    for mode in modes:
        ids, rows, report, catalog = build_rows(domain, mode, modules, schema)
        if initial_catalog is None: initial_catalog = catalog
        all_results.append((mode, ids, rows, report))
    if args.init_schema:
        if not args.schema: raise ValueError('--init-schema requires --schema')
        for _, _, _, report in all_results:
            missing_modules = [m for m, state in report['modules'].items() if state != 'read']
            if missing_modules:
                raise ValueError(f'Cannot initialize a full schema: {report["configuration"]} missing {missing_modules}')
        schema_records = [{'module': m, 'attribute': c, 'category': cat, 'source': source, 'unit': unit}
                          for m, c, cat, source, unit in initial_catalog]
        atomic_csv(args.schema, schema_records, ['module', 'attribute', 'category', 'source', 'unit'])
        print('Schema created:', args.schema)
    for mode, ids, rows, report in all_results:
        output = (domain / 'attributes' / f"{cfg['domain_name']}_attributes.csv" if mode == 'distributed'
                  else domain / 'lumped/attributes' / f"{cfg['domain_name']}_lumped_attributes.csv")
        atomic_csv(output, rows, ['Category', 'Attribute', 'Unit', 'Source', *map(id_label, ids)])
        # Re-open final output and compare its shape/keys before declaring success.
        with output.open(newline='') as fp:
            reader = csv.DictReader(fp)
            if reader.fieldnames != ['Category','Attribute','Unit','Source',*map(id_label,ids)]:
                raise RuntimeError(f'Incorrect output columns: {output}')
            count = sum(1 for _ in reader)
            if count != len(rows): raise RuntimeError(f'Incorrect row count: {output}')
        audit = args.reports / cfg['domain_name'] / f'{mode}.json'
        atomic_json(audit, report)
        print(f'{mode}: {len(ids)} HRUs; {len(rows)} rows; {report["missing_cells"]} blanks; {report["result"]}')
        print('  final:', output)
        print('  audit:', audit)
    print('All parameters/ datasets and intermediate module CSVs preserved.')


if __name__ == '__main__':
    main()
