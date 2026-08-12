import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from summarize_ensemble_csvs import summarize_outputs


MODELS = [
    "BCC-CSM2-MR",
    "CESM2",
    "CMCC-ESM2",
    "CNRM-ESM2-1",
    "IPSL-CM6A-LR",
    "MIROC-ES2L",
]
SCENARIOS = ["ssp245", "ssp370", "ssp585"]
SEASONS = ["DJF", "MAM", "JJA", "SON"]
PERIOD_VALUES = {
    "2040-2059": [-1.0, 0.2, 0.3, 0.4, 0.5, 0.6],
    "2060-2079": [0.1, 0.3, 0.5, 0.7, 0.9, 1.1],
    "2080-2099": [0.4, 0.6, 0.8, 1.0, 1.2, 1.4],
}


def write_percentile_tables(outputs_root: Path, label: str, multiplier: float) -> None:
    directory = outputs_root / f"{label}_ensemble_trends"
    directory.mkdir(parents=True)
    model_rows = []
    summary_rows = []
    for scenario in SCENARIOS:
        for period, base_values in PERIOD_VALUES.items():
            for season in SEASONS:
                values = np.asarray(base_values, dtype=float) * multiplier
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
                summary_rows.append({
                    "scenario": scenario,
                    "period": period,
                    "season": season,
                    "ensemble_mean": values.mean(),
                    "inter_model_std": values.std(ddof=1),
                    "model_min": values.min(),
                    "model_max": values.max(),
                    "model_count": len(values),
                    "units": "m s-1",
                })
    pd.DataFrame(model_rows).to_csv(
        directory / f"{label}_regional_model_values.csv", index=False
    )
    pd.DataFrame(summary_rows).to_csv(
        directory / f"{label}_ensemble_trend_summary.csv", index=False
    )


class EnsembleCsvSummaryTests(unittest.TestCase):
    def test_end_to_end_summary_writes_expected_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            outputs_root = Path(temporary) / "outputs"
            write_percentile_tables(outputs_root, "p98", 1.0)
            write_percentile_tables(outputs_root, "p99_9", 2.0)

            combination_path, progression_path = summarize_outputs(outputs_root)

            combinations = pd.read_csv(combination_path)
            progression = pd.read_csv(progression_path)
            self.assertEqual(len(combinations), 72)
            self.assertEqual(len(progression), 24)

            early_p98 = combinations[
                (combinations["percentile"] == "p98")
                & (combinations["period"] == "2040-2059")
                & (combinations["scenario"] == "ssp245")
                & (combinations["season"] == "DJF")
            ].iloc[0]
            self.assertEqual(int(early_p98["increase_count"]), 5)
            self.assertEqual(int(early_p98["decrease_count"]), 1)
            self.assertTrue(bool(early_p98["models_span_zero"]))
            self.assertEqual(early_p98["minimum_model"], "BCC-CSM2-MR")
            self.assertEqual(early_p98["maximum_model"], "MIROC-ES2L")
            self.assertAlmostEqual(
                float(early_p98["direction_agreement_fraction"]), 5 / 6
            )
            self.assertEqual(early_p98["agreement_category"], "strong")

            p98_progression = progression[
                (progression["percentile"] == "p98")
                & (progression["scenario"] == "ssp245")
                & (progression["season"] == "DJF")
            ].iloc[0]
            self.assertEqual(
                p98_progression["period_progression_pattern"],
                "monotonic_increase",
            )

    def test_mismatched_ensemble_table_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            outputs_root = Path(temporary) / "outputs"
            write_percentile_tables(outputs_root, "p98", 1.0)
            write_percentile_tables(outputs_root, "p99_9", 2.0)
            summary_path = (
                outputs_root
                / "p98_ensemble_trends"
                / "p98_ensemble_trend_summary.csv"
            )
            summary = pd.read_csv(summary_path)
            summary.loc[0, "ensemble_mean"] += 1.0
            summary.to_csv(summary_path, index=False)

            with self.assertRaisesRegex(ValueError, "does not match"):
                summarize_outputs(outputs_root)


if __name__ == "__main__":
    unittest.main()
