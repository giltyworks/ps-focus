---
permalink: /
body_class: home
---

<div class="hero" markdown="1">
<div class="hero-intro" markdown="1">

# Every second counts.

<p class="what">Automatically tracks your time in Photoshop, Krita, Clip Studio Paint, and PhotoCraft.</p>
<p class="what-sub">Free for Windows. Your hours become charts, a calendar, and a level.</p>

<a class="button" id="download" href="https://github.com/giltyworks/ps-focus/releases/download/v1.1.26/PS-Focus-Setup-1.1.26.exe">Download for Windows</a> <a class="try-link" href="#try">or try it right here</a>
<script>/* A PC downloads the installer and opens the release page beside it to read meanwhile; a phone can't run
   the installer, so it gets the release page alone */
(function () {
  var button = document.getElementById("download"), release = "https://github.com/giltyworks/ps-focus/releases/latest";
  if (matchMedia("(max-width: 760px), (pointer: coarse)").matches) button.href = release;
  else button.addEventListener("click", function () { window.open(release, "_blank", "noopener"); });
})();</script>

</div>

<div class="note" markdown="1">
Free and [open source](https://github.com/giltyworks/ps-focus) · Windows 10 and 11 (64-bit)

The app isn't code-signed yet, so you may see warnings. Your browser may say the file isn't commonly downloaded: choose to keep it (in Edge, **⋯** › **Keep** › **Keep anyway**). Then Windows may say "Windows protected your PC": choose **More info**, then **Run anyway**. Each release lists a SHA-256 checksum for checking your download.
</div>

<div class="hero-features" markdown="1">

## What it does

- **Tracks while you draw.** Time counts while your art app is in front, and pauses after five idle minutes.
- **Shows your habits.** Charts by day, week, month, and year, a calendar of sessions, streaks, and averages.
- **Levels 1 to 99.** Your total hours set your level, with a small celebration at each new one.
- **Make it your own.** Drag panels to rearrange them, or float and snap them beside the window, as in Photoshop. Tall, or a wide landscape strip.
- **Draw with friends.** Add friends by code to see each other's hours and who's drawing right now.
- **Stays out of the way.** Starts with Windows, sits in the tray, needs no account, and can turn see-through while your mouse is elsewhere.
- **Backs itself up.** Copies on your PC, plus an optional backup in your own Google Drive.

</div>

</div>

<section class="try" id="try" markdown="0">
  <h2>Try it</h2>
  <p class="try-intro"><span class="psf-pointer-only">A simplified demo, not the app itself, so some things differ. Drag the window around; the arrows show the rest.</span><span class="psf-touch-only">A simplified demo, not the app itself, so some things differ. It's made for PCs, so it's limited on a phone; the arrows show the rest.</span></p>
  <div class="psf-demo" data-painting="{{ '/assets/demo/sorolla.jpg' | relative_url }}" data-logo="{{ '/assets/logo-v2.png' | relative_url }}"></div>
  <p class="caption">Sample data and made-up friends; nothing you do here is sent anywhere. Painting: Joaquín Sorolla, <em>Strolling along the Seashore</em> (1909), public domain.</p>
  <noscript><p class="caption">The demo needs JavaScript.</p></noscript>
</section>
<link rel="stylesheet" href="{{ '/assets/demo/demo.css' | relative_url }}?v=1.1.26">
<script src="{{ '/assets/demo/demo.js' | relative_url }}?v=1.1.26" defer></script>

<figure class="wide-shot">
  <img src="{{ '/assets/screenshot-landscape.png' | relative_url }}" width="1495" height="228" alt="PS Focus in landscape: today's time in Photoshop, then friends and their hours, the hours graph and the October calendar side by side in one wide, short window">
  <figcaption class="caption">Landscape: everything side by side in one short strip</figcaption>
</figure>

<section class="maker" aria-label="Who makes PS Focus">
  <img class="avatar" src="{{ '/assets/avatar.jpg' | relative_url }}" width="96" height="96" alt="gilty_works">
  <div>
    <h2>gilty_works</h2>
    <p>Artist in training. I built PS Focus to turn my drawing hours into progress I can see, and a place where friends keep each other going.</p>
    <ul class="socials">
      <li><a href="https://www.artstation.com/gilty_works" title="ArtStation">{% include icon-artstation.svg %}</a></li>
      <li><a href="https://www.instagram.com/gilty_works/" title="Instagram">{% include icon-instagram.svg %}</a></li>
      <li><a href="https://www.youtube.com/@gilty_works" title="YouTube">{% include icon-youtube.svg %}</a></li>
      <li><a href="https://www.threads.com/@gilty_works" title="Threads">{% include icon-threads.svg %}</a></li>
    </ul>
  </div>
</section>

<div class="cards" markdown="1">
<section markdown="1">

## What it never records

Only the seconds you worked, per app and hour. No document names, window titles, keystrokes, screenshots, or file contents, and no ads or analytics. See the [Privacy Policy]({{ '/privacy/' | relative_url }}).

</section>
<section markdown="1">

## Google sign-in

Optional. PS Focus gets its own hidden Google Drive folder for your settings and backup, plus your email address. It can't see your other files, and your Drive data never reaches Giltyworks. Signing in also turns on Friends, which shares your name and hours with friends you accept; choose **Offline** to stop. See the [Privacy Policy]({{ '/privacy/' | relative_url }}).

</section>
<section markdown="1">

## Uninstalling

In Windows **Settings > Apps > Installed apps**, choose PS Focus, then **Uninstall**. Your history is kept unless you tick **Also delete all user data**.

</section>
<section markdown="1">

## Questions or feedback

Email [giltyworks@gmail.com](mailto:giltyworks@gmail.com), or use **Got feedback?** in the app's Settings.

</section>
</div>
