# Decision log

Decisions still in force, many of them a "no" or "not yet". I record them so that a
missing feature reads as a choice, not a blind spot. Each entry has a date, a verdict, and
the reasoning that has to be argued again before reversing it. Reversing a decision
replaces its entry with a new dated one; git history keeps the old.

## US person overlay

### 2026-10-18 — Cross-year overlay state is a carry the overlay returns, and carryback does not exist

The § 904(c) credit carryforward runs ten years, and the § 1296 loss pool runs
indefinitely. Both are **per-run** state that spans years.

**The overlay returns it rather than holding it.** `annual_tax` takes last year's carry
and returns the charge with the next carry (`USCarry`, a frozen dataclass). `HouseholdTax`
stores one carry per overlay and hands it back the next year without reading it, and
`HouseholdTax.close_year` returns the composite that holds them. The engine keeps that
composite and knows nothing of what is inside (invariants #1 and #2). The shape of the
carry stays in `tax/us/`, so the composite still holds no citizenship rules.

This replaces mutable state on the overlay instance (2026-07-28). That version made a
second `annual_investment_tax` call for the same year advance the state twice, so the
net-SWR drag probe had to avoid the composite, and `ChangeTaxResidence` had to keep the
same overlay objects for the state to survive the move. Now asking twice is harmless and
the move is a `replace` of the residence half. The federal modules were already pure:
`ftc.apply_credit` and `pfic.mark_to_market_inclusion` take the prior state and return the
new one.

**Carryback is not modelled.** § 904(c) allows one year back as well as ten forward. A
carryback means reopening a year the projection has already reported, which a forward
monthly engine cannot do without a second pass. That **overstates** cumulative US tax and
never understates it.

**One basket, the passive one.** § 904(d) splits the limitation between passive and
general income. The general-basket income here is Dutch wage income, and the FEIE excludes
it first, so little of it reaches the credit. Where a large unexcluded salary does remain,
one basket is more generous than two and **understates** US tax. It is the one place in the
credit that errs that way.

### 2026-07-28 — The PFIC loss pool is per treatment, not per security

§ 1296(a)(2) caps the deduction for a mark-to-market loss at that holding's *unreversed
inclusions*, per security. The overlay gets maps keyed by treatment, not accounts, so the
pool is one per `overlay_treatment` per person. For a single mark-to-market PFIC that is
exact. With several, a loss on one can be deducted against inclusions banked on another,
which the statute does not allow. **So it understates US tax**, but only for a household
with several PFICs whose returns diverge.

The fix is not local: it means giving the overlay accounts instead of treatment maps, and
the seam was drawn the other way on purpose (the engine states who owns what, the overlay
applies its rules). `tax/us/federal/pfic.py`'s docstring says the same.

### 2026-07-28 — US federal figures for 2026, and a threshold that must not be indexed

Every figure below comes from Rev. Proc. 2025-32 (which carries the One Big Beautiful
Bill amendments), except the NIIT thresholds, which are statutory. Checked 2026-07-28.

**Ordinary rates, 2026**, from § 1(j)(2). Married filing separately is *not* simply half of
joint. It follows the unmarried schedule exactly until the top band, which splits at
$384,350 rather than $640,600.

| Filing status | Band tops |
| --- | --- |
| Single and MFS | 12,400 · 50,400 · 105,700 · 201,775 · 256,225, then 640,600 (single) or 384,350 (MFS) |
| MFJ | 24,800 · 100,800 · 211,400 · 403,550 · 512,450 · 768,700 |

Rates are 10/12/22/24/32/35/37 throughout.

**Standard deduction, 2026** (§ 63(c)(2)): $32,200 MFJ, $16,100 single, $16,100 MFS.

**Long-term capital gains and qualified dividends** (§ 1(h), § 1(j)(5)(B)), given as the
top of the 0 % band and the top of the 15 % band: MFJ $98,900 / $613,700; single $49,450 /
$545,500; MFS $49,450 / $306,850.

**Foreign earned income exclusion, 2026** (§ 911(b)(2)(D)(i)): $132,900.

**NIIT** (§ 1411): 3.8 % above modified AGI of $250,000 MFJ, $125,000 MFS, $200,000
single.

**The NIIT thresholds are not adjusted for inflation.** § 1411(b) fixes them in nominal
dollars, which is why they have stood at $200,000 and $250,000 since 2013. Every other
figure above is re-indexed each year. `TaxConfigBase.indexed()` scales every `Money`
field, and over a forty-year projection an indexed NIIT threshold would **understate** US
tax more and more. So they are `FixedMoney`: range-validated and exported like any money
field, but left alone by `indexed()`.

Source: <https://www.irs.gov/pub/irs-drop/rp-25-32.pdf>;
<https://www.irs.gov/individuals/net-investment-income-tax>.

### 2026-07-28 — The citizenship seam: a narrow protocol behind a thin composite

`CitizenshipOverlay` sits next to `TaxRegime` with only the methods citizenship taxation
needs. It has no `purchase_costs` and no `state_pension_date`, because those are residence
concepts. `HouseholdTax` implements `TaxRegime` itself and holds a residence regime plus
any overlays, so `engine.py` still holds exactly one regime (invariant #1).

**The composite owns the ordering rule.** Residence tax comes first, and each overlay gets
that figure as its foreign-tax-credit input. Putting the order in the engine would make
the country-neutral layer take a position on international tax doctrine. For that input,
the residence tax is split per person pro rata by each person's share of the taxed base.
That is an approximation and is labelled as one: a progressive residence tax, or one with
allowances, is not linear in its base.

**`YearState.by_person` states ownership and stops there.** It carries what a person owns
outright and what the household owns jointly, neither divided up in advance. How much of a
joint holding falls inside another country's net follows from filing status, which is that
country's rule, so the overlay applies it.

**The composite is unconditional.** Every projection runs through it, even with nothing to
compose, so the overlay path is the only path and cannot rot.

### 2026-07-28 — FBAR and FATCA figures, and the exchange-rate trap

All figures below come from primary sources, checked 2026-07-28.

**FBAR (FinCEN Form 114)** is due when the aggregate value of foreign financial accounts
"exceeded $10,000 at any time during the calendar year reported": the total across all
accounts, at any moment, not at year end.

**Form 8938 thresholds for a filer living abroad** (Instructions Rev. November 2021; they
are not revised every year, so the date shows freshness, not the tax year). Either test
triggers:

| Filing status (abroad) | Last day of the tax year | Any time during the year |
| --- | --- | --- |
| Unmarried | > $200,000 | > $300,000 |
| Married filing jointly | > $400,000 | > $600,000 |
| Married filing separately | > $200,000 | > $300,000 |

These are the *abroad* figures. For an unmarried filer they are four times the domestic
ones.

**The exchange rate.** The Form 8938 instructions say: "In most cases, you must use the
U.S. Treasury Bureau of the Fiscal Service foreign currency exchange rate for purchasing
U.S. dollars", and "Use the currency exchange rate on the last day of the tax year".
Another public rate is allowed only where Treasury publishes none, and then the form must
disclose it. **So the ECB rate in `prices.py` is the wrong source here.** Reusing it would
be a compliance error, not an approximation, and the reporting helper has its own feed.

Both forms want the account's *maximum value during the year*, converted at the
*year-end* rate. A monthly engine computes that peak honestly; a person reading twelve
statements mostly cannot.

**The feed.** `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/rates_of_exchange`
needs no API key, returns JSON, and can be filtered by `country_currency_desc` and
`record_date`. Verified with a live call:

```text
?filter=country_currency_desc:eq:Euro Zone-Euro,record_date:eq:2025-12-31
→ {"exchange_rate":"0.851","record_date":"2025-12-31","effective_date":"2025-12-31"}
```

**Note the direction.** `exchange_rate` is units of foreign currency per one US dollar
(0.851 EUR to the dollar), the reciprocal of how `prices.py` stores the ECB rate. Getting
it the wrong way round would inflate every reported balance by roughly 38 %. It is a rate,
so it is `ExactDecimal` and never `Money` (invariant #4).

### 2026-07-28 — The NL–US re-sourcing article reaches the retained brokerage account

The case: a US citizen living in the Netherlands who holds US-domiciled funds in a
US brokerage account they kept. Dividends and gains from those funds are **US-source**, and
the foreign tax credit only relieves *foreign*-source income. The question is whether the
treaty rescues it.

**It does, and the saving clause does not get in the way.** Article 24(1) keeps each
state's right to tax its own nationals, but Article 24(2)(a) exempts Article 25 from that
by name.

**Article 25(6) is narrower than the summaries suggest.** It only reaches items of income
that, under the convention, are *exempt from US tax or subject to a reduced rate of US tax
when derived by a resident of the Netherlands who is not a United States citizen*. So each
type of income is checked against its own article:

- **Dividends qualify.** Article 10(2)(b) caps US tax at 15 % for a portfolio holder, and
  names Regulated Investment Companies explicitly, which is what a US-domiciled ETF is.
- **Capital gains qualify, more strongly.** Article 14(7): gains from property other than
  that in paragraphs 1–5 "shall be taxable only in the State of which the alienator is a
  resident". Securities are not in 1–5, so a non-citizen Dutch resident's gain is exempt
  from US tax outright.

**The treaty-rate tax stays.** Under 25(6)(b) the Netherlands credits the US tax the treaty
permits, and then the United States credits the remaining Dutch tax, but "the credit so
allowed shall not reduce the portion of the United States tax that is creditable against
the Netherlands tax". The US keeps its 15 % on dividends, and only US tax *above* the
treaty rate is relieved.

**Re-sourcing is capped.** Article 25(6)(c) treats the income as arising in the
Netherlands only "to the extent necessary to avoid double taxation of such income under
subparagraph (b)".

**It does not go in a separate treaty basket.** The Form 1116 instructions require a
separate Form 1116 per re-sourced amount, except for "income that is re-sourced by reason
of the relief from double taxation rules in any U.S. income tax treaty that is solely
applicable to U.S. citizens who are residents of the foreign treaty country". Article
25(6) is exactly that, so re-sourced income stays in the ordinary passive category.

**What the model does.** `tax/us/residence/nl.py` checks each income type against its own
treaty article, re-sources what qualifies into the passive basket, and charges the
treaty-rate US tax as a floor rather than crediting it away. Form 8833 disclosure is a
filing matter and outside the engine.

Sources, checked 2026-07-28: <https://www.irs.gov/pub/irs-trty/nether.pdf>
(Articles 10, 14, 24, 25); <https://www.irs.gov/pub/irs-pdf/i1116.pdf>
(Form 1116 instructions, "Certain Income Re-Sourced by Treaty");
<https://www.irs.gov/businesses/international-businesses/netherlands-technical-explanation>.

### 2026-07-28 — Box 3 is creditable against US tax, but by treaty rather than by § 901

**Box 3 is not a separate tax.** It is a box within *de inkomstenbelasting*, which Article
2(1)(a) of the 1992 US–Netherlands convention names as a covered tax. Article 2(2) extends
the convention to substantially similar later taxes, which covers the Wet IB 2001
restructuring that created the boxes.

**The § 901 route is the shakier one.** TD 9959 (87 FR 276, 4 January 2022) rewrote Treas.
Reg. § 1.901-2, adding an attribution requirement and realization, gross receipts and cost
recovery tests. Box 3 taxes an assumed yield and allows no recovery of actual costs, so
read strictly its § 901 creditability is doubtful.

**That reading is not the one in force.** Notice 2023-55 (21 July 2023) lets taxpayers apply
the *former* § 1.901-2(a) and (b), and Notice 2023-80 (11 December 2023) extended that
relief "until further notice". IRS Publication 514 for tax year 2025 still describes the
relief period as open. **This is the fact most likely to go stale:** the January
maintenance pass checks Publication 514 for its withdrawal.

**The WWR is the easier case.** It taxes actual return, so it meets the net gain
requirement far more easily than a deemed yield. Realization stays arguable for the
unrealized part.

**What the app applies.** Box 3 and the WWR are both creditable against US income tax,
sourced to the treaty. Where a projection depends on it, the app says so, because it rests
on relief that is explicitly temporary.

**NIIT is charged without a credit.** The 3.8 % tax sits in chapter 2A, outside the § 901
credit. *Christensen*, 168 Fed. Cl. 263 (2023) and *Bruyea*, 174 Fed. Cl. 238 (2024) held
otherwise on treaty grounds, but Treasury appealed both and the Federal Circuit
consolidated them in April 2025, undecided as of this entry. Charging NIIT without a
credit overstates US tax if the taxpayers win. The app takes the conservative side and
says which way it errs.

Sources, all checked 2026-07-28:
<https://www.irs.gov/pub/irs-trty/nether.pdf> (treaty text, Articles 2, 24, 25);
<https://www.federalregister.gov/documents/2022/01/04/2021-27887/guidance-related-to-the-foreign-tax-credit-clarification-of-foreign-derived-intangible-income>
(TD 9959); <https://www.irs.gov/pub/irs-drop/n-23-55.pdf>;
<https://www.irs.gov/pub/irs-drop/n-23-80.pdf>;
<https://www.irs.gov/publications/p514> (Publication 514, tax year 2025).

### 2026-07-28 — US figures are translated to euros at a flat yearly-average rate

`tax/us/parameters.yaml` is in USD, the only non-EUR parameter file. Comparing dollar
thresholds against euro amounts as if they were the same unit **understates** US tax.

**The law sets one rule for everything this app computes: the yearly average.**

- § 986(a)(1)(A) *requires* the yearly average rate for foreign income taxes claimed as a
  credit.
- Publication 54 allows the yearly average for income received evenly through the year. A
  projection's income is an annual figure with no dates inside it, so it qualifies.
- The spot-rate rule applies to a realization, and the engine already moves every
  realization to the annual pass.

**The assumed rate is flat.** Meese & Rogoff (1983) found that no structural exchange-rate
model beats a random walk out of sample, and a random walk's forecast is today's rate.
`Assumptions.usd_to_eur` defaults to 0.851, the Treasury rate at 2025-12-31. It carries no
`Provenance`, because nothing about 2065 can be sourced.

**Where it happens.** `TaxConfigBase.in_currency(rate)` translates every money figure once,
at the top of `USCitizenshipOverlay.annual_tax`, so the five federal modules do euro
arithmetic without knowing a rate exists. Translating the thresholds rather than the
amounts is the same arithmetic with less to get backwards. `in_currency` scales
`FixedMoney` and `indexed` does not: those two skip-lists are different, and mixing them
up would be a bug either way.

## Austria and the country seam

### 2026-10-21 — The residence regime returns a carry too: the WWR loss pool

The Wet werkelijk rendement (Kamerstuk 36748, as the Tweede Kamer passed it on
12 February 2026) carries a Box 3 loss forward. Art. 5.65: a negative income is a loss
"voor zover dit bedrag in absolute zin hoger is dan € 500". Art. 5.67: it is offset
against "de inkomens uit sparen en beleggen van de volgende kalenderjaren", which the
memorie van toelichting calls "onbeperkt in de tijd". Art. 5.1 takes it off the income
after the heffingsvrij resultaat.

**Same shape as the overlay carry.** `TaxRegime.next_carry` returns the per-run pool,
`HouseholdTax` stores it as `residence_carry` and hands it back on the next year's
`YearState`, and the engine never reads it. A change of residence drops it. That
**overstates** tax only for someone who moves back: the memorie van toelichting says
losses can go unused once Dutch tax liability ends, but nothing in art. 5.67 cancels a
loss that a returning resident could still offset.

**What it leaves out.** A fiscal partner pair is one taxpayer with one € 500 threshold,
the allocation the law allows that loses least to the threshold. Carryback is not
modelled: the one-year carryback amendment (nr. 43) is not in the passed text, and a
forward engine cannot reopen a reported year anyway. Persoonsgebonden aftrek is not
modelled, so it never creates or uses a loss.

### 2026-07-28 — `Person.sex` removed; Austria gets a flat pension age of 65

Austria's Regelpensionsalter for women rises 60 → 65 across 2024–2033, but reaches 65 at
the 1968-07-01 cohort. So the field only changed the answer for women born before mid-1968
taxed in Austria, and the cohort closes entirely in 2033. It also never worked:
`PersonRow.to_domain` left out `sex`, so a stored value never survived a round-trip.

**The flat 65 errs late**, which understates readiness rather than overstating it. It is a
stated omission in `tax/at/pension.py` next to the sourced schedule, so adding it back is a
lookup. Removing it took a parameter off `TaxRegime.state_pension_date`.

**The mapping stays fixed.** `PersonRow.to_domain` builds from the mapped columns like
`AccountRow` does, and a test guards it by comparing column values. A key-presence test
passed against the bug, because `model_dump()` emits every declared field whether or not
`to_domain` filled it in. The test's docstring says to give every nullable column a
non-default value.

### 2026-07-28 — AT fund taxation, income while held, and the loss offset

The regime models what dominates a comparison of staying in the Netherlands against moving to Austria.
`tax/at/regime.py`'s docstring lists what it leaves out, with the *direction* of each
error, so a number that flatters Austria is labelled as doing so.

**Income earned while holding.** `Account.distribution_yield` splits a holding's return
into dividends, coupons or interest and price growth. The engine accrues it monthly into
`YearState.income_by_treatment`, and AT charges KESt on it: 27.5% on securities and 25% on
deposits. It is a *decomposition*, not an addition: the balance still grows by
`return_assumption` alone, so taxing it does not inflate wealth. The default is 0.0.

**The step-up.** Income taxed while held raises the cost basis, or the same euro is taxed
again at sale (§ 186 Abs 3 InvFG). `annual_basis_step_up` handles it, spread across
accounts in proportion to the income each earned. NL returns zero: Box 3 creates no
acquisition cost.

**The second limb of a fund's deemed distribution.** `fund_realized_gain_yield` records
what the *fund* books by trading its own portfolio, which depends on its turnover and is
near zero for a physically replicating index ETF. It is separate from `distribution_yield`
because Austria deems 100% of income distributed but only 60% of realised gains. Both step
up the basis.

**Non-reporting funds** get their own `tax_treatment`, not a boolean on the account.
Austria taxes them on `max(90% of the year's rise, 10% of the year-end value)`, which
*replaces* what the fund earned, and the floor applies even in a losing year. This uses
`value_growth_by_treatment`, the year's change from returns alone. A US-domiciled ETF is a
non-reporting fund, which is the normal case for someone emigrating from the US.

**Within-year loss offset.** Withdrawal tax is computed on the year's *running* totals per
treatment, charging the difference from what is already taken, so a November loss reduces
the tax on a March gain. For a flat rate this equals charging each sale alone, so NL is
untouched. It resets with the tax year, because Austrian losses do not carry forward.

**Foreign withholding tax is not in the regime.** For an Austrian resident it usually nets
out: the source country takes ~15% under the treaty and Austria credits it against the
27.5%. What really leaks is withholding that can't be recovered *inside* an accumulating
fund, which the holder suffers wherever they live. So it belongs in `return_assumption`,
which is how net-return indices quote it.

**Purchase costs** receive `mortgage_amount`, because the Pfandrechtseintragungsgebuehr is
1.2% of the registered debt rather than of the price.

**The Einkommensteuer ladder** (`tax/at/income.py`) is built from config, so the yearly
kalte-Progression re-indexing is a data change. Social insurance is deducted before the
tariff; applying the bands to gross pay badly overstates Austrian tax. The 13th and 14th
salary (*Jahressechstel*) are taxed at a flat 6% above a Freibetrag, with a Freigrenze
below which they are free. A seven-band ladder fits in flat scalar fields; OpenFisca's
native `brackets:` scale is worth revisiting when a country needs one.

`annual_housing_adjustment` is ~0 for AT. There has been no mortgage-interest deduction
since the 2021 assessment and there is no imputed rent. Grundsteuer exists, but
Einheitswerte have not been revalued since 1973, so a typical house pays ~200 EUR/year,
and it is documented as not modelled.

### 2026-07-28 — G2: the five-method seam survives a realization tax, with three changes

A seam built around a Dutch *holding* tax survives Austria without a new concept, but
three changes came out of it:

1. **`annual_wealth_tax` became `annual_investment_tax`.** Austria taxes accumulating funds
   every year (§ 186 InvFG), so the method is not zero for AT; only its name was wrong.
   Renaming it kept the protocol from growing.
2. **`sweep_excluded_treatments()` split from `withdrawal_taxed_treatments()`.** The engine
   used one set both for "where `withdrawal_tax` can be non-zero" and "where surplus cash
   is never swept". Under AT an ordinary brokerage account is in the first set, so the
   sweep would have refused to invest at all. NL returns the lijfrente for both; AT
   returns its investment treatments for the first and only the locked pension wrappers
   for the second.
3. **`withdrawal_tax` takes a `realized_gain`.** KESt is 27.5% of proceeds minus
   acquisition cost. The engine carries a running basis per account, starting from
   `Account.cost_basis`, up with buys and down pro rata on sells. Pro-rata reduction *is*
   the `gleitender Durchschnittspreis` that § 27a Abs 4 Z 3 EStG requires. NL ignores the
   argument (a lijfrente uitkering is taxed on the gross).

### 2026-07-28 — Tax config schema: per-country classes, not one union; units by annotation

**Per-country subclasses.** `TaxConfigBase` keeps the year stamps, the provenance map,
indexing and range validation. `NLTaxConfig` declares the figures in `tax/nl/config.py`.
The loader takes the class: `parse_parameters(text, config_cls)`. Rejected: one union
config with every country's fields, mostly `None` (provenance on every field stops meaning
anything), and a generic `dict[str, Decimal]` (it loses typed fields, range validators and
the "no field without provenance" test).

**The seam is generic**, `TaxRegime[ConfigT: TaxConfigBase]`, so `NLTaxRegime` reads Dutch
fields with the type checker's help while `engine.py` holds `TaxRegime[Any]`. The regime
and config are paired by a country string at runtime, so `defaults_for` and
`resolve_tax_config` take an optional `expect=` that narrows the type and fails loudly on
another country's schema.

**Units come from the field annotation, not the YAML.** `_check_ranges` also runs inside
`resolve_tax_config`'s override path, where no YAML is in scope, so the class must
validate itself. Each field is declared `Money`, `Rate` or `Year`
(`Annotated[Decimal, Unit.MONEY]` etc.), and that one declaration drives indexing,
range-checking and the `unit:` the exporter writes. Descriptions live on the fields too,
so `scripts/export_tax_parameters.py` knows no country-specific name.

### 2026-07-28 — Un-defer the `accounts` scenario group rather than special-case the tornado

The sensitivity tornado varies `return_assumption`, which is per-`Account`. Rather than
give `solve.py` a private helper, the `accounts` group in `scenarios.py` is implemented, so
there is one path for changing a plan and the tornado cannot disagree with the scenario
comparison. Per-milestone patching stays unbuilt: no caller asks for it, and the
`milestones` group that only refused it has since been removed.

### 2026-07-27 — Open-source tax engines as a dependency: no; borrow PolicyEngine's parameter format

- **OpenFisca** has no production NL package with the rules that set this project apart
  (tegenbewijs, WWR verliesverrekening, HRA × EWF × Hillen). It vectorises across
  households per period, while this engine vectorises across MC runs and steps through
  months.
- **Catala** has no Dutch corpus, so adopting it means re-encoding `tax/nl/regime.py` in a
  niche DSL.
- **PSL Tax-Calculator** is US-only, and policyengine-us beats it.
- **PolicyEngine** is chosen, narrowly. Its parameter YAML is the living version of
  OpenFisca's format and maps ~1:1 onto `TaxConfig`; `status`/`verified_on` become
  extension keys. policyengine-us is the golden-test oracle for the US overlay, not an
  embedded dependency: it is too heavy for the Pyodide bundle.

**No project replaces the engine or the `TaxRegime` protocol.**

### 2026-07-25 — Country breadth (BE/CA/FR/DE/UK): no; depth over breadth

From the earlyretirementcalc parity audit. The depth on provenance, tegenbewijs, WWR and
fiscal partners is what sets this project apart. Also declined: MC yearly/std-dev modes, a
downgrade for a monthly engine.

## Design

### 2026-10-18 — Second design critique: 26/40 and 15/20, one regression filed

The first design pass shipped against design health **17/40** and audit health **11/20**.
The second critique ran over the browser build (the public demo): Today, Plan and its
three lenses, Flows, Settings, the demo gate and the account editor, at 1280 px and
375 px, light and dark, `nl` and `en`, with an overflow check at 320 px. It scored design
health **26/40** (Acceptable, top of the band) and audit health **15/20** (Good). Only the
two earlier totals survive, not their findings, so a regression can only be judged
against what the design pass promised. Most of it holds: axe (WCAG 2.2 AA, target size
included) reports no violations on any of the 48 captures, and no page scrolls sideways
at 375 px or 320 px.

**One promise had slipped, in the browser build only, and is fixed.** The design pass
moved the tax provenance up to a stamp under the Plan headline. The browser build showed
neither the stamp nor the Tax figures tab: its client sent every query string inside the
path, so `/api/tax-config?year=…` never reached its route. The client now passes the query
apart, and the browser-build test checks the stamp.

Two detector findings stay, on purpose:

- **"Radial-gradient halo" on the dark Plan surface is a false positive.** It is the
  scroll shadow of `.scroll-x-hint` on the deck tab strip, which tells a phone user more
  tabs exist. It is a cue, not decoration.
- **"Flat type hierarchy" on the Uncertainty lens is the Body Stays Small Rule.** Section
  headings there are `text-sm` uppercase labels, and DESIGN.md sets the hierarchy through
  weight, case and the display face rather than size steps.

The structural findings went on the board (the demo's first minute, Plan
readability, leaving the example household). The small ones were fixed in the same
change: chart age labels at 2.88:1, a colour-only outcomes chart, raw tax-treatment keys
in the account editor, an emoji that rendered as a missing-glyph box, a Flows total for
a part-year, and unlabelled assumption values on a phone.

## Scope

### 2026-07-24 — Multi-tenant (a version for tax advisors): parked

**Not started until an advisor has asked for it, and preferably paid.** The schema down
payment is made: `household_id` everywhere, `household_or_404`, nothing hardcodes it. So
multi-tenant would be a table *above* household. The code is the small half: an owner
table, auth, scoping, and the Postgres backend. The expensive half is looking after other
people's data: GDPR, processor agreements, backup and restore drills, breach exposure, and
an auth surface a `127.0.0.1` app never needed. And figures marked `provisional` in a
personal planner become advice in front of an advisor's client.

### 2026-07-25 — Box 3 aangifte figures: default no

Producing the numbers for a belastingaangifte is a short technical step, but it moves the
project from "a planner, figures marked provisional" to "tax software", with the yearly
deadlines, maintenance and liability that come with that. **The default is no.**

### 2026-07-24 — Allocation optimiser / efficient frontier: no

The allocation *comparison* is the version worth building. Mean-variance optimisation is
extremely sensitive to expected-return estimates with huge standard errors, and its inputs
would be the only figures here with no provenance. `gaussian_returns` correlates shocks per
`AccountKind`, five coarse buckets, so optimising gives "hold more equities". And the
constraints that bind are ones a frontier cannot see: PFIC restrictions, pension lock-ups,
the mortgage as leveraged property, the cash buffer.

### 2026-07-24 — Survivorship scenarios: not planned, revisit on demand

Survivor pensions (nabestaandenpensioen, Anw), single-person AOW, erfbelasting, a life
insurance that pays off the mortgage: a modelling project on the scale of a second tax
regime. Revisit on demand. One Wtp note: nabestaandenpensioen
is now risk-based only and *lapses when employment ends* (a 3–6 month uitloop), which
really hurts FIRE households and is worth a warning even while unmodelled. Sources:
[AFM nabestaandenpensioen](https://www.afm.nl/nl-nl/sector/pensioenuitvoerders/informeren-deelnemers/nabestaandenpensioen),
[Dirkzwager](https://www.dirkzwager.nl/kennis/artikelen/zo-werkt-het-nieuwe-nabestaandenpensioen).
If the receiving side of erfbelasting ships first, survivorship shares its tables.

### 2026-07-24 — Box 2 / BV route (DGA holdings), ZZP features: far backlog

A real community ask, but a heavy modelling project for a household this project doesn't
have. Territory for other users, after going public at the earliest.

### 2026-07-24 — Toeslagen modelling: no

FIRE trajectories pass the vermogenstoets almost immediately. At most a "vermogenstoets
exceeded" flag someday, never the full rules.

### 2026-07-24 — PSD2 / bank linking (bunq, GoCardless): no

It brings custody of OAuth tokens, a third-party data processor and bank APIs that break
every quarter, and undermines the "your data never leaves the machine" claim the browser
build stands on.

### 2026-07-24 — Alerts, notifications, scheduled emails: no

No server runs when the app is closed, and multi-tenant is the only future where one
would.

### 2026-07-24 — Multi-currency beyond display currency: no

Accounts carry a quote currency and everything settles in EUR. A second functional
currency makes FX gains a tax event: a modelling project, not a feature.

### 2026-07-24 — Replace-Actual-Budget ambition for the cash-flow view: undecided

Its own decision when the time comes, not folded into the activities-ledger track.

### 2026-07-24 — TypeScript engine port for the browser build: rejected

It would be a second implementation of eurocent arithmetic and the Box 3 rules, and the
golden baseline would stop testing what users run. The browser build is the same Python
via Pyodide.
