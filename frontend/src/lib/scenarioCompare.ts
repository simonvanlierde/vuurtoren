/**
 * Pure helpers for the scenario-comparison view: overlay-row
 * shaping, the user-edited-rate marker rule, and the standard tax-assumption
 * scenario templates. Net worth arrives from `/api/project` as plain euro floats,
 * so this stays a straight pivot with no cents/Decimal handling.
 */
import type { InlineOverrides, ScenarioCreate, TaxOverrides } from "./api";
import { LINE_COLORS } from "./chartColors";

/** One (colour, dash) per overlay line, so scenarios stay distinguishable without
 * colour (no colour-only encoding). Sea green for growth, ink navy,
 * brick — never beacon amber, which belongs to the beam alone. */
export const LINE_ENCODINGS = [
  { color: LINE_COLORS.baseline, dash: undefined }, // baseline — ink/paper, solid
  { color: LINE_COLORS.green, dash: undefined }, // sea green, solid
  { color: LINE_COLORS.brick, dash: "6 3" }, // brick, dashed
  { color: LINE_COLORS.baseline, dash: "1 4" }, // ink/paper, dotted
  { color: LINE_COLORS.green, dash: "8 3 2 3" }, // sea green, dash-dot
] as const;

/** True when a scenario hand-sets at least one tax rate: such a scenario
 * carries the marker everywhere its consequences show. An override that only touches
 * `assumptions` (e.g. frozen allowances) is NOT a user-edited *rate* and stays plain. */
export function hasUserTaxOverride(overrides: InlineOverrides): boolean {
  const tax = overrides.tax;
  if (!tax) return false;
  return Object.values(tax).some((byYear) =>
    Object.values(byYear).some((fields) => Object.keys(fields).length > 0),
  );
}

export interface OverlayColumn {
  key: string;
  netWorth: readonly number[];
}

export type OverlayRow = { date: string } & Record<string, number | string | null>;

/** Pivot each column's run-0 net-worth series into one row per month for Recharts.
 * A missing point becomes `null` so the line breaks rather than dropping to zero. */
export function buildOverlayRows(
  months: readonly string[],
  columns: readonly OverlayColumn[],
): OverlayRow[] {
  return months.map((date, i) => {
    const row: OverlayRow = { date };
    for (const c of columns) row[c.key] = c.netWorth[i] ?? null;
    return row;
  });
}

// A permanent regime change must bite every projected year, not just one:
// the engine resolves tax per calendar year with no carry-forward, so a single-year
// override would silently no-op. Cover the whole plausible horizon.
const HORIZON_END_YEAR = 2100;

/** The data-independent tax-assumption scenarios. "WWR from 2028"
 * is the baseline (no override), so it is not created here. Values are strings — the
 * API parses them to `Decimal`, never through a float. */
export interface RentVsBuyInput {
  householdId: number;
  /** Which EXPENSE cash flow is the rent — the one thing the form must ask. */
  rentFlowId: number;
  rentAmount: number;
  nicerRentAmount: number;
  /** First of the purchase month, ISO. */
  buyDate: string;
  priceA: number;
  priceB: number;
  mortgageA: number;
  annualRate: number;
}

/** First of the month before `iso` — rent must stop before the mortgage starts,
 * and `CashFlow.end_date` is inclusive. */
function monthBefore(iso: string): string {
  const [y, m] = iso.split("-").map(Number);
  const prev = m === 1 ? [y - 1, 12] : [y, m - 1];
  return `${prev[0]}-${String(prev[1]).padStart(2, "0")}-01`;
}

const asMoney = (euros: number): string => euros.toFixed(2);

/** The rent-vs-buy seed set — the question this app exists to answer.
 * Two renting scenarios patch the rent flow; two buying scenarios end the rent the
 * month before a BuyProperty milestone fires. All numbers travel as Decimal strings. */
export function rentVsBuyScenarios(input: RentVsBuyInput): ScenarioCreate[] {
  const rentEnd = monthBefore(input.buyDate);
  const buy = (price: number, mortgage: number): ScenarioCreate => ({
    household_id: input.householdId,
    name: `Buy €${Math.round(price / 1000)}k`,
    overrides: {
      cash_flows: { [input.rentFlowId]: { end_date: rentEnd } },
      added_milestones: [
        {
          // Synthetic id: this milestone exists only inside the scenario diff.
          id: -1,
          household_id: input.householdId,
          label: `Buy €${Math.round(price / 1000)}k`,
          on_date: input.buyDate,
          params: {
            type: "buy_property",
            price: String(price),
            mortgage: String(mortgage),
            annual_rate: String(input.annualRate),
          },
        },
      ],
    },
  });
  const rent = (name: string, amount: number): ScenarioCreate => ({
    household_id: input.householdId,
    name,
    overrides: {
      cash_flows: { [input.rentFlowId]: { amount_monthly: asMoney(amount) } },
    },
  });
  // NOTE: the dearer purchase keeps the same down payment (price − mortgage),
  // a per-scenario mortgage field if that rule ever misleads.
  const downPayment = input.priceA - input.mortgageA;
  return [
    rent(`Stay renting €${input.rentAmount}`, input.rentAmount),
    rent(`Rent nicer €${input.nicerRentAmount}`, input.nicerRentAmount),
    buy(input.priceA, input.mortgageA),
    buy(input.priceB, input.priceB - downPayment),
  ];
}

/** One life-event preset: what fraction of the baseline income survives the shock.
 * `fraction: 0` is a sabbatical (no income), `0.7` is WW-shaped. Deliberately a plain
 * number and not a modelled benefit: this is an income-shock preset,
 * not WIA/AOV law, and the same mechanism serves all three life events. */
export interface IncomeShockPreset {
  key: string;
  label: string;
  fraction: number;
}

export interface IncomeShockInput {
  householdId: number;
  /** Which INCOME cash flow takes the hit — the one thing the form must ask. */
  incomeFlowId: number;
  /** What that flow pays today; the restore milestone puts it back to exactly this. */
  baselineMonthly: number;
  /** First of the month the shock starts, ISO. */
  startDate: string;
  /** How long it lasts. `null` is permanent — no restore milestone at all. */
  months: number | null;
  presets: IncomeShockPreset[];
}

/** First of the month `count` months after `iso`. */
function monthsAfter(iso: string, count: number): string {
  const [y, m] = iso.split("-").map(Number);
  const zero = y * 12 + (m - 1) + count;
  return `${Math.floor(zero / 12)}-${String((zero % 12) + 1).padStart(2, "0")}-01`;
}

/** Sabbatical / job loss / disability as one mechanism: drop an income
 * flow at a date, put it back N months later. Two `income_change` milestones per
 * scenario — no engine change, and the three life events differ only in how much
 * income survives and for how long.
 *
 * A permanent shock (`months: null`) emits no restore milestone rather than a distant
 * one: "recovers in 2099" and "never recovers" are different claims.
 */
export function incomeShockScenarios(input: IncomeShockInput): ScenarioCreate[] {
  const change = (id: number, onDate: string, amount: number) => ({
    // Synthetic negative id: this milestone exists only inside the scenario diff.
    id,
    household_id: input.householdId,
    label: onDate,
    on_date: onDate,
    params: {
      type: "income_change",
      cash_flow_id: input.incomeFlowId,
      new_amount_monthly: asMoney(amount),
    },
  });
  return input.presets.map((preset) => ({
    household_id: input.householdId,
    name: preset.label,
    overrides: {
      added_milestones: [
        change(-1, input.startDate, input.baselineMonthly * preset.fraction),
        ...(input.months === null
          ? []
          : [change(-2, monthsAfter(input.startDate, input.months), input.baselineMonthly)]),
      ],
    },
  }));
}

export interface RetirementSmileInput {
  householdId: number;
  /** Which EXPENSE flow declines — usually the general living-expenses line. */
  expenseFlowId: number;
  baselineMonthly: number;
  /** First of the month the decline starts from; the first step lands a year later. */
  startDate: string;
  /** Real decline per year, in percent. 2 is Bernicke-shaped. */
  annualDeclinePct: number;
  /** How many yearly steps before it flattens. Spending tails off, it does not vanish. */
  years: number;
}

/** The retirement smile: real spending drifts down through the active
 * retirement years, then flattens. One `expense_change` milestone per year.
 *
 * Nominal amounts, real decline: a milestone's new amount is quoted in the euros of its
 * own change month and an inflation-linked flow re-bases there, so stepping
 * to `baseline × 0.98ⁿ` *is* a 2%/yr real cut rather than a nominal one.
 *
 * NL-specific and deliberate: healthcare costs are a flat budget line here, so the smile
 * is a decline that flattens, not the US curve that turns back up.
 */
export function retirementSmileScenario(input: RetirementSmileInput): ScenarioCreate {
  const factor = 1 - input.annualDeclinePct / 100;
  const steps = factor === 1 ? 0 : input.years;
  return {
    household_id: input.householdId,
    name: `Retirement smile −${input.annualDeclinePct}%/yr`,
    overrides: {
      added_milestones: Array.from({ length: steps }, (_, i) => {
        const onDate = monthsAfter(input.startDate, 12 * (i + 1));
        return {
          // Synthetic ids, negative so they never collide with a stored milestone.
          id: -(i + 1),
          household_id: input.householdId,
          label: onDate,
          on_date: onDate,
          params: {
            type: "expense_change",
            cash_flow_id: input.expenseFlowId,
            new_amount_monthly: asMoney(input.baselineMonthly * factor ** (i + 1)),
          },
        };
      }),
    },
  };
}

export interface AflossenVsBeleggenInput {
  householdId: number;
  /** Which CONTRIBUTION flow is the investing one — the beleggen arm raises it. */
  contributionFlowId: number;
  /** What that flow already puts away each month; the arm adds to it, never replaces. */
  contributionMonthly: number;
  /** The euros under debate: into the mortgage, or into the portfolio. */
  extraMonthly: number;
  /** First of the month both arms start, ISO. */
  startDate: string;
}

/** *The* Dutch household question: an extra €500 a month into the
 * mortgage, or into the portfolio?
 *
 * Two arms, one date, the same money — anything else rigs the comparison. Aflossen adds
 * an `extra_repayment` milestone (principal down, term shortens); beleggen raises the
 * chosen contribution flow by the same amount from the same month.
 *
 * Genuinely hard here rather than arithmetic, which is why it is worth a template: the
 * answer couples the mortgage rate against the return assumption, but also HRA,
 * eigenwoningforfait, Wet Hillen's phase-out and Box 3 — all four already modelled, and
 * all four moving in opposite directions as the balance falls.
 */
export function aflossenVsBeleggenScenarios(input: AflossenVsBeleggenInput): ScenarioCreate[] {
  const label = `€${Math.round(input.extraMonthly)}/mo`;
  const milestone = (params: Record<string, unknown>) => ({
    // Synthetic id: this milestone exists only inside the scenario diff.
    id: -1,
    household_id: input.householdId,
    label: input.startDate,
    on_date: input.startDate,
    params,
  });
  return [
    {
      household_id: input.householdId,
      name: `Aflossen ${label}`,
      overrides: {
        added_milestones: [
          milestone({ type: "extra_repayment", monthly_amount: asMoney(input.extraMonthly) }),
        ],
      },
    },
    {
      household_id: input.householdId,
      name: `Beleggen ${label}`,
      overrides: {
        added_milestones: [
          milestone({
            type: "contribution_change",
            cash_flow_id: input.contributionFlowId,
            new_amount_monthly: asMoney(input.contributionMonthly + input.extraMonthly),
          }),
        ],
      },
    },
  ];
}

export interface AllocationAccount {
  id: number;
  kind: "equity" | "bond";
  value: number;
}

export interface AllocationInput {
  householdId: number;
  /** Only the EQUITY and BOND accounts — cash, property and pension are not allocation. */
  accounts: AllocationAccount[];
  /** Equity percentages to compare, e.g. `[80, 60]` for 80/20 against 60/40. */
  splits: number[];
}

/** "80/20 or 60/40?" as a comparison rather than an answer.
 *
 * Each scenario restates today's equity and bond balances at a different split, holding
 * the invested total fixed — otherwise it compares allocation *and* wealth, and the
 * wealth would dominate. Within a kind the money keeps its existing proportions, so a
 * household with two trackers does not silently consolidate into one.
 *
 * Returns nothing when there is no bond side: with only equity accounts there is nowhere
 * for the non-equity share to sit, and a comparison that quietly invents an account
 * would be answering a different question. The caller says so instead.
 *
 * This is the honest form of the allocation question — a distribution to look at, not a
 * recommendation — which is also why the optimiser stays unbuilt (`docs/decisions.md`).
 */
export function allocationScenarios(input: AllocationInput): ScenarioCreate[] {
  const equity = input.accounts.filter((a) => a.kind === "equity");
  const bonds = input.accounts.filter((a) => a.kind === "bond");
  if (equity.length === 0 || bonds.length === 0) return [];

  const total = input.accounts.reduce((sum, a) => sum + a.value, 0);
  const equityNow = equity.reduce((sum, a) => sum + a.value, 0);
  const bondNow = bonds.reduce((sum, a) => sum + a.value, 0);

  /** Spread `target` across `group` in its existing proportions; an empty group's share
   * is split evenly, which only arises when that side currently holds nothing. */
  const spread = (group: AllocationAccount[], now: number, target: number) =>
    group.map((a) => ({
      id: a.id,
      value: now > 0 ? (a.value / now) * target : target / group.length,
    }));

  return input.splits.map((pct) => {
    const parts = [
      ...spread(equity, equityNow, (total * pct) / 100),
      ...spread(bonds, bondNow, (total * (100 - pct)) / 100),
    ];
    return {
      household_id: input.householdId,
      name: `${pct}/${100 - pct} aandelen/obligaties`,
      overrides: {
        accounts: Object.fromEntries(parts.map((p) => [p.id, { manual_value: asMoney(p.value) }])),
      },
    };
  });
}

export function standardTaxScenarios(householdId: number, fromYear: number): ScenarioCreate[] {
  const years: number[] = [];
  for (let y = fromYear; y <= HORIZON_END_YEAR; y++) years.push(y);
  const everyYear = (fields: Record<string, string>): TaxOverrides => ({
    NL: Object.fromEntries(years.map((y) => [y, fields])),
  });
  return [
    {
      household_id: householdId,
      name: "Forfaitair continues",
      overrides: { tax: everyYear({ regime_switch_year: "9999" }) },
    },
    {
      household_id: householdId,
      name: "Box 3 at 40%",
      overrides: { tax: everyYear({ box3_rate: "0.40" }) },
    },
    {
      household_id: householdId,
      name: "Heffingsvrij vermogen frozen",
      overrides: { assumptions: { index_tax_allowances: false } },
    },
  ];
}
