---
title: Code Signing Policy
permalink: /code-signing/
---

# Code Signing Policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org).

PS Focus for Windows is signed so you can check that an installer really comes from this project and has not been changed since it was built. Only the installer and the app it installs are signed, and only when they are built from the source code in the official repository: [github.com/giltyworks/ps-focus](https://github.com/giltyworks/ps-focus).

## How releases are built and signed

- Every release is built by GitHub Actions on a clean machine, from the public source code in the repository above.
- The build runs the app's tests and checks the result for leaked credentials before anything is signed.
- Signing is done by SignPath, which keeps the certificate's private key in a hardware security module. Each release is approved by hand before it is signed.
- Components made by others, such as Python and the libraries listed in "Third-Party Notices.txt", are included as they are and are not signed as this project's work.

## Team roles

PS Focus is made by one person, Giltyworks, who holds every role:

- **Committer and reviewer:** [Giltyworks](https://github.com/giltyworks)
- **Approver:** [Giltyworks](https://github.com/giltyworks)

## Privacy

PS Focus only sends information to other computers in these cases, each described in the [Privacy Policy]({{ '/privacy/' | relative_url }}):

- **Update check:** once a day and at launch, it asks for the latest version number. Nothing about you or your activity is sent.
- **Google Drive backup:** only if you sign in with Google, it backs up your activity history and settings to a private app folder in your own Google Drive.
- **Feedback:** only what you choose to send through the feedback window.

## Checking a signature

Right-click the installer, choose **Properties**, then the **Digital Signatures** tab. The signer should be **SignPath Foundation**.

## Reporting a problem

If you find a signed file you think is not genuine or behaves maliciously, don't run it. Email [giltyworks@gmail.com](mailto:giltyworks@gmail.com) with where you got it and, if you can, its SHA-256 checksum.
