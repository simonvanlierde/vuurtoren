/**
 * Groups the flat `TaxConfig` field set from GET /api/tax-config into the
 * subsections the tax panel renders under.
 * Field membership mirrors `tax/config.py`'s field comments — kept here rather than
 * fetched from the API because the endpoint returns values, not schema groupings.
 */

import { type Locale, MESSAGES } from "./i18n";

export type TaxStatus = "final" | "provisional" | "proposed" | "user";

/** What a figure denominates, as `tax/config.py`'s `Unit` serialises it. The same
 * declaration drives inflation indexing and the server's range validator, so the panel
 * formats and range-checks from it rather than guessing from field names. `null` for a figure whose config predates the annotation. */
export type TaxUnit = "currency" | "/1" | "year" | null;

export interface TaxField {
  value: string;
  unit: TaxUnit;
  status: TaxStatus;
  source: string;
  verified_on: string;
  /** The pydantic field's own description, which the server now sends. Optional: a
   * config field that predates the annotation has none, and the label falls back. */
  description?: string;
}

const RATE_FORMAT = new Intl.NumberFormat("nl-NL", {
  style: "percent",
  maximumFractionDigits: 2,
});

/** A resolved figure as a reader should see it: `36%`, `€ 59.357`, `2028`. The raw
 * `0.36` is what the engine holds and what an override is typed in; it is not what a
 * panel whose job is to be believed should be showing. */
export function formatTaxValue(value: string, unit: TaxUnit, currency: string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  if (unit === "/1") return RATE_FORMAT.format(n);
  if (unit === "currency") {
    // min 0 / max 2, not a fixed 2: a threshold is a round € 59.357 and printing it as
    // "€ 59.357,00" is false precision, while a figure that really carries cents keeps
    // them. Setting max below the currency default's min 2 would throw, so both are set.
    return new Intl.NumberFormat("nl-NL", {
      style: "currency",
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(n);
  }
  if (unit === "year") return String(Math.round(n));
  return value;
}

/** The server's own bounds (`TaxConfigBase._check_ranges`), applied at entry instead of
 * at projection time. Returns a message key, or null when the value is acceptable.
 *
 * NOTE: no range on `year`. That annotation covers calendar years *and* ages —
 * `starter_exemption_max_age` is 35 — and the server range-checks neither, only the
 * config's own `year`. A [1900, 2200] check here would reject a valid age.
 */
export function taxValueError(value: string, unit: TaxUnit): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return "plan.tax.error.empty";
  const n = Number(trimmed);
  if (!Number.isFinite(n)) return "plan.tax.error.notANumber";
  if (unit === "/1") return n < 0 || n > 1 ? "plan.tax.error.rateRange" : null;
  if (unit === "currency") return n < 0 ? "plan.tax.error.negativeMoney" : null;
  if (unit === "year" && !Number.isInteger(n)) return "plan.tax.error.wholeYear";
  return null;
}

export interface TaxFieldRow {
  name: string;
  label: string;
  field: TaxField;
}

export interface TaxFieldGroup {
  id: string;
  label: string;
  rows: TaxFieldRow[];
}

const GROUPS: { id: string; fields: string[] }[] = [
  {
    id: "box3",
    fields: [
      "box3_rate",
      "box3_allowance_per_person",
      "box3_debt_threshold_per_person",
      "box3_forfait_bank",
      "box3_forfait_investments",
      "box3_forfait_debt",
    ],
  },
  {
    id: "regime-b",
    fields: ["regime_switch_year", "wwr_rate", "wwr_allowance_per_person"],
  },
  {
    id: "box1-home",
    fields: [
      "hra_max_rate",
      "ewf_rate",
      "ewf_high_rate",
      "ewf_threshold",
      "hillen_rate",
      "hillen_phaseout_per_year",
      "pension_withdrawal_rate",
    ],
  },
  {
    id: "one-off",
    fields: [
      "transfer_tax_own_home_rate",
      "transfer_tax_general_rate",
      "starter_exemption_max_age",
      "starter_exemption_value_cap",
      "gift_exemption_onetime",
      "gift_exemption_annual",
      "gift_exemption_min_age",
      "gift_exemption_max_age",
    ],
  },
];

// NOTE: wage-tax figures (NL Box 1 loonheffing, the AT income ladder and its social
// insurance and Sonderzahlung fields) are hidden because no projection reads them yet;
// they return here when wage tax enters the projection.
const WAGE_TAX_FIELDS = new Set([
  "box1_rate_1",
  "box1_bracket_1_to",
  "box1_rate_2",
  "box1_bracket_2_to",
  "box1_rate_3",
  "general_credit_max",
  "labour_credit_max",
  ...[1, 2, 3, 4, 5, 6].map((n) => `income_bracket_${n}_to`),
  ...[1, 2, 3, 4, 5, 6, 7].map((n) => `income_rate_${n}`),
  "employee_credit",
  "social_insurance_employee_rate",
  "social_insurance_ceiling",
  "sonderzahlung_rate",
  "sonderzahlung_allowance",
  "sonderzahlung_exempt_below",
  "sonderzahlung_share",
]);

/** Dutch tax names, the same in both locales. A label with chrome to translate, and every
 * Austrian figure, is a `plan.tax.label.<field>` message instead. */
export const FIELD_LABELS: Record<string, string> = {
  box3_rate: "Tarief",
  box3_forfait_bank: "Forfait banktegoeden",
  box3_forfait_investments: "Forfait overige bezittingen",
  box3_forfait_debt: "Forfait schulden",
  wwr_rate: "WWR tarief",
  hra_max_rate: "Hypotheekrenteaftrek max tarief",
  ewf_rate: "Eigenwoningforfait tarief",
  ewf_high_rate: "Eigenwoningforfait tarief (boven drempel)",
  ewf_threshold: "Eigenwoningforfait drempel",
  hillen_rate: "Wet Hillen aftrek",
  hillen_phaseout_per_year: "Wet Hillen afbouw per jaar",
  transfer_tax_own_home_rate: "Overdrachtsbelasting eigen woning",
  transfer_tax_general_rate: "Overdrachtsbelasting algemeen",
  starter_exemption_max_age: "Startersvrijstelling max leeftijd",
  starter_exemption_value_cap: "Startersvrijstelling waardegrens",
  gift_exemption_onetime: "Schenkingsvrijstelling eenmalig",
  gift_exemption_annual: "Schenkingsvrijstelling jaarlijks",
  gift_exemption_min_age: "Schenkingsvrijstelling min leeftijd",
  gift_exemption_max_age: "Schenkingsvrijstelling max leeftijd",
};

/** Groups resolved fields by subsection, in panel order. The subsections are Dutch, so
 * anything they do not claim — every AT figure, and every NL field added since — lands in
 * a trailing "Other" group. A field is labelled by its `plan.tax.label.<field>` message,
 * then its Dutch name, then the server's own English `description`, then its raw name.
 * Dropping unclaimed fields was the older behaviour and it left a non-NL household
 * staring at an empty tax panel. */
export function groupTaxFields(
  fields: Readonly<Record<string, TaxField>>,
  locale: Locale,
): TaxFieldGroup[] {
  const messages: Readonly<Record<string, string>> = MESSAGES[locale];
  const claimed = new Set(GROUPS.flatMap((g) => g.fields));
  const row = (name: string): TaxFieldRow => ({
    name,
    label:
      messages[`plan.tax.label.${name}`] ?? FIELD_LABELS[name] ?? fields[name].description ?? name,
    field: fields[name],
  });
  const rest = Object.keys(fields).filter(
    (name) => !claimed.has(name) && !WAGE_TAX_FIELDS.has(name),
  );
  return [
    ...GROUPS.map(({ id, fields: names }) => ({
      id,
      rows: names.filter((name) => name in fields).map(row),
    })),
    { id: "other", rows: rest.map(row) },
  ]
    .filter((group) => group.rows.length > 0)
    .map((group) => ({ ...group, label: messages[`plan.tax.group.${group.id}`] }));
}
