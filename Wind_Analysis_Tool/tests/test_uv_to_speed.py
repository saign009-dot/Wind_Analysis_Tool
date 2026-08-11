import unittest
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wind_extreme_analysis.uv_to_speed import wind_speed_magnitude


class WindSpeedMagnitudeTests(unittest.TestCase):
    def test_wind_speed_magnitude(self):
        u = np.array([3.0, 5.0, 8.0])
        v = np.array([4.0, 12.0, 15.0])

        speed = wind_speed_magnitude(u, v)

        np.testing.assert_allclose(speed, np.array([5.0, 13.0, 17.0]))


if __name__ == "__main__":
    unittest.main()
