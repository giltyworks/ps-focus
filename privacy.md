---
title: Privacy Policy
permalink: /privacy/
---

# PS Focus Privacy Policy

Effective 2 October 2026

PS Focus is a free Windows app made by Giltyworks that records how long you spend working in Photoshop, Krita, and Clip Studio Paint. This policy explains what the app stores, where it goes, and how to remove it. Contact: giltyworks@gmail.com

## What PS Focus records on your PC

- **Activity time.** Once a second, PS Focus checks which program owns the window in front. If it is an art application you enabled, PS Focus adds the elapsed seconds to a total for that application, date, and hour. It does not record document names, window titles, keystrokes, screenshots, or file contents.
- **Ratings and session starts.** These are the daily productivity ratings you enter, and the time of day each day's tracking began.
- **Settings.** These include your preferences, the optional display name you type for your Google account, and a random identifier that tells your installations apart when merging backups.
- **Feedback waiting to be sent.** This holds feedback you submit, until it is delivered.

This information is stored in your Windows user folder at `%APPDATA%\PS Focus`. Backup copies of the activity database are stored in `Documents\PS Focus Backups` and, when OneDrive is set up, in `OneDrive\PS Focus Backups`. Each backup folder keeps a limited number of recent snapshots, and older ones are deleted automatically. If you use OneDrive, Microsoft syncs that folder under your own OneDrive account and terms.

## Google sign-in (optional)

If you choose **Connect Google**, PS Focus asks Google for:

- **Access to PS Focus's own hidden app-data folder in your Google Drive** (`drive.appdata`). PS Focus stores your settings and a backup of your activity database there. It cannot see or change any other files in your Drive.
- **Your Google account email address**, which PS Focus shows in the app so you know which account is connected.

This information travels directly between your PC and Google. Giltyworks does not receive it and cannot access your Drive. The sign-in token is kept on your PC, encrypted so that only your Windows account can read it.

PS Focus's use and transfer of information received from Google APIs adheres to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the Limited Use requirements. Google data is used only to provide PS Focus's backup and account display features. It is never sold or used for advertising, and no person reads it.

## Feedback

When you submit feedback, PS Focus sends the star rating, your message, and the local time you submitted it. It goes to a Google Apps Script web service run by Giltyworks, which emails Giltyworks a summary every six hours and then deletes its stored copy. Feedback emails are kept in Giltyworks' mailbox so suggestions can be followed up. Do not include personal information in feedback that you do not want Giltyworks to read.

## Update check

Once a day PS Focus asks the same web service which version is the latest. The request contains no information about you or your activity. If a newer version exists, Settings offers a link to the download page. PS Focus never downloads or installs anything by itself.

Like any web request, feedback and update checks reach Google's servers, which process your IP address under [Google's Privacy Policy](https://policies.google.com/privacy). PS Focus does not collect or log IP addresses itself.

## What PS Focus does not do

PS Focus has no advertising, analytics, or tracking services. Giltyworks does not sell or share your information. Apart from the Google services described above, your information is not sent anywhere.

## Removing your information

- **Uninstall PS Focus** (Windows **Settings > Apps > Installed apps**) and tick **Also delete all user data**. This signs out of Google and deletes the folders listed above.
- **Remove Google access** at any time from PS Focus Settings (**Log out**) or from your Google Account's [third-party connections page](https://myaccount.google.com/connections).
- **Delete the Drive backup.** In Google Drive on the web, open **Settings > Manage apps**. Find PS Focus, then choose **Options > Delete hidden app data**.
- **Delete feedback you sent** by emailing giltyworks@gmail.com.

## Children

PS Focus is not directed at children under 13, and Giltyworks does not knowingly collect information from them.

## Changes

If this policy changes, the new version will be published with an updated effective date. Significant changes will be announced in the release notes.
