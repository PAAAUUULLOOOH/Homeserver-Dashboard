#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ "$(uname -m)" != x86_64 || "$(uname -s)" != Linux ]]; then
  echo 'Die vorbereitete App-Laufzeit benötigt Linux x86_64.' >&2
  exit 1
fi
if [[ -f runtime/bin/python3.12 ]]; then
  chmod u+x runtime/bin/python3.12
  exit 0
fi
archive=portable-runtime/vitalux-linux-x86_64.tar.xz
expected=194c62824f26239a7460c7bc12f4627eda0b616cf31b0cf861b963121081f3c8
url=https://github.com/PAAAUUULLOOOH/Homeserver-Dashboard/releases/download/v0.10.0-test/vitalux-linux-x86_64.tar.xz
if [[ ! -f "$archive" ]]; then
  mkdir -p portable-runtime
  echo 'Vorbereitete Laufzeit vom GitHub-Release herunterladen …'
  if command -v curl >/dev/null 2>&1; then
    curl --fail --location --retry 3 --connect-timeout 15 --output "$archive.partial" "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget --https-only --output-document="$archive.partial" "$url"
  else
    echo 'Für einen Quellcode-Checkout wird curl oder wget benötigt. Alternativ das vollständige Test-ZIP vom Release verwenden.' >&2
    exit 1
  fi
  mv -- "$archive.partial" "$archive"
fi
actual="$(sha256sum "$archive")"
actual="${actual%% *}"
if [[ "$actual" != "$expected" ]]; then
  echo 'Die Laufzeit-Prüfsumme stimmt nicht. Datei nicht entpackt. portable-runtime/vitalux-linux-x86_64.tar.xz entfernen und erneut laden.' >&2
  exit 1
fi
echo 'Die mitgelieferte Laufzeit wird lokal entpackt …'
tar --no-same-owner -xJf "$archive"
chmod u+x runtime/bin/python3.12
