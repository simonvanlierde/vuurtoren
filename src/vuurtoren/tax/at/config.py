"""Austrian (AT) tax schema and figures.

Same shape as `tax/nl/config.py`: the machinery is country-neutral and lives in
`tax/config.py`, the schema is declared here, and the values live in `parameters.yaml`.

The field set is what `ATTaxRegime` consumes, plus the seven-band Einkommensteuer ladder
that `tax/at/income.py` reads. That helper is on the same footing as the Dutch
`gross_to_net`: no `TaxRegime` method taxes wage income.

Figures verified 2026-07-28 against the sources recorded in `parameters.yaml`.
"""

from pydantic import Field

from vuurtoren.tax.config import TAX_CONFIG, Money, Rate, TaxConfigBase
from vuurtoren.tax.parameters import load_country_parameters


class ATTaxConfig(TaxConfigBase):
    """The Austrian tax figures the engine can need, for one year."""

    kest_rate: Rate = Field(
        description=(
            "Kapitalertragsteuer on securities income — realized capital gains, "
            "dividends and bond interest."
        )
    )
    kest_bank_interest_rate: Rate = Field(
        description=(
            "Kapitalertragsteuer on interest from bank deposits and other "
            "non-securitised claims against credit institutions."
        )
    )
    fund_deemed_gain_share: Rate = Field(
        description=(
            "Share of a reporting fund's realised gains deemed distributed to a "
            "private investor each year (ausschuettungsgleiche Ertraege)."
        )
    )
    # Einkommensteuer (income.py). Seven bands: six thresholds plus a top open band.
    # Every threshold but the last is re-indexed each year for kalte Progression, so a
    # new tax year is a new dated value rather than an edit.
    income_bracket_1_to: Money = Field(description="Upper bound of the tax-free band.")
    income_rate_1: Rate = Field(description="Marginal rate in the tax-free band.")
    income_bracket_2_to: Money = Field(description="Upper bound of the second band.")
    income_rate_2: Rate = Field(description="Marginal rate in the second band.")
    income_bracket_3_to: Money = Field(description="Upper bound of the third band.")
    income_rate_3: Rate = Field(description="Marginal rate in the third band.")
    income_bracket_4_to: Money = Field(description="Upper bound of the fourth band.")
    income_rate_4: Rate = Field(description="Marginal rate in the fourth band.")
    income_bracket_5_to: Money = Field(description="Upper bound of the fifth band.")
    income_rate_5: Rate = Field(description="Marginal rate in the fifth band.")
    income_bracket_6_to: Money = Field(description="Upper bound of the sixth band.")
    income_rate_6: Rate = Field(description="Marginal rate in the sixth band.")
    income_rate_7: Rate = Field(
        description="Marginal rate above the top threshold, in force 2016-2029."
    )
    employee_credit: Money = Field(
        description="Verkehrsabsetzbetrag, the flat employee tax credit."
    )
    social_insurance_employee_rate: Rate = Field(
        description="Blended employee social insurance contribution rate."
    )
    social_insurance_ceiling: Money = Field(
        description="Hoechstbeitragsgrundlage, the annual social insurance ceiling."
    )
    sonderzahlung_rate: Rate = Field(
        description="Flat rate on the 13th and 14th salary within the Jahressechstel."
    )
    sonderzahlung_allowance: Money = Field(
        description="Freibetrag deducted from the Jahressechstel before the flat rate."
    )
    sonderzahlung_exempt_below: Money = Field(
        description="Freigrenze below which the Jahressechstel is exempt entirely."
    )
    sonderzahlung_share: Rate = Field(
        description=(
            "Share of annual pay treated as sonstige Bezuege — 2 of 14 monthly "
            "payments where a 13th and 14th salary are paid."
        )
    )

    nonreporting_gain_share: Rate = Field(
        description=(
            "Share of a non-reporting fund's yearly rise deemed distributed "
            "(the 90% limb of the lump-sum estimate)."
        )
    )
    nonreporting_minimum_share: Rate = Field(
        description=(
            "Minimum deemed distribution for a non-reporting fund, as a share of its "
            "year-end value (the 10% floor)."
        )
    )

    grunderwerbsteuer_rate: Rate = Field(
        description="Grunderwerbsteuer, the property transfer tax on the purchase price."
    )
    land_register_fee_rate: Rate = Field(
        description="Grundbuch-Eintragungsgebuehr, the land register registration fee."
    )
    mortgage_registration_fee_rate: Rate = Field(
        description=(
            "Pfandrechtseintragungsgebuehr, charged on the mortgage amount registered "
            "rather than on the purchase price."
        )
    )


TAX_CONFIG["AT"] = load_country_parameters("vuurtoren.tax.at", ATTaxConfig)
