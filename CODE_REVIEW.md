# PS Focus code review ? 12 October 2026

Review priorities: responsive interaction, low CPU and memory use, small installed/download footprint, and understandable code while preserving current behaviour. Reviewed the tracking loop, recent UI/docking changes, friend sync and dialogs, demo interactions, storage/backup paths, and release packaging. This is a focused engineering review, not a guarantee that every possible bug is eliminated.

## Fixed

- **Incorrect time attribution on activity transitions:** the old loop credited elapsed time to the newly detected program, including time before it became foreground, and dropped the final interval when leaving it. Elapsed time now belongs to the previous observed state. Fractional seconds stay with their own program, preventing cross-program rounding errors. Pause/resume updates immediately.
- **Duplicate activity detection:** a focus change previously sampled Windows twice. The transition now passes its existing sample to the refresh. The responsive 100ms polling remains; unchanged polls do not refresh the dashboard.
- **Repeated process enumeration and repaint:** open-program snapshots are reused for up to one second. The actual foreground program is added immediately, so active tracking does not wait for the cache. Removed unconditional Today repaint; changed text/state still schedules repaint.
- **Popup monitor placement:** menus use the screen at the requested location and clamp both lower and upper bounds, including monitors with negative coordinates.
- **Today hover erased activity colour:** program name retains its blue/green colour while hovering the strip.
- **Demo dropdown open styling:** open/close now sets and clears the shared button highlight class.
- **Dead and confusing code:** removed unused imports, the unused overlap helper, and the permanently enabled selector flag. Renamed friend detail storage to match its actual dialog purpose. Screenshot tooling stops the new focus timer.

Core tracking was subsequently audited and hardened in 1.1.20; see [TRACKING_REVIEW.md](TRACKING_REVIEW.md) for regression coverage and remaining accuracy limits.

## Remaining improvement candidates

1. **Medium ? synchronous backup/restore can delay the UI.** `qt/app.py::_backup_activity_now` creates local SQLite backups on the UI thread; `qt/google_sync.py::poll` applies downloaded history and creates/reads the upload snapshot there. Slow or unavailable backup folders can stall input. Move disk work to a single background worker using its own SQLite connection and return completion to the UI. Preserve the existing restore/rebinding order and bounded shutdown. This deserves dedicated failure and concurrent-write tests; simply moving the existing connection to another thread would introduce bugs.
2. **Medium ? docking logic duplicated in desktop and demo.** `qt/docking.py` and `docs/assets/demo/demo.js` implement geometry, snapping and group movement separately. This has caused behaviour drift. Keep the two renderers, but document a small shared specification and use the same geometry fixtures in Python and JavaScript. A new generic docking framework or rewriting the app would add more complexity than it saves.
3. **Low ? UI orchestration is concentrated in `qt/app.py`.** Extract tracking/accounting into a small controller when the next tracking feature is added. Avoid a broad rewrite now: the recent regression tests protect current behaviour, and splitting every callback into separate classes would make modification harder.
4. **Low ? handover history is long.** Keep the current state and outstanding issues near the top; move older resolved notes to an archive at the next handover cleanup. It has no runtime/package cost and is useful context, so it was preserved.

## Size and runtime observations

Before this review, installed 1.1.18 had a ~18.3 MB installer (decimal), ~56.0 MB logical installed files and ~22.4 MB allocated bytes with Windows compression. A running sample-friends instance showed ~36.8 MiB private memory and ~81.1 MiB working set. Working set includes shared framework pages and is not the same as private memory. These are snapshots, not peak memory or a long-run leak test.

Packaging already uses PySide6 Essentials only, excludes unused Qt/network/OpenSSL/toolkit components, strips Python docstrings, and uses a compressed installer with on-disk compression. Cached panel images avoid allocating/repainting complete charts on every mouse move. Keep those choices: more aggressive DLL removal, forcing Windows to trim working sets, or replacing Qt solely to chase a smaller number would put responsiveness and stability at risk. The cleanup aims to reduce redundant work; it does not claim a large reduction in framework memory.

## Cleanup and validation

Removed the empty accidental SERSELIHUPSFOCUS/docs/assets directory tree and disposable Python bytecode caches. Preserved credentials.json, history/settings/backups, handover notes, source assets, Qt licence wheel cache and the current installer. No Git history rewrite, commit, push or site publication.

Release 1.1.19 passed all 249 tests, source/package credential checks, Windows/offscreen packaged smoke tests, Node syntax and diff checks. Installed and reopened successfully. Final installer: 18,265,775 bytes; installed logical bytes: 55,986,489; allocated bytes: 22,402,186. A short post-install sample showed 40.2 MiB private memory, 83.6 MiB working set and 0.2031 CPU seconds over 10 seconds (about 2% of one core). The older instance sampled 36.6 MiB private / 81.5 MiB working set and 0.1562 CPU seconds over 10 seconds. These differently aged live instances are not a controlled before/after benchmark: **no material memory or installer reduction is demonstrated**, and the redundant-work reductions are verified by call-count tests rather than these noisy samples. Further measurements should compare the same history, visibility, activity state and elapsed runtime over a longer period.

Final checksum and handover are recorded in HANDOVER.md. Interactive Photoshop and browser checks were not performed during this review; automated Qt regression and packaged smoke checks cover the changes.
