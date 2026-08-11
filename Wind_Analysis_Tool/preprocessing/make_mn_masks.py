from pathlib import Path

import geopandas as gpd
import regionmask
import xarray as xr

# Your project receives all new mask files.
TOOL_ROOT = Path("/projects/standard/hroop/shared/saign009/wind_program/Wind_Analysis_Tool")

# Colleague data is read only.
SOURCE_DIR = Path("/scratch.global/liess/LCCMR2/historical_1995-2014")

# The Census state boundary downloaded during the first mask build.
STATE_SHAPEFILE = Path.home() / "mn_mask_build/census_states/cb_2024_us_state_20m.shp"

MODELS = [
    "BCC-CSM2-MR",
    "CESM2",
    "CMCC-ESM2",
    "CNRM-ESM2-1",
    "IPSL-CM6A-LR",
    "MIROC-ES2L",
]

if not STATE_SHAPEFILE.is_file():
    raise FileNotFoundError(f"State boundary file not found: {STATE_SHAPEFILE}")

states = gpd.read_file(STATE_SHAPEFILE)
minnesota = states.loc[states["STUSPS"] == "MN"]

for model in MODELS:
    source = (
        SOURCE_DIR
        / f"WSPD10_{model}_historical_1995-2014_chname_U10_"
          "WSPD10-sqrt-add-sqr-selname_U10.nc"
    )
    output = TOOL_ROOT / f"mn_mask_{model}.nc"

    if output.exists():
        print(f"SKIP existing mask: {output.name}")
        continue

    if not source.is_file():
        print(f"SKIP missing source: {source}")
        continue

    # Open only the file metadata and coordinate arrays, not all wind data.
    with xr.open_dataset(source) as ds:
        mask_3d = regionmask.mask_3D_geopandas(
            minnesota,
            ds["lon"],
            ds["lat"],
            wrap_lon=180,
        )

        # 1 means inside Minnesota; 0 means outside.
        mask = mask_3d.any("region").astype("int8").rename("mn_mask")
        mask.attrs["long_name"] = "Minnesota grid-cell mask; 1=inside, 0=outside"

        inside_cells = int(mask.sum().item())
        missing_cells = int(mask.isnull().sum().item())

        if inside_cells == 0 or missing_cells != 0:
            raise RuntimeError(
                f"Invalid {model} mask: inside={inside_cells}, missing={missing_cells}"
            )

        mask.to_dataset().to_netcdf(output)

    print(
        f"CREATED {output.name}: "
        f"grid_cells={mask.size}, minnesota_cells={inside_cells}"
    )

