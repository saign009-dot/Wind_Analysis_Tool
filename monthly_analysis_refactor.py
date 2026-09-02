#dependencies
from pathlib import Path #for file path handling
import xarray as xr #for netcdf handling
import numpy as np #for cosine latt weighting
import matplotlib.pyplot as plt #for visualization
from matplotlib.ticker import MultipleLocator #for axis and gridline customizability



# Define the path to the data directory
def percentile_path(root,run,month):
    filename= f"WSPD10_6model_{run}_MNmasked_{month}_percentiles.nc"
    return Path(root)/run/filename 


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
    dimension for dimension in field.dims if dimension != 'model')
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
def plot():
    fig, ax=plt.subplots(figsize=(4,5))

    ax.bar('Y', float(ensemble_mean.item()), yerr=float(inter_model_sd.item()), capsize=5, color='blue')
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

    ax.set_ylabel('Change in X Percentile Wind Speed (m/s)')
    ax.set_title('Change in X Percentile Wind Speed for Y')

    plt.tight_layout()
    plt.show()


#execute a monthly summary
model_changes, ensemble_mean, inter_model_sd = monthly_change_summary(
    root=Path(
        r"C:\Users\wesja\Desktop\MCAP\Wind_Analysis_Tool"
        r"\WASP\monthly_percentiles"
    ),
    future_run="ssp245_2040-2059",
    month="01",
    variable="p99_9_period",
)


#call the graphing function
plot()