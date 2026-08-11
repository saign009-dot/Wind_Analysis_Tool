# MCAP Wind Analysis

analyzes changes in wind speed percentiles between a historical baseline and future climate scenarios

It is designed for:

- Historical baseline: 1995-2014
- Scenarios: `ssp245`, `ssp370`, `ssp585`
- Future periods: `2040-2059`, `2060-2079`, `2080-2099`
- Percentiles: 98th and 99.9th
- NetCDF input

## Recommended Workflow

1. Install Python dependencies in the environment where you run Jupyter: pip install -r requirements.txt

2. Open the notebook: wind_extreme_control.ipynb
  
3. Edit the placeholders in: wind_extremes.config.json
   
4. Run the notebook cells from top to bottom.

The code lives in `src/wind_extreme_analysis` so the same workflow can be reused for other variables and datasets

This folder intentionally does not duplicate the large NetCDF files. Paths are resolved relative to the `wind_program` parent folder.

Outputs from the bundled notebook are written inside this folder: Wind_Analysis_Tool/outputs/

## Tests

Run the tests with: pytest

## Statistical Significance

The workflow includes three levels of evidence:

- Bootstrap confidence intervals
   randomly takes out blocks of value from your data and treats them as as representative of the larger dataset and calculates stats on that block then returns them to the larger dataset. repeats 1000s of times to build confidence intervals where the actual value lies between a min and max
- Mann-Whitney U 
   determines significance between two independent distributions in this case historical v. future
- Kolmogorov-Smirnov
   evaluates how two samples compmare to eachother
   if this does not pass there is not a difference in distribution between historical and future
- Optional grid-cell bootstrap significance maps with false discovery rate correction
   trims down significant finding in very large datasets because the larger the dataset the more likely it is to randomly find significance


The bootstrap can use block resampling so the test does not pretend every value is fully independent. The default block length in the example config is 56 timesteps, which is 7 days of 3-hourly values.

## U/V Component Conversion

If future datasets provide `u` and `v` wind components instead of wind-speed magnitude, use:


python -m wind_extreme_analysis.uv_to_speed `
  --u-file PLACEHOLDER_U_FILE.nc `
  --v-file PLACEHOLDER_V_FILE.nc `
  --u-var PLACEHOLDER_U_VAR `
  --v-var PLACEHOLDER_V_VAR `
  --out PLACEHOLDER_OUTPUT_WIND_SPEED.nc `
  --speed-var PLACEHOLDER_WIND_SPEED_VAR

