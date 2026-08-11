"""Create wind-speed magnitude NetCDF files from U/V components."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .config import is_placeholder


def wind_speed_magnitude(u_values, v_values):
    """Return sqrt(u^2 + v^2) for arrays or xarray DataArrays."""
    return np.hypot(u_values, v_values)


def combine_uv_netcdf(
    u_file: str | Path,
    v_file: str | Path,
    u_var: str,
    v_var: str,
    output_file: str | Path,
    speed_var: str = "WSPD10",
    chunks: dict[str, int] | None = None,
):
    """Combine U and V component NetCDF files into a wind-speed magnitude file."""
    if is_placeholder(u_var) or is_placeholder(v_var):
        raise ValueError("Replace PLACEHOLDER_U_VAR and PLACEHOLDER_V_VAR with real NetCDF variable names.")

    import xarray as xr

    u_ds = xr.open_dataset(u_file, chunks=chunks)
    v_ds = xr.open_dataset(v_file, chunks=chunks)

    if u_var not in u_ds:
        raise KeyError(f"{u_var!r} was not found in {u_file}. Available variables: {list(u_ds.data_vars)}")
    if v_var not in v_ds:
        raise KeyError(f"{v_var!r} was not found in {v_file}. Available variables: {list(v_ds.data_vars)}")

    u_da, v_da = xr.align(u_ds[u_var], v_ds[v_var], join="exact")
    speed = xr.apply_ufunc(np.hypot, u_da, v_da, dask="parallelized")
    speed.name = speed_var
    speed.attrs.update(
        {
            "long_name": "wind speed magnitude",
            "calculation": f"sqrt({u_var}^2 + {v_var}^2)",
            "units": u_da.attrs.get("units", ""),
        }
    )

    output = speed.to_dataset()
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_netcdf(output_path)
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create wind-speed magnitude from U/V NetCDF components.")
    parser.add_argument("--u-file", required=True, help="Path to U-component NetCDF file.")
    parser.add_argument("--v-file", required=True, help="Path to V-component NetCDF file.")
    parser.add_argument("--u-var", required=True, help="U-component variable name.")
    parser.add_argument("--v-var", required=True, help="V-component variable name.")
    parser.add_argument("--out", required=True, help="Output NetCDF file path.")
    parser.add_argument("--speed-var", default="WSPD10", help="Output wind-speed variable name.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = combine_uv_netcdf(
        u_file=args.u_file,
        v_file=args.v_file,
        u_var=args.u_var,
        v_var=args.v_var,
        output_file=args.out,
        speed_var=args.speed_var,
    )
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

