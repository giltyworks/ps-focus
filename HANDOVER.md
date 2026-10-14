# PS Focus handover

Updated 14 October 2026. Read this before resuming work.

## Pre-commit hooks: 14 October 2026

PS Focus now has local git pre-commit hooks that run gitleaks on the staged changes and `py tools/check_credentials.py`, and block the commit if either fails. They live in `.git\hooks` (`pre-commit` hands over to `pre-commit.ps1`) and aren't committed, so a fresh clone won't have them.

## today_panel.py comment: 14 October 2026

The owner asked to fix the stale main.py reference: the comment above TODAY_PANEL_PADDING in qt/today_panel.py now says the Tk panel's main.py was removed in 3e15ae5. Comment only, no behaviour change.

## Known issues

- PyInstaller is missing from requirements.txt. Only the Build installer workflow installs it (`pyinstaller==6.22.3`, `pyinstaller-hooks-contrib==2026.7`), so `py tools/build_release.py` fails on a fresh setup made from requirements.txt alone. Not fixed yet, by the owner's choice.

## Code quality review and fixes: 14 October 2026

Claude Code ran the code quality review (four read-only reviewers, merged into 33 numbered findings). The owner picked the recommended set; the rest are on hold. Not committed.

Fixed (each with a test):
- Double-clicking a rating star no longer sets and then clears the rating: DayOverview takes one rating per opening (`rated` flag).
- Session counts, streaks and longest session use `SESSION_MINIMUM_SECONDS` instead of their own `15 * 60` (tracker.py now imports it from app_config).
- The website demo's levels now use the app's exact `LEVEL_HOURS` table (it used straight lines between anchors). `tools/sync_site.py` writes the table into demo.js; test_site fails if the curve changes without running it. The demo's `?v=` cache number in docs/index.md was not bumped; do that when the site is next published.
- Google Drive: the 15-minute backup skips the merge and upload while Drive still holds exactly this PC's last upload (SHA-256 of the bytes) and the store's change count is unchanged. Back up now, signing in/out and switching account always upload. A stale copy uploaded by another PC is still replaced.
- Start-up recovery no longer crashes if a backup file vanishes between listing and reading (OneDrive).
- A second failed shutdown save now keeps both lots of unsaved time, under the older receipt so nothing is counted twice.
- "Remaining XP" rounds the next level up, so it can't show 0 before the level rises (52 levels were affected).
- Today's calendar fill is no longer drawn over the year view when the view is switched mid-animation.
- Dev version: the level-up fanfare request is always cleared after the menu's level-up.
- Tidying with no behaviour change: comments pointing at removed Tk files (qt/__init__.py now says the Tk sources are in the commit before 3e15ae5; make_celebration.py points at qt/celebration.py; uninstall.py, stat_lines.py, app_config.py, the update-check comment and the credentials error message corrected); dead friend-list code (dot, PRESENCE_COLORS, `_hide_person_tip`), unused `backup_error`, `MIN_WINDOW_HEIGHT` and arrow parameters removed; `self.panels` replaced by `self.today`; `_read_activity_state` and `_pending_rows` helpers; header cursor uses `interactive_at`; always-true `hasattr` guards removed in `_backup_activity_now`, `GoogleSync.poll` and docking; `FriendsSync.tick` checks `enabled()` once.
- Kept on purpose: the second `_send_pending_feedback()` at start-up (it still runs if the start-up backup fails) and, at the time, the qt/today_panel.py main.py comment (since fixed, see above).

301 tests and the credential check passed. 1.1.27 built (installer SHA-256 `1d8b24c1cc619d0ee714dd1bcebe837f4e4bf2598be270a1d4de664bba52f051`), installed silently (exit 0) and relaunched, normal and `--dev`. README updated (Drive upload skip, sync_site after level changes).

On hold, for the owner to decide: two PCs in the same hour lose time in the Drive merge (keeps the larger total per hour; a real fix changes the storage); local backups run on the UI thread (time them first; dropping the second integrity check is the cheap step); damaged-database recovery may pick another PC's OneDrive backup; the Drive restore swaps the store by hand in google_sync.py; uninstall.py keeps its own list of data folders; "preview" naming; optional items 21–33 (speed savings, helpers, shared test setup, version stamping, release-note warning that the harder top levels lower long-time users' levels).

## Code quality review skill: 14 October 2026

The "code quality review" instructions are a Claude Code skill in the owner's user folder, `C:\Users\elihu\.claude\skills\codequalityreview\SKILL.md`, so one copy serves every project. It is not in this repository; an earlier project copy under `.claude/skills/` was removed. It runs only when the owner asks for a code quality review. Four read-only reviewers (correctness, simplicity, performance, maintainability) work in parallel, and their findings are merged into one ranked list. It then stops until the owner picks which fixes to make, fixes only those, and verifies using the project's own CLAUDE.md: its test, build, release and verification steps and definition of done. For PS Focus that includes the release build, silent reinstall and relaunch.

## CLAUDE.md added: 14 October 2026

Claude Code added CLAUDE.md at the project root: what the app does, stack, commands, layout, conventions and a definition of done. It asks both tools to read this file at the start of a session and to update it at the end with what changed, what's next and any open questions. No code changed.

## Full release rollup since 1.1.0

Compared all commits v1.1.0..v1.1.21 and current implemented behaviour. Expanded published 1.1.21 What's new notes to cover the major omitted changes: Friends, presence choices, favourites/nicknames/sections, double-click details, custom Windows-aware title bar, compact layouts/Settings, transparent text readability, refined docking, consistent controls, calendar/Stats readouts, Today auto-follow, PhotoCraft, tracking reliability and interactive demo. Canonical notes are now versioned in release-notes/1.1.21.md. Kept Install formatting, exact existing asset/hash, and the UI-stall accuracy limitation. Published the expanded notes and verified the full body through the GitHub API. Installer assets were not replaced.

## Stale local preview resolved

User still saw old program copy and dead policy links because their browser URL was a file:// Claude scratchpad site_preview.html, not GitHub Pages. Inspected exact supplied file: old three-program text and href="#" policy placeholders. Live homepage and both policy pages were independently verified HTTP 200 with PhotoCraft. Replaced only the named temporary preview with a redirect to https://giltyworks.github.io/ps-focus/ and absolute fallback policy links; original preserved beside it as site_preview.before-live-redirect.html. No production code/deployment change was needed. Refreshing the user's existing preview tab now opens the live website.

## Release formatting and PhotoCraft website coverage

Reformatted published v1.1.21 notes to match v1.1.0: What's new heading, bold feature lead-ins, Install heading, preservation/SmartScreen instructions and inline SHA-256. Kept the sampled-tracking/UI-stall limitation. Installer assets unchanged. Website hero already named PhotoCraft; now the feature list, shared footer, privacy and terms pages also include it. Source PRIVACY.md/TERMS.md synced to site, and privacy sampling language now says regularly rather than once per second. These policy text updates are website/source-only; existing published installer still embeds its original policy text until a future rebuild. Site tests/diff checks passed. Published website commit 694e8d4882f513fb54059c65b1bd7b99471ee78c; live homepage/footer, privacy and terms content verified. Published release notes verified through GitHub API.

## Publication completed: 1.1.21

User explicitly authorized all necessary deployments and website publication, then resumed after an approval-review usage-limit interruption. Published application/source commit f4c03c53a39edb4160f15ae1c0b9bf4dc87477ed; all 71 prior local commits were fast-forward compatible with remote. Outgoing history credential scan passed for 204 new blobs, staged source scan passed, and GitHub credential workflow passed.

- Friends server: deployed https://ps-focus-friends.ps-focus-friends.workers.dev, version 89002927-eb25-41b6-91fa-420ce2639472. Local end-to-end tests passed including PhotoCraft status reaching a friend. No schema migration or production test accounts. Verified production returns 401 for development-auth tokens using the app's WinHTTP transport. Python urllib received an edge 403, so that transport was not used to infer application behaviour.
- Website: published https://giltyworks.github.io/ps-focus/ from main/docs. GitHub Pages build succeeded; live HTML contains PhotoCraft and versioned demo asset URLs. Demo credit now matches 1.1.21. Privacy/terms synced and site tests passed.
- Installer: latest public release https://github.com/giltyworks/ps-focus/releases/tag/v1.1.21 contains installer and checksum. Downloaded the public installer and verified SHA-256 `a7eed0ef567d26c927586c8b5564f4d5bd49866a6f489b60a92f3593624316db` matches the tested build. Tag targets f4c03c5; release is neither draft nor prerelease. Published local build passed 269 tests and credential/packaged smoke checks.
- Update notifications: user authenticated clasp through opened browser. Existing Apps Script project cloned to ignored build/publication/apps-script; remote source matched repository after changing only LATEST_VERSION. Pushed source and preserved manifest, created version 11, redeployed existing URL (deployment ending RMO7ag). Live GET confirms latest_version 1.1.21 and the correct GitHub latest-release URL. No feedback submissions or digest emails triggered.

Tag-triggered clean Windows build succeeded (GitHub Actions run 38195596313). Website and source are now public; earlier sections below describe historical states. Current installed app remains 1.1.21 with sample friends enabled. Core accuracy limitations remain documented in TRACKING_REVIEW.md.

## PhotoCraft tracking: 1.1.21

Added PhotoCraft to PROGRAMS and the exact executable registry (`photocraft.exe`). Confirmed installed running process at C:/Program Files/PhotoCraft/photocraft.exe and running_applications detects it. It inherits foreground/idle/pause accounting, Today auto-follow/manual history, chart/stat/calendar totals, and local active status. Added demo history option/sample values, README/site supported-program text, and the friends server PROGRAMS allowlist. Native executable test includes mixed-case PhotoCraft.EXE; integration regression verifies foreground following and separate PhotoCraft history. All 269 release tests passed; JS syntax checks passed. Build, source/package credential audits and packaged Windows/offscreen smoke checks passed. Installed successfully (exit 0), confirmed 1.1.21, reopened with sample friends enabled. Installer SHA-256: `a7eed0ef567d26c927586c8b5564f4d5bd49866a6f489b60a92f3593624316db`. Friends server source updated but NOT deployed, so remote friends won't see PhotoCraft active-program status until that worker is deployed. Local tracking does not depend on deployment. No Git commit, push or site publication.

## Core tracking audit: 1.1.20

See TRACKING_REVIEW.md for fixes, native API sources, benchmarks, tests and explicit limits. Actual elapsed fractional intervals now persist atomically by day/hour/program, split at boundaries. Failed writes retain pending buckets; observed state still advances, preventing wrong-app credit after retry. Flush occurs at each ordinary tick and transition, plus before shutdown UI/backup work. Exit failures use activity.pending.json with a transactional replay receipt to avoid duplication after interrupted cleanup. WAL synchronous=FULL protects acknowledged writes; live lock timeout is 100ms. TRACKING ERROR tooltip/label exposes errors. Windows awake clock excludes sleep; UOI_IO desktop check rejects lock/secure desktop; failed last-input queries stop crediting time. New tests cover 150 seeded transitions, fractions, midnight, failure/retry, actual SQLite locks/rollback, shutdown/recovery and detector API edge cases. Initial final suite exposed the unchanged idle failure path; fixed it and restarted release validation. Final release passed all 268 tests cleanly, source/package credential audits and Windows/offscreen packaged smoke checks. Installed successfully (exit 0), confirmed 1.1.20 and reopened with sample friends enabled. Final installer SHA-256: `a9354f90b176c3d7ed88fab698096dcd6fda1a4db59167ba6698435cfa0ce95d`.

Remaining important accuracy limitation: UI-thread polling/recording can still undercount during a long UI stall because unknown foreground intervals are capped at two seconds. A separate sampler/recorder is the proper future fix; removing the cap would invent activity. 100ms sampling and forced-kill/unwritable-storage limits also remain. Do not claim flawless tracking. Local 100-write FULL benchmark median 0.979ms / p95 1.221ms; foreground checks median 0.028ms / p95 0.052ms. No live lock/sleep/Photoshop interaction test performed. No commit/push/site publication.

## Code review and cleanup: 1.1.19

User prioritises highly responsive interaction, compact download/install/runtime footprint and simple modifiable code retaining UX. Detailed findings in CODE_REVIEW.md. Fixed activity transition time attribution (credit prior observed state, preserve fractions per program), reuse foreground samples, cache open-program snapshots for 1s while foreground changes remain immediate, remove unconditional Today repaint. Pause updates immediately. Popup uses requested monitor and clamps both bounds. Today name retains activity colour on title hover. Removed dead overlap helper, unused imports, permanently-enabled selector flag; renamed friend dialog details storage; screenshot tool stops focus timer. Demo menu anchors get psf-open styling. Regression fixtures now establish activity before simulating elapsed time, matching the corrected accounting semantics.

249 tests, source/package credential checks, Windows/offscreen packaged smoke tests, Node syntax/diff checks passed. Removed empty accidental SERSELIHUPSFOCUS/docs/assets tree and root/qt/tools bytecode caches. Preserved assets, personal settings/history/backups, credentials and licence wheels. Installed successfully (exit 0), confirmed 1.1.19 and reopened with samples enabled. Installer SHA-256: `8b70874238b688a67ebf97e9455fdd7306909a32ead747be9e6e9638a5bc00f5`. Installer 18,265,775 bytes; installed logical 55,986,489 bytes, allocated 22,402,186 bytes. Short live snapshot: private 40.2 MiB, working set 83.6 MiB, CPU 0.2031 seconds over 10s. Not a controlled benchmark; no large memory/package reduction claimed. Larger remaining candidates are UI-thread backup/restore stalls and duplicated Qt/demo docking rules. No commit, push, history rewrite or website publication.

## Responsive activity detection: 1.1.18

Added 100ms lightweight foreground/idle/pause polling alongside the existing 1s tracking tick. Only state transitions trigger an immediate full tick, updating Today and account presence promptly; unchanged polls do not redraw charts or query process snapshots. Poll timer stops on exit. Regression verifies active and inactive transitions, unchanged-poll suppression and timer interval. Updated all Qt test fixtures to stop the new timer before closing databases (initial suite passed but emitted cleanup errors; corrected full rerun passed 246 tests cleanly). Release build, credential audits and packaged smoke checks passed. Installed successfully (exit 0), confirmed 1.1.18, reopened with sample friends enabled. Installer SHA-256: `984a1b877cd7ef29f675ed206a88708dd0218fe1db563f4708a69bed1127d2a5`. No commit or publication.

## Demo canvas caption visibility

Simplified visible caption to "Demo canvas" only. Increased it from the former hint's 10px / 40% white to 12px / 90% white (brightened and enlarged again at user request), keeping top-left placement, normal weight, subtle shadow and no badge. Removed unused caption child classes. Syntax/diff checks passed. Demo-only, unpublished.

## Demo painting caption refinement

User preferred a much subtler top-left label and no drawing prompt. Caption now uses small normal-weight translucent text, inline Photoshop / Demo canvas, a slight readability shadow, and no badge background, border or padding. Removed click/tap-to-draw and revised accessible description to avoid implying a real brush. Existing painting-click activity simulation remains. No brush added. Syntax/diff checks passed; demo-only, unpublished.

## Demo painting visual cue

Added a quiet top-right Photoshop label on the painting with "Demo canvas ? click to draw" (tap on touch). Dark translucent badge preserves the artwork, fits narrow widths, and ignores pointer events so painting clicks still activate the demo. Canvas accessible description identifies Photoshop and the simulated action. Syntax/diff checks passed; no browser visual verification or website publication. Desktop unaffected.

## Demo focus/activity simulation

Demo starts active by user request: green Photoshop status and active username on website load. A root capture-phase primary pointerdown listener activates tracking when clicking the painting and deactivates it when clicking PS Focus's main window, detached modules, menus, dialogs or demo controls. Capture handles panel drag/resize handlers that stop propagation. renderToday updates Today color and calls renderAccount, producing green Photoshop status/name when Online and actively drawing, then light-blue name and Online caption after returning to PS Focus. Manual Away/Invisible/Offline and pause remain respected; hover does not change activity. Syntax/diff checks passed; no interactive browser verification or publication. Desktop remains 1.1.17 (demo-only change).

## Demo Today chevron correction

User screenshot showed tiny text arrow still present. Earlier Unicode string replacement missed the actual glyph; previous claim that Today's demo SVG was replaced was incorrect. Replaced the final child of today's program button explicitly with svg(ICONS.chevron), matching friend/account SVG and shared 16x16 button CSS. Verified source and Node syntax; no interactive browser verification or publication. Desktop stays installed at 1.1.17 because this correction is demo-only.

## Latest dropdown sizing: 1.1.17

User requested all dropdown buttons match Friends. Qt now shares DROPDOWN_BUTTON_SIZE=16 across Friends, account status and Today. All three have 16x16 hover/click rectangles as well as the shared glyph; account button is centered on the username line and Today on its strip. Demo's shared chevron class is now fixed 16x16 too. 82 targeted tests and all 245 release tests passed; syntax/diff checks passed. Build, credential audits and packaged smoke checks passed. Installed successfully (exit 0), confirmed version 1.1.17, and reopened with sample friends enabled. Installer SHA-256: `fa7ada7d8e39b1c516ccb54a4e32e72e121f2056d750ca76f0f7af7033b34217`. No Git commit or website publication.

## Latest dropdown fix: shared chevron, 1.1.16

Today now uses the same antialiased, rounded 1.4px chevron painter as Header and Friends, via `paint_dropdown_arrow` in qt/module.py. The arrow remains full-opacity regardless of program activity or glass alpha. Fixed the missing QRectF import in Today's hover path. Selector remains enabled during tracking. Demo now uses the standard SVG chevron and button class instead of a text glyph; all demo chevrons resist flex shrinking. Render regression verifies actual opaque glyph pixels for every supported program, active/inactive colors, opaque/translucent backgrounds, and hover states. Node syntax check passed. Initial sandbox suite failed Windows DPAPI tests; unrestricted release suite passed all 245 tests. Release build and packaged smoke checks passed. Installed successfully (exit code 0), confirmed installed version 1.1.16, and reopened with sample friends enabled. Installer SHA-256: `4d3ea588684916dde3bd67d39c33d547ca678085f3657e298095fe1bd332209e`. No website publication or Git commit.

## Latest demo-only adjustment: header centering

Centered the demo's name/status column on the header's midpoint rather than the asymmetric leftover flex space between Level and Settings. Name and status are centered within the same column; progress dot and dropdown chevron sit outside that column so they do not offset its text. Long names are truncated to available space. Settings stays right-aligned. CSS/JS syntax/diff checks passed; no interactive browser verification was performed. No desktop rebuild or website publication for this CSS-only edit.

## Latest Today layout change: manual PAUSED only, 1.1.15

User approved removing redundant ACTIVE/NOT ACTIVE labels. Only manual `tracking_paused` shows PAUSED; the slot is empty otherwise. PAUSED and the session count exchanged positions: pause indication sits beside lifetime record hours, and session count sits beside the last-session date below. App and demo match. A regression covers active/inactive/unpaused and manually paused states and verifies the row order. The user's wording "commit the paused change" was interpreted in context as applying the approved UI change, not staging/committing the accumulated unrelated working tree. Final build/install status follows.

1.1.15 passed 244 tests, credential audits, and Windows/offscreen packaged smoke tests. Installer SHA-256: `e931742bd277531fc73083b4f2561bcedd5f772dba00dd7c8f67043db1431370`. Installed successfully (exit code 0), confirmed version 1.1.15, and reopened with sample friends enabled. This is the latest installed build; no publication or commit.

## Latest dropdown clarification: always available, 1.1.14

User requested the Today selector remain enabled even during active tracking: interacting with PS Focus moves foreground away from the art program. Removed the stale `self.active` selection guard; selection immediately rechecks actual foreground through `_track_and_refresh`. If tracking truly resumes, automatic following still takes over. Arrow stays enabled in all states. A regression starts with cached active=True, changes foreground to PS Focus/None, and confirms manual selection succeeds immediately. Demo opening the selector stops its simulated drawing state, matching the focus change. This supersedes the disabled-active-selector behavior from 1.1.11. Final build/install status follows.

1.1.14 passed 243 tests, credential audits, and Windows/offscreen packaged smoke tests. Installer SHA-256: `2698b738aee0fc7603b167717a3a01fe9b56738deffc4c43bdc272676f39b276`. Installed successfully (exit code 0), confirmed version 1.1.14, and reopened with sample friends enabled. Demo clicking the painting resumes its simulated active program after manual selection. This is the latest installed build; no publication or commit.

## Latest UI consistency change: dropdowns, 1.1.13

Today program chevron now has the same subtle hover box as other dropdown arrows and retains its highlight while its popup is open. Open state clears when the menu is destroyed after dismissal/selection. Shared `PopupMenu` now uses a pointing-hand cursor over its entire menu, including program/status/friend/title dropdown choices. Outside a popup, it retains the underlying control's cursor as before. Regression assertions cover real popup hover cursor and Today open/close state. Final build/install result follows.

1.1.13 passed 242 tests, credential audits, and Windows/offscreen packaged smoke tests. Installer SHA-256: `8a24fd3e8fe17b08f184dec00e7b8e6661a5d6a6a972dc8f9b64c6f44eba0128`. Installed successfully (exit code 0), confirmed version 1.1.13, and reopened with sample friends enabled. This is the latest installed build; no publication or commit.

## Latest feature: friend details dialog, 1.1.12

Friend detailed figures (past-two-week hours, total hours, membership date when available) moved from the hover tooltip to a dark Qt `FriendDetails` dialog opened by double-clicking the friend's name strip. Context-menu arrows and row dragging remain as before; small Away/control hints are retained. Name hit testing accounts for scrolling and clipping. The demo also opens details on double-click rather than hover. Tests send actual double-click events to visible and scrolled friend name strips and verify dialog content/title. Build/install status follows.

1.1.12 passed 242 tests, credential audits, and Windows/offscreen packaged smoke tests. Installer SHA-256: `0b451a78432bbcc59879f10c9a314a49425567ff877e952e8cc4522eeae50b8b`. Installed successfully (exit code 0), confirmed version 1.1.12, and reopened with sample friends enabled. This is the latest installed build; no publication or commit.

## Latest feature: manual Today selection, 1.1.11

A chevron beside the Today program name opens the existing styled popup menu with Photoshop, Krita and Clip Studio Paint. Selection is available only while tracking is inactive; it changes the displayed history, persists `today_program`, and retitles a floating Today window. A manual choice survives inactive foreground ticks. As soon as active tracking resumes, automatic following takes over and the selector disables. The arrow is excluded from drag hit testing, retaining title/body docking behavior. The demo mirrors the selector (pause its simulated drawing session to choose other made-up program totals). Tests cover selected per-program history, automatic takeover, and selection rejection while active. Final build/install status follows.

1.1.11 passed the 240-test regression suite, plus a new targeted real-popup test verifying menu choices, selection, and drag hit testing (241 tests now in source). Credential audits and Windows/offscreen packaged smoke tests passed. Installer SHA-256: `a0d5adb5e8f1bdcf769f5e6f7b15876328f2ef15437a7ebbb96f1ba0effc7d24`. Installed successfully (exit code 0), confirmed version 1.1.11, and reopened with sample friends enabled. This is the latest installed build; no publication or commit.

## Latest color request: active username, 1.1.10

User now wants the username light green while actively tracking an art program. Online + live activity uses shared `name_drawing` (`#86e3a6`); Online without activity and Away use `name_online`. Invisible/Offline remain muted. Uses live `display_program`, not lingering server presence, so the username returns blue immediately when tracking stops. The small active-program caption remains stronger green. Demo now mirrors this, using green only alongside the actual program caption. This supersedes the earlier request for usernames to always remain blue while Online. Regression tests verify each supported active program and immediate blue return. Final build/install status follows.

1.1.10 passed 239 tests, credential audits, and Windows/offscreen packaged smoke tests. Additional transition assertions confirm Away remains blue and Invisible/Offline muted during tracking. Installer SHA-256: `4e3aa8cc18651c278952ad4452f501aab091bf29f27b57198a7287bb7ac0426a`. Installed successfully (exit code 0), confirmed version 1.1.10, and reopened with sample friends enabled. This is the latest installed build; no publication or commit.

## Latest change: active-program status caption, 1.1.9

While status is Online and the user is actively tracking a supported art program, the small caption beneath the username now shows that program (Photoshop, Krita, or Clip Studio Paint) in green. The username itself remains light blue. The caption returns immediately to Online when tracking stops, rather than using the friend-server presence linger interval. Away/Invisible/Offline keep their labels. `FriendsSync.display_program` tracks live UI state separately from the existing lingering `active_program` used for presence updates; header-only refresh avoids redrawing the friend list each tick. The demo mirrors this for its simulated Photoshop session. Regression tests cover each program and status transitions. Final build/install result follows.

1.1.9 passed 239 tests, credential audits, and Windows/offscreen packaged smoke tests. Installer SHA-256: `e6dfd9ecc22c91db2bfec1f1d37db3d8c13b65192af8bdb1c523b481c7bcb05c`. Installed successfully (exit code 0), confirmed version 1.1.9, and reopened with sample friends enabled. This is the latest installed build; no publication or commit.

## Latest behavior change: floating overlap, 1.1.8

The user explicitly reversed the old floating swap/displacement behavior: undocked windows may freely overlap. Removed release-time swapping and displacement from the shared `Docking` path and deleted the obsolete resolver. Ordinary docking into the main window, edge snapping, connected movement and deliberate gap closure remain intact. Tests cover every floating block pair across both orientations, checking that source/target retain the overlapped positions and main block order is unchanged. This supersedes earlier chat requests that floating windows should exchange occupied slots. Final build/install result follows.

1.1.8 passed 238 tests, credential audits, and Windows/offscreen packaged smoke tests. Installer SHA-256: `2e7002df89765cde287e38fbbf0c9d65054a862048008442c9c636789094521f`. Installed successfully (exit code 0), confirmed version 1.1.8, and reopened with sample friends enabled. This is the latest installed build; no publication or commit.

## Latest adjustment: Today online blue, 1.1.7

Today program names now use the shared online-friend name blue, `name_online` (`#aebdfa`), while open/background/idle/paused. Active tracking remains `active_green`; closed remains muted. Transition tests and the local website demo were updated to the same color token. This supersedes the royal-blue choice recorded under 1.1.3. Final build/install status follows.

1.1.7 passed 237 tests, credential audits, and Windows/offscreen packaged smoke tests. Installer SHA-256: `23faf22743ecd7636fb18e88aff113a2ac934682653abf9ca9896ec3380eab38`. Installed successfully (exit code 0), confirmed version 1.1.7, and reopened with sample friends enabled. This is the latest installed build; no publication or commit.

## Latest correction: username status colors, 1.1.6

User clarified that the header username must remain blue for Online and Away; green activity coloring is for the Today panel's program, not the user's name. `FriendsSync.header_name_color()` is now independent of art-program activity, while Invisible/Offline remain muted. Google connection fallback also uses light blue, preventing a green flash before Friends initializes. Friend-list In App names and Today program colors retain their green activity styling. The website demo already has the requested blue username behavior. Tests check Online/Away while Krita is active and Invisible muted. Build/install result follows.

1.1.6 passed 237 tests, credential audits, and packaged Windows/offscreen smoke tests. Installer SHA-256: `1d76fa0541b7b0a49e5245b29337f6bedc593f7e7dc225ffeb333593dc19bee2`. Installed successfully (exit code 0), confirmed version 1.1.6, and reopened with sample friends enabled. This is the latest installed build; nothing published or committed.

## Latest change: undocking position continuity, 1.1.5

Reported teleporting while moving modules. Reproduced cause: a docked title drag replaced the true pointer offset with the fixed `(30, 12)` when becoming floating, shifting the module sideways by about 120 pixels for a center-title grab. `Docking.press` now captures the real block-relative grab offset and `drag` preserves it across the docked-to-floating transition. Existing swaps/group/gap behavior remains unchanged.

Regression coverage checks every block in portrait and landscape: the grabbed point stays under the cursor immediately after undocking, and the next one-pixel pointer movement moves the module one pixel. Existing position-persistence and stationary-neighbor tests now assert actual original positions instead of the removed fixed offset. A clarification about whether other teleporting occurs during movement/release was asked but not answered at this point; do not assume all possible jumps share this cause. Final build status follows after validation.

1.1.5 passed 237 tests, both credential audits, and Windows/offscreen packaged smoke tests. Installer SHA-256: `21504136408e9c73f0db4d7bff50fcdc3c30338fc2b748d3f6bb5e6b9ba98335`. Installed with exit code 0, confirmed product version 1.1.5, and reopened with sample friends enabled. This is now the latest local installation; no publication or commit was made.

## Latest change: drag highlighting, 1.1.4

The blue drag outline was gated on docked reordering (`kind == title`), excluding floating-panel title and group drags. `BlockDrag` now marks every dragged block after the movement threshold. Shared release/cancellation cleanup removes the outline and restores the cursor. A real Qt mouse-event test covers every block (Today, Friends, Graph, Calendar, Stats) in both orientations, checking the outline mid-drag and after release.

236 tests, both credential audits, and packaged Windows/offscreen smoke tests passed. Installer SHA-256: `fba3fd492827d09cbaa2ad9e9b130764394caef10bff8bcce62e878a6e3bb3ff`. Installed 1.1.4 successfully (exit code 0), confirmed its product version, and reopened with sample friends enabled. This is the latest installed build; older build descriptions below are history. Nothing was published or committed.

## Latest installed build: 1.1.3, Today program colors

Today program name is royal blue (`calendar_blue`) while that program is open, green (`active_green`) while it is actively being tracked, and muted when closed. Background/minimized, idle, and paused programs stay blue. `tracker.running_applications()` uses a Windows process snapshot; foreground detection is also sufficient evidence that a program is open. No extra dependencies. The same Today widget paints these states in docked/floating layouts. The demo's simulated Today title also uses blue/green; website changes remain local.

235 tests passed, including open/background, active, idle, paused, and closed states. Both credential audits and Windows/offscreen packaged smoke tests passed. Installer SHA-256: `c1cd8446635ed64dc17acb1cba3d44b1ac8a3222701aa0cc87244e80beac63d0`. Installed 1.1.3 with exit code 0 and reopened with sample friends enabled. This supersedes the older local build statuses below; nothing was published or committed.

## Latest continuation: smooth snapping

The user reported that the website demo snaps more smoothly than the installed app. The Qt snap algorithm now matches the demo's independent-axis behavior: 20-pixel edge capture, 8-pixel corner/internal-edge alignment, and a 6-pixel release margin. Panels slide freely along touched edges rather than jumping between distant top/bottom anchors. Held snap state resets on a new drag, docking preview, cancellation, and release. Connected-group movement rules are preserved.

Validation includes continuous pointer trajectories, snap retention/release, top/bottom internal anchors, and actual Qt floating drag/release in both orientations. The reproduced trajectory's largest jump changed from 110 pixels to 1 pixel for one-pixel pointer steps. The 1.1.2 release passed 234 tests, both credential audits, and Windows/offscreen packaged smoke tests. SHA-256 of installer: `878e26458d6c531276724ac215fe53d22021245c4b5df50166f9b49a050f1367`. Installed 1.1.2 successfully (exit code 0) and relaunched with `PSFOCUS_SAMPLE_FRIENDS=1` for user testing. This supersedes the 1.1.1 local installation described below. No public release or website deployment was made.

## Current task and outcome

Claude's latest request was: make Today automatically follow the active art program and remove the program checkboxes from Settings. This is a Qt application now; the older Tk docking work in earlier chat history is obsolete.

- One `TodayPanel` has the stable docking key `today`. Its title and program-specific figures follow Photoshop, Krita, or Clip Studio Paint in the foreground. With no supported program in front, it keeps the last program.
- Switching programs keeps the same widget and floating window. The floating caption changes too. All supported programs remain tracked; changing the panel never filters history or combined totals.
- Legacy block orders and floating program panels migrate to `today`; the old program visibility settings are removed. Existing `today` placement wins over legacy placements.
- The Settings program checkbox row is removed. The website demo now also has only one Today panel and no program checkbox row. Its made-up session uses Photoshop; the browser cannot detect desktop programs.
- Sample friends retain Claude's newly added membership dates.
- README describes the automatic panel. Version is 1.1.1 for the local build; public publication is not authorized by this task.

## Validation

- Full unittest suite: 229 tests passed.
- New test covers the same floating Today widget switching through all three programs, program-specific totals, its caption, and combined history.
- `node --check docs/assets/demo/demo.js` passed. Interactive browser testing was not run (Playwright is not installed).
- Release builder audits credentials in the executable and runtime directory, runs Windows and offscreen packaged-app smoke tests, builds the installer and checksums, then removes intermediate build files.

## Operational preferences

- The user runs the installed app at `%LOCALAPPDATA%\Programs\PS Focus\PS Focus.exe`. Meaningful changes need a rebuild, silent reinstall and relaunch, as recorded in Claude's project memory.
- Build: `python tools/build_release.py`. Install the resulting `dist/installer/PS-Focus-Setup-1.1.1.exe` with `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`. The installer requests graceful exit of the running app; do not force-kill it preemptively.
- Only the current installer and checksums should remain as build outputs. Preserve credentials, history and recovery files. Never use the real uninstaller to test cleanup.
- Source runs use preview data by default. GUI tests must isolate data and disable network/tray behavior.
- Do not publish releases, push the site or redeploy the update endpoint without user authorization. Public release instructions are in Claude's `memory/public-release-setup.md`.

## Working tree and provenance

The starting working tree already contained Claude's changes in `app_config.py`, `qt/app.py`, `qt/docking.py`, `qt/friends_sync.py`, `qt/settings_page.py`, `qt/today_panel.py`, `test_qt_docking.py`, `test_qt_settings.py`, and the demo. Preserve them. Nothing has been committed or pushed by this continuation.

Claude context is at `C:\Users\elihu\.claude\projects\c--Users-elihu-PSFocus\memory\MEMORY.md`. The last task is recorded in session `fbdc11e2-a542-4f77-9743-dd09c72f8c37.jsonl`; it stopped at the website demo update due to the session limit. Read only relevant task text; do not expose credentials or unrelated session contents.

## Final build/install status

Sample-friends follow-up: enabled `show_friends` in the installed app's local settings and relaunched the installed 1.1.1 executable with `PSFOCUS_SAMPLE_FRIENDS=1` for this launch only. Built-in samples cover drawing, Online, Away, and Offline; they are not added to the server. A normal launch without that environment flag removes the samples. This mode requires the existing signed-in Friends state to load.

Follow-up: corrected the website demo header name to remain the app's light blue (`#aebdfa`) for Online/Away. The demo's simulated drawing clock no longer overrides that name with green while its status label still says Online. Invisible/Offline remain muted. Website edits are local, not published; this change does not require rebuilding the desktop app.

Release 1.1.1 built successfully, including both credential audits and Windows/offscreen executable smoke tests. Installer SHA-256: `7a12422c9fb42d0a1faa55eab5bde446a40f889df2343be2ce2a018578fda028`.

Silent installation completed with exit code 0. The installed executable reports product version 1.1.1 and was relaunched. Final artifacts are `dist/installer/PS-Focus-Setup-1.1.1.exe` and `dist/installer/PS-Focus-1.1.1-SHA256SUMS.txt`.

No code or website changes were published. A future public release should follow the release instructions rather than treating this local installation as a public release. The live art-program switching test used mocked foreground programs, not actual Photoshop/Krita/CSP launches. Website demo syntax was checked, but interactive browser verification remains a validation limitation.


## Claude Code log

### 14 October 2026: "Best day" request

The owner asked for a "Best day" line in Stats showing the day with the most focus time. It already exists as "Longest session" (`stat_lines.py`, from `longest_session`), and the existing "Best day" row is the best weekday on average. The owner chose to change nothing, so no code changed. Next: nothing. Open question: none.
