#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -c 'import sys; assert sys.version_info >= (3, 9), "Python 3.9+ is required"'
install -d "$repo_root/var/data" "$repo_root/var/logs"
if [[ ! -f "$repo_root/config/local.json" ]]; then
  cp "$repo_root/config/example.json" "$repo_root/config/local.json"
fi
printf 'Installed. Edit %s/config/local.json before starting.\n' "$repo_root"
