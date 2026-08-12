"""Build CSV-only summaries from completed WASP ensemble trend tables."""

#overall flow is find the four trend csv files -> validate them -> rebuild the
#ensemble statistics from the model rows -> add direction and agreement fields
#-> put the three periods beside each other -> create grouped tally csv files

#allows modern type hints to work consistently with the supported python versions
from __future__ import annotations

#reads command line options when this program is run from the MSI terminal
import argparse
#handles input and output paths in a way that works on MSI and other computers
from pathlib import Path

#used for number comparisons, differences, minimums, and maximums
import numpy as np
#used to read, group, merge, check, and write all of the csv tables
import pandas as pd


#these columns identify one scenario/period/season result within one percentile table
GROUP_COLUMNS = ["scenario", "period", "season"]
#percentile must be included after the p98 and p99.9 tables are joined together
COMBINATION_COLUMNS = ["percentile", *GROUP_COLUMNS]
#the exact six models expected in every ensemble combination
#keeping this list explicit prevents a missing model from quietly changing n=6
MODELS = (
    "BCC-CSM2-MR",
    "CESM2",
    "CMCC-ESM2",
    "CNRM-ESM2-1",
    "IPSL-CM6A-LR",
    "MIROC-ES2L",
)
#the three future emissions scenarios used throughout the WASP analysis
SCENARIOS = ("ssp245", "ssp370", "ssp585")
#the three future time windows compared to the 1995-2014 historical baseline
PERIODS = ("2040-2059", "2060-2079", "2080-2099")
#the four meteorological seasons used in the source data
SEASONS = ("DJF", "MAM", "JJA", "SON")
#connects each filename-safe percentile label to its probability and output folder
PERCENTILE_INPUTS = {
    "p98": {"probability": 0.98, "directory": "p98_ensemble_trends"},
    "p99_9": {"probability": 0.999, "directory": "p99_9_ensemble_trends"},
}
#columns that must exist in each six-model ensemble summary csv
SUMMARY_REQUIRED = {
    "scenario", "period", "season", "ensemble_mean", "inter_model_std",
    "model_min", "model_max", "model_count", "units",
}
#columns that must exist in each individual-model regional-value csv
MODEL_REQUIRED = {
    "model", "scenario", "period", "season", "regional_change", "units",
}


#checks that a table has every column the rest of the program needs
def _require_columns(table: pd.DataFrame, required: set[str], path: Path) -> None:
    #subtract the actual column names from the required names to find anything missing
    missing = sorted(required.difference(table.columns))
    #stop here instead of failing later with a less useful missing-column error
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")


#checks that the columns that identify a result do not appear more than once
def _require_unique(table: pd.DataFrame, columns: list[str], path: Path) -> None:
    #keep=False marks every copy of a duplicate so the error can show examples
    duplicated = table.duplicated(columns, keep=False)
    #duplicate combinations would count one result more than once in later tallies
    if duplicated.any():
        #only show the first few duplicates so the error message stays readable
        examples = table.loc[duplicated, columns].head().to_dict("records")
        raise ValueError(f"{path} contains duplicate rows for {columns}: {examples}")


#converts calculation columns to numbers and rejects text accidentally stored in them
def _numeric(table: pd.DataFrame, columns: list[str], path: Path) -> None:
    #check each requested calculation column separately so the error names the problem
    for column in columns:
        try:
            #errors=raise prevents bad values from quietly becoming missing values
            table[column] = pd.to_numeric(table[column], errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path} contains nonnumeric values in {column!r}") from exc


#compares two calculated columns while allowing tiny floating-point rounding differences
def _close(left: pd.Series, right: pd.Series) -> bool:
    #convert both pandas columns to plain floating-point arrays before comparing them
    return bool(np.allclose(
        left.to_numpy(dtype=float), right.to_numpy(dtype=float),
        #the tolerances are small enough to catch real differences but ignore csv rounding
        rtol=1e-7, atol=1e-10, equal_nan=True,
    ))


#reads one percentile's two source csv files and proves that they agree
def read_percentile_tables(
    outputs_root: str | Path,
    percentile: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read and cross-check one percentile's ensemble and model CSV tables."""
    #only p98 and p99.9 are supported because those are the WASP production runs
    if percentile not in PERCENTILE_INPUTS:
        raise ValueError(f"Unsupported percentile label: {percentile}")

    #normalize the root into a Path so joining folders works on any operating system
    outputs_root = Path(outputs_root)
    #look up the probability and folder that belong to this percentile label
    definition = PERCENTILE_INPUTS[percentile]
    #build the exact default paths created by percentile_ensemble_trends.py
    trend_root = outputs_root / str(definition["directory"])
    summary_path = trend_root / f"{percentile}_ensemble_trend_summary.csv"
    model_path = trend_root / f"{percentile}_regional_model_values.csv"
    #both files are required because the ensemble table is checked against model values
    for path in (summary_path, model_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required WASP result table not found: {path}")

    #read the six-model ensemble statistics and the individual model values
    summary = pd.read_csv(summary_path)
    models = pd.read_csv(model_path)
    #check table structure before performing calculations with the columns
    _require_columns(summary, SUMMARY_REQUIRED, summary_path)
    _require_columns(models, MODEL_REQUIRED, model_path)
    #there must be one ensemble row and six uniquely named model rows per combination
    _require_unique(summary, GROUP_COLUMNS, summary_path)
    _require_unique(models, ["model", *GROUP_COLUMNS], model_path)
    #force every stored calculation into numeric form so invalid csv contents stop the run
    _numeric(
        summary,
        ["ensemble_mean", "inter_model_std", "model_min", "model_max", "model_count"],
        summary_path,
    )
    _numeric(models, ["regional_change"], model_path)

    #build all 3 scenarios x 3 periods x 4 seasons = 36 expected combinations
    expected_combinations = {
        (scenario, period, season)
        for scenario in SCENARIOS
        for period in PERIODS
        for season in SEASONS
    }
    #turn the combinations actually found in each table into sets for exact comparison
    summary_combinations = set(summary[GROUP_COLUMNS].itertuples(index=False, name=None))
    model_combinations = set(models[GROUP_COLUMNS].itertuples(index=False, name=None))
    #apply the same missing/unexpected-combination check to both source tables
    for table_name, combinations in (
        (str(summary_path), summary_combinations),
        (str(model_path), model_combinations),
    ):
        #missing lists required results that did not appear in the table
        missing = sorted(expected_combinations.difference(combinations))
        #unexpected catches spelling errors or results outside the planned design
        unexpected = sorted(combinations.difference(expected_combinations))
        if missing or unexpected:
            raise ValueError(
                f"{table_name} does not contain the expected 36 combinations; "
                f"missing={missing}, unexpected={unexpected}"
            )

    #convert the expected model tuple to a set because order does not matter here
    expected_models = set(MODELS)
    #inspect the six model rows belonging to every scenario/period/season combination
    for keys, group in models.groupby(GROUP_COLUMNS, sort=False):
        #cast model names to strings before comparing them with the expected names
        actual_models = set(group["model"].astype(str))
        #stop if any model is missing, repeated under another name, or unexpected
        if actual_models != expected_models:
            raise ValueError(
                f"{model_path} has the wrong models for {keys}: "
                f"missing={sorted(expected_models - actual_models)}, "
                f"unexpected={sorted(actual_models - expected_models)}"
            )
    #the ensemble file must also report n=6 for every row
    if not (summary["model_count"] == len(MODELS)).all():
        raise ValueError(
            f"{summary_path} must report model_count={len(MODELS)} for every combination"
        )

    #collect the physical units recorded in each source table
    summary_units = set(summary["units"].dropna().astype(str))
    model_units = set(models["units"].dropna().astype(str))
    #one consistent unit must exist and it must match between both tables
    if len(summary_units) != 1 or summary_units != model_units:
        raise ValueError(
            f"Units do not match between {summary_path} and {model_path}: "
            f"summary={sorted(summary_units)}, models={sorted(model_units)}"
        )

    #recalculate the ensemble statistics directly from the six regional model values
    #pandas std uses sample standard deviation with ddof=1, matching the WASP workflow
    recalculated = (
        models.groupby(GROUP_COLUMNS, sort=False)["regional_change"]
        .agg(
            checked_mean="mean", checked_std="std", checked_min="min",
            checked_max="max", checked_count="count",
        )
        .reset_index()
    )
    #join stored and recalculated values so every statistic can be compared row by row
    checked = summary.merge(
        recalculated, on=GROUP_COLUMNS, how="outer", validate="one_to_one",
        indicator=True,
    )
    #outer merge plus this check proves both tables contain the same combinations
    if not (checked["_merge"] == "both").all():
        #show the combinations found on only one side of the merge
        missing = checked.loc[checked["_merge"] != "both", [*GROUP_COLUMNS, "_merge"]]
        raise ValueError(
            "The ensemble and model tables contain different combinations: "
            f"{missing.to_dict('records')}"
        )

    #map each original ensemble column to the version recalculated from model rows
    comparisons = {
        "ensemble_mean": "checked_mean",
        "inter_model_std": "checked_std",
        "model_min": "checked_min",
        "model_max": "checked_max",
        "model_count": "checked_count",
    }
    #record the names of any stored statistics that do not reproduce
    mismatches = [
        original for original, calculated in comparisons.items()
        if not _close(checked[original], checked[calculated])
    ]
    #do not summarize a table if its ensemble results disagree with its source models
    if mismatches:
        raise ValueError(
            f"{summary_path} does not match values recalculated from {model_path}: "
            f"{', '.join(mismatches)}"
        )

    #add percentile identity to both tables before p98 and p99.9 are combined
    #insert at column zero keeps the identifying fields at the front of output tables
    summary.insert(0, "percentile_probability", float(definition["probability"]))
    summary.insert(0, "percentile", percentile)
    models.insert(0, "percentile_probability", float(definition["probability"]))
    models.insert(0, "percentile", percentile)
    #return the checked tables so later functions do not have to reread the files
    return summary, models


#turns one wind-speed change into a plain-language direction category
def _direction(value: float, zero_tolerance: float) -> str:
    #a value larger than the allowed near-zero range is an increase
    if value > zero_tolerance:
        return "increase"
    #a value smaller than the negative tolerance is a decrease
    if value < -zero_tolerance:
        return "decrease"
    #values between the positive and negative limits are treated as near zero
    return "near_zero"


#turns the largest model-direction fraction into an easy-to-tally agreement label
def _agreement_category(fraction: float) -> str:
    #all six models point in the same direction
    if np.isclose(fraction, 1.0):
        return "unanimous"
    #five of six models point in the same direction because 5/6 is about 0.833
    if fraction >= 0.8:
        return "strong"
    #four of six models point in the same direction
    if fraction > 0.5:
        return "majority"
    #no direction has more than half of the six models
    return "split"


#creates the detailed 72-row table with one row for every exact result combination
def build_combination_summary(
    ensemble_summary: pd.DataFrame,
    model_values: pd.DataFrame,
    zero_tolerance: float = 0.0,
) -> pd.DataFrame:
    """Add model direction and model-extreme details to every exact combination."""
    #negative tolerance would make the increase/decrease boundaries overlap
    if zero_tolerance < 0:
        raise ValueError("zero_tolerance must be zero or greater")

    #each dictionary appended here will become one output csv row
    records: list[dict[str, object]] = []
    #split the model table into six-row groups identified by percentile/scenario/period/season
    for keys, group in model_values.groupby(COMBINATION_COLUMNS, sort=False):
        #unpack the group identity into clearly named variables
        percentile, scenario, period, season = keys
        #regional_change is the future-minus-historical area-weighted Minnesota value
        values = group["regional_change"].astype(float)
        #classify each of the six model values as increase, decrease, or near zero
        directions = values.map(lambda value: _direction(value, zero_tolerance))
        #count how many of the six models fall into each direction
        counts = directions.value_counts()
        #get returns zero when a direction is absent instead of raising an error
        increase_count = int(counts.get("increase", 0))
        decrease_count = int(counts.get("decrease", 0))
        near_zero_count = int(counts.get("near_zero", 0))
        #this should be six after the earlier validation and is kept explicit for fractions
        model_count = len(group)
        #store the three counts under their names so the largest one can be found
        count_map = {
            "increase": increase_count,
            "decrease": decrease_count,
            "near_zero": near_zero_count,
        }
        #the largest count represents the direction with the most model support
        largest_count = max(count_map.values())
        #there can be multiple leaders when the models are evenly split
        leaders = [name for name, count in count_map.items() if count == largest_count]
        #only name a dominant direction when exactly one direction leads
        dominant_direction = leaders[0] if len(leaders) == 1 else "split"
        #example: five models pointing the same way gives 5/6 = 0.833 agreement
        agreement_fraction = largest_count / model_count
        #find the smallest and largest model-level regional changes in this group
        minimum = float(values.min())
        maximum = float(values.max())
        #np.isclose allows tied extreme models despite tiny floating-point differences
        minimum_models = sorted(group.loc[np.isclose(values, minimum), "model"].astype(str))
        maximum_models = sorted(group.loc[np.isclose(values, maximum), "model"].astype(str))
        #save identities, counts, agreement, and model-name lists as one output row
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
            #agreement category translates 6/6, 5/6, 4/6, and split outcomes
            "agreement_category": _agreement_category(agreement_fraction),
            #true means at least one model increases and at least one decreases
            "models_span_zero": increase_count > 0 and decrease_count > 0,
            #semicolon-separated names keep multiple models readable in one csv cell
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

    #turn the list of dictionaries into a pandas table
    agreement = pd.DataFrame.from_records(records)
    #add the new model-direction fields to the original ensemble statistics
    result = ensemble_summary.merge(
        agreement, on=COMBINATION_COLUMNS, how="inner", validate="one_to_one",
    )
    #an inner merge could drop an unmatched row, so compare lengths to catch that
    if len(result) != len(ensemble_summary) or len(result) != len(agreement):
        raise ValueError("Not every ensemble combination has matching model-level values")
    #classify the six-model ensemble mean using the same direction boundaries
    result["ensemble_direction"] = result["ensemble_mean"].map(
        lambda value: _direction(float(value), zero_tolerance)
    )

    #set a deliberate column order so identifying and statistical fields are easy to read
    ordered = [
        "percentile", "percentile_probability", "scenario", "period", "season",
        "units", "ensemble_mean", "inter_model_std", "model_min", "minimum_model",
        "model_max", "maximum_model", "model_count", "ensemble_direction",
        "increase_count", "decrease_count", "near_zero_count",
        "dominant_model_direction", "direction_agreement_fraction",
        "agreement_category", "models_span_zero", "increase_models",
        "decrease_models", "near_zero_models",
    ]
    #return only the documented columns in the order listed above
    return result.loc[:, ordered]


#describes whether the three ensemble means move consistently through future time
def _progression_pattern(values: list[float], tolerance: float) -> str:
    #subtract early from middle and middle from late to get the two period steps
    differences = np.diff(np.asarray(values, dtype=float))
    #both steps larger than tolerance means the series increases each period
    if np.all(differences > tolerance):
        return "monotonic_increase"
    #both steps smaller than negative tolerance means the series decreases each period
    if np.all(differences < -tolerance):
        return "monotonic_decrease"
    #both steps within tolerance means there is no meaningful period-to-period movement
    if np.all(np.abs(differences) <= tolerance):
        return "stable"
    #anything that reverses direction or has only one stable step is labeled mixed
    return "mixed"


#creates a 24-row table that places all three periods beside each other
def build_period_progression_summary(
    combinations: pd.DataFrame,
    zero_tolerance: float = 0.0,
) -> pd.DataFrame:
    """Place all three future periods on one row for each percentile/scenario/season."""
    #each output row is collected as a dictionary before pandas builds the final table
    records: list[dict[str, object]] = []
    #group across periods while keeping percentile, scenario, and season separate
    for keys, group in combinations.groupby(
        ["percentile", "scenario", "season"], sort=False
    ):
        #name the three identifiers shared by every row in this group
        percentile, scenario, season = keys
        #make period the lookup index so values can be pulled in chronological order
        by_period = group.set_index("period")
        #list any required future periods that are absent from the group
        missing = [period for period in PERIODS if period not in by_period.index]
        #all three periods are necessary to describe a progression through time
        if missing:
            raise ValueError(
                f"Missing periods for {percentile} {scenario} {season}: {', '.join(missing)}"
            )
        #read means in the fixed early, middle, late order defined by PERIODS
        means = [float(by_period.at[period, "ensemble_mean"]) for period in PERIODS]
        #read inter-model sample standard deviations in the same order
        spreads = [float(by_period.at[period, "inter_model_std"]) for period in PERIODS]
        #read the model-direction agreement fractions in the same order
        agreements = [
            float(by_period.at[period, "direction_agreement_fraction"])
            for period in PERIODS
        ]
        #begin the wide output row with fields shared by all three periods
        record: dict[str, object] = {
            "percentile": percentile,
            "percentile_probability": float(by_period["percentile_probability"].iloc[0]),
            "scenario": scenario,
            "season": season,
            "units": str(by_period["units"].iloc[0]),
        }
        #add mean, spread, and agreement columns for each individual period
        for period, mean, spread, agreement in zip(PERIODS, means, spreads, agreements):
            #replace the dash so the period can be safely used inside a column name
            suffix = period.replace("-", "_")
            record[f"ensemble_mean_{suffix}"] = mean
            record[f"inter_model_std_{suffix}"] = spread
            record[f"direction_agreement_fraction_{suffix}"] = agreement
        #positive means the late-century ensemble mean is above the early-century mean
        record["late_minus_early_ensemble_mean"] = means[-1] - means[0]
        #classify the two steps between the three future periods
        record["period_progression_pattern"] = _progression_pattern(
            means, zero_tolerance
        )
        #record which future period has the lowest and highest ensemble mean
        record["minimum_mean_period"] = PERIODS[int(np.argmin(means))]
        record["maximum_mean_period"] = PERIODS[int(np.argmax(means))]
        #save the completed wide row
        records.append(record)
    #convert all 24 percentile/scenario/season records into the progression table
    return pd.DataFrame.from_records(records)


#tallies the three period-level rows without mixing percentile/scenario/season groups
def build_combination_tallies(combinations: pd.DataFrame) -> pd.DataFrame:
    """Tally three period-level combinations for each percentile/scenario/season."""
    #each dictionary becomes one of 24 grouped tally rows
    records: list[dict[str, object]] = []
    #period is intentionally left out because the three periods are being tallied
    group_columns = ["percentile", "scenario", "season"]
    #make one group containing three period rows for every percentile/scenario/season
    for keys, group in combinations.groupby(group_columns, sort=False):
        #unpack the identifiers that remain visible in the tally output
        percentile, scenario, season = keys
        #collect the period labels actually found in this group
        periods = set(group["period"].astype(str))
        #do not produce a tally if a period is missing or unexpected
        if periods != set(PERIODS):
            raise ValueError(
                f"Cannot tally {percentile} {scenario} {season}; "
                f"expected periods={list(PERIODS)}, found={sorted(periods)}"
            )
        #there should be three ensemble combinations, one for each future period
        combination_count = len(group)
        #three periods x six models gives 18 individual model direction votes
        model_vote_count = int(group["model_count"].sum())
        #count how many period-level ensemble means increase, decrease, or stay near zero
        ensemble_directions = group["ensemble_direction"].value_counts()
        #count how many periods have unanimous, strong, majority, or split model agreement
        agreement_categories = group["agreement_category"].value_counts()
        #sum the six-model direction counts across all three periods
        increase_votes = int(group["increase_count"].sum())
        decrease_votes = int(group["decrease_count"].sum())
        near_zero_votes = int(group["near_zero_count"].sum())
        #store raw counts and fractions together so every tally has a denominator
        record = {
            "percentile": percentile,
            "percentile_probability": float(group["percentile_probability"].iloc[0]),
            "scenario": scenario,
            "season": season,
            "period_combination_count": combination_count,
            #get supplies zero when none of the three periods has that direction
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
            #agreement counts describe model consensus, not statistical significance
            "unanimous_agreement_count": int(agreement_categories.get("unanimous", 0)),
            "strong_agreement_count": int(agreement_categories.get("strong", 0)),
            "majority_agreement_count": int(agreement_categories.get("majority", 0)),
            "split_agreement_count": int(agreement_categories.get("split", 0)),
            #span zero means at least one model increases and another decreases
            "models_span_zero_count": int(group["models_span_zero"].astype(bool).sum()),
            "models_span_zero_fraction": float(
                group["models_span_zero"].astype(bool).mean()
            ),
            #model vote fields preserve the underlying 18 individual model outcomes
            "model_vote_count": model_vote_count,
            "model_increase_vote_count": increase_votes,
            "model_decrease_vote_count": decrease_votes,
            "model_near_zero_vote_count": near_zero_votes,
            "model_increase_vote_fraction": increase_votes / model_vote_count,
            "model_decrease_vote_fraction": decrease_votes / model_vote_count,
            "model_near_zero_vote_fraction": near_zero_votes / model_vote_count,
        }
        #save the completed tally row before moving to the next group
        records.append(record)
    #return one row for each 2 percentiles x 3 scenarios x 4 seasons = 24 groups
    return pd.DataFrame.from_records(records)


#tallies the four seasonal progression rows without mixing percentiles or scenarios
def build_progression_tallies(
    progression: pd.DataFrame,
    zero_tolerance: float = 0.0,
) -> pd.DataFrame:
    """Tally four seasonal progression patterns for each percentile/scenario."""
    #each dictionary becomes one of six percentile/scenario tally rows
    records: list[dict[str, object]] = []
    #season is intentionally left out because all four seasons are being tallied
    for keys, group in progression.groupby(["percentile", "scenario"], sort=False):
        #keep percentile and scenario as identifiers in the tally output
        percentile, scenario = keys
        #collect the season labels found in this group
        seasons = set(group["season"].astype(str))
        #all four seasons must be present for a complete progression tally
        if seasons != set(SEASONS):
            raise ValueError(
                f"Cannot tally {percentile} {scenario}; "
                f"expected seasons={list(SEASONS)}, found={sorted(seasons)}"
            )
        #the denominator is four because the group contains DJF, MAM, JJA, and SON
        season_count = len(group)
        #count the four progression categories across the seasonal rows
        patterns = group["period_progression_pattern"].value_counts()
        #late_change compares the 2080-2099 mean with the 2040-2059 mean
        late_change = group["late_minus_early_ensemble_mean"].astype(float)
        #classify each season's late-minus-early value with the requested tolerance
        late_directions = late_change.map(
            lambda value: _direction(value, zero_tolerance)
        ).value_counts()
        #store progression counts, fractions, and late-versus-early counts in one row
        records.append({
            "percentile": percentile,
            "percentile_probability": float(group["percentile_probability"].iloc[0]),
            "scenario": scenario,
            "season_count": season_count,
            #get returns zero when none of the four seasons follows a pattern
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
            #these fields only compare the late and early endpoints
            "late_above_early_count": int(late_directions.get("increase", 0)),
            "late_below_early_count": int(late_directions.get("decrease", 0)),
            "late_equals_early_count": int(late_directions.get("near_zero", 0)),
        })
    #return one row for each 2 percentiles x 3 scenarios = 6 groups
    return pd.DataFrame.from_records(records)


#runs the complete validation, summary, progression, and tally workflow
def summarize_outputs(
    outputs_root: str | Path = "outputs",
    output_dir: str | Path | None = None,
    zero_tolerance: float = 0.0,
) -> tuple[Path, Path, Path, Path]:
    """Validate source CSVs and write detailed summaries plus grouped tallies."""
    #convert the source output folder into a Path for consistent path joining
    outputs_root = Path(outputs_root)
    #use a requested destination or default to a new folder under WASP outputs
    destination = Path(output_dir) if output_dir else outputs_root / "ensemble_csv_summary"
    #hold the checked p98 and p99.9 ensemble tables until they can be joined
    ensemble_tables: list[pd.DataFrame] = []
    #hold the checked p98 and p99.9 model-value tables until they can be joined
    model_tables: list[pd.DataFrame] = []
    #read and validate each percentile with the same rules
    for percentile in PERCENTILE_INPUTS:
        #read_percentile_tables also proves stored ensemble stats match the six models
        ensemble, models = read_percentile_tables(outputs_root, percentile)
        ensemble_tables.append(ensemble)
        model_tables.append(models)

    #join percentiles and make the 72-row detailed combination table
    combination_summary = build_combination_summary(
        pd.concat(ensemble_tables, ignore_index=True),
        pd.concat(model_tables, ignore_index=True),
        zero_tolerance,
    )
    #reshape the detailed table into 24 rows with all three periods side by side
    progression_summary = build_period_progression_summary(
        combination_summary, zero_tolerance
    )
    #tally the three periods within each percentile/scenario/season group
    combination_tallies = build_combination_tallies(combination_summary)
    #tally the four seasonal progression patterns within each percentile/scenario group
    progression_tallies = build_progression_tallies(
        progression_summary, zero_tolerance
    )
    #create the destination only after all validation and calculations succeed
    destination.mkdir(parents=True, exist_ok=True)
    #give every product a descriptive and non-colliding filename
    combination_path = destination / "wasp_percentile_combination_summary.csv"
    progression_path = destination / "wasp_percentile_period_progression.csv"
    combination_tally_path = destination / "wasp_percentile_combination_tallies.csv"
    progression_tally_path = destination / "wasp_percentile_progression_tallies.csv"
    #write plain csv files without pandas row numbers
    combination_summary.to_csv(combination_path, index=False)
    progression_summary.to_csv(progression_path, index=False)
    combination_tallies.to_csv(combination_tally_path, index=False)
    progression_tallies.to_csv(progression_tally_path, index=False)
    #return every created path so the command line can print them for the user
    return (
        combination_path,
        progression_path,
        combination_tally_path,
        progression_tally_path,
    )


#defines the terminal options for running the program on MSI or another computer
def build_parser() -> argparse.ArgumentParser:
    #the description appears when python summarize_ensemble_csvs.py --help is run
    parser = argparse.ArgumentParser(
        description="Validate and summarize completed p98 and p99.9 WASP regional CSV tables."
    )
    #source root defaults to the standard WASP outputs directory
    parser.add_argument(
        "--outputs-root", default="outputs",
        help="WASP outputs directory containing both ensemble trend directories.",
    )
    #optional output override leaves the standard source directory unchanged
    parser.add_argument(
        "--output-dir",
        help="Destination directory. Defaults to OUTPUTS_ROOT/ensemble_csv_summary.",
    )
    #optional tolerance lets very small changes be treated as near zero
    parser.add_argument(
        "--zero-tolerance", type=float, default=0.0,
        help="Absolute change at or below this value is classified as near zero.",
    )
    #return the configured parser so main can parse the actual command line
    return parser


#command-line entry point that runs the workflow and reports created files
def main(argv: list[str] | None = None) -> int:
    #parse either the real command line or an argument list supplied by a caller
    args = build_parser().parse_args(argv)
    #run every validation and create all four output csv files
    output_paths = summarize_outputs(
        outputs_root=args.outputs_root,
        output_dir=args.output_dir,
        zero_tolerance=args.zero_tolerance,
    )
    #print each final path so the files are easy to locate on MSI
    for output_path in output_paths:
        print(f"WROTE: {output_path}")
    #warn against treating descriptive model agreement as a significance test
    print(
        "NOTE: model direction counts and agreement categories are descriptive; "
        "they are not statistical-significance tests."
    )
    #zero tells the shell that the program completed successfully
    return 0


#only run main automatically when this file is executed as a program
#importing its functions into the calculation tests will not run the workflow
if __name__ == "__main__":
    raise SystemExit(main())
