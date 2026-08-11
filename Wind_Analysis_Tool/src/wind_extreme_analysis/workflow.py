"""Config-driven end-to-end analysis workflow."""
#general flow: read config -> choose dataset -> validate config -> create output folder -> load historical data -> 
    # compute historical percentiles -> loop through future periods -> make histogram -> loop through requested percentiles -> 
    # compute future percentile -> calculate future minus historical change -> optionally create grid-cell significance mask -> 
    # save absolute and percent change maps -> run regional bootstrap/statistical tests -> collect summary rows -> save summary CSV -> 
    # create scenario trend plots -> return summary table
 #this is the main guy it pulls from all the other programs to make a workflow
 #it ignores uv_to_speed because we dont need is for WSPD10
from __future__ import annotations
#you can run this from the command line
import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .analysis import (
    area_weighted_mean,
    change_fields,
    load_period_dataarray,
    percentile_field,
    period_midyear,
)
from .config import (
    get_dataset_config,
    load_config,
    normalize_percentile,
    percentile_label,
    validate_dataset_config,
)
from .plots import plot_histogram_comparison, plot_scenario_trends, plot_spatial_change
from .stats import (
    benjamini_hochberg,
    bootstrap_percentile_difference,
    gridcell_bootstrap_significance,
    ks_pvalue,
    mann_whitney_pvalue,
)

#define a name for our scenario and time step
def _period_id(period: dict[str, Any]) -> str:
    parts = [period.get("scenario"), period.get("period") or period.get("label")] #use netcdf attributes if they exist
    return "_".join(str(part) for part in parts if part) #join the pulled attributes together with underscores

#convert gridded data into values for regional statisticl tests
def _values_for_stats(data, time_dim: str, lat_name: str | None):
    #average across space using lattitude weights if possoble
    regional_series = area_weighted_mean(data, lat_name=lat_name, time_dim=time_dim)
    #save results as an array
    return np.asarray(regional_series.load().values, dtype=float)

#run the complete analysis for one dataset in the config.json
def analyze_dataset(
    config: dict[str, Any],
    dataset_name: str | None = None,
    base_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Run the configured analysis for one dataset and save outputs."""
    dataset_name, dataset = get_dataset_config(config, dataset_name)
    #validate before spending time processing
    issues = validate_dataset_config(dataset)
    #if config problems exist show all of them at once
    if issues:
        issue_text = "\n".join(f"- {issue}" for issue in issues)
        raise ValueError(f"Please fix these config values before running:\n{issue_text}")
    #decide where relative paths should start from
    project_root = Path(base_dir or Path.cwd())
    #create the output folder for this dataset
    output_dir = project_root / config.get("output_dir", "Analysis/wind_extreme_outputs") / dataset_name
    output_dir.mkdir(parents=True, exist_ok=True)
    #read analysis settings from the config.json
    percentiles = [normalize_percentile(q) for q in config.get("percentiles", [0.98, 0.999])]
    alpha = float(config.get("alpha", 0.05))
    n_boot = int(config.get("bootstrap_iterations", 1000))
    block_size = config.get("block_bootstrap_timesteps")
    block_size = int(block_size) if block_size else None
    #decide whether to run slow grid-cell signifcance mapping (off by default in config.json)
    make_grid_significance_maps = bool(config.get("make_grid_significance_maps", False))
    #pull dimension/coordinate names form the dataset
    time_dim = dataset["time_dim"]
    lat_name = dataset.get("lat_name")
    lon_name = dataset.get("lon_name")
    #load historical data
    historical = load_period_dataarray(dataset["historical"], dataset, base_dir=project_root)
    #convert historical gird data into a regional timeseries for statistics
    historical_stats_values = _values_for_stats(historical, time_dim=time_dim, lat_name=lat_name)
    #compute historical percentile fields
    historical_fields = {q: percentile_field(historical, q, time_dim=time_dim) for q in percentiles}
    #store summary tables here
    rows: list[dict[str, Any]] = []
    #loop throughe every future scenario/period in the config
    for future_period in dataset["futures"]:
        #load this future periods data
        future = load_period_dataarray(future_period, dataset, base_dir=project_root)
        #convert girdded data into regional time series for stats
        future_values = _values_for_stats(future, time_dim=time_dim, lat_name=lat_name)
        period_name = _period_id(future_period) # give it a anem
#save a hsitogram comparing historical and future distributions
        plot_histogram_comparison(
            historical_stats_values,
            future_values,
            output_dir / f"{period_name}_distribution_histogram.png",
            title=f"{dataset_name} distribution: historical vs {period_name}",
            percentile_lines=percentiles,
            units=historical.attrs.get("units", dataset_name),
        )
    #loop througheach requestion percentile
        for q in percentiles:
            #for each one create a label for filenames and titles
            label = percentile_label(q)
            future_field = percentile_field(future, q, time_dim=time_dim) #compute future
            changes = change_fields(historical_fields[q], future_field) #calculate abs and % change form hsitorical to future
    #define output paths for the map images
            abs_path = output_dir / f"{period_name}_{label}_absolute_change_map.png"
            pct_path = output_dir / f"{period_name}_{label}_percent_change_map.png"
#default to no significance ouput unless grid-cell maos are enabled
            significance = None
            sig_mask = None
            #optionally run bootstrab significance testing at every cell
            if make_grid_significance_maps:
                significance = gridcell_bootstrap_significance(
                    historical,
                    future,
                    percentile=q,
                    time_dim=time_dim,
                    n_boot=n_boot,
                    alpha=alpha,
                    block_size=block_size,
                )
                #extract raw p vaues from grid-cell significance results
                p_values = significance.sel(stat="p_value").load()
                #correct p-values
                fdr_reject, fdr_adjusted = benjamini_hochberg(p_values.values, alpha=alpha)
                #store T/F significance mask
                sig_mask = p_values.copy(data=fdr_reject)
                sig_mask.name = "fdr_significant"
                #store the corrected p values
                adjusted_p = p_values.copy(data=fdr_adjusted)
                adjusted_p.name = "fdr_adjusted_p_value"
#save all grid -cell significance results to  netcdf file
                significance_dataset = significance.to_dataset(dim="stat")
                significance_dataset["fdr_significant"] = sig_mask
                significance_dataset["fdr_adjusted_p_value"] = adjusted_p
                significance_dataset.to_netcdf(output_dir / f"{period_name}_{label}_gridcell_significance.nc")
#save the absolute change map, sig dots optional
            plot_spatial_change(
                changes["absolute"].load(),
                abs_path,
                title=f"{dataset_name} {label} absolute change: {period_name} minus historical",
                units=historical.attrs.get("units", ""),
                lat_name=lat_name,
                lon_name=lon_name,
                significance_mask=sig_mask,
            )
            #save the % change map sig dots optional
            plot_spatial_change(
                changes["percent"].load(),
                pct_path,
                title=f"{dataset_name} {label} percent change: {period_name} vs historical",
                units="percent",
                lat_name=lat_name,
                lon_name=lon_name,
                significance_mask=sig_mask,
            )
#run a regional bootstreap test comparing historical v future
            bootstrap = bootstrap_percentile_difference(
                historical_stats_values,
                future_values,
                percentile=q,
                n_boot=n_boot,
                alpha=alpha,
                block_size=block_size,
            )
#add a summary table row with all the results
            rows.append(
                {
                    "dataset": dataset_name,
                    "scenario": future_period.get("scenario"),
                    "period": future_period.get("period"),
                    "midyear": period_midyear(future_period),
                    "percentile": q,
                    "historical_percentile": bootstrap.historical_percentile,
                    "future_percentile": bootstrap.future_percentile,
                    "absolute_change": bootstrap.absolute_change,
                    "percent_change": bootstrap.percent_change,
                    "absolute_ci_low": bootstrap.absolute_ci_low,
                    "absolute_ci_high": bootstrap.absolute_ci_high,
                    "percent_ci_low": bootstrap.percent_ci_low,
                    "percent_ci_high": bootstrap.percent_ci_high,
                    "bootstrap_p_value": bootstrap.p_value,
                    "bootstrap_significant": bootstrap.significant,
                    "mann_whitney_p_value": mann_whitney_pvalue(historical_stats_values, future_values),
                    "ks_p_value": ks_pvalue(historical_stats_values, future_values),
                    "absolute_map": str(abs_path),
                    "percent_map": str(pct_path),
                }
            )
#close the period before moving to the next one
        future.close()
#convert all collected rows into a pandas dataframe
    summary = pd.DataFrame(rows)
    summary_path = output_dir / "summary_statistics.csv"
    summary.to_csv(summary_path, index=False) #save as a csv file
#for each percentile save scenrio specific trendplots from the summary table
    for q in percentiles:
        label = percentile_label(q)
        #plot abs cahnge
        plot_scenario_trends(
            summary,
            output_dir / f"{label}_absolute_change_trends.png",
            percentile=q,
            metric="absolute_change",
            title=f"{dataset_name} {label} absolute-change trends",
        )
        #plot percent change
        plot_scenario_trends(
            summary,
            output_dir / f"{label}_percent_change_trends.png",
            percentile=q,
            metric="percent_change",
            title=f"{dataset_name} {label} percent-change trends",
        )
#close historical dataset once all comparisons are finished
    historical.close()
    return summary

#builds CLI for this script, AI code that i dont quite understand
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MCAP wind extreme percentile analysis.")
    parser.add_argument("--config", default="configs/wind_extremes.example.json", help="Path to JSON config.")
    parser.add_argument("--dataset", default=None, help="Dataset name inside the config.")
    parser.add_argument("--base-dir", default=".", help="Project root for relative config paths.")
    return parser

#main entry point when running this workflow from the command line
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    summary = analyze_dataset(config, dataset_name=args.dataset, base_dir=args.base_dir)
    print(summary)
    return 0 #retunr 0 to mean command finished successfully

#only run main automatically when this file is executed dirrectly
if __name__ == "__main__":
    raise SystemExit(main())
