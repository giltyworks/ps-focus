# PS Focus

A Windows desktop app that counts time while Photoshop, Krita, or Clip Studio Paint owns the visible foreground window. All three are always counted; ticking one in Settings shows its panel, and a program's panel switches on by itself the first time it is used unless the user has already shown or hidden it. PS Focus stores totals locally, displays day/week/month charts, and can sync preferences to a private Google Drive app-data folder

- **Website:** https://giltyworks.github.io/ps-focus/ (its files are in `docs/`)
- **Download:** https://github.com/giltyworks/ps-focus/releases/latest

## Install

Run `PS-Focus-Setup-<version>.exe`. It installs PS Focus for the current Windows user in `%LOCALAPPDATA%\Programs\PS Focus` without administrator rights. It adds a Start menu shortcut (and a desktop one if ticked) and lists PS Focus under **Settings > Apps > Installed apps**. The installer shows the terms of use and places `Terms of Use.txt`, `Privacy Policy.txt`, and `Third-Party Notices.txt` beside the app. Running a newer installer upgrades in place and keeps all data. The policies themselves are [TERMS.md](TERMS.md) and [PRIVACY.md](PRIVACY.md).

## Run from source

Requires Windows and Python 3.14. PS Focus is built with Qt (PySide6). Install the dependencies first:

```powershell
py -m pip install -r requirements.txt
```

From this folder run:

```powershell
py -m qt
```

Run from source, PS Focus works on a copy of your real history and settings in `%APPDATA%\PS Focus Qt Preview`, made afresh at each start, so a copy under development never counts the same seconds into the installed app's history; its Google backups use separate file names in Drive. Add `--real-data` to use `%APPDATA%\PS Focus` itself. The installed app stores its activity data and preferences under `%APPDATA%\PS Focus`; data from earlier releases is carried over on first launch

Only one copy of PS Focus runs at a time for each Windows user, because two would each count the same seconds into the one history. Starting it again brings up the window of the copy already running. **Exit**, in the tray menu and on the Settings page, takes a final backup and closes the app; closing the window only hides it in the tray. Windows signing out or shutting down closes it the same way as Exit. The installer asks a running copy to close itself through a named signal before replacing its files, which takes about a second; versions before 1.0.4 are closed by Windows' Restart Manager instead. While the window is hidden or minimized the app keeps counting time but redraws nothing

## Google sign-in

Google sign-in is optional. Packaged releases include PS Focus's Google Desktop app client configuration, so users can choose **Connect Google** without downloading or creating a credentials file. Each user signs in to their own account and approves access; no developer account tokens are bundled.

For development or to supply a different client:

- Create an OAuth client ID of type **Desktop app** in Google Cloud Console and enable the Google Drive API
- Download the client JSON and place it in this folder as `credentials.json`
- An external `credentials.json` in `%APPDATA%\PS Focus` or beside the executable overrides the bundled configuration. Only Desktop app clients are accepted; Google sign-in uses PKCE (S256).
- In PS Focus, choose **Connect Google**. The browser requests access to PS Focus's private Drive app-data area and your Google account email, which PS Focus displays in the header
- Double-click the name in the header to replace the email with a name of your choice. Each Google account keeps its own name on this PC, so switching accounts shows that account's name, or its email if none was chosen

The app uploads settings when connected and when preferences change. Activity backups are saved in `%APPDATA%\PS Focus\backups` and `Documents\PS Focus Backups`, with another copy in `OneDrive\PS Focus Backups` when OneDrive is available. Each folder contains dated snapshots and an easy-to-find `activity-latest.sqlite3` file. A snapshot is written at launch, then every 15 minutes and at exit whenever activity or ratings have changed since the last one, so idle hours add no files. Each folder keeps its 10 newest snapshots, for recovering from a damaged history file, and the newest snapshot of each of the last 30 days, for undoing a mistake noticed later: about 40 files. After a break from drawing no new snapshots are made, so the 10 newest are kept however old they are. Older snapshots, and all but the 3 newest damaged files set aside during a restore, are deleted when a new snapshot is written. A year of regular use makes each snapshot about 160 KB, so all three folders together hold about 20 MB. Choose **Back up now** in Settings to write snapshots immediately, changed or not. When Google is connected, the latest activity database is also backed up in the private Drive app-data area. If the local database is damaged, PS Focus restores the newest valid local snapshot; on an empty installation, connecting Google restores its activity backup instead of overwriting it. When both the PC and Google Drive hold activity, PS Focus merges any history written by another installation into the local database, keeping the larger total for each hour, and then uploads the result automatically. OAuth tokens are stored in the current Windows user's `%APPDATA%\PS Focus` folder, encrypted with Windows data protection so only that Windows account can read them; a token copied to another PC or account will not work and the app asks to reconnect. If you previously connected before account display was added, choose **Reconnect** and approve the additional email permission

## Windows startup

The **Start with Windows** setting adds or removes PS Focus in the current user's Windows Run registry key. A new installation turns on both **Start with Windows** and **Start minimized** the first time it runs. **Start minimized** takes effect when launched by that entry. Each time a packaged build starts with the setting on, it points the entry at its own location, so a moved or reinstalled copy keeps starting with Windows. A copy run from source never changes the entry: the two settings are greyed out there. Preferences, including the chart period last viewed, are saved locally as they change and restored on later launches

## Levels

Lifetime tracked time across all programs sets a level from 1 to 99, shown beside **Level** in the top left. The hours each level needs are fixed in `app_config.py` (`LEVEL_ANCHORS`) and cannot be changed from the settings file. Reaching a new level plays a trumpet fanfare with fireworks over the window; with the window hidden or minimized only the sound plays, and **Disable fanfare sound** in Settings silences it.

## Stats

The Stats module lists each figure as a label on the left and its value in a column on the right: this week's total, the 7- and 30-day daily averages with their change against the period before, the best weekday, the longest session, the best start time once a day has been rated, and a count of the sessions in the month or year the calendar shows. When this week ranks in your top 10, 25 or 50 percent of weeks, a gold, silver or bronze medal appears beside its total with the percentile underneath. The week so far is compared with the same days of each of the past 52 weeks, from Monday up to today, so a week in progress is not measured against finished ones and a busy stretch more than a year ago stops setting the bar. No rank is shown until there are four weeks of history (`ActivityStore.week_rank`).

## Uninstall

Choose PS Focus under **Settings > Apps > Installed apps** and then **Uninstall**. This runs the app itself as `PS Focus.exe --uninstall`, which opens a dialog; there is no separate uninstaller program. It runs as the current user without administrator rights, because everything it removes belongs to that user.

**Uninstall** closes any running PS Focus and removes the Windows startup entry, the Installed apps entry, the shortcuts and the installed documents. It keeps activity history, settings, and backups. `PS Focus.exe` and its `_internal` folder cannot be deleted while the uninstall runs, so a helper removes them, and then the installation folder if it is empty, as soon as the dialog has closed. Ticking **Also delete all user data** shows a warning and, once accepted, also signs out of Google and deletes `%APPDATA%\PS Focus` and the `PS Focus Backups` folders in Documents and OneDrive. The activity backup stored in Google Drive's private app-data area is never deleted.

Run from source (`py -m qt --uninstall`), the dialog removes the startup entry and, if asked, the data, but no program files.

## Feedback

Feedback unlocks after two hours of tracked time across all art applications. From then on the level in the top left, which stays blurred until feedback has been submitted, opens the feedback dialog when clicked, and **Got feedback?** appears in Settings to open it again later. Submissions are queued in `%APPDATA%\PS Focus\feedback-outbox.json` and posted to a Google Apps Script web app, which emails everything received in each six-hour period as one message. To set it up:

- Create a project at script.google.com while signed in to the account that should send the email, and paste in `feedback_endpoint/Code.gs`
- Run the `setup` function once and approve the permissions it requests
- Choose **Deploy > New deployment > Web app**, with **Execute as** set to **Me** and **Who has access** set to **Anyone**
- Copy the web app URL into `FEEDBACK_ENDPOINT_URL` in `feedback.py`, then rebuild

Until a URL is set, feedback stays in the outbox and is delivered once one is configured. Queued feedback is retried at launch and every 15 minutes

The endpoint is public, so it holds at most 100 submissions between digests. Anything beyond that is refused and stays in the sender's outbox until the next digest frees space. After changing `Code.gs`, paste the new version into the Apps Script project and choose **Deploy > Manage deployments > Edit > New version** so the existing web app URL keeps working

## Updates

The Settings page shows the installed version at its top left. Once a day, and at launch, PS Focus asks the feedback web app for the latest published version. If a newer version exists, that text changes to **Get version x.y.z**, which opens the download page when clicked, and a tray notification appears once. PS Focus never downloads or installs anything itself. It opens a link only if it is an `https` address on the public site (`giltyworks.github.io`) or in the public repository (`github.com/giltyworks/ps-focus/`), whatever the web app returns. To move downloads elsewhere, first publish a release that adds the new address in `update_check.py`. To announce a release, set `LATEST_VERSION` and `DOWNLOAD_URL` at the top of `feedback_endpoint/Code.gs`, then deploy a new version of the web app. While `DOWNLOAD_URL` is empty, no update is offered.

## Privacy

See [PRIVACY.md](PRIVACY.md) for the full policy. The tracker checks the foreground process once per second and records only elapsed seconds grouped by local date and hour. Activity backups contain this database, including ratings and session starts. It does not save document names, window titles, screenshots, or file contents. Feedback contains only the star rating, the message, and the local time it was submitted

## Source layout

- `qt/`: the app, built with Qt. `app.py` runs it: the tracking loop, the tray icon, Settings, backups, feedback, updates and level-ups. `window.py` lays the blocks out by hand, in portrait or landscape. Each block paints itself: `today_panel.py` (a program's panel), `chart.py`, `calendar_module.py`, `stats_module.py`, with what they share in `module.py` (the name strip, buttons and glass). `header.py`, `settings_page.py`, `day_overview.py`, `feedback_dialog.py` and `uninstall_window.py` are the other parts of the interface; `theme.py` holds the colours, fonts and text measuring, laid out by Windows' own font metrics
- `qt/docking.py` and `qt/block_drag.py`: floating panels. A block's title strip puts it in a new order, or out of the window into a window of its own; anything else moves the window or panel with everything snapped to it. Windows move together in one step, and see-through glass is worked out per group of snapped windows
- `qt/google_sync.py`: Google sign-in, settings upload and activity backups for the app, run on background threads with the results handled on the interface's own
- `qt/preview.py`: the copy of your data a run from source works on
- `app_config.py`: paths, constants, colours, and default settings
- `tracker.py`: activity database and foreground-window detection. The database keeps a write-ahead log, so recording each second is a short append; backups are plain single files
- `stat_lines.py`: the Stats module's figures
- `google_drive.py`, `feedback.py`, `update_check.py`: Google Drive sync, the feedback outbox, and the daily check for a newer version
- `web.py`: HTTPS through Windows' own WinHTTP, so the app needs no copy of OpenSSL
- `windows_startup.py`: the Windows startup entry, taskbar identity, dark title bar, and the single-running-copy claim
- `uninstall.py`: what the uninstall mode removes, run as `PS Focus.exe --uninstall`
- `unpack_cleanup.py`: removes the temporary `_MEI…` folders that versions before 1.1 left behind when ended by force; they unpacked themselves there at each launch. It touches only folders that hold its own icon, and a folder in use is left whole
- `installer/PS Focus.iss`: the Inno Setup installer script
- `tools/`: release build, credential check, checksums, licence notices, executable version information, disk-use measuring, and the website's screenshots (`site_screenshots.py`, the real app on sample data)
- `assets/sounds/make_celebration.py`: generates `celebration.wav`; rerun it and rebuild after changing the sound

## Test

```powershell
py -m unittest discover -v
```

## Release build

To publish a version:

1. Raise `APP_VERSION` in `app_config.py`.
2. Build the installer, either with the **Build installer** workflow on GitHub (started by hand from the Actions tab, or by pushing a `v1.2.3` tag), which is how releases are made, or locally with `py tools/build_release.py`. It needs PyInstaller and Inno Setup 6 (`winget install --id JRSoftware.InnoSetup -e --scope user`). It runs the tests, writes the third-party licence notices, and builds the app as a folder, `dist/PS Focus` (the program and its `_internal` runtime), stamping the version into its file properties. It then runs the credential checks, starts the built app twice with throwaway data to check that it draws everything, switches layouts and Settings, sets up Google sign-in's local listener, and closes, builds `dist/installer/PS-Focus-Setup-<version>.exe`, and writes `dist/installer/PS-Focus-<version>-SHA256SUMS.txt`. Finally it tidies up, leaving the installer and its checksum as the only build files. To try a build, install it; a loose packaged copy would point the Windows startup entry at itself.
3. Publish the installer and its checksum file as a GitHub release, then download the installer back and compare its checksum.
4. Set `LATEST_VERSION` and `DOWNLOAD_URL` in `feedback_endpoint/Code.gs`, then deploy a new web app version so existing installations are told about it.

The executable is built without UPX compression, because UPX-packed files are flagged by antivirus far more often. To keep it small, it is built with Qt's essential modules only (`PySide6_Essentials`), and parts of Qt and Python the app never uses are left out: OpenGL, SVG, Qt's networking and translations, OpenSSL, and some archive formats; see `excludes` and `needed_file` in `PS Focus.spec` before using one of them. The installer has Windows compress the program files once installed, which roughly halves the space they take. Where PySide6 was installed without its package details, the licence notices are read from its wheels: `py -m pip download --no-deps --dest build/qt-preview/wheels PySide6==6.11.2 PySide6_Essentials==6.11.2 shiboken6==6.11.2`.

## Release security

The steps below are what `tools/build_release.py` runs; they are listed here to explain each check.

Build with `py -m PyInstaller --noconfirm --clean "PS Focus.spec"`. Supply a local Desktop app `credentials.json` or the `PSFOCUS_OAUTH_CREDENTIALS` environment variable. The build generates only the client ID and client secret in `assets/oauth/desktop-client.json` inside the executable. This Desktop OAuth configuration is extractable public-client configuration, not a confidential server credential. Never supply a Web client or service account. A build without configuration is for development and cannot provide Google sign-in.

Before distribution, run `py tools/check_credentials.py --archive "dist/PS Focus/PS Focus.exe" --verify-qt-binaries` and `py tools/check_credentials.py --directory "dist/PS Focus/_internal" --verify-qt-binaries`. The release scanner permits only the minimal Desktop configuration at that exact archive path; source scanning continues to reject OAuth secrets. User tokens, environment files, private/signing keys, and server credentials remain prohibited. Build directories and executables remain excluded from Git. For GitHub Actions builds, configure the repository secret `PSFOCUS_OAUTH_CREDENTIALS` with the Desktop client JSON.

After the credential check, write the checksum for the installer, the one file that is published:

```powershell
py tools/write_checksums.py "dist/installer/PS-Focus-Setup-1.0.3.exe"
```

This writes `dist/SHA256SUMS.txt`. Rerun it after every rebuild, since any change to a file changes its checksum. Post the file's contents beside each download, for example in the release notes. Downloaders can confirm their copy matches by running `Get-FileHash "$HOME\Downloads\PS-Focus-Setup-<version>.exe"` in PowerShell and comparing the `Hash` value with the published line, ignoring capitalisation. Always give the instruction with the full path to the Downloads folder: a bare file name only works if PowerShell happens to be open in that folder. A mismatch means the file is incomplete or is not the build you published. Checksums do not remove the Windows SmartScreen warning; only code signing does that.

The Google sign-in app is published to production in Google Auth Platform for External users, with only the `drive.appdata`, `userinfo.email`, and `openid` scopes. Its branding links point at the public site, `https://giltyworks.github.io/ps-focus/`, so keep that repository name and its `/privacy/` and `/terms/` pages in place. Adding a scope or a logo triggers a Google review. After changing `PRIVACY.md` or `TERMS.md`, run `py tools/sync_site.py` and push the site repository.

Binaries committed before October 2026 contained OAuth Desktop credentials, including an older client. Those binaries were purged from this repository's history and the older clients were deleted in Google Cloud.

## Licence

PS Focus is free software under the GNU General Public License, version 3; see [LICENSE](LICENSE). The PS Focus name and logo are not covered by it: give a changed version you share its own name and logo ([TERMS.md](TERMS.md), section 2).
