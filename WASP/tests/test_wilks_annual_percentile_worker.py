#creates temporary NetCDF inputs that are deleted after each test
import tempfile
#provides the test case and numerical assertion helpers
import unittest
#builds portable paths to the temporary source file
from pathlib import Path

#creates controlled wind values and datetime coordinates
import numpy as np
#writes the same labeled NetCDF structure expected by the production worker
import xarray as xr

#imports only the annual calculations exercised by this test module
from wilks_annual_percentile_worker import (
    annual_regional_percentiles,
    period_years,
    season_year_values,
)


#groups the annual-series worker checks in one discoverable test case
class WilksAnnualPercentileWorkerTests(unittest.TestCase):
    #checks strict parsing of the inclusive period labels used throughout WASP
    def test_period_years(self):
        self.assertEqual(period_years("2040-2059"), (2040, 2059))
        with self.assertRaisesRegex(ValueError, "expected YYYY-YYYY"):
            period_years("2040")
        with self.assertRaisesRegex(ValueError, "must not exceed"):
            period_years("2059-2040")

    #checks that December belongs to the next meteorological winter's year
    def test_december_is_assigned_to_following_djf_year(self):
        time = xr.DataArray(
            np.asarray(
                ["1999-12-15", "2000-01-15", "2000-12-15", "2001-02-15"],
                dtype="datetime64[ns]",
            ),
            dims=["time"],
        )
        labels = season_year_values(time, "DJF")
        np.testing.assert_array_equal(labels, [2000, 2000, 2001, 2001])

    #checks annual percentile grouping before any Wilks statistic is calculated
    def test_annual_regional_percentiles_returns_one_value_per_year(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "controlled_mam.nc"
            #four source values per year give exact, easy-to-check linear quantiles
            dates = np.asarray(
                [
                    f"{year}-{month_day}"
                    for year in (2000, 2001, 2002)
                    for month_day in ("03-01", "03-15", "04-01", "05-01")
                ],
                dtype="datetime64[ns]",
            )
            #every grid cell has the same controlled value, so latitude weighting
            #cannot change the expected annual regional percentile
            yearly_values = np.concatenate(
                [np.arange(4, dtype=float) + offset for offset in (0.0, 10.0, 20.0)]
            )
            wind = np.broadcast_to(yearly_values[:, None, None], (12, 2, 2)).copy()
            dataset = xr.Dataset(
                {
                    "WSPD10": (
                        ("time", "lat", "lon"),
                        wind,
                        {"units": "m s-1"},
                    )
                },
                coords={
                    "time": dates,
                    "lat": [44.0, 48.0],
                    "lon": [-96.0, -90.0],
                },
            )
            dataset.to_netcdf(source)

            series, years, counts, units = annual_regional_percentiles(
                source,
                variable="WSPD10",
                time_dim="time",
                lat_name="lat",
                lon_name="lon",
                season="MAM",
                period="2000-2002",
                percentiles=(0.5, 0.75),
            )

            np.testing.assert_array_equal(years, [2000, 2001, 2002])
            np.testing.assert_array_equal(counts, [4, 4, 4])
            #NumPy/xarray linear quantiles of [0, 1, 2, 3] are 1.5 and 2.25
            np.testing.assert_allclose(series[0.5], [1.5, 11.5, 21.5])
            np.testing.assert_allclose(series[0.75], [2.25, 12.25, 22.25])
            self.assertEqual(units, "m s-1")


#allows direct execution while remaining compatible with pytest discovery
if __name__ == "__main__":
    unittest.main()
