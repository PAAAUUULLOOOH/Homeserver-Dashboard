#!/usr/bin/env bash
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
echo 'Vitalux Homeserver · Voraussetzungen prüfen (ändert keine Systemkonfiguration)'
echo "Architektur: $(uname -m)"
if command -v docker >/dev/null 2>&1; then
  env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock version --format 'Docker Server: {{.Server.Version}}'
else
  echo 'Docker Engine fehlt. Anleitung: https://docs.docker.com/engine/install/'
fi
if [[ -f portable-runtime/vitalux-linux-x86_64.tar.xz ]]; then echo 'Python, PySide6 und psutil: im Paket enthalten.'; fi
if [[ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then echo 'Headless-Betrieb: START-UBUNTU.sh verwenden.'; else echo 'Desktop erkannt: START-APP.sh verfügbar.'; fi
echo 'Für das Web-Dashboard ist keine weitere Python-Paketinstallation nötig.'
