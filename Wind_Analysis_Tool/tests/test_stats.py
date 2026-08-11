import unittest
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wind_extreme_analysis.stats import benjamini_hochberg, bootstrap_percentile_difference, clean_1d


class StatsTests(unittest.TestCase):
    def test_clean_1d_removes_nan_and_inf(self):
        cleaned = clean_1d([1, np.nan, 2, np.inf, -np.inf, 3])
        np.testing.assert_array_equal(cleaned, np.array([1.0, 2.0, 3.0]))

    def test_bootstrap_percentile_difference_detects_shift(self):
        historical = np.linspace(0.0, 100.0, 500)
        future = historical + 10.0

        result = bootstrap_percentile_difference(
            historical,
            future,
            percentile=0.98,
            n_boot=200,
            random_seed=7,
        )

        self.assertAlmostEqual(result.absolute_change, 10.0, places=8)
        self.assertGreater(result.percent_change, 0.0)
        self.assertTrue(result.significant)
        self.assertLess(result.absolute_ci_low, result.absolute_change)
        self.assertGreater(result.absolute_ci_high, result.absolute_change)

    def test_bootstrap_accepts_percentile_as_percent(self):
        historical = np.arange(100.0)
        future = historical + 5.0

        result = bootstrap_percentile_difference(historical, future, percentile=98, n_boot=50, random_seed=1)

        self.assertAlmostEqual(result.percentile, 0.98)
        self.assertAlmostEqual(result.absolute_change, 5.0)

    def test_benjamini_hochberg(self):
        p_values = np.array([0.001, 0.02, 0.04, 0.2, np.nan])
        reject, adjusted = benjamini_hochberg(p_values, alpha=0.05)

        self.assertTrue(reject[0])
        self.assertTrue(reject[1])
        self.assertFalse(reject[3])
        self.assertTrue(np.isnan(adjusted[-1]))
        self.assertLessEqual(adjusted[0], adjusted[1])


if __name__ == "__main__":
    unittest.main()
