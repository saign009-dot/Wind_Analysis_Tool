"""Combine six model percentile-change maps into an ensemble mean and spread."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import xarray as xr

from percentile_change_worker import DEFAULT_PERCENTILE, percentile_label


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
SCENARIO_LABELS = {
    "ssp245": "SSP2-4.5",
    "ssp370": "SSP3-7.0",
    "ssp585": "SSP5-8.5",
}


def combination_for_task(task_index: int) -> tuple[str, str, str]:
    """Map a zero-based Slurm task number to scenario, period, and season."""
    combinations = [
        (scenario, period, season)
        for scenario in SCENARIOS
        for period in PERIODS
        for season in SEASONS
    ]
    if task_index < 0 or task_index >= len(combinations):
        raise IndexError(f"Task index must be between 0 and {len(combinations) - 1}.")
    return combinations[task_index]


def model_result_path(
    input_root: str | Path,
    model: str,
    scenario: str,
    period: str,
    season: str,
    percentile: float = DEFAULT_PERCENTILE,
) -> Path:
    run = f"{scenario}_{period}"
    label = percentile_label(percentile)
    filename = f"{label}_change_{model}_{run}_{season}.nc"
    return Path(input_root) / model / run / filename


def load_model_changes(
    input_root: str | Path,
    scenario: str,
    period: str,
    season: str,
    percentile: float = DEFAULT_PERCENTILE,
) -> xr.DataArray:
    """Load and align the six model absolute-change fields."""
    fields: list[xr.DataArray] = []
    missing: list[Path] = []

    for model in MODELS:
        path = model_result_path(
            input_root, model, scenario, period, season, percentile
        )
        if not path.is_file():
            missing.append(path)
            continue

        with xr.open_dataset(path) as dataset:
            variable = f"{percentile_label(percentile)}_absolute_change"
            if variable not in dataset:
                raise KeyError(f"{variable} is missing from {path}.")
            field = dataset[variable].load()
            fields.append(field)

    if missing:
        paths = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"The ensemble is missing model results:\n{paths}")
    if len(fields) != len(MODELS):
        raise ValueError(f"Expected {len(MODELS)} models, loaded {len(fields)}.")

    try:
        aligned = xr.align(*fields, join="exact")
    except ValueError as exc:
        raise ValueError(
            f"Model grids do not match for {scenario} {period} {season}."
        ) from exc

    units = {str(field.attrs.get("units", "")) for field in aligned}
    if len(units) != 1:
        raise ValueError(f"Model units do not match: {sorted(units)}")
    combined = xr.concat(aligned, dim="model")
    return combined.assign_coords(model=list(MODELS))


def calculate_ensemble(model_changes: xr.DataArray) -> xr.Dataset:
    """Calculate the ensemble mean, sample standard deviation, and model count."""
    units = str(model_changes.attrs.get("units", "m s-1"))
    percentile = float(model_changes.attrs.get("percentile", DEFAULT_PERCENTILE))
    percentile_text = f"{percentile * 100:g}th-percentile"
    mean = model_changes.mean("model", skipna=True)
    count = model_changes.count("model")
    # Write the ddof=1 formula explicitly so cells outside the common mask do
    # not emit NumPy warnings. Sample SD is undefined when fewer than two model
    # values are available, so those cells remain NaN.
    squared_deviations = ((model_changes - mean) ** 2).sum("model", skipna=True)
    denominator = (count - 1).where(count >= 2)
    spread = np.sqrt(squared_deviations / denominator)

    mean.name = "ensemble_mean"
    mean.attrs.update(
        long_name=f"multi-model mean {percentile_text} wind-speed change",
        units=units,
    )
    spread.name = "inter_model_std"
    spread.attrs.update(
        long_name=f"sample standard deviation of {percentile_text} change across models",
        units=units,
        ddof=1,
    )
    count.name = "model_count"
    count.attrs.update(long_name="number of finite model values", units="1")
    return xr.Dataset(
        {
            "ensemble_mean": mean,
            "inter_model_std": spread,
            "model_count": count,
        }
    )


def ensemble_output_paths(
    output_root: str | Path,
    scenario: str,
    period: str,
    season: str,
    percentile: float = DEFAULT_PERCENTILE,
) -> tuple[Path, Path]:
    run = f"{scenario}_{period}"
    label = percentile_label(percentile)
    stem = f"ensemble_{label}_absolute_change_{run}_{season}"
    directory = Path(output_root) / run
    return directory / f"{stem}.nc", directory / f"{stem}.png"


def _robust_upper(values, absolute: bool = False) -> float:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return 1.0
    if absolute:
        finite = np.abs(finite)
    upper = float(np.nanquantile(finite, 0.98))
    return upper if upper > 0 else 1.0


def plot_ensemble(ensemble: xr.Dataset, output_path: str | Path, title: str) -> Path:
    """Save the requested two-panel mean and inter-model-spread map."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    mean = ensemble["ensemble_mean"]
    spread = ensemble["inter_model_std"]
    units = str(mean.attrs.get("units", "m s-1"))
    mean_limit = _robust_upper(mean.values, absolute=True)
    spread_limit = _robust_upper(spread.values)

    diverging = plt.get_cmap("RdBu_r").copy()
    sequential = plt.get_cmap("viridis").copy()
    diverging.set_bad("#eeeeee")
    sequential.set_bad("#eeeeee")

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), constrained_layout=True)
    mean_mesh = axes[0].pcolormesh(
        mean["lon"], mean["lat"], mean,
        cmap=diverging, vmin=-mean_limit, vmax=mean_limit, shading="auto",
    )
    spread_mesh = axes[1].pcolormesh(
        spread["lon"], spread["lat"], spread,
        cmap=sequential, vmin=0, vmax=spread_limit, shading="auto",
    )
    axes[0].set_title("Ensemble mean")
    axes[1].set_title("Inter-model spread (sample SD)")
    for axis in axes:
        axis.set_xlabel("Longitude")
        axis.set_ylabel("Latitude")
        axis.set_aspect("equal")
    fig.colorbar(mean_mesh, ax=axes[0], label=units, extend="both")
    fig.colorbar(spread_mesh, ax=axes[1], label=units, extend="max")
    fig.suptitle(title, fontsize=15)
    fig.savefig(output, dpi=200)
    plt.close(fig)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one percentile ensemble task.")
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--task-index", required=True, type=int)
    parser.add_argument("--percentile", type=float, default=DEFAULT_PERCENTILE)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scenario, period, season = combination_for_task(args.task_index)
    netcdf_path, figure_path = ensemble_output_paths(
        args.output_root, scenario, period, season, args.percentile
    )
    print(f"Task {args.task_index}: {scenario} {period} {season}")

    if netcdf_path.exists() and figure_path.exists() and not args.overwrite:
        print(f"SKIP existing outputs: {netcdf_path} and {figure_path}")
        return 0

    model_changes = load_model_changes(
        args.input_root, scenario, period, season, args.percentile
    )
    ensemble = calculate_ensemble(model_changes)
    ensemble.attrs.update(
        scenario=scenario,
        period=period,
        season=season,
        percentile=args.percentile,
        change_definition="future percentile - historical percentile",
        models=", ".join(MODELS),
        ensemble_size=len(MODELS),
        spread_definition="sample standard deviation across models (ddof=1)",
        color_limits="98th percentile of plotted finite magnitudes",
    )

    netcdf_path.parent.mkdir(parents=True, exist_ok=True)
    ensemble.to_netcdf(netcdf_path)
    scenario_label = SCENARIO_LABELS.get(scenario, scenario.upper())
    percentile_text = f"{args.percentile * 100:g}th-percentile"
    title = (
        f"Change in {percentile_text} wind speed (future − historical) — "
        f"{scenario_label} {period} {season}, n={len(MODELS)}"
    )
    plot_ensemble(ensemble, figure_path, title)
    model_changes.close()
    ensemble.close()
    print(f"WROTE: {netcdf_path}")
    print(f"WROTE: {figure_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
