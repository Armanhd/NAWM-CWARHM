
#!/usr/bin/env python3
"""Calculate HRU-level and lumped terrain attributes.

Usage:
    python 2_calculate_terrain_attributes.py CONTROL_FILE

Requires the distributed control file.
SUMMA attributes.nc is read for HRU/GRU validation only.
"""

import argparse
import csv
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import xarray as xr

from rasterstats import zonal_stats
from scipy.stats import circmean, circstd


def control_value(path, key, default=None):
    for line in path.read_text().splitlines():

        if not line.strip() or line.lstrip().startswith("#"):
            continue

        if "|" not in line:
            continue

        k, v = line.split("|", 1)

        if k.strip() == key:
            value = v.split("#", 1)[0].strip()

            if not value:
                raise ValueError(
                    f"Empty control setting: {key}"
                )

            return value

    if default is not None:
        return default

    raise KeyError(f"Missing control setting: {key}")


def resolve(control, root, key, suffix):
    value = control_value(control, key, "default")

    if value == "default":
        return root / suffix

    return Path(value)


def aspect_mean(data):
    values = np.ma.array(data).compressed()

    values = values[
        np.isfinite(values)
        & (values >= 0)
        & (values <= 360)
    ]

    if values.size == 0:
        return np.nan

    return float(
        circmean(values, high=360, low=0)
    )


def aspect_std(data):
    values = np.ma.array(data).compressed()

    values = values[
        np.isfinite(values)
        & (values >= 0)
        & (values <= 360)
    ]

    if values.size == 0:
        return np.nan

    return float(
        circstd(values, high=360, low=0)
    )


def summarize(gdf, raster, name, is_aspect=False):

    with rasterio.open(raster) as src:

        if src.crs is None:
            raise ValueError(
                f"Raster has no CRS: {raster}"
            )

        shapes = gdf.to_crs(src.crs)

        if is_aspect:

            values = zonal_stats(
                shapes.geometry,
                str(raster),
                stats=["count", "min", "max"],
                add_stats={
                    "circular_mean": aspect_mean,
                    "circular_std": aspect_std,
                },
                all_touched=True,
            )

        else:

            values = zonal_stats(
                shapes.geometry,
                str(raster),
                stats=[
                    "count",
                    "min",
                    "mean",
                    "max",
                    "std",
                ],
                all_touched=True,
            )

    results = []

    for i, value in enumerate(values):

        if not value["count"]:
            print(
                f"WARNING: No valid {name} pixels "
                f"for polygon {i}",
                flush=True,
            )
            value = dict(value)
            value.update({
                "min": np.nan,
                "max": np.nan,
                "mean": np.nan,
                "std": np.nan,
                "circular_mean": np.nan,
                "circular_std": np.nan,
                "count": 0,
            })

        record = {
            f"{name}_min": value["min"],
            f"{name}_max": value["max"],
        }

        if is_aspect:

            record[f"{name}_mean"] = value[
                "circular_mean"
            ]

            record[f"{name}_std"] = value[
                "circular_std"
            ]

        else:

            record[f"{name}_mean"] = value["mean"]
            record[f"{name}_std"] = value["std"]

        record[f"{name}_valid_pixels"] = value[
            "count"
        ]

        results.append(record)

    return results


def read_polygon(path, mode, hru_field, gru_field):

    if not path.is_file():
        raise FileNotFoundError(
            f"{mode} shapefile missing: {path}"
        )

    gdf = gpd.read_file(path)

    if gdf.empty or gdf.crs is None:
        raise ValueError(
            f"Invalid {mode} catchment: {path}"
        )

    for field in (hru_field, gru_field):

        if field not in gdf.columns:
            raise ValueError(
                f"Missing {field} in {path}"
            )

        if gdf[field].isna().any():
            raise ValueError(
                f"Null IDs in {field}: {path}"
            )

        numbers = np.asarray(
            gdf[field],
            dtype=np.float64,
        )

        if (
            not np.isfinite(numbers).all()
            or not np.equal(
                numbers,
                np.rint(numbers),
            ).all()
        ):
            raise ValueError(
                f"{field} must contain integer IDs"
            )

        gdf[field] = numbers.astype(np.int64)

    if gdf[hru_field].duplicated().any():
        raise ValueError(
            f"Duplicate HRU IDs in {path}"
        )

    return gdf


def ordered_by_summa(
    gdf,
    base,
    hru_field,
    gru_field,
):

    attributes = (
        base
        / "settings/SUMMA/attributes.nc"
    )

    if not attributes.exists():
        raise FileNotFoundError(
            f"SUMMA attributes missing: {attributes}"
        )

    with xr.open_dataset(attributes) as ds:

        hru = np.asarray(
            ds["hruId"].values,
            dtype=np.int64,
        )

        gru = np.asarray(
            ds["hru2gruId"].values,
            dtype=np.int64,
        )

    if (
        set(hru) != set(gdf[hru_field].astype(int))
        or len(hru) != len(gdf)
    ):
        raise ValueError(
            f"HRU IDs disagree with SUMMA: {attributes}"
        )

    ordered = (
        gdf.set_index(hru_field, drop=False)
        .loc[hru]
        .copy()
        .reset_index(drop=True)
    )

    if not np.array_equal(
        gru,
        ordered[gru_field].to_numpy(dtype=np.int64),
    ):
        raise ValueError(
            f"GRU assignments disagree with SUMMA: {attributes}"
        )

    return ordered


def export(
    root,
    mode,
    gdf,
    hru_field,
    gru_field,
    dem,
    slope,
    aspect,
):

    statistics = [
        summarize(gdf, dem, "elev"),
        summarize(gdf, slope, "slope"),
        summarize(
            gdf,
            aspect,
            "aspect",
            is_aspect=True,
        ),
    ]

    rows = []

    for i, (_, polygon) in enumerate(gdf.iterrows()):

        record = {
            "hruId": int(polygon[hru_field]),
            "gruId": int(polygon[gru_field]),
        }

        if "HRU_area" in polygon:
            record["HRUarea_m2"] = float(
                polygon["HRU_area"]
            )

        for values in statistics:
            record.update(values[i])

        rows.append(record)

    if mode == "distributed":

        folder = root / "attributes/terrain"
        name = "hru_terrain_attributes.csv"

    else:

        folder = root / "lumped/attributes/terrain"
        name = "lumped_terrain_attributes.csv"

    folder.mkdir(parents=True, exist_ok=True)

    output = folder / name

    with output.open("w", newline="") as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0]),
        )

        writer.writeheader()
        writer.writerows(rows)

    print(
        f"{mode}: {len(rows)} HRUs; saved {output}"
    )

    return rows


def main():

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "control_file",
        type=Path,
        help="Distributed CWARHM control file",
    )

    parser.add_argument(
        "--mode",
        choices=("both", "distributed", "lumped"),
        default="both",
    )

    args = parser.parse_args()

    control = args.control_file.resolve(strict=True)

    domain = control_value(
        control,
        "domain_name",
    )

    root = (
        Path(control_value(control, "root_path"))
        / f"domain_{domain}"
    )

    dem_dir = resolve(
        control,
        root,
        "parameter_dem_tif_path",
        "parameters/dem/5_elevation",
    )

    dem = (
        dem_dir
        / control_value(control, "parameter_dem_tif_name")
    )

    slope = (
        root / "parameters/terrain/slope_degrees.tif"
    )

    aspect = (
        root / "parameters/terrain/aspect_degrees.tif"
    )

    for raster in (dem, slope, aspect):

        if not raster.is_file():
            raise FileNotFoundError(
                f"Input raster missing: {raster}"
            )

    hru_field = control_value(
        control,
        "catchment_shp_hruid",
    )

    gru_field = control_value(
        control,
        "catchment_shp_gruid",
    )

    dist_shp = (
        root / "shapefiles/catchment"
        / f"{domain}_distributed_basin.shp"
    )

    if not dist_shp.is_file():
        dist_shp = (
            root / "shapefiles/catchment"
            / control_value(control, "catchment_shp_name")
        )

    lump_shp = (
        root / "lumped/shapefiles/catchment"
        / f"{domain}_lumped_basin.shp"
    )

    if args.mode in ("both", "distributed"):
        distributed = read_polygon(
            dist_shp, "distributed", hru_field, gru_field
        )

        distributed = ordered_by_summa(
            distributed, root, hru_field, gru_field
        )

        export(
            root, "distributed", distributed,
            hru_field, gru_field,
            dem, slope, aspect,
        )

    if args.mode in ("both", "lumped"):
        lumped = read_polygon(
            lump_shp, "lumped", hru_field, gru_field
        )

        if len(lumped) != 1:
            raise ValueError(
                f"Expected 1 lumped HRU, found {len(lumped)}"
            )

        lumped = ordered_by_summa(
            lumped, root / "lumped",
            hru_field, gru_field,
        )

        export(
            root, "lumped", lumped,
            hru_field, gru_field,
            dem, slope, aspect,
        )

    print(
        "Finished. Terrain CSVs created; "
        "SUMMA files unchanged."
    )


if __name__ == "__main__":
    main()
