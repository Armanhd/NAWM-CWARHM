#!/usr/bin/env python3
"""
HydroLAKES attributes for NWAM-CWARHM.

CAMELS-SPAT-compatible attributes:
    open_water_number
    known_reservoirs
    open_water_area_[min,mean,max,std,total]
    open_water_volume_[min,mean,max,std,total]
    reservoir_area_[min,mean,max,std,total]
    reservoir_volume_[min,mean,max,std,total]

For lakes crossing HRU boundaries:
    clipped_area_km2 = round(intersection_area_km2, 2)
    clipped_volume = original_volume *
                     clipped_area_km2 / original_lake_area_km2

The rounding and proportional-volume approximation follow
the original CAMELS-SPAT HydroLAKES implementation.

Corrections:
    - Lakes are counted separately for each HRU.
    - Lakes are clipped to actual basin/HRU boundaries.
    - The global source archive is never modified.

Run:
    python 1_process_hydrolakes.py CONTROL.txt
    python 1_process_hydrolakes.py CONTROL.txt --mode distributed
    python 1_process_hydrolakes.py CONTROL.txt --mode lumped
"""

import argparse
import csv
import os
import tempfile
from pathlib import Path

import fiona
import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr


ARCHIVE = None

INNER_SHP = (
    "HydroLAKES_polys_v10_shp/"
    "HydroLAKES_polys_v10.shp"
)

EQUAL_AREA_CRS = "ESRI:102008"

STATISTICS = ("min", "mean", "max", "std", "total")



def safe_union(geometry):
    from shapely import set_precision, union_all

    valid = geometry.make_valid()

    try:
        result = valid.union_all()
    except Exception:
        result = union_all([
            set_precision(g, 0.01)
            for g in valid
        ])

    if result.is_empty or not result.is_valid:
        raise RuntimeError("Geometry union remained invalid")

    return result


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


def load_hrus(shapefile, attributes_file):
    if not shapefile.is_file():
        raise FileNotFoundError(shapefile)

    if not attributes_file.is_file():
        raise FileNotFoundError(attributes_file)

    gdf = gpd.read_file(shapefile)

    if gdf.empty or gdf.crs is None:
        raise RuntimeError(f"Invalid HRU geometry: {shapefile}")

    for name in ("HRU_ID", "GRU_ID", "HRU_area"):
        if name not in gdf.columns:
            raise RuntimeError(f"Missing {name}: {shapefile}")

    for name in ("HRU_ID", "GRU_ID"):
        values = pd.to_numeric(
            gdf[name], errors="raise"
        ).to_numpy(dtype=float)

        if (
            not np.isfinite(values).all()
            or not np.equal(values, np.rint(values)).all()
        ):
            raise RuntimeError(f"Invalid {name}: {shapefile}")

        gdf[name] = values.astype(np.int64)

    gdf["HRU_area"] = pd.to_numeric(
        gdf["HRU_area"], errors="raise"
    )

    if gdf["HRU_ID"].duplicated().any():
        raise RuntimeError("Duplicate HRU IDs")

    with xr.open_dataset(attributes_file) as ds:
        hru_ids = np.asarray(ds["hruId"].values, dtype=np.int64)
        gru_ids = np.asarray(ds["hru2gruId"].values, dtype=np.int64)

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

    return gdf.to_crs(EQUAL_AREA_CRS)


def read_lakes(archive, basin):
    """
    Read only candidate lakes overlapping the basin bounding box.
    The archive is accessed directly through GDAL/Fiona.
    """
    if not archive.is_file():
        raise FileNotFoundError(archive)

    source = (
        f"zip://{archive}!{INNER_SHP}"
        if archive.suffix.lower() == ".zip"
        else str(archive)
    )

    with fiona.open(source) as collection:
        fields = collection.schema["properties"]

        required = ("Lake_type", "Lake_area", "Vol_total")

        missing = [name for name in required if name not in fields]

        if missing:
            raise RuntimeError(
                f"Missing HydroLAKES attributes: {missing}"
            )

        print("HydroLAKES source CRS:", collection.crs)
        print("HydroLAKES attribute fields verified.", flush=True)

    basin_wgs84 = basin.to_crs("EPSG:4326")
    bounds = tuple(basin_wgs84.total_bounds)

    print("Reading lakes near basin...", flush=True)

    lakes = gpd.read_file(source, bbox=bounds)

    if lakes.empty:
        return gpd.GeoDataFrame(
            columns=["Lake_type", "Lake_area", "Vol_total", "geometry"],
            geometry="geometry",
            crs=EQUAL_AREA_CRS,
        )

    if lakes.crs is None:
        raise RuntimeError("HydroLAKES CRS is missing")

    lakes = lakes[
        lakes.geometry.notna()
        & ~lakes.geometry.is_empty
    ].copy()

    if not lakes.geometry.is_valid.all():
        lakes["geometry"] = lakes.geometry.make_valid()

    lakes = lakes.to_crs(EQUAL_AREA_CRS)

    lakes["Lake_type"] = pd.to_numeric(
        lakes["Lake_type"], errors="coerce"
    )
    lakes["Lake_area"] = pd.to_numeric(
        lakes["Lake_area"], errors="coerce"
    )
    lakes["Vol_total"] = pd.to_numeric(
        lakes["Vol_total"], errors="coerce"
    )

    # Preserve individual lake identities.
    lakes = lakes.reset_index(drop=True)

    print(f"Candidate lakes: {len(lakes)}", flush=True)

    return lakes


def clip_lakes_to_polygon(lakes, polygon):
    """
    One record per source lake intersecting the target polygon.
    Clipped lake area is in km2; volume is million m3.
    """
    records = []

    if lakes.empty:
        return records

    candidates = lakes[
        lakes.geometry.intersects(polygon)
    ]

    for _, lake in candidates.iterrows():
        intersection = lake.geometry.intersection(polygon)

        if intersection.is_empty:
            continue

        area_m2 = intersection.area

        if area_m2 <= 0:
            continue

        original_area = float(lake["Lake_area"])
        original_volume = float(lake["Vol_total"])

        clipped_area = round(area_m2 / 1e6, 2)

        if (
            np.isfinite(original_area)
            and original_area > 0
            and np.isfinite(original_volume)
        ):
            clipped_volume = (
                original_volume * clipped_area / original_area
            )
        else:
            clipped_volume = np.nan

        records.append({
            "Lake_type": lake["Lake_type"],
            "Lake_area": clipped_area,
            "Vol_total": clipped_volume,
            "geometry": intersection,
        })

    return records


def summary(values):
    """
    CAMELS-SPAT uses pandas min/mean/max/std/sum.
    Pandas std is sample std (ddof=1).

    For an empty lake category, report zero because
    there are no lakes or reservoirs contributing.
    """
    if not values:
        return {stat: 0.0 for stat in STATISTICS}

    series = pd.Series(values, dtype="float64")

    return {
        "min": float(series.min()),
        "mean": float(series.mean()),
        "max": float(series.max()),
        "std": float(series.std()),
        "total": float(series.sum()),
    }


def calculate_attributes(lakes):
    records = {}

    records["open_water_number"] = len(lakes)

    reservoirs = [
        lake for lake in lakes
        if lake["Lake_type"] == 2
    ]

    records["known_reservoirs"] = len(reservoirs)

    groups = {
        "open_water": lakes,
        "reservoir": reservoirs,
    }

    for name, group in groups.items():
        for original_field, label in (
            ("Lake_area", "area"),
            ("Vol_total", "volume"),
        ):
            values = [
                item[original_field] for item in group
            ]

            stats = summary(values)

            for stat in STATISTICS:
                records[f"{name}_{label}_{stat}"] = stats[stat]

    return records


def write_csv(path, rows):
    if not rows:
        raise RuntimeError("No rows to write")

    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary = tempfile.mkstemp(
        prefix=path.stem + "_",
        suffix=".tmp.csv",
        dir=path.parent,
    )
    os.close(fd)

    try:
        with open(temporary, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(rows[0].keys()),
            )
            writer.writeheader()
            writer.writerows(rows)

        os.replace(temporary, path)

    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("control_file", type=Path)

    parser.add_argument(
        "--archive",
        type=Path,
        required=True,
        help="HydroLAKES ZIP archive or extracted shapefile",
    )


    parser.add_argument(
        "--mode",
        choices=("both", "distributed", "lumped"),
        default="both",
    )

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

    all_hrus = gpd.GeoDataFrame(
        pd.concat(
            [gdf[["geometry"]] for gdf in configurations.values()],
            ignore_index=True,
        ),
        crs=EQUAL_AREA_CRS,
    )

    basin_polygon = safe_union(all_hrus.geometry)

    basin = gpd.GeoDataFrame(
        geometry=[basin_polygon],
        crs=EQUAL_AREA_CRS,
    )

    print(f"Domain: {domain}")
    print(f"Mode: {args.mode}", flush=True)

    lakes = read_lakes(args.archive, basin)

    # Save basin-specific clipped lake geometries for inspection.
    basin_lakes = clip_lakes_to_polygon(
        lakes,
        basin_polygon,
    )

    gpkg_path = (
        root / "parameters/hydrolakes"
        / "hydrolakes_clipped.gpkg"
    )

    if basin_lakes and not gpkg_path.exists():
        gpkg_path.parent.mkdir(parents=True, exist_ok=True)

        basin_gdf = gpd.GeoDataFrame(
            basin_lakes,
            geometry="geometry",
            crs=EQUAL_AREA_CRS,
        )

        basin_gdf.to_file(
            gpkg_path,
            layer="lakes",
            driver="GPKG",
        )

    print(
        f"Lakes intersecting basin: {len(basin_lakes)}",
        flush=True,
    )

    for mode, hrus in configurations.items():
        rows = []
        report = []

        for _, hru in hrus.iterrows():
            hru_lakes = clip_lakes_to_polygon(
                lakes,
                hru.geometry,
            )

            attributes = calculate_attributes(hru_lakes)

            row = {
                "hruId": int(hru["HRU_ID"]),
                "gruId": int(hru["GRU_ID"]),
                "HRUarea_m2": float(hru["HRU_area"]),
            }

            row.update(attributes)
            rows.append(row)

            report.append({
                "hruId": int(hru["HRU_ID"]),
                "lake_count": attributes["open_water_number"],
                "reservoir_count": attributes["known_reservoirs"],
                "clipped_lake_area_km2":
                    attributes["open_water_area_total"],
                "clipped_lake_volume_million_m3":
                    attributes["open_water_volume_total"],
            })

        if mode == "distributed":
            out_dir = root / "attributes/hydrolakes"
            attr_path = (
                out_dir / "hru_hydrolakes_attributes.csv"
            )
        else:
            out_dir = (
                root / "lumped/attributes/hydrolakes"
            )
            attr_path = (
                out_dir / "lumped_hydrolakes_attributes.csv"
            )

        report_path = (
            out_dir / "hydrolakes_processing_report.csv"
        )

        write_csv(attr_path, rows)
        write_csv(report_path, report)

        print(
            f"{mode}: {len(rows)} HRUs processed",
            flush=True,
        )
        print(f"Attributes: {attr_path}")
        print(f"Report: {report_path}")

    print("HydroLAKES processing completed.")
    print("Original source and SUMMA files unchanged.")


if __name__ == "__main__":
    main()
