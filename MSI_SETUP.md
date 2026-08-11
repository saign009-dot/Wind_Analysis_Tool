# Running W.A.S.P. (Wind Analysis and Statistics Package) on MSI Jupyter

Use this when the NetCDF data are already on MSI and you do not want to download tens of GB locally.

## Complete Folder Layout on MSI

Keep the same simple layout:

```text
/scratch.global/YOUR_X500/MCAP/
  WASP/
    preprocessing/
    src/
    tests/
    wind_extreme_control.ipynb
    wind_extremes.config.json
    manifests/
      ensemble_tasks.csv
    logs/
    Outputs/
    outputs/
      p98_model_changes/
      p98_model_changes_final/
      p98_ensemble/
      p98_ensemble_trends/
      p99_9_model_changes_final/
      p99_9_ensemble_final/
      p99_9_ensemble_trends/
  Analysis/
    BCC-CSM2-MR/
      historical_1995-2014/
        seasons/
          WSPD10_BCC-CSM2-MR_historical_1995-2014_MNmasked_DJF.nc
          ...
      ssp245_2040-2059/
        seasons/
          WSPD10_BCC-CSM2-MR_ssp245_2040-2059_MNmasked_DJF.nc
          ...
    ...
```

`WASP` is the program. `Analysis` is the model/run input tree used by the ensemble manifest. `WASP/Outputs` contains original notebook products, while lowercase `WASP/outputs` contains ensemble products. `WASP/manifests` and `WASP/logs` are generated runtime directories and are intentionally excluded from Git.

## Upload Only the Tool Folder

From Windows PowerShell, upload the small tool folder:

```powershell
scp -r .\WASP YOUR_X500@login.msi.umn.edu:/scratch.global/YOUR_X500/MCAP/
```

Do not upload the giant NetCDF files if they already exist on MSI.

## Put or Link the Data on MSI

If the data are already in another MSI folder, either update `wind_extremes.config.json` to use those absolute MSI paths, or make an `Analysis` folder next to `WASP`.

Relative paths in the config are easiest:

```json
"path": "Analysis/WSPD10_BCC-CSM2-MR_ssp585_2040-2059_3hourly.nc"
```

That means the file should be here:

```text
/scratch.global/YOUR_X500/MCAP/Analysis/WSPD10_BCC-CSM2-MR_ssp585_2040-2059_3hourly.nc
```

Avoid Windows paths on MSI. This will not work on MSI:

```json
"path": "C:/Users/wesja/some_file.nc"
```

Use a relative Linux path:

```json
"path": "Analysis/some_file.nc"
```

or an absolute Linux path:

```json
"path": "/scratch.global/YOUR_X500/MCAP/Analysis/some_file.nc"
```

## Create a Python Environment

Follow [MSI's best practices for managing conda environments](https://msi.umn.edu/getting-started/help/knowledge-base/best-practices-conda). MSI recommends Miniforge because it uses community-managed channels by default.

Create a dedicated, self-contained environment in an appropriate software location. Replace `/path/to/software` with a durable location in your group directory or personal software directory:

```bash
cd /scratch.global/YOUR_X500/MCAP
module load miniforge
conda create --copy -p /path/to/software/mcap-wind-env python=3.11 numpy pandas xarray dask netcdf4 h5netcdf scipy matplotlib pytest ipykernel cdo geopandas regionmask -y
source activate /path/to/software/mcap-wind-env
python -m ipykernel install --user --name mcap-wind --display-name "Python (MCAP wind)"
```

MSI recommends `source activate` for HPC environments rather than `conda activate`. Keep the environment outside the Git repository; commit an environment snapshot, not the installed environment itself.

After the environment is working, record its package versions for reproducibility:

```bash
conda env export --no-builds > WASP/environment.yml
```

## Reproduce Masking and Seasonal Splitting

The `WASP/preprocessing/` folder preserves the programs used before the wind analysis. They depend on CDO, GeoPandas, Regionmask, Xarray, the source WSPD10 NetCDF files, and the 2024 U.S. Census state-boundary shapefile referenced by `make_mn_masks.py`.

The programs retain the absolute MSI paths used for the original processing. Before rerunning them, review and update `PROJECT_ROOT`, `TOOL_ROOT`, `MASK_DIR`, `SOURCE_BASE`, and `STATE_SHAPEFILE`. Generate the grid-specific masks first, stage them in the directory expected by `MASK_DIR`, and preview the CDO operations before allowing writes:

```bash
cd /scratch.global/YOUR_X500/MCAP/WASP
python preprocessing/make_mn_masks.py
bash preprocessing/mask_and_split_all.sh
bash preprocessing/mask_and_split_all.sh run
```

Use `mask_and_split_all_forMIROC.sh` only for the separate MIROC rerun. The preprocessing scripts preserve the historical staging paths used for the analysis. Before building an ensemble manifest, copy or link the accepted seasonal products into the model/run layout shown above, or point `--analysis-root` to an equivalent existing layout.

## Create Slurm Manifests and Logs

The Slurm launchers write scheduler output to `logs/` and read `manifests/ensemble_tasks.csv`. Create the log directory before calling `sbatch`, because Slurm opens its output files before the job body runs:

```bash
cd /scratch.global/YOUR_X500/MCAP/WASP
mkdir -p logs manifests
PYTHONPATH=src python -m wind_extreme_analysis.ensemble_manifest \
  --analysis-root /scratch.global/YOUR_X500/MCAP/Analysis \
  --output manifests/ensemble_tasks.csv
```

The manifest builder validates all required files before writing its 216 task rows. If anything is missing, it prints the expected paths and exits without creating a runnable manifest.

The p98 change stage defaults to `outputs/p98_model_changes/`, but the p98 ensemble and trend stages default to `outputs/p98_model_changes_final/`. After checking the model-level results, either copy or move the accepted files into the `final` directory or submit the later stages with `INPUT_ROOT` set to the reviewed location. The p99.9 workflow writes and reads `outputs/p99_9_model_changes_final/` by default.

## Open Jupyter on MSI

1. Start an MSI Jupyter/JupyterLab session.
2. Navigate to:

   ```text
   /scratch.global/YOUR_X500/MCAP/WASP/
   ```

3. Open:

   ```text
   wind_extreme_control.ipynb
   ```

4. Select the kernel:

   ```text
   Python (MCAP wind)
   ```

5. Run the config-check cell first.

## Output Location

Outputs should appear here:

```text
/scratch.global/YOUR_X500/MCAP/WASP/Outputs/WSPD10/
```

If `scratch.global` is temporary storage for your MSI account, copy important final outputs to a more permanent project or home location.
