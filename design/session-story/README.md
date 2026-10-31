# Session story card

The approved design for sharing one PS Focus session to an Instagram-style story, settled on 31 October 2026.
`mockup.html` is the working mock-up (open it in a browser; pick any photo to see it over artwork). The app's
export follows these values.

## Layout

- A 9:16 card. Top left: the date in a frosted pill, the session title under it ("Sat Lunch Session": short
  weekday, part of day from the start time, "Session"), and the programs under that ("Photoshop · Krita").
  Top right: the PS Focus logo at 55% opacity
- Bottom left, one column, 48px between stats: **Records** (only when the session earned one), **Focus time**,
  **Started**. No streak, level or finish time, so every session stands on its own
- Exported as a 1080x1920 story: the card at 82% of the width, centred, with rounded corners, a faint 1px light
  edge and a soft shadow, over a blurred, enlarged and darkened copy of the same photo (as Runna's shared cards are)

## Type

Archivo (variable weight and width, SIL Open Font Licence). Sizes are px on a card 1080 wide; they scale with the
card.

| Text | Size | Weight | Width | Other |
|---|---|---|---|---|
| Date | 33px | 450 | 100% | uppercase, letter-spacing 0.08em, in a frosted pill (padding 0.4em 0.85em; 24% white over the blurred photo, slightly brighter and more saturated; no outline) |
| Session title | 71px | 750 | 100% | letter-spacing -0.01em, line-height 1.1, one line |
| Program | 44px | 500 | 100% | 85% opacity |
| Stat labels | 42px | 600 | 100% | 92% opacity |
| Big numbers | 162px | 660 | 96% | letter-spacing -0.025em, line-height 0.95, tabular figures |
| Record names (optional, off) | 50px | 600 | 100% | line-height 1.3, 90% opacity |

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
