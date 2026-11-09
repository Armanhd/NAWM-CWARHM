#!/usr/bin/env python3
"""
CWARHM / CAMELS-SPAT-compatible GLHYMPS attributes.

Calculates:
    porosity_min, porosity_mean, porosity_max, porosity_std
    log_permeability_min, log_permeability_mean,
    log_permeability_max, log_permeability_std

Original CAMELS-SPAT definitions:
    Porosity      -> porosity
    Permeabi_1    -> log_permeability
    Mean          -> polygon-area-weighted mean
    Std           -> polygon-area-weighted population std
    Min/Max       -> minimum/maximum of intersected polygons

Area calculations use ESRI:102008, as in CAMELS-SPAT.

Unlike the original CAMELS-SPAT implementation, geological
polygons are clipped to each HRU or the lumped basin before
calculating statistics.

The original GLHYMPS source and SUMMA files are never modified.

Usage:
    python 1_process_glhymps.py CONTROL.txt
    python 1_process_glhymps.py CONTROL.txt --mode distributed
    python 1_process_glhymps.py CONTROL.txt --mode lumped
"""

import argparse
import csv
import os
import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr


SOURCE_DEFAULT = None

EQUAL_AREA_CRS = "ESRI:102008"

SOURCE_FIELDS = {
    "Porosity": "porosity",
    "Permeabi_1": "log_permeability",
}

STAT_NAMES = ("min", "mean", "max", "std")



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


def read_control(path, key):
    with path.open() as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#") or "|" not in line:
                continue

            left, right = line.split("|", 1)

            if left.strip() == key:
                value = right.split("#", 1)[0].strip()
                if value:
                    return value

    raise KeyError(f"Missing control setting: {key}")


def load_hrus(shape_path, summa_path):
    if not shape_path.is_file():
        raise FileNotFoundError(shape_path)

    if not summa_path.is_file():
        raise FileNotFoundError(summa_path)

    gdf = gpd.read_file(shape_path)

    if gdf.empty or gdf.crs is None:
        raise RuntimeError(f"Invalid HRU shapefile: {shape_path}")

    for field in ("HRU_ID", "GRU_ID", "HRU_area"):
        if field not in gdf.columns:
            raise RuntimeError(
                f"Missing {field} in {shape_path}"
            )

    for field in ("HRU_ID", "GRU_ID"):
        values = pd.to_numeric(
            gdf[field], errors="raise"
        ).to_numpy(dtype=float)

        if (
            not np.isfinite(values).all()
            or not np.equal(values, np.rint(values)).all()
        ):
            raise RuntimeError(f"Invalid {field} values")

        gdf[field] = values.astype(np.int64)

    gdf["HRU_area"] = pd.to_numeric(
        gdf["HRU_area"], errors="raise"
    )

    if gdf["HRU_ID"].duplicated().any():
        raise RuntimeError("Duplicate HRU_ID values")

    if (
        not np.isfinite(gdf["HRU_area"]).all()
        or (gdf["HRU_area"] <= 0).any()
    ):
        raise RuntimeError("Invalid HRU_area values")

    with xr.open_dataset(summa_path) as ds:
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
        raise RuntimeError(
            "HRU IDs do not match SUMMA attributes.nc"
        )

    gdf = (
        gdf.set_index("HRU_ID", drop=False)
        .loc[hru_ids]
        .copy()
        .reset_index(drop=True)
    )

    if not np.array_equal(
        gdf["GRU_ID"].to_numpy(), gru_ids
    ):
        raise RuntimeError(
            "GRU assignments do not match SUMMA"
        )

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


def load_glhymps(source, combined_hrus):
    """
    Read only the GLHYMPS features overlapping the
    domain bounding box, not the entire continental file.
    """
    if not source.is_file():
        raise FileNotFoundError(source)

    bounds = (
        combined_hrus
        .to_crs("EPSG:4326")
        .total_bounds
    )

    print(
        "Reading GLHYMPS features within basin bounds...",
        flush=True,
    )

    geol = gpd.read_file(
        source,
        bbox=tuple(bounds),
    )

    if geol.empty:
        raise RuntimeError(
            "No GLHYMPS polygons found in domain bounds"
        )

    if geol.crs is None:
        raise RuntimeError("GLHYMPS source has no CRS")

    required = [
        "IDENTITY_",
        "Porosity",
        "Permeabi_1",
    ]

    missing = [
        col for col in required
        if col not in geol.columns
    ]

    if missing:
        raise RuntimeError(
            f"Missing GLHYMPS columns: {missing}"
        )

    # Keep only fields needed by the original
    # CAMELS-SPAT GLHYMPS calculations.
    geol = geol[
        required + ["geometry"]
    ].copy()

    geol = geol.rename(
        columns={
            "Porosity": "porosity",
            "Permeabi_1": "log_permeability",
        }
    )

    geol["porosity"] = pd.to_numeric(
        geol["porosity"], errors="coerce"
    )

    geol["log_permeability"] = pd.to_numeric(
        geol["log_permeability"], errors="coerce"
    )

    geol = geol[
        geol.geometry.notna()
        & ~geol.geometry.is_empty
    ].copy()

    # Repair only the in-memory selection, never
    # the original shapefile.
    if not geol.geometry.is_valid.all():
        geol["geometry"] = geol.geometry.make_valid()

    geol = geol.explode(
        index_parts=False,
        ignore_index=True,
    )

    geol = geol[
        geol.geom_type.isin(["Polygon", "MultiPolygon"])
    ].copy()

    geol = geol.to_crs(EQUAL_AREA_CRS)

    geol = geol[
        geol.geometry.area > 0
    ].copy()

    if geol.empty:
        raise RuntimeError(
            "No valid GLHYMPS polygons after filtering"
        )

    print(
        f"Candidate geological polygons: {len(geol)}",
        flush=True,
    )

    return geol


def clip_to_hrus(geology, hrus):
    """
    Intersect geology with individual HRU polygons.
    Each output polygon receives the matching HRU_ID.
    """
    hru_shapes = hrus[
        ["HRU_ID", "geometry"]
    ].copy()

    result = gpd.overlay(
        geology,
        hru_shapes,
        how="intersection",
        keep_geom_type=True,
    )

    if result.empty:
        return result

    result["intersection_area_m2"] = (
        result.geometry.area
    )

    result = result[
        result["intersection_area_m2"] > 0
    ].copy()

    return result


def weighted_statistics(df, variable):
    """
    Area-weighted mean and population standard deviation.

    Min and max match the original CAMELS-SPAT approach.
    """
    if df.empty:
        return dict.fromkeys(STAT_NAMES, np.nan)

    values = df[variable].to_numpy(dtype=float)

    weights = df[
        "intersection_area_m2"
    ].to_numpy(dtype=float)

    valid = (
        np.isfinite(values)
        & np.isfinite(weights)
        & (weights > 0)
    )

    if not valid.any():
        return dict.fromkeys(STAT_NAMES, np.nan)

    values = values[valid]
    weights = weights[valid]

    mean = np.average(
        values,
        weights=weights,
    )

    variance = np.average(
        (values - mean) ** 2,
        weights=weights,
    )

    return {
        "min": float(values.min()),
        "mean": float(mean),
        "max": float(values.max()),
        "std": float(np.sqrt(variance)),
    }


def summarize_configuration(hrus, intersections):
    rows = []
    report = []

    for _, hru in hrus.iterrows():
        hru_id = int(hru["HRU_ID"])

        subset = intersections[
            intersections["HRU_ID"] == hru_id
        ]

        row = {
            "hruId": hru_id,
            "gruId": int(hru["GRU_ID"]),
            "HRUarea_m2": float(hru["HRU_area"]),
        }

        for variable in (
            "porosity",
            "log_permeability",
        ):
            stats = weighted_statistics(
                subset, variable
            )

            for stat in STAT_NAMES:
                row[f"{variable}_{stat}"] = stats[stat]

        clipped_area = float(
            subset["intersection_area_m2"].sum()
        ) if not subset.empty else 0.0

        geometry_area = float(hru.geometry.area)

        coverage = (
            clipped_area / geometry_area
            if geometry_area > 0
            else np.nan
        )

        report.append({
            "hruId": hru_id,
            "gruId": int(hru["GRU_ID"]),
            "hru_geometry_area_m2": geometry_area,
            "glhymps_intersection_area_m2": clipped_area,
            "coverage_fraction": coverage,
            "intersected_polygon_count": len(subset),
            "porosity_valid_polygons": int(
                np.isfinite(
                    pd.to_numeric(
                        subset["porosity"],
                        errors="coerce",
                    )
                ).sum()
            ),
            "permeability_valid_polygons": int(
                np.isfinite(
                    pd.to_numeric(
                        subset["log_permeability"],
                        errors="coerce",
                    )
                ).sum()
            ),
        })

        rows.append(row)

    return rows, report


def write_csv(path, records):
    if not records:
        raise RuntimeError("No CSV records to write")

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temp = tempfile.mkstemp(
        prefix=path.stem + "_",
        suffix=".tmp.csv",
        dir=path.parent,
    )
    os.close(fd)

    try:
        with open(temp, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=records[0].keys(),
            )
            writer.writeheader()
            writer.writerows(records)

        os.replace(temp, path)

    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_geopackage(path, geology):
    """
    Store the domain-clipped geology as a GeoPackage.
    Never overwrite an existing output.
    """
    if path.exists():
        print(
            f"Clipped geology already exists: {path}",
            flush=True,
        )
        return

    if geology.empty:
        return

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    geology.to_file(
        path,
        driver="GPKG",
        layer="glhymps_clipped",
    )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "control_file",
        type=Path,
    )

    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to the GLHYMPS shapefile",
    )

    parser.add_argument(
        "--mode",
        choices=(
            "both",
            "distributed",
            "lumped",
        ),
        default="both",
    )

    args = parser.parse_args()

    control = args.control_file.resolve(
        strict=True
    )

    domain = read_control(
        control, "domain_name"
    )

    root = (
        Path(read_control(control, "root_path"))
        / f"domain_{domain}"
    )

    if not root.is_dir():
        raise FileNotFoundError(root)

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
            root
            / "lumped/shapefiles/catchment"
            / f"{domain}_lumped_basin.shp",
            root
            / "lumped/settings/SUMMA/attributes.nc",
        )

    all_hrus = gpd.GeoDataFrame(
        pd.concat(
            [
                gdf[["geometry"]]
                for gdf in configurations.values()
            ],
            ignore_index=True,
        ),
        crs=EQUAL_AREA_CRS,
    )

    print(f"Domain: {domain}")
    print(f"Mode: {args.mode}")

    geology = load_glhymps(
        args.source,
        all_hrus,
    )

    # Save basin-clipped geological polygons.
    # Use the union of all selected HRUs.
    domain_geometry = safe_union(all_hrus.geometry)

    domain_shape = gpd.GeoDataFrame(
        geometry=[domain_geometry],
        crs=EQUAL_AREA_CRS,
    )

    basin_geology = gpd.overlay(
        geology,
        domain_shape,
        how="intersection",
        keep_geom_type=True,
    )

    if basin_geology.empty:
        raise RuntimeError(
            "No geology intersects the basin"
        )

    clipped_path = (
        root
        / "parameters/glhymps"
        / "glhymps_clipped.gpkg"
    )

    save_geopackage(
        clipped_path,
        basin_geology,
    )

    for mode, hrus in configurations.items():

        intersections = clip_to_hrus(
            basin_geology,
            hrus,
        )

        rows, report = summarize_configuration(
            hrus,
            intersections,
        )

        if mode == "distributed":
            out_dir = (
                root / "attributes/glhymps"
            )
            attr_file = (
                out_dir
                / "hru_glhymps_attributes.csv"
            )
        else:
            out_dir = (
                root
                / "lumped/attributes/glhymps"
            )
            attr_file = (
                out_dir
                / "lumped_glhymps_attributes.csv"
            )

        report_file = (
            out_dir
            / "glhymps_coverage_report.csv"
        )

        write_csv(attr_file, rows)
        write_csv(report_file, report)

        incomplete = sum(
            (r["coverage_fraction"] < 0.99)
            or (r["coverage_fraction"] > 1.01)
            or (r["porosity_valid_polygons"] == 0)
            or (r["permeability_valid_polygons"] == 0)
            for r in report
        )

        print(
            f"{mode}: {len(hrus)} HRUs processed; "
            f"{incomplete} with potential coverage/data issues"
        )

        print(f"Attributes: {attr_file}")
        print(f"Coverage report: {report_file}")

    print(f"Clipped geology: {clipped_path}")
    print("GLHYMPS processing completed.")
    print("Original source and SUMMA files unchanged.")


if __name__ == "__main__":
    main()
