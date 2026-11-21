#!/bin/bash
B=https://raw.githubusercontent.com/acolite/acolite_luts/main
D=~/acolite_py_linux/data/LUT
start=$(date +%s)
for s in S2A_MSI S2B_MSI; do for m in 1 2; do for p in "romix+rsky_t" "romix"; do for b in 1 2 3 4 5 6 7 8 8A 9 10 11 12; do
  f="ACOLITE-LUT-202110-Reverse/$s/ACOLITE-LUT-202110-MOD$m-reverse-$s-$p-$b.nc"
  [ -s "$D/$f" ] && continue
  now=$(date +%s); [ $((now-start)) -gt 33 ] && { echo "pausa"; ls $D/ACOLITE-LUT-202110-Reverse/*/ | wc -l; exit 0; }
  mkdir -p "$D/$(dirname $f)"; curl -sL --max-time 10 -o "$D/$f.part" "$B/$f" && mv "$D/$f.part" "$D/$f"
done; done; done; done
echo TODO_LISTO
