#!/usr/bin/env python3
"""
CWARHM forest-height attributes, compatible with CAMELS-SPAT.

Original attributes:
  forest_height_2000_min/mean/max/std
  forest_height_2020_min/mean/max/std

Uses rasterstats.zonal_stats(all_touched=True).
Runs distributed and lumped configurations independently or together.

Source rasters and SUMMA files remain unchanged.
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

YEARS = (2000, 2020)
NODATA = -9999.0
STATS = ("min", "mean", "max", "std")


def control_value(path, key):
    for line in path.read_text().splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "|" not in line:
            continue

        left, right = line.split("|", 1)

        if left.strip() == key:
            return right.split("#", 1)[0].strip()

    raise KeyError(f"Missing control setting: {key}")


def load_hrus(shapefile, summa_file):
    if not shapefile.is_file():
        raise FileNotFoundError(shapefile)

    if not summa_file.is_file():
        raise FileNotFoundError(summa_file)

    gdf = gpd.read_file(shapefile)

    if gdf.empty or gdf.crs is None:
        raise RuntimeError(f"Invalid geometry: {shapefile}")

    for col in ("HRU_ID", "GRU_ID", "HRU_area"):
        if col not in gdf:
            raise RuntimeError(f"Missing {col}: {shapefile}")

    for col in ("HRU_ID", "GRU_ID"):
        values = pd.to_numeric(
            gdf[col], errors="raise"
        ).to_numpy(dtype=float)

        if (
            not np.isfinite(values).all()
            or not np.equal(values, np.rint(values)).all()
        ):
            raise RuntimeError(f"Invalid {col}")

        gdf[col] = values.astype(np.int64)

    if gdf["HRU_ID"].duplicated().any():
        raise RuntimeError("Duplicate HRU IDs")

    with xr.open_dataset(summa_file) as ds:
        hru_ids = np.asarray(
            ds["hruId"].values, dtype=np.int64
        )
        gru_ids = np.asarray(
            ds["hru2gruId"].values, dtype=np.int64
        )

    if (
        len(hru_ids) != len(gdf)
        or set(hru_ids) != set(gdf["HRU_ID"])
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

    return gdf


def save_raster(path, array, profile):
    path.parent.mkdir(parents=True, exist_ok=True)

    profile = profile.copy()
    profile.pop("blockxsize", None)
    profile.pop("blockysize", None)

    profile.update(
        driver="GTiff",
        count=1,
        width=array.shape[1],
        height=array.shape[0],
        dtype="float32",
        nodata=NODATA,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )

    fd, temp = tempfile.mkstemp(
        prefix=path.stem + "_",
        suffix=".tmp.tif",
        dir=path.parent,
    )
    os.close(fd)

    try:
        with rasterio.open(temp, "w", **profile) as dst:
            dst.write(array.astype(np.float32), 1)

        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def clip_raster(source, destination, basin, force=False):
    if destination.exists() and not force:
        with rasterio.open(destination) as ds:
            if ds.count != 1 or ds.crs is None:
                raise RuntimeError(
                    f"Invalid existing output: {destination}"
                )
        return "reused"

    with rasterio.open(source) as src:
        if src.count != 1 or src.crs is None:
            raise RuntimeError(f"Invalid source raster: {source}")

        print(
            f"{source.name}: CRS={src.crs}, "
            f"nodata={src.nodata}, "
            f"scale={src.scales[0]}, "
            f"offset={src.offsets[0]}",
            flush=True,
        )

        polygon = basin.to_crs(src.crs).geometry.union_all()

        clipped, transform = mask(
            src,
            [polygon.__geo_interface__],
            crop=True,
            all_touched=True,
            filled=False,
        )

        values = clipped[0]

        valid = (
            ~np.ma.getmaskarray(values)
            & np.isfinite(values.data)
        )

        if not valid.any():
            raise RuntimeError(f"No valid pixels: {source}")

        # Preserve CAMELS-SPAT treatment of GDAL scale/offset.
        scale = src.scales[0]
        offset = src.offsets[0]

        scale = 1.0 if scale is None else scale
        offset = 0.0 if offset is None else offset

        output = np.full(
            values.shape,
            NODATA,
            dtype=np.float32,
        )

        output[valid] = (
            values.data[valid] * scale + offset
        )

        profile = src.profile.copy()
        profile.update(transform=transform)

    save_raster(destination, output, profile)

    return "created"


def calculate_stats(gdf, raster, year, rows):
    with rasterio.open(raster) as src:
        polygons = gdf.to_crs(src.crs)

    result = zonal_stats(
        polygons.geometry,
        str(raster),
        stats=["count", *STATS],
        all_touched=True,
    )

    covered = 0

    for row, item in zip(rows, result):
        name = f"forest_height_{year}"
        count = int(item.get("count") or 0)

        row[f"{name}_valid_pixels"] = count

        for stat in STATS:
            value = item.get(stat)
            row[f"{name}_{stat}"] = (
                float(value) if value is not None else np.nan
            )

        if count:
            covered += 1

    return covered


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp = tempfile.mkstemp(
        prefix=path.stem + "_",
        suffix=".tmp.csv",
        dir=path.parent,
    )
    os.close(fd)

    try:
        with open(temp, "w", newline="") as file:
            writer = csv.DictWriter(
                file, fieldnames=rows[0].keys()
            )
            writer.writeheader()
            writer.writerows(rows)

        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("control_file", type=Path)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Directory containing forest_height_2000.tif and forest_height_2020.tif",
    )

    parser.add_argument(
        "--mode",
        choices=("both", "distributed", "lumped"),
        default="both",
    )
    parser.add_argument("--force", action="store_true")

    args = parser.parse_args()

    control = args.control_file.resolve(strict=True)
    domain = control_value(control, "domain_name")

    root = (
        Path(control_value(control, "root_path"))
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
                / control_value(control, "catchment_shp_name")
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

    # Use the union of all selected HRUs for shared clips.
    basin = gpd.GeoDataFrame(
        geometry=[
            gpd.GeoSeries(
                [
                    gdf.to_crs("EPSG:4326").geometry.union_all()
                    for gdf in configurations.values()
                ],
                crs="EPSG:4326",
            ).union_all()
        ],
        crs="EPSG:4326",
    )

    rows = {}

    for mode, gdf in configurations.items():
        rows[mode] = [
            {
                "hruId": int(feature["HRU_ID"]),
                "gruId": int(feature["GRU_ID"]),
                "HRUarea_m2": float(feature["HRU_area"]),
            }
            for _, feature in gdf.iterrows()
        ]

    report = []

    print(f"Domain: {domain}")
    print(f"Mode: {args.mode}", flush=True)

    for year in YEARS:
        source = args.source / f"forest_height_{year}.tif"
        destination = (
            root / "parameters/forest_height"
            / f"forest_height_{year}.tif"
        )

        if not source.is_file():
            raise FileNotFoundError(source)

        status = clip_raster(
            source, destination, basin, args.force
        )

        record = {"year": year, "status": status}

        for mode, gdf in configurations.items():
            covered = calculate_stats(
                gdf, destination, year, rows[mode]
            )
            record[f"{mode}_valid_hrus"] = covered
            record[f"{mode}_total_hrus"] = len(gdf)

        report.append(record)

        print(
            f"forest_height_{year}: {status}",
            flush=True,
        )

    for mode, values in rows.items():
        if mode == "distributed":
            output = (
                root / "attributes/forest_height"
                / "hru_forest_height_attributes.csv"
            )
        else:
            output = (
                root / "lumped/attributes/forest_height"
                / "lumped_forest_height_attributes.csv"
            )

        write_csv(output, values)
        print(f"{mode}: {len(values)} HRUs; saved {output}")

    report_path = (
        root / "attributes/forest_height"
        / f"forest_height_processing_report_{args.mode}.csv"
    )
    write_csv(report_path, report)

    print(f"Report: {report_path}")
    print("Forest-height processing completed.")
    print("Original sources and SUMMA files unchanged.")


if __name__ == "__main__":
    main()
