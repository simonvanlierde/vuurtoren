# Product

## Platform

web

## Users

Primary: a Dutch household planning for financial independence and early retirement:
two fiscal partners with a mortgage, taxable investment accounts, pensions and a real Box 3
exposure. They come back again and again with their own real numbers, on a laptop and more
and more on a phone.

Secondary: a first-time visitor from a shared link (r/DutchFIRE), with no data of their
own, who decides in the first minute whether the tool is trustworthy. Where the two
conflict, the household comes first, but the visitor's first-run path is still designed on
purpose.

## Product Purpose

Project a household's net worth, taxes and FIRE date over decades, with a Dutch tax engine
that is correct rather than approximate. Answer the decisions the household actually
faces: when to retire, how much to spend, rent or buy, aflossen or beleggen, move abroad or
not. Success is a household making a real financial decision from the tool's numbers
instead of a spreadsheet.

## Positioning

Tax depth and provenance that no neighbouring tool can truthfully claim (the list is in
the [README](README.md)), plus a state-pension age modelled as an assumption rather than a
constant. Every tax figure carries a source URL and a verification date.

Second, local-first is a fact of how the tool is built, not a privacy promise. The browser
build runs the real Python engine in the page with no origin server, so a visitor can
check in the network tab that nothing left the machine: the only outside request is the
Pyodide runtime from cdn.jsdelivr.net, and an e2e test fails on any other host.

Depth over breadth is deliberate: correct NL beats a long list of countries. Competitors
model US tax (ProjectionLab, Boldin), track without projecting (Ghostfolio), or ship an NL
preset of "preliminary research" quality (earlyretirementcalc).

## Operating Context

Self-hosted (FastAPI + SQLite on the user's machine) or the browser build (the same app
in a Pyodide worker, served as static files, with an in-memory database kept by export and
import, and no price refresh because of CORS).

Sessions are long and repeat: enter accounts, flows, milestones and scenarios, then read
the projection through several lenses (build-up, uncertainty fan, scenario comparison,
crossover, tax burden, solver). Planning happens against real balances, so screenshots and
shared links are a privacy concern, not a growth feature.

## Capabilities and Constraints

- Deterministic and Monte Carlo projection, scenario comparison, solve-for-X, sweeps,
  crossover and cumulative-tax readouts, CSV export of any series, and sharing of
  assumptions through the URL hash.
- Two tax regimes: NL and AT, with a residence-change milestone between them. The seam is
  built for more countries. A US citizenship overlay adds US tax for a US person on top.
- Locales `nl` and `en`. The chrome is translated. Dutch tax terms stay Dutch in both,
  because they are names: "Box 3", "hypotheekrenteaftrek", "lijfrente", "tegenbewijs".
- Runs offline: fonts are self-hosted, with no CDN and no third-party calls at runtime.
  The browser build has one exception, the Pyodide runtime from cdn.jsdelivr.net.
- Charts must stay readable at 320px. Wide content scrolls in its own container, and the
  page body never scrolls horizontally.
- Some modelling simplifications are deliberate and documented. The product's rule is to
  state a limit in the UI rather than hide it, and to fail loudly rather than approximate
  quietly (a gift tax that isn't modelled raises an error instead of guessing).
- Undecided: hosting for the public build, and whether the tool ever becomes multi-user
  (the schema carries a household id as a down payment, nothing more).

## Brand Commitments

The product name is *vuurtoren* (Dutch for lighthouse). The current visual world
([DESIGN.md](DESIGN.md)) is **evidence, not authority**: the user confirmed it is open to
replacement, as long as product truth, terminology and function survive.

Voice: plain and specific, Dutch-first, no marketing inflation. The tool states what it
does not model.

## Evidence on Hand

- Real, dated tax provenance: every figure in `src/vuurtoren/tax/<cc>/parameters.yaml`
  carries `source`, `status` and `verified_on`, and the tax panel shows them. This is the
  strongest proof the product has, and it is genuine.
- A golden baseline projection that locks the engine's numbers, and a Pyodide probe that
  proves the browser build matches it to the eurocent.
- A fictional example household for the tests and the demo. Real household data never
  appears in tracked files or screenshots.
- No customers, testimonials, press, pricing, benchmarks or usage numbers exist. Future
  work must not invent any.

## Product Principles

1. **Correct beats broad.** A figure is sourced and dated, or it does not ship. A number
   shown is a number computed, never an illustration.
2. **State the limits.** What the model does not cover is written where the user reads the
   result, not buried in docs.
3. **Local-first, by construction.** Nothing requires an origin server. The privacy claim
   must stay something you can check, not something we promise.
4. **Built for the second visit.** Density, speed and keyboard reach for repeated real use,
   while a newcomer with no data still finds their way.
5. **The household's language.** Dutch fiscal terms are names and stay intact. The chrome
   adapts, the terminology does not.

## Accessibility & Inclusion

WCAG 2.2 AA is the standard for future work. That means AA contrast in both themes, full
keyboard reach with visible focus (the amber `:focus-visible` outline is an existing
floor), labelled controls, and chart meaning never carried by colour alone. Touch targets
must be big enough on phones, which is a known gap today.
