"""Record Dutch calculations while the real deterministic engine runs."""

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Literal

import numpy as np

from vuurtoren.tax.config import Unit
from vuurtoren.tax.explanation import TaxCalculation, TaxParameterUsed, TaxStep
from vuurtoren.tax.nl.aow import aow_year_share
from vuurtoren.tax.nl.box1 import box1_steps, gross_from_net_array, net_housing_tax_effect_array
from vuurtoren.tax.nl.regime import NLTaxRegime

if TYPE_CHECKING:
    from datetime import date

    from vuurtoren.tax.nl.config import NLTaxConfig
    from vuurtoren.tax.regime import YearState


_BOX3_RULES = {
    "bank": ("Banktegoeden (modelpeildatum: einde jaar)", ("box3_forfait_bank",)),
    "investments": (
        "Overige bezittingen (modelpeildatum: einde jaar)",
        ("box3_forfait_investments",),
    ),
    "debt": ("Schulden, inclusief roodstand", ("box3_debt_threshold_per_person",)),
    "eligible_debt": (
        "Aftrekbare schulden na schuldendrempel",
        ("box3_debt_threshold_per_person",),
    ),
    "grondslag": ("Rendementsgrondslag", ("box3_debt_threshold_per_person",)),
    "allowance": ("Heffingsvrij vermogen", ("box3_allowance_per_person",)),
    "bank_return": ("Forfaitair rendement spaargeld", ("box3_forfait_bank",)),
    "investment_return": (
        "Forfaitair rendement overige bezittingen",
        ("box3_forfait_investments",),
    ),
    "debt_return": ("Forfaitair rendement aftrekbare schulden", ("box3_forfait_debt",)),
    "rendement": (
        "Forfaitair rendement spaargeld + beleggingen - schulden",
        ("box3_forfait_bank", "box3_forfait_investments", "box3_forfait_debt"),
    ),
    "aandeel": ("Belastbaar aandeel na heffingsvrij vermogen", ("box3_allowance_per_person",)),
    "forfaitair_income": (
        "Voordeel uit sparen en beleggen (forfaitair)",
        ("box3_allowance_per_person",),
    ),
    "actual_return": ("Werkelijk beleggingsrendement (zonder bankrente)", ("regime_switch_year",)),
    "wwr_income": ("Werkelijk rendement na heffingsvrij inkomen", ("wwr_allowance_per_person",)),
    "loss_carry": ("Verrekenbaar verlies uit eerdere jaren", ("wwr_loss_threshold",)),
    "loss_used": ("Verliesverrekening dit jaar", ("wwr_loss_threshold",)),
    "next_carry": ("Verrekenbaar verlies naar volgend jaar", ("wwr_loss_threshold",)),
}


class NLTaxExplanation(NLTaxRegime):
    """Capture one year; later hypothetical drag calls cannot replace its assessment.

    Withdrawal calls replace the same owner's entry: December's final true-up is the
    last call, after the cash sweep and after all that year's income has arrived.
    """

    def __init__(self, year: int) -> None:
        self.year = year
        self.box3: list[TaxCalculation] = []
        self.housing: list[TaxCalculation] = []
        self.payouts: dict[int | None, list[TaxCalculation]] = {}
        self.totals: dict[str, str] = {}

    @property
    def calculations(self) -> list[TaxCalculation]:
        """Housing and pension effects in Box 1, followed by each Box 3 taxpayer."""
        return self.housing + [c for group in self.payouts.values() for c in group] + self.box3

    @staticmethod
    def _step(
        cfg: NLTaxConfig,
        rule: str,
        value: np.ndarray,
        fields: tuple[str, ...],
        unit: Literal["currency", "rate", "number"] = "currency",
    ) -> TaxStep:
        units = {name: u for u in Unit for name in type(cfg).fields_with_unit(u)}
        return TaxStep(
            rule=rule,
            value=(
                str(Decimal(str(value[0])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                if unit == "currency"
                else str(value[0])
            ),
            unit=unit,
            parameters={
                name: TaxParameterUsed(
                    value=str(getattr(cfg, name)),
                    unit=units.get(name),
                    source_year=cfg.source_years[name],
                    status=cfg.provenance[name].status,
                    source=cfg.provenance[name].source,
                    sources=list(
                        getattr(cfg.provenance[name], "sources", ())
                        or (cfg.provenance[name].source,)
                    ),
                    verified_on=cfg.provenance[name].verified_on.isoformat(),
                )
                for name in fields
            },
        )

    def annual_investment_tax(self, s: YearState, cfg: NLTaxConfig) -> np.ndarray:
        """Read the first actual assessment, before the engine asks hypothetical ones."""
        due = super().annual_investment_tax(s, cfg)
        if s.year != self.year or self.box3:
            return due
        for person_id, balances, gain in self._taxpayers(s):
            values: dict[str, np.ndarray] = {}
            pools = s.residence_carry or {}
            self._box3(balances, gain, s, cfg, pools.get(person_id), steps=values)
            rate = "wwr_rate" if s.year >= cfg.regime_switch_year else "box3_rate"
            rules = {
                **_BOX3_RULES,
                "taxable": ("Belastbaar rendement (na tegenbewijs of verliesverrekening)", (rate,)),
                "tax": ("Box 3-belasting", (rate,)),
            }
            self.box3.append(
                TaxCalculation(
                    label="Box 3",
                    person_id=person_id,
                    steps=[
                        self._step(
                            cfg,
                            rules[key][0],
                            value,
                            rules[key][1],
                            "rate" if key == "aandeel" else "currency",
                        )
                        for key, value in values.items()
                    ],
                )
            )
        self.totals["investment_tax"] = str(due[0])
        return due

    def annual_housing_adjustment(self, s: YearState, cfg: NLTaxConfig) -> np.ndarray:
        """Read the same housing calculation the engine charges."""
        values: dict[str, np.ndarray] | None = (
            {} if s.year == self.year and not self.housing else None
        )
        effect = net_housing_tax_effect_array(
            s.mortgage_interest_paid, s.home_value, year=s.year, cfg=cfg, steps=values
        )
        if values is not None:
            rules = {
                "woz": ("WOZ in het model (verkochte woning naar maanden gewogen)", ("ewf_rate",)),
                "interest": ("Betaalde hypotheekrente", ("hra_max_rate",)),
                "ewf": ("Eigenwoningforfait", ("ewf_rate", "ewf_threshold", "ewf_high_rate")),
                "hillen": (
                    "Aftrek wegens geen of geringe eigenwoningschuld (Wet Hillen)",
                    ("hillen_rate", "hillen_phaseout_per_year"),
                ),
                "housing_adjustment": (
                    "Netto belastingvoordeel eigen woning (+ is teruggave)",
                    ("hra_max_rate",),
                ),
            }
            self.housing.append(
                TaxCalculation(
                    label="Box 1 — eigen woning",
                    steps=[
                        self._step(
                            cfg,
                            rules[key][0],
                            value,
                            rules[key][1],
                            "rate" if key == "hillen" else "currency",
                        )
                        for key, value in values.items()
                    ],
                )
            )
            self.totals["housing_adjustment"] = str(effect[0])
        return effect

    def withdrawal_tax(
        self,
        amount: np.ndarray,
        *,
        treatment: str,
        realized_gain: np.ndarray,
        owner_person_id: int | None,
        owner_income: np.ndarray,
        owner_state_pension_date: date | None,
        year: int,
        cfg: NLTaxConfig,
    ) -> np.ndarray:
        """Keep the final per-owner year-to-date pension calculation."""
        due = super().withdrawal_tax(
            amount,
            treatment=treatment,
            realized_gain=realized_gain,
            owner_person_id=owner_person_id,
            owner_income=owner_income,
            owner_state_pension_date=owner_state_pension_date,
            year=year,
            cfg=cfg,
        )
        if year != self.year or treatment not in self.withdrawal_taxed_treatments():
            return due
        share = aow_year_share(owner_state_pension_date, year)
        gross = gross_from_net_array(owner_income, aow_share=share, cfg=cfg)
        calculations = []
        for label, income in (
            ("Box 1 — vóór lijfrente-uitkering", gross),
            ("Box 1 — inclusief lijfrente-uitkering", gross + np.maximum(amount, 0)),
        ):
            values = box1_steps(income, labour_income=gross, aow_share=share, cfg=cfg)
            steps = [
                self._step(
                    cfg,
                    "Ingevoerd netto jaarinkomen",
                    owner_income,
                    ("box1_rate_1", "box1_rate_2", "box1_rate_3"),
                ),
                self._step(cfg, "Lijfrente-uitkering (bruto)", amount, ("box1_rate_1",)),
            ]
            for key, value in values.items():
                rule, fields, unit = _income_rule(key, cfg)
                steps.append(self._step(cfg, rule, value, fields, unit))
            calculations.append(TaxCalculation(label=label, person_id=owner_person_id, steps=steps))
        calculations.append(
            TaxCalculation(
                label="Box 1 — belasting op lijfrente-uitkering",
                person_id=owner_person_id,
                steps=[
                    self._step(
                        cfg,
                        "Belasting inclusief uitkering - belasting vóór uitkering",
                        due,
                        ("box1_rate_1", "box1_rate_2", "box1_rate_3"),
                    )
                ],
            )
        )
        self.payouts[owner_person_id] = calculations
        return due


def _income_rule(
    key: str, cfg: NLTaxConfig
) -> tuple[str, tuple[str, ...], Literal["currency", "rate", "number"]]:
    """Map shared arithmetic steps to Dutch rules and their parameter names."""
    if key in {"income", "labour_income", "tax"}:
        names = {
            "income": "Belastbaar Box 1-inkomen (bruto terugberekend)",
            "labour_income": "Arbeidsinkomen (bruto terugberekend)",
            "tax": "Box 1 na kortingen, per AOW-deel begrensd op nul en gewogen",
        }
        return names[key], ("box1_rate_1", "box1_rate_2", "box1_rate_3"), "currency"
    prefix, part = key.split("_", 1)
    suffix = " (AOW-leeftijd)" if prefix == "aow" else " (vóór AOW-leeftijd)"
    if part == "share":
        return "Aandeel van het jaar" + suffix, ("aow_premium_rate",), "rate"
    if part.startswith("bracket_"):
        number = part[-1]
        fields = {
            "1": ("box1_rate_1", "box1_bracket_1_to"),
            "2": ("box1_rate_2", "box1_bracket_1_to", "box1_bracket_2_to"),
            "3": ("box1_rate_3", "box1_bracket_2_to"),
        }[number]
        if prefix == "aow" and number == "1":
            fields += ("aow_premium_rate",)
        return "Schijf " + number + suffix, fields, "currency"
    if part == "general":
        fields = (
            (
                "general_credit_max_aow",
                "general_credit_phaseout_from",
                "general_credit_phaseout_rate_aow",
            )
            if prefix == "aow"
            else (
                "general_credit_max",
                "general_credit_phaseout_from",
                "general_credit_phaseout_rate",
            )
        )
        return "Algemene heffingskorting" + suffix, fields, "currency"
    if part == "labour":
        return (
            "Arbeidskorting" + suffix,
            tuple(name for name in type(cfg).model_fields if name.startswith("labour_credit_")),
            "currency",
        )
    return (
        "Ouderenkorting" + suffix,
        ("elderly_credit_max", "elderly_credit_phaseout_from", "elderly_credit_phaseout_rate"),
        "currency",
    )
