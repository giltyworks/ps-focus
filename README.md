# PS Focus

A Windows desktop app that counts time while Photoshop, Krita, or Clip Studio Paint owns the visible foreground window. All three are always counted; ticking one in Settings shows its panel, and a program's panel switches on by itself the first time it is used unless the user has already shown or hidden it. PS Focus stores totals locally, displays day/week/month charts, and can sync preferences to a private Google Drive app-data folder

- **Website:** https://giltyworks.github.io/ps-focus/ (its files are in `docs/`)
- **Download:** https://github.com/giltyworks/ps-focus/releases/latest

## Install

Run `PS-Focus-Setup-<version>.exe`. It installs PS Focus for the current Windows user in `%LOCALAPPDATA%\Programs\PS Focus` without administrator rights. It adds a Start menu shortcut (and a desktop one if ticked) and lists PS Focus under **Settings > Apps > Installed apps**. The installer shows the terms of use and places `Terms of Use.txt`, `Privacy Policy.txt`, and `Third-Party Notices.txt` beside the app. Running a newer installer upgrades in place and keeps all data. The policies themselves are [TERMS.md](TERMS.md) and [PRIVACY.md](PRIVACY.md).

## Run from source

Requires Windows and Python 3.10 or newer. Install the Python dependencies first:

```powershell
py -m pip install -r requirements.txt
```

From this folder run:

```powershell
py main.py
```

Activity data and preferences are stored under `%APPDATA%\PS Focus`. Data from earlier releases is migrated on first launch

Only one copy of PS Focus runs at a time for each Windows user, because two would each count the same seconds into the one history. Starting it again brings up the window of the copy already running. **Exit**, in the tray menu and on the Settings page, takes a final backup and closes the app; closing the window only hides it in the tray. Windows signing out or shutting down closes it the same way as Exit. The installer asks a running copy to close itself through a named signal before replacing its files, which takes about a second; closed by Windows' Restart Manager instead, as versions before 1.0.4 are, the launcher at the front of the packaged app waits about 30 seconds to be ended by force. While the window is hidden or minimized the app keeps counting time but redraws nothing

## Google sign-in

Google sign-in is optional. Packaged releases include PS Focus's Google Desktop app client configuration, so users can choose **Connect Google** without downloading or creating a credentials file. Each user signs in to their own account and approves access; no developer account tokens are bundled.

For development or to supply a different client:

- Create an OAuth client ID of type **Desktop app** in Google Cloud Console and enable the Google Drive API
- Download the client JSON and place it beside `main.py` as `credentials.json`
- An external `credentials.json` in `%APPDATA%\PS Focus` or beside the executable overrides the bundled configuration. Only Desktop app clients are accepted; Google sign-in uses PKCE (S256).
- In PS Focus, choose **Connect Google**. The browser requests access to PS Focus's private Drive app-data area and your Google account email, which PS Focus displays in the header
- Double-click the name in the header to replace the email with a name of your choice. Each Google account keeps its own name on this PC, so switching accounts shows that account's name, or its email if none was chosen

The app uploads settings when connected and when preferences change. Activity backups are saved in `%APPDATA%\PS Focus\backups` and `Documents\PS Focus Backups`, with another copy in `OneDrive\PS Focus Backups` when OneDrive is available. Each folder contains dated snapshots and an easy-to-find `activity-latest.sqlite3` file. A snapshot is written at launch, then every 15 minutes and at exit whenever activity or ratings have changed since the last one, so idle hours add no files. Each folder keeps its 10 newest snapshots, for recovering from a damaged history file, and the newest snapshot of each of the last 30 days, for undoing a mistake noticed later: about 40 files. After a break from drawing no new snapshots are made, so the 10 newest are kept however old they are. Older snapshots, and all but the 3 newest damaged files set aside during a restore, are deleted when a new snapshot is written. A year of regular use makes each snapshot about 160 KB, so all three folders together hold about 20 MB. Choose **Back up now** in Settings to write snapshots immediately, changed or not. When Google is connected, the latest activity database is also backed up in the private Drive app-data area. If the local database is damaged, PS Focus restores the newest valid local snapshot; on an empty installation, connecting Google restores its activity backup instead of overwriting it. When both the PC and Google Drive hold activity, PS Focus merges any history written by another installation into the local database, keeping the larger total for each hour, and then uploads the result automatically. OAuth tokens are stored in the current Windows user's `%APPDATA%\PS Focus` folder, encrypted with Windows data protection so only that Windows account can read them; a token copied to another PC or account will not work and the app asks to reconnect. If you previously connected before account display was added, choose **Reconnect** and approve the additional email permission

## Windows startup

The **Start with Windows** setting adds or removes PS Focus in the current user's Windows Run registry key. A new installation turns on both **Start with Windows** and **Start minimized** the first time it runs. **Start minimized** takes effect when launched by that entry. Each time a packaged build starts with the setting on, it points the entry at its own location, so a moved or reinstalled copy keeps starting with Windows. Running from source never changes the entry unless the setting is toggled. Preferences, including the chart period last viewed, are saved locally as they change and restored on later launches

## Levels

Lifetime tracked time across all programs sets a level from 1 to 99, shown beside **Level** in the top left. The hours each level needs are fixed in `app_config.py` (`LEVEL_ANCHORS`) and cannot be changed from the settings file. Reaching a new level plays a trumpet fanfare with fireworks over the window; with the window hidden or minimized only the sound plays, and **Disable fanfare sound** in Settings silences it. To preview the celebrations without touching real data, run:

```powershell
py tools/simulate_level_ups.py 15
```

## Stats

The Stats module lists each figure as a label on the left and its value in a column on the right: this week's total, the 7- and 30-day daily averages with their change against the period before, the best weekday, the longest session, the best start time once a day has been rated, and a count of the sessions in the month or year the calendar shows. When this week ranks in your top 10, 25 or 50 percent of weeks, a gold, silver or bronze medal appears beside its total with the percentile underneath. The week so far is compared with the same days of each of the past 52 weeks, from Monday up to today, so a week in progress is not measured against finished ones and a busy stretch more than a year ago stops setting the bar. No rank is shown until there are four weeks of history (`ActivityStore.week_rank`).

## Uninstall

Choose PS Focus under **Settings > Apps > Installed apps** and then **Uninstall**. This runs the app itself as `PS Focus.exe --uninstall`, which opens a dialog; there is no separate uninstaller program. It runs as the current user without administrator rights, because everything it removes belongs to that user.

**Uninstall** closes any running PS Focus and removes the Windows startup entry, the Installed apps entry, the shortcuts, the installed documents, and the temporary folder the closed app had unpacked itself into. It keeps activity history, settings, and backups. `PS Focus.exe` cannot delete itself while it is running, so a helper removes it, and then the installation folder if it is empty, as soon as the dialog has closed. Ticking **Also delete all user data** shows a warning and, once accepted, also signs out of Google and deletes `%APPDATA%\PS Focus` and the `PS Focus Backups` folders in Documents and OneDrive. The activity backup stored in Google Drive's private app-data area is never deleted.

Run from source (`py main.py --uninstall`), the dialog removes the startup entry and, if asked, the data, but no program files.

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

- `main.py`: the application window, tracking loop, header, program panels, and tray icon
- `ui_chart.py`, `ui_calendar.py`, `ui_modules.py`, `ui_settings.py`, `ui_google.py`, `ui_backup.py`, `ui_feedback.py`, `ui_celebration.py`: one area of the window each, as mixins of the main application class
- `app_config.py`: paths, constants, colours, and default settings
- `rendering.py`: Pillow drawing of the level badge and line chart
- `windows_startup.py`: the Windows startup entry, taskbar identity, and the single-running-copy claim
- `tracker.py`: activity database and foreground-window detection
- `google_drive.py`, `feedback.py`: Google sign-in and Drive sync, and the feedback outbox
- `uninstall.py`: the uninstall mode, run as `PS Focus.exe --uninstall`
- `unpack_cleanup.py`: removes the temporary folders left by runs that were ended by force. The packaged app unpacks itself into a `_MEI…` folder in the temporary folder at each launch, about 36 MB, and its launcher deletes it on exit; a run ended by the uninstaller, Task Manager, a crash, or a power cut leaves it behind. At each launch, and when uninstalling, the app deletes those folders. It touches only folders that hold its own icon, and it starts by deleting the Python library inside, which Windows refuses while any running copy has it loaded, so a folder in use is left whole. Do not test for use by renaming the folder: Windows allows that while it is in use
- `ui_header.py`: the header row, drawn on one canvas
- `widgets.py`: the rounded button, and text and buttons drawn on a canvas. Tk repaints every widget separately while the window is resized, and drawn text and frames that stretch with the window cost the most. So each panel and module is one canvas rather than many labels and frames, the calendar and stats are shown as a single picture taken from a hidden canvas (`drawing_surface` and `show_drawing`, which need Tk 9), and the pages do not stretch. Add to a canvas rather than adding widgets, and compare screenshots before and after any layout change
- `update_check.py`, `ui_updates.py`: the daily check for a newer version and the version line in Settings
- `installer/PS Focus.iss`: the Inno Setup installer script
- `tools/`: release build, credential check, checksums, and executable version information
- `tools/simulate_level_ups.py`: a preview tool that plays the level-up celebrations against a throwaway data folder; not part of the app
- `assets/sounds/make_celebration.py`: generates `celebration.wav`; rerun it and rebuild after changing the sound

## Test

```powershell
py -m unittest discover -v
```

## Release build

To publish a version:

1. Raise `APP_VERSION` in `app_config.py`.
2. Close PS Focus and run `py tools/build_release.py`. It needs PyInstaller and Inno Setup 6 (`winget install --id JRSoftware.InnoSetup -e --scope user`). It runs the tests and builds `dist/PS Focus.exe`, stamping the version into its file properties. It then runs the credential check, generates the third-party licence notices, builds `dist/installer/PS-Focus-Setup-<version>.exe`, and writes `dist/installer/PS-Focus-<version>-SHA256SUMS.txt`. Finally it tidies up, leaving the installer and its checksum as the only build files: it deletes `dist/PS Focus.exe`, which is now inside the installer, the installers of earlier versions, and the `build` folder, which is only a cache and holds a copy of the sign-in client configuration. To try a build, install it; a loose packaged copy would point the Windows startup entry at itself.
3. Upload the installer and publish the checksum lines beside it.
4. Set `LATEST_VERSION` and `DOWNLOAD_URL` in `feedback_endpoint/Code.gs`, then deploy a new web app version so existing installations are told about it.

The executable is built without UPX compression, because UPX-packed files are flagged by antivirus far more often. Parts of Pillow the app never uses, such as its AVIF and WebP decoders, are left out to keep it small; see `excludes` in `PS Focus.spec` before using a new Pillow feature.

## Release security

The steps below are what `tools/build_release.py` runs; they are listed here to explain each check.

Build with `py -m PyInstaller --noconfirm "PS Focus.spec"`. Supply a local Desktop app `credentials.json` or the `PSFOCUS_OAUTH_CREDENTIALS` environment variable. The build generates only the client ID and client secret in `assets/oauth/desktop-client.json` inside the executable. This Desktop OAuth configuration is extractable public-client configuration, not a confidential server credential. Never supply a Web client or service account. A build without configuration is for development and cannot provide Google sign-in.

Before distribution, run `py tools/check_credentials.py --archive "dist/PS Focus.exe"`. The release scanner permits only the minimal Desktop configuration at that exact archive path; source scanning continues to reject OAuth secrets. User tokens, environment files, private/signing keys, and server credentials remain prohibited. Build directories and executables remain excluded from Git. For GitHub Actions builds, configure the repository secret `PSFOCUS_OAUTH_CREDENTIALS` with the Desktop client JSON.

After the credential check, write the checksum for the installer, the one file that is published:

```powershell
py tools/write_checksums.py "dist/installer/PS-Focus-Setup-1.0.3.exe"
```

This writes `dist/SHA256SUMS.txt`. Rerun it after every rebuild, since any change to a file changes its checksum. Post the file's contents beside each download, for example in the release notes. Downloaders can confirm their copy matches by running `Get-FileHash "$HOME\Downloads\PS-Focus-Setup-<version>.exe"` in PowerShell and comparing the `Hash` value with the published line, ignoring capitalisation. Always give the instruction with the full path to the Downloads folder: a bare file name only works if PowerShell happens to be open in that folder. A mismatch means the file is incomplete or is not the build you published. Checksums do not remove the Windows SmartScreen warning; only code signing does that.

The Google sign-in app is published to production in Google Auth Platform for External users, with only the `drive.appdata`, `userinfo.email`, and `openid` scopes. Its branding links point at the public site, `https://giltyworks.github.io/ps-focus/`, so keep that repository name and its `/privacy/` and `/terms/` pages in place. Adding a scope or a logo triggers a Google review. After changing `PRIVACY.md` or `TERMS.md`, run `py tools/sync_site.py` and push the site repository.

Binaries committed before October 2026 contained OAuth Desktop credentials, including an older client. Those binaries were purged from this repository's history and the older clients were deleted in Google Cloud.

## Licence

PS Focus is free software under the GNU General Public License, version 3; see [LICENSE](LICENSE). The PS Focus name and logo are not covered by it: give a changed version you share its own name and logo ([TERMS.md](TERMS.md), section 2).
