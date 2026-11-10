# Changelog

All notable changes to vuurtoren are listed here. The format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-11-10

### Upgrading

- **Back up your database first.** The first start of 0.2.0 upgrades `data/vuurtoren.db`,
  and 0.1.1 cannot open the upgraded file. Copy the file, or export your household, before
  you start the new version. An export from 0.1.1 still imports, except a two-person
  household's pension with no owner: set `owner_person_id` in the file first (the import's
  error says so). An export from 0.2.0 imports into 0.1.1.
- **Every pension account needs an owner.** In a household of one person, the upgrade
  makes that person the owner. In a household of two, the Plan asks you to pick an owner
  in Accounts before it projects.
- **A scenario that set the flat pension withdrawal rate loses that override.** The rate no
  longer exists (see Changed), so the upgrade drops it, and the scenario projects on the
  Box 1 brackets.

### Added

- **Austria's pension age for women.** When a household is taxed in Austria or moves there,
  the person editor asks for each person's sex. A woman taxed in Austria now gets her
  cohort's Regelpensionsalter instead of a flat 65: 60 if born before 1964, 60 to 65 by
  birth half-year for 1964 to mid-1968. Leaving it empty still gives 65.
- **An MCP server.** `vuurtoren-mcp` (the `mcp` extra) lets an AI assistant read your
  household and run projections over stdio. It never writes, and it refuses a database
  that the app has not created or upgraded. See the README.
- **What the US overlay leaves out.** A US person's Plan lists what the US overlay does not
  model.
- **More context in the tax panel.** Each figure shows its source year, an amount says
  which year's prices it is in, a note says which year an edit applies to, and the Box 1
  income figures are listed.
- **2027 figures**, as far as they are published: the proposed Box 1 rates and the maximum
  hypotheekrenteaftrek rate, the top-rate threshold (frozen at €78,426), the provisional
  Box 3 bank and debt forfaits, the €615,000 startersvrijstelling cap and the 7% transfer
  tax on a home the buyer will not live in. [docs/tax-coverage.md](docs/tax-coverage.md)
  lists what is still carried from 2026.
- **A link preview.** A shared link to the demo shows a card.
- **`overlay_countries` in `/api/meta`**, the countries that have a citizenship overlay.

### Changed

- **Pension and lijfrente payouts are taxed on the Box 1 brackets.** A withdrawal is added
  to its owner's other income for the year and taxed through the brackets, the AOW-age
  rates and the heffingskortingen, instead of at one flat rate of 37.56%. Most plans pay
  less tax on payouts after the AOW age. The AOW-age rates follow the statutory AOW date,
  even when you set an earlier pension age.
- **The Plan reads more easily.** The tabs under the chart sit in two groups, Decisions and
  Evidence, that fit on a phone. The headline leads with the FI date, with the Coast-FIRE
  and crossover dates under it. Every chart uses the same legend.
- **A pension account needs an owner.** Saving or importing one without an owner answers
  422, and so does an account with the `nl.box1_pension` tax treatment.
- **An unknown assumption name in a request or a saved scenario answers 422** instead of being ignored.
- **The demo moved** to [simonvanlierde.com/vuurtoren](https://simonvanlierde.com/vuurtoren/).

### Removed

- `household.base_currency` and `scenario.is_baseline`, from the API and the export file.
  Neither did anything.
- The assumption name `aow_growth_months_per_decade`. Stored scenarios and imported
  exports are renamed to `state_pension_growth_months_per_decade`.
- The tax field `pension_withdrawal_rate`, replaced by the Box 1 brackets.
- The top-level `source_year` in `/api/tax-config`. Each figure now carries its own.

### Fixed

- **`/api/tax-config?country=US` answers 404** instead of a server error.
- **After a move from Austria back to the Netherlands,** payouts use the Dutch AOW date
  again.
- **A Box 3 loss survives a move abroad and back.** Under the Wet werkelijk rendement, a
  resident who left and returned lost the loss they carried forward.
- **Settings no longer overwrites newer household values with stale ones.** "Saved" shows
  only after the save succeeds, and an empty "Plan until age" cannot be saved.
- **The FI-date and early-retirement solvers** stay inside the range where an answer
  exists.
- **A failed solve, Monte Carlo run or early-retirement check says why.** These panels
  showed only "failed: 400" and now show the reason the server gave.
- **The English tax panel labels every figure in English.** Some read in Dutch ("Eigenwoningforfait drempel"); the Dutch tax names themselves stay Dutch.
- **Accessibility.** The lens panel stays in place while it loads, the chart image no longer
  holds buttons, and focus returns where it was after a drawer closes.

## [0.1.1] - 2026-10-21

### Fixed

- **The 2026 arbeidskorting.** Its maximum was €5,712 where the Belastingdienst's table gives
  €5,685. Every tax figure now cites the official page that states it, and the Tax figures
  tab shows the corrected value.
- **The projection's last month.** It stopped in January of the life-expectancy year
  whatever the youngest person's birth month; it now runs to their birthday month, so a
  household born later in the year gains up to eleven months at the end.
- **The Dutch interface.** Tax figure labels, status chips, the US filing status, milestone
  markers and the number of runs are translated, the crossover and milestone dates read as
  months, and chart legends leave out series that stay at zero.
- **Milestone details are in your language.** The detail panel under the Composition chart
  named each parameter by its stored key in English ("New amount monthly"), also in the
  Dutch UI. It now uses the same labels as the milestone editor. Its values show the
  person, account or cash flow by name instead of by id, a move lists each account's new
  tax treatment instead of "[object Object]", and yes/no settings read as words.
- **Box 3 losses under the Wet werkelijk rendement carry forward.** From 2028 a loss year
  was taxed as zero and the loss was gone. As the bill sets out, a loss above €500 now
  offsets later years' income without a time limit, after the heffingsvrij resultaat.
  A move abroad still drops it, which overstates tax only for someone who returns.

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

[Unreleased]: https://github.com/simonvanlierde/vuurtoren/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/simonvanlierde/vuurtoren/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/simonvanlierde/vuurtoren/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/simonvanlierde/vuurtoren/releases/tag/v0.1.0
