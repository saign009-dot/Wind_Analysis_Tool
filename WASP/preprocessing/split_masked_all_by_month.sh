#!/usr/bin/env bash

#Stop on command failures, unset variables, or failed pipeline components.
set -euo pipefail

#Split already-masked WASP NetCDF files into one multi-year file per month.
#The default mode is a non-writing preview; pass "run" to create the files.
MODE="${1:-preview}"

#These defaults follow the current MSI repository layout. Every path can be
#overridden as an environment variable when the data are staged elsewhere.
PROJECT_ROOT="${PROJECT_ROOT:-/projects/standard/hroop/shared/saign009/WSPD10_wind_program}"
TOOL_ROOT="${TOOL_ROOT:-${PROJECT_ROOT}/Wind_Analysis_Tool/WASP}"
ANALYSIS_ROOT="${ANALYSIS_ROOT:-${TOOL_ROOT}/Analysis}"

#Use the complete six-model ensemble and the same run definitions as the
#seasonal analysis. Model names in output files prevent collisions in a shared run folder.
MODELS=(BCC-CSM2-MR CESM2 CMCC-ESM2 CNRM-ESM2-1 IPSL-CM6A-LR MIROC-ES2L)
SCENARIOS=(ssp245 ssp370 ssp585)
PERIODS=(2040-2059 2060-2079 2080-2099)
MONTHS=(01 02 03 04 05 06 07 08 09 10 11 12)

#Map each calendar month to the seasonal file that contains it when a complete
#already-masked period file is unavailable. December remains in DJF; selmon
#selects by calendar month and therefore does not alter any time coordinate.
season_for_month() {
  local month="$1"
  case "$month" in
    12|01|02) echo "DJF" ;;
    03|04|05) echo "MAM" ;;
    06|07|08) echo "JJA" ;;
    09|10|11) echo "SON" ;;
    *)
      echo "ERROR: unsupported month: $month" >&2
      return 1
      ;;
  esac
}

#Find either supported analysis layout. The preferred layout is MODEL/RUN,
#while the older masking script placed all model files together under RUN.
find_run_directory() {
  local model="$1"
  local run="$2"
  local candidate
  local full_name="WSPD10_${model}_${run}_MNmasked.nc"
  local djf_name="WSPD10_${model}_${run}_MNmasked_DJF.nc"

  for candidate in \
    "${ANALYSIS_ROOT}/${model}/${run}" \
    "${ANALYSIS_ROOT}/${run}"
  do
    if [ -f "${candidate}/${full_name}" ] \
      || [ -f "${candidate}/seasons/${djf_name}" ] \
      || [ -f "${candidate}/${djf_name}" ]; then
      echo "$candidate"
      return 0
    fi
  done

  echo "ERROR: no masked input layout found for ${model} ${run}" >&2
  echo "CHECKED: ${ANALYSIS_ROOT}/${model}/${run}" >&2
  echo "CHECKED: ${ANALYSIS_ROOT}/${run}" >&2
  return 1
}

#Prefer one complete already-masked period file. If only seasonal files exist,
#return the file containing the requested calendar month.
find_month_source() {
  local run_directory="$1"
  local model="$2"
  local run="$3"
  local month="$4"
  local full_source="${run_directory}/WSPD10_${model}_${run}_MNmasked.nc"
  local season
  local seasonal_name

  if [ -f "$full_source" ]; then
    echo "$full_source"
    return 0
  fi

  season="$(season_for_month "$month")" || return 1
  seasonal_name="WSPD10_${model}_${run}_MNmasked_${season}.nc"
  if [ -f "${run_directory}/seasons/${seasonal_name}" ]; then
    echo "${run_directory}/seasons/${seasonal_name}"
    return 0
  fi
  if [ -f "${run_directory}/${seasonal_name}" ]; then
    echo "${run_directory}/${seasonal_name}"
    return 0
  fi

  echo "ERROR: missing ${season} source for ${model} ${run} month ${month}" >&2
  return 1
}

#Process one model/run pair. Each output contains all timesteps from the selected
#calendar month across the full historical or future period.
process_run() {
  local model="$1"
  local run="$2"
  local run_directory
  local month_directory
  local month
  local source
  local output
  local temporary_output

  run_directory="$(find_run_directory "$model" "$run")" || return 1
  #Place months beside seasons: RUN/seasons/ and RUN/months/ are sibling folders.
  month_directory="${run_directory}/months"

  for month in "${MONTHS[@]}"; do
    source="$(find_month_source "$run_directory" "$model" "$run" "$month")" \
      || return 1
    output="${month_directory}/WSPD10_${model}_${run}_MNmasked_${month}.nc"

    #Existing outputs are preserved by default. Set OVERWRITE=1 only after
    #reviewing the exact paths printed by preview mode.
    if [ -f "$output" ] && [ "${OVERWRITE:-0}" != "1" ]; then
      echo "SKIP existing: $output"
      continue
    fi

    if [ "$MODE" != "run" ]; then
      echo "WOULD SELECT MONTH ${month}: $source"
      echo "WOULD WRITE: $output"
      continue
    fi

    mkdir -p "$month_directory"
    #Write to a task-specific partial file first so an interrupted CDO process
    #cannot leave a damaged NetCDF file under the final production filename.
    temporary_output="${output}.part.$$"
    echo "WRITING MONTH ${month}: ${model} ${run}"
    if ! cdo -L -O "selmon,$((10#$month))" "$source" "$temporary_output"; then
      rm -f -- "$temporary_output"
      return 1
    fi
    mv -f -- "$temporary_output" "$output"
  done
}

#Only the two documented modes are accepted, preventing a misspelling of "run"
#from producing a misleading preview that looks like a submitted calculation.
if [ "$MODE" != "preview" ] && [ "$MODE" != "run" ]; then
  echo "Usage: $0 [preview|run]" >&2
  exit 2
fi

#CDO is unnecessary for preview mode, but it must be available before any
#production output directory or partial file is created.
if [ "$MODE" = "run" ] && ! command -v cdo >/dev/null 2>&1; then
  echo "ERROR: cdo is not available in the active environment" >&2
  exit 2
fi

failed=0
for model in "${MODELS[@]}"; do
  process_run "$model" "historical_1995-2014" || { failed=1; break; }

  for scenario in "${SCENARIOS[@]}"; do
    for period in "${PERIODS[@]}"; do
      process_run "$model" "${scenario}_${period}" || { failed=1; break 2; }
    done
  done

  [ "$failed" -eq 0 ] || break
done

if [ "$failed" -eq 0 ]; then
  if [ "$MODE" = "run" ]; then
    echo "Completed monthly splitting successfully."
  else
    echo "Preview completed; no files were written. Pass 'run' to create outputs."
  fi
else
  echo "Stopped after an error." >&2
  exit 1
fi
