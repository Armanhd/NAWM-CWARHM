#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Convert concatenated LUMPED SUMMA forcing from UTC to Local Standard Time.

This follows the CAMELS-SPAT convention:

    dv_flow_obs_timezone

is read from CAMELS-SPAT metadata and used as the basin's fixed
Local Standard Time (LST).

IMPORTANT
---------
This script:

- processes LUMPED forcing only;
- reads root_path and domain_name from the lumped control file;
- reads the CAMELS-SPAT metadata location from
  camels_spat_metadata_path.txt;
- reads dv_flow_obs_timezone from CAMELS-SPAT metadata;
- applies a fixed UTC -> LST offset;
- does NOT apply daylight-saving-time changes;
- does NOT alter meteorological forcing values;
- does NOT alter HRU structure;
- writes a NEW NetCDF file;
- does NOT modify the original UTC concatenated forcing.

Expected input:

<root_path>/domain_<DOMAIN>/lumped/forcing/5_SUMMA_input_concat/
NWAM_SUMMA_forcing_195001_201912.nc

Expected output:

<root_path>/domain_<DOMAIN>/lumped/forcing/6_SUMMA_input_LST/
NWAM_SUMMA_forcing_195001_201912_LST.nc


Example
-------
python 1_convert_concat_utc_to_lst_lumped.py \
    --control-file \
    /path/to/control_CAN_05BB001_lumped.txt
"""

from pathlib import Path
from datetime import datetime
from shutil import copy2
import argparse

import numpy as np
import pandas as pd
from netCDF4 import Dataset, num2date


# ============================================================
# SCRIPT DIRECTORY
# ============================================================

SCRIPT_DIR = Path(
    __file__
).resolve().parent


# ============================================================
# METADATA PATH FILE
# ============================================================

METADATA_PATH_FILE = (
    SCRIPT_DIR
    / "camels_spat_metadata_path.txt"
)


# ============================================================
# REQUIRED SUMMA VARIABLES
# ============================================================

REQUIRED_VARS = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "pptrate",
    "airtemp",
    "spechum",
    "windspd",
]


# ============================================================
# STANDARD-TIME OFFSETS
# ============================================================
#
# CAMELS-SPAT uses standard-time abbreviations.
#
# Newfoundland Standard Time is half-hour based. CAMELS-SPAT
# converted NST to AST because the forcing is hourly.
#
# We reproduce that same behaviour here.

TIMEZONE_OFFSETS = {
    "HST": -10.0,
    "AKST": -9.0,
    "PST": -8.0,
    "MST": -7.0,
    "CST": -6.0,
    "EST": -5.0,
    "AST": -4.0,
}


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(
    control_file,
    setting,
):
    """
    Read one setting using exact control-key matching.
    """

    with open(control_file) as contents:

        for line in contents:

            stripped = line.strip()

            if (
                not stripped
                or stripped.startswith("#")
                or "|" not in stripped
            ):
                continue

            left, right = stripped.split(
                "|",
                1,
            )

            if left.strip() != setting:
                continue

            value = (
                right
                .split("#", 1)[0]
                .strip()
            )

            if value == "":

                raise ValueError(
                    f"Setting '{setting}' is empty in:\n"
                    f"{control_file}"
                )

            return value

    raise ValueError(
        f"Setting '{setting}' not found in:\n"
        f"{control_file}"
    )


# ============================================================
# METADATA PATH
# ============================================================

def read_metadata_path():
    """
    Read CAMELS-SPAT metadata path from text file.
    """

    if not METADATA_PATH_FILE.is_file():

        raise FileNotFoundError(
            "Metadata path file not found:\n"
            f"{METADATA_PATH_FILE}"
        )

    lines = [
        line.strip()
        for line in METADATA_PATH_FILE.read_text().splitlines()
        if (
            line.strip()
            and not line.strip().startswith("#")
        )
    ]

    if len(lines) != 1:

        raise RuntimeError(
            "camels_spat_metadata_path.txt must contain "
            "exactly one non-comment, non-empty path."
        )

    metadata_file = Path(
        lines[0]
    ).expanduser().resolve()

    if not metadata_file.is_file():

        raise FileNotFoundError(
            "CAMELS-SPAT metadata file not found:\n"
            f"{metadata_file}"
        )

    return metadata_file


# ============================================================
# METADATA TIMEZONE
# ============================================================

def get_basin_timezone(
    metadata_file,
    domain,
):
    """
    Find dv_flow_obs_timezone for DOMAIN.

    DOMAIN is expected to look like:

        CAN_05BB001
        USA_08164300
    """

    if "_" not in domain:

        raise ValueError(
            f"Unexpected domain name:\n{domain}"
        )

    country, station_id = domain.split(
        "_",
        1,
    )

    metadata = pd.read_csv(
        metadata_file,
        dtype=str,
    )

    required_columns = [
        "Country",
        "Station_id",
        "dv_flow_obs_timezone",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in metadata.columns
    ]

    if missing_columns:

        raise RuntimeError(
            "Required CAMELS-SPAT metadata columns "
            "are missing:\n"
            + "\n".join(
                missing_columns
            )
        )

    metadata["Country"] = (
        metadata["Country"]
        .astype(str)
        .str.strip()
    )

    metadata["Station_id"] = (
        metadata["Station_id"]
        .astype(str)
        .str.strip()
    )

    matches = metadata[
        (
            metadata["Country"] == country
        )
        &
        (
            metadata["Station_id"] == station_id
        )
    ]

    if len(matches) == 0:

        raise RuntimeError(
            "Domain was not found in CAMELS-SPAT metadata:\n"
            f"{domain}"
        )

    if len(matches) > 1:

        raise RuntimeError(
            "Multiple CAMELS-SPAT metadata rows found for:\n"
            f"{domain}"
        )

    timezone = (
        matches.iloc[0][
            "dv_flow_obs_timezone"
        ]
    )

    if pd.isna(timezone):

        raise RuntimeError(
            "dv_flow_obs_timezone is missing for:\n"
            f"{domain}"
        )

    timezone = str(
        timezone
    ).strip().upper()

    if timezone in {
        "",
        "NAN",
        "NONE",
        "NA",
    }:

        raise RuntimeError(
            "Invalid dv_flow_obs_timezone for:\n"
            f"{domain}"
        )

    return timezone


# ============================================================
# TIMEZONE OFFSET
# ============================================================

def resolve_timezone(
    metadata_timezone,
):
    """
    Return applied timezone and UTC offset.

    Reproduce CAMELS-SPAT handling of NST:
        NST -> AST
    """

    applied_timezone = (
        metadata_timezone
    )

    if metadata_timezone == "NST":

        print(
            "NST found. Following CAMELS-SPAT convention: "
            "using AST because forcing timestamps are hourly."
        )

        applied_timezone = "AST"

    if applied_timezone not in TIMEZONE_OFFSETS:

        raise RuntimeError(
            "Unsupported standard-time abbreviation:\n"
            f"{metadata_timezone}\n\n"
            "Known whole-hour timezones:\n"
            + ", ".join(
                sorted(
                    TIMEZONE_OFFSETS
                )
            )
        )

    offset_hours = TIMEZONE_OFFSETS[
        applied_timezone
    ]

    return (
        applied_timezone,
        offset_hours,
    )


# ============================================================
# COPY NETCDF
# ============================================================

def copy_netcdf_with_shifted_time(
    input_file,
    output_file,
    offset_hours,
    metadata_timezone,
    applied_timezone,
    domain,
    control_file,
    metadata_file,
):
    """
    Copy complete NetCDF while shifting only numeric time values.
    """

    with Dataset(
        input_file,
        "r",
    ) as src:

        if "time" not in src.variables:

            raise RuntimeError(
                "Input NetCDF has no time variable:\n"
                f"{input_file}"
            )

        if "time" not in src.dimensions:

            raise RuntimeError(
                "Input NetCDF has no time dimension:\n"
                f"{input_file}"
            )

        if "hru" not in src.dimensions:

            raise RuntimeError(
                "Input NetCDF has no hru dimension:\n"
                f"{input_file}"
            )

        if len(
            src.dimensions["hru"]
        ) != 1:

            raise RuntimeError(
                "Lumped forcing must contain exactly one HRU.\n"
                f"Found: {len(src.dimensions['hru'])}\n"
                f"File : {input_file}"
            )

        missing_vars = [
            variable
            for variable in REQUIRED_VARS
            if variable not in src.variables
        ]

        if missing_vars:

            raise RuntimeError(
                "Required SUMMA variables missing:\n"
                + "\n".join(
                    missing_vars
                )
            )

        if "hruId" in src.variables:

            hru_id = np.asarray(
                src.variables[
                    "hruId"
                ][:]
            ).reshape(-1)

            if (
                len(hru_id) != 1
                or int(hru_id[0]) != 1
            ):

                raise RuntimeError(
                    "Unexpected lumped hruId values:\n"
                    f"{hru_id.tolist()}"
                )

        time_var = src.variables[
            "time"
        ]

        if "units" not in time_var.ncattrs():

            raise RuntimeError(
                "Input time variable has no units attribute."
            )

        time_units = time_var.getncattr(
            "units"
        )

        time_calendar = getattr(
            time_var,
            "calendar",
            "standard",
        )

        original_time = np.asarray(
            time_var[:]
        )

        original_dates = num2date(
            original_time,
            units=time_units,
            calendar=time_calendar,
            only_use_cftime_datetimes=True,
        )

        if len(
            original_dates
        ) == 0:

            raise RuntimeError(
                "Input forcing contains zero timesteps."
            )

        # ----------------------------------------------------
        # Verify input UTC forcing is continuous hourly
        # ----------------------------------------------------

        if len(
            original_dates
        ) > 1:

            for i in range(
                len(original_dates) - 1
            ):

                dt = (
                    original_dates[i + 1]
                    - original_dates[i]
                ).total_seconds()

                if dt != 3600:

                    raise RuntimeError(
                        "Input UTC forcing is not continuous hourly.\n"
                        f"Index {i}: "
                        f"{original_dates[i]} -> "
                        f"{original_dates[i + 1]}"
                    )

        # ----------------------------------------------------
        # CAMELS-SPAT approach
        #
        # Because the concatenated file uses hourly numeric
        # time units, shift numeric time coordinate directly.
        # ----------------------------------------------------

        shifted_time = (
            original_time
            + offset_hours
        )

        output_dir = (
            output_file.parent
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with Dataset(
            output_file,
            "w",
            format=src.data_model,
        ) as dst:

            # -----------------------------------------------
            # Dimensions
            # -----------------------------------------------

            for dim_name, dim in (
                src.dimensions.items()
            ):

                if dim.isunlimited():

                    dst.createDimension(
                        dim_name,
                        None,
                    )

                else:

                    dst.createDimension(
                        dim_name,
                        len(dim),
                    )

            # -----------------------------------------------
            # Global attributes
            # -----------------------------------------------

            for attr in src.ncattrs():

                dst.setncattr(
                    attr,
                    src.getncattr(
                        attr
                    ),
                )

            now = datetime.now()

            existing_history = ""

            if "History" in src.ncattrs():

                existing_history = str(
                    src.getncattr(
                        "History"
                    )
                )

            elif "history" in src.ncattrs():

                existing_history = str(
                    src.getncattr(
                        "history"
                    )
                )

            history_entry = (
                f" On {now:%Y-%m-%d %H:%M:%S}: "
                f"converted lumped concatenated forcing "
                f"from UTC to {applied_timezone} "
                f"using fixed offset {offset_hours:+g} hours "
                f"from CAMELS-SPAT dv_flow_obs_timezone."
            )

            dst.setncattr(
                "History",
                (
                    existing_history
                    + history_entry
                ).strip(),
            )

            dst.setncattr(
                "time_zone",
                applied_timezone,
            )

            dst.setncattr(
                "metadata_time_zone",
                metadata_timezone,
            )

            dst.setncattr(
                "utc_to_lst_offset_hours",
                float(offset_hours),
            )

            dst.setncattr(
                "time_zone_source",
                (
                    "CAMELS-SPAT "
                    "dv_flow_obs_timezone"
                ),
            )

            dst.setncattr(
                "time_zone_processing",
                (
                    "Fixed Local Standard Time offset; "
                    "no daylight-saving-time adjustment."
                ),
            )

            dst.setncattr(
                "forcing_configuration",
                "lumped",
            )

            dst.setncattr(
                "CWARHM_control_file",
                control_file.name,
            )

            dst.setncattr(
                "CAMELS_SPAT_metadata_file",
                str(
                    metadata_file
                ),
            )

            # -----------------------------------------------
            # Variables
            # -----------------------------------------------

            for var_name, src_var in (
                src.variables.items()
            ):

                fill_value = None

                if (
                    "_FillValue"
                    in src_var.ncattrs()
                ):

                    fill_value = (
                        src_var.getncattr(
                            "_FillValue"
                        )
                    )

                create_kwargs = {}

                # Preserve compression where practical.
                filters = {}

                try:
                    filters = src_var.filters()
                except Exception:
                    filters = {}

                if (
                    filters
                    and filters.get(
                        "zlib",
                        False,
                    )
                ):

                    create_kwargs[
                        "zlib"
                    ] = True

                    if (
                        filters.get(
                            "complevel"
                        )
                        is not None
                    ):

                        create_kwargs[
                            "complevel"
                        ] = filters[
                            "complevel"
                        ]

                if fill_value is not None:

                    dst_var = (
                        dst.createVariable(
                            var_name,
                            src_var.datatype,
                            src_var.dimensions,
                            fill_value=fill_value,
                            **create_kwargs,
                        )
                    )

                else:

                    dst_var = (
                        dst.createVariable(
                            var_name,
                            src_var.datatype,
                            src_var.dimensions,
                            **create_kwargs,
                        )
                    )

                for attr in (
                    src_var.ncattrs()
                ):

                    if attr == "_FillValue":
                        continue

                    dst_var.setncattr(
                        attr,
                        src_var.getncattr(
                            attr
                        ),
                    )

                if var_name == "time":

                    dst_var[:] = (
                        shifted_time
                    )

                else:

                    dst_var[:] = (
                        src_var[:]
                    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Convert concatenated lumped SUMMA forcing "
            "from UTC to Local Standard Time."
        )
    )

    parser.add_argument(
        "--control-file",
        required=True,
        help=(
            "Lumped control file, for example "
            "control_CAN_05BB001_lumped.txt"
        ),
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Overwrite existing LST output."
        ),
    )

    args = parser.parse_args()

    control_file = Path(
        args.control_file
    ).resolve()

    if not control_file.is_file():

        raise FileNotFoundError(
            "Control file not found:\n"
            f"{control_file}"
        )

    # ========================================================
    # CONTROL SETTINGS
    # ========================================================

    domain = read_from_control(
        control_file,
        "domain_name",
    )

    root_path = Path(
        read_from_control(
            control_file,
            "root_path",
        )
    ).resolve()

    # ========================================================
    # CAMELS-SPAT METADATA
    # ========================================================

    metadata_file = (
        read_metadata_path()
    )

    metadata_timezone = (
        get_basin_timezone(
            metadata_file,
            domain,
        )
    )

    (
        applied_timezone,
        offset_hours,
    ) = resolve_timezone(
        metadata_timezone
    )

    # ========================================================
    # PATHS
    # ========================================================

    domain_root = (
        root_path
        / f"domain_{domain}"
        / "lumped"
    )

    input_dir = (
        domain_root
        / "forcing"
        / "5_SUMMA_input_concat"
    )

    output_dir = (
        domain_root
        / "forcing"
        / "6_SUMMA_input_LST"
    )

    if not input_dir.is_dir():

        raise FileNotFoundError(
            "Lumped concatenated forcing directory "
            "does not exist:\n"
            f"{input_dir}"
        )

    candidates = sorted(
        input_dir.glob(
            "NWAM_SUMMA_forcing_*.nc"
        )
    )

    candidates = [
        f
        for f in candidates
        if not f.name.endswith(
            "_LST.nc"
        )
    ]

    if len(candidates) == 0:

        raise FileNotFoundError(
            "No lumped concatenated SUMMA forcing "
            "file found in:\n"
            f"{input_dir}"
        )

    if len(candidates) > 1:

        raise RuntimeError(
            "Expected exactly one concatenated "
            "lumped forcing file, but found:\n"
            + "\n".join(
                str(f)
                for f in candidates
            )
        )

    input_file = candidates[
        0
    ]

    output_file = (
        output_dir
        / (
            input_file.stem
            + "_LST.nc"
        )
    )

    # ========================================================
    # REPORT
    # ========================================================

    print()
    print("=" * 78)
    print(
        "LUMPED CONCATENATED FORCING: UTC -> LST"
    )
    print("=" * 78)

    print(
        f"Domain              : {domain}"
    )

    print(
        f"Control file        : {control_file}"
    )

    print(
        f"root_path           : {root_path}"
    )

    print(
        f"CAMELS-SPAT metadata: {metadata_file}"
    )

    print(
        f"Metadata timezone   : {metadata_timezone}"
    )

    print(
        f"Applied timezone    : {applied_timezone}"
    )

    print(
        f"UTC offset          : {offset_hours:+g} hours"
    )

    print(
        f"Input UTC file      : {input_file}"
    )

    print(
        f"Output LST file     : {output_file}"
    )

    print("=" * 78)
    print()

    # ========================================================
    # OUTPUT HANDLING
    # ========================================================

    if output_file.exists():

        if not args.overwrite:

            raise FileExistsError(
                "LST output already exists.\n"
                "Use --overwrite if intentional:\n"
                f"{output_file}"
            )

        output_file.unlink()

    # ========================================================
    # CONVERT
    # ========================================================

    copy_netcdf_with_shifted_time(
        input_file=input_file,
        output_file=output_file,
        offset_hours=offset_hours,
        metadata_timezone=metadata_timezone,
        applied_timezone=applied_timezone,
        domain=domain,
        control_file=control_file,
        metadata_file=metadata_file,
    )

    # ========================================================
    # FINAL VERIFICATION
    # ========================================================

    with Dataset(
        input_file,
        "r",
    ) as utc_ds, Dataset(
        output_file,
        "r",
    ) as lst_ds:

        # ----------------------------------------------------
        # Dimensions
        # ----------------------------------------------------

        if (
            len(
                utc_ds.dimensions["time"]
            )
            != len(
                lst_ds.dimensions["time"]
            )
        ):

            raise RuntimeError(
                "Time dimension changed during "
                "UTC-to-LST conversion."
            )

        if (
            len(
                lst_ds.dimensions["hru"]
            )
            != 1
        ):

            raise RuntimeError(
                "LST output is not one-HRU lumped forcing."
            )

        # ----------------------------------------------------
        # hruId
        # ----------------------------------------------------

        if "hruId" in lst_ds.variables:

            hru_id = np.asarray(
                lst_ds.variables[
                    "hruId"
                ][:]
            ).reshape(-1)

            if (
                len(hru_id) != 1
                or int(hru_id[0]) != 1
            ):

                raise RuntimeError(
                    "LST output hruId is not [1]."
                )

        # ----------------------------------------------------
        # Required variables
        # ----------------------------------------------------

        missing = [
            var
            for var in REQUIRED_VARS
            if var not in lst_ds.variables
        ]

        if missing:

            raise RuntimeError(
                "Required SUMMA variables missing "
                "from LST output:\n"
                + "\n".join(
                    missing
                )
            )

        # ----------------------------------------------------
        # Ensure meteorological data did not change
        # ----------------------------------------------------

        for var in REQUIRED_VARS:

            utc_values = np.asarray(
                utc_ds.variables[
                    var
                ][:]
            )

            lst_values = np.asarray(
                lst_ds.variables[
                    var
                ][:]
            )

            if not np.array_equal(
                utc_values,
                lst_values,
                equal_nan=True,
            ):

                raise RuntimeError(
                    "Meteorological data changed during "
                    "UTC-to-LST conversion:\n"
                    f"{var}"
                )

        # ----------------------------------------------------
        # Decode times
        # ----------------------------------------------------

        utc_time_var = (
            utc_ds.variables["time"]
        )

        lst_time_var = (
            lst_ds.variables["time"]
        )

        utc_dates = num2date(
            utc_time_var[:],
            units=utc_time_var.units,
            calendar=getattr(
                utc_time_var,
                "calendar",
                "standard",
            ),
            only_use_cftime_datetimes=True,
        )

        lst_dates = num2date(
            lst_time_var[:],
            units=lst_time_var.units,
            calendar=getattr(
                lst_time_var,
                "calendar",
                "standard",
            ),
            only_use_cftime_datetimes=True,
        )

        first_offset = (
            lst_dates[0]
            - utc_dates[0]
        ).total_seconds() / 3600.0

        last_offset = (
            lst_dates[-1]
            - utc_dates[-1]
        ).total_seconds() / 3600.0

        if (
            first_offset != offset_hours
            or last_offset != offset_hours
        ):

            raise RuntimeError(
                "UTC-to-LST offset verification failed.\n"
                f"Expected : {offset_hours}\n"
                f"First    : {first_offset}\n"
                f"Last     : {last_offset}"
            )

        # ----------------------------------------------------
        # Continuous hourly LST
        # ----------------------------------------------------

        if len(
            lst_dates
        ) > 1:

            for i in range(
                len(lst_dates) - 1
            ):

                dt = (
                    lst_dates[i + 1]
                    - lst_dates[i]
                ).total_seconds()

                if dt != 3600:

                    raise RuntimeError(
                        "LST output is not continuous hourly."
                    )

    # ========================================================
    # WORKFLOW LOG
    # ========================================================

    log_dir = (
        output_dir
        / "_workflow_log"
    )

    log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    copy2(
        Path(__file__).resolve(),
        log_dir
        / Path(__file__).name,
    )

    copy2(
        control_file,
        log_dir
        / control_file.name,
    )

    now = datetime.now()

    log_file = (
        log_dir
        / (
            f"{now:%Y%m%d_%H%M%S}_"
            "lumped_utc_to_lst.txt"
        )
    )

    with open(
        log_file,
        "w",
    ) as log:

        log.write(
            f"Domain: {domain}\n"
        )

        log.write(
            f"Control file: {control_file}\n"
        )

        log.write(
            f"Metadata file: {metadata_file}\n"
        )

        log.write(
            f"Metadata timezone: "
            f"{metadata_timezone}\n"
        )

        log.write(
            f"Applied timezone: "
            f"{applied_timezone}\n"
        )

        log.write(
            f"UTC offset hours: "
            f"{offset_hours}\n"
        )

        log.write(
            f"Input UTC file: "
            f"{input_file}\n"
        )

        log.write(
            f"Output LST file: "
            f"{output_file}\n"
        )

        log.write(
            "Configuration: lumped\n"
        )

        log.write(
            "Daylight saving adjustment: no\n"
        )

    # ========================================================
    # FINISH
    # ========================================================

    print()
    print("=" * 78)
    print(
        "PASS: LUMPED CONCATENATED UTC-TO-LST CONVERSION"
    )
    print("=" * 78)

    print(
        f"Domain          : {domain}"
    )

    print(
        f"Timezone        : {applied_timezone}"
    )

    print(
        f"UTC offset      : {offset_hours:+g} hours"
    )

    print(
        f"Timesteps       : {len(lst_dates)}"
    )

    print(
        f"HRUs            : 1"
    )

    print(
        f"UTC first       : {utc_dates[0]}"
    )

    print(
        f"LST first       : {lst_dates[0]}"
    )

    print(
        f"UTC last        : {utc_dates[-1]}"
    )

    print(
        f"LST last        : {lst_dates[-1]}"
    )

    print(
        f"Output          : {output_file}"
    )

    print(
        f"Workflow log    : {log_file}"
    )

    print("=" * 78)


if __name__ == "__main__":

    main()