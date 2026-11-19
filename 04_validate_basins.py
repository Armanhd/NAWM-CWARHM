#!/usr/bin/env python3
"""Step 04: Independent, read-only validation of CAMELS-SPAT lumped conversions.

Checks converted files against basin-specific original CWARHM inputs and the
CENTURY-style reference. Optionally compares numerically with saved examples.
Writes only a consolidated CSV report (never modifies model files).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import tomllib
from collections import Counter
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
REQUIRED = (
    "summa_inputs/attributes.nc", "summa_inputs/trialParams.nc",
    "summa_inputs/trialParams.priori.nc", "summa_inputs/forcingFileList.txt",
    "summa_state/coldState.nc", "mizuroute_inputs/topology.nc",
    "mizuroute_inputs/lumped_to_hru.nc", "mizuroute_inputs/mizuroute.param",
)
FORCING_VARIABLES = (
    "airpres", "airtemp", "LWRadAtm", "pptrate", "spechum",
    "SWRadAtm", "windspd",
)
COMPARE_FILES = (
    "summa_inputs/attributes.nc", "summa_inputs/trialParams.nc",
    "summa_inputs/trialParams.priori.nc", "summa_state/coldState.nc",
    "mizuroute_inputs/topology.nc", "mizuroute_inputs/lumped_to_hru.nc",
)
FIELDS = (
    "index", "group", "basin", "status", "issues", "warnings",
    "historical_comparison", "historical_differences", "forcing_files",
    "forcing_time_steps", "forcing_start", "forcing_end",
    "routing_hrus", "daily_observations", "hourly_observations",
    "domain", "source",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def values(var):
    return np.ma.asarray(var[:])


def identical_values(a, b):
    """Compare masked arrays, including masks and NaNs at identical positions."""
    aa, bb = np.ma.asarray(a), np.ma.asarray(b)
    if aa.shape != bb.shape or not np.array_equal(np.ma.getmaskarray(aa), np.ma.getmaskarray(bb)):
        return False
    x, y = np.asarray(aa.filled(0)), np.asarray(bb.filled(0))
    return bool(np.array_equal(x, y, equal_nan=True)) if x.dtype.kind in 'fc' and y.dtype.kind in 'fc' else bool(np.array_equal(x, y))


def integer_ids(ds, name):
    a = values(ds.variables[name]).reshape(-1)
    require(a.size > 0 and not np.ma.getmaskarray(a).any(), f"{name} is empty or masked")
    out = np.asarray(a, dtype=np.int64)
    require(np.all(np.asarray(a) == out), f"{name} contains non-integer values")
    return out


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def compare_copied(a, b, label, issues, hash_files=False):
    if not a.is_file() or not b.is_file():
        issues.append(f"{label}: missing input or output")
    elif a.stat().st_size != b.stat().st_size:
        issues.append(f"{label}: source/output sizes differ")
    elif hash_files and digest(a) != digest(b):
        issues.append(f"{label}: source/output SHA256 differ")


def forcing_names(path):
    names = [s.strip() for s in path.read_text().splitlines()
             if s.strip() and not s.lstrip().startswith('#')]
    require(names and len(names) == len(set(names)), 'Empty/duplicate forcing list')
    for name in names:
        require(name not in ('.', '..') and Path(name).name == name and '\\' not in name,
                f"Unsafe forcing name: {name}")
    return names


def compare_netcdf(old, new):
    """Return substantive differences only; ignore global/variable attributes."""
    problems = []
    with Dataset(old) as a, Dataset(new) as b:
        if {k: len(v) for k, v in a.dimensions.items()} != {k: len(v) for k, v in b.dimensions.items()}:
            problems.append('dimensions')
        if set(a.variables) != set(b.variables):
            problems.append('variable names')
        for name in sorted(set(a.variables) & set(b.variables)):
            av, bv = a.variables[name], b.variables[name]
            if av.dimensions != bv.dimensions or av.dtype != bv.dtype:
                problems.append(f'{name}: schema')
            elif not identical_values(values(av), values(bv)):
                problems.append(f'{name}: values')
    return problems


def inspect_forcing(file, ids, issues):
    """Check known SUMMA meteorological variables and basic time validity."""
    with Dataset(file) as ds:
        require('hruId' in ds.variables, 'missing hruId')
        require(np.array_equal(integer_ids(ds, 'hruId'), ids), 'forcing HRU ID mismatch')
        missing = [v for v in FORCING_VARIABLES if v not in ds.variables]
        require(not missing, f"missing SUMMA forcing variables: {','.join(missing)}")
        require('time' in ds.variables, 'missing time variable')
        t = values(ds.variables['time']).reshape(-1)
        require(t.size > 0 and not np.ma.getmaskarray(t).any(), 'empty/masked time values')
        time = np.asarray(t, dtype=np.float64)
        require(np.all(np.isfinite(time)), 'nonfinite time values')
        require(np.all(np.diff(time) > 0), 'time not strictly increasing')
        time_var = ds.variables['time']
        require(bool(getattr(time_var, 'units', '')), 'time units missing')
        for name in FORCING_VARIABLES:
            v = ds.variables[name]
            require(any(dim == 'time' for dim in v.dimensions), f'{name} missing time dimension')
            require(v.shape[v.dimensions.index('time')] == len(time), f'{name} time length mismatch')
        return len(time), float(time[0]), float(time[-1]), str(time_var.units)


def inspect_one(row, dest, config, examples, hash_copies):
    basin, source = row['basin'], Path(row['source'])
    domain = dest / 'domain' / basin
    result = {k: '' for k in FIELDS}
    result.update(index=row['index'], group=row['group'], basin=basin,
                  domain=str(domain), source=str(source), forcing_files=0,
                  forcing_time_steps=0, routing_hrus=0, daily_observations=0,
                  hourly_observations=0)
    issues, warnings = [], []
    history_status = 'SKIPPED' if examples is None else 'MISSING'
    history_diffs = []
    if row['status'] != 'READY':
        result.update(status='SOURCE_REVIEW', issues=row['problems'])
        return result
    if not domain.is_dir():
        result.update(status='MISSING', issues='Converted domain directory missing')
        return result
    missing = [p for p in REQUIRED if not (domain / p).is_file()]
    if missing:
        result.update(status='FAIL', issues='Missing converted files: ' + ', '.join(missing))
        return result
    ref = Path(config['paths']['reference_basin'])
    pol = config['reference_policy']
    require(config['selection']['model_type'] == 'lumped', 'Configuration is not lumped')
    require(pol['mode'] == 'century_exact', 'Unsupported reference policy for this validator')
    srcattr = source / 'lumped/settings/SUMMA/attributes.nc'
    srccold = source / 'lumped/settings/SUMMA/coldState.nc'
    srctop = source / 'settings/mizuRoute/topology.nc'
    srclist = source / 'lumped/settings/SUMMA/forcingFileList_LST.txt'
    refattr = ref / 'summa_inputs/attributes.nc'
    refcold = ref / 'summa_state/coldState.nc'
    refprior = ref / 'summa_inputs/trialParams.priori.nc'
    compare_copied(srctop, domain / 'mizuroute_inputs/topology.nc', 'topology', issues, hash_copies)
    compare_copied(srclist, domain / 'summa_inputs/forcingFileList.txt', 'forcing list', issues, hash_copies)
    compare_copied(ref / 'mizuroute_inputs/mizuroute.param', domain / 'mizuroute_inputs/mizuroute.param',
                   'routing parameters', issues, True)

    try:
        with Dataset(srcattr) as original, Dataset(refattr) as reference, \
             Dataset(domain / 'summa_inputs/attributes.nc') as attrs:
            ids = integer_ids(attrs, 'hruId')
            require(ids.size == 1 and ids[0] > 0, 'expected one positive SUMMA HRU')
            require(np.array_equal(ids, integer_ids(original, 'hruId')), 'source attributes HRU mismatch')
            require(set(attrs.variables) == set(original.variables), 'attributes variable set differs from source')
            require(identical_values(values(attrs.variables['contourLength']),
                                     values(reference.variables['contourLength'])),
                    'contourLength differs from reference')
            for name in original.variables:
                if name != 'contourLength':
                    require(identical_values(values(original.variables[name]), values(attrs.variables[name])),
                            f'attributes changed unexpectedly: {name}')
        with Dataset(refprior) as template:
            require(set(template.variables) == {'hru', 'hruId'}, 'reference trialParams has extra variables')
            for name in ('trialParams.nc', 'trialParams.priori.nc'):
                with Dataset(domain / 'summa_inputs' / name) as trial:
                    require(set(trial.variables) == {'hru', 'hruId'}, f'{name} has extra variables')
                    require(len(trial.dimensions['hru']) == 1, f'{name} not lumped')
                    require(np.array_equal(integer_ids(trial, 'hruId'), ids), f'{name} HRU mismatch')
                    require(np.array_equal(integer_ids(trial, 'hru'), ids), f'{name} hru mismatch')
                    require(all(trial.variables[v].dtype == template.variables[v].dtype for v in ('hru', 'hruId')),
                            f'{name} dtype mismatch')
        with Dataset(refcold) as reference, Dataset(srccold) as srcstate, \
             Dataset(domain / 'summa_state/coldState.nc') as cold:
            require(np.array_equal(integer_ids(srcstate, 'hruId'), ids), 'source cold-state HRU mismatch')
            require(set(cold.variables) == set(reference.variables), 'cold-state variable set differs from reference')
            require({d:len(v) for d,v in cold.dimensions.items()} ==
                    {d:len(v) for d,v in reference.dimensions.items()}, 'cold-state dimensions differ')
            for name, v in reference.variables.items():
                out = cold.variables[name]
                require(v.dtype == out.dtype and v.dimensions == out.dimensions,
                        f'cold-state schema mismatch: {name}')
                if name in ('hru', 'hruId'):
                    require(np.array_equal(integer_ids(cold, name), ids), f'cold-state {name} mismatch')
                else:
                    require(identical_values(values(v), values(out)), f'cold-state differs from reference: {name}')
            nsoil = np.asarray(values(cold.variables['nSoil'])).reshape(-1)
            depths = np.asarray(values(cold.variables['mLayerDepth']), dtype=float).reshape(-1)
            require(nsoil.size == 1 and int(nsoil[0]) == int(pol['soil_layers']), 'nSoil mismatch')
            require(np.allclose(depths, pol['soil_layer_depths_m'], rtol=0, atol=1e-8),
                    'mLayerDepth differs from configured depths')
            require(math.isclose(float(np.sum(depths)), 1.0, abs_tol=1e-8), 'total soil depth is not 1m')
        with Dataset(domain / 'mizuroute_inputs/topology.nc') as topo, \
             Dataset(domain / 'mizuroute_inputs/lumped_to_hru.nc') as mapping:
            routing = integer_ids(topo, 'hruId')
            segments = integer_ids(topo, 'segId')
            down = integer_ids(topo, 'downSegId')
            hru_to_seg = integer_ids(topo, 'hruToSegId')
            require(len(set(routing.tolist())) == routing.size, 'routing HRU IDs duplicated')
            require(len(set(segments.tolist())) == segments.size, 'routing segment IDs duplicated')
            require(set(down.tolist()) <= set(segments.tolist()) | {0}, 'invalid downstream segment IDs')
            require(set(hru_to_seg.tolist()) <= set(segments.tolist()), 'routing HRU points to absent segment')
            polyid = integer_ids(mapping, 'polyid')
            qhru = integer_ids(mapping, 'qhru_id')
            n = integer_ids(mapping, 'nOverlaps')
            weights = np.asarray(values(mapping.variables['weight']), dtype=float).reshape(-1)
            require(routing.size == polyid.size == qhru.size == n.size == weights.size,
                    'mapping variable lengths disagree')
            require(np.array_equal(routing, polyid), 'mapping polyid differs from topology HRU order')
            require(np.all(qhru == ids[0]), 'mapping qhru_id mismatch')
            require(np.all(n == 1) and np.all(weights == 1), 'mapping weights/overlap counts incorrect')
            result['routing_hrus'] = routing.size
        names = forcing_names(domain / 'summa_inputs/forcingFileList.txt')
        original_names = forcing_names(srclist)
        require(names == original_names, 'forcing list names differ from source')
        result['forcing_files'] = len(names)
        first_last = []
        for name in names:
            out = domain / 'summa_forcing' / name
            src = source / 'lumped/forcing/6_SUMMA_input_LST' / name
            require(out.is_file(), f'missing forcing: {name}')
            compare_copied(src, out, f'forcing {name}', issues, hash_copies)
            try:
                nt, t0, t1, units = inspect_forcing(out, ids, issues)
                result['forcing_time_steps'] += nt
                first_last.append((t0, t1, units))
            except Exception as exc:
                issues.append(f'forcing {name}: {type(exc).__name__}: {exc}')
        if first_last:
            result['forcing_start'] = f'{first_last[0][0]:g} [{first_last[0][2]}]'
            result['forcing_end'] = f'{first_last[-1][1]:g} [{first_last[-1][2]}]'
            if len({x[2] for x in first_last}) == 1:
                for earlier, later in zip(first_last, first_last[1:]):
                    if later[0] <= earlier[1]:
                        issues.append('forcing time files overlap or are out of order')
            else:
                warnings.append('forcing files have differing time units; across-file ordering not checked')
        if config['processing'].get('copy_observations', True):
            for subset, key in (('obs-daily', 'daily_observations'), ('obs-hourly', 'hourly_observations')):
                originals = sorted((source / 'observations' / subset).glob('*.nc'))
                result[key] = len(originals)
                for original in originals:
                    target = dest / 'observations' / subset / original.name
                    compare_copied(original, target, f'observation {subset}/{original.name}', issues, hash_copies)
        marker_path = domain / '.conversion_complete.json'
        require(marker_path.is_file(), 'missing completion marker')
        marker = json.loads(marker_path.read_text())
        require(marker.get('basin') == basin and marker.get('group') == row['group'], 'completion marker basin/group mismatch')
        require(marker.get('validation') == 'PASS', 'completion marker validation not PASS')
        require(marker.get('reference_policy') == pol['mode'], 'completion marker policy mismatch')
        require(int(marker.get('hru_id', -1)) == int(ids[0]), 'completion marker HRU mismatch')
        require(int(marker.get('forcing_files', -1)) == len(names), 'completion marker forcing count mismatch')
    except Exception as exc:
        issues.append(f'{type(exc).__name__}: {exc}')

    if examples is not None:
        example = examples / basin
        if example.is_dir():
            history_status = 'MATCH'
            for relative in COMPARE_FILES:
                old, new = example / relative, domain / relative
                if old.is_file() and new.is_file():
                    try:
                        for problem in compare_netcdf(old, new):
                            history_diffs.append(f'{relative}: {problem}')
                    except Exception as exc:
                        history_diffs.append(f'{relative}: unreadable ({exc})')
                elif not old.is_file():
                    warnings.append(f'Example lacks {relative}; comparison skipped')
                else:
                    history_diffs.append(f'{relative}: new file missing')
            for relative in ('mizuroute_inputs/mizuroute.param', 'summa_inputs/forcingFileList.txt'):
                old, new = example / relative, domain / relative
                if old.is_file() and new.is_file() and old.read_bytes() != new.read_bytes():
                    history_diffs.append(f'{relative}: content differs')
            history_status = 'DIFFERENT' if history_diffs else 'MATCH'
        else:
            warnings.append('Historical example not available')
    result.update(status='FAIL' if issues else 'PASS', issues='; '.join(issues),
                  warnings='; '.join(warnings), historical_comparison=history_status,
                  historical_differences='; '.join(history_diffs))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=HERE / 'config/camels_spat_arc.toml')
    parser.add_argument('--inventory', type=Path, default=HERE / 'reports/camels_spat_lumped_inventory.csv')
    parser.add_argument('--destination', type=Path, help='Root containing domain/ and observations/')
    parser.add_argument('--examples', type=Path, default=None,
                        help='Directory containing saved examples by basin ID, e.g. CODE root')
    parser.add_argument('--basin', action='append', help='Select basin; repeat flag to select several')
    parser.add_argument('--all', action='store_true', help='Validate every inventory row')
    parser.add_argument('--hash-copies', action='store_true', help='SHA256-check forcing/observation copies (slower)')
    parser.add_argument('--output', type=Path, default=HERE / 'reports/camels_spat_conversion_validation.csv')
    args = parser.parse_args()
    if bool(args.all) == bool(args.basin):
        parser.error('Choose --all or one/more --basin arguments')
    with args.config.open('rb') as f:
        config = tomllib.load(f)
    with args.inventory.open(newline='') as f:
        rows = list(csv.DictReader(f))
    if args.basin:
        selected = set(args.basin)
        found = [r for r in rows if r['basin'] in selected]
        require(len(found) == len(selected), 'Some selected basins not found or duplicated in inventory')
        rows = found
    dest = args.destination or Path(config['paths']['output_root'])
    results = [inspect_one(row, dest, config, args.examples, args.hash_copies) for row in rows]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)
    print('========== STEP 04 INDEPENDENT VALIDATION ==========')
    print('Destination:', dest)
    for status, count in sorted(Counter(r['status'] for r in results).items()):
        print(f'{status}: {count}')
    for status, count in sorted(Counter(r['historical_comparison'] for r in results).items()):
        print(f'Historical {status}: {count}')
    for r in results:
        print(f"{r['basin']}: {r['status']} | historical={r['historical_comparison']}"
              + (f" | {r['issues']}" if r['issues'] else ''))
    print('CSV report:', args.output)
    if any(r['status'] != 'PASS' or r['historical_comparison'] == 'DIFFERENT' for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
