#!/usr/bin/env python3
"""Read-only audit for Step 11 source settings and extractor CLI compatibility."""
import argparse
from pathlib import Path
import subprocess
import sys
from module_registry import MODULES, PELLETIER_LAYERS
from process_basin_attributes import read_control, HERE, PARAMETERS

def main():
    p = argparse.ArgumentParser()
    p.add_argument('control', type=Path)
    args = p.parse_args()
    cfg = read_control(args.control)
    bad = 0
    print('Domain:', cfg.get('domain_name'))
    for name, script in MODULES:
        source = cfg.get(f'attribute_{name}_source', 'default')
        folder = cfg.get(f'attribute_{name}_raw_dir', '')
        print(f'{name:15} SOURCE={source} DIR={folder}')
        if source != 'default' and not Path(source).exists():
            print('  MISSING EXPLICIT SOURCE'); bad += 1
        if script:
            output = subprocess.run([sys.executable, str(PARAMETERS/script), '--help'], capture_output=True, text=True)
            if output.returncode:
                print('  ERROR: --help failed'); bad += 1
            elif name == 'hydrolakes' and '--archive' not in output.stdout:
                print('  ERROR: HydroLAKES lacks --archive'); bad += 1
            elif name not in ('terrain', 'pelletier', 'hydrolakes') and '--source' not in output.stdout:
                print('  ERROR: extractor lacks --source'); bad += 1
    folder = Path(cfg.get('attribute_pelletier_raw_dir', '/missing'))
    for field, filename in PELLETIER_LAYERS.items():
        target = Path(cfg.get('attribute_pelletier_layer_'+field, str(folder/filename)))
        if not target.is_file():
            print('MISSING PELLETIER LAYER', field, target); bad += 1
    print('Preflight issues:', bad)
    return 1 if bad else 0

if __name__ == '__main__': raise SystemExit(main())
