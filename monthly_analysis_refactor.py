#dependencies
from pathlib import Path#for file path handling
import xarray as xr #for netcdf handling
import numpy as np #for cosine latt weighting
import matplotlib.pyplot as plt #for visualization
from matplotlib.ticker import MultipleLocator #for axis and gridline customizability



# Define the path to the data directory
def percentile_path(root,run,month):
    filename= f"WSPD10_6model_{run}_MNmasked_{month}_percentiles.nc"
    return Path(root)/run/filename 


#produce a monthly change summary for a given month and future run
def monthly_change_summary(root, future_run, month, variable):
#construct historical and future paths
    historical_run='historical_1995-2014'
    historical=percentile_path(root, historical_run, month)
    future=percentile_path(root, future_run, month)
#check that both files exist and raise error if not
    if historical.is_file() != True:
        print('historical file not found')
    if future.is_file() != True:
        print('future file not found')
#open both datasets
    with(
        xr.open_dataset(historical) as historical_ds,
        xr.open_dataset(future) as future_ds,
    ):
#select the variable
        historical_p=historical_ds[variable]
        future_p=future_ds[variable]
#align the data
        future_p, historical_p = xr.align(future_p, historical_p, join='exact')
#calculate change and load to memory
        change=(future_p-historical_p).load()
#identify all dims except model and avarage them also aggregate values for single month change into one value per model
    field=change
    spatial_dimensions=tuple(
    dimension for dimension in field.dims if dimension == 'lat' or dimension=='lon')
#weight by area avarage
    latitude_weights=np.cos(
        np.deg2rad(field['lat'])
    )
    model_changes=field.weighted(
        latitude_weights
    ).mean(
        dim=spatial_dimensions,
        skipna=True
    )
#calculate mean and model spread (SD)
    ensemble_mean=model_changes.mean('model')
    inter_model_sd=model_changes.std('model', ddof=1)
    return model_changes, ensemble_mean, inter_model_sd


#plot the change with the model spread
def plot(months, mo_mean, mo_sd, run, percentile):
    fig, ax=plt.subplots(figsize=(10,5))

    ax.bar(months, mo_mean, yerr=mo_sd, capsize=5, color='blue')
    ax.axhline(0, color='black', linewidth=0.5)
    ax.yaxis.set_major_locator(MultipleLocator(0.1))
    ax.set_axisbelow(True)

    ax.grid(
        axis="y",
        linestyle="--",
        linewidth=0.7,
        alpha=0.5,
    )
    ax.yaxis.set_minor_locator(MultipleLocator(0.05))

    ax.grid(
        axis="y",
        which="minor",
        linestyle=":",
        linewidth=0.4,
        alpha=0.3,
    )

    ax.set_ylabel('Change in Wind Speed (m/s-1)')
    ax.set_xlabel('Month')
    ax.set_title(f'Change in {percentile} Wind Speed for {run}')

    plt.tight_layout()
    plt.savefig(f'{run}_{percentile}.png', dpi=300, bbox_inches='tight') #should make this so it saves to a specific folder instead of the working directory


#make some lists that can be used for loops
months=['01','02','03','04','05','06','07','08','09','10','11','12']
future_runs=['ssp245_2040-2059','ssp245_2060-2079','ssp245_2080-2099','ssp370_2040-2059','ssp370_2060-2079','ssp370_2080-2099','ssp585_2040-2059','ssp585_2060-2079','ssp585_2080-2099'] #note ssp585 is discontinued
percentiles=['p98_period','p99_9_period'] 
#loop through variables time periods and scenarios
for percentile in percentiles:
    for run in future_runs:
        mo_mean=[]
        mo_sd=[]
    #loopo through producing a monthly summary for each month and storing the results in lists
        for month in months:
            model_changes, ensemble_mean, inter_model_sd = monthly_change_summary(
            root=Path(
                r"C:\Users\wesja\Desktop\MCAP\Wind_Analysis_Tool"
                r"\WASP\monthly_percentiles"
            ),
            future_run=run,
            month=month,
            variable=percentile,
        )
            mo_mean.append(ensemble_mean.item())
            mo_sd.append(inter_model_sd.item())


    #call the graphing function
        plot(months, mo_mean, mo_sd, run, percentile)