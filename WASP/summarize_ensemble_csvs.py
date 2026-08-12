"""Build CSV-only summaries from completed WASP ensemble trend tables."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


GROUP_COLUMNS = ["scenario", "period", "season"]
COMBINATION_COLUMNS = ["percentile", *GROUP_COLUMNS]
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
PERCENTILE_INPUTS = {
    "p98": {"probability": 0.98, "directory": "p98_ensemble_trends"},
    "p99_9": {"probability": 0.999, "directory": "p99_9_ensemble_trends"},
}
SUMMARY_REQUIRED = {
    "scenario", "period", "season", "ensemble_mean", "inter_model_std",
    "model_min", "model_max", "model_count", "units",
}
MODEL_REQUIRED = {
    "model", "scenario", "period", "season", "regional_change", "units",
}


def _require_columns(table: pd.DataFrame, required: set[str], path: Path) -> None:
    missing = sorted(required.difference(table.columns))
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")


def _require_unique(table: pd.DataFrame, columns: list[str], path: Path) -> None:
    duplicated = table.duplicated(columns, keep=False)
    if duplicated.any():
        examples = table.loc[duplicated, columns].head().to_dict("records")
        raise ValueError(f"{path} contains duplicate rows for {columns}: {examples}")


def _numeric(table: pd.DataFrame, columns: list[str], path: Path) -> None:
    for column in columns:
        try:
            table[column] = pd.to_numeric(table[column], errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path} contains nonnumeric values in {column!r}") from exc


def _close(left: pd.Series, right: pd.Series) -> bool:
    return bool(np.allclose(
        left.to_numpy(dtype=float), right.to_numpy(dtype=float),
        rtol=1e-7, atol=1e-10, equal_nan=True,
    ))


def read_percentile_tables(
    outputs_root: str | Path,
    percentile: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read and cross-check one percentile's ensemble and model CSV tables."""
    if percentile not in PERCENTILE_INPUTS:
        raise ValueError(f"Unsupported percentile label: {percentile}")

    outputs_root = Path(outputs_root)
    definition = PERCENTILE_INPUTS[percentile]
    trend_root = outputs_root / str(definition["directory"])
    summary_path = trend_root / f"{percentile}_ensemble_trend_summary.csv"
    model_path = trend_root / f"{percentile}_regional_model_values.csv"
    for path in (summary_path, model_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required WASP result table not found: {path}")

    summary = pd.read_csv(summary_path)
    models = pd.read_csv(model_path)
    _require_columns(summary, SUMMARY_REQUIRED, summary_path)
    _require_columns(models, MODEL_REQUIRED, model_path)
    _require_unique(summary, GROUP_COLUMNS, summary_path)
    _require_unique(models, ["model", *GROUP_COLUMNS], model_path)
    _numeric(
        summary,
        ["ensemble_mean", "inter_model_std", "model_min", "model_max", "model_count"],
        summary_path,
    )
    _numeric(models, ["regional_change"], model_path)

    expected_combinations = {
        (scenario, period, season)
        for scenario in SCENARIOS
        for period in PERIODS
        for season in SEASONS
    }
    summary_combinations = set(summary[GROUP_COLUMNS].itertuples(index=False, name=None))
    model_combinations = set(models[GROUP_COLUMNS].itertuples(index=False, name=None))
    for table_name, combinations in (
        (str(summary_path), summary_combinations),
        (str(model_path), model_combinations),
    ):
        missing = sorted(expected_combinations.difference(combinations))
        unexpected = sorted(combinations.difference(expected_combinations))
        if missing or unexpected:
            raise ValueError(
                f"{table_name} does not contain the expected 36 combinations; "
                f"missing={missing}, unexpected={unexpected}"
            )

    expected_models = set(MODELS)
    for keys, group in models.groupby(GROUP_COLUMNS, sort=False):
        actual_models = set(group["model"].astype(str))
        if actual_models != expected_models:
            raise ValueError(
                f"{model_path} has the wrong models for {keys}: "
                f"missing={sorted(expected_models - actual_models)}, "
                f"unexpected={sorted(actual_models - expected_models)}"
            )
    if not (summary["model_count"] == len(MODELS)).all():
        raise ValueError(
            f"{summary_path} must report model_count={len(MODELS)} for every combination"
        )

    summary_units = set(summary["units"].dropna().astype(str))
    model_units = set(models["units"].dropna().astype(str))
    if len(summary_units) != 1 or summary_units != model_units:
        raise ValueError(
            f"Units do not match between {summary_path} and {model_path}: "
            f"summary={sorted(summary_units)}, models={sorted(model_units)}"
        )

    recalculated = (
        models.groupby(GROUP_COLUMNS, sort=False)["regional_change"]
        .agg(
            checked_mean="mean", checked_std="std", checked_min="min",
            checked_max="max", checked_count="count",
        )
        .reset_index()
    )
    checked = summary.merge(
        recalculated, on=GROUP_COLUMNS, how="outer", validate="one_to_one",
        indicator=True,
    )
    if not (checked["_merge"] == "both").all():
        missing = checked.loc[checked["_merge"] != "both", [*GROUP_COLUMNS, "_merge"]]
        raise ValueError(
            "The ensemble and model tables contain different combinations: "
            f"{missing.to_dict('records')}"
        )

    comparisons = {
        "ensemble_mean": "checked_mean",
        "inter_model_std": "checked_std",
        "model_min": "checked_min",
        "model_max": "checked_max",
        "model_count": "checked_count",
    }
    mismatches = [
        original for original, calculated in comparisons.items()
        if not _close(checked[original], checked[calculated])
    ]
    if mismatches:
        raise ValueError(
            f"{summary_path} does not match values recalculated from {model_path}: "
            f"{', '.join(mismatches)}"
        )

    summary.insert(0, "percentile_probability", float(definition["probability"]))
    summary.insert(0, "percentile", percentile)
    models.insert(0, "percentile_probability", float(definition["probability"]))
    models.insert(0, "percentile", percentile)
    return summary, models


def _direction(value: float, zero_tolerance: float) -> str:
    if value > zero_tolerance:
        return "increase"
    if value < -zero_tolerance:
        return "decrease"
    return "near_zero"


def _agreement_category(fraction: float) -> str:
    if np.isclose(fraction, 1.0):
        return "unanimous"
    if fraction >= 0.8:
        return "strong"
    if fraction > 0.5:
        return "majority"
    return "split"


def build_combination_summary(
    ensemble_summary: pd.DataFrame,
    model_values: pd.DataFrame,
    zero_tolerance: float = 0.0,
) -> pd.DataFrame:
    """Add model direction and model-extreme details to every exact combination."""
    if zero_tolerance < 0:
        raise ValueError("zero_tolerance must be zero or greater")

    records: list[dict[str, object]] = []
    for keys, group in model_values.groupby(COMBINATION_COLUMNS, sort=False):
        percentile, scenario, period, season = keys
        values = group["regional_change"].astype(float)
        directions = values.map(lambda value: _direction(value, zero_tolerance))
        counts = directions.value_counts()
        increase_count = int(counts.get("increase", 0))
        decrease_count = int(counts.get("decrease", 0))
        near_zero_count = int(counts.get("near_zero", 0))
        model_count = len(group)
        count_map = {
            "increase": increase_count,
            "decrease": decrease_count,
            "near_zero": near_zero_count,
        }
        largest_count = max(count_map.values())
        leaders = [name for name, count in count_map.items() if count == largest_count]
        dominant_direction = leaders[0] if len(leaders) == 1 else "split"
        agreement_fraction = largest_count / model_count
        minimum = float(values.min())
        maximum = float(values.max())
        minimum_models = sorted(group.loc[np.isclose(values, minimum), "model"].astype(str))
        maximum_models = sorted(group.loc[np.isclose(values, maximum), "model"].astype(str))
        records.append({
            "percentile": percentile,
            "scenario": scenario,
            "period": period,
            "season": season,
            "minimum_model": "; ".join(minimum_models),
            "maximum_model": "; ".join(maximum_models),
            "increase_count": increase_count,
            "decrease_count": decrease_count,
            "near_zero_count": near_zero_count,
            "dominant_model_direction": dominant_direction,
            "direction_agreement_fraction": agreement_fraction,
            "agreement_category": _agreement_category(agreement_fraction),
            "models_span_zero": increase_count > 0 and decrease_count > 0,
            "increase_models": "; ".join(
                sorted(group.loc[directions == "increase", "model"].astype(str))
            ),
            "decrease_models": "; ".join(
                sorted(group.loc[directions == "decrease", "model"].astype(str))
            ),
            "near_zero_models": "; ".join(
                sorted(group.loc[directions == "near_zero", "model"].astype(str))
            ),
        })

    agreement = pd.DataFrame.from_records(records)
    result = ensemble_summary.merge(
        agreement, on=COMBINATION_COLUMNS, how="inner", validate="one_to_one",
    )
    if len(result) != len(ensemble_summary) or len(result) != len(agreement):
        raise ValueError("Not every ensemble combination has matching model-level values")
    result["ensemble_direction"] = result["ensemble_mean"].map(
        lambda value: _direction(float(value), zero_tolerance)
    )

    ordered = [
        "percentile", "percentile_probability", "scenario", "period", "season",
        "units", "ensemble_mean", "inter_model_std", "model_min", "minimum_model",
        "model_max", "maximum_model", "model_count", "ensemble_direction",
        "increase_count", "decrease_count", "near_zero_count",
        "dominant_model_direction", "direction_agreement_fraction",
        "agreement_category", "models_span_zero", "increase_models",
        "decrease_models", "near_zero_models",
    ]
    return result.loc[:, ordered]


def _progression_pattern(values: list[float], tolerance: float) -> str:
    differences = np.diff(np.asarray(values, dtype=float))
    if np.all(differences > tolerance):
        return "monotonic_increase"
    if np.all(differences < -tolerance):
        return "monotonic_decrease"
    if np.all(np.abs(differences) <= tolerance):
        return "stable"
    return "mixed"


def build_period_progression_summary(
    combinations: pd.DataFrame,
    zero_tolerance: float = 0.0,
) -> pd.DataFrame:
    """Place all three future periods on one row for each percentile/scenario/season."""
    records: list[dict[str, object]] = []
    for keys, group in combinations.groupby(
        ["percentile", "scenario", "season"], sort=False
    ):
        percentile, scenario, season = keys
        by_period = group.set_index("period")
        missing = [period for period in PERIODS if period not in by_period.index]
        if missing:
            raise ValueError(
                f"Missing periods for {percentile} {scenario} {season}: {', '.join(missing)}"
            )
        means = [float(by_period.at[period, "ensemble_mean"]) for period in PERIODS]
        spreads = [float(by_period.at[period, "inter_model_std"]) for period in PERIODS]
        agreements = [
            float(by_period.at[period, "direction_agreement_fraction"])
            for period in PERIODS
        ]
        record: dict[str, object] = {
            "percentile": percentile,
            "percentile_probability": float(by_period["percentile_probability"].iloc[0]),
            "scenario": scenario,
            "season": season,
            "units": str(by_period["units"].iloc[0]),
        }
        for period, mean, spread, agreement in zip(PERIODS, means, spreads, agreements):
            suffix = period.replace("-", "_")
            record[f"ensemble_mean_{suffix}"] = mean
            record[f"inter_model_std_{suffix}"] = spread
            record[f"direction_agreement_fraction_{suffix}"] = agreement
        record["late_minus_early_ensemble_mean"] = means[-1] - means[0]
        record["period_progression_pattern"] = _progression_pattern(
            means, zero_tolerance
        )
        record["minimum_mean_period"] = PERIODS[int(np.argmin(means))]
        record["maximum_mean_period"] = PERIODS[int(np.argmax(means))]
        records.append(record)
    return pd.DataFrame.from_records(records)


def build_combination_tallies(combinations: pd.DataFrame) -> pd.DataFrame:
    """Tally three period-level combinations for each percentile/scenario/season."""
    records: list[dict[str, object]] = []
    group_columns = ["percentile", "scenario", "season"]
    for keys, group in combinations.groupby(group_columns, sort=False):
        percentile, scenario, season = keys
        periods = set(group["period"].astype(str))
        if periods != set(PERIODS):
            raise ValueError(
                f"Cannot tally {percentile} {scenario} {season}; "
                f"expected periods={list(PERIODS)}, found={sorted(periods)}"
            )
        combination_count = len(group)
        model_vote_count = int(group["model_count"].sum())
        ensemble_directions = group["ensemble_direction"].value_counts()
        agreement_categories = group["agreement_category"].value_counts()
        increase_votes = int(group["increase_count"].sum())
        decrease_votes = int(group["decrease_count"].sum())
        near_zero_votes = int(group["near_zero_count"].sum())
        record = {
            "percentile": percentile,
            "percentile_probability": float(group["percentile_probability"].iloc[0]),
            "scenario": scenario,
            "season": season,
            "period_combination_count": combination_count,
            "ensemble_increase_count": int(ensemble_directions.get("increase", 0)),
            "ensemble_decrease_count": int(ensemble_directions.get("decrease", 0)),
            "ensemble_near_zero_count": int(ensemble_directions.get("near_zero", 0)),
            "ensemble_increase_fraction": float(
                ensemble_directions.get("increase", 0) / combination_count
            ),
            "ensemble_decrease_fraction": float(
                ensemble_directions.get("decrease", 0) / combination_count
            ),
            "ensemble_near_zero_fraction": float(
                ensemble_directions.get("near_zero", 0) / combination_count
            ),
            "unanimous_agreement_count": int(agreement_categories.get("unanimous", 0)),
            "strong_agreement_count": int(agreement_categories.get("strong", 0)),
            "majority_agreement_count": int(agreement_categories.get("majority", 0)),
            "split_agreement_count": int(agreement_categories.get("split", 0)),
            "models_span_zero_count": int(group["models_span_zero"].astype(bool).sum()),
            "models_span_zero_fraction": float(
                group["models_span_zero"].astype(bool).mean()
            ),
            "model_vote_count": model_vote_count,
            "model_increase_vote_count": increase_votes,
            "model_decrease_vote_count": decrease_votes,
            "model_near_zero_vote_count": near_zero_votes,
            "model_increase_vote_fraction": increase_votes / model_vote_count,
            "model_decrease_vote_fraction": decrease_votes / model_vote_count,
            "model_near_zero_vote_fraction": near_zero_votes / model_vote_count,
        }
        records.append(record)
    return pd.DataFrame.from_records(records)


def build_progression_tallies(
    progression: pd.DataFrame,
    zero_tolerance: float = 0.0,
) -> pd.DataFrame:
    """Tally four seasonal progression patterns for each percentile/scenario."""
    records: list[dict[str, object]] = []
    for keys, group in progression.groupby(["percentile", "scenario"], sort=False):
        percentile, scenario = keys
        seasons = set(group["season"].astype(str))
        if seasons != set(SEASONS):
            raise ValueError(
                f"Cannot tally {percentile} {scenario}; "
                f"expected seasons={list(SEASONS)}, found={sorted(seasons)}"
            )
        season_count = len(group)
        patterns = group["period_progression_pattern"].value_counts()
        late_change = group["late_minus_early_ensemble_mean"].astype(float)
        late_directions = late_change.map(
            lambda value: _direction(value, zero_tolerance)
        ).value_counts()
        records.append({
            "percentile": percentile,
            "percentile_probability": float(group["percentile_probability"].iloc[0]),
            "scenario": scenario,
            "season_count": season_count,
            "monotonic_increase_count": int(patterns.get("monotonic_increase", 0)),
            "monotonic_decrease_count": int(patterns.get("monotonic_decrease", 0)),
            "stable_count": int(patterns.get("stable", 0)),
            "mixed_count": int(patterns.get("mixed", 0)),
            "monotonic_increase_fraction": float(
                patterns.get("monotonic_increase", 0) / season_count
            ),
            "monotonic_decrease_fraction": float(
                patterns.get("monotonic_decrease", 0) / season_count
            ),
            "stable_fraction": float(patterns.get("stable", 0) / season_count),
            "mixed_fraction": float(patterns.get("mixed", 0) / season_count),
            "late_above_early_count": int(late_directions.get("increase", 0)),
            "late_below_early_count": int(late_directions.get("decrease", 0)),
            "late_equals_early_count": int(late_directions.get("near_zero", 0)),
        })
    return pd.DataFrame.from_records(records)


def summarize_outputs(
    outputs_root: str | Path = "outputs",
    output_dir: str | Path | None = None,
    zero_tolerance: float = 0.0,
) -> tuple[Path, Path, Path, Path]:
    """Validate source CSVs and write detailed summaries plus grouped tallies."""
    outputs_root = Path(outputs_root)
    destination = Path(output_dir) if output_dir else outputs_root / "ensemble_csv_summary"
    ensemble_tables: list[pd.DataFrame] = []
    model_tables: list[pd.DataFrame] = []
    for percentile in PERCENTILE_INPUTS:
        ensemble, models = read_percentile_tables(outputs_root, percentile)
        ensemble_tables.append(ensemble)
        model_tables.append(models)

    combination_summary = build_combination_summary(
        pd.concat(ensemble_tables, ignore_index=True),
        pd.concat(model_tables, ignore_index=True),
        zero_tolerance,
    )
    progression_summary = build_period_progression_summary(
        combination_summary, zero_tolerance
    )
    combination_tallies = build_combination_tallies(combination_summary)
    progression_tallies = build_progression_tallies(
        progression_summary, zero_tolerance
    )
    destination.mkdir(parents=True, exist_ok=True)
    combination_path = destination / "wasp_percentile_combination_summary.csv"
    progression_path = destination / "wasp_percentile_period_progression.csv"
    combination_tally_path = destination / "wasp_percentile_combination_tallies.csv"
    progression_tally_path = destination / "wasp_percentile_progression_tallies.csv"
    combination_summary.to_csv(combination_path, index=False)
    progression_summary.to_csv(progression_path, index=False)
    combination_tallies.to_csv(combination_tally_path, index=False)
    progression_tallies.to_csv(progression_tally_path, index=False)
    return (
        combination_path,
        progression_path,
        combination_tally_path,
        progression_tally_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and summarize completed p98 and p99.9 WASP regional CSV tables."
    )
    parser.add_argument(
        "--outputs-root", default="outputs",
        help="WASP outputs directory containing both ensemble trend directories.",
    )
    parser.add_argument(
        "--output-dir",
        help="Destination directory. Defaults to OUTPUTS_ROOT/ensemble_csv_summary.",
    )
    parser.add_argument(
        "--zero-tolerance", type=float, default=0.0,
        help="Absolute change at or below this value is classified as near zero.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_paths = summarize_outputs(
        outputs_root=args.outputs_root,
        output_dir=args.output_dir,
        zero_tolerance=args.zero_tolerance,
    )
    for output_path in output_paths:
        print(f"WROTE: {output_path}")
    print(
        "NOTE: model direction counts and agreement categories are descriptive; "
        "they are not statistical-significance tests."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
