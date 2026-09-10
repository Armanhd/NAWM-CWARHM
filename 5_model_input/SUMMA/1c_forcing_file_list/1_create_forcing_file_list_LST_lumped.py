#!/usr/bin/env python3

import sys
from pathlib import Path
from netCDF4 import Dataset


if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: python 1_create_forcing_file_list_LST_lumped.py "
        "/path/to/control_DOMAIN_lumped.txt"
    )

CONTROL_FILE = Path(sys.argv[1]).resolve()


def read_control(key):

    with open(CONTROL_FILE) as f:
        for line in f:

            if "|" not in line or line.lstrip().startswith("#"):
                continue

            left, right = line.split("|", 1)

            if left.strip() == key:
                return right.split("#", 1)[0].strip()

    raise ValueError(f"Missing control setting: {key}")


domain = read_control("domain_name")
root_path = Path(read_control("root_path"))

domain_root = root_path / f"domain_{domain}" / "lumped"

forcing_dir = (
    domain_root
    / "forcing"
    / "6_SUMMA_input_LST"
)

settings_dir = (
    domain_root
    / "settings"
    / "SUMMA"
)

settings_dir.mkdir(
    parents=True,
    exist_ok=True
)

files = sorted(
    forcing_dir.glob(
        "NWAM_SUMMA_forcing_*_LST.nc"
    )
)

if len(files) != 1:
    raise RuntimeError(
        f"Expected exactly one concatenated LST forcing file.\n"
        f"Found: {len(files)}\n"
        f"Directory: {forcing_dir}"
    )

forcing_file = files[0]


with Dataset(forcing_file) as ds:

    if "hru" not in ds.dimensions:
        raise RuntimeError("Missing hru dimension.")

    if len(ds.dimensions["hru"]) != 1:
        raise RuntimeError(
            "Lumped forcing must contain exactly one HRU."
        )

    if "hruId" not in ds.variables:
        raise RuntimeError("Missing hruId.")

    hru_id = int(
        ds.variables["hruId"][:].reshape(-1)[0]
    )

    if hru_id != 1:
        raise RuntimeError(
            f"Expected hruId=1; found {hru_id}"
        )


output = (
    settings_dir
    / "forcingFileList_LST.txt"
)

output.write_text(
    forcing_file.name + "\n"
)


print()
print("=" * 70)
print("LUMPED LST FORCING FILE LIST")
print("=" * 70)
print(f"Domain       : {domain}")
print(f"Forcing file : {forcing_file}")
print("HRUs         : 1")
print("hruId        : 1")
print(f"Output       : {output}")
print("=" * 70)
print("PASS: LUMPED LST FORCING FILE LIST")