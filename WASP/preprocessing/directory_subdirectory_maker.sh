BASE=/scratch.global/saign009

MODELS=(BCC-CSM2-MR CMCC-ESM2 CESM2 CNRM-ESM2-1 IPSL-CMA6-LR MIROC-ES2L)
SCENARIOS=(historical ssp245 ssp370 ssp585)

for MODEL in "${MODELS[@]}"; do
  for SCENARIO in "${SCENARIOS[@]}"; do
    mkdir -p "$BASE/$MODEL/$SCENARIO"
  done
done
