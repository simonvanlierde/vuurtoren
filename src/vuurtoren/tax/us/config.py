"""US federal tax schema and figures.

Same shape as `tax/nl/config.py` and `tax/at/config.py`: the machinery is
country-neutral and lives in `tax/config.py`, the schema is declared here, and the values
live in `parameters.yaml`.

**The figures are US dollars.** Every other parameter file in the repo is euros, so the
exported `unit:` says `currency-USD` and `currency` below is what makes it. Converting to
the household's currency is the overlay's job, not this file's.

Three things about the field set are worth stating, because each is a decision rather
than an omission:

- **Filing status is spelled out three ways** (`_single`, `_mfs`, `_mfj`) wherever the
  statute differs. For 2026 the MFS schedule happens to equal the unmarried one for every
  band but the top, and happens to be exactly half the joint one throughout. Both are
  coincidences of § 1(j)(2) as currently written, not rules, so all three are shipped as
  data instead of derived from each other.
- **The seven ordinary rates are declared once**, not per status: 10/12/22/24/32/35/37
  apply to every filer. Only the band tops move.
- **There is no PFIC mark-to-market rate.** § 1296 gains are taxed at *ordinary* rates,
  so `tax/us/federal/pfic.py` reaches for `ordinary_rate_*` rather than a rate of its
  own. A separate figure here would be an invented one.

Figures verified 2026-07-28 against the sources recorded in `parameters.yaml`, and
reasoned about in `docs/decisions.md` ("US federal figures for 2026").
"""

from typing import TYPE_CHECKING, cast

from pydantic import Field

from vuurtoren.tax.config import TAX_CONFIG, FixedMoney, Money, Rate, TaxConfigBase
from vuurtoren.tax.parameters import load_country_parameters

if TYPE_CHECKING:
    from decimal import Decimal

    from vuurtoren.domain import FilingStatus

_STATUS_SUFFIX = {
    "single": "single",
    "married_filing_separately": "mfs",
    "married_filing_jointly": "mfj",
}
"""`domain.FilingStatus` -> the field-name suffix the figures below use.

Two spellings, deliberately. `domain.FilingStatus` is what a person records and what the
database stores, so it is spelled out; the statute's tables are keyed by the short form
and repeating `married_filing_separately` across forty-two field names would help nobody.
This dict is the only place the two meet, and
`test_every_domain_filing_status_maps_to_a_figure_suffix` fails if a status is added to
the domain type without a home here.

A US citizen married to a non-US spouse, the case the overlay is built around, files
MFS unless they elect to treat the spouse as a resident (§ 6013(g)), which drags the
spouse's whole worldwide income into the US net. So MFS is the interesting one, and it
is *not* the single schedule under another name: the top band splits.
"""


class USTaxConfig(TaxConfigBase):
    """The US federal figures a citizenship overlay can need, for one year."""

    currency = "USD"

    standard_deduction_single: Money = Field(
        description="Standard deduction for an unmarried filer."
    )
    standard_deduction_mfs: Money = Field(
        description="Standard deduction for a married filer filing separately."
    )
    standard_deduction_mfj: Money = Field(
        description="Standard deduction for a married couple filing jointly."
    )

    # Ordinary income. Seven bands: six thresholds per filing status plus a top open
    # band, and one set of rates for all three statuses. Every threshold is re-indexed
    # annually, so a new tax year is a new dated value rather than an edit.
    ordinary_bracket_1_to_single: Money = Field(
        description="Top of the first ordinary band, unmarried."
    )
    ordinary_bracket_1_to_mfs: Money = Field(
        description="Top of the first ordinary band, married filing separately."
    )
    ordinary_bracket_1_to_mfj: Money = Field(
        description="Top of the first ordinary band, married filing jointly."
    )
    ordinary_bracket_2_to_single: Money = Field(
        description="Top of the second ordinary band, unmarried."
    )
    ordinary_bracket_2_to_mfs: Money = Field(
        description="Top of the second ordinary band, married filing separately."
    )
    ordinary_bracket_2_to_mfj: Money = Field(
        description="Top of the second ordinary band, married filing jointly."
    )
    ordinary_bracket_3_to_single: Money = Field(
        description="Top of the third ordinary band, unmarried."
    )
    ordinary_bracket_3_to_mfs: Money = Field(
        description="Top of the third ordinary band, married filing separately."
    )
    ordinary_bracket_3_to_mfj: Money = Field(
        description="Top of the third ordinary band, married filing jointly."
    )
    ordinary_bracket_4_to_single: Money = Field(
        description="Top of the fourth ordinary band, unmarried."
    )
    ordinary_bracket_4_to_mfs: Money = Field(
        description="Top of the fourth ordinary band, married filing separately."
    )
    ordinary_bracket_4_to_mfj: Money = Field(
        description="Top of the fourth ordinary band, married filing jointly."
    )
    ordinary_bracket_5_to_single: Money = Field(
        description="Top of the fifth ordinary band, unmarried."
    )
    ordinary_bracket_5_to_mfs: Money = Field(
        description="Top of the fifth ordinary band, married filing separately."
    )
    ordinary_bracket_5_to_mfj: Money = Field(
        description="Top of the fifth ordinary band, married filing jointly."
    )
    ordinary_bracket_6_to_single: Money = Field(
        description="Top of the sixth ordinary band, unmarried."
    )
    ordinary_bracket_6_to_mfs: Money = Field(
        description="Top of the sixth ordinary band, married filing separately."
    )
    ordinary_bracket_6_to_mfj: Money = Field(
        description="Top of the sixth ordinary band, married filing jointly."
    )
    ordinary_rate_1: Rate = Field(description="Marginal rate in the first ordinary band.")
    ordinary_rate_2: Rate = Field(description="Marginal rate in the second ordinary band.")
    ordinary_rate_3: Rate = Field(description="Marginal rate in the third ordinary band.")
    ordinary_rate_4: Rate = Field(description="Marginal rate in the fourth ordinary band.")
    ordinary_rate_5: Rate = Field(description="Marginal rate in the fifth ordinary band.")
    ordinary_rate_6: Rate = Field(description="Marginal rate in the sixth ordinary band.")
    ordinary_rate_7: Rate = Field(description="Marginal rate above the top ordinary threshold.")

    # Long-term capital gains and qualified dividends. The thresholds are read against
    # *total* taxable income, not against the gain alone — the preferential rates stack
    # on top of ordinary income.
    ltcg_zero_rate_top_single: Money = Field(
        description="Taxable income up to which long-term gains are untaxed, unmarried."
    )
    ltcg_zero_rate_top_mfs: Money = Field(
        description=(
            "Taxable income up to which long-term gains are untaxed, married filing separately."
        )
    )
    ltcg_zero_rate_top_mfj: Money = Field(
        description=(
            "Taxable income up to which long-term gains are untaxed, married filing jointly."
        )
    )
    ltcg_fifteen_rate_top_single: Money = Field(
        description="Top of the 15 % long-term gains band, unmarried."
    )
    ltcg_fifteen_rate_top_mfs: Money = Field(
        description="Top of the 15 % long-term gains band, married filing separately."
    )
    ltcg_fifteen_rate_top_mfj: Money = Field(
        description="Top of the 15 % long-term gains band, married filing jointly."
    )
    ltcg_rate_1: Rate = Field(description="Long-term gains rate in the lowest band.")
    ltcg_rate_2: Rate = Field(description="Long-term gains rate in the middle band.")
    ltcg_rate_3: Rate = Field(description="Long-term gains rate above the top threshold.")

    niit_rate: Rate = Field(
        description=(
            "Net investment income tax rate on the lesser of net investment income and "
            "modified AGI above the threshold."
        )
    )
    niit_threshold_single: FixedMoney = Field(
        description="Modified AGI above which the net investment income tax applies, unmarried."
    )
    niit_threshold_mfs: FixedMoney = Field(
        description=(
            "Modified AGI above which the net investment income tax applies, "
            "married filing separately."
        )
    )
    niit_threshold_mfj: FixedMoney = Field(
        description=(
            "Modified AGI above which the net investment income tax applies, "
            "married filing jointly."
        )
    )

    feie_limit: Money = Field(
        description="Maximum foreign earned income excludable under the section 911 election."
    )

    def by_filing_status(self, figure: str, status: FilingStatus) -> Decimal:
        """The `<figure>_<status>` field — `("standard_deduction", MFJ)` → 32,200.

        A built name rather than a `match` per family: five families vary by status (the
        standard deduction, six ordinary band tops, two long-term gains tops and the NIIT
        threshold), so spelling each out three ways would be sixty lines of mechanical
        selection. `test_every_status_varying_figure_resolves_for_every_status` walks the
        whole product, so a mistyped family fails in the suite, not in a projection.
        """
        suffix = _STATUS_SUFFIX[status]
        try:
            return cast("Decimal", getattr(self, f"{figure}_{suffix}"))
        except AttributeError:
            msg = (
                f"{type(self).__name__} has no figure {figure!r} for filing status "
                f"{status!r} (looked for {figure}_{suffix})"
            )
            raise KeyError(msg) from None


TAX_CONFIG["US"] = load_country_parameters("vuurtoren.tax.us", USTaxConfig)
