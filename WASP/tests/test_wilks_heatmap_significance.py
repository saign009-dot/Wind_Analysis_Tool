#provides standard test cases and assertion helpers
import unittest

#creates controlled annual values and checks numerical output
import numpy as np
#builds a complete in-memory version of the 216 worker tables
import pandas as pd

#uses the production ensemble levels to make the synthetic table structurally exact
from percentile_ensemble_worker import MODELS, PERIODS, SCENARIOS, SEASONS
#imports the statistics and 72-cell builder under test
from wilks_heatmap_significance import (
    PERCENTILES,
    SIGNIFICANCE_COLUMNS,
    build_wilks_results,
    lag1_autocorrelation,
    wilks_effective_sample_size,
    wilks_welch_test,
)


#creates complete annual rows without reading large model NetCDF files
def synthetic_annual_table() -> pd.DataFrame:
    """Return a complete six-model, 72-cell annual percentile table."""
    rows: list[dict[str, object]] = []
    #the irregular pattern avoids a perfect +1/-1 lag correlation while retaining
    #an ordered signal with enough variation for the Wilks calculation
    pattern = np.asarray([0.0, 0.8, -0.4, 0.5, -0.7, 0.9, -0.2, 0.3])
    historical_years = np.arange(1995, 2003)
    for percentile_index, percentile in enumerate(PERCENTILES):
        probability = 0.98 if percentile == "p98" else 0.999
        for scenario in SCENARIOS:
            for period in PERIODS:
                future_start = int(period.split("-")[0])
                future_years = np.arange(future_start, future_start + len(pattern))
                for season_index, season in enumerate(SEASONS):
                    #a fixed future shift makes every synthetic cell clearly positive
                    shift = 1.25 + 0.1 * percentile_index + 0.02 * season_index
                    for model_index, model in enumerate(MODELS):
                        #model offsets create a nonzero inter-model SD but cancel when
                        #future-minus-historical changes are formed for each model
                        model_offset = 0.05 * model_index
                        baseline = 8.0 + percentile_index + model_offset
                        for period_type, years, values in (
                            ("historical", historical_years, baseline + pattern),
                            ("future", future_years, baseline + shift + pattern),
                        ):
                            for year, value in zip(years, values):
                                rows.append({
                                    "model": model,
                                    "scenario": scenario,
                                    "period": period,
                                    "season": season,
                                    "percentile": percentile,
                                    "percentile_probability": probability,
                                    "period_type": period_type,
                                    "year": int(year),
                                    "regional_percentile_mps": float(value),
                                    "source_timesteps": 120,
                                    "units": "m s-1",
                                    "source": f"{model}.nc",
                                })
    return pd.DataFrame.from_records(rows)


#groups the formula and complete heatmap-table checks
class WilksHeatmapSignificanceTests(unittest.TestCase):
    #checks the exact effective-sample-size equation requested for autocorrelation
    def test_effective_sample_size_uses_wilks_lag1_formula(self):
        self.assertAlmostEqual(
            wilks_effective_sample_size(20, 0.5),
            20.0 * (1.0 - 0.5) / (1.0 + 0.5),
        )
        #negative lag correlation increases information under the untruncated formula
        self.assertGreater(wilks_effective_sample_size(20, -0.2), 20.0)

    #checks that the test compares future and historical ordered ensemble series
    def test_wilks_welch_test_reports_change_interval_and_raw_p(self):
        historical = np.asarray([0.0, 0.8, -0.4, 0.5, -0.7, 0.9, -0.2, 0.3])
        future = historical + 1.25
        result = wilks_welch_test(historical, future, alpha=0.05)
        self.assertAlmostEqual(
            result["historical_lag1_autocorrelation"],
            lag1_autocorrelation(historical),
        )
        self.assertLess(result["raw_p_value"], 0.05)
        self.assertGreater(result["mean_change_ci_low_mps"], 0.0)
        self.assertAlmostEqual(
            (result["mean_change_ci_low_mps"] + result["mean_change_ci_high_mps"]) / 2,
            1.25,
        )

    #checks that there is exactly one raw test per p/scenario/period/season cell
    def test_complete_builder_returns_72_unadjusted_cell_tests(self):
        significance, combined = build_wilks_results(synthetic_annual_table())
        self.assertEqual(len(significance), 72)
        self.assertEqual(list(significance.columns), SIGNIFICANCE_COLUMNS)
        self.assertNotIn("fdr_adjusted_p_value", significance.columns)
        self.assertNotIn("fdr_significant", significance.columns)
        self.assertTrue(significance["wilks_significant"].all())
        self.assertTrue((significance["model_count"] == 6).all())
        self.assertTrue((significance["models_increase"] == 6).all())
        #72 cells x 2 periods x 8 years provides every auditable test input
        self.assertEqual(len(combined), 72 * 2 * 8)
        self.assertTrue((combined["model_count"] == 6).all())


#allows direct execution while remaining compatible with pytest discovery
if __name__ == "__main__":
    unittest.main()
