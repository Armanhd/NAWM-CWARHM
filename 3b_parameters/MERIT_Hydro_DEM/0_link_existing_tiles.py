from pathlib import Path
import math
import os
import subprocess
import re

# ============================================================
# PROJECT SETTINGS
# ============================================================

script_dir = Path(__file__).resolve().parent
cwarhm_root = script_dir.parent.parent

control_file = cwarhm_root / "0_control_files" / "control_active.txt"

merit_archive = Path(
    "/work/comphyd_lab/data/geospatial-data/MERIT-Hydro/elv"
)

# ============================================================
# READ CONTROL FILE
# ============================================================

def read_from_control(file, setting):
    with open(file) as contents:
        for line in contents:
            if setting in line and not line.startswith("#"):
                value = line.split("|", 1)[1]
                value = value.split("#", 1)[0]
                return value.strip()

    raise ValueError(f"Setting not found: {setting}")


root_path = Path(read_from_control(control_file, "root_path"))
domain_name = read_from_control(control_file, "domain_name")

catchment_path = read_from_control(control_file, "catchment_shp_path")
catchment_name = read_from_control(control_file, "catchment_shp_name")

# ============================================================
# RESOLVE SHAPEFILE PATH
# ============================================================

if catchment_path == "default":
    catchment_path = (
        root_path
        / f"domain_{domain_name}"
        / "shapefiles"
        / "catchment"
    )
else:
    catchment_path = Path(catchment_path)

catchment_file = catchment_path / catchment_name

if not catchment_file.exists():
    raise FileNotFoundError(f"Catchment shapefile not found: {catchment_file}")

print(f"\nCatchment shapefile:\n{catchment_file}")

# ============================================================
# GET EXTENT USING ogrinfo
# ============================================================

cmd = [
    "ogrinfo",
    "-so",
    "-al",
    str(catchment_file)
]

result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    check=True
)

match = re.search(
    r"Extent:\s*\(([-0-9.]+),\s*([-0-9.]+)\)\s*-\s*\(([-0-9.]+),\s*([-0-9.]+)\)",
    result.stdout
)

if not match:
    raise RuntimeError("Could not parse shapefile extent from ogrinfo output.")

min_lon = float(match.group(1))
min_lat = float(match.group(2))
max_lon = float(match.group(3))
max_lat = float(match.group(4))

print("\nDomain extent:")
print(f"Longitude: {min_lon:.6f} to {max_lon:.6f}")
print(f"Latitude : {min_lat:.6f} to {max_lat:.6f}")

# ============================================================
# MERIT-HYDRO TILE NAMING
# ============================================================

def floor_to_30(value):
    return math.floor(value / 30.0) * 30

def format_lat(lat):
    if lat >= 0:
        return f"n{abs(lat):02d}"
    return f"s{abs(lat):02d}"

def format_lon(lon):
    if lon >= 0:
        return f"e{abs(lon):03d}"
    return f"w{abs(lon):03d}"

lat_starts = range(
    floor_to_30(min_lat),
    floor_to_30(max_lat) + 1,
    30
)

lon_starts = range(
    floor_to_30(min_lon),
    floor_to_30(max_lon) + 1,
    30
)

required_tiles = []

for lat in lat_starts:
    for lon in lon_starts:
        filename = f"elv_{format_lat(lat)}{format_lon(lon)}.tar"
        required_tiles.append(filename)

# ============================================================
# TARGET DIRECTORY
# ============================================================

target_dir = (
    root_path
    / f"domain_{domain_name}"
    / "parameters"
    / "dem"
    / "1_MERIT_hydro_raw_data"
)

target_dir.mkdir(parents=True, exist_ok=True)

# ============================================================
# LINK REQUIRED TILES
# ============================================================

print("\nRequired MERIT-Hydro tiles:")

missing = []

for filename in required_tiles:

    source = merit_archive / filename
    target = target_dir / filename

    print(f"  {filename}")

    if not source.exists():
        print("    MISSING")
        missing.append(filename)
        continue

    if target.exists() or target.is_symlink():
        print("    already exists")
        continue

    os.symlink(source, target)
    print("    linked")

# ============================================================
# SUMMARY
# ============================================================

print("\nTarget directory:")
print(target_dir)

if missing:
    print("\nMissing tiles:")
    for filename in missing:
        print(f"  {filename}")
else:
    print("\nAll required MERIT-Hydro tiles were found and linked.")
