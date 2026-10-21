# Changelog

All notable changes to vuurtoren are listed here. The format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **A scenario with an unknown override group is refused.** Saving or previewing one now
  answers 422 instead of storing the stray key and ignoring it. The `milestones` group,
  which v0.1.0 accepted but refused to project, is gone. Your database upgrades on its
  own, and a v0.1.0 export still imports. If a scenario carries a non-empty `milestones`
  override, the upgrade stops and names it: remove that override in v0.1.0 first.

## [0.1.0] - 2026-10-21

The first public release, and a beta: the export format and the API may still change before
1.0, and the Plan surface lists what the tax engine does not model yet.

### Added

- **Projection.** Month-by-month net worth, taxes and cash flow for a household of one or
  two people, over their whole lives. The FI and coast-FI dates are in today's euros.
- **Dutch tax engine.** Box 1 with the heffingskortingen and the hypotheekrenteaftrek net of
  the eigenwoningforfait and Wet Hillen. Box 3 under the forfaitair regime, with the
  tegenbewijs and the *Wet werkelijk rendement* scheduled for 2028, split across fiscal
  partners or with an allowance per person. Transfer tax with the starter exemption, the
  annual and one-time gift exemptions, and the AOW age. Every figure is dated and cites its
  source, and you can override any of them per scenario.
- **Austria and moving abroad.** An Austrian regime, and a milestone that changes tax
  residence partway through a plan, where you pick each account's tax treatment in the
  new country.
- **US person overlay.** For US citizens living in the Netherlands: federal income tax with
  the foreign tax credit, PFIC treatment of non-US funds, and FBAR and FATCA reporting
  thresholds.
- **Milestones.** Buy or sell a home with an annuity mortgage, extra repayments, retire,
  change an income, expense or contribution, and one-off sums in or out.
- **Plan.** Three lenses (Composition, Uncertainty with a Monte Carlo range, and Scenarios
  side by side), a sensitivity view of what moves your FIRE date most, and a solver for the
  spending or contributions that reach a goal: FIRE by a year, deplete to zero by a year, or
  hold a success rate, counting a bequest floor when you set one.
- **Today, Flows and Settings.** Accounts with a manual or fetched price (Yahoo Finance for
  listed funds, ECB rates for currency) that also opens the plan, cash flows, display
  currency, light and dark theme, English and Dutch, and a way to start over with an empty
  household.
- **Local-first.** Your plan lives in a SQLite file on your machine, with JSON export and
  import. The browser build runs the same engine in WebAssembly, so nothing leaves the page;
  it cannot refresh prices.

[Unreleased]: https://github.com/simonvanlierde/vuurtoren/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/simonvanlierde/vuurtoren/releases/tag/v0.1.0
