# W.A.S.P. — Wind Analysis and Statistics Package

W.A.S.P. analyzes changes in wind-speed percentiles between a historical baseline and future climate scenarios. It combines the original Wind Analysis Tool workflow with the later multi-model ensemble calculations.

## Scientific Version History

- The repository's `main` branch preserves the original Wind Analysis Tool code without the ensemble-analysis additions.
- The `WASP` branch contains the renamed Wind Analysis and Statistics Package and the ensemble workflow added during the reanalysis.

It is designed for:

- Historical baseline: 1995-2014
- Scenarios: `ssp245`, `ssp370`, `ssp585`
- Future periods: `2040-2059`, `2060-2079`, `2080-2099`
- Percentiles: 98th and 99.9th
- NetCDF input

## Recommended Workflow

1. On MSI, use the Miniforge environment workflow in [`MSI_SETUP.md`](../MSI_SETUP.md), following [MSI's conda best practices](https://msi.umn.edu/getting-started/help/knowledge-base/best-practices-conda). On other systems, install the dependencies with `python -m pip install -r requirements.txt`.

2. Open the notebook: wind_extreme_control.ipynb
  
3. Edit the placeholders in: wind_extremes.config.json
   
4. Run the notebook cells from top to bottom.

The code lives in `src/wind_extreme_analysis` so the same workflow can be reused for other variables and datasets

This folder intentionally does not duplicate the large NetCDF files. Paths are resolved relative to the `wind_program` parent folder.

Outputs from the bundled notebook are written inside this folder: `WASP/Outputs/`.

## Multi-model Ensemble Workflow

The `WASP` branch also includes the ensemble-analysis programs:

- `src/wind_extreme_analysis/ensemble_manifest.py` validates the required model inputs and creates the Slurm task manifest.
- `percentile_change_worker.py` calculates model-level gridded percentile changes.
- `percentile_ensemble_worker.py` calculates the six-model ensemble mean, inter-model sample standard deviation, and model count.
- `percentile_ensemble_trends.py` creates regional ensemble summaries and trend plots.
- The `slurm_p98_*.sh` and `slurm_p99_9_*.sh` launchers run the model-change, ensemble, and trend stages for the 98th and 99.9th percentiles.

The Slurm launchers write generated products below `WASP/outputs/` by default.

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
