/** Pure draft↔body logic for the milestone editor — kept out of the
 * component so the conversions and completeness gate are unit-testable. All
 * Decimal params stay strings end to end; ints (ids, months, years) convert
 * via Number at the boundary. */
import type { Milestone, MilestoneIn } from "../../lib/api";
import { isDecimalString } from "../../lib/money";

export const MILESTONE_TYPES = [
  "retire",
  "lump_sum_in",
  "lump_sum_out",
  "buy_property",
  "sell_property",
  "extra_repayment",
  "income_change",
  "expense_change",
  "contribution_change",
  "change_tax_residence",
] as const;
export type MilestoneType = (typeof MILESTONE_TYPES)[number];

export interface MilestoneDraft {
  label: string;
  timing: "date" | "age";
  on_date: string;
  age_person: string;
  age_years: string;
  type: MilestoneType;
  params: Record<string, string | boolean>;
}

/** Per-type param fields: [name, kind]. Kinds drive both conversion and the
 * completeness gate; "id?"/"decimal?" are optional. A "retag" field is a map from
 * account id to tax treatment, held in the draft as one `retag.<id>` entry per account
 * so the flat params record can carry it; an empty entry keeps that account's tag. */
const PARAM_FIELDS: Record<
  MilestoneType,
  [string, "decimal" | "decimal?" | "id" | "id?" | "int" | "bool" | "text" | "retag"][]
> = {
  retire: [["person_id", "id"]],
  lump_sum_in: [
    ["amount", "decimal"],
    ["target_account_id", "id?"],
    ["is_gift_exemption", "bool"],
  ],
  lump_sum_out: [["amount", "decimal"]],
  buy_property: [
    ["price", "decimal"],
    ["mortgage", "decimal"],
    ["annual_rate", "decimal"],
    ["term_months", "int"],
    ["vve_monthly", "decimal"],
    ["buyer_person_id", "id?"],
    ["gift_used", "decimal"],
    ["own_occupancy", "bool"],
  ],
  sell_property: [["costs", "decimal"]],
  // Aflossen: a fixed monthly amount straight onto the principal, from this date until
  // the mortgage is gone. The annuity payment is untouched, so the term shortens.
  extra_repayment: [["monthly_amount", "decimal"]],
  income_change: [
    ["cash_flow_id", "id"],
    ["new_amount_monthly", "decimal"],
  ],
  expense_change: [
    ["cash_flow_id", "id"],
    ["new_amount_monthly", "decimal"],
  ],
  contribution_change: [
    ["cash_flow_id", "id"],
    ["new_amount_monthly", "decimal"],
  ],
  change_tax_residence: [
    ["country", "text"],
    ["retag", "retag"],
  ],
};

const RETAG_PREFIX = "retag.";

/** The draft key for one account's new treatment in a move's retag map. */
export function retagKey(accountId: number): string {
  return `${RETAG_PREFIX}${accountId}`;
}

export function defaultParams(type: MilestoneType): Record<string, string | boolean> {
  const defaults: Record<string, string | boolean> = {};
  for (const [name, kind] of PARAM_FIELDS[type]) {
    if (kind === "retag") continue; // one entry per account, added as they are picked
    if (kind === "bool") defaults[name] = name === "own_occupancy";
    else if (name === "term_months") defaults[name] = "360";
    else if (name === "vve_monthly" || name === "gift_used" || name === "costs")
      defaults[name] = "0";
    else defaults[name] = "";
  }
  return defaults;
}

export function emptyDraft(): MilestoneDraft {
  return {
    label: "",
    timing: "date",
    on_date: "",
    age_person: "",
    age_years: "",
    type: "retire",
    params: defaultParams("retire"),
  };
}

export function fromMilestone(m: Milestone): MilestoneDraft {
  const { type, ...rest } = m.params;
  const params: Record<string, string | boolean> = defaultParams(type as MilestoneType);
  for (const [key, value] of Object.entries(rest)) {
    if (key === "retag" && typeof value === "object" && value !== null) {
      for (const [id, treatment] of Object.entries(value)) {
        params[`${RETAG_PREFIX}${id}`] = String(treatment);
      }
      continue;
    }
    params[key] = typeof value === "boolean" ? value : value == null ? "" : String(value);
  }
  return {
    label: m.label,
    timing: m.on_date != null ? "date" : "age",
    on_date: m.on_date ?? "",
    age_person: m.age_person_id != null ? String(m.age_person_id) : "",
    age_years: m.age_years != null ? String(m.age_years) : "",
    type: type as MilestoneType,
    params,
  };
}

/** `requiredRetags` lists the accounts a move must retag: those whose current treatment
 * the target country does not know. `null` means that is not known yet (the country's
 * treatments are still loading), which holds the draft back like a missing field. */
export function isComplete(
  d: MilestoneDraft,
  requiredRetags: readonly number[] | null = [],
): boolean {
  if (d.timing === "date" ? d.on_date === "" : d.age_person === "" || d.age_years === "") {
    return false;
  }
  return PARAM_FIELDS[d.type].every(([name, kind]) => {
    const value = d.params[name];
    if (kind === "retag") {
      return requiredRetags?.every((id) => Boolean(d.params[retagKey(id)])) ?? false;
    }
    if (kind === "bool" || kind === "id?" || kind === "decimal?") return true;
    if (kind === "decimal") return typeof value === "string" && isDecimalString(value);
    if (kind === "id" || kind === "int") return typeof value === "string" && value !== "";
    return typeof value === "string" && value !== "";
  });
}

export function toBody(d: MilestoneDraft, householdId: number): MilestoneIn {
  const params: Record<string, unknown> = { type: d.type };
  for (const [name, kind] of PARAM_FIELDS[d.type]) {
    const value = d.params[name];
    if (kind === "retag") {
      params[name] = Object.fromEntries(
        Object.entries(d.params)
          .filter(([key, v]) => key.startsWith(RETAG_PREFIX) && v !== "")
          .map(([key, v]) => [key.slice(RETAG_PREFIX.length), v]),
      );
    } else if (kind === "bool") params[name] = value === true;
    else if (kind === "id" || kind === "int") params[name] = Number(value);
    else if (kind === "id?") params[name] = value === "" ? null : Number(value);
    else params[name] = value;
  }
  return {
    household_id: householdId,
    label: d.label,
    on_date: d.timing === "date" ? d.on_date : null,
    age_person_id: d.timing === "age" ? Number(d.age_person) : null,
    age_years: d.timing === "age" ? Number(d.age_years) : null,
    params: params as MilestoneIn["params"],
  };
}
