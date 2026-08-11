#!/usr/bin/env bash
#SBATCH -p b3csbr2
#SBATCH --job-name=p98-trends
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=logs/p98-trends-%j.out
#SBATCH --error=logs/p98-trends-%j.err
#SBATCH --mail-user=saign009@umn.edu
#SBATCH --mail-type=END,FAIL

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python)}"
TOOL_DIR="${TOOL_DIR:-${SLURM_SUBMIT_DIR}}"
WORKER="${WORKER:-${TOOL_DIR}/percentile_ensemble_trends.py}"
INPUT_ROOT="${INPUT_ROOT:-${TOOL_DIR}/outputs/p98_model_changes_final}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${TOOL_DIR}/outputs/p98_ensemble_trends}"

if [ ! -f "${WORKER}" ]; then
    echo "ERROR: trend program not found: ${WORKER}" >&2
    exit 2
fi
if [ ! -d "${INPUT_ROOT}" ]; then
    echo "ERROR: model-result directory not found: ${INPUT_ROOT}" >&2
    exit 2
fi
if [ -z "${PYTHON_BIN}" ] || [ ! -x "${PYTHON_BIN}" ]; then
    echo "ERROR: Python executable not found: ${PYTHON_BIN}" >&2
    exit 2
fi

mkdir -p "${OUTPUT_ROOT}" "${TOOL_DIR}/logs"
export OMP_NUM_THREADS=1

echo "Started: $(date --iso-8601=seconds)"
echo "Python: ${PYTHON_BIN}"
echo "Input root: ${INPUT_ROOT}"
"${PYTHON_BIN}" -c 'import matplotlib, numpy, pandas, xarray, netCDF4; print("Scientific Python imports passed")'

"${PYTHON_BIN}" -u "${WORKER}" \
    --input-root "${INPUT_ROOT}" \
    --output-root "${OUTPUT_ROOT}"

echo "Finished: $(date --iso-8601=seconds)"
