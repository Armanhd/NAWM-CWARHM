#!/usr/bin/env python3
"""Step 11: Process distributed and/or lumped spatial attributes.

Dry run by default; --execute required for processing.
All external dataset paths come from the control file.
Scientific calculations remain in the original 3b_parameters modules.
"""

import argparse
import csv
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from module_registry import MODULES, PELLETIER_LAYERS, output_paths


HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PARAMETERS = REPO / "3b_parameters"

MODES = ("both", "distributed", "lumped")

FILE_SOURCES = {
    "glhymps",
    "hydrolakes",
    "glclu2019",
    "lgrip30",
}


def read_control(path):
    settings = {}

    for line in path.read_text().splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "|" not in line:
            continue

        key, val = line.split("|", 1)
        settings[key.strip()] = val.split("#", 1)[0].strip()

    return settings


def require_path(path, label):
    if not path.is_file():
        raise FileNotFoundError(f"{label}: {path}")


def resolve_domain(control):
    settings = read_control(control)
    name = settings["domain_name"]
    root = Path(settings["root_path"]) / f"domain_{name}"

    return settings, name, root


def selected_paths(paths, mode):
    if mode == "distributed":
        return paths[:1]

    if mode == "lumped":
        return paths[1:]

    return paths


def output_good(paths):
    for path in paths:
        if not path.is_file() or path.stat().st_size < 16:
            return False

        with path.open(newline="") as file:
            if len(next(csv.reader(file), [])) < 4:
                return False

    return True


def build_command(name, script, control, settings, mode):
    if name == "terrain":
        terrain = HERE / "run_terrain_correction.sh"
        require_path(terrain, "Terrain wrapper")

        return [
            "bash",
            str(terrain),
            str(control),
            mode,
        ]

    scriptpath = PARAMETERS / script
    require_path(scriptpath, "Extractor")

    cmd = [
        sys.executable,
        str(scriptpath),
        str(control),
        "--mode",
        mode,
    ]

    if name == "pelletier":
        base = settings.get("attribute_pelletier_raw_dir", "").strip()

        if not base or base.lower() == "default":
            raise ValueError(
                "Missing attribute_pelletier_raw_dir in control"
            )

        for layer, filename in PELLETIER_LAYERS.items():
            key = f"attribute_pelletier_layer_{layer}"

            file_path = settings.get(key) or str(
                Path(base) / filename
            )

            source = Path(file_path).expanduser().resolve()
            require_path(source, f"Pelletier {layer}")

            cmd += [
                "--layer",
                f"{layer}={source}",
            ]

        return cmd

    key = f"attribute_{name}_source"
    src = settings.get(key, "").strip()

    if not src or src.lower() == "default":
        raise ValueError(
            f"Missing explicit source path: {key}"
        )

    source = Path(src).expanduser().resolve()

    if name in FILE_SOURCES:
        require_path(source, key)
    elif not source.is_dir():
        raise NotADirectoryError(f"{key}: {source}")

    option = "--archive" if name == "hydrolakes" else "--source"

    cmd += [
        option,
        str(source),
    ]

    return cmd


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("control", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--with-worldclim", action="store_true")

    parser.add_argument(
        "--force",
        action="store_true",
        help="Rerun extractors even when selected module CSVs exist",
    )

    parser.add_argument(
        "--no-consolidate",
        action="store_true",
    )

    args = parser.parse_args()

    control = args.control.resolve()
    require_path(control, "Control file")

    cfg, basin, domain = resolve_domain(control)

    mode = cfg.get(
        "attribute_processing_mode", "both"
    ).strip().lower()

    if mode not in MODES:
        raise ValueError(
            f"Invalid attribute_processing_mode: {mode}"
        )

    print(f"Processing mode: {mode}", flush=True)

    print(
        f"BASIN={basin} DOMAIN={domain} EXECUTE={args.execute}",
        flush=True,
    )

    report_dir = domain / "_workflow_log/step11_attributes"

    result = {
        "basin": basin,
        "control": str(control),
        "mode": mode,
        "modules": {},
        "consolidation": "not_run",
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    failures = []

    # --------------------------------------------------------
    # PROCESS DATASET MODULES
    # --------------------------------------------------------

    for name, script in MODULES:
        if name == "worldclim" and not args.with_worldclim:
            result["modules"][name] = "not_selected"
            continue

        targets = selected_paths(
            output_paths(domain, name),
            mode,
        )

        if output_good(targets) and not args.force:
            print(
                f"SKIP {name}: existing nonempty CSVs "
                f"for {mode}",
                flush=True,
            )

            result["modules"][name] = "existing"
            continue

        try:
            cmd = build_command(
                name,
                script,
                control,
                cfg,
                mode,
            )

        except Exception as exc:
            print(
                f"CONFIG ERROR {name}: {exc}",
                flush=True,
            )

            result["modules"][name] = (
                f"configuration_error: {exc}"
            )

            failures.append(name)
            continue

        print("$ " + shlex.join(cmd), flush=True)

        if not args.execute:
            result["modules"][name] = "dry_run"
            continue

        completed = subprocess.run(cmd)

        if (
            completed.returncode != 0
            or not output_good(targets)
        ):
            result["modules"][name] = (
                f"failed_exit_{completed.returncode}"
            )
            failures.append(name)

        else:
            result["modules"][name] = "success"

    # --------------------------------------------------------
    # CONSOLIDATE SELECTED MODE
    # --------------------------------------------------------

    if not args.no_consolidate and not failures:
        consolidate = HERE / "consolidate_nwam_attributes.py"
        schema = HERE / "attribute_metadata.csv"

        try:
            require_path(
                consolidate,
                "Consolidation script",
            )

            require_path(
                schema,
                "Attribute metadata",
            )

            cmd = [
                sys.executable,
                str(consolidate),
                str(control),
                "--mode",
                mode,
                "--schema",
                str(schema),
            ]

            if args.with_worldclim:
                cmd.append("--with-worldclim")

            print("$ " + shlex.join(cmd), flush=True)

            if args.execute:
                rc = subprocess.run(cmd).returncode

                finals = selected_paths(
                    (
                        domain
                        / "attributes"
                        / f"{basin}_attributes.csv",

                        domain
                        / "lumped/attributes"
                        / f"{basin}_lumped_attributes.csv",
                    ),
                    mode,
                )

                if rc == 0 and output_good(finals):
                    result["consolidation"] = "success"
                else:
                    result["consolidation"] = f"failed_{rc}"
                    failures.append("consolidation")

            else:
                result["consolidation"] = "dry_run"

        except Exception as exc:
            result["consolidation"] = (
                f"configuration_error: {exc}"
            )
            failures.append("consolidation")

    # --------------------------------------------------------
    # STATUS REPORT
    # --------------------------------------------------------

    if args.execute:
        result["status"] = (
            "failed" if failures else "complete_or_partial_data"
        )

        report_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        report = report_dir / "status.json"
        temporary = report.with_suffix(".tmp")

        temporary.write_text(
            json.dumps(result, indent=2)
        )

        temporary.replace(report)

    else:
        result["status"] = (
            "dry_run_with_errors" if failures else "dry_run"
        )

    print(
        f"RESULT: {result['status']} | {basin} | {mode}",
        flush=True,
    )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())