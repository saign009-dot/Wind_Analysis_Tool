"""Core xarray analysis helpers for extreme wind percentiles."""

#overall flow is open data -> select variable -> compute percentiles -> compare future vs historical -> summarize or clean data

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

#imports helper functions from this projects config.py file
from .config import is_placeholder, normalize_percentile, percentile_label, resolve_path


def open_dataset(path: str | Path, chunks: dict[str, int] | None = None, decode_times: bool = True): 
    """Open a NetCDF dataset with xarray, importing xarray only when needed.""" 
    #import xarray inside the function so the package is only loaded when this helper is used
    import xarray as xr
    # Open the NetCDF file at path
    # chunks are segments... large files are to be loaded into memory in segments to avoid crashing
    # decode_times tells xarray whether to convert time values into date/time objects ie 0, 1 -> 10/25/2025, 10/26/2025
    return xr.open_dataset(path, chunks=chunks, decode_times=decode_times)


def open_dataarray(
    path: str | Path,
    variable: str,
    chunks: dict[str, int] | None = None,
    decode_times: bool = True,
):
    """Open one variable from a NetCDF file as an xarray DataArray."""
    #stop eary if the config file still has a placeholder name
    if is_placeholder(variable):
        raise ValueError("Replace PLACEHOLDER_WIND_VAR with the actual NetCDF variable name.")
    #uses to function above to open netcdf and assign it to a Variable 
    #'Variable' means python variable 'variable' means netcdf variable
    dataset = open_dataset(path, chunks=chunks, decode_times=decode_times)
    
    #check that variable actually exists and if it doesnt complain and hint
    if variable not in dataset:
        #build a list of
        available = ", ".join(str(name) for name in dataset.data_vars)
        dataset.close()
        raise KeyError(f"Variable {variable!r} was not found in {path}. Available variables: {available}")
    #return only the requested variable from the dataset
    return dataset[variable]

#automatically detects which demensions are spatial
def infer_spatial_dims(data, time_dim: str) -> list[str]:
    """Return dimensions other than time and xarray's quantile dimension."""
    return [dim for dim in data.dims if dim not in {time_dim, "quantile"}] #docstring above


def percentile_field(data, percentile: float, time_dim: str):
    """Compute a spatial field of a percentile across time."""
    #convert percentiles intoo 0-1 format and assign that bhavior to Variable
    q = normalize_percentile(percentile)
    #compute percentiles across time and ignore missing values return that computation to Variable
    result = data.quantile(q, dim=time_dim, skipna=True)
    
    #AI code that fixed an issue i was having I dont exactly understand but seems to be good for the output
    if "quantile" in result.coords and result.sizes.get("quantile") == 1:
        result = result.squeeze("quantile", drop=True)
    #give name, store, and return calulated percentile field
    result.name = percentile_label(q)
    result.attrs["percentile"] = q
    return result


def percentile_fields(data, percentiles: list[float], time_dim: str) -> dict[float, Any]:
    """Compute multiple percentile fields across time."""
    #loop through each requested percentile and store them in a dictionary
    #dict key is percentile value ie 0.98
    #dict value is the xarray datarray produced by percentile_field()
    return {normalize_percentile(q): percentile_field(data, q, time_dim) for q in percentiles}

#compares future percentiles to historical percentiles
def change_fields(historical_field, future_field) -> dict[str, Any]:
    """Return absolute and percent change relative to historical."""
    absolute = future_field - historical_field #future value-historical value
    #give the absolute-change datarraya name
    absolute.name = f"{future_field.name}_absolute_change"
    #calculate a percent change and give it a name and does not ignores historical 0 values
    percent = absolute / historical_field.where(historical_field != 0) * 100.0
    percent.name = f"{future_field.name}_percent_change"
    #return both absolute and percent change stored in a dictionary
    return {"absolute": absolute, "percent": percent}


def area_weighted_mean(data, lat_name: str | None = None, time_dim: str | None = None):
    """Compute a regional mean, using cosine-latitude weights when possible."""
    #take all dimensions in the data
    spatial_dims = list(data.dims)
    #if time dimension tags along get rid of it
    if time_dim in spatial_dims:
        spatial_dims.remove(time_dim)
        #if wuantile dim exists get rid of it
    if "quantile" in spatial_dims:
        spatial_dims.remove("quantile")
        #if no spatial dimension do nothing
    if not spatial_dims:
        return data
    #more AI code that is smarter than me; tries to take a weighted average but if that fails foes back to regualar average
    if lat_name and lat_name in data.coords:
        weights = np.cos(np.deg2rad(data[lat_name]))
        try:
            return data.weighted(weights).mean(dim=spatial_dims, skipna=True)
        except Exception: #this is kind of a problematic line beacuse it ignores errors with averaging and just moves on
            pass

    return data.mean(dim=spatial_dims, skipna=True)

#turns each lat, lon, time sample into a single dimensionless point for plotting and statisitcs
def flatten_valid(*arrays) -> list[np.ndarray]:
    """Flatten arrays and keep finite values shared by all inputs."""
    flattened = [np.asarray(array).ravel() for array in arrays]
    if not flattened:
        return []

    mask = np.ones(flattened[0].shape, dtype=bool)
    for array in flattened:
        mask &= np.isfinite(array)

    return [array[mask] for array in flattened]

#configures chunk settings
def prepare_chunks(dataset_config: dict[str, Any]) -> dict[str, int] | None:
    """Convert placeholder chunk keys to real dimension names."""
    chunks = dataset_config.get("chunks")
    if not chunks:
        return None

    time_dim = dataset_config.get("time_dim")
    prepared: dict[str, int] = {}
    for key, value in chunks.items():
        chunk_key = time_dim if is_placeholder(key) else key
        if not is_placeholder(chunk_key):
            prepared[str(chunk_key)] = int(value)
    return prepared or None

#looks at config file and uses function above for chunk settings
def load_period_dataarray(
    period_config: dict[str, Any],
    dataset_config: dict[str, Any],
    base_dir: str | Path | None = None,
):
    """Load a historical or future period from config."""
    path = resolve_path(period_config["path"], base_dir=base_dir)
    #use the function above to pull up chunk settings
    chunks = prepare_chunks(dataset_config)
    return open_dataarray(path, variable=dataset_config["variable"], chunks=chunks)

#give each time period interval a single x value at its midpoint for scatter plot and trend lines
def period_midyear(period_config: dict[str, Any]) -> float:
    """Return the midpoint year for a period config."""
    years = period_config.get("years")
    if years and len(years) == 2:
        return (float(years[0]) + float(years[1])) / 2.0

    label = str(period_config.get("period", ""))
    if "-" in label:
        start, end = label.split("-", maxsplit=1)
        return (float(start) + float(end)) / 2.0

    return np.nan

