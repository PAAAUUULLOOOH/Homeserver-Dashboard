# License texts, copyright notices and rebuild information

The files in this directory reproduce upstream notices without rewriting their license terms. [THIRD-PARTY.md](../THIRD-PARTY.md) maps them to shipped components. [LICENSE-NOTICE.md](../LICENSE-NOTICE.md) describes the separate status of Vitalux's original code and branding.

- `runtime/`: CPython and psutil notices.
- `upstream/`: verbatim licenses, copyright files and Qt attribution records from the exact source archives in `third_party/sources.lock.json`. This conservative collection can include notices for upstream optional or test components that are not distributed as binaries.
- `system-libraries/`: copyright/license notices for bundled X11/XCB/xkbcommon and zlib helpers, plus retained package notices from the original runtime.
- `appimage-dependencies/`: musl, zstd, zlib and mimalloc notices for the upstream AppImage runtime build.
- `GPL-2.0.txt`, `GPL-3.0.txt`, `LGPL-2.1.txt`, `LGPL-3.0.txt`: complete license texts.
- `source/fio-3.43-build-source.tar.gz` in extracted portable packages: the exact fio build-source tree, including its original COPYING and build files. The release's separate third-party source download includes the same archive.

## Rebuild and replacement

**Qt 6.12.0:** unpack matching QtBase, QtDeclarative, QtSvg, QtWayland and QtImageFormats source archives. Follow their included README/configure/CMake instructions to build a shared Qt installation. Qt's platform prerequisites remain necessary. Use a compatible build configuration/ABI when replacing the shipped shared libraries.

**PySide6/Shiboken 6.12.0:** unpack the matching `pyside-setup` archive and follow its included build instructions, pointing the build at the compatible Qt installation. Replace bindings and libraries together under `runtime/lib/python3.12/site-packages/`; keep applicable notices with them.

**CPython 3.12.7:** the CPython archive includes its configure/Makefile build system and complete license information. A shared Python build uses `./configure --enable-shared`, then `make`; platform dependencies and installation paths must match the intended runtime layout.

**fio 3.43:** unpack the preserved build-source archive, read its `README` and `HOWTO`, and use its `configure`/`make` build system. Vitalux invokes fio as a separate process through `bin/fio`; it does not link fio into the Python application.

**libaio 0.3.113:** unpack the locked source archive and run `make -j2` on Linux x86-64 with GCC. The unmodified upstream Makefile builds `src/libaio.so.1.0.2` with SONAME `libaio.so.1`; Vitalux supplies that shared object as `tools-lib/libaio.so.1`.

**AppImage runtime:** the pinned `type2-runtime` source includes its build scripts, Alpine environment and libfuse patch. Use those instructions with the included libfuse/squashfuse source versions. Vitalux's `packaging/runtime/SHA256SUMS` identifies the embedded runtime binary. To inspect or replace the application payload without FUSE, use `./Vitalux.AppImage --appimage-extract` and run `squashfs-root/AppRun --portable`.

All third-party license rights, source obligations and warranty disclaimers continue to apply. Preserve these notices when redistributing those components.
