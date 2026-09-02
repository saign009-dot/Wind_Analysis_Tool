#!/usr/bin/env bash
#SBATCH -p b3csbr2
#SBATCH --job-name=monthly-percentiles
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --array=0-119%12
#SBATCH --chdir=/projects/standard/hroop/shared/saign009/WSPD10_wind_program/Wind_Analysis_Tool/WASP
#SBATCH --output=logs/monthly-percentiles-%A_%a.out
#SBATCH --error=logs/monthly-percentiles-%A_%a.err
#SBATCH --mail-user=saign009@umn.edu
#SBATCH --mail-type=END,FAIL

#Calculate model-specific p98 and p99.9 fields for one run/month per array task.
#The six model fields are stored together; raw monthly time series stay untouched.
set -euo pipefail

MODE="${1:-preview}"
if [ "$MODE" != "preview" ] && [ "$MODE" != "run" ]; then
  echo "Usage: $0 [preview|run]" >&2
  exit 2
fi

PROJECT_ROOT="${PROJECT_ROOT:-/projects/standard/hroop/shared/saign009/WSPD10_wind_program}"
TOOL_ROOT="${TOOL_ROOT:-${PROJECT_ROOT}/Wind_Analysis_Tool}"
ANALYSIS_ROOT="${ANALYSIS_ROOT:-${TOOL_ROOT}/Analysis}"
INPUT_ROOT="${INPUT_ROOT:-${ANALYSIS_ROOT}}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${ANALYSIS_ROOT}/monthly_percentiles}"
WORKER="${WORKER:-${TOOL_ROOT}/WASP/monthly_percentile_ensemble_worker.py}"
SPATIAL_CHUNK_SIZE="${SPATIAL_CHUNK_SIZE:-16}"
WORKERS="${SLURM_CPUS_PER_TASK:-1}"
TASK_INDEX="${SLURM_ARRAY_TASK_ID:-${TASK_INDEX:-}}"

#Initialize the project-specific MCAP wind environment on every compute node.
#This is the same environment path used by the existing MSI validation jobs.
#Override MCAP_WIND_ENV only when the environment has been installed elsewhere.
MCAP_WIND_ENV="${MCAP_WIND_ENV:-${TOOL_ROOT}/~mcap-wind-env}"
ACTIVATE_SCRIPT="${MCAP_WIND_ENV}/bin/activate"
if [ ! -r "$ACTIVATE_SCRIPT" ]; then
  echo "ERROR: MCAP wind environment activation script not found: $ACTIVATE_SCRIPT" >&2
  echo "Set MCAP_WIND_ENV to the installed mcap-wind environment path." >&2
  exit 2
fi
source "$ACTIVATE_SCRIPT"

PYTHON_BIN="${MCAP_WIND_ENV}/bin/python"
if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  echo "ERROR: Python executable not found in the MCAP wind environment: $PYTHON_BIN" >&2
  exit 2
fi
if [ ! -f "$WORKER" ]; then
  echo "ERROR: worker not found: $WORKER" >&2
  exit 2
fi
if [ -z "$TASK_INDEX" ]; then
  echo "ERROR: no task index is set." >&2
  echo "Submit with sbatch, or set TASK_INDEX=0 through 119 for a local check." >&2
  exit 2
fi
if ! [[ "$TASK_INDEX" =~ ^[0-9]+$ ]] || [ "$TASK_INDEX" -gt 119 ]; then
  echo "ERROR: task index must be an integer from 0 through 119: $TASK_INDEX" >&2
  exit 2
fi
if ! [[ "$WORKERS" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: worker count must be a positive integer: $WORKERS" >&2
  exit 2
fi
if ! [[ "$SPATIAL_CHUNK_SIZE" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: spatial chunk size must be a positive integer: $SPATIAL_CHUNK_SIZE" >&2
  exit 2
fi

arguments=(
  --input-root "$INPUT_ROOT"
  --output-root "$OUTPUT_ROOT"
  --task-index "$TASK_INDEX"
  --workers "$WORKERS"
  --spatial-chunk-size "$SPATIAL_CHUNK_SIZE"
)

if [ "$MODE" = "preview" ]; then
  arguments+=(--preview)
else
  "$PYTHON_BIN" -c 'import dask, netCDF4, numpy, xarray; print("Scientific Python imports passed")'
fi
if [ "${OVERWRITE:-0}" = "1" ]; then
  arguments+=(--overwrite)
fi

export OMP_NUM_THREADS=1
echo "Started: $(date --iso-8601=seconds)"
echo "Mode: $MODE"
echo "Task index: $TASK_INDEX"
echo "Input root: $INPUT_ROOT"
echo "Output root: $OUTPUT_ROOT"
echo "Worker: $WORKER"
echo "MCAP wind environment: $MCAP_WIND_ENV"
echo "Python: $PYTHON_BIN"

"$PYTHON_BIN" -u "$WORKER" "${arguments[@]}"

echo "Finished: $(date --iso-8601=seconds)"
