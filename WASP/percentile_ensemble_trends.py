"""Create seasonal trend plots from model-level percentile-change maps."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from percentile_change_worker import DEFAULT_PERCENTILE, percentile_label
from percentile_ensemble_worker import (
    MODELS,
    PERIODS,
    SCENARIOS,
    SCENARIO_LABELS,
    SEASONS,
    model_result_path,
)


SCENARIO_COLORS = {
    # Colorblind-friendly blue, orange, and reddish purple keep overlapping
    # spread bands visually distinct.
    "ssp245": "#0072B2",
    "ssp370": "#E69F00",
    "ssp585": "#CC79A7",
}

SPREAD_ALPHA = 0.20


def area_weighted_regional_mean(field: xr.DataArray) -> float:
    """Calculate a Minnesota mean using cosine-latitude cell weights."""
    if "lat" not in field.coords or "lon" not in field.coords:
        raise KeyError("Expected lat and lon coordinates in each model change field.")
    spatial_dims = [dim for dim in field.dims if dim in {"lat", "lon"}]
    if set(spatial_dims) != {"lat", "lon"}:
        raise ValueError(f"Expected lat/lon field dimensions, found {field.dims}.")

    weights = np.cos(np.deg2rad(field["lat"]))
    regional_mean = field.weighted(weights).mean(spatial_dims, skipna=True)
    return float(regional_mean.values)


def collect_model_trends(
    input_root: str | Path,
    percentile: float = DEFAULT_PERCENTILE,
) -> pd.DataFrame:
    """Read all 216 model results and calculate one regional value per file."""
    rows: list[dict[str, object]] = []
    missing: list[Path] = []

    for model in MODELS:
        for scenario in SCENARIOS:
            for period in PERIODS:
                for season in SEASONS:
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
                        field = dataset[variable]
                        rows.append(
                            {
                                "model": model,
                                "scenario": scenario,
                                "period": period,
                                "season": season,
                                "regional_change": area_weighted_regional_mean(field),
                                "units": field.attrs.get("units", "m s-1"),
                                "source": str(path),
                            }
                        )

    if missing:
        paths = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Trend analysis is missing model results:\n{paths}")
    return pd.DataFrame(rows)


def summarize_ensemble(model_values: pd.DataFrame) -> pd.DataFrame:
    """Calculate ensemble statistics across the six regional model values."""
    summary = (
        model_values.groupby(["scenario", "period", "season"], sort=False)[
            "regional_change"
        ]
        .agg(
            ensemble_mean="mean",
            inter_model_std="std",
            model_min="min",
            model_max="max",
            model_count="count",
        )
        .reset_index()
    )
    if not (summary["model_count"] == len(MODELS)).all():
        raise ValueError("At least one trend point does not contain all six models.")
    summary["units"] = str(model_values["units"].iloc[0])
    return summary


def plot_trends(
    summary: pd.DataFrame,
    output_path: str | Path,
    percentile: float = DEFAULT_PERCENTILE,
) -> Path:
    """Plot one seasonal panel with scenario mean lines and SD bands."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    x = np.arange(len(PERIODS))
    period_labels = [
        f"{period.split('-')[0]}–{period.split('-')[1][-2:]}"
        for period in PERIODS
    ]
    units = str(summary["units"].iloc[0])

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True, sharey=True)
    for axis, season in zip(axes.flat, SEASONS):
        seasonal = summary[summary["season"] == season]
        for scenario in SCENARIOS:
            group = seasonal[seasonal["scenario"] == scenario].set_index("period")
            group = group.loc[list(PERIODS)]
            mean = group["ensemble_mean"].to_numpy(dtype=float)
            spread = group["inter_model_std"].to_numpy(dtype=float)
            color = SCENARIO_COLORS[scenario]
            axis.plot(
                x,
                mean,
                color=color,
                marker="o",
                linewidth=2.2,
                label=SCENARIO_LABELS[scenario],
            )
            axis.fill_between(
                x,
                mean - spread,
                mean + spread,
                color=color,
                alpha=SPREAD_ALPHA,
                linewidth=0,
            )
        axis.axhline(0, color="#333333", linewidth=0.9, linestyle="--")
        axis.set_title(season, fontweight="bold")
        axis.set_xticks(x, period_labels)
        # sharex keeps every panel aligned but hides upper-row labels by
        # default; explicitly show the period labels on all four panels.
        axis.tick_params(axis="x", labelbottom=True)
        # Likewise, sharey hides right-column tick labels by default.
        axis.tick_params(axis="y", labelleft=True)
        axis.set_ylabel(f"Area-weighted mean change ({units})")
        axis.grid(axis="y", color="#d5d5d5", linewidth=0.7)

    axes[1, 0].set_xlabel("Future period")
    axes[1, 1].set_xlabel("Future period")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.895),
        ncol=3,
        frameon=False,
        fontsize=13,
        handlelength=2.6,
        columnspacing=2.4,
        markerscale=1.25,
    )
    fig.suptitle(
        f"Minnesota ensemble trend in {percentile * 100:g}th-percentile wind-speed change\n"
        "Future minus historical (1995–2014)",
        fontsize=15,
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "Lines show six-model ensemble means; shading represents inter-model spread "
        "(±1 sample SD), not confidence intervals.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.83))
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create percentile ensemble trend summaries and plot.")
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--percentile", type=float, default=DEFAULT_PERCENTILE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    model_values = collect_model_trends(args.input_root, args.percentile)
    summary = summarize_ensemble(model_values)
    label = percentile_label(args.percentile)
    model_csv = output_root / f"{label}_regional_model_values.csv"
    summary_csv = output_root / f"{label}_ensemble_trend_summary.csv"
    figure = output_root / f"{label}_ensemble_trends.png"
    model_values.to_csv(model_csv, index=False)
    summary.to_csv(summary_csv, index=False)
    plot_trends(summary, figure, args.percentile)
    print(f"WROTE: {model_csv}")
    print(f"WROTE: {summary_csv}")
    print(f"WROTE: {figure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
