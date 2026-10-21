"""The treaty seam inside `tax/us/`, beside the statute seam that is `federal/`.

`federal/` is what every US expatriate faces wherever they live. What a *treaty* does to
that charge depends entirely on where they live, so it is a module per residence country
rather than a branch inside the overlay — the same split PolicyEngine draws between
`gov/irs` and `gov/states/xx`.

**Sourcing is deliberately not here.** Which income is US-source is § 861 and § 865:
federal law, and the same in Amsterdam as in Vienna. The overlay decides it, and this
layer answers only the two questions a treaty answers:

1. How much of that US-source income does the treaty deem to arise abroad, so the § 904
   limitation stops excluding it from the foreign tax credit?
2. How much US tax does the treaty insist on keeping anyway, credit or no credit?

The second is what stops a naive model zeroing the US side. Relief is not exemption:
Article 25(6)(b) of the NL-US convention preserves the tax the treaty itself permits.

A residence country with no entry in `REGISTRY` gets no relief at all, which is the
statute's own answer and **overstates** US tax wherever a treaty exists and this repo has
not modelled it.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class TreatyRelief:
    """What one residence treaty does to one person's US-source income, per run."""

    resourced: np.ndarray
    """The part of US-source income the treaty deems to arise in the residence country.

    It joins the foreign-source total the § 904 limitation is measured against, which is
    the whole mechanism: without it, US tax on US-source income is exactly the tax the
    credit may never shelter.
    """

    preserved_us_tax: np.ndarray
    """US tax the treaty keeps standing after the credit has been applied.

    A floor, not a charge — the caller clamps it to the US tax that actually arose, since
    a treaty can preserve a portion of a tax but cannot conjure one.
    """


@runtime_checkable
class ResidenceTreatyRules(Protocol):
    """What the treaty between the United States and one residence country does."""

    @property
    def residence(self) -> str:
        """ISO 3166-1 alpha-2 code of the country these rules govern residence in.

        A read-only property for the same reason `TaxRegime.country` is one: which treaty
        a module implements is a fact about it, not a setting.
        """
        ...

    def relief(
        self, *, us_source_dividends: np.ndarray, us_source_gains: np.ndarray, year: int
    ) -> TreatyRelief:
        """Apply the treaty to this year's US-source income, per run.

        Split by income type because a treaty is: each article reaches its own kind of
        income at its own rate, and an implementation that took one lump sum could not
        tell a dividend the treaty caps at 15 % from a gain it exempts outright.

        `year` rather than a config object: which figures a treaty needs is the treaty's
        own business, so each implementation resolves its own.
        """
        ...
