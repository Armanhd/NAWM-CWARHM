
#!/usr/bin/env python3
"""Generate slope and aspect from an existing CWARHM MERIT DEM.

Usage:
    python 1_generate_slope_aspect.py CONTROL_FILE [--force]

The existing DEM is never modified.
"""

import argparse
import math
import os
import tempfile
from pathlib import Path

import geopandas as gpd
from osgeo import gdal, osr


gdal.UseExceptions()

NODATA = -9999.0


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
                raise ValueError(f"Empty control setting: {key}")

            return value

    if default is not None:
        return default

    raise KeyError(f"Missing control setting: {key}")


def resolve(control, root, key, suffix):
    value = control_value(control, key, "default")

    if value == "default":
        return root / suffix

    return Path(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("control_file", type=Path)
    parser.add_argument("--force", action="store_true")

    args = parser.parse_args()

    control = args.control_file.resolve(strict=True)

    domain = control_value(control, "domain_name")

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

    if not dem.is_file():
        raise FileNotFoundError(f"DEM not found: {dem}")

    catchment = (
        root
        / "shapefiles/catchment"
        / f"{domain}_distributed_basin.shp"
    )

    if not catchment.is_file():
        raise FileNotFoundError(
            f"Catchment shapefile not found: {catchment}"
        )

    gdf = gpd.read_file(catchment)

    if gdf.empty or gdf.crs is None:
        raise ValueError("Invalid catchment shapefile")

    centroid = gdf.to_crs("EPSG:4326").unary_union.centroid

    zone = max(
        1,
        min(
            60,
            int(math.floor((centroid.x + 180) / 6) + 1),
        ),
    )

    epsg = (
        32600 if centroid.y >= 0 else 32700
    ) + zone

    out_dir = root / "parameters/terrain"
    out_dir.mkdir(parents=True, exist_ok=True)

    slope = out_dir / "slope_degrees.tif"
    aspect = out_dir / "aspect_degrees.tif"

    if slope.exists() and aspect.exists() and not args.force:
        for output in (slope, aspect):
            if gdal.Open(str(output)) is None:
                raise RuntimeError(
                    f"Cannot read existing raster: {output}"
                )

        print("Existing terrain rasters found. Skipping.")
        return

    if slope.exists() != aspect.exists() and not args.force:
        raise RuntimeError(
            "Only one terrain map exists. Inspect outputs "
            "before using --force."
        )

    src = gdal.Open(str(dem), gdal.GA_ReadOnly)

    if src.RasterCount != 1:
        raise ValueError("Expected a single-band DEM")

    band = src.GetRasterBand(1)
    gt = src.GetGeoTransform()

    if not src.GetProjection():
        raise ValueError("DEM is missing a CRS")

    extent = (
        gt[0],
        gt[3] + src.RasterYSize * gt[5],
        gt[0] + src.RasterXSize * gt[1],
        gt[3],
    )

    src_srs = osr.SpatialReference(wkt=src.GetProjection())
    source_crs = src_srs.ExportToWkt()

    width = src.RasterXSize
    height = src.RasterYSize
    src_nodata = band.GetNoDataValue()

    src = None

    with tempfile.TemporaryDirectory(
        prefix="nwam_terrain_",
        dir=str(out_dir),
    ) as temp_dir:

        work = Path(temp_dir)

        metric = work / "metric_dem.tif"
        metric_slope = work / "metric_slope.tif"
        metric_aspect = work / "metric_aspect.tif"

        warp_options = {
            "format": "GTiff",
            "dstSRS": f"EPSG:{epsg}",
            "resampleAlg": "bilinear",
            "dstNodata": NODATA,
            "multithread": True,
            "creationOptions": [
                "TILED=YES",
                "COMPRESS=DEFLATE",
            ],
        }

        if src_nodata is not None:
            warp_options["srcNodata"] = src_nodata

        ds = gdal.Warp(
            str(metric),
            str(dem),
            options=gdal.WarpOptions(**warp_options),
        )

        if ds is None:
            raise RuntimeError("DEM reprojection failed")

        ds = None

        for kind, destination in (
            ("slope", metric_slope),
            ("aspect", metric_aspect),
        ):

            ds = gdal.DEMProcessing(
                str(destination),
                str(metric),
                kind,
                options=gdal.DEMProcessingOptions(
                    format="GTiff",
                    computeEdges=True,
                    creationOptions=[
                        "COMPRESS=DEFLATE",
                        "TILED=YES",
                    ],
                ),
            )

            if ds is None:
                raise RuntimeError(
                    f"GDAL {kind} calculation failed"
                )

            ds = None

        for intermediate, output, interpolation in (
            (metric_slope, slope, "bilinear"),
            (metric_aspect, aspect, "near"),
        ):

            temp_output = work / output.name

            ds = gdal.Warp(
                str(temp_output),
                str(intermediate),
                options=gdal.WarpOptions(
                    format="GTiff",
                    dstSRS=source_crs,
                    outputBounds=extent,
                    width=width,
                    height=height,
                    resampleAlg=interpolation,
                    srcNodata=NODATA,
                    dstNodata=NODATA,
                    multithread=True,
                    creationOptions=[
                        "COMPRESS=DEFLATE",
                        "TILED=YES",
                        "BIGTIFF=IF_SAFER",
                    ],
                ),
            )

            if ds is None:
                raise RuntimeError(
                    f"Failed to create {output}"
                )

            ds = None

            check = gdal.Open(
                str(temp_output),
                gdal.GA_ReadOnly,
            )

            if (
                check is None
                or check.RasterXSize != width
                or check.RasterYSize != height
            ):
                raise RuntimeError(
                    f"Raster validation failed: {temp_output}"
                )

            check = None

            os.replace(temp_output, output)

    print(f"Domain: {domain}")
    print(f"Metric projection: EPSG:{epsg}")
    print(f"Original DEM (unchanged): {dem}")
    print(f"Slope: {slope}")
    print(f"Aspect: {aspect}")


if __name__ == "__main__":
    main()
