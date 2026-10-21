"""ATTaxRegime — the Austrian implementation of the country seam.

Comparison-grade for "what changes after a move to Austria", and now reasonably complete on
the things that dominate that answer: no wealth tax, KESt on what a holding throws off
each year and on the gain when it is sold, the punitive treatment of a non-reporting
fund, Austria's higher purchase costs, and the Regelpensionsalter.

**What is still approximate, and which way each one bends the answer.**

0. The women's Regelpensionsalter transition, which reaches 65 at the 1968-07-01 cohort.
   A flat 65 applies instead, so a woman born before then retires later here than the law
   allows — **understating** her readiness. See `pension.py` for why it is not modelled.

1. Foreign withholding tax on non-Austrian dividends. Deliberately *not* modelled here,
   because for an Austrian resident it usually nets out: the source country takes ~15%
   under the treaty and Austria credits it against the 27.5%, so the total is 27.5%
   either way. What genuinely leaks is unrecoverable withholding suffered *inside* an
   accumulating fund. That belongs in `Account.return_assumption`, not in a tax regime —
   it is suffered wherever the holder lives — and a net-return index already embeds it.
   Model it by quoting a net return.
2. The Regelbesteuerungsoption (§ 27a Abs 5 EStG), electing the progressive tariff when
   it is cheaper than 27.5%. Only helps low-income households; not modelling it
   **overstates** their tax.
3. Depot transfers where the acquisition cost is not transmitted, and the grandfathering
   cutoffs for pre-2011 holdings. Dead weight for a forward-looking projection.
4. Einkommensteuer detail beyond the tariff: the income-dependent Absetzbetraege, the
   Familienbonus, and the negative-tax SV-Rueckerstattung. All **understate** net income
   for those who qualify. See `income.py`.
5. A move to Austria keeps each account's running cost basis from before the move. A
   step-up to market value on arrival, where Austrian law grants one, is not modelled,
   so KESt on gains that built up before the move **overstates** the tax.

Figures: `parameters.yaml`. Sources are BMF, BMJ, WKO, AK, sozialversicherung.at and PV;
verified 2026-07-28.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

import numpy as np

from vuurtoren.tax.at.pension import pension_date
from vuurtoren.tax.regime import Limitation

if TYPE_CHECKING:
    from datetime import date

    from vuurtoren.tax.at.config import ATTaxConfig
    from vuurtoren.tax.regime import YearState

_LIMITATIONS = (
    Limitation(
        direction="understates",
        nl=(
            "Het Regelpensionsalter voor vrouwen loopt hier vlak op 65, zonder de "
            "overgangsregeling. Een vrouw geboren voor 1 juli 1968 gaat hier dus later "
            "met pensioen dan de wet toestaat."
        ),
        en=(
            "The women's Regelpensionsalter is flat at 65 here, without the transition "
            "that reaches 65 at the 1968-07-01 cohort. A woman born before then retires "
            "later here than the law allows."
        ),
    ),
    Limitation(
        direction="overstates",
        nl=(
            "De Regelbesteuerungsoption (§ 27a Abs 5 EStG) ontbreekt: het progressieve "
            "tarief kiezen als dat goedkoper is dan 27,5%. Dat helpt alleen lagere "
            "inkomens, waarvoor de belasting hier dus te hoog uitvalt."
        ),
        en=(
            "The Regelbesteuerungsoption (§ 27a Abs 5 EStG) — electing the progressive "
            "tariff when it beats 27.5% — is not modelled. It only helps lower incomes, "
            "whose tax therefore reads too high here."
        ),
    ),
    Limitation(
        direction="overstates",
        nl=(
            "Van de Einkommensteuer zit alleen het tarief erin. De "
            "inkomensafhankelijke Absetzbetraege, de Familienbonus en de negatieve "
            "SV-Rueckerstattung ontbreken, dus je netto-inkomen is hier te laag."
        ),
        en=(
            "Only the Einkommensteuer tariff is modelled. The income-dependent "
            "Absetzbetraege, the Familienbonus and the negative-tax SV-Rueckerstattung "
            "are absent, so net income reads too low here."
        ),
    ),
    Limitation(
        direction="either",
        nl=(
            "Buitenlandse bronbelasting op dividenden zit niet in het regime: onder het "
            "verdrag valt die meestal weg tegen de 27,5%. Wat wel lekt is niet-"
            "verrekenbare bronbelasting binnen een fonds — zet die in het "
            "rendementspercentage van de rekening."
        ),
        en=(
            "Foreign withholding tax on dividends is not modelled here — under the "
            "treaty it usually nets out against the 27.5%. What does leak is "
            "unrecoverable withholding suffered inside a fund; quote it in the account's "
            "return assumption instead."
        ),
    ),
    Limitation(
        direction="overstates",
        nl=(
            "Na een verhuizing naar Oostenrijk houdt elke rekening haar aankoopwaarde "
            "van voor de verhuizing. Een opwaardering naar de marktwaarde bij aankomst, "
            "waar de Oostenrijkse wet die geeft, ontbreekt, dus de KESt op winst van voor "
            "de verhuizing valt te hoog uit."
        ),
        en=(
            "After a move to Austria each account keeps its cost basis from before the "
            "move. A step-up to market value on arrival, where Austrian law grants one, "
            "is not modelled, so KESt on gains from before the move reads too high."
        ),
    ),
)
"""What this regime does not model. See `ATTaxRegime.limitations`.

The module docstring above is the engineering record and goes further — why each is not
modelled, and which sibling module owns it. This is the same list for a reader of the
*result*, so the two are kept in step by hand: adding a numbered paragraph up there means
adding a line here.
"""

# Austria taxes by realization, so the treatments describe *what a thing is* rather than
# which annual box it falls in — there is no Austrian equivalent of Box 1 vs Box 3.
BANK = "at.bank"
INVESTMENT = "at.investment"
NONREPORTING = "at.investment_nonreporting"
"""A fund not on the OeKB reporting list — a US-domiciled ETF, typically.

Its own treatment rather than a flag on the account, because that is exactly what a
tax_treatment is: a country-scoped classification only the regime interprets. Austria
taxes it on a punitive lump-sum estimate instead of on what it actually earned, which is
a different calculation, not a different rate.
"""
DEBT = "at.debt"
HOME = "at.home"
PENSION = "at.pension"
NONE = "at.none"

_TREATMENTS = frozenset({BANK, INVESTMENT, NONREPORTING, DEBT, HOME, PENSION, NONE})
# Securities treatments, as opposed to deposits — the 27.5% bucket.
_SECURITIES = frozenset({INVESTMENT, NONREPORTING})
# KESt falls due when an investment is sold. Bank interest is taxed too (at 25%), but
# the engine cannot separate it from ordinary cash flows, so BANK is absent here for the
# same reason it is absent under NL.
_WITHDRAWAL_TAXED = frozenset({INVESTMENT, NONREPORTING})
# Nothing about Austrian tax makes a brokerage account a bad place for surplus cash —
# this is exactly the case that forced `sweep_excluded_treatments` apart from
# `withdrawal_taxed_treatments`. Only the locked pension wrapper is off-limits.
_SWEEP_EXCLUDED = frozenset({PENSION})
# No annual tax is charged on holdings (see the module docstring on AgE), so nothing
# needs an actual-return base — that concept is the Dutch tegenbewijs, not an Austrian one.
_ACTUAL_RETURN_TREATMENTS: frozenset[str] = frozenset()

_CENTS = Decimal("0.01")


class ATTaxRegime:
    """The Austrian `TaxRegime`. See `vuurtoren.tax.regime.TaxRegime` for the contract."""

    country = "AT"

    @property
    def limitations(self) -> tuple[Limitation, ...]:
        """See `_LIMITATIONS`."""
        return _LIMITATIONS

    def annual_investment_tax(self, s: YearState, cfg: ATTaxConfig) -> np.ndarray:
        """KESt on what a holding threw off this year — nothing on the holding itself.

        Austria abolished the Vermoegensteuer in 1994, so wealth is never taxed for being
        wealth. What is taxed annually is a fund's ausschuettungsgleiche Ertraege, which
        fall due even when the fund accumulates and nothing is sold, plus bank interest
        on receipt. Three bases, per § 186 InvFG:

        - a reporting fund's ordinary income, in full;
        - a reporting fund's own realised gains, at `fund_deemed_gain_share` (60%);
        - a **non-reporting** fund's lump-sum estimate, which replaces both:
          `max(90% of the year's rise, 10% of the year-end value)`. The floor bites even
          in a year the fund fell, which is what makes it punitive.

        Securities are charged at 27.5% and deposits at 25%.
        """
        zero = np.zeros_like(s.home_value)
        bank = np.maximum(0.0, s.income_by_treatment.get(BANK, zero))
        securities = sum(self._securities_base(s, cfg).values(), start=zero)
        return securities * float(cfg.kest_rate) + bank * float(cfg.kest_bank_interest_rate)

    def _securities_base(self, s: YearState, cfg: ATTaxConfig) -> dict[str, np.ndarray]:
        """The 27.5% base for the year per securities treatment, and only that.

        It is what the annual charge falls on, and `annual_basis_step_up` returns it
        unchanged, which is the point of it being one method: the euro that was charged
        here is the euro whose basis rises, so a later sale cannot tax it a second time.
        Computing the step-up from the raw reported figures instead would double-tax the
        whole gap between a non-reporting fund's lump-sum estimate and what it actually
        reported.
        """
        zero = np.zeros_like(s.home_value)
        income = s.income_by_treatment
        fund_gains = s.fund_realized_gains_by_treatment
        base = {
            k: np.maximum(0.0, income.get(k, zero))
            + np.maximum(0.0, fund_gains.get(k, zero)) * float(cfg.fund_deemed_gain_share)
            for k in _SECURITIES
            if k in income or k in fund_gains
        }
        # A non-reporting fund is estimated instead of measured, so whatever income and
        # gains it reported are replaced rather than added to.
        nonreporting = s.balances_by_treatment.get(NONREPORTING)
        if nonreporting is not None:
            growth = s.value_growth_by_treatment.get(NONREPORTING, zero)
            base[NONREPORTING] = np.maximum(
                np.maximum(0.0, growth) * float(cfg.nonreporting_gain_share),
                np.maximum(0.0, nonreporting) * float(cfg.nonreporting_minimum_share),
            )
        return base

    def next_carry(self, s: YearState, cfg: ATTaxConfig) -> None:
        """None: the annual charge carries nothing into the next year."""
        del s, cfg

    def annual_basis_step_up(self, s: YearState, cfg: ATTaxConfig) -> dict[str, np.ndarray]:
        """The income just taxed raises the basis, so a later sale cannot tax it again.

        § 186 Abs 3 InvFG states it outright for deemed distributions. Bank interest is
        excluded: a deposit has no acquisition cost to step up, and the engine never
        charges KESt on withdrawing one. A non-reporting fund steps up by the lump-sum
        estimate it was charged on, not by what it reported — see `_securities_base`.
        """
        return self._securities_base(s, cfg)

    def annual_housing_adjustment(self, s: YearState, cfg: ATTaxConfig) -> np.ndarray:
        """Zero: no mortgage-interest deduction and no imputed rent on an own home.

        The Topfsonderausgaben deduction for owner-occupied housing was phased out and
        could be claimed for the last time in the 2021 assessment; Austria has never had
        an eigenwoningforfait equivalent. Grundsteuer exists but the Einheitswerte behind
        it have not been revalued since 1973, so a typical house pays about 200 EUR a
        year — around 0.05% of value, below the resolution of a FIRE projection.
        """
        del cfg
        return np.zeros_like(s.home_value)

    def purchase_costs(
        self,
        price: Decimal,
        *,
        buyer_age: int,
        own_occupancy: bool = True,
        starter_exemption_used: bool,
        mortgage_amount: Decimal,
        cfg: ATTaxConfig,
    ) -> tuple[Decimal, bool]:
        """Grunderwerbsteuer and the Grundbuch fees, on two different bases.

        GrESt (3.5%) and the Eintragungsgebuehr (1.1%) are charged on the price; the
        Pfandrechtseintragungsgebuehr (1.2%) is charged on the mortgage registered, so a
        cash purchase avoids it entirely and a fully financed one pays it on close to the
        whole price.

        Austria has no first-time-buyer relief, so `buyer_age`, `own_occupancy` and
        `starter_exemption_used` are ignored and nothing is ever consumed. (The 2024-2026
        Eintragungsgebuehr waiver for a primary residence was a registration-fee relief,
        not a GrESt one, and it expired on 2026-06-30.) The returned flag is always False
        so the caller's exemption state is left untouched.
        """
        del buyer_age, own_occupancy, starter_exemption_used
        duty = (
            price * (cfg.grunderwerbsteuer_rate + cfg.land_register_fee_rate)
            + max(Decimal(0), mortgage_amount) * cfg.mortgage_registration_fee_rate
        )
        return duty.quantize(_CENTS, rounding=ROUND_HALF_UP), False

    def state_pension_date(self, birth_date: date, *, growth: int) -> date:
        """The Regelpensionsalter: a flat 65.

        `growth` is ignored: it is the household's assumption about the AOW tracking life
        expectancy, which is a Dutch legal mechanism. Austria's 65 has no scheduled rise,
        so applying the drift here would invent one.

        The women's transition is not modelled — see `tax/at/pension.py` for why, and
        which way the omission bends.
        """
        del growth
        return pension_date(birth_date)

    def gift_tax_free_amount(
        self,
        amount: Decimal,
        *,
        recipient_birth_date: date,
        gift_date: date,
        onetime_used: bool,
        cfg: ATTaxConfig,
    ) -> Decimal:
        """The whole gift: Austria abolished Schenkungssteuer in 2008.

        A gift is fully tax-free regardless of size or the recipient's age, so the
        engine's "a gift above its exemption fails loudly" guard can never fire here.
        Gifts above 50,000 EUR between relatives in twelve months must be *reported*
        (Schenkungsmeldepflicht, § 121a BAO), but reporting is not tax and the engine
        does not model it. Gifted real estate is not free — it attracts GrESt on a
        separate scale — but that arrives as a property milestone, not as a gift.
        """
        del recipient_birth_date, gift_date, onetime_used, cfg
        return amount

    def withdrawal_tax(
        self,
        amount: np.ndarray,
        *,
        treatment: str,
        realized_gain: np.ndarray,
        owner_person_id: int | None,  # noqa: ARG002  # country-neutral seam; only an overlay reads it
        year: int,  # noqa: ARG002  # cfg is already resolved for it; only an overlay needs the year
        cfg: ATTaxConfig,
    ) -> np.ndarray:
        """KESt at 27.5% of the realized gain — not of the gross proceeds.

        This is the whole difference between a realization tax and a holding tax, and it
        is why the engine carries a cost basis: taxing `amount` would tax the return of
        capital. A sale at or below basis realizes nothing and is charged nothing; losses
        are floored at zero rather than credited, because Austrian capital losses cannot
        be carried forward (module docstring, limitation 2).
        """
        if treatment not in _SECURITIES:
            return np.zeros_like(amount)
        # float() at the last moment: the engine is float64 arrays inside, and the rate
        # reached here as an exact Decimal from parameters.yaml (invariant #4).
        return np.maximum(0.0, realized_gain) * float(cfg.kest_rate)

    def withdrawal_taxed_treatments(self) -> frozenset[str]:
        """Investments only: KESt falls due on sale — see `_WITHDRAWAL_TAXED`."""
        return _WITHDRAWAL_TAXED

    def sweep_excluded_treatments(self) -> frozenset[str]:
        """Just the pension wrapper — see `_SWEEP_EXCLUDED`."""
        return _SWEEP_EXCLUDED

    def valid_treatments(self) -> frozenset[str]:
        """The `at.*` tax_treatment keys an Account may carry under this regime."""
        return _TREATMENTS

    def actual_return_treatments(self) -> frozenset[str]:
        """Empty: the actual-return base is a Dutch concept — see `_ACTUAL_RETURN_TREATMENTS`."""
        return _ACTUAL_RETURN_TREATMENTS
