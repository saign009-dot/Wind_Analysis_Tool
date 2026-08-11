"""Plotting helpers for wind extreme analysis."""
#a bunch of helper functions that create and save plots from analysis results
#overall flow: prepare output folder-> convert analysis result to NumPy-> choose a clean color scale-> create a Matplotlib figure-> plot by lon/lat if available
#-> otherwise plot by grid index-> optionally overlay significance dots-> add labels/colorbar/title-> save image file
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

#make sure output file exists before saving to it and return the path to it
def _ensure_parent(path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path

#convert data into numpy array
def _as_numpy(data):
    if hasattr(data, "values"):
        return np.asarray(data.values)
    return np.asarray(data)

#remove missing/infinite values
def _finite_sample(values, max_points: int = 250000, seed: int = 42) -> np.ndarray:
    array = np.asarray(values, dtype=float).ravel()
    array = array[np.isfinite(array)]
    #if there are too many values randomly keep a smaller sample
    if array.size > max_points:
        rng = np.random.default_rng(seed)
        array = rng.choice(array, size=max_points, replace=False)
    return array

#save a map like heat plot
def plot_spatial_change(
    change_da,
    output_path: str | Path,
    title: str,
    units: str = "",
    lat_name: str | None = None,
    lon_name: str | None = None,
    cmap: str = "RdBu_r",
    significance_mask=None,
):
    """Save a spatial heat map of a gridded change field."""
    import matplotlib.pyplot as plt
    #use functionn above to check for ouput foder and route result to it
    output_path = _ensure_parent(output_path)
    #convert the change data to a NumPy array so  matplotlib can plot it
    data = _as_numpy(change_da)
    #keep only the non zero and non infinite values
    finite = data[np.isfinite(data)]
    #use 98th percentile of absolute values to set color range
    vmax = float(np.nanquantile(np.abs(finite), 0.98)) if finite.size else 1.0
    #if values are zero force a color scale but this wont happen jsut a lil defensive code
    if vmax == 0:
        vmax = 1.0
    #create a figure and axes object for plottign 
    fig, ax = plt.subplots(figsize=(9, 7), constrained_layout=True)
    #try to find lat and lon in the xarray 
    lon = change_da.coords.get(lon_name) if lon_name and hasattr(change_da, "coords") and lon_name in change_da.coords else None
    lat = change_da.coords.get(lat_name) if lat_name and hasattr(change_da, "coords") and lat_name in change_da.coords else None
    #if can find lat lon then plot using those coordinates
    if lon is not None and lat is not None and lon_name is not None and lat_name is not None:
        mesh = ax.pcolormesh(
        _as_numpy(lon),
        _as_numpy(lat),
        data,
        cmap=cmap,
        vmin=-vmax,
        vmax=vmax,
        shading="auto",
        )
        ax.set_xlabel(lon_name)
        ax.set_ylabel(lat_name)
        #otherwise plot by grid index instead of geographic 
        #this might be problematic as we care about the geographic distribution quite a bit
    else:
        mesh = ax.imshow(data, cmap=cmap, vmin=-vmax, vmax=vmax, origin="lower", aspect="auto")
        ax.set_xlabel("grid x")
        ax.set_ylabel("grid y")
    #a significance mask will apply a black dot to grid cells where change passes statistical tests and should be noted
    #ideally this makes the heat map show the size/direction of change as well as where that change is statistically meaningful
    #if a significance map is provided overlay it on the heat map
    if significance_mask is not None:
        mask = _as_numpy(significance_mask).astype(bool) 
        y_idx, x_idx = np.where(mask) #find where the mask is true
        if y_idx.size:
            step = max(1, int(np.ceil(y_idx.size / 4000))) #thin dots if too many
            #all the conditionals below this jsut match dots to coordinates where possible
            if lon is not None and lat is not None:
                lon_values = _as_numpy(lon)
                lat_values = _as_numpy(lat)
                if lon_values.shape == mask.shape and lat_values.shape == mask.shape:
                    x_values = lon_values[mask]
                    y_values = lat_values[mask]
                elif lon_values.ndim == 1 and lat_values.ndim == 1:
                    lon_grid, lat_grid = np.meshgrid(lon_values, lat_values)
                    x_values = lon_grid[mask]
                    y_values = lat_grid[mask]
                else:
                    x_values = x_idx
                    y_values = y_idx
            else:
                x_values = x_idx
                y_values = y_idx
            ax.scatter(x_values[::step], y_values[::step], s=2, c="black", alpha=0.35, linewidths=0)
    #add color bar, title, save, close, and return the path
    cbar = fig.colorbar(mesh, ax=ax)
    cbar.set_label(units)
    ax.set_title(title)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path

#histogram to show full distribtuion shifts
def plot_histogram_comparison(
    historical_values,
    future_values,
    output_path: str | Path,
    title: str,
    percentile_lines: Iterable[float] = (0.98, 0.999),
    units: str = "",
):
    """Save overlaid histograms for historical and future distributions."""
    import matplotlib.pyplot as plt
    #make sure output exists and sample both historical and scenario values
    output_path = _ensure_parent(output_path)
    hist = _finite_sample(historical_values)
    fut = _finite_sample(future_values)
    #create the figure and plot the axes 
    fig, ax = plt.subplots(figsize=(9, 6), constrained_layout=True)
    ax.hist(hist, bins=80, density=True, alpha=0.45, label="Historical", color="#4C78A8")
    ax.hist(fut, bins=80, density=True, alpha=0.45, label="Future", color="#F58518")
    #include percentile reference lines 
    for q in percentile_lines:
        #percentile can be 0.98 or 98
        q_value = q if q <= 1 else q / 100
        ax.axvline(np.nanquantile(hist, q_value), color="#4C78A8", linestyle="--", linewidth=1.2) #historical percentile lines are blue
        ax.axvline(np.nanquantile(fut, q_value), color="#F58518", linestyle="--", linewidth=1.2) #future scenario percentile lines are orange

    ax.set_title(title)
    ax.set_xlabel(units or "value")
    ax.set_ylabel("density")
    ax.legend()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path


def plot_scenario_trends(
    summary: pd.DataFrame,
    output_path: str | Path,
    percentile: float,
    metric: str = "absolute_change",
    title: str | None = None,
):
    """Save scatter plots with one linear trend line per scenario."""
    import matplotlib.pyplot as plt

    output_path = _ensure_parent(output_path)
    subset = summary[np.isclose(summary["percentile"], percentile)]
    subset = subset[np.isfinite(subset["midyear"]) & np.isfinite(subset[metric])]

    fig, ax = plt.subplots(figsize=(8.5, 6), constrained_layout=True)
    colors = {"ssp245": "#54A24B", "ssp370": "#B279A2", "ssp585": "#E45756"}

    for scenario, group in subset.groupby("scenario"):
        color = colors.get(str(scenario), None)
        ax.scatter(group["midyear"], group[metric], label=scenario, s=52, color=color)
        if len(group) >= 2:
            slope, intercept = np.polyfit(group["midyear"], group[metric], deg=1)
            x_line = np.linspace(group["midyear"].min(), group["midyear"].max(), 50)
            ax.plot(x_line, slope * x_line + intercept, color=color, linewidth=1.8)

    ax.axhline(0, color="black", linewidth=0.8, alpha=0.7)
    ax.set_title(title or f"Scenario trend for percentile {percentile:g}")
    ax.set_xlabel("period midpoint year")
    ax.set_ylabel(metric.replace("_", " "))
    ax.legend(title="scenario")
    fig.savefig(output_path, dpi=180)
    plt.close(fig)
    return output_path
