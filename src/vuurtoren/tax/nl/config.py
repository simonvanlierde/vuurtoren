"""Dutch (NL) tax schema and figures.

The machinery — provenance, per-year resolution, indexing, range validation — is
country-neutral and lives in `tax/config.py`. The *schema* is not: `NLTaxConfig` declares
the Dutch figures, because no other country has a `box3_rate`. The values themselves live
in `parameters.yaml` (keyed by `NLTaxConfig` field, in the policyengine/OpenFisca
parameter shape — dated values with `status`, `verified_on` and a source `reference`).
This module declares the schema, loads the file against it, and registers the result into
`tax.config.TAX_CONFIG` at import time. Every rate in the engine comes from there; nothing
is written inline. 2026 values verified 2026-07-23 against the sources recorded in the file.

Each field carries its `description` here, which the tax panel shows, so the schema
stays the one place that knows what a figure means.
"""

from pydantic import Field

from vuurtoren.tax.config import (
    TAX_CONFIG,
    Money,
    Provenance,
    Rate,
    Status,
    TaxConfigBase,
    Unit,
    Year,
    defaults_for,
    resolve_tax_config,
)
from vuurtoren.tax.parameters import load_country_parameters

# Re-exported so callers can reach the country-neutral machinery through the NL module,
# which guarantees the registration below has run before they use it.
__all__ = [
    "TAX_CONFIG",
    "NLTaxConfig",
    "Provenance",
    "Status",
    "TaxConfigBase",
    "Unit",
    "defaults_for",
    "resolve_tax_config",
]


class NLTaxConfig(TaxConfigBase):
    """Every Dutch tax figure the engine can need, for one year."""

    # Box 3 — forfaitair regime (regime A)
    box3_rate: Rate = Field(description="Box 3 tax rate on the forfaitair rendement.")
    box3_allowance_per_person: Money = Field(
        description="Box 3 tax-free allowance (heffingvrij vermogen) per person."
    )
    box3_debt_threshold_per_person: Money = Field(
        description="Box 3 debt threshold (drempel) per person."
    )
    box3_forfait_bank: Rate = Field(
        description="Box 3 forfaitair return on bank and savings balances."
    )
    box3_forfait_investments: Rate = Field(
        description="Box 3 forfaitair return on investments (overige bezittingen)."
    )
    box3_forfait_debt: Rate = Field(description="Box 3 forfaitair rate deducted for debts.")

    # Box 3 — regime switch and the WWR regime (regime B)
    regime_switch_year: Year = Field(
        description="Year the Box 3 forfaitair regime switches to werkelijk rendement (WWR)."
    )
    wwr_rate: Rate = Field(description="Werkelijk-rendement (WWR) tax rate.")
    wwr_allowance_per_person: Money = Field(
        description="WWR tax-free allowance (heffingvrij resultaat) per person."
    )

    # Box 1 — home
    hra_max_rate: Rate = Field(
        description="Maximum rate at which hypotheekrenteaftrek is deductible."
    )

    # Box 1 — wages: the progressive below-AOW-age schedule and the two
    # kortingen at their maxima (the income-dependent phase-outs are not modelled).
    box1_rate_1: Rate = Field(description="Box 1 first-bracket rate (below AOW age).")
    box1_bracket_1_to: Money = Field(description="Upper bound of the Box 1 first bracket.")
    box1_rate_2: Rate = Field(description="Box 1 second-bracket rate (below AOW age).")
    box1_bracket_2_to: Money = Field(description="Upper bound of the Box 1 second bracket.")
    box1_rate_3: Rate = Field(description="Box 1 third-bracket rate (below AOW age).")
    general_credit_max: Money = Field(description="Algemene heffingskorting at its maximum.")
    """Algemene heffingskorting, at its maximum."""
    labour_credit_max: Money = Field(description="Arbeidskorting at its maximum.")
    """Arbeidskorting, at its maximum."""

    # Box 1 — pension withdrawal
    pension_withdrawal_rate: Rate = Field(
        description="Marginal Box 1 rate charged on withdrawing locked pension capital."
    )
    """Marginal Box 1 rate charged on withdrawing locked pension capital.

    A flat marginal rate, not the progressive schedule: a lijfrente uitkering lands on
    top of AOW and any other income, so the marginal bracket is the honest single number
    and a progressive-from-zero calculation would understate it badly. Same figure and
    the same reasoning as `hra_max_rate` — both are defined as the second Box 1 bracket
    rate; the shipped values derive all three from one constant (parameters.yaml), and
    the field stays separate only so it remains individually overridable.

    Approximations this does not model: the lower below-AOW
    premium rate, bracket progression on a large one-off withdrawal, and the
    heffingskortingen.
    """
    ewf_rate: Rate = Field(description="Eigenwoningforfait rate below the high-value threshold.")
    ewf_high_rate: Rate = Field(description="Eigenwoningforfait rate on value above the threshold.")
    ewf_threshold: Money = Field(
        description="Property value above which the high eigenwoningforfait rate applies."
    )
    hillen_rate: Rate = Field(
        description=("Wet Hillen deduction rate (aftrek wegens geen of geringe eigenwoningschuld).")
    )
    hillen_phaseout_per_year: Rate = Field(
        description="Annual phase-out step of the Wet Hillen deduction."
    )

    # One-off
    transfer_tax_own_home_rate: Rate = Field(
        description="Overdrachtsbelasting rate for an owner-occupied home."
    )
    transfer_tax_general_rate: Rate = Field(description="Overdrachtsbelasting general rate.")
    starter_exemption_max_age: Year = Field(
        description="Maximum age for the overdrachtsbelasting startersvrijstelling."
    )
    starter_exemption_value_cap: Money = Field(
        description="Property value cap for the startersvrijstelling."
    )
    gift_exemption_onetime: Money = Field(
        description="One-time increased gift exemption (eenmalig verhoogd)."
    )
    gift_exemption_annual: Money = Field(description="Annual gift exemption per recipient.")
    gift_exemption_min_age: Year = Field(
        description="Minimum recipient age for the one-time gift exemption."
    )
    gift_exemption_max_age: Year = Field(
        description="Maximum recipient age for the one-time gift exemption."
    )


TAX_CONFIG["NL"] = load_country_parameters("vuurtoren.tax.nl", NLTaxConfig)
