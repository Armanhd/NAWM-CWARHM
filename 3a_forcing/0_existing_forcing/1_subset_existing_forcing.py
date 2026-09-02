#!/usr/bin/env python3

from pathlib import Path
import pandas as pd
import xarray as xr


# =========================================================
# CONFIG
# =========================================================

EMEARTH_BASE = Path(
    "/work/comphyd_lab/data/meteorological-data/EM_Earth_v1/deterministic_hourly"
)

ERA5_BASE = Path(
    "/work/comphyd_lab/data/meteorological-data/era5"
)

# Change this to your CWARHM/NWAM domain folder
DOMAIN_DIR = Path(
    "/work/comphyd_lab/users/arman.haddadchi/YOUR_CWARHM_PATH/domain_Example"
)

OUTPUT_BASE = DOMAIN_DIR / "forcing" / "1_raw_data"

# Temporary explicit settings.
# Later we can replace these with values read directly from the CWARHM control file.
START = "1950-01-01"
END = "2019-12-31"

# Set these to the model-domain bounding box.
# Example only — replace with your actual forcing_raw_space limits.
LAT_MIN = 40.0
LAT_MAX = 85.0
LON_MIN = -180.0
LON_MAX = -50.0


# =========================================================
# OUTPUT DIRECTORIES
# =========================================================

OUT_PRCP = OUTPUT_BASE / "EM_Earth" / "prcp"
OUT_TMEAN = OUTPUT_BASE / "EM_Earth" / "tmean"
OUT_ERA5 = OUTPUT_BASE / "ERA5"

for folder in [OUT_PRCP, OUT_TMEAN, OUT_ERA5]:
    folder.mkdir(parents=True, exist_ok=True)


# =========================================================
# HELPER
# =========================================================

def subset_lat_lon(ds, lat_min, lat_max, lon_min, lon_max):

    # Latitude may be ascending or descending
    if ds["lat"][0] > ds["lat"][-1]:
        lat_slice = slice(lat_max, lat_min)
    else:
        lat_slice = slice(lat_min, lat_max)

    # Longitude may also be ascending or descending
    if ds["lon"][0] > ds["lon"][-1]:
        lon_slice = slice(lon_max, lon_min)
    else:
        lon_slice = slice(lon_min, lon_max)

    return ds.sel(
        lat=lat_slice,
        lon=lon_slice
    )


def process_file(input_file, output_file, variables=None):

    print(f"Reading: {input_file}")

    with xr.open_dataset(input_file, engine="netcdf4") as ds:

        ds_sub = subset_lat_lon(
            ds,
            LAT_MIN,
            LAT_MAX,
            LON_MIN,
            LON_MAX
        )

        if variables is not None:
            ds_sub = ds_sub[variables]

        print("Subset dimensions:", dict(ds_sub.sizes))

        ds_sub.to_netcdf(
            output_file,
            engine="netcdf4"
        )

    print(f"Saved: {output_file}")


# =========================================================
# MONTHLY LOOP
# =========================================================

months = pd.period_range(
    START,
    END,
    freq="M"
)

for period in months:

    yyyymm = period.strftime("%Y%m")

    print("\n====================================================")
    print(f"Processing {yyyymm}")
    print("====================================================")

    # -----------------------------------------------------
    # EM-Earth precipitation
    # -----------------------------------------------------

    prcp_file = (
        EMEARTH_BASE
        / "prcp"
        / "NorthAmerica"
        / f"EM_Earth_deterministic_hourly_NorthAmerica_{yyyymm}.nc"
    )

    if not prcp_file.exists():
        raise FileNotFoundError(f"Missing precipitation file: {prcp_file}")

    process_file(
        prcp_file,
        OUT_PRCP / prcp_file.name,
        variables=["prcp", "prcp_corrected"]
    )

    # -----------------------------------------------------
    # EM-Earth temperature
    # -----------------------------------------------------

    tmean_file = (
        EMEARTH_BASE
        / "tmean"
        / "NorthAmerica"
        / f"EM_Earth_deterministic_hourly_NorthAmerica_{yyyymm}.nc"
    )

    if not tmean_file.exists():
        raise FileNotFoundError(f"Missing temperature file: {tmean_file}")

    process_file(
        tmean_file,
        OUT_TMEAN / tmean_file.name,
        variables=["tmean"]
    )

    # -----------------------------------------------------
    # ERA5
    # -----------------------------------------------------

    era5_file = (
        ERA5_BASE
        / f"ERA5_merged_{yyyymm}.nc"
    )

    if not era5_file.exists():
        raise FileNotFoundError(f"Missing ERA5 file: {era5_file}")

    process_file(
        era5_file,
        OUT_ERA5 / era5_file.name,
        variables=None
    )


print("\nFinished subsetting all forcing files.")