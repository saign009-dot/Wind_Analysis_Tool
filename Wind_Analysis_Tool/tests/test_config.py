import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wind_extreme_analysis.config import percentile_label, normalize_percentile, validate_dataset_config


class ConfigTests(unittest.TestCase):
    def test_normalize_percentile(self):
        self.assertEqual(normalize_percentile(98), 0.98)
        self.assertEqual(normalize_percentile(0.999), 0.999)

    def test_percentile_label(self):
        self.assertEqual(percentile_label(0.98), "p98")
        self.assertEqual(percentile_label(0.999), "p99_9")

    def test_validate_dataset_config_finds_placeholders(self):
        dataset = {
            "variable": "PLACEHOLDER_WIND_VAR",
            "time_dim": "time",
            "lat_name": "lat",
            "lon_name": "lon",
            "historical": {"path": "PLACEHOLDER_HIST.nc"},
            "futures": [{"scenario": "ssp585", "period": "2040-2059", "path": "future.nc"}],
        }

        issues = validate_dataset_config(dataset)

        self.assertTrue(any("variable" in issue for issue in issues))
        self.assertTrue(any("historical path" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
