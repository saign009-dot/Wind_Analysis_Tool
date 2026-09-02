"""Calculate compact monthly percentile fields for the six-model ensemble.

Each task handles one run/month combination. Percentiles are calculated across
time independently for every model, then the six model fields are stored in one
NetCDF file with a model dimension. Raw monthly time-series data are never
written to the derived output.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import xarray as xr


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
MONTHS = tuple(f"{month:02d}" for month in range(1, 13))
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
HISTORICAL_RUN = "historical_1995-2014"
RUNS = (HISTORICAL_RUN,) + tuple(
    f"{scenario}_{period}" for scenario in SCENARIOS for period in PERIODS
)
PERCENTILES = (0.98, 0.999)
PERCENTILE_VARIABLES = {0.98: "p98", 0.999: "p99_9"}


def combinations() -> tuple[tuple[str, str], ...]:
    """Return the deterministic 120-task run/month manifest."""
    return tuple((run, month) for run in RUNS for month in MONTHS)


def combination_for_task(task_index: int) -> tuple[str, str]:
    """Map a zero-based Slurm task index to a run and calendar month."""
    tasks = combinations()
    if task_index < 0 or task_index >= len(tasks):
        raise IndexError(f"Task index must be between 0 and {len(tasks) - 1}.")
    return tasks[task_index]


def run_metadata(run: str) -> tuple[str, str]:
    """Split a run label into its scenario and period metadata."""
    if run == HISTORICAL_RUN:
        return "historical", "1995-2014"
    scenario, separator, period = run.partition("_")
    if not separator or scenario not in SCENARIOS or period not in PERIODS:
        raise ValueError(f"Unsupported run label: {run}")
    return scenario, period


def expected_years_for_run(run: str) -> tuple[int, ...]:
    """Return every inclusive calendar year represented by a run label."""
    _, period = run_metadata(run)
    start_text, end_text = period.split("-", maxsplit=1)
    start = int(start_text)
    end = int(end_text)
    return tuple(range(start, end + 1))


def monthly_filename(model: str, run: str, month: str) -> str:
    """Return the established monthly masked-input filename."""
    if month not in MONTHS:
        raise ValueError(f"Month must be one of {MONTHS}; received {month!r}.")
    return f"WSPD10_{model}_{run}_MNmasked_{month}.nc"


def monthly_input_candidates(
    input_root: str | Path,
    model: str,
    run: str,
    month: str,
) -> tuple[Path, ...]:
    """Return supported input locations in preferred-layout order."""
    root = Path(input_root)
    filename = monthly_filename(model, run, month)
    return (
        root / model / run / "months" / filename,
        root / run / "months" / filename,
        root / "months" / filename,
        root / model / run / filename,
        root / run / filename,
        root / filename,
    )


def monthly_input_path(
    input_root: str | Path,
    model: str,
    run: str,
    month: str,
) -> Path:
    """Find one model's monthly file or report every checked location."""
    candidates = monthly_input_candidates(input_root, model, run, month)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    checked = "\n".join(f"- {candidate}" for candidate in candidates)
    raise FileNotFoundError(
        f"Missing monthly input for {model} {run} month {month}. Checked:\n{checked}"
    )


def percentile_output_path(
    output_root: str | Path,
    run: str,
    month: str,
) -> Path:
    """Return the compact six-model percentile output path."""
    if month not in MONTHS:
        raise ValueError(f"Month must be one of {MONTHS}; received {month!r}.")
    filename = f"WSPD10_6model_{run}_MNmasked_{month}_percentiles.nc"
    return Path(output_root) / run / filename


def percentile_fields(
    path: str | Path,
    month: str,
    expected_years: tuple[int, ...],
    variable: str = "WSPD10",
    time_dim: str = "time",
    workers: int = 1,
    spatial_chunk_size: int = 16,
    units: str = "m s-1",
) -> xr.Dataset:
    """Calculate annual and pooled p98/p99.9 fields for one model/month."""
    if workers < 1 or spatial_chunk_size < 1:
        raise ValueError("workers and spatial_chunk_size must both be positive")

    with xr.open_dataset(path, chunks={time_dim: -1}) as dataset:
        if variable not in dataset:
            available = ", ".join(dataset.data_vars)
            raise KeyError(
                f"{variable!r} is not in {path}. Available variables: {available}"
            )
        wind = dataset[variable]
        if time_dim not in wind.dims:
            raise KeyError(f"Time dimension {time_dim!r} is not in {wind.dims} for {path}.")

        time = dataset[time_dim]
        try:
            source_months = tuple(sorted({int(value) for value in time.dt.month.values}))
            source_years = tuple(sorted({int(value) for value in time.dt.year.values}))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"Could not read calendar years and months from {path}.") from exc
        if source_months != (int(month),):
            raise ValueError(
                f"Expected only calendar month {month} in {path}; found {source_months}."
            )
        if not source_years:
            raise ValueError(f"No calendar years were found in {path}.")
        if source_years != expected_years:
            raise ValueError(
                f"Expected years {expected_years[0]}-{expected_years[-1]} in {path}; "
                f"found {source_years[0]}-{source_years[-1]} with "
                f"{len(source_years)} distinct years."
            )

        spatial_chunks = {
            dimension: min(spatial_chunk_size, wind.sizes[dimension])
            for dimension in wind.dims
            if dimension != time_dim
        }
        wind = wind.chunk({time_dim: -1, **spatial_chunks})
        pooled = wind.quantile(
            PERCENTILES,
            dim=time_dim,
            skipna=True,
            keep_attrs=True,
        )
        annual = wind.groupby(f"{time_dim}.year").quantile(
            PERCENTILES,
            dim=time_dim,
            skipna=True,
            keep_attrs=True,
        )
        fields = xr.Dataset({"annual": annual, "period": pooled}).compute(
            scheduler="threads",
            num_workers=workers,
        )

    for field in fields.data_vars.values():
        field.attrs.setdefault("units", units)
        field.attrs["percentile_method"] = "linear"
        field.attrs["percentile_dimension"] = time_dim
    return fields


def build_monthly_percentile_dataset(
    input_root: str | Path,
    run: str,
    month: str,
    variable: str = "WSPD10",
    time_dim: str = "time",
    workers: int = 1,
    spatial_chunk_size: int = 16,
    units: str = "m s-1",
) -> tuple[xr.Dataset, tuple[Path, ...]]:
    """Calculate and combine the six model-specific percentile fields."""
    fields: list[xr.Dataset] = []
    sources: list[Path] = []
    expected_years = expected_years_for_run(run)

    for model in MODELS:
        source = monthly_input_path(input_root, model, run, month)
        field = percentile_fields(
            source,
            month,
            expected_years,
            variable=variable,
            time_dim=time_dim,
            workers=workers,
            spatial_chunk_size=spatial_chunk_size,
            units=units,
        )
        fields.append(field)
        sources.append(source)

    reference_coordinates = fields[0].coords.to_dataset()
    for model, field in zip(MODELS[1:], fields[1:]):
        if not reference_coordinates.equals(field.coords.to_dataset()):
            raise ValueError(
                f"Coordinates do not match the first model for {model} {run} "
                f"month {month}."
            )

    model_units = {str(field["period"].attrs.get("units", "")) for field in fields}
    if len(model_units) != 1:
        raise ValueError(f"Model units do not match: {sorted(model_units)}")

    aligned = xr.align(*fields, join="exact")
    combined = xr.concat(
        aligned,
        dim=xr.IndexVariable("model", list(MODELS)),
        data_vars="all",
        coords="minimal",
        compat="equals",
        join="exact",
        combine_attrs="override",
    )
    output_variables: dict[str, xr.DataArray] = {}
    output_units = model_units.pop()
    for percentile, name in PERCENTILE_VARIABLES.items():
        annual_values = combined["annual"].sel(quantile=percentile, drop=True)
        annual_name = f"{name}_annual"
        annual_values.name = annual_name
        annual_values.attrs.update(
            long_name=(
                f"model-specific annual {percentile * 100:g}th percentile of "
                "monthly 10-metre wind speed"
            ),
            units=output_units,
            percentile=percentile,
            percentile_method="linear",
            percentile_dimension=time_dim,
        )
        output_variables[annual_name] = annual_values

        period_values = combined["period"].sel(quantile=percentile, drop=True)
        period_name = f"{name}_period"
        period_values.name = period_name
        period_values.attrs.update(
            long_name=(
                f"model-specific pooled {percentile * 100:g}th percentile of "
                "monthly 10-metre wind speed across the full period"
            ),
            units=output_units,
            percentile=percentile,
            percentile_method="linear",
            percentile_dimension=time_dim,
        )
        output_variables[period_name] = period_values

    scenario, period = run_metadata(run)
    result = xr.Dataset(output_variables)
    result.attrs.update(
        title="Six-model monthly wind-speed percentile fields",
        scenario=scenario,
        period=period,
        run=run,
        calendar_month=int(month),
        calendar_month_name=MONTH_NAMES[int(month) - 1],
        variable=variable,
        units=output_units,
        models=", ".join(MODELS),
        ensemble_size=len(MODELS),
        percentiles="0.98, 0.999",
        reduction=(
            "annual percentiles calculated within each calendar year and pooled "
            "percentiles calculated across the full period, independently for each model"
        ),
        annual_years=f"{expected_years[0]}-{expected_years[-1]}",
        source_files="\n".join(str(source) for source in sources),
    )
    combined.close()
    for field in fields:
        field.close()
    return result, tuple(sources)


def write_atomic(dataset: xr.Dataset, destination: Path) -> None:
    """Write compressed NetCDF4 output without exposing an incomplete file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part.{os.getpid()}")
    encoding = {
        variable: {
            "zlib": True,
            "complevel": 4,
            "shuffle": True,
            "dtype": "float32",
        }
        for variable in dataset.data_vars
    }
    try:
        dataset.to_netcdf(
            temporary,
            engine="netcdf4",
            format="NETCDF4",
            encoding=encoding,
        )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate six-model p98 and p99.9 fields for one run/month."
    )
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--task-index", required=True, type=int)
    parser.add_argument("--variable", default="WSPD10")
    parser.add_argument("--time-dim", default="time")
    parser.add_argument("--units", default="m s-1")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--spatial-chunk-size", type=int, default=16)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--preview", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run, month = combination_for_task(args.task_index)
    destination = percentile_output_path(args.output_root, run, month)
    print(f"Task {args.task_index}: {run} month {month}")

    if destination.exists() and not args.overwrite and not args.preview:
        print(f"SKIP existing output: {destination}")
        return 0

    sources = tuple(
        monthly_input_path(args.input_root, model, run, month) for model in MODELS
    )
    if args.preview:
        for source in sources:
            print(f"WOULD READ: {source}")
        print(f"WOULD WRITE: {destination}")
        return 0

    result, sources = build_monthly_percentile_dataset(
        args.input_root,
        run,
        month,
        variable=args.variable,
        time_dim=args.time_dim,
        workers=args.workers,
        spatial_chunk_size=args.spatial_chunk_size,
        units=args.units,
    )
    try:
        write_atomic(result, destination)
    finally:
        result.close()

    for source in sources:
        print(f"READ: {source}")
    print(f"WROTE: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
