#!/usr/bin/env bash
#SBATCH -p b3csbr2
#SBATCH --job-name=p99_9-trends
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=logs/p99_9-trends-%j.out
#SBATCH --error=logs/p99_9-trends-%j.err
#SBATCH --mail-user=saign009@umn.edu
#SBATCH --mail-type=END,FAIL

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python)}"
TOOL_DIR="${TOOL_DIR:-${SLURM_SUBMIT_DIR}}"
WORKER="${WORKER:-${TOOL_DIR}/percentile_ensemble_trends.py}"
INPUT_ROOT="${INPUT_ROOT:-${TOOL_DIR}/outputs/p99_9_model_changes_final}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${TOOL_DIR}/outputs/p99_9_ensemble_trends}"

if [ ! -f "${WORKER}" ] || [ ! -d "${INPUT_ROOT}" ]; then
    echo "ERROR: trend program or input directory is missing" >&2
    exit 2
fi
mkdir -p "${OUTPUT_ROOT}" "${TOOL_DIR}/logs"
export OMP_NUM_THREADS=1

echo "Started: $(date --iso-8601=seconds)"
"${PYTHON_BIN}" -u "${WORKER}" \
    --input-root "${INPUT_ROOT}" \
    --output-root "${OUTPUT_ROOT}" \
    --percentile 0.999

echo "Finished: $(date --iso-8601=seconds)"
