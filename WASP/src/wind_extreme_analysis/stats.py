"""Statistical tests for extreme percentile changes. Differentiates meaningful vs. noisey change"""

#overall flow: clean raw values->resample with bootstrap->compare hist percentile v future precentiles->estimate CI and p-val
#->flag stat sig change->optionally run MW and KS tests->correct p-values with ben-Hoch->apply bootstrapping for each grid cell when sig maps are enabled
#allows better hint behavior
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import normalize_percentile

#stores the resut of one bootstrap percentile comparison
#frozen means values cannot be changed after the object is created
@dataclass(frozen=True)
class BootstrapResult:
    percentile: float
    historical_percentile: float
    future_percentile: float
    absolute_change: float
    percent_change: float
    absolute_ci_low: float
    absolute_ci_high: float
    percent_ci_low: float
    percent_ci_high: float
    p_value: float
    significant: bool
    n_historical: int
    n_future: int


def clean_1d(values) -> np.ndarray:
    """Return a finite 1D float array."""
    array = np.asarray(values, dtype=float).ravel() #convert values and flatten into a vector
    return array[np.isfinite(array)] #return only finite values

#resample values for bootstrapping
#can be random or block
def _resample(values: np.ndarray, size: int, rng: np.random.Generator, block_size: int | None) -> np.ndarray:
    #if not block size provided randomly sample individual values with replacement
    if block_size is None or block_size <= 1:
        return rng.choice(values, size=size, replace=True)
    #make sure block size is an integer
    block_size = int(block_size)
    #if the block size is as long as the whle dataset fall back to normal resampling
    if block_size >= len(values):
        return rng.choice(values, size=size, replace=True)
    #randomly choose starting positions for blocks
    starts = rng.integers(0, len(values), size=int(np.ceil(size / block_size)))
    pieces = [] #store each sampled block here before comibinging them
    #build each block of consecutive values
    for start in starts:
        indices = (np.arange(start, start + block_size) % len(values)).astype(int)
        pieces.append(values[indices])
    return np.concatenate(pieces)[:size] #return all blocks and trim the result to the requested sample size

#compares historical sample and future sample using bootstrap resampling
def bootstrap_percentile_difference(
    historical,
    future,
    percentile: float,
    n_boot: int = 1000,
    alpha: float = 0.05,
    block_size: int | None = None,
    random_seed: int | None = 42,
    min_samples: int = 20,
) -> BootstrapResult:
    """Bootstrap the change in a percentile between historical and future samples.

    The confidence interval is the main significance test: if the interval does
    not cross zero, the change is considered significant at the requested alpha.
    """
    hist = clean_1d(historical)
    fut = clean_1d(future)
    q = normalize_percentile(percentile)
    #if either sample is too small(min defined in the function) return nan instead of passing 
    if len(hist) < min_samples or len(fut) < min_samples:
        nan = float("nan")
        return BootstrapResult(q, nan, nan, nan, nan, nan, nan, nan, nan, nan, False, len(hist), len(fut))
    #calculate percentile values and change
    hist_q = float(np.nanquantile(hist, q))
    fut_q = float(np.nanquantile(fut, q))
    absolute_change = fut_q - hist_q
    percent_change = absolute_change / hist_q * 100.0 if hist_q != 0 else float("nan")
    #random number generator used for reproducable bootstrap samples
    rng = np.random.default_rng(random_seed)
    #allocate arrays to store bootstrap results
    absolute_samples = np.empty(int(n_boot), dtype=float)
    percent_samples = np.empty(int(n_boot), dtype=float)
    #repreat the process n_boot times and n_boot is defined in the function
    for idx in range(int(n_boot)):
        hist_sample = _resample(hist, len(hist), rng, block_size) #these two resample
        fut_sample = _resample(fut, len(fut), rng, block_size)
        sample_hist_q = float(np.nanquantile(hist_sample, q)) #these two calculate percentiles within resampled set
        sample_fut_q = float(np.nanquantile(fut_sample, q))
        sample_diff = sample_fut_q - sample_hist_q #store the resampled difference 
        absolute_samples[idx] = sample_diff
        percent_samples[idx] = sample_diff / sample_hist_q * 100.0 if sample_hist_q != 0 else np.nan
    #compute the confidence interval bounds for % change
    lo, hi = np.nanquantile(absolute_samples, [alpha / 2.0, 1.0 - alpha / 2.0])
    pct_lo, pct_hi = np.nanquantile(percent_samples, [alpha / 2.0, 1.0 - alpha / 2.0])
    #estimate a two-sided p-value from how often the bootstrap differences fall on each side of zero
    below_or_equal_zero = float(np.mean(absolute_samples <= 0.0))
    above_or_equal_zero = float(np.mean(absolute_samples >= 0.0))
    p_value = min(1.0, 2.0 * min(below_or_equal_zero, above_or_equal_zero))
    significant = bool(lo > 0.0 or hi < 0.0) #signioficant is CI does not cross 0
    #return all bootstrap results into one structured object
    return BootstrapResult(
        percentile=q,
        historical_percentile=hist_q,
        future_percentile=fut_q,
        absolute_change=absolute_change,
        percent_change=percent_change,
        absolute_ci_low=float(lo),
        absolute_ci_high=float(hi),
        percent_ci_low=float(pct_lo),
        percent_ci_high=float(pct_hi),
        p_value=float(p_value),
        significant=significant,
        n_historical=len(hist),
        n_future=len(fut),
    )

# test for a difference in location between distributions
def mann_whitney_pvalue(historical, future) -> float:
    """Return a Mann-Whitney U p-value, or NaN if scipy is unavailable."""
    try:
        from scipy.stats import mannwhitneyu
    except ImportError:
        return float("nan")

    hist = clean_1d(historical)
    fut = clean_1d(future)
    if len(hist) == 0 or len(fut) == 0:
        return float("nan")
    return float(mannwhitneyu(hist, fut, alternative="two-sided").pvalue)

#compares underlining continuous ditributions between f(x) and g(x); a goodness of fit test
def ks_pvalue(historical, future) -> float:
    """Return a Kolmogorov-Smirnov p-value, or NaN if scipy is unavailable."""
    try:
        from scipy.stats import ks_2samp
    except ImportError:
        return float("nan")

    hist = clean_1d(historical)
    fut = clean_1d(future)
    if len(hist) == 0 or len(fut) == 0:
        return float("nan")
    return float(ks_2samp(hist, fut, alternative="two-sided").pvalue)

#a method that allosw correction of many p-values at once
def benjamini_hochberg(p_values, alpha: float = 0.05) -> tuple[np.ndarray, np.ndarray]:
    """False discovery rate correction for a collection of p-values."""
    p = np.asarray(p_values, dtype=float) #cnvert values to array
    adjusted = np.full(p.shape, np.nan, dtype=float) #create output arrays matching the shape of the input
    reject = np.zeros(p.shape, dtype=bool)
    #only work with finite values
    finite_mask = np.isfinite(p)
    finite_p = p[finite_mask]
    n = finite_p.size
    #if no valid p-values return empty outputs
    if n == 0:
        return reject, adjusted
    #sort values from smallest to largest
    order = np.argsort(finite_p)
    sorted_p = finite_p[order]
    ranks = np.arange(1, n + 1, dtype=float)
    #calculate Ben-Hoch threshold for each ranked p value 
    thresholds = alpha * ranks / n
    #identify which sorted p-values pass their thresheholds
    passed = sorted_p <= thresholds
    #if any p-values pass mark all p-values up through the largest passing rank as significant
    if np.any(passed):
        max_idx = int(np.max(np.where(passed)))
        reject_sorted = np.zeros(n, dtype=bool)
        reject_sorted[: max_idx + 1] = True
        reject_finite = np.zeros(n, dtype=bool)
        reject_finite[order] = reject_sorted
        reject[finite_mask] = reject_finite
    #calculate adjusted p-values
    adjusted_sorted = sorted_p * n / ranks
    #makes sure a more significant raw p values does not become less significant after adjustment and vice cersa
    adjusted_sorted = np.minimum.accumulate(adjusted_sorted[::-1])[::-1]
    adjusted_sorted = np.clip(adjusted_sorted, 0.0, 1.0) #makes sure adjusted values stay between zero and 1
    #move adjusted values back into origional shape
    adjusted_finite = np.empty(n, dtype=float)
    adjusted_finite[order] = adjusted_sorted
    adjusted[finite_mask] = adjusted_finite
    #return both the t and false significance mask and the adjusted p values
    return reject, adjusted

#runs bootstrap significance for all cells
def gridcell_bootstrap_significance(
    historical_da,
    future_da,
    percentile: float,
    time_dim: str,
    n_boot: int = 500,
    alpha: float = 0.05,
    block_size: int | None = None,
    random_seed: int | None = 42,
):
    """Apply bootstrap percentile significance testing independently at each grid cell."""
    import xarray as xr
    
    q = normalize_percentile(percentile)
    #runts bootstrap test for one grid cell
    def _cell_stats(hist_values, fut_values): #compare historical and predicted time series for one cell
        result = bootstrap_percentile_difference(
            hist_values,
            fut_values,
            percentile=q,
            n_boot=n_boot,
            alpha=alpha,
            block_size=block_size,
            random_seed=random_seed,
        )
        #return the result values as a numeric array
        return np.array(
            [
                result.absolute_change,
                result.percent_change,
                result.absolute_ci_low,
                result.absolute_ci_high,
                result.p_value,
                float(result.significant),
            ],
            dtype=float,
        )
    #apply the function across the whole grid
    output = xr.apply_ufunc(
        _cell_stats,
        historical_da,
        future_da,
        input_core_dims=[[time_dim], [time_dim]],
        output_core_dims=[["stat"]],
        vectorize=True,
        dask="parallelized",
        output_dtypes=[float],
        dask_gufunc_kwargs={"output_sizes": {"stat": 6}},
    )
    ##lable the output statistics so they can be selected by name
    output = output.assign_coords(stat=["absolute_change", "percent_change", "ci_low", "ci_high", "p_value", "significant"])
    return output

