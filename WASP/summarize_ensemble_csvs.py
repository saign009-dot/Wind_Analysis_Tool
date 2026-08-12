"""Build CSV-only summaries from completed WASP ensemble trend tables."""

#overall flow is find the four trend csv files -> validate them -> rebuild the
#ensemble statistics from the model rows -> add direction and agreement fields
#-> put the three periods beside each other -> create a concise direction tally

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


#checks that the requested number of decimal places is sensible for csv output
def _validate_decimal_places(decimal_places: int) -> None:
    #bool is technically an integer in python but is not a meaningful rounding choice
    if isinstance(decimal_places, bool) or not isinstance(decimal_places, int):
        raise ValueError("decimal_places must be an integer")
    #zero is allowed for whole numbers and six still preserves far more than needed here
    if not 0 <= decimal_places <= 6:
        raise ValueError("decimal_places must be between 0 and 6")


#creates the compact 72-row agreement table with exactly five result metrics
def build_agreement_summary(
    ensemble_summary: pd.DataFrame,
    model_values: pd.DataFrame,
    zero_tolerance: float = 0.0,
    decimal_places: int = 3,
) -> pd.DataFrame:
    """Create five compact magnitude and model-agreement metrics per combination."""
    #negative tolerance would make the increase/decrease boundaries overlap
    if zero_tolerance < 0:
        raise ValueError("zero_tolerance must be zero or greater")
    #validate rounding once before applying it to any output values
    _validate_decimal_places(decimal_places)

    #each dictionary appended here holds the three exact model-direction counts
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
        #the three counts must still add to six even when a near-zero tolerance is used
        if increase_count + decrease_count + near_zero_count != len(MODELS):
            raise ValueError(
                f"Direction counts do not add to {len(MODELS)} for {keys}"
            )
        #save only the identifiers and exact integer counts needed for the compact output
        records.append({
            "percentile": percentile,
            "scenario": scenario,
            "period": period,
            "season": season,
            "models_increase": increase_count,
            "models_decrease": decrease_count,
            "models_near_zero": near_zero_count,
        })

    #turn the count records into a table before joining them to ensemble magnitude fields
    direction_counts = pd.DataFrame.from_records(records)
    #select only the two scientifically important ensemble magnitude metrics
    magnitudes = ensemble_summary[
        [*COMBINATION_COLUMNS, "ensemble_mean", "inter_model_std"]
    ].copy()
    #join the two magnitudes and three model counts into exactly five result metrics
    result = magnitudes.merge(
        direction_counts, on=COMBINATION_COLUMNS, how="inner", validate="one_to_one",
    )
    #an inner merge could hide an unmatched combination, so compare source/output lengths
    if len(result) != len(magnitudes) or len(result) != len(direction_counts):
        raise ValueError("Not every ensemble combination has matching model-level values")
    #round only the displayed wind values; all validation used the full-precision values
    result["ensemble_mean_mps"] = result["ensemble_mean"].round(decimal_places)
    result["inter_model_sd_mps"] = result["inter_model_std"].round(decimal_places)
    #identifiers are followed by exactly five requested agreement metrics
    ordered = [
        "percentile", "scenario", "period", "season",
        "ensemble_mean_mps", "inter_model_sd_mps",
        "models_increase", "models_decrease", "models_near_zero",
    ]
    #return the small rectangular table and discard the wider source-only columns
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


#creates the compact 24-row progression table with exactly five result metrics
def build_progression_summary(
    ensemble_summary: pd.DataFrame,
    zero_tolerance: float = 0.0,
    decimal_places: int = 3,
) -> pd.DataFrame:
    """Create four compact magnitude fields and one progression pattern per group."""
    #negative tolerance would make positive and negative movement overlap
    if zero_tolerance < 0:
        raise ValueError("zero_tolerance must be zero or greater")
    #validate rounding before building any progression output rows
    _validate_decimal_places(decimal_places)
    #each output row is collected as a dictionary before pandas builds the final table
    records: list[dict[str, object]] = []
    #group across periods while keeping percentile, scenario, and season separate
    for keys, group in ensemble_summary.groupby(
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
        #calculate late-minus-early from full precision before rounding display values
        late_minus_early = means[-1] - means[0]
        #store identifiers followed by the five requested progression metrics
        records.append({
            "percentile": percentile,
            "scenario": scenario,
            "season": season,
            "early_mean_mps": round(means[0], decimal_places),
            "middle_mean_mps": round(means[1], decimal_places),
            "late_mean_mps": round(means[2], decimal_places),
            "late_minus_early_mps": round(late_minus_early, decimal_places),
            "progression_pattern": _progression_pattern(means, zero_tolerance),
        })
    #convert all 24 percentile/scenario/season records into the progression table
    return pd.DataFrame.from_records(records)


#builds a short summary-of-the-summary without treating model directions as significance
def build_summary_tally(
    ensemble_summary: pd.DataFrame,
    model_values: pd.DataFrame,
    zero_tolerance: float = 0.0,
) -> pd.DataFrame:
    """Tally seasonal ensemble directions and model-season directions."""
    #negative tolerance would make the direction boundaries overlap
    if zero_tolerance < 0:
        raise ValueError("zero_tolerance must be zero or greater")
    #each dictionary becomes one percentile/scenario/period line in the text output
    records: list[dict[str, object]] = []
    #keep percentile separate, fixing the main interpretability problem in the old tally
    for keys, model_group in model_values.groupby(
        ["percentile", "scenario", "period"], sort=False
    ):
        #unpack the three identifiers that stay visible in the output
        percentile, scenario, period = keys
        #select the four matching seasonal ensemble rows from the ensemble table
        ensemble_group = ensemble_summary[
            (ensemble_summary["percentile"] == percentile)
            & (ensemble_summary["scenario"] == scenario)
            & (ensemble_summary["period"] == period)
        ]
        #the group must contain one row for each of DJF, MAM, JJA, and SON
        if set(ensemble_group["season"].astype(str)) != set(SEASONS):
            raise ValueError(
                f"Expected four seasons for {percentile} {scenario} {period}"
            )
        #six models across four seasons gives 24 model-season direction votes
        if len(model_group) != len(MODELS) * len(SEASONS):
            raise ValueError(
                f"Expected 24 model-season values for {percentile} {scenario} {period}"
            )
        #store season names under their direction in the standard DJF/MAM/JJA/SON order
        ensemble_names = {direction: [] for direction in ("increase", "decrease", "near_zero")}
        for season in SEASONS:
            #validation above guarantees exactly one ensemble row for this season
            value = float(
                ensemble_group.loc[
                    ensemble_group["season"] == season, "ensemble_mean"
                ].iloc[0]
            )
            #append the season name to the direction calculated from its ensemble mean
            ensemble_names[_direction(value, zero_tolerance)].append(season)
        #store model/season labels under their direction in standard model and season order
        model_season_names = {
            direction: [] for direction in ("increase", "decrease", "near_zero")
        }
        for model in MODELS:
            for season in SEASONS:
                #validation above guarantees one regional value for every model/season pair
                value = float(
                    model_group.loc[
                        (model_group["model"] == model)
                        & (model_group["season"] == season),
                        "regional_change",
                    ].iloc[0]
                )
                #model/season makes the identity unambiguous in the text tally
                label = f"{model}/{season}"
                model_season_names[_direction(value, zero_tolerance)].append(label)
        #store explicit denominators, direction counts, and the identities behind each count
        records.append({
            "percentile": percentile,
            "scenario": scenario,
            "period": period,
            "season_count": len(SEASONS),
            "season_ensemble_increase": len(ensemble_names["increase"]),
            "season_ensemble_decrease": len(ensemble_names["decrease"]),
            "season_ensemble_near_zero": len(ensemble_names["near_zero"]),
            "season_ensemble_increase_names": tuple(ensemble_names["increase"]),
            "season_ensemble_decrease_names": tuple(ensemble_names["decrease"]),
            "season_ensemble_near_zero_names": tuple(ensemble_names["near_zero"]),
            "model_season_vote_count": len(MODELS) * len(SEASONS),
            "model_season_increase": len(model_season_names["increase"]),
            "model_season_decrease": len(model_season_names["decrease"]),
            "model_season_near_zero": len(model_season_names["near_zero"]),
            "model_season_increase_names": tuple(model_season_names["increase"]),
            "model_season_decrease_names": tuple(model_season_names["decrease"]),
            "model_season_near_zero_names": tuple(model_season_names["near_zero"]),
        })
    #return 2 percentiles x 3 scenarios x 3 periods = 18 interpretable tally rows
    return pd.DataFrame.from_records(records)


#writes the concise tally in the same plain-text spirit as Summary of the summary.txt
def write_summary_tally(table: pd.DataFrame, output_path: str | Path) -> Path:
    """Write 18 direction blocks with counts and their season/model identities."""
    #normalize the output path before creating its parent folder
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    #start with definitions that prevent these counts from being mistaken for significance
    lines = [
        "WASP direction tally",
        "",
        "Each block covers 4 seasons and 24 model-season values (6 models x 4 seasons).",
        "Counts describe the sign of area-weighted wind-speed change, not statistical significance.",
        "Percentiles are kept separate and no overall pooled percentage is calculated.",
        "",
    ]
    #keep p98 and p99.9 in separate labeled text sections
    for percentile in PERCENTILE_INPUTS:
        lines.append(percentile)
        #preserve the standard scenario and period order instead of alphabetic sorting
        for scenario in SCENARIOS:
            for period in PERIODS:
                #there must be exactly one already-validated tally row for this combination
                row = table[
                    (table["percentile"] == percentile)
                    & (table["scenario"] == scenario)
                    & (table["period"] == period)
                ].iloc[0]
                #show a readable name list or the word none when a category is empty
                def names(column: str) -> str:
                    values = row[column]
                    return ", ".join(values) if values else "none"

                #make one short block so every count is directly connected to its identities
                lines.extend([
                    f"  {scenario}, {period}",
                    f"    Ensemble + ({int(row['season_ensemble_increase'])}/4): "
                    f"{names('season_ensemble_increase_names')}",
                    f"    Ensemble - ({int(row['season_ensemble_decrease'])}/4): "
                    f"{names('season_ensemble_decrease_names')}",
                    f"    Model-season + ({int(row['model_season_increase'])}/24): "
                    f"{names('model_season_increase_names')}",
                    f"    Model-season - ({int(row['model_season_decrease'])}/24): "
                    f"{names('model_season_decrease_names')}",
                    f"    Near-zero: ensemble {int(row['season_ensemble_near_zero'])}/4 "
                    f"[{names('season_ensemble_near_zero_names')}]; "
                    f"model-season {int(row['model_season_near_zero'])}/24 "
                    f"[{names('model_season_near_zero_names')}]",
                ])
        #blank line separates the two percentile sections
        lines.append("")
    #write utf-8 text with one final newline for standard text-file formatting
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    #return the created path so the command line can print it
    return output_path


#runs the complete validation, compact summaries, and text tally workflow
def summarize_outputs(
    outputs_root: str | Path = "outputs",
    output_dir: str | Path | None = None,
    zero_tolerance: float = 0.0,
    decimal_places: int = 3,
) -> tuple[Path, Path, Path]:
    """Validate source CSVs and write two compact CSVs plus one text tally."""
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

    #join the separately checked p98 and p99.9 tables for shared output functions
    ensemble_summary = pd.concat(ensemble_tables, ignore_index=True)
    model_values = pd.concat(model_tables, ignore_index=True)
    #make the compact 72-row agreement table with five result metrics
    agreement_summary = build_agreement_summary(
        ensemble_summary,
        model_values,
        zero_tolerance,
        decimal_places,
    )
    #make the compact 24-row progression table with five result metrics
    progression_summary = build_progression_summary(
        ensemble_summary,
        zero_tolerance,
        decimal_places,
    )
    #make the 18-row scenario-period tally that keeps percentiles separate
    summary_tally = build_summary_tally(ensemble_summary, model_values, zero_tolerance)
    #create the destination only after all validation and calculations succeed
    destination.mkdir(parents=True, exist_ok=True)
    #give the two compact csvs and plain-text tally direct descriptive names
    agreement_path = destination / "wasp_agreement_summary.csv"
    progression_path = destination / "wasp_progression_summary.csv"
    tally_path = destination / "wasp_summary_tally.txt"
    #fixed float formatting keeps every displayed wind value at the same compact precision
    float_format = f"%.{decimal_places}f"
    #write compact plain csv files without pandas row numbers
    agreement_summary.to_csv(agreement_path, index=False, float_format=float_format)
    progression_summary.to_csv(progression_path, index=False, float_format=float_format)
    #write the human-readable tally after its counts are calculated
    write_summary_tally(summary_tally, tally_path)
    #return every created path so the command line can print them for the user
    return agreement_path, progression_path, tally_path


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
    #three decimals preserves 0.001 m/s while keeping the two csv tables compact
    parser.add_argument(
        "--decimal-places", type=int, default=3,
        help="Decimal places for displayed wind values. Defaults to 3 (0.001 m/s).",
    )
    #return the configured parser so main can parse the actual command line
    return parser


#command-line entry point that runs the workflow and reports created files
def main(argv: list[str] | None = None) -> int:
    #parse either the real command line or an argument list supplied by a caller
    args = build_parser().parse_args(argv)
    #run every validation and create the two compact csvs plus the text tally
    output_paths = summarize_outputs(
        outputs_root=args.outputs_root,
        output_dir=args.output_dir,
        zero_tolerance=args.zero_tolerance,
        decimal_places=args.decimal_places,
    )
    #print each final path so the files are easy to locate on MSI
    for output_path in output_paths:
        print(f"WROTE: {output_path}")
    #warn against treating descriptive model-direction counts as a significance test
    print(
        "NOTE: model direction counts are descriptive; they are not "
        "statistical-significance tests."
    )
    #zero tells the shell that the program completed successfully
    return 0


#only run main automatically when this file is executed as a program
#importing its functions into the calculation tests will not run the workflow
if __name__ == "__main__":
    raise SystemExit(main())
