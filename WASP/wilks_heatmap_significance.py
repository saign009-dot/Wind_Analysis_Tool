"""Run one Wilks-autocorrelation-corrected time-series test per heatmap cell."""
from __future__ import annotations

#reads command-line choices for the annual-series folder, output folder, and alpha
import argparse
#handles the 216 worker inputs and two final CSV destinations consistently
from pathlib import Path

#performs finite-value checks and the lag-1 correlation calculation
import numpy as np
#reads, validates, reshapes, and writes the annual time-series tables
import pandas as pd
#provides the Student t distribution for Welch p-values and confidence intervals
from scipy import stats

#reuses the exact ensemble design used by the existing WASP production workflow
from percentile_ensemble_worker import MODELS, PERIODS, SCENARIOS, SEASONS
#reuses the deterministic worker filename instead of duplicating its path rules
from wilks_annual_percentile_worker import output_path


#the filename-safe labels match the existing p98 and p99.9 heatmap panels
PERCENTILES = ("p98", "p99_9")
#these four fields uniquely identify one of the 72 heatmap cells
CELL_COLUMNS = ["percentile", "scenario", "period", "season"]
#each annual worker CSV must provide every field used in validation or aggregation
ANNUAL_REQUIRED = {
    "model", "scenario", "period", "season", "percentile",
    "percentile_probability", "period_type", "year",
    "regional_percentile_mps", "source_timesteps", "units", "source",
}
#the heatmap reader can use this schema to reject stale FDR-era significance files
SIGNIFICANCE_COLUMNS = [
    "percentile", "scenario", "period", "season", "model_count",
    "models_increase", "models_decrease", "models_near_zero",
    "ensemble_mean_change_mps", "inter_model_sd_mps",
    "historical_years", "future_years",
    "historical_lag1_autocorrelation", "future_lag1_autocorrelation",
    "historical_effective_sample_size", "future_effective_sample_size",
    "welch_t_statistic", "welch_degrees_of_freedom",
    "mean_change_ci_low_mps", "mean_change_ci_high_mps",
    "raw_p_value", "wilks_significant", "alpha", "confidence_level", "units",
]


#checks table structure before later code tries to select a missing field
def _require_columns(table: pd.DataFrame, required: set[str], path: Path) -> None:
    """Raise a direct error when an annual worker table is incomplete."""
    missing = sorted(required.difference(table.columns))
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")


#loads every manifest task and proves its identifying fields match its filename
def read_annual_worker_tables(annual_root: str | Path) -> pd.DataFrame:
    """Read and validate all 216 annual percentile worker CSV files."""
    annual_root = Path(annual_root)
    tables: list[pd.DataFrame] = []
    missing_paths: list[Path] = []

    #the nested loop is deliberately the same 6 x 3 x 3 x 4 ensemble design
    #used to create the manifest, so a missing task cannot silently reduce a cell
    for model in MODELS:
        for scenario in SCENARIOS:
            for period in PERIODS:
                for season in SEASONS:
                    identity = {
                        "model": model,
                        "scenario": scenario,
                        "period": period,
                        "season": season,
                    }
                    path = output_path(annual_root, identity)
                    if not path.is_file():
                        missing_paths.append(path)
                        continue
                    table = pd.read_csv(path)
                    _require_columns(table, ANNUAL_REQUIRED, path)

                    #every row in a task file must belong to the model and heatmap
                    #coordinates encoded in that file's deterministic destination
                    for column, expected in identity.items():
                        actual = set(table[column].dropna().astype(str))
                        if actual != {expected}:
                            raise ValueError(
                                f"{path} has {column}={sorted(actual)}, expected {expected!r}"
                            )
                    tables.append(table)

    if missing_paths:
        examples = "\n".join(f"- {path}" for path in missing_paths[:10])
        remainder = len(missing_paths) - min(10, len(missing_paths))
        suffix = f"\n- ... and {remainder} more" if remainder else ""
        raise FileNotFoundError(
            f"Missing {len(missing_paths)} annual Wilks worker files:\n{examples}{suffix}"
        )

    annual = pd.concat(tables, ignore_index=True)
    numeric_columns = [
        "percentile_probability", "year", "regional_percentile_mps",
        "source_timesteps",
    ]
    for column in numeric_columns:
        try:
            annual[column] = pd.to_numeric(annual[column], errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Annual Wilks inputs contain nonnumeric {column!r}") from exc

    #finite annual values and positive source counts are minimum requirements for
    #a meaningful ordered time series and a reproducible annual percentile
    if not np.isfinite(annual[numeric_columns].to_numpy(dtype=float)).all():
        raise ValueError("Annual Wilks inputs contain nonfinite numeric values")
    if (annual["source_timesteps"] <= 0).any():
        raise ValueError("Annual Wilks inputs contain nonpositive source timestep counts")
    annual["year"] = annual["year"].astype(int)

    #reject misspelled levels and stale worker outputs before forming an ensemble
    expected_levels = {
        "model": set(MODELS),
        "scenario": set(SCENARIOS),
        "period": set(PERIODS),
        "season": set(SEASONS),
        "percentile": set(PERCENTILES),
        "period_type": {"historical", "future"},
    }
    for column, expected in expected_levels.items():
        actual = set(annual[column].astype(str))
        if actual != expected:
            raise ValueError(
                f"Annual Wilks inputs have unexpected {column} levels: "
                f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
            )

    #there must be exactly one value for each model/cell/period-type/year; a
    #duplicate would give that model extra weight in the six-model annual mean
    unique_columns = [
        "model", *CELL_COLUMNS, "period_type", "year",
    ]
    duplicated = annual.duplicated(unique_columns, keep=False)
    if duplicated.any():
        examples = annual.loc[duplicated, unique_columns].head().to_dict("records")
        raise ValueError(f"Annual Wilks inputs contain duplicate annual rows: {examples}")

    units = set(annual["units"].dropna().astype(str))
    if len(units) != 1:
        raise ValueError(f"Annual Wilks input units are inconsistent: {sorted(units)}")
    return annual


#calculates the ordered-series dependence parameter used by the Wilks correction
def lag1_autocorrelation(values: np.ndarray) -> float:
    """Return the Pearson correlation between adjacent annual values."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or values.size < 3 or not np.isfinite(values).all():
        raise ValueError("Lag-1 autocorrelation requires at least three finite values")
    #both lagged slices need variation; otherwise the Pearson correlation is undefined
    if np.ptp(values[:-1]) == 0.0 or np.ptp(values[1:]) == 0.0:
        raise ValueError("Lag-1 autocorrelation is undefined for a constant lagged series")
    correlation = float(np.corrcoef(values[:-1], values[1:])[0, 1])
    if not np.isfinite(correlation):
        raise ValueError("Lag-1 autocorrelation could not be calculated")
    #floating-point roundoff can produce values a few ulps outside the valid range
    return float(np.clip(correlation, -1.0, 1.0))


#turns nominal years into the amount of independent information under an AR(1) model
def wilks_effective_sample_size(sample_size: int, lag1: float) -> float:
    """Return Wilks' lag-1 effective sample size n*(1-rho)/(1+rho)."""
    if isinstance(sample_size, bool) or not isinstance(sample_size, (int, np.integer)):
        raise ValueError("sample_size must be an integer")
    if sample_size < 3:
        raise ValueError("Wilks effective sample size requires at least three years")
    if not np.isfinite(lag1) or not -1.0 < lag1 < 1.0:
        raise ValueError("lag1 must be finite and strictly between -1 and 1")
    effective = float(sample_size * (1.0 - lag1) / (1.0 + lag1))
    #Welch's degrees-of-freedom calculation needs more than one effective value
    if not np.isfinite(effective) or effective <= 1.0:
        raise ValueError(
            f"Wilks effective sample size is {effective:g}; more than one is required"
        )
    return effective


#compares future and historical means after replacing nominal n with Wilks ESS
def wilks_welch_test(
    historical: np.ndarray,
    future: np.ndarray,
    alpha: float = 0.05,
) -> dict[str, float]:
    """Return a two-sided Welch test using Wilks-adjusted sample sizes."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between 0 and 1")
    historical = np.asarray(historical, dtype=float)
    future = np.asarray(future, dtype=float)
    if historical.ndim != 1 or future.ndim != 1:
        raise ValueError("Historical and future values must be one-dimensional")
    if not np.isfinite(historical).all() or not np.isfinite(future).all():
        raise ValueError("Historical and future values must be finite")

    historical_rho = lag1_autocorrelation(historical)
    future_rho = lag1_autocorrelation(future)
    historical_neff = wilks_effective_sample_size(historical.size, historical_rho)
    future_neff = wilks_effective_sample_size(future.size, future_rho)

    historical_mean = float(historical.mean())
    future_mean = float(future.mean())
    mean_change = future_mean - historical_mean
    historical_variance = float(historical.var(ddof=1))
    future_variance = float(future.var(ddof=1))
    historical_mean_variance = historical_variance / historical_neff
    future_mean_variance = future_variance / future_neff
    standard_error_squared = historical_mean_variance + future_mean_variance
    if not np.isfinite(standard_error_squared) or standard_error_squared <= 0.0:
        raise ValueError("Wilks-adjusted Welch standard error must be positive")
    standard_error = float(np.sqrt(standard_error_squared))

    #Welch-Satterthwaite degrees of freedom allow different period variances and
    #the fractional effective sample sizes produced by the Wilks formula
    degrees_of_freedom = float(
        standard_error_squared ** 2
        / (
            historical_mean_variance ** 2 / (historical_neff - 1.0)
            + future_mean_variance ** 2 / (future_neff - 1.0)
        )
    )
    if not np.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0.0:
        raise ValueError("Welch degrees of freedom must be positive and finite")

    t_statistic = mean_change / standard_error
    raw_p_value = float(2.0 * stats.t.sf(abs(t_statistic), degrees_of_freedom))
    critical_t = float(stats.t.ppf(1.0 - alpha / 2.0, degrees_of_freedom))
    confidence_margin = critical_t * standard_error
    return {
        "historical_lag1_autocorrelation": historical_rho,
        "future_lag1_autocorrelation": future_rho,
        "historical_effective_sample_size": historical_neff,
        "future_effective_sample_size": future_neff,
        "welch_t_statistic": t_statistic,
        "welch_degrees_of_freedom": degrees_of_freedom,
        "mean_change_ci_low_mps": mean_change - confidence_margin,
        "mean_change_ci_high_mps": mean_change + confidence_margin,
        "raw_p_value": raw_p_value,
    }


#requires a complete six-model cross-section for every retained calendar year
def combined_ensemble_series(
    cell: pd.DataFrame,
    period_type: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ordered years and the year-by-year mean across all six models."""
    selected = cell[cell["period_type"] == period_type]
    pivot = selected.pivot(index="year", columns="model", values="regional_percentile_mps")
    pivot = pivot.reindex(columns=MODELS).sort_index()
    if pivot.empty or pivot.isna().any().any():
        raise ValueError(
            f"{period_type} series does not contain all six models in every year"
        )
    if len(pivot) < 3:
        raise ValueError(f"{period_type} ensemble series has fewer than three years")
    years = pivot.index.to_numpy(dtype=int)
    values = pivot.mean(axis=1).to_numpy(dtype=float)
    return years, values


#creates the transparent ensemble series and one inferential row for each heatmap cell
def build_wilks_results(
    annual: pd.DataFrame,
    alpha: float = 0.05,
    zero_tolerance: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build combined annual series and 72 Wilks-corrected Welch test rows."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between 0 and 1")
    if zero_tolerance < 0.0:
        raise ValueError("zero_tolerance must be zero or greater")

    significance_records: list[dict[str, object]] = []
    series_records: list[dict[str, object]] = []
    units = str(annual["units"].iloc[0])
    for keys, cell in annual.groupby(CELL_COLUMNS, sort=False):
        percentile, scenario, period, season = keys
        historical_years, historical = combined_ensemble_series(cell, "historical")
        future_years, future = combined_ensemble_series(cell, "future")
        test = wilks_welch_test(historical, future, alpha=alpha)

        #the heatmap's direction counts use the same annual-percentile statistic as
        #the test: each model's future annual mean minus its historical annual mean
        model_period_means = (
            cell.groupby(["model", "period_type"])["regional_percentile_mps"]
            .mean()
            .unstack("period_type")
            .reindex(MODELS)
        )
        if model_period_means[["historical", "future"]].isna().any().any():
            raise ValueError(f"Cell {keys} is missing a model-period annual mean")
        model_changes = (
            model_period_means["future"] - model_period_means["historical"]
        ).to_numpy(dtype=float)
        increases = int(np.count_nonzero(model_changes > zero_tolerance))
        decreases = int(np.count_nonzero(model_changes < -zero_tolerance))
        near_zero = int(len(model_changes) - increases - decreases)

        significance_records.append({
            "percentile": percentile,
            "scenario": scenario,
            "period": period,
            "season": season,
            "model_count": len(model_changes),
            "models_increase": increases,
            "models_decrease": decreases,
            "models_near_zero": near_zero,
            "ensemble_mean_change_mps": float(future.mean() - historical.mean()),
            "inter_model_sd_mps": float(model_changes.std(ddof=1)),
            "historical_years": len(historical_years),
            "future_years": len(future_years),
            **test,
            #no FDR or other multiplicity adjustment is applied; this raw decision
            #implements the advisor's requested one-test-per-heatmap-cell method
            "wilks_significant": bool(test["raw_p_value"] < alpha),
            "alpha": alpha,
            "confidence_level": 1.0 - alpha,
            "units": units,
        })

        #save both ordered input series so every displayed p-value can be audited
        for period_type, years, values in (
            ("historical", historical_years, historical),
            ("future", future_years, future),
        ):
            for year, value in zip(years, values):
                series_records.append({
                    "percentile": percentile,
                    "scenario": scenario,
                    "period": period,
                    "season": season,
                    "period_type": period_type,
                    "year": int(year),
                    "combined_ensemble_percentile_mps": float(value),
                    "model_count": len(MODELS),
                    "units": units,
                })

    significance = pd.DataFrame.from_records(significance_records)
    expected_cells = len(PERCENTILES) * len(SCENARIOS) * len(PERIODS) * len(SEASONS)
    if len(significance) != expected_cells:
        raise ValueError(
            f"Expected {expected_cells} Wilks heatmap tests; found {len(significance)}"
        )
    significance = significance[SIGNIFICANCE_COLUMNS]
    combined_series = pd.DataFrame.from_records(series_records)
    return significance, combined_series


#runs validation, calculations, and full-precision CSV output as one reusable workflow
def calculate_wilks_outputs(
    annual_root: str | Path = "outputs/wilks_annual_percentiles",
    output_dir: str | Path = "outputs/ensemble_csv_summary",
    alpha: float = 0.05,
    zero_tolerance: float = 0.0,
) -> tuple[Path, Path]:
    """Calculate and write the cell tests and combined annual input series."""
    annual = read_annual_worker_tables(annual_root)
    significance, combined_series = build_wilks_results(
        annual, alpha=alpha, zero_tolerance=zero_tolerance
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    significance_path = output_dir / "wasp_heatmap_wilks_significance.csv"
    series_path = output_dir / "wasp_combined_ensemble_annual_percentiles.csv"
    #inferential values retain full precision so small p-values and ESS values are not lost
    significance.to_csv(significance_path, index=False)
    combined_series.to_csv(series_path, index=False)
    return significance_path, series_path


#defines the standalone command used after all 216 Slurm array tasks finish
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one combined-ensemble Wilks-corrected time-series test per heatmap cell."
        )
    )
    parser.add_argument(
        "--annual-root", default="outputs/wilks_annual_percentiles",
        help="Directory containing all 216 annual percentile worker CSVs.",
    )
    parser.add_argument(
        "--output-dir", default="outputs/ensemble_csv_summary",
        help="Destination for Wilks test and combined annual-series CSVs.",
    )
    parser.add_argument(
        "--alpha", type=float, default=0.05,
        help="Per-cell raw significance level; 0.05 also produces 95%% CIs.",
    )
    parser.add_argument(
        "--zero-tolerance", type=float, default=0.0,
        help="Absolute model change at or below this value counts as near zero.",
    )
    return parser


#executes the complete aggregation and prints paths suitable for MSI logs
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = calculate_wilks_outputs(
        annual_root=args.annual_root,
        output_dir=args.output_dir,
        alpha=args.alpha,
        zero_tolerance=args.zero_tolerance,
    )
    for path in paths:
        print(f"WROTE: {path}")
    print(
        "NOTE: each heatmap cell has one raw two-sided Welch p-value using "
        "Wilks lag-1 effective sample sizes; no FDR correction is applied."
    )
    return 0


#importing the calculation functions into tests does not execute the command line
if __name__ == "__main__":
    raise SystemExit(main())
