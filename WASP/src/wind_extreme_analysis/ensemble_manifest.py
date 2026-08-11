"""Build the input manifest used by the p98 ensemble Slurm array."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


MODELS = (
    "BCC-CSM2-MR",
    "CESM2",
    "CMCC-ESM2",
    "CNRM-ESM2-1",
    "IPSL-CM6A-LR",
    "MIROC-ES2L",
)
SCENARIOS = ("ssp245", "ssp370", "ssp585")
PERIODS = ("2040-2059", "2060-2079", "2080-2099")
SEASONS = ("DJF", "MAM", "JJA", "SON")
HISTORICAL_RUN = "historical_1995-2014"


def seasonal_file(analysis_root: Path, model: str, run: str, season: str) -> Path:
    """Find a seasonal file in either layout used by the model directories."""
    filename = f"WSPD10_{model}_{run}_MNmasked_{season}.nc"
    run_directory = analysis_root / model / run

    # BCC uses run/seasons/file.nc; the other model folders use run/file.nc.
    candidates = (
        run_directory / "seasons" / filename,
        run_directory / filename,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    # Return the preferred layout when neither exists so validation can print
    # a clear expected path instead of failing inside this helper.
    return candidates[0]


def build_rows(analysis_root: str | Path) -> tuple[list[dict[str, str]], list[Path]]:
    """Create manifest rows and return any input paths that are missing."""
    root = Path(analysis_root)
    rows: list[dict[str, str]] = []
    missing: list[Path] = []

    # Each pass through these four loops becomes one Slurm array task.
    for model in MODELS:
        for scenario in SCENARIOS:
            for period in PERIODS:
                future_run = f"{scenario}_{period}"
                for season in SEASONS:
                    historical_path = seasonal_file(root, model, HISTORICAL_RUN, season)
                    future_path = seasonal_file(root, model, future_run, season)

                    for path in (historical_path, future_path):
                        if not path.is_file():
                            missing.append(path)

                    rows.append(
                        {
                            "model": model,
                            "scenario": scenario,
                            "period": period,
                            "season": season,
                            "historical_path": str(historical_path),
                            "future_path": str(future_path),
                        }
                    )

    return rows, missing


def write_manifest(rows: list[dict[str, str]], output_path: str | Path) -> Path:
    """Write the task table that Slurm workers will read by row number."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "model",
        "scenario",
        "period",
        "season",
        "historical_path",
        "future_path",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate p98 ensemble inputs and create a 216-row Slurm manifest."
    )
    parser.add_argument("--analysis-root", required=True, help="Analysis directory containing model folders.")
    parser.add_argument("--output", default="ensemble_tasks.csv", help="Manifest CSV to create.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows, missing = build_rows(args.analysis_root)

    if missing:
        print(f"Cannot create the manifest: {len(missing)} required files are missing.")
        for path in missing:
            print(f"MISSING: {path}")
        return 2

    output = write_manifest(rows, args.output)
    print(f"Validated {len(rows) * 2} input references.")
    print(f"Wrote {len(rows)} Slurm tasks to {output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
