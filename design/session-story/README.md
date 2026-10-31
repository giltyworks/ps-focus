# Session story card

The approved design for sharing one PS Focus session to an Instagram-style story, settled on 31 October 2026.
`mockup.html` is the working mock-up (open it in a browser; pick any photo to see it over artwork). The app's
export follows these values.

## Layout

- A card shaped as Runna's, about 1 wide to 1.58 tall. Top left: the date in a frosted pill, the session title under it ("Sat Lunch Session": short
  weekday, part of day from the start time, "Session"), and the programs under that ("Photoshop · Krita").
  Top right: the PS Focus logo at 35% opacity, white only, its black stroke hollowed out
- Bottom left, one column, 48px between stats: **Records** (only when the session earned one), **Time**,
  **Started**. No streak, level or finish time, so every session stands on its own
- Exported as a 1080x1920 story: the card at 82% of the width, centred, with rounded corners, a faint 1px light
  edge and a diffuse shadow straight behind it (no drop), over a blurred, enlarged and darkened copy of the same photo (as Runna's shared cards are)

## Type

Segoe UI, the same as the rest of PS Focus; it has only the Regular, Semibold and Bold weights. Sizes are px on a card
1080 wide; they scale with the card.

| Text | Size | Weight | Other |
|---|---|---|---|
| Date | 27px | 600 | uppercase, letter-spacing 0.12em, in a frosted pill (text box padding 0.4em 1.1em, the pill itself 0.1em shorter top and bottom; 28% white over the blurred photo, softly blurred; no outline) |
| Session title | 57px | 700 | letter-spacing -0.01em, line-height 1.1, one line |
| Program | 46px | 600 | 85% opacity |
| Stat labels | 41px | 600 | 92% opacity |
| Big numbers | 134px | 700 | letter-spacing -0.045em, line-height 0.95, tabular figures |
| Record names (optional, off) | 50px | 600 | line-height 1.3, 90% opacity |

## Colour and effects

- Big numbers pure white; all other text light grey `#e6e8eb`. No shadow on any text, the logo or the badge
- Card padding 76px (7% of the width)
- Over the photo: 10% black overall, plus a top-to-bottom fade: 42% black at the top, 8% at 24%, clear at 40%,
  30% at 54%, 36% at the bottom, so every stat sits on the same darkness
- Records badge: the app's own award icon (`qt/icons.py`, gold `#f0c33c`, see-through gap between disc and tails),
  0.66 of the big-number size, beside the count

## Records

Earned only, counted like this: a session's day total beats every earlier day (of at least the session minimum) in
the period. Longest session ever outranks this year, which outranks this month, so only the biggest shows; the
longest session in the main program counts separately.
