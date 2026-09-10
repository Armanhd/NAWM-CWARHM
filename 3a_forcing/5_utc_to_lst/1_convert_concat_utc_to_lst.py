#!/usr/bin/env python3
# coding: utf-8

"""
Convert concatenated distributed NWAM SUMMA forcing from UTC
to Local Standard Time (LST).

The timezone is taken from the CAMELS-SPAT metadata field:

    dv_flow_obs_timezone

The CAMELS-SPAT metadata CSV location is NOT hardcoded here.
It is read from:

    camels_spat_metadata_path.txt

The basin is identified from the CWARHM control file:

    domain_name | CAN_05BB001

For example:

    CAN_05BB001
        Country    = CAN
        Station_id = 05BB001

Following the CAMELS-SPAT workflow:

    NST -> AST

because the forcing is hourly and a half-hour shift is not used.

The UTC concatenated forcing is retained unchanged.

Input:
    domain_<DOMAIN>/
        forcing/
            5_SUMMA_input_concat/
                NWAM_SUMMA_forcing_*.nc

Output:
    domain_<DOMAIN>/
        forcing/
            6_SUMMA_input_LST/
                NWAM_SUMMA_forcing_*_LST.nc

Usage:
    python 1_convert_concat_utc_to_lst.py CONTROL_FILE
"""

from pathlib import Path
from datetime import datetime
import argparse
import shutil

import pandas as pd
from netCDF4 import Dataset


# ============================================================
# SCRIPT PATHS
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent

METADATA_PATH_FILE = (
    SCRIPT_DIR
    / "camels_spat_metadata_path.txt"
)


# ============================================================
# CAMELS-SPAT STANDARD-TIME OFFSETS
# ============================================================

TIMEZONE_OFFSETS = {
    "AST": -4.0,
    "EST": -5.0,
    "CST": -6.0,
    "MST": -7.0,
    "PST": -8.0,
    "AKST": -9.0,
    "HST": -10.0,
}


# ============================================================
# FUNCTIONS
# ============================================================

def read_control_setting(control_file, setting):

    matches = []

    with control_file.open() as contents:

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
                1
            )

            if left.strip() != setting:
                continue

            value = (
                right
                .split("#", 1)[0]
                .strip()
            )

            matches.append(
                value
            )

    if len(matches) == 0:

        raise RuntimeError(
            f"Setting '{setting}' not found in:\n"
            f"{control_file}"
        )

    if len(matches) > 1:

        raise RuntimeError(
            f"Setting '{setting}' occurs more than once in:\n"
            f"{control_file}"
        )

    if not matches[0]:

        raise RuntimeError(
            f"Setting '{setting}' is empty in:\n"
            f"{control_file}"
        )

    return matches[0]


def read_metadata_path():

    if not METADATA_PATH_FILE.is_file():

        raise FileNotFoundError(
            "CAMELS-SPAT metadata-path file not found:\n"
            f"{METADATA_PATH_FILE}"
        )

    lines = [
        line.strip()
        for line in METADATA_PATH_FILE.read_text().splitlines()
        if line.strip()
        and not line.strip().startswith("#")
    ]

    if len(lines) != 1:

        raise RuntimeError(
            "camels_spat_metadata_path.txt must contain "
            "exactly one non-comment path."
        )

    metadata_file = (
        Path(lines[0])
        .expanduser()
        .resolve()
    )

    if not metadata_file.is_file():

        raise FileNotFoundError(
            "CAMELS-SPAT metadata CSV not found:\n"
            f"{metadata_file}"
        )

    return metadata_file


def split_domain(domain):

    if "_" not in domain:

        raise RuntimeError(
            "domain_name must have COUNTRY_STATION format.\n"
            f"Found: {domain}"
        )

    country, station_id = domain.split(
        "_",
        1
    )

    if not country or not station_id:

        raise RuntimeError(
            f"Invalid domain_name: {domain}"
        )

    return country, station_id


def find_timezone(
    metadata_file,
    country,
    station_id,
):

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
            "Required CAMELS-SPAT metadata columns missing:\n"
            + "\n".join(
                missing_columns
            )
        )

    metadata["Country"] = (
        metadata["Country"]
        .fillna("")
        .str.strip()
    )

    metadata["Station_id"] = (
        metadata["Station_id"]
        .fillna("")
        .str.strip()
    )

    match = metadata[
        (metadata["Country"] == country)
        &
        (metadata["Station_id"] == station_id)
    ]

    if len(match) == 0:

        raise RuntimeError(
            "Basin not found in CAMELS-SPAT metadata:\n"
            f"Country    : {country}\n"
            f"Station_id : {station_id}"
        )

    if len(match) > 1:

        raise RuntimeError(
            "Multiple CAMELS-SPAT metadata rows found for:\n"
            f"{country}_{station_id}"
        )

    timezone = (
        match.iloc[0][
            "dv_flow_obs_timezone"
        ]
    )

    if pd.isna(timezone):

        raise RuntimeError(
            "dv_flow_obs_timezone is missing for:\n"
            f"{country}_{station_id}"
        )

    timezone = str(
        timezone
    ).strip().upper()

    if not timezone:

        raise RuntimeError(
            "dv_flow_obs_timezone is empty for:\n"
            f"{country}_{station_id}"
        )

    original_timezone = timezone

    # Same treatment used by CAMELS-SPAT.
    if timezone == "NST":

        print(
            "NST found. Following CAMELS-SPAT: "
            "using AST because forcing is hourly."
        )

        timezone = "AST"

    if timezone not in TIMEZONE_OFFSETS:

        raise RuntimeError(
            "Unsupported dv_flow_obs_timezone:\n"
            f"  {original_timezone}\n\n"
            "Supported whole-hour standard zones:\n"
            + ", ".join(
                sorted(TIMEZONE_OFFSETS)
            )
            + "\nNST is converted to AST."
        )

    offset = TIMEZONE_OFFSETS[
        timezone
    ]

    return (
        original_timezone,
        timezone,
        offset,
    )


def find_concat_file(input_dir):

    files = sorted(
        input_dir.glob(
            "NWAM_SUMMA_forcing_*.nc"
        )
    )

    # Exclude any previously generated LST products
    files = [
        file
        for file in files
        if not file.stem.endswith(
            "_LST"
        )
    ]

    if len(files) == 0:

        raise FileNotFoundError(
            "No concatenated SUMMA forcing file found in:\n"
            f"{input_dir}"
        )

    if len(files) > 1:

        raise RuntimeError(
            "More than one concatenated SUMMA forcing file "
            "was found.\n"
            "Expected exactly one file:\n"
            + "\n".join(
                str(file)
                for file in files
            )
        )

    return files[0]


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Convert distributed concatenated "
            "NWAM SUMMA forcing from UTC to LST."
        )
    )

    parser.add_argument(
        "control_file",
        type=Path,
        help="Domain-specific distributed CWARHM control file.",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing LST output file.",
    )

    args = parser.parse_args()

    control_file = (
        args.control_file
        .expanduser()
        .resolve()
    )

    if not control_file.is_file():

        raise FileNotFoundError(
            f"Control file not found:\n"
            f"{control_file}"
        )

    # ========================================================
    # CONTROL SETTINGS
    # ========================================================

    domain = read_control_setting(
        control_file,
        "domain_name",
    )

    root_path = Path(
        read_control_setting(
            control_file,
            "root_path",
        )
    ).expanduser().resolve()

    country, station_id = split_domain(
        domain
    )

    # ========================================================
    # CAMELS-SPAT METADATA
    # ========================================================

    metadata_file = read_metadata_path()

    (
        metadata_timezone,
        applied_timezone,
        utc_offset_hours,
    ) = find_timezone(
        metadata_file,
        country,
        station_id,
    )

    # ========================================================
    # PATHS
    # ========================================================

    domain_root = (
        root_path
        / f"domain_{domain}"
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
            "Concatenated forcing directory not found:\n"
            f"{input_dir}"
        )

    input_file = find_concat_file(
        input_dir
    )

    output_file = (
        output_dir
        / (
            f"{input_file.stem}"
            "_LST.nc"
        )
    )

    # ========================================================
    # REPORT
    # ========================================================

    print()
    print("=" * 78)
    print("DISTRIBUTED CONCATENATED FORCING: UTC -> LST")
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
        f"UTC offset          : {utc_offset_hours:+g} hours"
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

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output_file.exists():

        if not args.overwrite:

            raise FileExistsError(
                "LST output already exists.\n"
                "Use --overwrite if intentional:\n"
                f"{output_file}"
            )

        output_file.unlink()

    # Keep original UTC forcing untouched.
    shutil.copy2(
        input_file,
        output_file,
    )

    # ========================================================
    # SHIFT TIME
    # ========================================================

    try:

        with Dataset(
            output_file,
            "a",
        ) as ds:

            if "time" not in ds.variables:

                raise RuntimeError(
                    "time variable is missing from:\n"
                    f"{output_file}"
                )

            time_var = ds.variables[
                "time"
            ]

            if "units" not in time_var.ncattrs():

                raise RuntimeError(
                    "time variable has no units attribute."
                )

            time_units = str(
                time_var.getncattr(
                    "units"
                )
            )

            # CAMELS-SPAT applies the offset directly to
            # the numeric time coordinate. That requires
            # an hourly time unit.
            if not time_units.lower().startswith(
                "hours since"
            ):

                raise RuntimeError(
                    "UTC-to-LST conversion expects time units "
                    "in hours.\n"
                    f"Found: {time_units}"
                )

            original_first = float(
                time_var[0]
            )

            original_last = float(
                time_var[-1]
            )

            time_var[:] = (
                time_var[:]
                + utc_offset_hours
            )

            shifted_first = float(
                time_var[0]
            )

            shifted_last = float(
                time_var[-1]
            )

            history_entry = (
                f"On {datetime.now():%Y-%m-%d %H:%M:%S}: "
                f"shifted concatenated forcing time from UTC "
                f"to {applied_timezone} "
                f"using CAMELS-SPAT dv_flow_obs_timezone; "
                f"offset={utc_offset_hours:+g} hours."
            )

            if "History" in ds.ncattrs():

                previous = str(
                    ds.getncattr(
                        "History"
                    )
                )

                ds.setncattr(
                    "History",
                    previous
                    + " "
                    + history_entry,
                )

            elif "history" in ds.ncattrs():

                previous = str(
                    ds.getncattr(
                        "history"
                    )
                )

                ds.setncattr(
                    "history",
                    previous
                    + " "
                    + history_entry,
                )

            else:

                ds.setncattr(
                    "History",
                    history_entry,
                )

            ds.setncattr(
                "time_zone",
                applied_timezone,
            )

            ds.setncattr(
                "time_zone_source",
                (
                    "CAMELS-SPAT "
                    "dv_flow_obs_timezone"
                ),
            )

            ds.setncattr(
                "time_zone_metadata_file",
                str(metadata_file),
            )

            ds.setncattr(
                "utc_to_lst_offset_hours",
                utc_offset_hours,
            )

            ds.setncattr(
                "original_time_zone",
                "UTC",
            )

            ds.setncattr(
                "time_conversion",
                (
                    f"UTC to {applied_timezone}; "
                    f"{utc_offset_hours:+g} hours"
                ),
            )

    except Exception:

        # Avoid leaving an incomplete output.
        if output_file.exists():
            output_file.unlink()

        raise

    # ========================================================
    # VERIFY
    # ========================================================

    with Dataset(
        output_file,
        "r",
    ) as ds:

        time_var = ds.variables[
            "time"
        ]

        check_first = float(
            time_var[0]
        )

        check_last = float(
            time_var[-1]
        )

        expected_first = (
            original_first
            + utc_offset_hours
        )

        expected_last = (
            original_last
            + utc_offset_hours
        )

        if check_first != expected_first:

            raise RuntimeError(
                "First timestamp was not shifted correctly."
            )

        if check_last != expected_last:

            raise RuntimeError(
                "Last timestamp was not shifted correctly."
            )

        saved_timezone = getattr(
            ds,
            "time_zone",
            None,
        )

        if saved_timezone != applied_timezone:

            raise RuntimeError(
                "Output timezone metadata verification failed."
            )

    # ========================================================
    # FINISH
    # ========================================================

    print("=" * 78)
    print("PASS: DISTRIBUTED CONCATENATED UTC-TO-LST CONVERSION")
    print("=" * 78)

    print(
        f"Domain           : {domain}"
    )

    print(
        f"Timezone         : {applied_timezone}"
    )

    print(
        f"Offset           : {utc_offset_hours:+g} hours"
    )

    print(
        f"Original first   : {original_first}"
    )

    print(
        f"Shifted first    : {shifted_first}"
    )

    print(
        f"Original last    : {original_last}"
    )

    print(
        f"Shifted last     : {shifted_last}"
    )

    print(
        f"UTC input kept   : {input_file}"
    )

    print(
        f"LST output       : {output_file}"
    )

    print("=" * 78)


if __name__ == "__main__":
    main()