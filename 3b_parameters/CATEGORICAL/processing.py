#!/usr/bin/env python3
"""
Common categorical spatial-attribute processor for NWAM-CWARHM.

Reproduces the CAMELS-SPAT calculation:
    rasterstats.zonal_stats(
        polygons, raster, categorical=True, all_touched=True
    )

Class fraction = class pixel count / all valid classified pixels.

Original source rasters and SUMMA inputs remain unchanged.
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

DATASETS = {
    "glclu2019": {
        "source": None,
        "prefix": "lc1_",
        "classes": {
            1: "true_desert",
            2: "semi_arid",
            3: "dense_short_vegetation",
            4: "open_tree_cover",
            5: "dense_tree_cover",
            6: "tree_cover_gain",
            7: "tree_cover_loss",
            8: "salt_pan",
            9: "wetland_sparse_vegetation",
            10: "wetland_dense_short_vegetation",
            11: "wetland_open_tree_cover",
            12: "wetland_dense_tree_cover",
            13: "wetland_tree_cover_gain",
            14: "wetland_tree_cover_loss",
            15: "ice",
            16: "water",
            17: "cropland",
            18: "built_up",
            19: "ocean",
            20: "no_data",
        },
        "expected_nodata": 255,
    },
    "lgrip30": {
        "source": None,
        "prefix": "lc3_",
        "classes": {
            0: "water",
            1: "non_cropland",
            2: "irrigated_cropland",
            3: "rainfed_cropland",
        },
        "expected_nodata": None,
    },
}


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

    raise KeyError(f"Missing control setting: {key}")


def load_hrus(shapefile, summa_file):
    if not shapefile.is_file():
        raise FileNotFoundError(shapefile)

    if not summa_file.is_file():
        raise FileNotFoundError(summa_file)

    gdf = gpd.read_file(shapefile)

    if gdf.empty or gdf.crs is None:
        raise RuntimeError(f"Invalid HRU shapefile: {shapefile}")

    for col in ("HRU_ID", "GRU_ID", "HRU_area"):
        if col not in gdf.columns:
            raise RuntimeError(f"Missing {col}: {shapefile}")

    for col in ("HRU_ID", "GRU_ID"):
        values = pd.to_numeric(
            gdf[col], errors="raise"
        ).to_numpy(dtype=float)

        if (
            not np.isfinite(values).all()
            or not np.equal(values, np.rint(values)).all()
        ):
            raise RuntimeError(f"Invalid {col} values")

        gdf[col] = values.astype(np.int64)

    if gdf["HRU_ID"].duplicated().any():
        raise RuntimeError("Duplicate HRU IDs")

    if (
        not np.isfinite(gdf["HRU_area"]).all()
        or (gdf["HRU_area"] <= 0).any()
    ):
        raise RuntimeError("Invalid HRU areas")

    with xr.open_dataset(summa_file) as ds:
        hru_ids = np.asarray(
            ds["hruId"].values, dtype=np.int64
        )
        gru_ids = np.asarray(
            ds["hru2gruId"].values, dtype=np.int64
        )

    if len(hru_ids) != len(gdf) or set(hru_ids) != set(gdf.HRU_ID):
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
        raise RuntimeError("Invalid HRU geometries")

    return gdf


def atomic_raster_write(destination, array, profile):
    destination.parent.mkdir(parents=True, exist_ok=True)

    profile = profile.copy()
    profile.pop("blockxsize", None)
    profile.pop("blockysize", None)

    profile.update(
        driver="GTiff",
        count=1,
        dtype="int16",
        nodata=-9999,
        height=array.shape[0],
        width=array.shape[1],
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )

    fd, temp = tempfile.mkstemp(
        dir=destination.parent,
        prefix=destination.stem + "_",
        suffix=".tmp.tif",
    )
    os.close(fd)

    try:
        with rasterio.open(temp, "w", **profile) as dst:
            dst.write(array.astype(np.int16), 1)

        os.replace(temp, destination)

    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def clip_source(source, destination, basin, expected_nodata, force=False):
    if destination.exists() and not force:
        with rasterio.open(destination) as ds:
            if (
                ds.count != 1
                or ds.crs is None
                or ds.nodata != -9999
            ):
                raise RuntimeError(
                    f"Invalid existing raster: {destination}"
                )
        return "reused"

    with rasterio.open(source) as src:
        if src.count != 1 or src.crs is None:
            raise RuntimeError(f"Invalid source raster: {source}")

        if src.nodata != expected_nodata:
            raise RuntimeError(
                f"Unexpected NoData for {source}: "
                f"{src.nodata}; expected {expected_nodata}"
            )

        if src.scales[0] != 1 or src.offsets[0] != 0:
            raise RuntimeError(
                f"Unexpected categorical raster scale/offset: {source}"
            )

        geometry = basin.to_crs(src.crs).geometry.union_all()

        clipped, transform = mask(
            src,
            [geometry.__geo_interface__],
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

        output = np.full(values.shape, -9999, dtype=np.int16)
        output[valid] = values.data[valid]

        profile = src.profile.copy()
        profile.update(transform=transform)

    atomic_raster_write(destination, output, profile)
    return "created"


def calculate_attributes(gdf, raster, configuration):
    classes = configuration["classes"]
    prefix = configuration["prefix"]

    with rasterio.open(raster) as src:
        polygons = gdf.to_crs(src.crs)

    results = zonal_stats(
        polygons.geometry,
        str(raster),
        categorical=True,
        all_touched=True,
    )

    records = []
    report = []

    for (_, feature), histogram in zip(gdf.iterrows(), results):
        histogram = {
            int(k): int(v)
            for k, v in histogram.items()
        }

        # LGRIP30 V001 documents classes 0-3 only.
        # Treat class 4 as unclassified, not as cropland.
        if prefix == "lc3_":
            excluded = histogram.pop(4, 0)
            if excluded:
                print(
                    f"WARNING: LGRIP30 excluded {excluded} "
                    f"unclassified class-4 pixels for "
                    f"HRU {feature['HRU_ID']}",
                    flush=True,
                )

        total = sum(histogram.values())
        unexpected = sorted(set(histogram) - set(classes))

        if unexpected:
            raise RuntimeError(
                f"Unexpected categorical IDs: {unexpected}"
            )

        row = {
            "hruId": int(feature["HRU_ID"]),
            "gruId": int(feature["GRU_ID"]),
            "HRUarea_m2": float(feature["HRU_area"]),
        }

        for class_id, label in classes.items():
            column = f"{prefix}{label}_fraction"

            row[column] = (
                histogram.get(class_id, 0) / total
                if total > 0
                else np.nan
            )

        fraction_sum = sum(
            row[f"{prefix}{label}_fraction"]
            for label in classes.values()
        )

        report.append({
            "hruId": int(feature["HRU_ID"]),
            "gruId": int(feature["GRU_ID"]),
            "valid_pixels": total,
            "classes_present": len(histogram),
            "fraction_sum": fraction_sum,
            "complete": bool(
                total > 0
                and np.isclose(fraction_sum, 1.0, atol=1e-8)
            ),
        })

        records.append(row)

    return records, report


def write_csv(destination, records):
    if not records:
        raise RuntimeError("No records to write")

    destination.parent.mkdir(parents=True, exist_ok=True)

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
            os.unlink(temporary)


def main(dataset):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("control_file", type=Path)
    parser.add_argument(
        "--mode",
        choices=("both", "distributed", "lumped"),
        default="both",
    )
    parser.add_argument("--force", action="store_true")

    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Path to the categorical source raster",
    )

    args = parser.parse_args()

    config = DATASETS[dataset]

    if args.source is None:
        parser.error(
            f"--source is required; configure "
            f"attribute_{dataset}_source in the control file"
        )

    source = args.source.expanduser().resolve()


    if not source.is_file():
        raise FileNotFoundError(source)

    control = args.control_file.resolve(strict=True)
    domain = control_value(control, "domain_name")

    root = (
        Path(control_value(control, "root_path"))
        / f"domain_{domain}"
    )

    geometries = {}

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

        geometries["distributed"] = load_hrus(
            shapefile,
            root / "settings/SUMMA/attributes.nc",
        )


    if args.mode in ("both", "lumped"):
        geometries["lumped"] = load_hrus(
            root / "lumped/shapefiles/catchment"
            / f"{domain}_lumped_basin.shp",
            root / "lumped/settings/SUMMA/attributes.nc",
        )

    combined = gpd.GeoDataFrame(
        geometry=[
            gpd.GeoSeries(
                [
                    gdf.to_crs("EPSG:4326").geometry.union_all()
                    for gdf in geometries.values()
                ],
                crs="EPSG:4326",
            ).union_all()
        ],
        crs="EPSG:4326",
    )

    destination = (
        root / "parameters"
        / dataset / source.name
    )

    print(f"Domain: {domain}", flush=True)
    print(f"Dataset: {dataset}", flush=True)
    print(f"Mode: {args.mode}", flush=True)

    status = clip_source(
        source,
        destination,
        combined,
        config["expected_nodata"],
        force=args.force,
    )

    print(f"Raster: {status}", flush=True)

    for mode, gdf in geometries.items():
        rows, report = calculate_attributes(
            gdf, destination, config
        )

        if mode == "distributed":
            out_dir = root / "attributes" / dataset
            output = (
                out_dir / f"hru_{dataset}_attributes.csv"
            )
        else:
            out_dir = (
                root / "lumped/attributes" / dataset
            )
            output = (
                out_dir / f"lumped_{dataset}_attributes.csv"
            )

        report_path = (
            out_dir / f"{dataset}_processing_report.csv"
        )

        write_csv(output, rows)
        write_csv(report_path, report)

        complete = sum(item["complete"] for item in report)

        print(
            f"{mode}: {complete}/{len(gdf)} HRUs "
            "with complete class fractions",
            flush=True,
        )
        print(f"Attributes: {output}")
        print(f"Report: {report_path}")

        if complete != len(gdf):
            if dataset == "lgrip30":
                print(
                    f"WARNING: LGRIP30 incomplete coverage "
                    f"for {len(gdf) - complete}/{len(gdf)} "
                    f"HRUs ({mode}). Missing fractions "
                    "remain NaN and are recorded in "
                    "the processing report.",
                    flush=True,
                )
            else:
                raise RuntimeError(
                    f"Incomplete categorical coverage for {mode}"
                )

    print(f"{dataset} processing completed.")
    print("Source rasters and SUMMA files unchanged.")
