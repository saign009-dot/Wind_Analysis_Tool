# W.A.S.P. — Wind Analysis and Statistics Package

This `WASP` branch contains the refined 'Wind Analysis and Statistics Package', including the original single model wind-analysis workflow and the later multi-model ensemble calculations.

## Version History

This repository intentionally maintains two versions:

- [`main`](https://github.com/saign009-dot/Wind_Analysis_Tool/tree/main) preserves the original Wind Analysis Tool used for the initial analysis, without the ensemble additions.
- [`WASP`](https://github.com/saign009-dot/Wind_Analysis_Tool/tree/WASP) contains the renamed and expanded reanalysis package.

The branches remain separate to make the change in methodology explicit and reproducible. The `WASP` branch should not be merged into `main`, because `main` serves as the historical record.

## Computing Requirements

WASP does not require MSI or another high-performance computing (HPC) system. Small tests, individual models, and the final ensemble summaries can be run on a sufficiently capable local computer. MSI or comparable HPC resources are strongly recommended for the complete six-model 98th- and 99.9th-percentile analysis because it consists of hundreds of independent, memory-intensive NetCDF tasks. The included Slurm launchers are specifically intended for running that full workflow on MSI.

## WASP Contents

- [`WASP/`](WASP/) contains the analysis package, notebook, configuration, tests, ensemble workers, Slurm launchers, and the replacement `summarize_ensemble_csvs.py` utility. The original `count_csv_trues.py` remains on the historical `main` branch; it was replaced on `WASP` because its pooled metric had limited scientific value.
- [`WASP/preprocessing/`](WASP/preprocessing/) contains the programs used to create Minnesota masks, apply them to the source NetCDF files, and split the masked files into meteorological seasons.
- [`WASP/README.md`](WASP/README.md) contains detailed workflow and statistical-method documentation.
- [`MSI_SETUP.md`](MSI_SETUP.md) documents the MSI Miniforge setup and recommended folder layout.

During Slurm ensemble runs, WASP creates untracked `WASP/manifests/`, `WASP/logs/`, and `WASP/outputs/` directories for task tables, scheduler logs, and calculated products. Their expected structure and creation commands are documented in `MSI_SETUP.md`.

## Added Ensemble Capabilities

The WASP workflow includes model-level 98th and 99.9th percentile change calculations, six-model ensemble means, inter-model sample standard deviations, model counts, regional trend tables and plots, CSV-only result summaries, and Slurm launchers for MSI.

Large NetCDF inputs and generated outputs are intentionally not duplicated in this repository. They are stored, respectively, on MCAP MSI storage and in the MCAP team drive under `proj_wind analysis_undergradRA`.
