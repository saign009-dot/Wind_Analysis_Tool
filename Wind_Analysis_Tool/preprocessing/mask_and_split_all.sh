#!/usr/bin/env bash

# Default is preview. Use "run" to actually write files.
MODE="${1:-preview}"

PROJECT_ROOT="/projects/standard/hroop/shared/saign009/wind_program"
TOOL_ROOT="$PROJECT_ROOT/Wind_Analysis_Tool"
MASK_DIR="$PROJECT_ROOT/masks"
SOURCE_BASE="/scratch.global/liess/LCCMR2"
ANALYSIS_DIR="$TOOL_ROOT/Analysis"

MODELS=(CESM2 CMCC-ESM2 CNRM-ESM2-1 IPSL-CM6A-LR MIROC-ES2L)
SCENARIOS=(ssp245 ssp370 ssp585)
PERIODS=(2040-2059 2060-2079 2080-2099)
SEASONS=(DJF MAM JJA SON)

all_seasons_exist() {
  local masked="$1"
  local season_dir="$(dirname "$masked")/seasons"
  local base_name="$(basename "${masked%.nc}")"
  local season

  for season in "${SEASONS[@]}"; do
    [ -f "$season_dir/${base_name}_${season}.nc" ] || return 1
  done
}

process_file() {
  local model="$1"
  local source="$2"
  local masked="$3"
  local mask="$MASK_DIR/mn_mask_${model}.nc"
  local season_dir="$(dirname "$masked")/seasons"
  local base_name="$(basename "${masked%.nc}")"
  local season

  if [ ! -f "$mask" ]; then
    echo "ERROR: missing model mask: $mask"
    return 1
  fi

  if [ ! -f "$source" ]; then
    echo "ERROR: missing source: $source"
    return 1
  fi

  if all_seasons_exist "$masked"; then
    echo "SKIP complete: $masked"
    return 0
  fi

  if [ "$MODE" != "run" ]; then
    echo "WOULD MASK: $source"
    echo "WOULD WRITE: $masked and its four seasonal files"
    return 0
  fi

  mkdir -p "$season_dir"

  echo "MASKING: $source"
  cdo -L -O ifthen "$mask" "$source" "$masked" || return 1

  for season in "${SEASONS[@]}"; do
    echo "WRITING: ${model} ${season}"
    cdo -L -O selseas,"$season" \
      "$masked" \
      "$season_dir/${base_name}_${season}.nc" || return 1
  done
}

failed=0

for model in "${MODELS[@]}"; do
  historical_source="$SOURCE_BASE/historical_1995-2014/WSPD10_${model}_historical_1995-2014_chname_U10_WSPD10-sqrt-add-sqr-selname_U10.nc"
  historical_output="$ANALYSIS_DIR/historical_1995-2014/WSPD10_${model}_historical_1995-2014_MNmasked.nc"

  process_file "$model" "$historical_source" "$historical_output" || { failed=1; break; }

  for scenario in "${SCENARIOS[@]}"; do
    for period in "${PERIODS[@]}"; do
      source="$SOURCE_BASE/${scenario}_${period}/WSPD10_${model}_${scenario}_${period}_chname_U10_WSPD10-sqrt-add-sqr-selname_U10.nc"
      output="$ANALYSIS_DIR/${scenario}_${period}/WSPD10_${model}_${scenario}_${period}_MNmasked.nc"

      process_file "$model" "$source" "$output" || { failed=1; break 2; }
    done
  done

  [ "$failed" -eq 0 ] || break
done

[ "$failed" -eq 0 ] && echo "Completed successfully." || echo "Stopped after an error."
