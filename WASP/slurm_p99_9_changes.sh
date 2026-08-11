#!/usr/bin/env bash
#SBATCH -p b3csbr2
#SBATCH --job-name=p99_9-change
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=24G
#SBATCH --time=01:00:00
#SBATCH --array=0-215%32
#SBATCH --output=logs/p99_9-change-%A_%a.out
#SBATCH --error=logs/p99_9-change-%A_%a.err
#SBATCH --mail-user=saign009@umn.edu
#SBATCH --mail-type=END,FAIL

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python)}"
TOOL_DIR="${TOOL_DIR:-${SLURM_SUBMIT_DIR}}"
MANIFEST="${MANIFEST:-${TOOL_DIR}/manifests/ensemble_tasks.csv}"
WORKER="${WORKER:-${TOOL_DIR}/percentile_change_worker.py}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${TOOL_DIR}/outputs/p99_9_model_changes_final}"

for required_file in "${MANIFEST}" "${WORKER}"; do
    if [ ! -f "${required_file}" ]; then
        echo "ERROR: required file not found: ${required_file}" >&2
        exit 2
    fi
done
if [ -z "${PYTHON_BIN}" ] || [ ! -x "${PYTHON_BIN}" ]; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

mkdir -p "${OUTPUT_ROOT}" "${TOOL_DIR}/logs"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

echo "Started: $(date --iso-8601=seconds)"
echo "Python: ${PYTHON_BIN}"
echo "Task index: ${SLURM_ARRAY_TASK_ID}"
"${PYTHON_BIN}" -c 'import dask, numpy, xarray, netCDF4; print("Scientific Python imports passed")'

"${PYTHON_BIN}" -u "${WORKER}" \
    --manifest "${MANIFEST}" \
    --task-index "${SLURM_ARRAY_TASK_ID}" \
    --output-root "${OUTPUT_ROOT}" \
    --percentile 0.999 \
    --workers "${SLURM_CPUS_PER_TASK}" \
    --spatial-chunk-size "${SPATIAL_CHUNK_SIZE:-16}"

echo "Finished: $(date --iso-8601=seconds)"
