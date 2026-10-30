# Vitalux Homeserver 0.10.0 test package

Independent local test build for Ubuntu/Debian with Docker on Linux x86_64. It does not modify an installed Vitalux, register a service or publish a website. Download the [complete test ZIP](https://github.com/PAAAUUULLOOOH/Homeserver-Dashboard/releases/download/v0.10.0-test/Vitalux-Homeserver-v0.10.0-Test-linux-x86_64.zip) from the [GitHub release](https://github.com/PAAAUUULLOOOH/Homeserver-Dashboard/releases/tag/v0.10.0-test).

The complete release ZIP includes the runtime. A Git checkout or GitHub's generated source archive downloads the pinned runtime from the same release on first launch and verifies its SHA256 before extracting it.

Extract into a new writable folder. Run `bash PRUEFEN.sh` to check prerequisites, then `bash START-APP.sh` for the native desktop UI or `bash START-UBUNTU.sh` for a headless server. The first launch extracts the bundled Python 3.12, PySide6 6.12, psutil and XCB runtime. Docker Engine and local Docker-socket access must already be available. Create your own admin password of at least twelve characters. Web mode uses http://127.0.0.1:8765 and user `admin`.

Includes original native Vitalux design components, seven designs, real host metrics, Docker game templates, TeamSpeak 3, Minecraft Paper/Vanilla/Fabric/Forge, stopped-server backups and restore, Minecraft JAR management and RCON. PAULFLIX runs in the system browser and indexes configured local media folders with protected range streaming. Browser UI components are CSS implementations using original palettes and Qt-rendered backgrounds. Player queries, transcoding, a mod marketplace, schedules and automatic container upgrades are not implemented.

The runtime and designs are bundled; game images and game binaries are not. Use the catalogue's preload button or `bash VORLADEN.sh --list`, `bash VORLADEN.sh minecraft teamspeak`, or `bash VORLADEN.sh --all`. Initial game startup can still require additional downloads. `--export /path/images.tar` and `--import-file /path/images.tar` support transferring Docker images.

All state is stored under the extracted folder's `data/`, including a separate native design profile. Stopping the dashboard does not stop game containers. Remove a stopped container in the dashboard to remove its tile; saves and backups remain. Game template integration is present, but full downloads and game client connections were not tested for every title. See README.md and TESTBERICHT.md for detailed scope and actual validation. Retained upstream and third-party license notices apply.
