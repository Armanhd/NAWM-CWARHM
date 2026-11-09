#!/usr/bin/env python3
"""
CWARHM / NWAM - CAMELS-SPAT-compatible LAI attributes.

Original CAMELS-SPAT methodology:
    attributes_from_lai()
    calculate_monthly_lai_maps()

For each calendar month:
    1. Use a monthly MODIS LAI climatology raster.
    2. Retain valid stored LAI values between 0 and 100.
    3. Apply the MODIS scale factor (0.1).
    4. Calculate spatial mean and standard deviation using:
         zonal_stats(..., stats=["mean", "std"],
                     all_touched=True)

Original attribute names:
    lai_mean_month_01 ... lai_mean_month_12
    lai_std_month_01  ... lai_std_month_12

Units:
    m2/m2 (dimensionless LAI)

Source:
    Existing water-masked MODIS monthly climatology, 2013-2023.

Important distinction:
    Original CAMELS-SPAT computes monthly climatologies from its
    available raw 8-day MODIS observations. Here, the existing
    2013-2023 monthly climatology rasters are used directly.

    Therefore, the spatial aggregation and attribute definitions
    follow CAMELS-SPAT, but the temporal source period may differ.

Both distributed and lumped configurations are supported.

No original source raster, shapefile, or SUMMA file is modified.
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


# ============================================================
# Source configuration
# ============================================================

SOURCE_ROOT = None

MONTHS = range(1, 13)

RAW_MIN = 0.0
RAW_MAX = 100.0

OUTPUT_NODATA = -9999.0

TEMPORAL_PERIOD = "2013-2023"


# ============================================================
# Control file
# ============================================================

def read_control(path, key):
    with open(path) as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            if "|" not in line:
                continue

            left, right = line.split("|", 1)

            if left.strip() == key:
                value = right.split("#", 1)[0].strip()

                if value:
                    return value

    raise KeyError(
        f"Setting '{key}' not found in {path}"
    )


# ============================================================
# Read HRUs and validate SUMMA mapping
# ============================================================

def load_hrus(shapefile, summa_file):

    if not shapefile.is_file():
        raise FileNotFoundError(shapefile)

    if not summa_file.is_file():
        raise FileNotFoundError(summa_file)

    gdf = gpd.read_file(shapefile)

    if gdf.empty:
        raise RuntimeError(
            f"No HRUs in shapefile: {shapefile}"
        )

    if gdf.crs is None:
        raise RuntimeError(
            f"Missing CRS: {shapefile}"
        )

    required = [
        "HRU_ID",
        "GRU_ID",
        "HRU_area",
    ]

    for col in required:
        if col not in gdf.columns:
            raise RuntimeError(
                f"Missing field '{col}' in {shapefile}"
            )

    for col in ["HRU_ID", "GRU_ID"]:
        values = pd.to_numeric(
            gdf[col], errors="raise"
        ).to_numpy(dtype=float)

        if (
            not np.isfinite(values).all()
            or not np.equal(
                values, np.rint(values)
            ).all()
        ):
            raise RuntimeError(
                f"Invalid identifiers in {col}"
            )

        gdf[col] = values.astype(np.int64)

    gdf["HRU_area"] = pd.to_numeric(
        gdf["HRU_area"],
        errors="raise",
    )

    if (
        not np.isfinite(gdf["HRU_area"]).all()
        or (gdf["HRU_area"] <= 0).any()
    ):
        raise RuntimeError(
            "Invalid HRU areas"
        )

    if gdf["HRU_ID"].duplicated().any():
        raise RuntimeError(
            "Duplicate HRU_ID values"
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
        raise RuntimeError(
            f"Invalid HRU geometry: {shapefile}"
        )

    with xr.open_dataset(summa_file) as ds:

        hru_ids = np.asarray(
            ds["hruId"].values,
            dtype=np.int64,
        ).ravel()

        gru_ids = np.asarray(
            ds["hru2gruId"].values,
            dtype=np.int64,
        ).ravel()

    if (
        len(gdf) != len(hru_ids)
        or set(gdf["HRU_ID"]) != set(hru_ids)
    ):
        raise RuntimeError(
            "Shapefile HRU_ID values do not match SUMMA"
        )

    # Use SUMMA order, not shapefile feature order.
    gdf = (
        gdf.set_index("HRU_ID", drop=False)
        .loc[hru_ids]
        .copy()
        .reset_index(drop=True)
    )

    if not np.array_equal(
        gdf["GRU_ID"].to_numpy(),
        gru_ids,
    ):
        raise RuntimeError(
            "Shapefile GRU_ID values do not match SUMMA"
        )

    return gdf


# ============================================================
# Atomic CSV writer
# ============================================================

def write_csv(destination, records):

    if not records:
        raise RuntimeError(
            f"No records for {destination}"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temporary = tempfile.mkstemp(
        dir=destination.parent,
        prefix=destination.stem + "_",
        suffix=".tmp.csv",
    )

    os.close(fd)

    try:
        with open(
            temporary, "w", newline=""
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=list(records[0].keys()),
            )

            writer.writeheader()
            writer.writerows(records)

        os.replace(
            temporary,
            destination,
        )

    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


# ============================================================
# Source raster naming
# ============================================================

def monthly_source(directory, month):

    return directory / (
        f"2013_2023_{month:02d}_"
        "MOD_Grid_MOD15A2H_Lai_500m.tif"
    )


# ============================================================
# Create basin-clipped, scaled monthly LAI raster
# ============================================================

def process_monthly_raster(
    source,
    destination,
    basin,
    force=False,
):

    if destination.exists() and not force:

        with rasterio.open(destination) as ds:

            if (
                ds.count != 1
                or ds.crs is None
                or ds.nodata != OUTPUT_NODATA
                or not np.isclose(
                    ds.scales[0], 1.0
                )
            ):
                raise RuntimeError(
                    "Invalid existing clipped raster: "
                    f"{destination}"
                )

        return "reused"

    with rasterio.open(source) as src:

        if src.count != 1:
            raise RuntimeError(
                f"Expected one band: {source}"
            )

        if src.crs is None:
            raise RuntimeError(
                f"Missing source CRS: {source}"
            )

        scale = src.scales[0]
        offset = src.offsets[0]

        if not np.isclose(scale, 0.1):
            raise RuntimeError(
                f"Unexpected LAI scale {scale}: {source}"
            )

        if not np.isclose(offset, 0.0):
            raise RuntimeError(
                f"Unexpected LAI offset {offset}: {source}"
            )

        # Reproject the basin polygon into raster CRS.
        basin_projected = basin.to_crs(src.crs)

        geometry = (
            basin_projected.geometry.union_all()
        )

        clipped, transform = mask(
            src,
            [geometry.__geo_interface__],
            crop=True,
            all_touched=True,
            filled=False,
        )

        band = clipped[0]

        raw = band.data

        # Exclude:
        #   - pixels outside basin
        #   - nonfinite values
        #   - raw LAI < 0
        #   - raw LAI > 100
        #
        # In particular, 249-255 are excluded.
        valid = (
            ~np.ma.getmaskarray(band)
            & np.isfinite(raw)
            & (raw >= RAW_MIN)
            & (raw <= RAW_MAX)
        )

        output = np.full(
            raw.shape,
            OUTPUT_NODATA,
            dtype=np.float32,
        )

        output[valid] = (
            raw[valid] * scale + offset
        )

        if not valid.any():
            print(
                f"WARNING: No valid LAI pixels in basin: {source}. "
                "Saving an all-NoData raster.",
                flush=True,
            )

        profile = src.profile.copy()

        # Prevent inherited GeoTIFF block sizes from
        # causing errors for small basin rasters.
        for key in [
            "blockxsize",
            "blockysize",
            "tiled",
            "compress",
            "interleave",
        ]:
            profile.pop(key, None)

        profile.update(
            driver="GTiff",
            count=1,
            width=output.shape[1],
            height=output.shape[0],
            transform=transform,
            dtype="float32",
            nodata=OUTPUT_NODATA,
            compress="deflate",
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temporary = tempfile.mkstemp(
        dir=destination.parent,
        prefix=destination.stem + "_",
        suffix=".tmp.tif",
    )

    os.close(fd)

    try:
        with rasterio.open(
            temporary, "w", **profile
        ) as dst:

            dst.write(output, 1)

            # Values are already in physical LAI units.
            # Do not apply the scale again downstream.
            dst.scales = (1.0,)
            dst.offsets = (0.0,)

            dst.update_tags(
                1,
                source_period=TEMPORAL_PERIOD,
                source_product="MOD15A2H",
                original_scale=scale,
                raw_valid_min=RAW_MIN,
                raw_valid_max=RAW_MAX,
                units="m2/m2",
                aggregation="monthly_climatology",
            )

        os.replace(
            temporary,
            destination,
        )

    finally:
        if os.path.exists(temporary):
            os.remove(temporary)

    return "created"


# ============================================================
# Calculate monthly spatial LAI attributes
# ============================================================

def calculate_monthly_attributes(
    gdf,
    raster,
    month,
    attribute_rows,
    coverage_rows,
):

    with rasterio.open(raster) as src:

        geometries = gdf.to_crs(src.crs).geometry

    # Original CAMELS-SPAT spatial method.
    statistics = zonal_stats(
        geometries,
        str(raster),
        stats=["count", "mean", "std"],
        all_touched=True,
    )

    if len(statistics) != len(gdf):
        raise RuntimeError(
            "Unexpected number of zonal-statistics records"
        )

    valid_hrus = 0

    for attr, coverage, result in zip(
        attribute_rows,
        coverage_rows,
        statistics,
    ):

        count = int(
            result.get("count") or 0
        )

        mean = result.get("mean")
        std = result.get("std")

        mean = (
            float(mean)
            if mean is not None
            else np.nan
        )

        std = (
            float(std)
            if std is not None
            else np.nan
        )

        # Exact original CAMELS-SPAT names.
        attr[
            f"lai_mean_month_{month:02d}"
        ] = mean

        attr[
            f"lai_std_month_{month:02d}"
        ] = std

        coverage[
            f"month_{month:02d}_valid_pixels"
        ] = count

        coverage[
            f"month_{month:02d}_has_data"
        ] = bool(
            count > 0
            and np.isfinite(mean)
            and np.isfinite(std)
        )

        if coverage[
            f"month_{month:02d}_has_data"
        ]:
            valid_hrus += 1

    return valid_hrus


# ============================================================
# Main
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
        "--mode",
        choices=[
            "both",
            "distributed",
            "lumped",
        ],
        default="both",
    )

    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Directory containing 12 monthly LAI rasters",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Recreate existing clipped rasters",
    )

    args = parser.parse_args()

    control = args.control_file.resolve(
        strict=True
    )

    domain_name = read_control(
        control,
        "domain_name",
    )

    root_path = Path(
        read_control(
            control,
            "root_path",
        )
    )

    domain_root = (
        root_path
        / f"domain_{domain_name}"
    )

    # --------------------------------------------------------
    # Load distributed and/or lumped HRUs
    # --------------------------------------------------------

    configurations = {}

    if args.mode in ("both", "distributed"):

        shapefile = (
            domain_root / "shapefiles/catchment"
            / f"{domain_name}_distributed_basin.shp"
        )

        if not shapefile.is_file():
            shapefile = (
                domain_root / "shapefiles/catchment"
                / read_control(control, "catchment_shp_name")
            )

        configurations["distributed"] = load_hrus(
            shapefile,
            domain_root / "settings/SUMMA/attributes.nc",
        )

    if args.mode in [
        "both",
        "lumped",
    ]:

        configurations[
            "lumped"
        ] = load_hrus(
            domain_root
            / "lumped/shapefiles/catchment"
            / f"{domain_name}_lumped_basin.shp",

            domain_root
            / "lumped/settings/SUMMA/attributes.nc",
        )

    # --------------------------------------------------------
    # Create common basin geometry
    # --------------------------------------------------------

    polygons = []

    for gdf in configurations.values():

        projected = gdf.to_crs(
            "EPSG:4326"
        )

        polygons.append(
            projected.geometry.union_all()
        )

    basin_union = gpd.GeoSeries(
        polygons,
        crs="EPSG:4326",
    ).union_all()

    basin = gpd.GeoDataFrame(
        geometry=[basin_union],
        crs="EPSG:4326",
    )

    # --------------------------------------------------------
    # Initialize output records
    # --------------------------------------------------------

    attribute_rows = {}
    coverage_rows = {}

    for mode, gdf in configurations.items():

        attribute_rows[mode] = []
        coverage_rows[mode] = []

        for _, feature in gdf.iterrows():

            hru_id = int(
                feature["HRU_ID"]
            )

            gru_id = int(
                feature["GRU_ID"]
            )

            area = float(
                feature["HRU_area"]
            )

            attribute_rows[mode].append({
                "hruId": hru_id,
                "gruId": gru_id,
                "HRUarea_m2": area,
            })

            coverage_rows[mode].append({
                "hruId": hru_id,
                "gruId": gru_id,
            })

    print("=" * 65)
    print("CAMELS-SPAT-compatible MODIS LAI attributes")
    print("=" * 65)

    print(f"Domain: {domain_name}")
    print(f"Mode: {args.mode}")
    print(f"Source period: {TEMPORAL_PERIOD}")
    print(f"Source directory: {args.source}")
    print(f"Raw valid range: {RAW_MIN}-{RAW_MAX}")
    print("Scale factor: 0.1")
    print("Zonal statistics: mean, std")
    print("all_touched: True")
    print("=" * 65, flush=True)

    # --------------------------------------------------------
    # Process all 12 months
    # --------------------------------------------------------

    for month in MONTHS:

        source = monthly_source(
            args.source,
            month,
        )

        if not source.is_file():
            raise FileNotFoundError(
                source
            )

        destination = (
            domain_root
            / "parameters/lai"
            / f"lai_month_{month:02d}.tif"
        )

        status = process_monthly_raster(
            source,
            destination,
            basin,
            force=args.force,
        )

        counts = []

        for mode, gdf in configurations.items():

            valid_hrus = (
                calculate_monthly_attributes(
                    gdf,
                    destination,
                    month,
                    attribute_rows[mode],
                    coverage_rows[mode],
                )
            )

            counts.append(
                f"{mode}: "
                f"{valid_hrus}/{len(gdf)}"
            )

        print(
            f"Month {month:02d}: "
            f"{status}; "
            + ", ".join(counts),
            flush=True,
        )

    # --------------------------------------------------------
    # Validate all attributes before writing CSVs
    # --------------------------------------------------------

    expected_fields = [
        field
        for month in MONTHS
        for field in (
            f"lai_mean_month_{month:02d}",
            f"lai_std_month_{month:02d}",
        )
    ]

    for mode, rows in attribute_rows.items():

        for row in rows:

            for field in expected_fields:

                if field not in row:
                    raise RuntimeError(
                        f"Missing attribute: {field}"
                    )

                if not np.isfinite(row[field]):
                    print(
                        f"WARNING: missing {field} for "
                        f"HRU {row['hruId']} ({mode})",
                        flush=True,
                    )

    # --------------------------------------------------------
    # Write distributed and lumped results
    # --------------------------------------------------------

    for mode, rows in attribute_rows.items():

        if mode == "distributed":

            output_dir = (
                domain_root
                / "attributes/lai"
            )

            output_file = (
                output_dir
                / "hru_lai_attributes.csv"
            )

        else:

            output_dir = (
                domain_root
                / "lumped/attributes/lai"
            )

            output_file = (
                output_dir
                / "lumped_lai_attributes.csv"
            )

        report_file = (
            output_dir
            / "lai_coverage_report.csv"
        )

        write_csv(
            output_file,
            rows,
        )

        write_csv(
            report_file,
            coverage_rows[mode],
        )

        print()
        print(
            f"{mode}: {len(rows)} HRUs processed"
        )

        print(
            f"LAI attributes: {output_file}"
        )

        print(
            f"Coverage report: {report_file}"
        )

    print()
    print("=" * 65)
    print("LAI processing completed successfully.")
    print("24 CAMELS-SPAT-compatible attributes per HRU.")
    print("Original source and SUMMA files unchanged.")
    print("=" * 65)


if __name__ == "__main__":
    main()
