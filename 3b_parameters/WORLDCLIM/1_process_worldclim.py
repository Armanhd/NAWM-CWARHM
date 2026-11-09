#!/usr/bin/env python3
"""
NWAM-CWARHM: Compact WorldClim climate attributes.

Creates 10 long-term climate descriptors for each HRU:

    mean_annual_precipitation      mm/year
    mean_annual_temperature        deg C
    mean_annual_pet                mm/year
    annual_aridity_index           dimensionless
    annual_snow_fraction           dimensionless
    precipitation_seasonality      dimensionless
    temperature_annual_range       deg C
    climate_index_im               dimensionless
    climate_index_imr              dimensionless
    climate_index_fs               dimensionless

Sources:
    WorldClim monthly precipitation and temperature
    Derived monthly PET (mm/day)
    Derived monthly snowfall (mm/month)
    Knoben climate indices IM, IMR and FS

Definitions:
    Annual precipitation = sum of 12 monthly precipitation means.
    Annual temperature = day-weighted mean of monthly temperatures.
    Annual PET = sum of PET (mm/day) * days in month.
    Annual aridity = annual PET / annual precipitation.
    Annual snow fraction = annual snow / annual precipitation.
    Precipitation seasonality = monthly precipitation CV (population).
    Temperature range = max(monthly Tmean) - min(monthly Tmean).

Spatial aggregation:
    Raster zonal mean, all_touched=True.

Note:
    Annual descriptors are calculated from the spatially averaged
    monthly climatologies for each HRU. They are not the same as
    spatial means of pixel-wise annual ratios.

    The Knoben indices use the original supplied index rasters.

The script does not modify original rasters or SUMMA files.
"""

import argparse
import csv
import os
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr

from rasterio.mask import mask
from rasterstats import zonal_stats


SOURCE_ROOT = None

MONTHS = range(1, 13)

# Match the original CAMELS-SPAT February convention.
DAYS = np.array(
    [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31],
    dtype=float,
)

NODATA = -9999.0

MONTHLY_SOURCES = {
    "prec": "raw/prec",
    "tavg": "raw/tavg",
    "pet": "derived/pet",
    "snow": "derived/snow",
}

INDEX_SOURCES = {
    "climate_index_im":
        "derived/climate_indices/"
        "wc2.1_30s_climate_index_im.tif",

    "climate_index_imr":
        "derived/climate_indices/"
        "wc2.1_30s_climate_index_imr.tif",

    "climate_index_fs":
        "derived/climate_indices/"
        "wc2.1_30s_climate_index_fs.tif",
}


def read_control(path, key):
    with open(path) as file:
        for line in file:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "|" not in line:
                continue

            name, value = line.split("|", 1)

            if name.strip() == key:
                value = value.split("#", 1)[0].strip()

                if value:
                    return value

    raise KeyError(f"Missing control parameter: {key}")


def load_hrus(shapefile, summa_file):
    if not shapefile.is_file():
        raise FileNotFoundError(shapefile)

    if not summa_file.is_file():
        raise FileNotFoundError(summa_file)

    gdf = gpd.read_file(shapefile)

    if gdf.empty or gdf.crs is None:
        raise RuntimeError(f"Invalid HRU shapefile: {shapefile}")

    for column in ("HRU_ID", "GRU_ID", "HRU_area"):
        if column not in gdf.columns:
            raise RuntimeError(
                f"Missing field {column}: {shapefile}"
            )

    for column in ("HRU_ID", "GRU_ID"):
        values = pd.to_numeric(
            gdf[column], errors="raise"
        ).to_numpy(dtype=float)

        if (
            not np.isfinite(values).all()
            or not np.equal(values, np.rint(values)).all()
        ):
            raise RuntimeError(f"Invalid {column} values")

        gdf[column] = values.astype(np.int64)

    gdf["HRU_area"] = pd.to_numeric(
        gdf["HRU_area"], errors="raise"
    )

    if (
        not np.isfinite(gdf["HRU_area"]).all()
        or (gdf["HRU_area"] <= 0).any()
    ):
        raise RuntimeError("Invalid HRU areas")

    if gdf["HRU_ID"].duplicated().any():
        raise RuntimeError("Duplicate HRU IDs")

    # Repair invalid HRU geometries in memory only.
    # Original shapefiles are never modified.
    if not gdf.geometry.isna().any() and not gdf.geometry.is_empty.any():
        if not gdf.geometry.is_valid.all():
            repaired = gdf.geometry.make_valid()
            if not repaired.geom_type.isin(
                ["Polygon", "MultiPolygon"]
            ).all():
                raise RuntimeError(
                    "Geometry repair produced non-polygon features"
                )
            gdf = gdf.set_geometry(repaired)

    if (
        gdf.geometry.isna().any()
        or gdf.geometry.is_empty.any()
        or not gdf.geometry.is_valid.all()
    ):
        raise RuntimeError("Invalid HRU geometry")

    with xr.open_dataset(summa_file) as ds:
        hru_ids = np.asarray(
            ds["hruId"].values, dtype=np.int64
        ).ravel()

        gru_ids = np.asarray(
            ds["hru2gruId"].values, dtype=np.int64
        ).ravel()

    if (
        len(gdf) != len(hru_ids)
        or set(gdf["HRU_ID"]) != set(hru_ids)
    ):
        raise RuntimeError("HRU IDs do not match SUMMA")

    gdf = (
        gdf.set_index("HRU_ID", drop=False)
        .loc[hru_ids]
        .copy()
        .reset_index(drop=True)
    )

    if not np.array_equal(
        gdf["GRU_ID"].to_numpy(), gru_ids
    ):
        raise RuntimeError("GRU IDs do not match SUMMA")

    return gdf


def find_monthly_source(root, variable, month):
    folder = root / MONTHLY_SOURCES[variable]

    # All current source filenames end with _01.tif, etc.
    matches = sorted(folder.glob(f"*_{month:02d}.tif"))

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one file for {variable}, "
            f"month {month:02d}; found {len(matches)} "
            f"in {folder}"
        )

    return matches[0]


def read_basin_raster(source, basin):
    """
    Crop one source raster to the basin.

    Respect source NoData masks and apply scale/offset once.
    Other special values are not guessed: report source ranges
    so they can be audited before production processing.
    """
    with rasterio.open(source) as src:
        if src.count != 1 or src.crs is None:
            raise RuntimeError(f"Invalid raster: {source}")

        scale = src.scales[0]
        offset = src.offsets[0]

        if scale is None or offset is None:
            raise RuntimeError(
                f"Missing scale or offset: {source}"
            )

        geometry = basin.to_crs(src.crs).geometry.union_all()

        clipped, transform = mask(
            src,
            [geometry.__geo_interface__],
            crop=True,
            all_touched=True,
            filled=False,
        )

        band = clipped[0]
        data = band.data

        valid = (
            ~np.ma.getmaskarray(band)
            & np.isfinite(data)
        )

        output = np.full(
            data.shape,
            NODATA,
            dtype=np.float32,
        )

        output[valid] = (
            data[valid].astype(np.float64) * scale + offset
        )

        # Guard against failed scaling or numeric overflow.
        valid &= np.isfinite(output)
        output[~valid] = NODATA

        if not valid.any():
            raise RuntimeError(
                f"No valid pixels: {source}"
            )

        info = {
            "source": str(source),
            "source_nodata": src.nodata,
            "scale": float(scale),
            "offset": float(offset),
            "valid_source_pixels": int(valid.sum()),
            "source_min": float(output[valid].min()),
            "source_max": float(output[valid].max()),
        }

        return output, transform, src.crs, info


def zonal_means(source, basin, configurations):
    array, transform, crs, info = read_basin_raster(
        source, basin
    )

    values = {}
    counts = {}

    for mode, gdf in configurations.items():
        polygons = gdf.to_crs(crs)

        stats = zonal_stats(
            polygons.geometry,
            array,
            affine=transform,
            nodata=NODATA,
            stats=["mean", "count"],
            all_touched=True,
        )

        means = []
        valid_pixels = []

        for item in stats:
            count = int(item.get("count") or 0)
            mean = item.get("mean")

            means.append(
                float(mean)
                if mean is not None
                else np.nan
            )

            valid_pixels.append(count)

        values[mode] = np.asarray(means, dtype=float)
        counts[mode] = np.asarray(
            valid_pixels, dtype=int
        )

    return values, counts, info


def write_csv(destination, records):
    destination.parent.mkdir(
        parents=True, exist_ok=True
    )

    if not records:
        raise RuntimeError("No records to write")

    fd, temporary = tempfile.mkstemp(
        dir=destination.parent,
        prefix=destination.stem + "_",
        suffix=".tmp.csv",
    )
    os.close(fd)

    try:
        with open(temporary, "w", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=list(records[0].keys()),
            )
            writer.writeheader()
            writer.writerows(records)

        os.replace(temporary, destination)

    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def calculate_descriptors(monthly, indices):
    """
    monthly[var] has shape (12, number_of_hrus).
    indices[name] has shape (number_of_hrus,).
    """
    prec = monthly["prec"]
    temp = monthly["tavg"]
    pet_daily = monthly["pet"]
    snow = monthly["snow"]

    annual_prec = np.sum(prec, axis=0)
    annual_pet = np.sum(
        pet_daily * DAYS[:, None],
        axis=0,
    )
    annual_snow = np.sum(snow, axis=0)

    annual_temp = np.sum(
        temp * DAYS[:, None], axis=0
    ) / DAYS.sum()

    with np.errstate(
        divide="ignore", invalid="ignore"
    ):
        aridity = np.where(
            annual_prec > 0,
            annual_pet / annual_prec,
            np.nan,
        )

        snow_fraction = np.where(
            annual_prec > 0,
            annual_snow / annual_prec,
            np.nan,
        )

        monthly_mean_prec = np.mean(prec, axis=0)

        precipitation_cv = np.where(
            monthly_mean_prec > 0,
            np.std(prec, axis=0, ddof=0)
            / monthly_mean_prec,
            np.nan,
        )

    temperature_range = (
        np.max(temp, axis=0)
        - np.min(temp, axis=0)
    )

    return {
        "mean_annual_precipitation": annual_prec,
        "mean_annual_temperature": annual_temp,
        "mean_annual_pet": annual_pet,
        "annual_aridity_index": aridity,
        "annual_snow_fraction": snow_fraction,
        "precipitation_seasonality": precipitation_cv,
        "temperature_annual_range": temperature_range,
        "climate_index_im": indices["climate_index_im"],
        "climate_index_imr": indices["climate_index_imr"],
        "climate_index_fs": indices["climate_index_fs"],
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "control_file", type=Path
    )

    parser.add_argument(
        "--mode",
        choices=("both", "distributed", "lumped"),
        default="both",
    )

    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="WorldClim source directory",
    )

    args = parser.parse_args()

    control = args.control_file.resolve(strict=True)

    domain = read_control(
        control, "domain_name"
    )

    root = (
        Path(read_control(control, "root_path"))
        / f"domain_{domain}"
    )

    configurations = {}

    if args.mode in ("both", "distributed"):

        shapefile = (
            root / "shapefiles/catchment"
            / f"{domain}_distributed_basin.shp"
        )

        if not shapefile.is_file():
            shapefile = (
                root / "shapefiles/catchment"
                / read_control(control, "catchment_shp_name")
            )

        configurations["distributed"] = load_hrus(
            shapefile,
            root / "settings/SUMMA/attributes.nc",
        )

    if args.mode in ("both", "lumped"):
        configurations["lumped"] = load_hrus(
            root / "lumped/shapefiles/catchment"
            / f"{domain}_lumped_basin.shp",
            root / "lumped/settings/SUMMA/attributes.nc",
        )

    polygons = [
        gdf.to_crs("EPSG:4326").geometry.union_all()
        for gdf in configurations.values()
    ]

    basin = gpd.GeoDataFrame(
        geometry=[
            gpd.GeoSeries(
                polygons, crs="EPSG:4326"
            ).union_all()
        ],
        crs="EPSG:4326",
    )

    print("=" * 65)
    print("NWAM-CWARHM WorldClim climate attributes")
    print("=" * 65)
    print("Domain:", domain)
    print("Mode:", args.mode)
    print("Source:", args.source)
    print("Attributes: 10")
    print("Spatial aggregation: all_touched=True")
    print("=" * 65, flush=True)

    monthly = {
        mode: {
            variable: []
            for variable in MONTHLY_SOURCES
        }
        for mode in configurations
    }

    indices = {
        mode: {}
        for mode in configurations
    }

    coverage = {
        mode: []
        for mode in configurations
    }

    source_report = []

    # --------------------------------------------------------
    # Monthly climatology
    # --------------------------------------------------------

    for variable in MONTHLY_SOURCES:
        print(f"\nProcessing: {variable}", flush=True)

        for month in MONTHS:
            source = find_monthly_source(
                args.source, variable, month
            )

            means, counts, info = zonal_means(
                source, basin, configurations
            )

            info["variable"] = variable
            info["month"] = month
            source_report.append(info)

            for mode in configurations:
                monthly[mode][variable].append(
                    means[mode]
                )

                for i, count in enumerate(counts[mode]):
                    coverage[mode].append({
                        "hruId": int(
                            configurations[mode].iloc[i]["HRU_ID"]
                        ),
                        "variable": variable,
                        "month": month,
                        "valid_pixels": int(count),
                    })

            print(
                f"  Month {month:02d}: "
                f"min={info['source_min']:.4g}, "
                f"max={info['source_max']:.4g}",
                flush=True,
            )

    # --------------------------------------------------------
    # Knoben climate indices
    # --------------------------------------------------------

    print("\nProcessing climate indices...", flush=True)

    for name, relative in INDEX_SOURCES.items():
        source = args.source / relative

        if not source.is_file():
            raise FileNotFoundError(source)

        means, counts, info = zonal_means(
            source, basin, configurations
        )

        info["variable"] = name
        info["month"] = "annual"
        source_report.append(info)

        for mode in configurations:
            indices[mode][name] = means[mode]

            for i, count in enumerate(counts[mode]):
                coverage[mode].append({
                    "hruId": int(
                        configurations[mode].iloc[i]["HRU_ID"]
                    ),
                    "variable": name,
                    "month": "annual",
                    "valid_pixels": int(count),
                })

        print(
            f"  {name}: "
            f"min={info['source_min']:.4g}, "
            f"max={info['source_max']:.4g}",
            flush=True,
        )

    # --------------------------------------------------------
    # Generate the 10 attributes
    # --------------------------------------------------------

    for mode, gdf in configurations.items():
        stacks = {
            name: np.stack(arrays, axis=0)
            for name, arrays in monthly[mode].items()
        }

        descriptors = calculate_descriptors(
            stacks, indices[mode]
        )

        rows = []

        for i, hru in gdf.iterrows():
            row = {
                "hruId": int(hru["HRU_ID"]),
                "gruId": int(hru["GRU_ID"]),
                "HRUarea_m2": float(hru["HRU_area"]),
            }

            for name, values in descriptors.items():
                row[name] = float(values[i])

            rows.append(row)

        # Check for missing or invalid numerical results.
        failures = []

        for row in rows:
            invalid = [
                name for name in descriptors
                if not np.isfinite(row[name])
            ]

            if invalid:
                failures.append(
                    (row["hruId"], invalid)
                )

            if (
                np.isfinite(row["annual_snow_fraction"])
                and not (
                    -1e-6 <= row["annual_snow_fraction"]
                    <= 1 + 1e-6
                )
            ):
                failures.append(
                    (
                        row["hruId"],
                        ["annual_snow_fraction outside 0-1"],
                    )
                )

            if (
                row["mean_annual_precipitation"] < 0
                or row["mean_annual_pet"] < 0
            ):
                failures.append(
                    (row["hruId"], ["negative annual total"])
                )

        if failures:
            raise RuntimeError(
                f"WorldClim QA failed in {mode}: "
                f"{failures[:10]}"
            )

        if mode == "distributed":
            output_dir = root / "attributes/worldclim"
            attr_path = (
                output_dir / "hru_worldclim_attributes.csv"
            )
        else:
            output_dir = (
                root / "lumped/attributes/worldclim"
            )
            attr_path = (
                output_dir / "lumped_worldclim_attributes.csv"
            )

        write_csv(attr_path, rows)

        write_csv(
            output_dir / "worldclim_coverage_report.csv",
            coverage[mode],
        )

        print(
            f"\n{mode}: {len(rows)} HRUs processed",
            flush=True,
        )
        print("Attributes:", attr_path)

    # Shared source audit.
    report_path = (
        root / "attributes/worldclim"
        / "worldclim_source_report.csv"
    )

    write_csv(report_path, source_report)

    print("\nSource audit:", report_path)
    print("WorldClim processing completed.")
    print("Original source and SUMMA files unchanged.")


if __name__ == "__main__":
    main()
