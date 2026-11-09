#!/usr/bin/env python3
"""
CWARHM continuous SoilGrids attribute processing.

Supports distributed, lumped, and both configurations.

Original SoilGrids, SUMMA files, and existing soil
classes are never modified.

Scientific calculations are unchanged.
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
from rasterio.warp import reproject, Resampling
from rasterstats import zonal_stats


PROPERTIES = (
    "bdod",
    "cfvo",
    "clay",
    "sand",
    "silt",
    "soc",
)

DEPTHS = (
    "0-5cm",
    "5-15cm",
    "15-30cm",
    "30-60cm",
    "60-100cm",
    "100-200cm",
)

AVAILABLE_FIELDS = (
    "mean",
    "uncertainty",
    "Q0.05",
    "Q0.5",
    "Q0.95",
)

NODATA = -9999.0


# ============================================================
# CONTROL FILE
# ============================================================

def read_control(path, key):
    with open(path) as file:
        for line in file:
            line = line.strip()

            if (
                not line
                or line.startswith("#")
                or "|" not in line
            ):
                continue

            left, right = line.split("|", 1)

            if left.strip() == key:
                value = right.split("#", 1)[0].strip()

                if not value:
                    raise ValueError(
                        f"Empty control setting: {key}"
                    )

                return value

    raise KeyError(f"Missing control setting: {key}")


def distributed_shapefile(control, root, domain):
    """Support standardized and original MERIT basin names."""

    folder = root / "shapefiles/catchment"

    standard = folder / f"{domain}_distributed_basin.shp"

    if standard.is_file():
        return standard

    original_name = read_control(
        control,
        "catchment_shp_name",
    )

    original = folder / original_name

    if original.is_file():
        return original

    raise FileNotFoundError(
        f"Distributed catchment shapefile missing: "
        f"{standard} or {original}"
    )


# ============================================================
# INPUT GEOMETRY
# ============================================================

def load_geometry(shapefile, attributes_file):
    if not shapefile.is_file():
        raise FileNotFoundError(shapefile)

    if not attributes_file.is_file():
        raise FileNotFoundError(attributes_file)

    gdf = gpd.read_file(shapefile)

    if gdf.empty or gdf.crs is None:
        raise RuntimeError(
            f"Invalid catchment shapefile: {shapefile}"
        )

    for column in ("HRU_ID", "GRU_ID", "HRU_area"):
        if column not in gdf.columns:
            raise RuntimeError(
                f"Missing {column}: {shapefile}"
            )

    for column in ("HRU_ID", "GRU_ID"):
        values = np.asarray(
            gdf[column],
            dtype=np.float64,
        )

        if (
            not np.isfinite(values).all()
            or not np.equal(values, np.rint(values)).all()
        ):
            raise RuntimeError(
                f"Invalid integer IDs: {column}"
            )

        gdf[column] = values.astype(np.int64)

    if gdf["HRU_ID"].duplicated().any():
        raise RuntimeError(
            f"Duplicate HRU_ID values: {shapefile}"
        )

    with xr.open_dataset(attributes_file) as ds:
        hru_ids = np.asarray(
            ds["hruId"].values,
            dtype=np.int64,
        )

        gru_ids = np.asarray(
            ds["hru2gruId"].values,
            dtype=np.int64,
        )

    if (
        len(hru_ids) != len(gdf)
        or set(hru_ids) != set(gdf["HRU_ID"])
    ):
        raise RuntimeError(
            f"HRU IDs do not match SUMMA: {shapefile}"
        )

    gdf = (
        gdf.set_index("HRU_ID", drop=False)
        .loc[hru_ids]
        .copy()
        .reset_index(drop=True)
    )

    if not np.array_equal(
        gdf["GRU_ID"].to_numpy(dtype=np.int64),
        gru_ids,
    ):
        raise RuntimeError(
            f"GRU assignments do not match SUMMA: {shapefile}"
        )

    # Repair invalid geometries in memory only.
    if (
        not gdf.geometry.isna().any()
        and not gdf.geometry.is_empty.any()
    ):
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
        raise RuntimeError(
            f"Invalid catchment geometry: {shapefile}"
        )

    if (
        not np.isfinite(gdf["HRU_area"]).all()
        or (gdf["HRU_area"] <= 0).any()
    ):
        raise RuntimeError(
            f"Invalid HRU_area: {shapefile}"
        )

    return gdf


# ============================================================
# ATOMIC GEOTIFF WRITER
# ============================================================

def write_raster(destination, profile, array):
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    profile = profile.copy()
    profile.pop("blockxsize", None)
    profile.pop("blockysize", None)

    profile.update(
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype="float32",
        nodata=NODATA,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
        BIGTIFF="IF_SAFER",
    )

    fd, temporary = tempfile.mkstemp(
        prefix=destination.stem + "_",
        suffix=".tmp.tif",
        dir=destination.parent,
    )

    os.close(fd)

    try:
        with rasterio.open(
            temporary, "w", **profile
        ) as dst:
            dst.write(
                array.astype(np.float32),
                1,
            )

        with rasterio.open(temporary) as check:
            if check.count != 1:
                raise RuntimeError(
                    f"Invalid output: {temporary}"
                )

        os.replace(temporary, destination)

    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


# ============================================================
# VALIDATE EXISTING CLIP
# ============================================================

def valid_existing_raster(path):
    if not path.is_file():
        return False

    try:
        with rasterio.open(path) as src:
            if (
                src.count != 1
                or src.crs is None
                or src.width == 0
                or src.height == 0
                or src.nodata is None
            ):
                return False

            for _, window in src.block_windows(1):
                data = src.read(
                    1,
                    window=window,
                    masked=True,
                )

                if np.ma.count(data) > 0:
                    return True

    except Exception:
        return False

    return False


# ============================================================
# CLIP SOURCE RASTER
# ============================================================

def create_clip(source, destination, basin):
    if valid_existing_raster(destination):
        return "reused"

    if not source.is_file():
        return "missing_source"

    with rasterio.open(source) as src:
        if src.crs is None:
            raise RuntimeError(
                f"Source has no CRS: {source}"
            )

        basin_src = basin.to_crs(src.crs)
        geometry = basin_src.geometry.union_all()

        try:
            clipped, transform = mask(
                src,
                [geometry.__geo_interface__],
                crop=True,
                all_touched=True,
                filled=False,
            )

        except ValueError:
            return "outside_source_extent"

        data = clipped[0]

        valid = (
            ~np.ma.getmaskarray(data)
            & np.isfinite(data.data)
        )

        if not np.any(valid):
            return "no_valid_source_pixels"

        output = np.full(
            data.shape,
            NODATA,
            dtype=np.float32,
        )

        output[valid] = data.data[valid]

        profile = src.profile.copy()
        profile.update(transform=transform)

    write_raster(destination, profile, output)

    return "created"


# ============================================================
# DERIVE SOIL PROPERTIES
# ============================================================

def derive_properties(sand_file, clay_file, output_dir, depth):
    porosity_file = (
        output_dir / f"porosity_{depth}_mean.tif"
    )

    conductivity_file = (
        output_dir / f"conductivity_{depth}_mean.tif"
    )

    if (
        valid_existing_raster(porosity_file)
        and valid_existing_raster(conductivity_file)
    ):
        return {
            "porosity": porosity_file,
            "conductivity": conductivity_file,
        }

    if (
        not valid_existing_raster(sand_file)
        or not valid_existing_raster(clay_file)
    ):
        return {}

    with rasterio.open(sand_file) as sand_src:
        sand = sand_src.read(
            1,
            masked=True,
        ).astype(np.float64)

        profile = sand_src.profile.copy()

        with rasterio.open(clay_file) as clay_src:
            if (
                clay_src.crs == sand_src.crs
                and clay_src.transform == sand_src.transform
                and clay_src.shape == sand_src.shape
            ):
                clay = clay_src.read(
                    1,
                    masked=True,
                ).astype(np.float64)

            else:
                aligned = np.full(
                    sand_src.shape,
                    NODATA,
                    dtype=np.float32,
                )

                reproject(
                    source=rasterio.band(clay_src, 1),
                    destination=aligned,
                    src_transform=clay_src.transform,
                    src_crs=clay_src.crs,
                    src_nodata=clay_src.nodata,
                    dst_transform=sand_src.transform,
                    dst_crs=sand_src.crs,
                    dst_nodata=NODATA,
                    resampling=Resampling.nearest,
                )

                clay = np.ma.masked_equal(
                    aligned,
                    NODATA,
                ).astype(np.float64)

    sand_values = np.asarray(sand.data)
    clay_values = np.asarray(clay.data)

    valid = (
        ~np.ma.getmaskarray(sand)
        & ~np.ma.getmaskarray(clay)
        & np.isfinite(sand_values)
        & np.isfinite(clay_values)
        & (sand_values >= 0)
        & (clay_values >= 0)
        & (sand_values <= 1000)
        & (clay_values <= 1000)
    )

    if not valid.any():
        return {}

    # Original SoilGrids texture g/kg -> percent.
    sand_percent = sand_values[valid] / 10.0
    clay_percent = clay_values[valid] / 10.0

    # Original CAMELS-SPAT / Cosby equations.
    theta_s = (
        50.5
        - 0.142 * sand_percent
        - 0.037 * clay_percent
    )

    porosity = theta_s / 100.0

    log_ks = (
        -0.6
        + 0.0126 * sand_percent
        - 0.0064 * clay_percent
    )

    conductivity = (
        2.54 * np.power(10.0, log_ks)
    )

    derived = {
        "porosity": (porosity_file, porosity),
        "conductivity": (
            conductivity_file,
            conductivity,
        ),
    }

    outputs = {}

    for name, (destination, values) in derived.items():
        if not valid_existing_raster(destination):
            array = np.full(
                sand.shape,
                NODATA,
                dtype=np.float32,
            )

            array[valid] = values.astype(np.float32)

            write_raster(
                destination,
                profile,
                array,
            )

        outputs[name] = destination

    return outputs


# ============================================================
# ZONAL STATISTICS
# ============================================================

def harmonic_mean(data):
    values = np.ma.array(data).compressed()

    values = values[
        np.isfinite(values) & (values > 0)
    ]

    if len(values) == 0:
        return np.nan

    return float(
        len(values) / np.sum(1.0 / values)
    )


def add_statistics(rows, gdf, raster, name, harmonic=False):
    keys = ("min", "mean", "max", "std")

    for row in rows:
        for stat in keys:
            row[f"{name}_{stat}"] = np.nan

        row[f"{name}_valid_pixels"] = 0

        if harmonic:
            row[f"{name}_harmonic_mean"] = np.nan

    if not valid_existing_raster(raster):
        return 0

    with rasterio.open(raster) as src:
        shapes = gdf.to_crs(src.crs)

    extra = (
        {"harmonic_mean": harmonic_mean}
        if harmonic
        else None
    )

    result = zonal_stats(
        shapes.geometry,
        str(raster),
        stats=["count", *keys],
        add_stats=extra,
        all_touched=True,
    )

    valid_hrus = 0

    for row, values in zip(rows, result):
        count = int(values.get("count") or 0)

        row[f"{name}_valid_pixels"] = count

        if count == 0:
            continue

        valid_hrus += 1

        for stat in keys:
            value = values.get(stat)

            row[f"{name}_{stat}"] = (
                float(value)
                if value is not None
                else np.nan
            )

        if harmonic:
            value = values.get("harmonic_mean")

            row[f"{name}_harmonic_mean"] = (
                float(value)
                if value is not None
                else np.nan
            )

    return valid_hrus


# ============================================================
# WRITE CSV
# ============================================================

def write_csv(path, rows):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temporary = tempfile.mkstemp(
        prefix=path.stem + "_",
        suffix=".tmp.csv",
        dir=path.parent,
    )

    os.close(fd)

    try:
        with open(
            temporary,
            "w",
            newline="",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=list(rows[0].keys()),
            )

            writer.writeheader()
            writer.writerows(rows)

        os.replace(temporary, path)

    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "control_file",
        type=Path,
    )

    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Directory containing raw SoilGrids property rasters",
    )

    parser.add_argument(
        "--mode",
        choices=("both", "distributed", "lumped"),
        default="both",
    )

    parser.add_argument(
        "--fields",
        nargs="+",
        choices=AVAILABLE_FIELDS,
        default=["mean", "uncertainty"],
    )

    args = parser.parse_args()

    if not args.source.is_dir():
        raise NotADirectoryError(args.source)

    control = args.control_file.resolve(strict=True)

    domain = read_control(
        control,
        "domain_name",
    )

    root = (
        Path(read_control(control, "root_path"))
        / f"domain_{domain}"
    )

    # --------------------------------------------------------
    # SELECT DISTRIBUTED AND/OR LUMPED INPUTS
    # --------------------------------------------------------

    geometries = {}

    if args.mode in ("both", "distributed"):
        shapefile = distributed_shapefile(
            control, root, domain
        )

        geometries["distributed"] = load_geometry(
            shapefile,
            root / "settings/SUMMA/attributes.nc",
        )

    if args.mode in ("both", "lumped"):
        lumped = load_geometry(
            root
            / "lumped/shapefiles/catchment"
            / f"{domain}_lumped_basin.shp",

            root
            / "lumped/settings/SUMMA/attributes.nc",
        )

        if len(lumped) != 1:
            raise RuntimeError(
                "Expected one lumped HRU"
            )

        geometries["lumped"] = lumped

    # Preserve original lumped clipping when available.
    # Distributed-only basins use the distributed basin.
    clip_geometry = (
        geometries["lumped"]
        if "lumped" in geometries
        else geometries["distributed"]
    )

    rows = {}

    for mode, gdf in geometries.items():
        rows[mode] = [
            {
                "hruId": int(feature["HRU_ID"]),
                "gruId": int(feature["GRU_ID"]),
                "HRUarea_m2": float(feature["HRU_area"]),
            }
            for _, feature in gdf.iterrows()
        ]

    raw_dir = (
        root / "parameters/soilgrids_properties/raw"
    )

    derived_dir = (
        root / "parameters/soilgrids_properties/derived"
    )

    report = []

    print(f"Domain: {domain}")
    print(f"Mode: {args.mode}")

    for mode, gdf in geometries.items():
        print(f"{mode} HRUs: {len(gdf)}")

    fields = list(args.fields)

    if "mean" not in fields:
        fields.insert(0, "mean")

    print(
        "Requested source rasters:",
        len(PROPERTIES) * len(DEPTHS) * len(fields),
        flush=True,
    )

    # --------------------------------------------------------
    # SOURCE SOILGRIDS
    # --------------------------------------------------------

    for prop in PROPERTIES:
        for depth in DEPTHS:
            for field in fields:
                name = f"{prop}_{depth}_{field}"

                source = (
                    args.source
                    / prop
                    / f"{name}.tif"
                )

                destination = (
                    raw_dir
                    / prop
                    / f"{name}.tif"
                )

                status = create_clip(
                    source,
                    destination,
                    clip_geometry,
                )

                result = {
                    "layer": name,
                    "status": status,
                }

                for mode, gdf in geometries.items():
                    count = add_statistics(
                        rows[mode],
                        gdf,
                        destination,
                        name,
                    )

                    result[f"{mode}_valid_hrus"] = count

                report.append(result)

                print(
                    f"{name}: {status}",
                    flush=True,
                )

    # --------------------------------------------------------
    # DERIVED SOIL PROPERTIES
    # --------------------------------------------------------

    for depth in DEPTHS:
        sand_file = (
            raw_dir
            / "sand"
            / f"sand_{depth}_mean.tif"
        )

        clay_file = (
            raw_dir
            / "clay"
            / f"clay_{depth}_mean.tif"
        )

        derived = derive_properties(
            sand_file,
            clay_file,
            derived_dir,
            depth,
        )

        for name in ("porosity", "conductivity"):
            attribute = f"{name}_{depth}_mean"
            destination = derived.get(name)

            result = {
                "layer": attribute,
                "status": (
                    "available"
                    if destination is not None
                    else "missing_input_or_valid_pixels"
                ),
            }

            for mode, gdf in geometries.items():
                count = (
                    add_statistics(
                        rows[mode],
                        gdf,
                        destination,
                        attribute,
                        harmonic=(name == "conductivity"),
                    )
                    if destination is not None
                    else 0
                )

                if destination is None:
                    for row in rows[mode]:
                        for stat in (
                            "min", "mean", "max", "std"
                        ):
                            row[f"{attribute}_{stat}"] = np.nan

                        row[f"{attribute}_valid_pixels"] = 0

                        if name == "conductivity":
                            row[
                                f"{attribute}_harmonic_mean"
                            ] = np.nan

                result[f"{mode}_valid_hrus"] = count

            report.append(result)

            print(
                f"{attribute}: {result['status']}",
                flush=True,
            )

    # --------------------------------------------------------
    # OUTPUTS
    # --------------------------------------------------------

    if "distributed" in rows:
        write_csv(
            root
            / "attributes/soilgrids"
            / "hru_soilgrids_attributes.csv",
            rows["distributed"],
        )

    if "lumped" in rows:
        write_csv(
            root
            / "lumped/attributes/soilgrids"
            / "lumped_soilgrids_attributes.csv",
            rows["lumped"],
        )

    write_csv(
        root
        / "attributes/soilgrids"
        / "soilgrids_processing_report.csv",
        report,
    )

    incomplete = [
        item
        for item in report
        if any(
            item[f"{mode}_valid_hrus"] < len(gdf)
            for mode, gdf in geometries.items()
        )
    ]

    print()
    print("=" * 65)
    print("SOILGRIDS PROCESSING COMPLETED")
    print("=" * 65)

    print(f"Domain: {domain}")
    print(f"Mode: {args.mode}")
    print(f"Layers assessed: {len(report)}")
    print(
        f"Layers with incomplete coverage: {len(incomplete)}"
    )

    for item in incomplete:
        coverage = ", ".join(
            f"{mode}: "
            f"{item[f'{mode}_valid_hrus']}/{len(gdf)}"
            for mode, gdf in geometries.items()
        )

        print(
            f"  {item['layer']}: "
            f"{item['status']} ({coverage})"
        )

    print()
    print(
        "Report:",
        root
        / "attributes/soilgrids"
        / "soilgrids_processing_report.csv",
    )

    print(
        "Existing SUMMA and soil-class files unchanged."
    )


if __name__ == "__main__":
    main()