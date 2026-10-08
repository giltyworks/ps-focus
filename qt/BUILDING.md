# Qt preview builds

The Tk release specification and installer are unchanged. This is a separate executable for testing the unfinished Qt port, not a replacement release.

Run from the repository root on Windows:

```powershell
python -m pip install -r requirements-qt.txt pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.7
python tools/build_qt_preview.py
# Also build the separate per-user installer:
python tools/build_qt_preview.py --installer
# Recommended low-disk-footprint installer (folder runtime, Windows compression):
python tools/build_qt_preview.py --compact --installer
```

Output: `dist/qt-preview/PS Focus Qt Preview.exe` and `SHA256SUMS.txt`. The executable includes collected Python and Qt package notices and the same minimal public Desktop OAuth client configuration used by the existing build. It excludes Tk, Pillow and pystray. The separate **Build Qt preview** GitHub workflow can be started manually; it uploads artifacts and does not publish a release.

`--compact` outputs into `dist/qt-preview/compact-build`: the installer, a fresh `app-*` folder containing the executable and required `_internal` runtime, and checksums with relative paths. Keep the executable and runtime folder together. The installer uses Windows `compact.exe /EXE:LZX` on its own program directory after installation; it never compresses activity data or changes OS compression settings. Unsupported filesystems retain a working, uncompressed installation. The standalone folder is uncompressed; the measured saving applies to installation through this installer.

Measured installed allocation on Windows/NTFS: **27,153,546 bytes (27.2 MB)** including the uninstaller, from **68,860,802 logical bytes**. The installer download is **20,471,239 bytes (20.47 MB)**. Folder packaging avoids the one-file executable's temporary extracted runtime, so running uses the same program footprint, plus user history/backups. Keeping the downloaded installer also consumes space. The old one-file build remains available for comparison. The manual CI workflow now builds the compact installer and enforces a 50,000,000-byte installed allocation budget. `tools/qt_disk_usage.py` measures allocation using Windows `GetCompressedFileSizeW`; the installer test saves its measurement in `build/qt-preview/installed-footprint.json`.

The installer now uses solid LZMA2/ultra64 with one compression block thread and 273 fast bytes, saving 511,937 bytes versus the earlier installer. This increases build compression time/memory and the install-time dictionary from 8 to 64 MB; application memory use is unaffected. See [Inno compression options](https://jrsoftware.org/ishelp/topic_setup_compression.htm).

For the user's 35 MB **including retained offline installer** request, the measured total is **47,714,059 bytes (47.71 MB)** with their current preview data. Local backup folder NTFS compression was applied separately on this PC, reducing its 11 files from 450,560 to 45,056 allocated bytes with identical SHA-256 contents. Total preview data is now 89,274 allocated bytes (494,778 logical bytes). No backups were deleted. This backup compression is a local filesystem setting, not yet automatic behavior in the installer/app for other users. Neither current history nor the Tk data directory was compressed. The 35 MB combined target is not achieved with this runtime/package.

Further safe trimming removes optional BZIP2/LZMA/Zstandard archive codecs that `shutil` and `zipfile` otherwise collect. SQLite backups and Shiboken's zlib ZIP signatures still work. Revisit these exclusions before adding those archive formats. The build sets `PYINSTALLER_ZLIB_COMPRESSION_LEVEL=9` and builds with `--clean` to avoid reusing an archive made at a different compression level; assertions and docstrings are retained. Packed smoke tests also create a default SSL context, checking that Python/OpenSSL and trusted certificate loading remain available (no live OAuth/network test).

The requested 15 MB installed target is **not achieved**: six required stock Qt DLLs/bindings alone occupy 14,061,568 compressed bytes, with Python's core DLL adding 2,666,496 bytes before the remaining runtime/services/UI/uninstaller. These are measurements of the current binaries, not a lower bound for every possible custom Qt build. Apparent MSVC duplicates have different hashes and are retained. Custom Qt/binding compilation or native rewriting is separate work, deferred for Claude rather than changing the port's structure.

The build first stages and smoke-tests the executable. If the existing output executable is running/locked, new files go into `dist/qt-preview/next-build` so the running preview can stay open. `--installer` creates `PS-Focus-Qt-Preview-Setup-<version>.exe` beside the new executable, with checksums for both files.

The package is trimmed for the current raster-painted, English-only interface: it retains Windows/offscreen platform plugins, ICO decoding, built-in PNG support and the Windows style. It excludes software OpenGL, SVG, unused image formats, Qt networking/plugins and translations; Google HTTPS continues through Python's SSL libraries. Revisit these exclusions if the app adds OpenGL, SVG assets, other image formats, translated native UI or Qt network APIs. Current size: executable 25.7 MiB, installer 27.4 MiB.

Packed smoke tests now exercise both Windows and offscreen platforms, icon decoding, graph/calendar/stats rendering, portrait/landscape layouts, Settings navigation and shutdown with temporary data.

The installer has its own AppId, install directory (`%LOCALAPPDATA%/Programs/PS Focus Qt Preview`), Installed apps entry, shortcuts and Windows taskbar identity. It uses Inno's uninstaller, preserves preview AppData/tokens and offers no Windows-startup task. It does not reuse Tk's app-managed uninstaller or installation identity. The CI workflow builds and validates this installer too.

Validate installation only when no Qt preview is already installed:

```powershell
python tools/test_qt_installer.py "dist/qt-preview/PS-Focus-Qt-Preview-Setup-1.0.7.exe"
# Compact installer with the disk target enforced:
python tools/test_qt_installer.py "dist/qt-preview/compact-build/PS-Focus-Qt-Preview-Setup-1.0.7.exe" --max-installed-bytes 50000000
```

This temporarily installs into the workspace, starts with isolated data, uninstalls, and checks that its registration is gone, preview data is retained, startup entries are unchanged and the installed Tk executable has not changed. It refuses to run over an existing installed preview. The running loose preview need not be closed.

The packaged entry always copies installed activity/settings into `%APPDATA%/PS Focus Qt Preview` before importing the app. It uses separate Google Drive filenames, `qt-preview-settings.json` and `qt-preview-activity.sqlite3`. Startup controls are disabled. Existing preview tokens remain in that preview folder; installed tokens are not copied. Starting a preview resets its history/settings from the installed app, as the source preview does.

The build runs the Qt/tracker tests, checks the archive for credentials, writes a checksum, and checks startup/shutdown with temporary data using the offscreen Qt platform. The three Qt TLS DLLs containing PEM marker strings are accepted by the credential checker only if their SHA-256 hashes match the installed Qt binaries; other credential patterns remain checked.

If a manually copied Qt installation lacks distribution metadata, download matching wheels without installing them:

```powershell
python -m pip download --no-deps --dest build/qt-preview/wheels PySide6==6.11.2 PySide6_Essentials==6.11.2 shiboken6==6.11.2
```

The notices collector preserves the licence fields and licence documents supplied by those distributions. The current wheels contain a commercial licence reference while their metadata also lists open-source licensing options. Complete Qt runtime/third-party licence notices and public distribution review remain part of release preparation; the generated preview notices do not claim that work is complete.

Production replacement/upgrade behaviour, startup registration, update endpoint behaviour, native visual testing and performance comparisons remain in `CLAUDE_HANDOVER_TEMP.md`. The separate preview installer is complete; do not point the existing Tk installer at the preview executable.
