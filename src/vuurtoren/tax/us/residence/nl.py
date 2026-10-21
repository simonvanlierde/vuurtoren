"""The 1992 US-Netherlands convention, as it reaches a US citizen living in the Netherlands.

`docs/decisions.md` (2026-07-28, "The NL-US re-sourcing article") is the specification and
carries the sources. Three findings drive everything below:

- **The saving clause does not bite.** Article 24(1) reserves each state's right to tax its
  own nationals as though the convention had not been made, but Article 24(2)(a) exempts
  Article 25 from that reservation *by name*. The relief survives because the treaty says
  so, not because a citizen is treated as a non-citizen.
- **Article 25(6) reaches an item only if the convention exempts it or reduces its US rate
  for a Dutch resident who is not a US citizen.** So each income type is checked against
  its own article rather than re-sourced wholesale: dividends under Article 10(2)(b), which
  caps US tax at 15 % for a portfolio holder and names Regulated Investment Companies —
  a US-domiciled ETF is one; gains under Article 14(7), which makes a securities gain
  taxable only in the residence state.
- **Relief is not exemption.** Article 25(6)(b) lets the Netherlands credit the US tax the
  treaty permits and only then lets the United States credit what Dutch tax remains, "the
  credit so allowed shall not reduce the portion of the United States tax that is
  creditable against the Netherlands tax". The 15 % on dividends stands.

**One basket, not two.** The Form 1116 instructions demand a separate form per re-sourced
amount and then except income re-sourced under a treaty relief rule "solely applicable to
U.S. citizens who are residents of the foreign treaty country". Article 25(6) is exactly
that, so the re-sourced dividends and gains stay in the passive category `ftc.py` already
runs — no second limitation, and nothing here to keep in step with it.

**Not modelled:** Article 25(6)(c) caps re-sourcing at what is "necessary to avoid double
taxation", and this module re-sources the qualifying income whole. The cap is what the
preserved-tax floor implements from the other side — relief can never take US tax below
the treaty rate — so the two agree wherever the floor binds. Where they can part is a year
whose Dutch tax is smaller than the US tax on the same income: re-sourcing more than was
necessary leaves a larger § 904 limitation than the treaty requires, so more of the credit
carryforward can be spent. It **understates** US tax in that year and, because the bank is
drawn down faster, overstates it later. Modelling the cap exactly needs the double-taxed
amount item by item, which one basket does not carry.

Form 8833 disclosure may be required for the position. That is a filing matter, and this
app files nothing.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import Field

from vuurtoren.tax.config import TAX_CONFIG, Rate, TaxConfigBase, defaults_for
from vuurtoren.tax.parameters import load_country_parameters
from vuurtoren.tax.us.residence.protocol import TreatyRelief

if TYPE_CHECKING:
    import numpy as np


class USNLTreatyConfig(TaxConfigBase):
    """The treaty rates, carrying provenance like every other rate in the repo.

    Registered under `"US-NL"` rather than a country code, because a treaty is a pair and
    not a place. `TAX_CONFIG` is keyed by plain strings, so this costs nothing and buys the
    year fallback, the scenario-override path and the provenance test that walks the whole
    registry.

    No money figures, so `currency` never renders — it is set for the reader.
    """

    currency = "USD"

    resourced_dividend_rate: Rate = Field(
        description=(
            "Maximum US tax on a portfolio dividend derived by a Dutch resident under "
            "Article 10(2)(b) — the portion of US tax Article 25(6)(b) preserves against "
            "the foreign tax credit."
        )
    )
    resourced_gain_rate: Rate = Field(
        description=(
            "Maximum US tax on a securities gain derived by a Dutch resident under "
            "Article 14(7), which makes such a gain taxable only in the residence state."
        )
    )


TAX_CONFIG["US-NL"] = load_country_parameters(
    "vuurtoren.tax.us.residence", USNLTreatyConfig, "nl_parameters.yaml"
)


@dataclass(frozen=True)
class NLTreatyRules:
    """Article 25(6) applied to one person's year. Stateless — the overlay holds the state."""

    residence: str = "NL"

    def relief(
        self, *, us_source_dividends: np.ndarray, us_source_gains: np.ndarray, year: int
    ) -> TreatyRelief:
        """Both income types qualify, so both are re-sourced whole; only the rates differ."""
        cfg = defaults_for("US-NL", year, expect=USNLTreatyConfig)
        return TreatyRelief(
            resourced=us_source_dividends + us_source_gains,
            preserved_us_tax=(
                us_source_dividends * float(cfg.resourced_dividend_rate)
                + us_source_gains * float(cfg.resourced_gain_rate)
            ),
        )
