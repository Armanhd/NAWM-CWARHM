#!/usr/bin/env python3

"""
Create a true lumped SUMMA catchment from an existing distributed catchment.

Input:
    control_<DOMAIN>_lumped.txt

The catchment_shp_path/name in the lumped control identify the existing
distributed source catchment.

Output:
    <root_path>/domain_<DOMAIN>/lumped/shapefiles/catchment/
        <DOMAIN>_lumped_basin.shp

The output contains exactly:
    1 polygon
    1 HRU
    1 GRU

The distributed source shapefile is never modified.
"""

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd


def read_control(control_file):
    settings = {}

    with open(control_file, "r") as f:
        for line in f:
            stripped = line.strip()

            if not stripped or stripped.startswith("#") or "|" not in line:
                continue

            key, value = line.split("|", 1)
            value = value.split("#", 1)[0].strip()

            settings[key.strip()] = value

    return settings


def remove_shapefile(path):
    for ext in [
        ".shp", ".shx", ".dbf", ".prj",
        ".cpg", ".qix", ".sbn", ".sbx"
    ]:
        candidate = path.with_suffix(ext)

        if candidate.exists():
            candidate.unlink()


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "control_file",
        type=Path,
        help="Lumped CWARHM control file."
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing lumped shapefile."
    )

    args = parser.parse_args()

    control_file = args.control_file.resolve()

    if not control_file.exists():
        raise FileNotFoundError(control_file)

    control = read_control(control_file)

    domain = control["domain_name"]
    root_path = Path(control["root_path"])

    source_file = (
        Path(control["catchment_shp_path"])
        / control["catchment_shp_name"]
    )

    output_dir = (
        root_path
        / f"domain_{domain}"
        / "lumped"
        / "shapefiles"
        / "catchment"
    )

    output_file = (
        output_dir
        / f"{domain}_lumped_basin.shp"
    )

    print("=" * 78)
    print("PREPARE LUMPED CATCHMENT")
    print("=" * 78)
    print(f"Domain          : {domain}")
    print(f"Source          : {source_file}")
    print(f"Output          : {output_file}")

    if not source_file.exists():
        raise FileNotFoundError(
            f"Source catchment does not exist:\n{source_file}"
        )

    if output_file.exists() and not args.overwrite:
        raise FileExistsError(
            f"Lumped catchment already exists:\n{output_file}\n"
            "Use --overwrite if intentional."
        )

    gdf = gpd.read_file(source_file)

    print(f"Source features : {len(gdf)}")

    if len(gdf) == 0:
        raise RuntimeError("Source catchment contains no features.")

    if gdf.crs is None:
        raise RuntimeError("Source catchment has no CRS.")

    if gdf.geometry.isna().any():
        raise RuntimeError("Source catchment contains null geometries.")

    if gdf.geometry.is_empty.any():
        raise RuntimeError("Source catchment contains empty geometries.")

    # Repair invalid geometries where possible.
    if not gdf.geometry.is_valid.all():
        print("Repairing invalid source geometries...")
        gdf["geometry"] = gdf.geometry.buffer(0)

    if not gdf.geometry.is_valid.all():
        raise RuntimeError(
            "Invalid geometries remain after attempted repair."
        )

    # Standardize source geometry to WGS84.
    gdf = gdf.to_crs("EPSG:4326")

    # Dissolve every distributed HRU into one whole-basin geometry.
    basin_geometry = gdf.geometry.union_all()

    if basin_geometry is None or basin_geometry.is_empty:
        raise RuntimeError("Dissolve produced an empty geometry.")

    # Create temporary one-feature GeoDataFrame.
    lumped = gpd.GeoDataFrame(
        {"geometry": [basin_geometry]},
        crs="EPSG:4326"
    )

    # Calculate area and representative location in equal-area CRS.
    projected = lumped.to_crs("EPSG:6933")

    area_m2 = float(projected.geometry.area.iloc[0])

    if area_m2 <= 0:
        raise RuntimeError(
            f"Invalid lumped basin area: {area_m2}"
        )

    # Use representative point rather than raw geographic centroid.
    point_projected = projected.geometry.representative_point().iloc[0]

    point = gpd.GeoSeries(
        [point_projected],
        crs="EPSG:6933"
    ).to_crs("EPSG:4326").iloc[0]

    # SUMMA lumped identifiers.
    lumped["GRU_ID"] = 1
    lumped["HRU_ID"] = 1
    lumped["HRU_area"] = float(area_m2)
    lumped["area"] = float(area_m2)
    lumped["center_lat"] = float(point.y)
    lumped["center_lon"] = float(point.x)

    # Put attributes before geometry.
    lumped = lumped[
        [
            "GRU_ID",
            "HRU_ID",
            "HRU_area",
            "area",
            "center_lat",
            "center_lon",
            "geometry",
        ]
    ]

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    if args.overwrite:
        remove_shapefile(output_file)

    lumped.to_file(output_file)

    # ----------------------------------------------------------
    # Verification
    # ----------------------------------------------------------

    check = gpd.read_file(output_file)

    written_area = float(check.iloc[0]["HRU_area"])

    relative_error = abs(written_area - area_m2) / area_m2

    if relative_error > 1e-6:
        raise RuntimeError(
            "HRU_area was not preserved correctly when writing shapefile.\n"
            f"Expected : {area_m2}\n"
            f"Written  : {written_area}\n"
            f"Relative error: {relative_error}"
        )
    if len(check) != 1:
        raise RuntimeError(
            f"Expected 1 lumped feature; found {len(check)}."
        )

    if int(check.iloc[0]["HRU_ID"]) != 1:
        raise RuntimeError("HRU_ID verification failed.")

    if int(check.iloc[0]["GRU_ID"]) != 1:
        raise RuntimeError("GRU_ID verification failed.")

    if check.geometry.iloc[0].is_empty:
        raise RuntimeError("Output geometry is empty.")

    if not check.geometry.iloc[0].is_valid:
        raise RuntimeError("Output geometry is invalid.")

    print()
    print("VERIFICATION")
    print("-" * 78)
    print("Features        : 1")
    print("HRU_ID          : 1")
    print("GRU_ID          : 1")
    print(f"Area (m2)       : {area_m2:.3f}")
    print(f"Center latitude : {point.y:.6f}")
    print(f"Center longitude: {point.x:.6f}")
    print(f"Geometry        : {check.geometry.iloc[0].geom_type}")

    print()
    print("PASS: lumped catchment created successfully.")
    print("=" * 78)


if __name__ == "__main__":
    main()
