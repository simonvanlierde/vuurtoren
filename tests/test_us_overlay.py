"""`USCitizenshipOverlay`: filing-status attribution, composition order, and its state."""

import numpy as np
import pytest

from vuurtoren.domain import Account, AccountKind, FilingStatus, Person
from vuurtoren.tax.config import defaults_for
from vuurtoren.tax.overlay import PersonSlice, TreatmentMaps, overlays_for
from vuurtoren.tax.us.config import USTaxConfig
from vuurtoren.tax.us.federal import pfic
from vuurtoren.tax.us.overlay import NON_PFIC, USCitizenshipOverlay

CFG = defaults_for("US", 2026, expect=USTaxConfig)


def _one(x: float) -> np.ndarray:
    return np.array([x])


def _person(status: FilingStatus | None = "single", *, us: bool = True) -> Person:
    return Person(id=1, household_id=1, name="Sam", us_person=us, us_filing_status=status)


def _slice(
    *,
    earned: float = 0.0,
    owned: dict[str | None, float] | None = None,
    joint: dict[str | None, float] | None = None,
    growth: dict[str | None, float] | None = None,
    sold: dict[str | None, float] | None = None,
) -> PersonSlice:
    return PersonSlice(
        person_id=1,
        owned=TreatmentMaps(
            income={k: _one(v) for k, v in (owned or {}).items()},
            value_growth={k: _one(v) for k, v in (growth or {}).items()},
            realized_gains={k: _one(v) for k, v in (sold or {}).items()},
        ),
        joint=TreatmentMaps(income={k: _one(v) for k, v in (joint or {}).items()}),
        earned_income=_one(earned),
    )


def _charge(overlay: USCitizenshipOverlay, s: PersonSlice, *, residence_tax: float = 0.0) -> float:
    return float(overlay.annual_tax(s, CFG, residence_tax=_one(residence_tax), carry=None)[0][0])


def test_a_salary_inside_the_exclusion_costs_nothing() -> None:
    """The common expat year: a Dutch salary, fully excluded, no US charge."""
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")

    assert _charge(overlay, _slice(earned=90_000.0)) == pytest.approx(0.0)


def test_a_salary_above_the_exclusion_is_charged() -> None:
    """And it is charged at the rate the whole salary would have met — § 911(f)."""
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")

    charged = _charge(overlay, _slice(earned=250_000.0))

    assert charged > 0.0


def test_preferential_income_stacks_on_top_of_the_excluded_salary() -> None:
    """§ 911(f)(2): qualified dividends are taxed where they land above the excluded wages.

    The Foreign Earned Income Tax Worksheet for $100,000 of excluded wages and $50,000 of
    qualified dividends, single, 2026: taxable income is 50,000 - 16,100 = 33,900, all of
    it dividends. Re-adding the exclusion gives 133,900, where the ordinary part (the
    100,000) already fills the 0 % band, so the 33,900 meets 15 %: 5,085. Stacked on the
    33,900 alone, it fell inside the 0 % band and was taxed at nothing. A country with
    no treaty module, so no floor or re-sourcing touches the result.
    """
    overlay = USCitizenshipOverlay(person=_person(), residence="XX")
    s = _slice(earned=100_000.0, owned={NON_PFIC: 50_000.0})

    assert _charge(overlay, s) == pytest.approx(0.15 * (50_000.0 - 16_100.0))


def test_the_credit_limitation_leaves_out_the_excluded_salary() -> None:
    """§ 911(d)(6): excluded wages are not foreign-source income for the § 904 fraction.

    The same year as above, for a resident of Austria paying KESt on the dividends. The
    dividends are US-source, so the foreign-source taxable income is zero and so is the
    credit: the whole 5,085 stays due, and the KESt is banked. Counting the excluded
    100,000 as foreign-source credited two thirds of it away.
    """
    overlay = USCitizenshipOverlay(person=_person(), residence="AT")
    s = _slice(earned=100_000.0, owned={NON_PFIC: 50_000.0})

    charge, carry = overlay.annual_tax(s, CFG, residence_tax=_one(13_750.0), carry=None)

    assert float(charge[0]) == pytest.approx(5_085.0)
    assert float(carry.credit_bank[-1][0]) == pytest.approx(13_750.0)


def test_married_filing_separately_takes_half_of_a_joint_account() -> None:
    """The attribution table, applied by the overlay and never by the engine.

    Filing status is held fixed and only the *ownership* varies, because MFS and MFJ are
    different schedules as well as different shares — comparing the two statuses would
    measure the band widths rather than the attribution.
    """
    status: FilingStatus = "married_filing_separately"

    def charge(**where: dict[str | None, float]) -> float:
        return _charge(
            USCitizenshipOverlay(person=_person(status), residence="NL"),
            _slice(earned=200_000.0, **where),
        )

    outright = charge(owned={NON_PFIC: 100_000.0})
    jointly_held = charge(joint={NON_PFIC: 100_000.0})
    half_outright = charge(owned={NON_PFIC: 50_000.0})

    assert jointly_held == pytest.approx(half_outright)
    assert jointly_held < outright


def test_a_joint_filer_takes_the_whole_joint_account() -> None:
    """The other row of the table: electing jointly brings all of it into the net."""
    status: FilingStatus = "married_filing_jointly"

    def charge(**where: dict[str | None, float]) -> float:
        return _charge(
            USCitizenshipOverlay(person=_person(status), residence="NL"),
            _slice(earned=200_000.0, **where),
        )

    assert charge(joint={NON_PFIC: 100_000.0}) == pytest.approx(charge(owned={NON_PFIC: 100_000.0}))


def test_an_unrecorded_filing_status_falls_back_to_single() -> None:
    """Phase 5 asks for it explicitly; this is what happens until it does."""
    overlay = USCitizenshipOverlay(person=_person(None), residence="NL")

    assert overlay.filing_status == "single"


def test_a_high_dutch_tax_bill_credits_the_us_charge_away() -> None:
    """The reason a US person in the Netherlands usually owes nothing and still files."""
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")
    # Under the NIIT threshold on purpose: that charge is uncredited by design and is
    # what `test_the_niit_survives_the_credit` covers. Unclassified — a Dutch bank
    # account — because it must be *foreign*-source for the credit to reach all of it;
    # US-source income keeps its treaty-rate tax, which test_us_residence.py covers.
    year = _slice(owned={None: 150_000.0})

    uncredited = _charge(USCitizenshipOverlay(person=_person(), residence="NL"), year)
    credited = _charge(overlay, year, residence_tax=uncredited * 2)

    assert uncredited > 0.0
    assert credited == pytest.approx(0.0)


def test_unused_credit_is_banked_for_a_later_year() -> None:
    """The state the carry exists to hold: a lean year draws on a fat one."""
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")
    fat = _slice(owned={None: 150_000.0})  # foreign-source, so the credit can reach it all

    _, carry = overlay.annual_tax(fat, CFG, residence_tax=_one(500_000.0), carry=None)
    later, _ = overlay.annual_tax(fat, CFG, residence_tax=_one(0.0), carry=carry)
    fresh = _charge(overlay, fat, residence_tax=0.0)

    assert float(later[0]) == pytest.approx(0.0), "last year's excess credit should cover this"
    assert fresh > 0.0, "without the carry the same year is charged"


def test_the_niit_survives_the_credit() -> None:
    """§ 1411 is outside the § 901 credit, so a huge foreign tax does not erase it.

    The conservative side of the undecided *Christensen*/*Bruyea* appeal — see
    `docs/decisions.md`.
    """
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")
    year = _slice(earned=400_000.0, owned={NON_PFIC: 300_000.0})

    charged = _charge(overlay, year, residence_tax=10_000_000.0)

    assert charged > 0.0, "the NIIT should stand even when everything else is credited"


def test_a_mark_to_market_pfic_is_charged_on_its_yearly_rise() -> None:
    """§ 1296, and the pool it leaves behind is what caps next year's loss."""
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")

    due, carry = overlay.annual_tax(
        _slice(earned=200_000.0, growth={pfic.MTM: 60_000.0}),
        CFG,
        residence_tax=_one(0.0),
        carry=None,
    )
    charged = float(due[0])
    flat = _charge(
        USCitizenshipOverlay(person=_person(), residence="NL"),
        _slice(earned=200_000.0, growth={pfic.MTM: 0.0}),
    )

    assert charged > flat
    assert carry.pfic_pool == pytest.approx(60_000.0)


def test_asking_twice_with_the_same_carry_gives_the_same_answer() -> None:
    """The overlay holds no year, so a second question about one year changes nothing.

    The carry exercised is a real one: a PFIC pool and an unspent credit from year one.
    """
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")
    _, carry = overlay.annual_tax(
        _slice(earned=200_000.0, growth={pfic.MTM: 60_000.0}),
        CFG,
        residence_tax=_one(1_000_000.0),
        carry=None,
    )
    assert carry.credit_bank, "year one should leave unspent credit to carry"
    year_two = _slice(earned=200_000.0, owned={NON_PFIC: 50_000.0}, growth={pfic.MTM: -20_000.0})

    first, first_carry = overlay.annual_tax(year_two, CFG, residence_tax=_one(0.0), carry=carry)
    second, second_carry = overlay.annual_tax(year_two, CFG, residence_tax=_one(0.0), carry=carry)

    np.testing.assert_array_equal(first, second)
    assert first_carry.pfic_pool is not None
    assert second_carry.pfic_pool is not None
    np.testing.assert_array_equal(first_carry.pfic_pool, second_carry.pfic_pool)
    assert len(first_carry.credit_bank) == len(second_carry.credit_bank)
    for a, b in zip(first_carry.credit_bank, second_carry.credit_bank, strict=True):
        np.testing.assert_array_equal(a, b)


def test_an_unclassified_account_is_still_taxed() -> None:
    """`None` means "no overlay classification", not "outside the US net".

    A US person's ordinary Dutch savings account earns interest the United States taxes;
    dropping the key rather than carrying it would silently exempt it.
    """
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")

    charged = _charge(overlay, _slice(owned={None: 300_000.0}))

    assert charged > 0.0


def test_a_realized_gain_is_charged_at_the_preferential_rate_and_the_niit() -> None:
    """Selling is taxable in the US even though Box 3 does not notice it.

    And a gain landing above the NIIT threshold pays both charges: 15 % under § 1(h) and
    3.8 % under § 1411, which sit in different chapters and do not displace each other.
    """
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")

    charged = _charge(overlay, _slice(earned=200_000.0, sold={NON_PFIC: 100_000.0}))
    without = _charge(
        USCitizenshipOverlay(person=_person(), residence="NL"), _slice(earned=200_000.0)
    )

    assert charged - without == pytest.approx(100_000.0 * float(CFG.ltcg_rate_2 + CFG.niit_rate))


def test_a_gain_is_stacked_on_the_year_it_was_realized_in() -> None:
    """The reason the charge is annual and not per sale.

    The same $60,000 gain is untaxed for a household with no other income and taxed at
    15 % for one whose salary already fills the zero band. A rate picked at the moment of
    sale could not know which — see `USCitizenshipOverlay.withdrawal_tax`.
    """
    lean = _charge(
        USCitizenshipOverlay(person=_person(), residence="NL"), _slice(sold={NON_PFIC: 60_000.0})
    )
    rich = _charge(
        USCitizenshipOverlay(person=_person(), residence="NL"),
        _slice(earned=200_000.0, sold={NON_PFIC: 60_000.0}),
    )

    assert lean == pytest.approx(0.0)
    assert rich > 0.0


def test_selling_a_marked_to_market_pfic_is_charged_only_on_the_residue() -> None:
    """§ 1296(b): the yearly marks raised basis, so the sale is not taxed twice."""
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")

    # Year one marks a $50,000 rise. Year two sells it, realizing $50,000 of gain.
    _, carry = overlay.annual_tax(
        _slice(earned=200_000.0, growth={pfic.MTM: 50_000.0}),
        CFG,
        residence_tax=_one(0.0),
        carry=None,
    )
    on_sale, _ = overlay.annual_tax(
        _slice(earned=200_000.0, sold={pfic.MTM: 50_000.0}),
        CFG,
        residence_tax=_one(0.0),
        carry=carry,
    )
    flat = _charge(overlay, _slice(earned=200_000.0))

    assert float(on_sale[0]) == pytest.approx(flat), "the marks already taxed the whole gain"


def test_a_sale_is_charged_nothing_at_the_moment_it_happens() -> None:
    """And that is the design, not a gap — `annual_tax` above is where it lands."""
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")

    charged = overlay.withdrawal_tax(
        _one(50_000.0), treatment=NON_PFIC, realized_gain=_one(30_000.0), cfg=CFG
    )

    assert charged == pytest.approx(0.0)


def test_an_unelected_pfic_is_refused() -> None:
    """`validate_accounts` is the overlay's half of the loud failure."""
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")
    account = Account(
        id=1,
        household_id=1,
        name="UCITS ETF",
        kind=AccountKind.EQUITY,
        tax_treatment="nl.box3_investment",
        overlay_treatment=pfic.UNELECTED,
        owner_person_id=1,
    )

    with pytest.raises(ValueError, match="UCITS ETF"):
        overlay.validate_accounts([account], person=_person())


def test_an_unknown_overlay_key_is_refused_by_name() -> None:
    """A typo in a classification must not silently mean "no overlay applies"."""
    overlay = USCitizenshipOverlay(person=_person(), residence="NL")
    account = Account(
        id=1,
        household_id=1,
        name="Mystery",
        kind=AccountKind.EQUITY,
        tax_treatment="nl.box3_investment",
        overlay_treatment="us.made_up",
        owner_person_id=1,
    )

    with pytest.raises(ValueError, match=r"us\.made_up"):
        overlay.validate_accounts([account], person=_person())


def test_a_residence_key_is_not_a_valid_overlay_key() -> None:
    """Invariant #2 from the overlay's side: `nl.*` means nothing here."""
    assert (
        "nl.box3_investment"
        not in USCitizenshipOverlay(person=_person(), residence="NL").valid_treatments()
    )


def test_overlays_are_built_only_for_us_people() -> None:
    """Only a US person gets an overlay.

    The household without one gets an empty tuple, which is what keeps its numbers
    bit-for-bit what they were before any of this existed.
    """
    us, other = _person(), _person(None, us=False)

    assert [p.id for p, _ in overlays_for([us], residence="NL")] == [1]
    assert overlays_for([other], residence="NL") == ()


def test_each_person_gets_their_own_overlay() -> None:
    """Two US people must not share a credit bank — the credit is per taxpayer.

    `HouseholdTax` keeps one carry per overlay, so one overlay per person is what keeps
    the banks apart.
    """
    a = Person(id=1, household_id=1, name="A", us_person=True, us_filing_status="single")
    b = Person(id=2, household_id=1, name="B", us_person=True, us_filing_status="single")

    built = overlays_for([a, b], residence="NL")

    assert len({id(overlay) for _, overlay in built}) == 2


def test_joint_filing_is_refused_for_two_us_people() -> None:
    """MFJ is one return for the couple, but each US person's overlay is its own return.

    Two spouses both marked MFJ were each charged the joint return's tax on the joint
    income, so the household paid it twice (52,680 against 26,340 on 200,000 of joint
    interest).
    """
    a = _person("married_filing_jointly")
    b = a.model_copy(update={"id": 2, "name": "Alex"})
    with pytest.raises(ValueError, match="married_filing_jointly"):
        overlays_for([a, b], residence="NL")


def test_joint_filing_stands_for_one_us_person() -> None:
    """One US person filing jointly with a non-US spouse (§ 6013(g)) is still modelled."""
    a = _person("married_filing_jointly")
    spouse = _person(None, us=False).model_copy(update={"id": 2})
    assert [p.id for p, _ in overlays_for([a, spouse], residence="NL")] == [1]
