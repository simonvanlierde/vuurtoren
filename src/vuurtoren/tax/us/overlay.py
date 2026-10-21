"""`USCitizenshipOverlay` — the five federal pieces composed behind the seam.

`HouseholdTax` computes the residence tax first and hands it here as the foreign-tax-credit
input; this module turns one person's year into a US charge on top of it. Nothing under
`tax/us/federal/` knows about the Netherlands, and nothing here reads an `nl.*` key.

**The only cross-year state in the design is this overlay's `USCarry`** — the § 904(c)
credit bank and the § 1296 loss pool, both per run. `annual_tax` takes last year's carry
and returns the next one rather than holding it, so asking about the same year twice is
harmless and the caller decides which answer is the charged one. The carry is opaque to
everyone outside `tax/us/`: `HouseholdTax` stores it and hands it back, nothing reads it.
The federal modules stay pure functions of (year, state).

**The order is PFIC, ordinary, preferential, NIIT, then the credit.** Each step feeds the
next: the mark-to-market inclusion is ordinary income, ordinary taxable income is where
the preferential thresholds are read from, and the credit relieves everything except the
NIIT.

**Sourcing lives here, relief lives in `residence/`.** Which income is US-source is § 861
and § 865 — federal law, the same wherever the person lives — so this module decides it:
`us.non_pfic` is the retained US brokerage account and is US-source, everything else is
foreign-source already. What a treaty then does to that US-source income is the residence
layer's answer, looked up by the household's tax country. A residence with no treaty
module gets no relief and its US-source income is limited out of the credit, which is the
statute's own answer.

**The figures are USD and the engine's arrays are EUR, and this is where they meet.** The
whole config is translated once, at the top of `annual_tax`, so every federal module below
works in euros without knowing a rate exists. One boundary rather than five, and it is the
config that moves rather than the amounts — translating the thresholds is the same
arithmetic as translating the income and leaves far less to get backwards.

The rate is the *yearly average*, which is what § 986(a)(1)(A) requires for creditable
foreign taxes and what Publication 54 allows for income received evenly through the year.
A projection's income is annual with no dates inside it, so the average is both the
mandated rule and the only one it can honestly apply — the spot-rate-on-the-day rule for a
realization has no date to read. `Assumptions.usd_to_eur` carries the value and the
reasoning for holding it flat.

Two simplifications, each stated with its direction:

- **Income on `us.non_pfic` is treated as qualified dividends**, everything else as
  ordinary. That is right for a US-domiciled fund or individual stocks, which is what the
  key means; a non-qualified dividend classified this way would be undertaxed.
- **Every non-PFIC realized gain is treated as long-term**, so it meets the preferential
  ladder. A holding the cash sweep sells in a FIRE projection has almost always been held
  over a year; where it has not, a short-term gain is ordinary and this understates it.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np

from vuurtoren.tax.us.federal import ftc, income, investment, pfic
from vuurtoren.tax.us.residence import REGISTRY

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vuurtoren.domain import Account, FilingStatus, Person
    from vuurtoren.tax.overlay import PersonSlice
    from vuurtoren.tax.us.config import USTaxConfig

NON_PFIC = "us.non_pfic"
"""A US-domiciled fund or individual stocks — the retained-brokerage case."""

RETIREMENT = "us.retirement"
"""Reserved for a foreign pension wrapper. Recognised so an account can carry it, but not
modelled: what a treaty does to a Dutch pension is phase 4's question at the earliest."""

_JOINT_SHARE: dict[FilingStatus, float] = {
    "single": 1.0,
    "married_filing_separately": 0.5,
    "married_filing_jointly": 1.0,
}
"""How much of a jointly held account falls inside the US net, by filing status.

The attribution table. It lives here and not in the engine because it is a US tax rule:
`PersonSlice` states plain ownership and this applies the fraction, which is what lets a
second citizenship overlay — were one ever to exist — disagree about the share.
"""


def check_filing_statuses(us_people: Sequence[Person]) -> None:
    """Refuse a joint return the overlays cannot compute.

    Each US person's overlay is its own return. Married filing jointly is one return for
    the couple, so it is modelled only for a lone US person (with a non-US spouse, under
    a § 6013(g) election). With two US people, each overlay would charge the joint
    return's tax on the joint income and the household would pay it twice.
    """
    joint = [p.name for p in us_people if p.us_filing_status == "married_filing_jointly"]
    if joint and len(us_people) != 1:
        msg = (
            f"married_filing_jointly is modelled only for a household with one US person; "
            f"{', '.join(joint)} file jointly alongside another US person. Record each as "
            "married_filing_separately instead"
        )
        raise ValueError(msg)


def _combined(
    owned: dict[str | None, np.ndarray], joint: dict[str | None, np.ndarray], share: float
) -> dict[str | None, np.ndarray]:
    """`owned + share * joint`, per overlay treatment."""
    out = dict(owned)
    for key, value in joint.items():
        out[key] = out[key] + value * share if key in out else value * share
    return out


@dataclass(frozen=True)
class USCarry:
    """What one US person's year leaves for the next, per run.

    `credit_bank` is the § 904(c) carryforward, newest year last; `pfic_pool` is the
    § 1296 unreversed inclusions, None before the first year.
    """

    credit_bank: tuple[np.ndarray, ...] = ()
    pfic_pool: np.ndarray | None = None


@dataclass(frozen=True)
class USCitizenshipOverlay:
    """One US person's federal charge, on top of whatever they already paid at home.

    Holds no year: the cross-year state travels as a `USCarry` in and out of `annual_tax`.
    """

    person: Person
    residence: str
    """The household's tax country, which is what picks the treaty rules.

    Taken from the residence regime the projection starts under, like the pension unlock
    date: a mid-horizon `ChangeTaxResidence` does not re-pick the treaty. Somebody who
    moves country mid-projection has a filing problem this app is not the place to solve.
    """

    usd_to_eur: Decimal = Decimal(1)
    """Euros per dollar. Defaults to 1 — an explicit "no translation", for the unit tests
    that check a federal figure against the statute in its own currency. Every projection
    passes the household's assumption; see `Assumptions.usd_to_eur` for the rule and why
    it is a yearly average."""

    citizenship: str = "US"

    _treatments: frozenset[str] = field(
        default_factory=lambda: frozenset({NON_PFIC, pfic.MTM, pfic.UNELECTED, RETIREMENT})
    )

    @property
    def filing_status(self) -> FilingStatus:
        """The recorded status, defaulting to single when none was given.

        Single rather than MFS, because an unrecorded status most often means an
        unmarried filer; where it does not, single is the *less* punitive schedule at the
        top band and so understates the tax for a married-filing-separately expatriate.
        The frontend asks for it explicitly (phase 5) rather than leaning on this.
        """
        return self.person.us_filing_status or "single"

    def annual_tax(
        self,
        s: PersonSlice,
        cfg: USTaxConfig,
        *,
        residence_tax: np.ndarray,
        carry: USCarry | None,
    ) -> tuple[np.ndarray, USCarry]:
        """The year's US charge for this person, per run, net of the foreign tax credit.

        `carry` is what last year's call returned, None for the first year. Returns the
        charge and the carry for next year; `carry` itself is never changed.
        """
        if carry is None:
            carry = USCarry()
        # The one place dollars become euros. Everything below — the ladders, the
        # thresholds, the treaty floor — is euro arithmetic against euro arrays.
        cfg = cfg.in_currency(self.usd_to_eur)
        status = self.filing_status
        share = _JOINT_SHARE[status]
        zero = np.zeros_like(s.earned_income)
        earned = s.earned_income

        by_treatment = _combined(s.owned.income, s.joint.income, share)
        growth = _combined(s.owned.value_growth, s.joint.value_growth, share)
        sold = _combined(s.owned.realized_gains, s.joint.realized_gains, share)

        inclusion, pfic_pool = pfic.mark_to_market_inclusion(
            growth.get(pfic.MTM, zero),
            unreversed_inclusions=zero if carry.pfic_pool is None else carry.pfic_pool,
        )
        # Selling a marked-to-market holding realizes only what the yearly marks have not
        # already taxed, and that residue is ordinary (§ 1296(c)(1)(A)), never
        # preferential. The pool is left standing: the holding usually survives a partial
        # sale, and not drawing it down over-shelters a later one — understating tax in
        # the uncommon case where a PFIC is sold down in stages.
        pfic_sold = pfic.sale_gain_after_step_up(
            sold.get(pfic.MTM, zero), unreversed_inclusions=pfic_pool
        )

        qualified = by_treatment.get(NON_PFIC, zero)
        other_investment = sum(
            (v for k, v in by_treatment.items() if k != NON_PFIC), start=zero.copy()
        )
        # Every non-PFIC gain is treated as long-term. A holding sold by the cash sweep in
        # a FIRE projection has almost always been held over a year; where it has not, a
        # short-term gain is ordinary income and this understates the tax.
        long_term = sum((v for k, v in sold.items() if k != pfic.MTM), start=zero.copy())

        ordinary_base = other_investment + inclusion + pfic_sold
        taxable = income.taxable_income(earned, ordinary_base, status=status, cfg=cfg)
        excluded = income.excluded_earned_income(earned, cfg=cfg)
        ordinary = income.ordinary_tax(taxable, excluded=excluded, status=status, cfg=cfg)
        # Whatever the deduction did not absorb comes off the preferential base instead —
        # otherwise a retiree living on qualified dividends alone would lose it entirely.
        spare = income.unused_deduction(earned, ordinary_base, status=status, cfg=cfg)
        # § 911(f)(2): the preferential slice starts above the excluded wages too, as on
        # the Foreign Earned Income Tax Worksheet. Stacked on `taxable` alone, dividends
        # beside an excluded salary would land in the 0 % band.
        preferential = investment.preferential_tax(
            np.maximum(0.0, qualified + long_term - spare),
            ordinary_taxable=taxable + excluded,
            status=status,
            cfg=cfg,
        )

        net_investment_income = qualified + long_term + other_investment + inclusion + pfic_sold
        # § 1411(d): modified AGI adds the § 911 exclusion back, so the NIIT threshold is
        # read against gross earnings. Netting the exclusion off first would let a high
        # earner abroad slip under a threshold Congress fixed in nominal dollars.
        magi = earned + net_investment_income
        niit = investment.net_investment_income_tax(
            net_investment_income, modified_agi=magi, status=status, cfg=cfg
        )

        total_income = earned + net_investment_income
        # § 861/§ 865: the retained US brokerage account's dividends and gains arise in the
        # United States. A Dutch salary, Dutch bank interest and a UCITS holding do not.
        us_source = qualified + sold.get(NON_PFIC, zero)
        treaty = REGISTRY.get(self.residence)
        relief = (
            treaty.relief(
                us_source_dividends=qualified,
                us_source_gains=sold.get(NON_PFIC, zero),
                year=cfg.year,
            )
            if treaty is not None
            else None
        )
        resourced = relief.resourced if relief is not None else zero

        gross = ordinary + preferential
        # § 911(d)(6): excluded wages earn no credit, so they leave both sides of the
        # § 904 fraction. Left in, they counted as foreign-source income and let foreign
        # tax on other income shelter US tax on US-source dividends.
        after_credit, credit_bank = ftc.apply_credit(
            gross,
            foreign_tax_paid=residence_tax,
            foreign_source_income=total_income - excluded - us_source + resourced,
            total_income=total_income - excluded,
            carryforward=carry.credit_bank,
        )
        # Article 25(6)(b) and its analogues: the treaty relieves down to the rate it
        # permits the United States to charge, never past it. Clamped to the tax that
        # actually arose — a treaty preserves a portion of a tax, it does not create one.
        # NOTE: the credit spent above is computed before this floor puts tax back, so the
        # bank is drawn down as though the floor were not there. That leaves less
        # carryforward for later years and so overstates US tax, never understates it.
        if relief is not None:
            after_credit = np.maximum(after_credit, np.minimum(relief.preserved_us_tax, gross))
        return after_credit + niit, USCarry(credit_bank=credit_bank, pfic_pool=pfic_pool)

    def withdrawal_tax(
        self,
        amount: np.ndarray,  # noqa: ARG002  # realization is charged annually, not per sale
        *,
        treatment: str,  # noqa: ARG002  # for the same reason, for every treatment
        realized_gain: np.ndarray,
        cfg: USTaxConfig,  # noqa: ARG002  # the figures are read by `annual_tax` instead
    ) -> np.ndarray:
        """Zero at the moment of sale — the charge lands in `annual_tax` instead.

        Not a gap: a US capital gain meets a *graduated* schedule whose bands are read
        against the year's total taxable income, so a sale in March cannot be priced
        until December. Charging it here would mean guessing that income or picking a
        flat rate, and both are worse than putting the gain where the rest of the year
        already is. The engine hands the year's realized gains to `annual_tax` through
        `PersonSlice.realized_gains`.

        It stays implemented rather than removed because the protocol has it and a future
        residence country might tax a US person's sale at the moment it happens.
        """
        return np.zeros_like(realized_gain)

    def valid_treatments(self) -> frozenset[str]:
        """The `overlay_treatment` keys this overlay understands."""
        return self._treatments

    def validate_accounts(self, accounts: Sequence[Account], *, person: Person) -> None:
        """Refuse an unelected PFIC, and any key this overlay cannot read."""
        unknown = sorted(
            {
                f"{a.name}={a.overlay_treatment}"
                for a in accounts
                if a.overlay_treatment is not None and a.overlay_treatment not in self._treatments
            }
        )
        if unknown:
            msg = (
                f"account(s) with an overlay_treatment the US overlay does not know: "
                f"{unknown}. Valid: {sorted(self._treatments)}"
            )
            raise ValueError(msg)
        pfic.check_no_unelected_pfic(accounts, person=person)
