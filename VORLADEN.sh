#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
bash ./ensure-runtime.sh
chmod u+x runtime/bin/python3.12
unset PYTHONHOME PYTHONPATH PYTHONUSERBASE
exec runtime/bin/python3.12 preload.py "$@"
