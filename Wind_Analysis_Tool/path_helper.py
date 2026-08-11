import json
from copy import deepcopy

seasons = ["DJF", "MAM", "JJA", "SON"]
scenarios = ["ssp245", "ssp370", "ssp585"]
periods = ["2040-2059", "2060-2079", "2080-2099"]

template = deepcopy(dataset)

seasonal_datasets = {}

for season in seasons:
    seasonal = deepcopy(template)
    seasonal["description"] = f"10 m wind speed magnitude, Minnesota masked, {season} only."
    seasonal["historical"]["path"] = (
        f"Wind_Analysis_Tool/Analysis/historical_1995-2014/seasons/"
        f"WSPD10_BCC-CSM2-MR_historical_1995-2014_MNmasked_{season}.nc"
    )

    seasonal["futures"] = []
    for scenario in scenarios:
        for period in periods:
            seasonal["futures"].append({
                "scenario": scenario,
                "period": period,
                "path": (
                    f"Wind_Analysis_Tool/Analysis/{scenario}_{period}/seasons/"
                    f"WSPD10_BCC-CSM2-MR_{scenario}_{period}_MNmasked_{season}.nc"
                ),
                "years": [int(period[:4]), int(period[-4:])]
            })

    seasonal_datasets[f"WSPD10_{season}"] = seasonal

print(json.dumps(seasonal_datasets, indent=2))