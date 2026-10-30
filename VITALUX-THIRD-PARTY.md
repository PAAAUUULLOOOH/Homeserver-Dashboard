# Third-party components and source

This inventory describes Vitalux's Linux x86-64 distribution. The application source, third-party runtime and optional system tools are separate components. Third-party licenses do not automatically license Vitalux's original code; see [LICENSE-NOTICE.md](LICENSE-NOTICE.md).

| Component | Distributed version / scope | License and notices | Source |
| --- | --- | --- | --- |
| CPython | 3.12.7, interpreter and standard library | [PSF and included historical/third-party notices](licenses/runtime/Python-3.12.7.txt), [upstream notices](licenses/upstream/cpython) | [v3.12.7](https://github.com/python/cpython/tree/v3.12.7) |
| PySide6 and Shiboken | 6.12.0, dynamically loaded Python bindings | LGPL-3.0 option; [complete upstream license collection](licenses/upstream/pyside-setup/LICENSES) | [v6.12.0](https://github.com/pyside/pyside-setup/tree/v6.12.0) |
| Qt | 6.12.0, QtBase, QtDeclarative, QtSvg, QtWayland and QtImageFormats runtime modules | LGPL-3.0 option for the included runtime; [Qt licenses and bundled third-party notices](licenses/upstream/qtbase), plus the corresponding module directories | [Qt source repositories](https://github.com/qt), exact archives in [source manifest](third_party/sources.lock.json) |
| ICU | 73.2, Qt Unicode libraries | Unicode/ICU and included third-party notices in [ICU source notices](licenses/upstream/icu) | [release-73-2](https://github.com/unicode-org/icu/tree/release-73-2) |
| psutil | 7.2.2 | [BSD-3-Clause](licenses/runtime/psutil-7.2.2.txt) | [release-7.2.2](https://github.com/giampaolo/psutil/tree/release-7.2.2) |
| fio | 3.43, separate disk-benchmark executable | [GPL-2.0](licenses/GPL-2.0.txt); exact previously built source archive remains in `licenses/source/fio-3.43-build-source.tar.gz` in extracted packages | Complete build source in that archive and the release source package |
| libaio | 0.3.113, dynamically linked fio helper, rebuilt without source changes | [LGPL-2.1](licenses/LGPL-2.1.txt), [upstream notices](licenses/upstream/libaio) | Exact archive and digest in the source manifest |
| Xau, XCB and xkbcommon | Linux shared libraries in `lib/` | MIT/X11-style notices; [package copyright files](licenses/system-libraries) | Upstream/source URLs in those copyright files |
| zlib | Shared helper in `tools-lib/` | [zlib notice](licenses/system-libraries/zlib1g.copyright.txt) | [zlib](https://zlib.net/) |
| AppImage type-2 runtime | `fedfad51acc2860b2916a1eef32ba4a500ff31ef`, AppImage only | [MIT and statically linked dependency notices](licenses/upstream/type2-runtime/LICENSE); [additional verbatim notices](licenses/appimage-dependencies) | [Exact runtime source](https://github.com/AppImage/type2-runtime/tree/fedfad51acc2860b2916a1eef32ba4a500ff31ef) |
| libfuse and squashfuse | Runtime build uses libfuse 3.15.0 and squashfuse 0.5.2, including upstream runtime patches | [LGPL-2.1](licenses/LGPL-2.1.txt), [libfuse notices](licenses/upstream/libfuse), [squashfuse notices](licenses/upstream/squashfuse) | Exact archives, checksums and runtime patches in the release source package |
| musl, zstd, zlib and mimalloc | Used by the upstream static AppImage runtime build; individual embedded versions are not recorded in its binary | MIT/BSD/zlib notices in [appimage-dependencies](licenses/appimage-dependencies) | Upstream runtime build scripts identify its Alpine environment and build dependencies |

## Source availability and replacing libraries

Each release provides **`Vitalux-vVERSION-ThirdPartySources.zip`** beside the binary downloads and their SHA-256 manifest. It contains checksum-locked upstream archives for the listed source components, the exact fio build-source archive, the AppImage runtime sources and its libfuse/squashfuse dependencies. [sources.lock.json](third_party/sources.lock.json) records the download addresses and SHA-256 digests. Complete Qt source archives also retain their own third-party source, attribution and license files.

The exact source archives are also available from the addresses in that manifest. Keep the source download available alongside redistributed binaries. The notices include upstream optional/test components as well; their presence in the notice collection does not mean every upstream module is included in Vitalux.

Qt/PySide6 libraries are dynamically loaded from `runtime/lib/python3.12/site-packages/PySide6/`. Compatible replacement shared libraries and bindings can be used there. For AppImages, extract first with `./Vitalux.AppImage --appimage-extract`, replace libraries under `squashfs-root/`, then run `squashfs-root/AppRun --portable`. Modifications for debugging LGPL library changes are not prohibited. Rebuild guidance and license text links are in [licenses/README.md](licenses/README.md).

## Assets, fonts and trademarks

The Vitalux SVG logo, custom outlined wordmark, separate theme/accent palettes, procedural interface drawings and existing background images are carried as project assets. The new wordmark is stored as vector contours and has no external font dependency. `assets/brand/palettes.json` and `assets/brand/geometry.json` are the editable branding sources; `scripts/build-brand-assets.py` rebuilds the SVGs using the Python standard library. Sidebar category symbols are drawn by Vitalux rather than an external icon package. No separate font files are distributed; normal text uses the desktop's available fonts. Original project assets retain the same licensing position as the project code.

Distribution logos are loaded from the host's icon theme; Vitalux does not include a distribution icon pack. The README screenshot displays a Debian host. Debian and other distribution names/logos belong to their respective holders; their appearance does not imply endorsement. The host Debian package copyright notice is retained in `licenses/system-libraries/debconf.copyright.txt`.

## System tools and build tools

Desktop OpenGL/Vulkan drivers, the compositor, PulseAudio or PipeWire's PulseAudio service, Linux sensors, SMART utilities and other external diagnostics are supplied by the operating system, not bundled into Vitalux. Their availability and licenses are governed by their distributions. CI's Xvfb, Weston and audio test server are test infrastructure. Appimagetool is a build tool, not an additional executable shipped inside Vitalux.

This inventory records identified components and retained notices. It is not a legal opinion or a warranty of copyright/trademark clearance for original project material.

## Branding build tools

The approved concept silhouettes were converted to vector paths locally using vtracer 0.6.15 (MIT), NumPy 2.5.4 (BSD and included notices) and fontTools 4.67.0 (MIT and included notices). Their verbatim license collections are retained in [licenses/branding-build-tools/](licenses/branding-build-tools/). These tools are not bundled as executable code or added as Vitalux runtime dependencies. Rebuilding the supplied vector geometry does not require them. Qt/PySide6 and the system FFmpeg were used to validate and record previews; no FFmpeg executable is shipped with Vitalux.

## Optional network helper

The Vitalux network helper and its eBPF instruction generator are original project code, using Python’s standard library and Linux kernel APIs. No BCC, LLVM, OpenSnitch or external firewall daemon is bundled. Polkit and the optional host Python interpreter are supplied by the operating system. The `Proprietary` BPF program license string declares compatibility to the kernel; it does not grant additional rights in the Vitalux source. The Linux kernel, QEMU and a disposable test root filesystem used for integration validation are test infrastructure and are not included in the application packages.

## PCI identification data

`assets/hardware/pci.ids` is the complete 2026.10.24 [PCI ID Database](https://github.com/pciutils/pciids) snapshot, maintained by Albert Pool, Martin Mares and contributors. Copyright in its aggregation and formatting belongs to Martin Mares and Albert Pool. It is distributed here under GPL-2.0-or-later; the complete preferred source data is included verbatim, with provenance and SHA-256 in `assets/hardware/provenance.json`. See [GPL-2.0](licenses/GPL-2.0.txt). An optional background refresh reads the same upstream project's public source file into the active profile cache.
