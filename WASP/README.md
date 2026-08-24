# W.A.S.P. — Wind Analysis and Statistics Package

W.A.S.P. analyzes changes in wind-speed percentiles between a historical baseline and future climate scenarios. It combines the original Wind Analysis Tool workflow with the later multi-model ensemble calculations.

## Version History

- The repository's `main` branch preserves the original Wind Analysis Tool code without the ensemble-analysis additions.
- The `WASP` branch contains the renamed Wind Analysis and Statistics Package and the ensemble workflow added during the reanalysis.

It is designed for:

- Historical baseline: 1995-2014
- Scenarios: `ssp245`, `ssp370`, `ssp585`
- Future periods: `2040-2059`, `2060-2079`, `2080-2099`
- Percentiles: 98th and 99.9th
- NetCDF input

## Input Data Preprocessing

The NetCDF inputs analyzed by WASP were first spatially masked to Minnesota and then split into DJF, MAM, JJA, and SON files. The programs used for that preparation are preserved in `preprocessing/`:

1. `directory_subdirectory_maker.sh` creates the original model/scenario scratch-directory layout.
2. `make_mn_masks.py` builds a grid-specific Minnesota mask for each model using a U.S. Census state-boundary shapefile.
3. `mask_and_split_all.sh` applies each mask with CDO `ifthen` and creates the four seasonal files with CDO `selseas`.
4. `mask_and_split_all_forMIROC.sh` is the MIROC-specific rerun used when processing that model separately.
5. `split_masked_all_by_month.sh` is the no-masking follow-on for data that are already Minnesota-masked. It creates one multi-year NetCDF file for each calendar month using CDO `selmon`.

These scripts preserve the project-specific MSI paths used for the analysis. Review `PROJECT_ROOT`, `TOOL_ROOT`, `MASK_DIR`, `SOURCE_BASE`, `STATE_SHAPEFILE`, model names, and filename patterns before reusing them. The masking scripts default to a non-writing preview; pass `run` only after reviewing the displayed paths.

```bash
bash preprocessing/mask_and_split_all.sh
bash preprocessing/mask_and_split_all.sh run
```

To split already-masked files by calendar month, preview the resolved paths first and then run the monthly splitter:

```bash
bash preprocessing/split_masked_all_by_month.sh
bash preprocessing/split_masked_all_by_month.sh run
```

The monthly splitter supports either a complete `WSPD10_MODEL_RUN_MNmasked.nc` file or the four existing `DJF/MAM/JJA/SON` files. It finds the preferred `Analysis/MODEL/RUN/` layout, the older shared `Analysis/RUN/` layout, and the BCC layout where files are stored directly in `Analysis/seasons/`. Outputs are always written to a `months/` folder beside the matched `seasons/` folder and use sortable `_01.nc` through `_12.nc` suffixes. For the BCC layout, that means `Analysis/seasons/` is read and `Analysis/months/` is written. Each file contains that calendar month across all years in the period; no spatial mask is read or applied. Existing monthly files are preserved unless the run is explicitly submitted with `OVERWRITE=1`.

## Recommended Workflow

1. On MSI, use the Miniforge environment workflow in [`MSI_SETUP.md`](../MSI_SETUP.md), following [MSI's conda best practices](https://msi.umn.edu/getting-started/help/knowledge-base/best-practices-conda). On other systems, install the dependencies with `python -m pip install -r requirements.txt`.

2. Open the notebook: wind_extreme_control.ipynb
  
3. Edit the placeholders in: wind_extremes.config.json
   
4. Run the notebook cells from top to bottom.

The code lives in `src/wind_extreme_analysis` so the same workflow can be reused for other variables and datasets

This folder intentionally does not duplicate the large NetCDF files. Paths are resolved relative to the parent folder.

Outputs from the bundled notebook are written inside this folder: `WASP/Outputs/`.

## Multi-model Ensemble Workflow

The `WASP` branch also includes the ensemble-analysis programs:

- `src/wind_extreme_analysis/ensemble_manifest.py` validates the required model inputs and creates the Slurm task manifest.
- `percentile_change_worker.py` calculates model-level gridded percentile changes.
- `percentile_ensemble_worker.py` calculates the six-model ensemble mean, inter-model sample standard deviation, and model count.
- `percentile_ensemble_trends.py` creates regional ensemble summaries and trend plots.
- `wilks_annual_percentile_worker.py` calculates annual regional p98 and p99.9 time series from each model's historical and future seasonal NetCDF files.
- `wilks_heatmap_significance.py` averages the six models year by year and runs one Wilks-autocorrelation-corrected Welch test for each of the 72 heatmap cells.
- `summarize_ensemble_csvs.py` replaces the old pooled `count_csv_trues.py` utility on this branch. It validates the completed p98 and p99.9 regional tables, reads the independent Wilks results, and creates two compact five-metric CSVs, a direction tally, and one Wilks-marked model-direction heatmap.
- The `slurm_p98_*.sh` and `slurm_p99_9_*.sh` launchers run the model-change, ensemble, and trend stages for the 98th and 99.9th percentiles.
- `slurm_wilks_annual_percentiles.sh` runs the 216 annual-series tasks needed for the heatmap tests. Each task produces both percentiles, so a second percentile array is not needed.

The Slurm launchers write generated products below `WASP/outputs/` by default.

### Slurm Runtime Directories

Run the ensemble commands from the `WASP/` directory. The tracked programs and generated runtime folders are organized as follows:

```text
WASP/
  preprocessing/                 # Masking and seasonal-splitting programs
  src/wind_extreme_analysis/     # Reusable Python package and manifest builder
  tests/                         # Unit tests
  manifests/                     # Generated task tables; not tracked by Git
    ensemble_tasks.csv           # 216 model/scenario/period/season tasks
  logs/                          # Generated Slurm stdout and stderr; not tracked
  Outputs/                       # Original notebook workflow products
  outputs/                       # Ensemble workflow products
    p98_model_changes/
    p98_model_changes_final/     # Default input expected by later p98 stages
    p98_ensemble/
    p98_ensemble_trends/
    p99_9_model_changes_final/
    p99_9_ensemble_final/
    p99_9_ensemble_trends/
    wilks_annual_percentiles/    # Annual p98/p99.9 values from 216 Slurm tasks
    ensemble_csv_summary/        # Generated by summarize_ensemble_csvs.py
```

Create `logs/` before submitting jobs, then validate the ensemble inputs and write the manifest:

```bash
mkdir -p logs manifests
PYTHONPATH=src python -m wind_extreme_analysis.ensemble_manifest \
  --analysis-root /path/to/model_run_analysis \
  --output manifests/ensemble_tasks.csv
```

The manifest input root must use the model/run layout accepted by `ensemble_manifest.py`, such as `MODEL/historical_1995-2014/` and `MODEL/ssp245_2040-2059/`, with either seasonal files directly in each run directory or in a nested `seasons/` directory. The original preprocessing scripts preserve their historical staging paths, so copy, link, or point the processed seasonal files into this manifest layout before submitting the ensemble arrays.

The p98 change launcher writes to `outputs/p98_model_changes/`, while the later p98 ensemble and trend launchers default to `outputs/p98_model_changes_final/`. After quality control, either move/copy the accepted results to the latter directory or override `INPUT_ROOT` when submitting those stages.

In the seasonal trend figures, lines show the six-model ensemble means and the colored shading represents inter-model spread (±1 sample standard deviation). The shading is not a confidence interval and should not be interpreted by itself as a statistical-significance test.

### Calculate Heatmap Significance and Summarize the Tables

The Wilks correction requires ordered annual values. The existing regional model-change CSVs contain only one pooled historical-to-future change per model, so they do not contain the time dimension needed for this test. After the manifest is available, submit the annual-series array from the `WASP/` directory:

```bash
sbatch slurm_wilks_annual_percentiles.sh
```

After all 216 tasks finish successfully, form the combined six-model series and run the 72 cell tests:

```bash
python wilks_heatmap_significance.py \
  --annual-root outputs/wilks_annual_percentiles \
  --output-dir outputs/ensemble_csv_summary
```

Then validate the existing trend tables and draw the heatmap:

```bash
python summarize_ensemble_csvs.py
```

The program automatically reads:

```text
outputs/p98_ensemble_trends/p98_ensemble_trend_summary.csv
outputs/p98_ensemble_trends/p98_regional_model_values.csv
outputs/p99_9_ensemble_trends/p99_9_ensemble_trend_summary.csv
outputs/p99_9_ensemble_trends/p99_9_regional_model_values.csv
outputs/ensemble_csv_summary/wasp_heatmap_wilks_significance.csv
```

It validates each ensemble statistic against the six underlying model values, rounds displayed wind values to three decimal places (`0.001 m/s`), then writes:

```text
outputs/ensemble_csv_summary/wasp_agreement_summary.csv
outputs/ensemble_csv_summary/wasp_progression_summary.csv
outputs/ensemble_csv_summary/wasp_heatmap_wilks_significance.csv
outputs/ensemble_csv_summary/wasp_combined_ensemble_annual_percentiles.csv
outputs/ensemble_csv_summary/wasp_summary_tally.txt
outputs/ensemble_csv_summary/wasp_model_direction_wilks_significance_heatmap.png
```

The agreement CSV keeps every percentile/scenario/period/season separate and contains only five result metrics: ensemble mean, inter-model sample SD, number of models increasing, number decreasing, and number near zero. The three model counts always total six.

The progression CSV keeps every percentile/scenario/season separate and contains only five result metrics: early-, middle-, and late-period ensemble means, late minus early mean, and the progression pattern.

The text tally follows the concise style of the earlier `Summary of the summary.txt`, but it does not pool percentiles or report a misleading overall percentage. Each of its 18 blocks covers one percentile/scenario/period and reports four seasonal ensemble directions plus 24 model-season direction votes. Every count is followed by the exact seasons or `model/season` pairs behind it, in the standard WASP model and season order. These direction counts are descriptive and are not statistical-significance results.

The single heatmap keeps p98 and p99.9 in separate panels, puts scenarios and periods on the rows, and puts seasons on the columns. Color shows the model-direction balance (`models increasing - models decreasing`) on the fixed possible range from -6 to +6. These directions use each model's change in mean annual percentile, matching the statistic used by the significance workflow. Every cell also prints the exact increasing, decreasing, and near-zero model counts, so the plot does not rely on color alone. An asterisk marks a cell whose combined ensemble annual time series has a raw Wilks-corrected Welch p-value below alpha.

`wasp_heatmap_wilks_significance.csv` stores the values behind those markers: both lag-1 autocorrelations, both Wilks effective sample sizes, historical and future year counts, ensemble mean change, 95% confidence interval, Welch t statistic and degrees of freedom, raw p-value, alpha, and final per-cell significance flag. `wasp_combined_ensemble_annual_percentiles.csv` stores every annual value passed to the 72 tests so the calculation can be audited. Use `--alpha` on `wilks_heatmap_significance.py` to change the default 0.05 test level and corresponding 95% confidence level.

No Benjamini-Hochberg or other multiple-testing correction is applied to the heatmap. The 72 raw p-values are retained separately, and every cell is judged only against its configured alpha. An older generated `wasp_heatmap_significance.csv` or `wasp_model_direction_significance_heatmap.png` came from the retired six-model/FDR method and should not be used.

Use `--decimal-places` to override the three-decimal display default if a different precision is required. Older four-table summary files left by a previous program version are no longer created and can be ignored.

## Tests

Run the tests with: pytest

## Statistical Significance

The heatmap uses one combined ensemble time-series test per percentile/scenario/future-period/season cell. There are `2 percentiles x 3 scenarios x 3 future periods x 4 seasons = 72` tests. The complete calculation for one cell is:

1. For each model and retained year, calculate that year's seasonal p98 or p99.9 wind speed at every Minnesota grid cell.
2. Take the cosine-latitude-weighted Minnesota mean of that annual percentile field. This produces one regional annual value per model.
3. Align the six models by calendar year and average them year by year. This produces one combined historical ensemble series and one combined future ensemble series for the cell. A year is not used unless all six model values are present.
4. Calculate lag-1 autocorrelation separately for the ordered historical and future ensemble series: `rho = cor(x[t], x[t+1])`.
5. Convert each nominal year count to the Wilks effective sample size: `n_eff = n(1 - rho)/(1 + rho)`. Positive persistence reduces effective sample size; negative lag-1 correlation can increase it. The implementation retains the fractional result and does not round it to an integer.
6. Calculate a two-sided Welch unequal-variance t test for `future mean - historical mean = 0`, substituting each period's Wilks effective sample size into its mean-variance term: `SE^2 = s_hist^2/n_eff,hist + s_future^2/n_eff,future`.
7. Calculate the Welch-Satterthwaite degrees of freedom from those two adjusted mean-variance terms. The raw two-sided p-value is `2 P(T_df >= |t|)`.
8. Mark the cell when `raw p < alpha`. The default is `alpha = 0.05`. There is no FDR adjustment and no pooling of p-values across cells.

The confidence interval uses the same adjusted standard error and Welch degrees of freedom: `mean change +/- t_(1-alpha/2, df) SE`. At the default `alpha = 0.05`, the central probability is `1 - alpha = 0.95`, which is why the output is called a 95% confidence interval. It reports the range of mean changes compatible with this model under repeated sampling; it is not a range containing 95% of annual wind values. A two-sided 95% interval excludes zero exactly when the corresponding two-sided raw p-value is below 0.05, apart from numerical rounding.

This method tests the difference between the historical and future **mean annual regional percentiles**. That statistic is intentionally different from taking one percentile after pooling all timesteps across an entire 20-year period. Annual values are necessary to estimate autocorrelation and apply the Wilks correction.

The Wilks formula is an AR(1)-style approximation based on lag-1 dependence. The Welch test also assumes the historical and future period means can be compared as independent samples after that adjustment. Climate models are an ensemble of opportunity rather than guaranteed independent draws, but model independence is not used as the test sample size here: the six models are first averaged into one annual ensemble time series. Interpret each marker as evidence for that cell under these assumptions, not as proof that all possible models or all locations behave the same way. Because no multiple-testing correction is applied, testing 72 cells at alpha 0.05 can produce more false-positive markers than a familywise or FDR-controlled analysis.

The effective-sample-size equation follows the lag-1 correction described in Wilks' statistical methods for atmospheric science and in applied climate guidance. See [Wilks (1997), *Resampling Hypothesis Tests for Autocorrelated Fields*](https://journals.ametsoc.org/view/journals/clim/10/1/1520-0442_1997_010_0065_rhtfaf_2.0.co_2.xml) and the [University of Toronto climate-model guidebook's effective sample size example](https://utcdw.physics.utoronto.ca/UTCDW_Guidebook/Chapter3/section3.4_climate_model_output.html).

The separate raw-data workflow also supports block-bootstrap percentile confidence intervals, Mann-Whitney U and Kolmogorov-Smirnov distribution checks, and optional grid-cell bootstrap maps. Those tests do not control the asterisks on the ensemble direction heatmap. The temporal bootstrap can use block resampling so it does not treat every adjacent value as independent; the example config uses 56 timesteps, or 7 days of 3-hourly data.

## U/V Component Conversion

If future datasets provide `u` and `v` wind components instead of wind-speed magnitude, use:


python -m wind_extreme_analysis.uv_to_speed `
  --u-file PLACEHOLDER_U_FILE.nc `
  --v-file PLACEHOLDER_V_FILE.nc `
  --u-var PLACEHOLDER_U_VAR `
  --v-var PLACEHOLDER_V_VAR `
  --out PLACEHOLDER_OUTPUT_WIND_SPEED.nc `
  --speed-var PLACEHOLDER_WIND_SPEED_VAR
