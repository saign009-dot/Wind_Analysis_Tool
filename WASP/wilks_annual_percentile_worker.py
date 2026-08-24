"""Build annual regional percentile series for one Wilks manifest task."""
from __future__ import annotations

#reads command-line options when this worker is launched by Slurm
import argparse
#writes the small annual time-series table created from the two source NetCDF files
import csv
#handles input and output paths consistently on MSI and Windows
from pathlib import Path

#calculates cosine-latitude weights and creates one row per annual value
import numpy as np
#opens the source climate files and performs grouped percentile calculations
import xarray as xr

#reuses the production manifest reader and filename-safe percentile labels
from percentile_change_worker import percentile_label, read_manifest_row


#the Wilks heatmap keeps the same two percentiles as the existing direction heatmap
DEFAULT_PERCENTILES = (0.98, 0.999)
#the historical period is fixed by the ensemble manifest and current WASP design
HISTORICAL_PERIOD = "1995-2014"


#turns a configured year range such as 2040-2059 into inclusive integer endpoints
def period_years(period: str) -> tuple[int, int]:
    """Return the inclusive start and end years from a YYYY-YYYY period label."""
    try:
        start_text, end_text = str(period).split("-", maxsplit=1)
        start, end = int(start_text), int(end_text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid period label {period!r}; expected YYYY-YYYY") from exc
    if start > end:
        raise ValueError(f"Period start must not exceed period end: {period!r}")
    return start, end


#assigns December to the following meteorological winter before annual grouping
def season_year_values(time: xr.DataArray, season: str) -> np.ndarray:
    """Return meteorological season-year labels for a seasonal time coordinate."""
    years = np.asarray(time.dt.year.values, dtype=int)
    if season == "DJF":
        months = np.asarray(time.dt.month.values, dtype=int)
        years = years + (months == 12).astype(int)
    return years


#calculates annual percentiles at every grid cell and then averages over Minnesota
def annual_regional_percentiles(
    path: str | Path,
    variable: str,
    time_dim: str,
    lat_name: str,
    lon_name: str,
    season: str,
    period: str,
    percentiles: tuple[float, ...] = DEFAULT_PERCENTILES,
    workers: int = 1,
    spatial_chunk_size: int = 16,
    minimum_complete_fraction: float = 0.8,
) -> tuple[dict[float, np.ndarray], np.ndarray, np.ndarray, str]:
    """Return annual area-weighted percentile series and retained timestep counts."""
    if not 0.0 < minimum_complete_fraction <= 1.0:
        raise ValueError("minimum_complete_fraction must be greater than 0 and at most 1")
    start_year, end_year = period_years(period)

    #the full time axis stays in one chunk so each annual percentile is exact;
    #spatial dimensions are tiled so independent Minnesota cells can run in parallel
    with xr.open_dataset(path, chunks={time_dim: -1}) as dataset:
        if variable not in dataset:
            available = ", ".join(dataset.data_vars)
            raise KeyError(f"{variable!r} is not in {path}. Available variables: {available}")
        wind = dataset[variable]
        required = {time_dim, lat_name, lon_name}
        missing = sorted(required.difference(wind.dims))
        if missing:
            raise KeyError(f"{path} is missing required dimensions: {', '.join(missing)}")

        spatial_chunks = {
            lat_name: min(spatial_chunk_size, wind.sizes[lat_name]),
            lon_name: min(spatial_chunk_size, wind.sizes[lon_name]),
        }
        wind = wind.chunk({time_dim: -1, **spatial_chunks})
        season_year = season_year_values(wind[time_dim], season)
        wind = wind.assign_coords(season_year=(time_dim, season_year))

        #count source timesteps independently of the spatial missing-value mask so
        #incomplete boundary winters can be removed before the percentile calculation
        timestep_counter = xr.DataArray(
            np.ones(wind.sizes[time_dim], dtype=int),
            dims=[time_dim],
            coords={time_dim: wind[time_dim], "season_year": (time_dim, season_year)},
        )
        counts = timestep_counter.groupby("season_year").sum().compute()
        #where(..., drop=True) is the xarray-supported way to retain coordinate
        #labels selected by a Boolean expression; sel is reserved for label values
        requested = counts.where(
            (counts["season_year"] >= start_year)
            & (counts["season_year"] <= end_year),
            drop=True,
        )
        if requested.sizes.get("season_year", 0) == 0:
            raise ValueError(f"{path} contains no season years within {period}")

        #complete seasons have very similar lengths; the fractional threshold removes
        #the January-February or December fragment created at a DJF file boundary
        typical_count = float(np.median(requested.values))
        complete = requested >= minimum_complete_fraction * typical_count
        retained_years = np.asarray(requested["season_year"].values[complete.values], dtype=int)
        retained_counts = np.asarray(requested.values[complete.values], dtype=int)
        if retained_years.size < 3:
            raise ValueError(
                f"{path} has only {retained_years.size} complete season years in {period}"
            )

        annual_fields = wind.groupby("season_year").quantile(
            list(percentiles), dim=time_dim, skipna=True, keep_attrs=True
        )
        annual_fields = annual_fields.sel(season_year=retained_years)
        #cosine-latitude weights account for the smaller physical area of cells at
        #higher latitude while xarray broadcasts the one-dimensional weights by lon
        latitude_weights = np.cos(np.deg2rad(annual_fields[lat_name]))
        regional = annual_fields.weighted(latitude_weights).mean(
            dim=[lat_name, lon_name], skipna=True
        )
        regional = regional.compute(scheduler="threads", num_workers=workers)
        units = str(wind.attrs.get("units", "m s-1"))

    series: dict[float, np.ndarray] = {}
    for percentile in percentiles:
        values = np.asarray(regional.sel(quantile=percentile).values, dtype=float)
        if values.size != retained_years.size or not np.isfinite(values).all():
            raise ValueError(f"Annual {percentile:g} series is incomplete for {path}")
        series[float(percentile)] = values
    return series, retained_years, retained_counts, units


#runs both periods in one manifest row and returns plain dictionaries for CSV output
def calculate_task_rows(
    row: dict[str, str],
    variable: str = "WSPD10",
    time_dim: str = "time",
    lat_name: str = "lat",
    lon_name: str = "lon",
    percentiles: tuple[float, ...] = DEFAULT_PERCENTILES,
    workers: int = 1,
    spatial_chunk_size: int = 16,
    minimum_complete_fraction: float = 0.8,
) -> list[dict[str, object]]:
    """Calculate historical and future annual percentile rows for one model task."""
    period_definitions = (
        ("historical", HISTORICAL_PERIOD, row["historical_path"]),
        ("future", row["period"], row["future_path"]),
    )
    output_rows: list[dict[str, object]] = []
    for period_type, period, path in period_definitions:
        series, years, counts, units = annual_regional_percentiles(
            path=path,
            variable=variable,
            time_dim=time_dim,
            lat_name=lat_name,
            lon_name=lon_name,
            season=row["season"],
            period=period,
            percentiles=percentiles,
            workers=workers,
            spatial_chunk_size=spatial_chunk_size,
            minimum_complete_fraction=minimum_complete_fraction,
        )
        for percentile in percentiles:
            for year, value, timestep_count in zip(years, series[percentile], counts):
                output_rows.append({
                    "model": row["model"],
                    "scenario": row["scenario"],
                    "period": row["period"],
                    "season": row["season"],
                    "percentile": percentile_label(percentile),
                    "percentile_probability": percentile,
                    "period_type": period_type,
                    "year": int(year),
                    "regional_percentile_mps": float(value),
                    "source_timesteps": int(timestep_count),
                    "units": units,
                    "source": str(path),
                })
    return output_rows


#gives every array task a deterministic destination that cannot collide with another row
def output_path(output_root: str | Path, row: dict[str, str]) -> Path:
    """Return the annual-series CSV path for one manifest row."""
    run = f"{row['scenario']}_{row['period']}"
    filename = f"annual_percentiles_{row['model']}_{run}_{row['season']}.csv"
    return Path(output_root) / row["model"] / run / filename


#writes an explicit header so downstream validation can distinguish missing columns
def write_rows(rows: list[dict[str, object]], destination: str | Path) -> Path:
    """Write one worker's annual percentile rows to CSV."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "model", "scenario", "period", "season", "percentile",
        "percentile_probability", "period_type", "year",
        "regional_percentile_mps", "source_timesteps", "units", "source",
    )
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return destination


#defines the MSI command line used by the 216-task Slurm array
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build annual regional p98 and p99.9 series for one Wilks task."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--task-index", required=True, type=int)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--variable", default="WSPD10")
    parser.add_argument("--time-dim", default="time")
    parser.add_argument("--lat-name", default="lat")
    parser.add_argument("--lon-name", default="lon")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--spatial-chunk-size", type=int, default=16)
    parser.add_argument("--minimum-complete-fraction", type=float, default=0.8)
    parser.add_argument("--overwrite", action="store_true")
    return parser


#loads one manifest row, performs the annual calculations, and writes its small table
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.workers < 1 or args.spatial_chunk_size < 1:
        raise ValueError("workers and spatial-chunk-size must both be positive")
    row = read_manifest_row(args.manifest, args.task_index)
    destination = output_path(args.output_root, row)
    print(
        f"Task {args.task_index}: {row['model']} {row['scenario']} "
        f"{row['period']} {row['season']}"
    )
    if destination.exists() and not args.overwrite:
        print(f"SKIP existing output: {destination}")
        return 0
    rows = calculate_task_rows(
        row,
        variable=args.variable,
        time_dim=args.time_dim,
        lat_name=args.lat_name,
        lon_name=args.lon_name,
        workers=args.workers,
        spatial_chunk_size=args.spatial_chunk_size,
        minimum_complete_fraction=args.minimum_complete_fraction,
    )
    write_rows(rows, destination)
    print(f"WROTE: {destination}")
    return 0


#importing this worker into tests does not execute the command-line workflow
if __name__ == "__main__":
    raise SystemExit(main())
