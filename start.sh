#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
mode="${1:---web}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ "$(uname -m)" != x86_64 ]]; then
  echo 'Die gebündelte Laufzeit benötigt Linux x86_64. Für ARM: python3 server.py verwenden.' >&2
  exit 1
fi
bash ./ensure-runtime.sh
chmod u+x runtime/bin/python3.12
unset PYTHONHOME PYTHONPATH PYTHONUSERBASE
task_data="${VITALUX_DATA:-$PWD/data}"
mkdir -p "$task_data/cache"
chmod 700 "$task_data"
export XDG_CACHE_HOME="$task_data/cache"
export LD_LIBRARY_PATH="$PWD/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [[ "$mode" == --desktop || "$mode" == --web ]]; then
  if command -v flock >/dev/null 2>&1 && [[ "${VITALUX_TEST_LOCKED:-0}" != 1 ]]; then
    export VITALUX_TEST_LOCKED=1
    exec flock --nonblock --conflict-exit-code 75 "${VITALUX_DATA:-$PWD/data}/dashboard.lock" bash ./start.sh "$mode" "$@"
  fi
fi
if [[ "$mode" == --desktop ]]; then
  if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    echo 'Kein Desktop erkannt. Auf einem headless Homeserver START-UBUNTU.sh verwenden.' >&2
    exit 1
  fi
  exec runtime/bin/python3.12 desktop.py "$@"
elif [[ "$mode" == --web ]]; then
  exec runtime/bin/python3.12 server.py "$@"
else
  echo 'Aufruf: bash start.sh --web [--host IP --port 8765] oder --desktop' >&2
  exit 1
fi
