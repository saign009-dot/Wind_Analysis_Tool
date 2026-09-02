#dependencies
from pathlib import Path #for file path handling
import xarray as xr #for netcdf handling
import numpy as np #for cosine latt weighting
import matplotlib.pyplot as plt #for visualization



# Define the path to the data directory
def percentile_path(root,run,month):
    filename= f"WSPD10_6model_{run}_MNmasked_{month}_percentiles.nc"
    return Path(root)/run/filename 

#define future, historical, root, and month
month="01"
root=Path(r"C:\Users\wesja\Desktop\MCAP\Wind_Analysis_Tool\WASP\monthly_percentiles")
historical=percentile_path(root, "historical_1995-2014", month)
future=percentile_path(root, "ssp245_2040-2059", month)

#check thath the files exist
print("Historical:", historical)
print("Exists:", historical.is_file())
print("Future:", future)
print("Exists:", future.is_file())


#inspect the dataset for the percentile variables
with xr.open_dataset(historical) as historical_ds:
    print("Historical Dataset:")
    print(historical_ds)

with xr.open_dataset(future) as future_ds:
    print("Future Dataset:")
    print(future_ds)


#variables exisit so assign them
variables = ['p98_period','p99_9_period']


#calculate grid change between historical and future percentiles
with(
    xr.open_dataset(historical) as historical_ds, #open the ds with 'as' to allow it to be initialized but also close it when done
    xr.open_dataset(future) as future_ds,
): #assign the datasets to the variables
    historical_percentiles=historical_ds[variables]
    future_percentiles=future_ds[variables]
    #explicitly aling coordinates before calculating the change
    future_percentiles, historical_percentiles = xr.align(future_percentiles, historical_percentiles, join='exact') #align the datasets to ensure they have the same coordinates
    change=(future_percentiles - historical_percentiles).load() #calculate the change and load it into memory

    print(change)


#check the change dataset to make sure values make sense and are not all NaN
for variable in ['p98_period', 'p99_9_period']:
    field=change[variable]

    valid=int(field.count().item())
    total=field.size

    print(variable)
    print('valid values', valid)
    print('total values', total)

    if valid>0:
        print('minimum change:', float(field.min(skipna=True).item()))
        print('maximum change:', float(field.max(skipna=True).item()))


#aggregate the change for single month into one value per model
field=change['p99_9_period']

print('dimensions:', field.dims)

spatial_dimensions=tuple(
    dimension for dimension in field.dims if dimension != 'model')
print('spatial dimensions:', spatial_dimensions)
model_changes=field.mean(dim=spatial_dimensions, skipna=True)
print(model_changes)

#calculate ensemble mean of change and inter-model standard deviation
ensemble_mean=model_changes.mean('model')
inter_model_sd=model_changes.std('model', ddof=1)
print('January ensemble mean:', float(ensemble_mean.item()))
print('January inter-model standard deviation:', float(inter_model_sd.item()))

#plot the change for janurary with the model spread
fig, ax=plt.subplots(figsize=(4,5))

ax.bar('Janurary', float(ensemble_mean.item()), yerr=float(inter_model_sd.item()), capsize=5, color='blue')

ax.axhline(0, color='black', linewidth=1)

ax.set_ylabel('Change in 99.9th Percentile Wind Speed (m/s)')
ax.set_title('Change in 99.9th Percentile Wind Speed for January')

plt.tight_layout()
plt.show()




