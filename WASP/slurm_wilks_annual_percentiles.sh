#!/usr/bin/env bash
#SBATCH -p b3csbr2
#SBATCH --job-name=wilks-annual
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --array=0-215%32
#SBATCH --output=logs/wilks-annual-%A_%a.out
#SBATCH --error=logs/wilks-annual-%A_%a.err
#SBATCH --mail-user=saign009@umn.edu
#SBATCH --mail-type=END,FAIL

#stop on an error, an unset variable, or a failed command inside a pipeline
set -euo pipefail

#allow MSI users to override paths at submission while keeping repository defaults
PYTHON_BIN="${PYTHON_BIN:-$(command -v python)}"
TOOL_DIR="${TOOL_DIR:-${SLURM_SUBMIT_DIR}}"
MANIFEST="${MANIFEST:-${TOOL_DIR}/manifests/ensemble_tasks.csv}"
WORKER="${WORKER:-${TOOL_DIR}/wilks_annual_percentile_worker.py}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${TOOL_DIR}/outputs/wilks_annual_percentiles}"

#fail before allocating calculation memory if a required tracked/generated file is absent
for required_file in "${MANIFEST}" "${WORKER}"; do
    if [ ! -f "${required_file}" ]; then
        echo "ERROR: required file not found: ${required_file}" >&2
        exit 2
    fi
done

#the selected environment must contain xarray, Dask, NetCDF, NumPy, and pandas
if [ -z "${PYTHON_BIN}" ] || [ ! -x "${PYTHON_BIN}" ]; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

#create only generated runtime folders; neither directory is tracked by Git
mkdir -p "${OUTPUT_ROOT}" "${TOOL_DIR}/logs"
#Dask controls task-level threading, so BLAS/OpenMP should not create nested workers
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

#record enough environment information to reproduce or diagnose each array task
echo "Started: $(date --iso-8601=seconds)"
echo "Host: $(hostname)"
echo "Python: ${PYTHON_BIN}"
echo "Manifest: ${MANIFEST}"
echo "Task index: ${SLURM_ARRAY_TASK_ID}"
"${PYTHON_BIN}" --version
"${PYTHON_BIN}" -c 'import dask, numpy, xarray, netCDF4; print("Scientific Python imports passed")'

#one task reads one model/scenario/period/season pair and produces both percentiles
"${PYTHON_BIN}" -u "${WORKER}" \
    --manifest "${MANIFEST}" \
    --task-index "${SLURM_ARRAY_TASK_ID}" \
    --output-root "${OUTPUT_ROOT}" \
    --workers "${SLURM_CPUS_PER_TASK}" \
    --spatial-chunk-size "${SPATIAL_CHUNK_SIZE:-16}"

echo "Finished: $(date --iso-8601=seconds)"
