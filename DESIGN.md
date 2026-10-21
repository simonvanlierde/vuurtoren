---
name: vuurtoren
description: A navigator's chart for a Dutch household's money — paper, ink, one amber beam.
colors:
  paper: "#f7f9fb"
  ink-navy: "#0b1b2b"
  night-sea: "#071019"
  beacon-amber: "#ffb020"
  beacon-amber-deep: "#c77e00"
  sea-green: "#1f7a5a"
  brick: "#b4462e"
  card-paper: "#ffffff"
  mist: "#e8edf2"
  series-blue: "#2e6f9e"
  series-slate: "#4b5d73"
  series-violet: "#7a4a9c"
  beam-core: "#ffe9b8"
  marker-user: "#1d4ed8"
typography:
  display:
    fontFamily: "Bricolage Grotesque, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 400
    lineHeight: 1.25
  headline:
    fontFamily: "Bricolage Grotesque, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.4
  body:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
  label:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    letterSpacing: "0.025em"
  mono:
    fontFamily: "IBM Plex Mono, monospace"
    fontSize: "0.875rem"
    fontWeight: 400
rounded:
  sm: "0.225rem"
  md: "0.3rem"
  lg: "0.375rem"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.ink-navy}"
    textColor: "{colors.paper}"
    rounded: "{rounded.lg}"
    padding: "4px 10px"
    height: "32px"
  button-emphasis:
    backgroundColor: "transparent"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.lg}"
    padding: "4px 10px"
    height: "32px"
  button-outline:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.lg}"
    padding: "4px 10px"
    height: "32px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.lg}"
    padding: "4px 10px"
    height: "32px"
  input:
    backgroundColor: "transparent"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.lg}"
    padding: "4px 10px"
    height: "32px"
  chip-status:
    backgroundColor: "transparent"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.sm}"
    padding: "2px 6px"
    typography: "{typography.label}"
---

# Design System: vuurtoren

## Overview

**Creative North Star: "The Harbour Chart"**

A navigator's chart, not a dashboard. Paper that reads as paper, ink that is navy rather
than black, and exactly one light source, the beacon amber, that shows where the safe
water is. Nothing is drawn to impress. The density is tight and tabular, legible on a
laptop and on a phone.

The system is flat and ruled. Depth comes from hairline borders at 12 % ink and from
tonal layers (paper → white card, night sea → ink-navy card), never from shadows at rest.
Colour is rationed. Ink and paper do the work. Amber marks the one thing that leads
(focus, the active tab, the beam). Green is reserved for growth and brick for debt. The
chart series ramp is the only place where more than three hues meet.

**Key Characteristics:**

- Two tonal surfaces: paper/white by day, night sea/ink-navy by night, with the same ink.
- One accent that leads (amber), two that classify (green = growth, brick = debt).
- Hairlines, not shadows. Tabular figures everywhere. No decoration that doesn't help the
  reading.
- Bricolage Grotesque only for headlines and headline numbers. Public Sans does the rest.
- A 44 px touch floor carried by the primitives, and compact 32 px controls from `sm` up.

## Colors

### Primary

- **Ink Navy** (`ink-navy`): all text, the primary button fill, the text weight of the
  active nav underline. On night sea it becomes the card surface.
- **Beacon Amber** (`beacon-amber`): the light source. Focus rings and the active
  underline on night sea, and the beam's translucent fill in both themes. At 1.73:1 on
  paper it is a wash, not a mark.
- **Beacon Amber Deep** (`beacon-amber-deep`): the same light, deepened to clear 3:1 on
  paper. Every focus ring, active marker, median line and tornado bar in the light theme
  uses this, never the headline amber.

### Secondary

- **Sea Green** (`sea-green`): growth. Investments, income, the net-worth composition
  ramp (four steps from green to green-pale), the crossover "covered" state.
- **Brick** (`brick`): debt, expenses, destructive actions, the crossover "not covered"
  state. Lightened to `#d3654c` on night sea for AA.

### Tertiary (chart series only)

- **Chart Blue** (`series-blue`), **Chart Slate** (`series-slate`), **Chart Violet**
  (`series-violet`): extra series when a chart needs more than growth and debt. Pension
  is slate, and comparisons take blue and violet. Each has a lighter night-sea twin in
  `index.css`, and components reach them only through `lib/chartColors.ts`.
- **Beam Core** (`beam-core`): the bright centre of the uncertainty beam's gradient.
- **User Marker** (`marker-user`): "this figure is yours, not the Belastingdienst's".
  Blue on purpose, so a user override never reads as a provisional official figure.

### Neutral

- **Paper** (`paper`): the day background and the night-sea text colour.
- **Night Sea** (`night-sea`): the dark background.
- **Card Paper** (`card-paper`): white cards, popovers and sheets on paper. Ink-navy
  takes that role at night.
- **Mist** (`mist`): secondary and muted fills on paper, such as chips, secondary buttons
  and subtle bands. At night the equivalent is paper at 8 %.
- **Hairline**: ink at 12 % for borders and dividers. At night it is paper at 12 %.
  Muted text is the foreground at 60 %.
- **Input stroke**: ink at 50 % on paper and paper at 40 % at night, so a control's
  edge clears 3:1 in both themes (WCAG 1.4.11). At 20 % it was 1.5:1.

### Named Rules

**The One Light Rule.** Amber is the only colour allowed to say "look here". It marks
focus, the active tab, the beam and the median. It is never the fill of a button, a badge
or a background band.
**The Two Hues Rule.** Green means growth and brick means debt, on every surface and in
every chart. No chart draws income in brick or debt in green, and no status chip borrows
either.
**The Contrast-Measured Rule.** A colour enters the system with its contrast on both
backgrounds recorded in the comment beside it. Series colours clear 3:1 on their own
background, and text clears 4.5:1. Headline amber is never drawn thin on paper.

## Typography

**Display Font:** Bricolage Grotesque (with sans-serif fallback), 400 and 700
**Body Font:** Public Sans (with sans-serif fallback), 400 / 500 / 600
**Label/Mono Font:** IBM Plex Mono (with monospace fallback), 400 / 500

**Character:** Bricolage gives the headline numbers a little grit and width. Public Sans
keeps the body neutral. Tabular numerals are on everywhere (`tnum`). Fonts are
self-hosted, latin + latin-ext only, and nothing loads from a CDN.

### Hierarchy

- **Display** (400, 1.5rem / `text-2xl`, 1.25): the page `<h1>` and the four headline
  figures in the Plan strip (FIRE number, FI date, lens slot, savings rate). Bricolage.
- **Headline** (400, 1.125rem / `text-lg`, 1.4): section `<h2>` inside a view. Bricolage.
  A few read-outs use `text-3xl` for the single number a panel exists to show.
- **Body** (400, 0.875rem / `text-sm`, 1.5): the working size of the whole app, with 150+
  uses. Captions and explanatory sentences under charts are capped at `max-w-prose`.
- **Label** (400, 0.75rem / `text-xs`, `tracking-wide`, uppercase where it names a column
  or group): definition-list terms, chart axis labels, status chips, hints.
- **Mono** (400, 0.875rem): ISO dates, ISINs, raw parameter values, and anything the user
  may need to copy exactly.

### Named Rules

**The Headline Number Rule.** A figure that is the answer (a FIRE number, an FI date, a
probability) is set in Bricolage at display size with tabular numerals. A figure that is
evidence stays in Public Sans at body size. Nothing in between.
**The Body Stays Small Rule.** `text-sm` is the body. Add emphasis with weight (500 or
600) or the display face, not by stepping up to `text-base`.

## Layout

A single-column page with a 16 px gutter on phones and 32 px from `sm` up
(`px-4 sm:px-8`). There is no fixed container. Content runs the full viewport width, and
tables, charts and tab strips scroll inside their own `overflow-x-auto` wrapper. The body
never scrolls horizontally. `overflow-x-hidden` on `body` is a guard, not the mechanism.

Navigation shows the same four destinations twice: an underline tab bar at the top from
`sm` up, and a fixed bottom bar of four cells with `env(safe-area-inset-bottom)` below
that. On the Plan surface the chart and its assumptions sit side by side from `lg`
(`lg:flex-row`). The rail on the right carries the live sliders, and the deck below
carries read-only panels.

Spacing uses Tailwind's 4 px grid at 1 / 2 / 3 / 4 / 6 / 8 (`gap-1`…`gap-8`): `gap-4`
between fields, `gap-6` between sections, `mt-2` for a hint under its control. The density
is a planner's: 32 px controls, a 44 px minimum hit area on touch, and tables with
`py-1.5` rows.

Charts are hand-drawn SVG (the timeline) or Recharts with a smaller type scale on narrow
screens, so axis labels stay legible at 320 px instead of being hidden.

## Elevation & Depth

Flat at rest. Depth is tonal: paper → white card, night sea → ink-navy card, with a 12 %
hairline border where two surfaces meet. The one shadow in the app is a shadcn default on
an overlay (`shadow-lg` on the sheet). It is tolerated, not part of the vocabulary.

### Named Rules

**The Ruled Paper Rule.** A panel is separated by a hairline or a tonal step, never by a
drop shadow. If something must float (a sheet, a dialog), it may carry shadcn's overlay
shadow and nothing else.

## Shapes

Tight corners: a 6 px base radius (`--radius: 0.375rem`), scaled to 3.6 / 4.8 / 6 px for
sm / md / lg. Buttons and inputs take `rounded-lg` (6 px). Chips and bands take the bare
`rounded` (4 px). Nothing is pill-shaped, and nothing is square except table cells. Borders
are 1 px hairlines at 12 % of the foreground (dividers), or the input stroke above. The
primary action uses a full-strength foreground border (`emphasis`) rather than a fill.

## Components

### Buttons

- **Shape:** gently rounded (6 px), 32 px tall from `sm`, 44 px minimum on touch,
  `text-sm` 500.
- **Primary (`default`):** ink-navy fill with paper text, and paper fill with ink text at
  night. Reserved for the single action that commits a form (Save).
- **Emphasis:** transparent with a full-strength foreground border. It is the app's own
  primary weight where a fill would shout: Run, Solve, "+ cash flow".
- **Outline / Secondary / Ghost:** 12 % hairline, mist fill, or no chrome. All of them
  hover to the muted fill.
- **Destructive:** brick at 10 % fill with brick text. Never a solid brick button.
- **Focus:** an opaque 3 px amber ring (deep on paper). Everything else that can take
  focus gets the global 2 px amber outline with a 2 px offset. `:active` nudges 1 px down.

### Chips

- **Status chip:** hairline border, `text-xs` 500, 4 px radius, foreground text. It
  carries a tax figure's provenance (`final` / `provisional` / `proposed`).
- **Edited badge (`EditedBadge`):** the user-marker blue, the only blue in the chrome. It
  says "this is your override".

### Cards / Containers

- **Corner Style:** 4 px for bands, 6 px for panels.
- **Background:** paper/white by day, night-sea/ink-navy by night. Subtle bands are the
  foreground at 5 %.
- **Border:** 12 % hairline.
- **Internal Padding:** 12 × 8 px for bands, 16 px for panels.

### Inputs / Fields

- **Style:** transparent fill, the input stroke (`--input`), 6 px radius, 32 px tall from `sm`
  (44 px on touch). `text-base` on phones to stop iOS zooming in, and `text-sm` from `md`.
- **Focus:** the border turns to the ring colour with an opaque 3 px ring. A ring at
  50 % composited to 1.7:1 on paper; opaque it clears 3:1.
- **Error:** `aria-invalid` turns the stroke brick with a 20 % brick ring. The message
  sits under the field in `text-sm` brick. **Disabled:** 50 % opacity, not-allowed cursor.
- **Range slider:** `accent-color` from the ring, a 24 px thumb, and `py-3.5` for a 44 px
  hit area.

### Navigation

- **Style:** underline tabs in `text-sm` 500. Inactive tabs are at 60 % foreground, the
  active one at full with a 2 px amber underline, and hover restores full foreground. A
  top bar from `sm`, and below that a fixed bottom bar with four equal cells at 44 px.
- **Lens / deck tabs (shadcn `Tabs`):** the same weight. Triggers are 44 px on touch and
  compact from `sm`. Long strips scroll horizontally with `shrink-0` triggers.

### The Beam (signature)

The timeline draws its uncertainty band as a translucent amber beam: a headline amber fill
with a bright `beam-core` centre. On first render it grows from left to right over 1.1 s,
and `prefers-reduced-motion` turns that off. It is the lighthouse built into the
structure, and the one place the brand is allowed to be a picture.

### Interpretive sentence (signature)

Every chart ends in one plain sentence that says what the chart means for this household
("Your FIRE date moves most on Safe withdrawal rate"). `text-sm`, muted foreground,
`max-w-prose`. It is part of the component, not a caption.

## Do's and Don'ts

### Do

- **Do** draw every chart colour through `lib/chartColors.ts` → `--vt-series-*`. A hex in
  a component is a theme bug waiting to happen.
- **Do** deepen amber to `beacon-amber-deep` for any thin mark on paper. Keep headline
  amber for wide translucent fills and for night sea.
- **Do** keep the 44 px touch floor in the primitive (`Button`, `Input`, `TabsTrigger`),
  never at the call site.
- **Do** end a chart with its interpretive sentence, and state what the model does not
  cover beside the result.
- **Do** set Dutch tax terms in body text without Bricolage, unchanged in both locales.
  They are names.

### Don't

- **Don't** add hero imagery, emoji, social-proof badges, testimonials or any claim the
  product has no evidence for. The product has none, and the chrome must not imply them.
- **Don't** fill a button, badge or band with amber. Amber leads, it does not decorate.
- **Don't** introduce a shadow at rest, a pill radius, or a gradient outside the beam.
- **Don't** show a database key (`nl.box3_bank`) or a raw decimal (`0.36`) where a person
  reads. Format by the field's annotation (`36 %`, `€ 59.357`, `2028`).
- **Don't** let the browser supply an error. Every validation message is ours, in the
  user's locale, under the field.
