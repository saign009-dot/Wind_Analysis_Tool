# Wind Analysis Tool

This `main` branch preserves the original Wind Analysis Tool used for the initial analysis. It does not include the later multi-model ensemble calculations.

## Scientific Lineage

This repository intentionally maintains two versions:

- [`main`](https://github.com/saign009-dot/Wind_Analysis_Tool/tree/main) is the historical Wind Analysis Tool version.
- [`WASP`](https://github.com/saign009-dot/Wind_Analysis_Tool/tree/WASP) is the refined Wind Analysis and Statistics Package, which adds the ensemble-analysis workflow.

The branches remain separate to make the methodological change explicit and reproducible. The `WASP` branch should not be merged into `main`, because doing so would alter the historical version represented here.

## Original Tool Contents

- [`Wind_Analysis_Tool/`](Wind_Analysis_Tool/) contains the original analysis package, notebook, configuration, tests, and CSV summary utility.
- [`Wind_Analysis_Tool/preprocessing/`](Wind_Analysis_Tool/preprocessing/) contains the original programs used to create Minnesota masks, apply them to the source NetCDF files, and split the masked files into meteorological seasons.
- [`Wind_Analysis_Tool/README.md`](Wind_Analysis_Tool/README.md) contains the detailed workflow and statistical-method documentation.
- [`MSI_SETUP.md`](MSI_SETUP.md) documents the MSI Miniforge setup and folder layout.

Large NetCDF inputs and generated analysis products are intentionally excluded from the repository.
