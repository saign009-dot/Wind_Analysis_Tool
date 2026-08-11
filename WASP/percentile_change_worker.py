"""Calculate one model's gridded percentile change from a manifest row."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import xarray as xr


DEFAULT_PERCENTILE = 0.98


def percentile_label(percentile: float) -> str:
    """Return filename-safe labels such as p98 and p99_9."""
    if not 0.0 < percentile < 1.0:
        raise ValueError("percentile must be between 0 and 1")
    return f"p{percentile * 100:g}".replace(".", "_")


def read_manifest_row(manifest_path: str | Path, task_index: int) -> dict[str, str]:
    """Return the zero-based manifest row assigned to this array task."""
    if task_index < 0:
        raise ValueError("task_index must be zero or greater")

    with Path(manifest_path).open(newline="", encoding="utf-8") as handle:
        for row_index, row in enumerate(csv.DictReader(handle)):
            if row_index == task_index:
                return row

    raise IndexError(f"Manifest has no task row {task_index}.")


def percentile_field(
    path: str | Path,
    variable: str,
    time_dim: str,
    workers: int,
    spatial_chunk_size: int,
    units: str,
    percentile: float,
):
    """Read one NetCDF file and calculate a percentile field across time."""
    # The complete time axis must be in each Dask block because the percentile
    # is calculated across time. Spatial dimensions are divided into tiles so
    # several tiles can be calculated concurrently.
    with xr.open_dataset(path, chunks={time_dim: -1}) as dataset:
        if variable not in dataset:
            available = ", ".join(dataset.data_vars)
            raise KeyError(f"{variable!r} is not in {path}. Available variables: {available}")

        wind = dataset[variable]
        if time_dim not in wind.dims:
            raise KeyError(f"Time dimension {time_dim!r} is not in {wind.dims} for {path}.")

        spatial_chunks = {
            dim: min(spatial_chunk_size, wind.sizes[dim])
            for dim in wind.dims
            if dim != time_dim
        }
        wind = wind.chunk({time_dim: -1, **spatial_chunks})
        lazy_field = wind.quantile(
            percentile,
            dim=time_dim,
            skipna=True,
            keep_attrs=True,
        )

        # Dask's threaded scheduler calculates independent spatial tiles in
        # parallel. compute() finishes before the source dataset is closed.
        field = lazy_field.compute(scheduler="threads", num_workers=workers)

    # A scalar quantile coordinate is metadata, not a spatial dimension.
    if "quantile" in field.coords:
        field = field.reset_coords("quantile", drop=True)
    # These WSPD10 source files do not carry unit metadata, so record the
    # configured physical unit in every derived field.
    field.attrs.setdefault("units", units)
    field.attrs["percentile"] = percentile
    return field


def calculate_change(
    row: dict[str, str],
    variable: str = "WSPD10",
    time_dim: str = "time",
    workers: int = 1,
    spatial_chunk_size: int = 16,
    units: str = "m s-1",
    percentile: float = DEFAULT_PERCENTILE,
) -> xr.Dataset:
    """Calculate historical/future percentile fields and their difference."""
    historical = percentile_field(
        row["historical_path"], variable, time_dim, workers, spatial_chunk_size, units,
        percentile,
    )
    future = percentile_field(
        row["future_path"], variable, time_dim, workers, spatial_chunk_size, units,
        percentile,
    )

    if not historical.coords.to_dataset().equals(future.coords.to_dataset()):
        raise ValueError(
            f"Historical and future spatial coordinates do not match for {row['model']} "
            f"{row['scenario']} {row['period']} {row['season']}."
        )
    try:
        historical, future = xr.align(historical, future, join="exact")
    except ValueError as exc:
        raise ValueError(
            f"Historical and future grids do not match for {row['model']} "
            f"{row['scenario']} {row['period']} {row['season']}."
        ) from exc

    units = historical.attrs.get("units", future.attrs.get("units", ""))
    absolute_change = future - historical
    label = percentile_label(percentile)
    absolute_change.name = f"{label}_absolute_change"
    absolute_change.attrs.update(
        long_name=f"future minus historical {percentile * 100:g}th-percentile wind speed",
        units=units,
    )

    result = xr.Dataset(
        {
            f"historical_{label}": historical,
            f"future_{label}": future,
            f"{label}_absolute_change": absolute_change,
        }
    )
    result.attrs.update(
        model=row["model"],
        scenario=row["scenario"],
        period=row["period"],
        season=row["season"],
        percentile=percentile,
        units=units,
        change_definition="future percentile - historical percentile",
        historical_source=row["historical_path"],
        future_source=row["future_path"],
    )
    return result


def output_path(
    output_root: str | Path,
    row: dict[str, str],
    percentile: float = DEFAULT_PERCENTILE,
) -> Path:
    """Give every task a deterministic, non-colliding output filename."""
    run = f"{row['scenario']}_{row['period']}"
    label = percentile_label(percentile)
    filename = f"{label}_change_{row['model']}_{run}_{row['season']}.nc"
    return Path(output_root) / row["model"] / run / filename


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one percentile-change task from the manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--task-index", required=True, type=int, help="Zero-based CSV data-row index.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--variable", default="WSPD10")
    parser.add_argument("--time-dim", default="time")
    parser.add_argument("--units", default="m s-1", help="Physical units to record in derived fields.")
    parser.add_argument("--percentile", type=float, default=DEFAULT_PERCENTILE)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--spatial-chunk-size", type=int, default=16)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    row = read_manifest_row(args.manifest, args.task_index)
    destination = output_path(args.output_root, row, args.percentile)

    print(
        f"Task {args.task_index}: {row['model']} {row['scenario']} "
        f"{row['period']} {row['season']}"
    )
    if destination.exists() and not args.overwrite:
        print(f"SKIP existing output: {destination}")
        return 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    if args.workers < 1 or args.spatial_chunk_size < 1:
        raise ValueError("workers and spatial-chunk-size must both be positive")
    result = calculate_change(
        row,
        variable=args.variable,
        time_dim=args.time_dim,
        workers=args.workers,
        spatial_chunk_size=args.spatial_chunk_size,
        units=args.units,
        percentile=args.percentile,
    )
    result.to_netcdf(destination)
    result.close()
    print(f"WROTE: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
