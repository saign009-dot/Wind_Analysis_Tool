# Running the Wind Analysis Tool on MSI Jupyter

Use this when the NetCDF data are already on MSI and you do not want to download tens of GB locally.

## Recommended Folder Layout on MSI

Keep the same simple layout:

```text
/scratch.global/YOUR_X500/MCAP/
  Wind_Analysis_Tool/
    preprocessing/
    wind_extreme_control.ipynb
    wind_extremes.config.json
    src/
    tests/
    Analysis/
      historical_1995-2014/
        seasons/
      ssp245_2040-2059/
        seasons/
      ...
    outputs/
  Analysis/
    WSPD10_BCC-CSM2-MR_historical_1995-2014.nc
    WSPD10_BCC-CSM2-MR_ssp245_2040-2059_3hourly.nc
    WSPD10_BCC-CSM2-MR_ssp245_2060-2079_3hourly.nc
    ...
```

`Wind_Analysis_Tool` is the program. The sibling `Analysis` folder is the simple notebook input layout, while the unchanged preprocessing scripts write their seasonal products below `Wind_Analysis_Tool/Analysis/`. The notebook can use either location when its configuration paths are set consistently. `Wind_Analysis_Tool/outputs` is created when the notebook runs.

## Upload Only the Tool Folder

From Windows PowerShell, upload the small tool folder:

```powershell
scp -r C:\Users\wesja\Desktop\MCAP\Wind_Analysis_Tool YOUR_X500@login.msi.umn.edu:/scratch.global/YOUR_X500/MCAP/
```

Do not upload the giant NetCDF files if they already exist on MSI.

## Put or Link the Data on MSI

If the data are already in another MSI folder, either update `wind_extremes.config.json` to use those absolute MSI paths, or make an `Analysis` folder next to `Wind_Analysis_Tool`.

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
conda env export --no-builds > Wind_Analysis_Tool/environment.yml
```

## Reproduce Masking and Seasonal Splitting

The original preprocessing programs are preserved unchanged in `Wind_Analysis_Tool/preprocessing/`. They depend on CDO, GeoPandas, Regionmask, Xarray, the source WSPD10 NetCDF files, and the 2024 U.S. Census state-boundary shapefile referenced by `make_mn_masks.py`.

The programs retain the absolute MSI paths used during the original work. Before rerunning them, review `PROJECT_ROOT`, `TOOL_ROOT`, `MASK_DIR`, `SOURCE_BASE`, and `STATE_SHAPEFILE`. Generate and inspect the model-specific masks first. The mask generator writes them to `TOOL_ROOT`, while the seasonal-splitting scripts expect them in `MASK_DIR`, so copy or link the accepted files to that directory.

Preview the CDO work before allowing writes:

```bash
cd /projects/standard/hroop/shared/YOUR_X500/wind_program/Wind_Analysis_Tool
python preprocessing/make_mn_masks.py
bash preprocessing/mask_and_split_all.sh
bash preprocessing/mask_and_split_all.sh run
```

Use `mask_and_split_all_forMIROC.sh` only for the separate MIROC rerun. The seasonal files are written below `Wind_Analysis_Tool/Analysis/<run>/seasons/` using the original filename conventions.

## Open Jupyter on MSI

1. Start an MSI Jupyter/JupyterLab session.
2. Navigate to:

   ```text
   /scratch.global/YOUR_X500/MCAP/Wind_Analysis_Tool/
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
/scratch.global/YOUR_X500/MCAP/Wind_Analysis_Tool/outputs/WSPD10/
```

If `scratch.global` is temporary storage for your MSI account, copy important final outputs to a more permanent project or home location.

