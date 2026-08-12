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
    #checks both compact csv files, the concise text tally, and the one summary heatmap
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
            agreement_path, progression_path, tally_path, heatmap_path = summarize_outputs(
                outputs_root
            )

            #read the two compact csvs and tally while keeping the image path for checks
            agreement = pd.read_csv(agreement_path)
            progression = pd.read_csv(progression_path)
            tally_text = tally_path.read_text(encoding="utf-8")
            #the fourth product must be a real nonempty png rather than a mislabeled file
            self.assertEqual(heatmap_path.suffix, ".png")
            self.assertGreater(heatmap_path.stat().st_size, 1000)
            self.assertEqual(
                heatmap_path.read_bytes()[:8],
                b"\x89PNG\r\n\x1a\n",
            )
            #2 percentiles x 3 scenarios x 3 periods x 4 seasons = 72 rows
            self.assertEqual(len(agreement), 72)
            #2 percentiles x 3 scenarios x 4 seasons = 24 progression rows
            self.assertEqual(len(progression), 24)
            #identifiers plus exactly five agreement metrics gives nine columns
            self.assertEqual(len(agreement.columns), 9)
            #identifiers plus exactly five progression metrics gives eight columns
            self.assertEqual(len(progression.columns), 8)

            #check the compact agreement table has only the selected five metrics
            self.assertEqual(
                list(agreement.columns),
                [
                    "percentile", "scenario", "period", "season",
                    "ensemble_mean_mps", "inter_model_sd_mps",
                    "models_increase", "models_decrease", "models_near_zero",
                ],
            )
            #check the compact progression table has only the selected five metrics
            self.assertEqual(
                list(progression.columns),
                [
                    "percentile", "scenario", "season",
                    "early_mean_mps", "middle_mean_mps", "late_mean_mps",
                    "late_minus_early_mps", "progression_pattern",
                ],
            )

            #select one exact early-period p98 agreement row for detailed checks
            early_p98 = agreement[
                (agreement["percentile"] == "p98")
                & (agreement["period"] == "2040-2059")
                & (agreement["scenario"] == "ssp245")
                & (agreement["season"] == "DJF")
            ].iloc[0]
            #the full-precision mean is 1/6 and displays as 0.167 at three decimals
            self.assertAlmostEqual(float(early_p98["ensemble_mean_mps"]), 0.167)
            #the controlled values have five positive models and one negative model
            self.assertEqual(int(early_p98["models_increase"]), 5)
            self.assertEqual(int(early_p98["models_decrease"]), 1)
            self.assertEqual(int(early_p98["models_near_zero"]), 0)

            #select one exact compact progression row
            p98_progression = progression[
                (progression["percentile"] == "p98")
                & (progression["scenario"] == "ssp245")
                & (progression["season"] == "DJF")
            ].iloc[0]
            #the three controlled period means and endpoint difference are rounded to 3 places
            self.assertAlmostEqual(float(p98_progression["early_mean_mps"]), 0.167)
            self.assertAlmostEqual(float(p98_progression["middle_mean_mps"]), 0.6)
            self.assertAlmostEqual(float(p98_progression["late_mean_mps"]), 0.9)
            self.assertAlmostEqual(float(p98_progression["late_minus_early_mps"]), 0.733)
            #inspect raw csv text to prove trailing zeroes keep the table visually square
            self.assertIn(
                "p98,ssp245,DJF,0.167,0.600,0.900,0.733,monotonic_increase",
                progression_path.read_text(encoding="utf-8"),
            )
            #the controlled means increase from early to middle to late
            self.assertEqual(
                p98_progression["progression_pattern"],
                "monotonic_increase",
            )

            #the text tally retains percentile and scenario/period identifiers
            self.assertIn("p98", tally_text)
            self.assertIn("p99_9", tally_text)
            #the tally lists all four positive ensemble seasons by name in standard order
            self.assertIn(
                "Ensemble + (4/4): DJF, MAM, JJA, SON",
                tally_text,
            )
            #an empty direction category must say none rather than leaving an unclear blank
            self.assertIn("Ensemble - (0/4): none", tally_text)
            #the only negative model is BCC, so all four of its seasonal labels are listed
            self.assertIn(
                "Model-season - (4/24): BCC-CSM2-MR/DJF, BCC-CSM2-MR/MAM, "
                "BCC-CSM2-MR/JJA, BCC-CSM2-MR/SON",
                tally_text,
            )
            #the positive list begins with CESM2 and ends with MIROC in production order
            positive_model_seasons = ", ".join(
                f"{model}/{season}" for model in MODELS[1:] for season in SEASONS
            )
            self.assertIn(
                f"Model-season + (20/24): {positive_model_seasons}",
                tally_text,
            )
            #near-zero categories also show both the count and the empty identity list
            self.assertIn(
                "Near-zero: ensemble 0/4 [none]; model-season 0/24 [none]",
                tally_text,
            )
            #the header explicitly prevents interpreting direction counts as significance
            self.assertIn("not statistical significance", tally_text)

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
