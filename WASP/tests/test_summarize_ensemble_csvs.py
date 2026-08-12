#creates temporary folders that are deleted automatically after each calculation test
import tempfile
#provides the test case class and assertion methods
import unittest
#builds test input and output file paths without depending on one operating system
from pathlib import Path

#creates the six numeric model values used to calculate expected statistics
import numpy as np
#creates source csv tables and reads the program's generated csv outputs
import pandas as pd

#imports the complete summary workflow being checked by these tests
from summarize_ensemble_csvs import summarize_outputs


#uses the exact six production model names required by the validation code
MODELS = [
    "BCC-CSM2-MR",
    "CESM2",
    "CMCC-ESM2",
    "CNRM-ESM2-1",
    "IPSL-CM6A-LR",
    "MIROC-ES2L",
]
#uses all three production scenarios so the fake inputs contain all 36 combinations
SCENARIOS = ["ssp245", "ssp370", "ssp585"]
#uses all four seasons expected in every production percentile table
SEASONS = ["DJF", "MAM", "JJA", "SON"]
#model values increase through the periods so the expected progression is unambiguous
#the first early-period value is negative to also test disagreement and zero spanning
PERIOD_VALUES = {
    "2040-2059": [-1.0, 0.2, 0.3, 0.4, 0.5, 0.6],
    "2060-2079": [0.1, 0.3, 0.5, 0.7, 0.9, 1.1],
    "2080-2099": [0.4, 0.6, 0.8, 1.0, 1.2, 1.4],
}


#writes one percentile's fake model and ensemble tables in the real WASP folder layout
def write_percentile_tables(outputs_root: Path, label: str, multiplier: float) -> None:
    #match the p98_ensemble_trends or p99_9_ensemble_trends production folder name
    directory = outputs_root / f"{label}_ensemble_trends"
    #parents=True also creates the temporary outputs root when it does not exist
    directory.mkdir(parents=True)
    #model_rows will become the 216-row individual model table
    model_rows = []
    #summary_rows will become the 36-row six-model ensemble table
    summary_rows = []
    #repeat the same controlled values across all required scenarios
    for scenario in SCENARIOS:
        #iterate in early, middle, late order using PERIOD_VALUES insertion order
        for period, base_values in PERIOD_VALUES.items():
            #repeat the controlled values across all four required seasons
            for season in SEASONS:
                #multiplier makes p99.9 values different without changing their pattern
                values = np.asarray(base_values, dtype=float) * multiplier
                #make one regional-value row for each of the six production models
                for model, value in zip(MODELS, values):
                    model_rows.append({
                        "model": model,
                        "scenario": scenario,
                        "period": period,
                        "season": season,
                        "regional_change": value,
                        "units": "m s-1",
                        "source": f"{model}.nc",
                    })
                #calculate the exact ensemble statistics expected from those six rows
                summary_rows.append({
                    "scenario": scenario,
                    "period": period,
                    "season": season,
                    #ordinary mean across the six model values
                    "ensemble_mean": values.mean(),
                    #ddof=1 matches the sample standard deviation used by WASP
                    "inter_model_std": values.std(ddof=1),
                    "model_min": values.min(),
                    "model_max": values.max(),
                    "model_count": len(values),
                    "units": "m s-1",
                })
    #write the model-level source table with the exact filename used in production
    pd.DataFrame(model_rows).to_csv(
        directory / f"{label}_regional_model_values.csv", index=False
    )
    #write the ensemble source table with the exact filename used in production
    pd.DataFrame(summary_rows).to_csv(
        directory / f"{label}_ensemble_trend_summary.csv", index=False
    )


#groups all calculation tests for summarize_ensemble_csvs.py
class EnsembleCsvSummaryTests(unittest.TestCase):
    #checks all four output csv files from controlled valid source tables
    def test_end_to_end_summary_writes_expected_values(self):
        #keep fake production files outside the repository and remove them afterward
        with tempfile.TemporaryDirectory() as temporary:
            #build the standard outputs folder inside the temporary directory
            outputs_root = Path(temporary) / "outputs"
            #create a complete p98 source dataset
            write_percentile_tables(outputs_root, "p98", 1.0)
            #create a complete p99.9 source dataset with values twice as large
            write_percentile_tables(outputs_root, "p99_9", 2.0)

            #run the same complete workflow that the user runs on MSI
            (
                combination_path,
                progression_path,
                combination_tally_path,
                progression_tally_path,
            ) = summarize_outputs(outputs_root)

            #read each generated csv so its rows and calculated fields can be checked
            combinations = pd.read_csv(combination_path)
            progression = pd.read_csv(progression_path)
            combination_tallies = pd.read_csv(combination_tally_path)
            progression_tallies = pd.read_csv(progression_tally_path)
            #2 percentiles x 3 scenarios x 3 periods x 4 seasons = 72 rows
            self.assertEqual(len(combinations), 72)
            #2 percentiles x 3 scenarios x 4 seasons = 24 progression rows
            self.assertEqual(len(progression), 24)
            #the combination tally also keeps one row per percentile/scenario/season
            self.assertEqual(len(combination_tallies), 24)
            #2 percentiles x 3 scenarios = 6 progression tally rows
            self.assertEqual(len(progression_tallies), 6)

            #select one exact early-period p98 combination for detailed checks
            early_p98 = combinations[
                (combinations["percentile"] == "p98")
                & (combinations["period"] == "2040-2059")
                & (combinations["scenario"] == "ssp245")
                & (combinations["season"] == "DJF")
            ].iloc[0]
            #the controlled values have five positive models and one negative model
            self.assertEqual(int(early_p98["increase_count"]), 5)
            self.assertEqual(int(early_p98["decrease_count"]), 1)
            #positive and negative values mean the model results span zero
            self.assertTrue(bool(early_p98["models_span_zero"]))
            #the first and last controlled model values are the minimum and maximum
            self.assertEqual(early_p98["minimum_model"], "BCC-CSM2-MR")
            self.assertEqual(early_p98["maximum_model"], "MIROC-ES2L")
            #five models agreeing out of six gives the expected agreement fraction
            self.assertAlmostEqual(
                float(early_p98["direction_agreement_fraction"]), 5 / 6
            )
            #five of six is classified as strong rather than unanimous agreement
            self.assertEqual(early_p98["agreement_category"], "strong")

            #select one exact wide progression row
            p98_progression = progression[
                (progression["percentile"] == "p98")
                & (progression["scenario"] == "ssp245")
                & (progression["season"] == "DJF")
            ].iloc[0]
            #the controlled means increase from early to middle to late
            self.assertEqual(
                p98_progression["period_progression_pattern"],
                "monotonic_increase",
            )

            #select the tally of all three periods for the same percentile/scenario/season
            p98_combination_tally = combination_tallies[
                (combination_tallies["percentile"] == "p98")
                & (combination_tallies["scenario"] == "ssp245")
                & (combination_tallies["season"] == "DJF")
            ].iloc[0]
            #three period-level combinations must be included in the tally
            self.assertEqual(int(p98_combination_tally["period_combination_count"]), 3)
            #all three controlled ensemble means are positive
            self.assertEqual(int(p98_combination_tally["ensemble_increase_count"]), 3)
            #early period is 5/6 strong and the other two periods are 6/6 unanimous
            self.assertEqual(int(p98_combination_tally["strong_agreement_count"]), 1)
            self.assertEqual(int(p98_combination_tally["unanimous_agreement_count"]), 2)
            #only the early period contains both increasing and decreasing models
            self.assertEqual(int(p98_combination_tally["models_span_zero_count"]), 1)
            #three periods multiplied by six models gives 18 individual votes
            self.assertEqual(int(p98_combination_tally["model_vote_count"]), 18)
            #17 of those votes are positive and one is negative
            self.assertEqual(int(p98_combination_tally["model_increase_vote_count"]), 17)
            self.assertEqual(int(p98_combination_tally["model_decrease_vote_count"]), 1)

            #select the four-season progression tally for one percentile/scenario
            p98_progression_tally = progression_tallies[
                (progression_tallies["percentile"] == "p98")
                & (progression_tallies["scenario"] == "ssp245")
            ].iloc[0]
            #the tally must include all four seasons
            self.assertEqual(int(p98_progression_tally["season_count"]), 4)
            #the repeated controlled values make all four seasons increase monotonically
            self.assertEqual(int(p98_progression_tally["monotonic_increase_count"]), 4)
            #late-century mean is also above early-century mean in all four seasons
            self.assertEqual(int(p98_progression_tally["late_above_early_count"]), 4)

    #checks that the program catches an ensemble csv that was changed independently
    def test_mismatched_ensemble_table_is_rejected(self):
        #use a new temporary directory so this test cannot affect the valid test
        with tempfile.TemporaryDirectory() as temporary:
            outputs_root = Path(temporary) / "outputs"
            #first create two complete and internally consistent percentile datasets
            write_percentile_tables(outputs_root, "p98", 1.0)
            write_percentile_tables(outputs_root, "p99_9", 2.0)
            #locate the p98 ensemble summary that will be intentionally corrupted
            summary_path = (
                outputs_root
                / "p98_ensemble_trends"
                / "p98_ensemble_trend_summary.csv"
            )
            #read the table and change only one stored mean, not its six source models
            summary = pd.read_csv(summary_path)
            summary.loc[0, "ensemble_mean"] += 1.0
            summary.to_csv(summary_path, index=False)

            #the cross-check must reject the altered ensemble statistic
            with self.assertRaisesRegex(ValueError, "does not match"):
                summarize_outputs(outputs_root)


#lets this test file also be run directly with python if needed
if __name__ == "__main__":
    unittest.main()
