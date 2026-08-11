# Running W.A.S.P. (Wind Analysis and Statistics Package) on MSI Jupyter

Use this when the NetCDF data are already on MSI and you do not want to download tens of GB locally.

## Recommended Folder Layout on MSI

Keep the same simple layout:

```text
/scratch.global/YOUR_X500/MCAP/
  WASP/
    wind_extreme_control.ipynb
    wind_extremes.config.json
    src/
    tests/
    outputs/
  Analysis/
    WSPD10_BCC-CSM2-MR_historical_1995-2014.nc
    WSPD10_BCC-CSM2-MR_ssp245_2040-2059_3hourly.nc
    WSPD10_BCC-CSM2-MR_ssp245_2060-2079_3hourly.nc
    ...
```

`WASP` is the program. `Analysis` is the data folder. `WASP/Outputs` is created when the notebook runs.

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

In an MSI terminal, try the conda/mamba route first if it is available:

```bash
cd /scratch.global/YOUR_X500/MCAP
module load mamba
mamba create -n mcap-wind -c conda-forge python=3.11 xarray dask netcdf4 h5netcdf scipy matplotlib pandas pytest ipykernel -y
conda activate mcap-wind
python -m ipykernel install --user --name mcap-wind --display-name "Python (MCAP wind)"
```

If `mamba` is not available, try a Python virtual environment:

```bash
cd /scratch.global/YOUR_X500/MCAP
python3 -m venv mcap-wind-env
source mcap-wind-env/bin/activate
python -m pip install --upgrade pip
python -m pip install -r WASP/requirements.txt
python -m ipykernel install --user --name mcap-wind --display-name "Python (MCAP wind)"
```

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
