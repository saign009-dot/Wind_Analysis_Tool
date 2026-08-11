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

## Input Data Preprocessing

The NetCDF inputs analyzed by WASP were first spatially masked to Minnesota and then split into DJF, MAM, JJA, and SON files. The programs used for that preparation are preserved in `preprocessing/`:

1. `directory_subdirectory_maker.sh` creates the original model/scenario scratch-directory layout.
2. `make_mn_masks.py` builds a grid-specific Minnesota mask for each model using a U.S. Census state-boundary shapefile.
3. `mask_and_split_all.sh` applies each mask with CDO `ifthen` and creates the four seasonal files with CDO `selseas`.
4. `mask_and_split_all_forMIROC.sh` is the MIROC-specific rerun used when processing that model separately.

These scripts preserve the project-specific MSI paths used for the analysis. Review `PROJECT_ROOT`, `TOOL_ROOT`, `MASK_DIR`, `SOURCE_BASE`, `STATE_SHAPEFILE`, model names, and filename patterns before reusing them. The masking scripts default to a non-writing preview; pass `run` only after reviewing the displayed paths.

```bash
bash preprocessing/mask_and_split_all.sh
bash preprocessing/mask_and_split_all.sh run
```

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
