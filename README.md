# W.A.S.P. — Wind Analysis and Statistics Package

This `WASP` branch contains the refined Wind Analysis and Statistics Package, including the original wind-analysis workflow and the later multi-model ensemble calculations.

## Scientific Lineage

This repository intentionally maintains two versions:

- [`main`](https://github.com/saign009-dot/Wind_Analysis_Tool/tree/main) preserves the original Wind Analysis Tool used for the initial analysis, without the ensemble additions.
- [`WASP`](https://github.com/saign009-dot/Wind_Analysis_Tool/tree/WASP) contains the renamed and expanded reanalysis package.

The branches remain separate to make the change in methodology explicit and reproducible. The `WASP` branch should not be merged into `main`, because `main` serves as the historical record.

## WASP Contents

- [`WASP/`](WASP/) contains the analysis package, notebook, configuration, tests, CSV summary utility, ensemble workers, and Slurm launchers.
- [`WASP/README.md`](WASP/README.md) contains detailed workflow and statistical-method documentation.
- [`MSI_SETUP.md`](MSI_SETUP.md) documents the MSI Miniforge setup and folder layout.

## Added Ensemble Capabilities

The WASP workflow includes model-level 98th- and 99.9th-percentile change calculations, six-model ensemble means, inter-model sample standard deviations, model counts, regional summaries, trend plots, and Slurm launchers for MSI.

Large NetCDF inputs and generated analysis products are intentionally excluded from the repository.
