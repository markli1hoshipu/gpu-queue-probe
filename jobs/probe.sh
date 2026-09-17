#!/usr/bin/env bash
set -euo pipefail

# The allocation itself is the measurement. Do no GPU computation; record a
# compact marker and release the allocation immediately.
printf '{"started_at":"%s","gpu_count":%s,"cluster":"%s","node":"%s"}\n' \
  "$(date --utc +%FT%TZ)" "${1:?gpu count required}" "${2:?cluster required}" "${SLURMD_NODENAME:-unknown}"
