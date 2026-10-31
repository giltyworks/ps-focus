# Session story card

The design for sharing one PS Focus session as an Instagram-style story. The code is `qt/story_card.py` (the card and
the story), `qt/story_dialog.py` (the window) and `session_story.py` (the card's words); every size below is a constant
there, named as in this page's tables.

- `tuner.html` is the working tool: open it in a browser, move the sliders, and press **Copy values** for a block of
  constants named as in `qt/story_card.py`. It starts at the card's current values. It draws the card with the
  browser's text, so spacing and the shadow differ a little from the app, which is the final judge
- `mockup.html` is the first mock-up, kept for its history. Its values (the Archivo typeface, a full-height card)
  are out of date

## Layout

- A card shaped as Runna's, 1 wide to 1.58 tall. Top left: the date in a frosted pill, the session title under it
  ("Sat Lunch Session": short weekday, part of day from the start time, "Session"), and the programs under that
  ("Photoshop · Krita"). Top right: the PS Focus logo at 35% opacity, white only, its black stroke hollowed out
- Bottom left, one column, 4.5% of the card's width between stats: **Records** (only when the session earned one),
  **Time**, **Started**. No streak, level or finish time, so every session stands on its own
- Exported as a 1080x1920 story: the card at 81% of the width, centred, with rounded corners (5% of the story's
  width), a faint 3px light edge at 5% and a diffuse shadow straight behind it (12% black, no drop), over a blurred,
  enlarged and darkened copy of the same photo (as Runna's shared cards are)

## Type

Segoe UI, the same as the rest of PS Focus. It has only the Regular, Semibold and Bold weights, so the card's weights
are those. Sizes are px on a card 1080 wide; they scale with the card. The small
text (not the title or the big numbers) is drawn a little heavier than Qt's plain drawing, which leaves light text on a
photo thinner than a browser shows it.

| Text | Size | Weight | Other |
|---|---|---|---|
| Date | 27px | 600 | uppercase, letter-spacing 0.12em, in a frosted pill (text box padding 0.4em 1.1em, the pill itself 0.1em shorter top and bottom; 28% white over the blurred photo, softly blurred; no outline) |
| Session title | 57px | 700 | letter-spacing -0.01em, line-height 1.1, one line |
| Program | 46px | 600 | white at 50% opacity |
| Stat labels | 41px | 600 | white at 50% opacity |
| Big numbers | 134px | 700 | letter-spacing -0.045em, line-height 0.95 |

## Colour and effects

- Big numbers pure white; the date and title light grey `#e6e8eb`; the program line and stat labels white at 50% opacity. No shadow on any text, the logo or the badge
- Card padding 7% of the card's width
- Over the photo: 10% black overall, plus a top-to-bottom fade: 42% black at the top, 8% at 24%, clear at 40%,
  30% at 54%, 36% at the bottom, so every stat sits on the same darkness
- Records badge: the app's own award icon (`qt/icons.py`, gold `#f0c33c`, see-through gap between disc and tails),
  0.66 of the big-number size, beside the count

## Records

Earned only, counted like this: a session's day total beats every earlier day (of at least the session minimum) in
the period. Longest session ever outranks this year, which outranks this month, so only the biggest shows; the
longest session in the main program counts separately.

## The share window

Opened from a day's overview. It has the app's own title row (Windows' close button, rounded corners on Windows 11,
dragged by the title), with the name of the chosen photo in the title and an icon button for choosing one. The preview
is a quarter of the story, and a click on it chooses a photo, and an expand button over its top right corner shows it as large as the screen allows. Under it, one row the preview's width:
**Save to iCloud** (the `iCloudPhotos\Photos` folder iCloud for Windows syncs), **Save to G Drive** (a `PS Focus
Stories` folder in My Drive, for Google Drive for desktop), copy to the clipboard, and save as a PNG. A message about
the last save shows below the row, which makes the window taller only while it is there. The text on the card cannot
be edited.
