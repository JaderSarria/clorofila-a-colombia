#!/bin/bash
B=https://raw.githubusercontent.com/acolite/acolite_luts/main
D=~/acolite_py_linux/data/LUT
start=$(date +%s)
for s in S2A_MSI S2B_MSI; do
  for f in ACOLITE-LUT-202110/$s/ACOLITE-LUT-202110-MOD{1,2}-{0500,0750,1013,1100}mb_$s.nc RSKY-202102/$s/ACOLITE-RSKY-202102-82W-MOD{1,2}_$s.nc; do
    [ -s "$D/$f" ] && continue
    now=$(date +%s); [ $((now-start)) -gt 30 ] && { echo "pausa"; exit 0; }
    mkdir -p "$D/$(dirname $f)"; curl -sL --max-time 12 -o "$D/$f.part" "$B/$f" && mv "$D/$f.part" "$D/$f" && echo "ok $f"
  done
done
echo TODO_LISTO
