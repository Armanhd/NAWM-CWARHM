#!/usr/bin/env python3
"""
CWARHM Pelletier attributes.

Usage:
  python 1_process_pelletier.py --list
  python 1_process_pelletier.py CONTROL \
      --layer soil_thickness=/absolute/path/to/source.tif \
      --layer regolith_thickness=/absolute/path/to/source.tif

Options:
  --mode both|distributed|lumped
  --force

Original raster sources, SUMMA files, and existing soil classes
are never modified. No assumption is made about source units.
"""

import argparse
import csv
import os
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import xarray as xr
from rasterio.mask import mask
from rasterstats import zonal_stats


DEFAULT_SOURCE = None

NODATA = -9999.0


def control_value(path, key):
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        left, right = line.split("|", 1)
        if left.strip() == key:
            value = right.split("#", 1)[0].strip()
            if value:
                return value
    raise KeyError(f"Missing control field: {key}")


def load_hru_geometry(shape_path, summa_path):
    if not shape_path.is_file():
        raise FileNotFoundError(shape_path)
    if not summa_path.is_file():
        raise FileNotFoundError(summa_path)

    gdf = gpd.read_file(shape_path)

    if gdf.empty or gdf.crs is None:
        raise RuntimeError(f"Invalid geometry: {shape_path}")

    required = ["HRU_ID", "GRU_ID", "HRU_area"]
    for col in required:
        if col not in gdf:
            raise RuntimeError(f"Missing {col}: {shape_path}")

    gdf["HRU_ID"] = gdf["HRU_ID"].astype(np.int64)
    gdf["GRU_ID"] = gdf["GRU_ID"].astype(np.int64)

    if gdf["HRU_ID"].duplicated().any():
        raise RuntimeError("Duplicate HRU_ID values")

    with xr.open_dataset(summa_path) as ds:
        hru_ids = np.asarray(ds["hruId"].values, dtype=np.int64)
        gru_ids = np.asarray(ds["hru2gruId"].values, dtype=np.int64)

    if len(hru_ids) != len(gdf) or set(hru_ids) != set(gdf.HRU_ID):
        raise RuntimeError("HRU IDs do not match SUMMA")

    gdf = (
        gdf.set_index("HRU_ID", drop=False)
        .loc[hru_ids]
        .reset_index(drop=True)
    )

    if not np.array_equal(gdf.GRU_ID.to_numpy(), gru_ids):
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


def atomic_raster_write(path, array, profile):
    path.parent.mkdir(parents=True, exist_ok=True)

    profile = profile.copy()
    profile.pop("blockxsize", None)
    profile.pop("blockysize", None)
    profile.update(
        driver="GTiff",
        count=1,
        height=array.shape[0],
        width=array.shape[1],
        dtype="float32",
        nodata=NODATA,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
    )

    fd, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=path.stem + "_", suffix=".tmp.tif"
    )
    os.close(fd)

    try:
        with rasterio.open(temporary, "w", **profile) as dst:
            dst.write(array.astype("float32"), 1)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def clip_raster(source, destination, geometry, force=False):
    if destination.exists() and not force:
        try:
            with rasterio.open(destination) as old:
                if old.count == 1 and old.crs and old.nodata is not None:
                    return "reused"
        except Exception:
            pass

    with rasterio.open(source) as src:
        if src.count != 1 or src.crs is None or src.nodata is None:
            raise RuntimeError(
                f"Source must be single-band with CRS and NoData: {source}"
            )

        projected = geometry.to_crs(src.crs)
        union = projected.geometry.union_all()

        try:
            clipped, transform = mask(
                src,
                [union.__geo_interface__],
                crop=True,
                all_touched=True,
                filled=False,
            )
        except ValueError:
            return "outside_extent"

        values = clipped[0]
        valid = (
            ~np.ma.getmaskarray(values)
            & np.isfinite(values.data)
        )

        if not np.any(valid):
            return "no_valid_pixels"

        output = np.full(values.shape, NODATA, dtype=np.float32)
        output[valid] = values.data[valid]

        profile = src.profile.copy()
        profile.update(transform=transform)

    atomic_raster_write(destination, output, profile)
    return "created"


def add_zonal_stats(rows, polygons, raster, name):
    columns = ["min", "mean", "max", "std", "valid_pixels"]

    for row in rows:
        for col in columns:
            row[f"{name}_{col}"] = 0.0 if col != "valid_pixels" else 0

    if not raster.exists():
        return 0

    with rasterio.open(raster) as src:
        polygons = polygons.to_crs(src.crs)

    statistics = zonal_stats(
        polygons.geometry,
        str(raster),
        stats=["count", "min", "mean", "max", "std"],
        all_touched=True,
    )

    valid_hrus = 0

    for row, result in zip(rows, statistics):
        count = int(result.get("count") or 0)
        row[f"{name}_valid_pixels"] = count

        if count:
            valid_hrus += 1
            for stat in ("min", "mean", "max", "std"):
                value = result.get(stat)
                row[f"{name}_{stat}"] = (
                    float(value) if value is not None else np.nan
                )

    return valid_hrus


def save_csv(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        return

    fd, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=path.stem + "_", suffix=".tmp.csv"
    )
    os.close(fd)

    try:
        with open(temporary, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parse_layers(items):
    result = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Expected NAME=/path/to/raster: {item}")

        name, path = item.split("=", 1)
        name = name.strip()
        path = Path(path.strip()).expanduser().resolve()

        if (
            not name
            or not all(c.isalnum() or c == "_" for c in name)
            or name in result
        ):
            raise ValueError(f"Invalid or duplicate layer name: {name}")

        if not path.is_file():
            raise FileNotFoundError(path)

        result[name] = path

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control", nargs="?", type=Path)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--layer", action="append", default=[])
    parser.add_argument(
        "--mode",
        choices=("both", "distributed", "lumped"),
        default="both",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.list:
        if args.source is None:
            parser.error("--list requires --source DIRECTORY")
        if not args.source.is_dir():
            raise FileNotFoundError(args.source)

        print(f"Source directory: {args.source}")

        for path in sorted(args.source.rglob("*")):
            if path.is_file() and path.suffix.lower() in (
                ".tif", ".tiff", ".vrt", ".nc"
            ):
                print(path)
        return

    if args.control is None:
        parser.error("A control file is required")

    if not args.layer:
        parser.error("Provide at least one --layer NAME=/path/to/raster")

    layers = parse_layers(args.layer)
    control = args.control.resolve(strict=True)

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

        configurations["distributed"] = load_hru_geometry(
            shapefile,
            root / "settings/SUMMA/attributes.nc",
        )


    if args.mode in ("both", "lumped"):
        configurations["lumped"] = load_hru_geometry(
            root / "lumped/shapefiles/catchment"
            / f"{domain}_lumped_basin.shp",
            root / "lumped/settings/SUMMA/attributes.nc",
        )

    # Clip against all selected HRUs, keeping a shared basin map.
    combined = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries(
            [
                gdf.to_crs("EPSG:4326").geometry.union_all()
                for gdf in configurations.values()
            ],
            crs="EPSG:4326",
        ),
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

    print(f"Domain: {domain}", flush=True)
    print(f"Mode: {args.mode}", flush=True)

    for name, source in layers.items():
        clipped = root / "parameters/pelletier" / f"{name}.tif"

        status = clip_raster(
            source, clipped, combined, force=args.force
        )

        if status == "outside_extent":
            raise RuntimeError(
                f"Pelletier raster does not cover basin: {source}"
            )

        record = {
            "layer": name,
            "source": str(source),
            "status": status,
        }

        for mode, gdf in configurations.items():
            valid = add_zonal_stats(
                rows[mode], gdf, clipped, name
            )
            record[f"{mode}_valid_hrus"] = valid
            record[f"{mode}_total_hrus"] = len(gdf)

        report.append(record)
        print(f"{name}: {status}", flush=True)

    for mode, values in rows.items():
        if mode == "distributed":
            output = (
                root / "attributes/pelletier"
                / "hru_pelletier_attributes.csv"
            )
        else:
            output = (
                root / "lumped/attributes/pelletier"
                / "lumped_pelletier_attributes.csv"
            )

        save_csv(output, values)
        print(f"{mode}: {len(values)} HRUs; saved {output}")

    report_file = (
        root / "attributes/pelletier"
        / f"pelletier_processing_report_{args.mode}.csv"
    )
    save_csv(report_file, report)

    print(f"Report: {report_file}")
    print("Existing SUMMA and soil-class files unchanged.")


if __name__ == "__main__":
    main()
