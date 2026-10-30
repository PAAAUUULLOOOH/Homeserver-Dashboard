# Vorbereitete Laufzeit

Die vollständige Linux-x86_64-Laufzeit wird als Datei `vitalux-linux-x86_64.tar.xz` im GitHub-Release `v0.10.0-test` bereitgestellt. Sie enthält Python 3.12, PySide6, psutil und ergänzende Bibliotheken.

Das vollständige Test-ZIP des Releases enthält diese Datei bereits. Bei einem Git-Checkout oder GitHubs automatisch erzeugtem „Source code (zip)“ lädt `ensure-runtime.sh` die Datei beim ersten Start vom selben Repository nach und prüft ihre feste SHA256-Prüfsumme. Die Binärdatei wird nicht im Git-Verlauf gespeichert.

SHA256: `194c62824f26239a7460c7bc12f4627eda0b616cf31b0cf861b963121081f3c8`
