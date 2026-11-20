#!/bin/bash
# Run any command while holding the one GPU lock. Two Blender renders at once crash the 4 GB GPU ("Shadow buffer full", exit 139).
# Usage: ./with_gpu_lock.sh "/c/Program Files/Blender Foundation/Blender 5.3/blender.exe" -b -P build_neighborhood_walk_v2.py -- still 600 50
L="$(dirname "$0")/.gpu.lock"
until mkdir "$L" 2>/dev/null; do
  find "$L" -maxdepth 0 -mmin +120 -exec rmdir {} \; 2>/dev/null   # a lock older than 2 h is stale
  sleep 5
done
trap 'rmdir "$L"' EXIT
"$@"
