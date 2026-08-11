"""Config loading and validation helpers."""
#general flow: read JSON config file-> choose the requested dataset-> check that required fields exist-> catch placeholder values before analysis starts
    #->normalize percentile inputs-> create clean percentile labels for filenames-> resolve relative file paths into real paths
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#used to detect placeholder values that still need to be replaced in the config.json
PLACEHOLDER = "PLACEHOLDER"

#check is config value is still a placeholder instead of a real value
def is_placeholder(value: Any) -> bool:
    """Return True when a config value still needs user input."""
    return isinstance(value, str) and PLACEHOLDER in value

#make a python directory
def load_config(path: str | Path) -> dict[str, Any]:
    """Load the JSON config file."""
    #conert input path into a Path object
    config_path = Path(path)
    #open config file in read mode
    with config_path.open("r", encoding="utf-8") as handle:
        #go through the JSON and return results as dictionaries/lits/strings/numbers
        return json.load(handle)

#get one dataset section from the full config
def get_dataset_config(config: dict[str, Any], dataset_name: str | None = None) -> tuple[str, dict[str, Any]]:
    """Return a dataset config by name, or the first one when no name is given."""
    datasets = config.get("datasets", {})
    #complain if no defined datasets in config
    if not datasets:
        raise ValueError("Config does not contain any datasets.")
    #default to first dataset in config if not specified otherwise
    if dataset_name is None:
        dataset_name = next(iter(datasets))
    #stop if requested datset is not present and hint/complain
    if dataset_name not in datasets:
        available = ", ".join(datasets)
        raise KeyError(f"Dataset {dataset_name!r} was not found. Available datasets: {available}")
    #return name and dictionary
    return dataset_name, datasets[dataset_name]

#check a datset config and collect all the problems found
#jsut a huge defensive code and helpful complainer
def validate_dataset_config(dataset: dict[str, Any], require_paths: bool = True) -> list[str]:
    """Return human-readable config issues instead of failing at the first one."""
    #start with empty list of issue messages
    issues: list[str] = []
    #establish what keys are required
    required_keys = ["variable", "time_dim", "lat_name", "lon_name", "historical", "futures"]
    #'dont leave the house with checking for your keys' (makes sure required keys are there)
    for key in required_keys:
        if key not in dataset:
            issues.append(f"Missing required dataset key: {key}")
    #make sure key is not placeholder
    for key in ["variable", "time_dim", "lat_name", "lon_name"]:
        if is_placeholder(dataset.get(key)):
            issues.append(f"Replace dataset {key!r}: {dataset.get(key)!r}")
    #get hsitorical period config
    historical = dataset.get("historical", {})
    #check the file path for placeholder value 
    if require_paths and is_placeholder(historical.get("path")):
        issues.append(f"Replace historical path: {historical.get('path')!r}")
    #make sure futures is a non empty list
    if not isinstance(dataset.get("futures"), list) or not dataset.get("futures"):
        issues.append("Add at least one future scenario period.")
    #loop through every scenario
    for idx, period in enumerate(dataset.get("futures", [])):
        #each scenrio needs a name, period, and file path
        for key in ["scenario", "period", "path"]:
            if key not in period: #report missing keys 
                issues.append(f"Future period {idx} is missing {key!r}.")
            elif require_paths and is_placeholder(period.get(key)): #report placeholder values
                issues.append(f"Replace future period {idx} {key!r}: {period.get(key)!r}")
    #return a list of issues with hints
    return issues

#convert percentile input to 0-1 format
def normalize_percentile(percentile: float) -> float:
    """Accept either 0.98 or 98 and return the xarray/numpy quantile form."""
    q = float(percentile)
    if q > 1.0:
        q = q / 100.0
    if not 0.0 < q < 1.0:
        raise ValueError(f"Percentile must be between 0 and 1, or 0 and 100. Got {percentile!r}.")
    return q

#create filename-friendly label for percentiles
def percentile_label(percentile: float) -> str:
    """Return a compact label like p98 or p99_9."""
    pct = normalize_percentile(percentile) * 100.0
    label = f"p{pct:g}".replace(".", "_")
    return label

#conver config path to a useable full Path
def resolve_path(path: str | Path, base_dir: str | Path | None = None) -> Path:
    """Resolve config paths relative to the project directory."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if base_dir is None:
        base_dir = Path.cwd()
    return Path(base_dir) / candidate

