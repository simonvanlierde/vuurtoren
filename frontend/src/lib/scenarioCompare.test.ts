import { describe, expect, it } from "vitest";
import type { InlineOverrides } from "./api";
import {
  aflossenVsBeleggenScenarios,
  allocationScenarios,
  buildOverlayRows,
  hasUserTaxOverride,
  incomeShockScenarios,
  rentVsBuyScenarios,
  retirementSmileScenario,
  standardTaxScenarios,
} from "./scenarioCompare";

const overrides = (o: InlineOverrides): InlineOverrides => o;

describe("hasUserTaxOverride", () => {
  it("is true when a tax rate is hand-set", () => {
    expect(hasUserTaxOverride(overrides({ tax: { NL: { 2026: { box3_rate: "0.40" } } } }))).toBe(
      true,
    );
  });

  it("is false for an empty or absent tax group", () => {
    expect(hasUserTaxOverride(overrides({}))).toBe(false);
    expect(hasUserTaxOverride(overrides({ tax: {} }))).toBe(false);
    expect(hasUserTaxOverride(overrides({ tax: { NL: {} } }))).toBe(false);
  });

  it("is false for an assumptions-only override (not a user-edited rate)", () => {
    expect(hasUserTaxOverride(overrides({ assumptions: { index_tax_allowances: false } }))).toBe(
      false,
    );
  });
});

describe("buildOverlayRows", () => {
  it("pivots columns into one row per month, null for gaps", () => {
    const rows = buildOverlayRows(
      ["2026-01-01", "2026-02-01"],
      [
        { key: "baseline", netWorth: [100, 200] },
        { key: "s1", netWorth: [110] },
      ],
    );
    expect(rows).toEqual([
      { date: "2026-01-01", baseline: 100, s1: 110 },
      { date: "2026-02-01", baseline: 200, s1: null },
    ]);
  });
});

describe("standardTaxScenarios", () => {
  const set = standardTaxScenarios(7, 2026);

  it("creates the three data-independent templates", () => {
    expect(set.map((s) => s.name)).toEqual([
      "Forfaitair continues",
      "Box 3 at 40%",
      "Heffingsvrij vermogen frozen",
    ]);
    expect(set.every((s) => s.household_id === 7)).toBe(true);
  });

  it("keys tax overrides across the whole horizon so they bite every year", () => {
    const forfaitair = set[0].overrides.tax?.NL ?? {};
    const years = Object.keys(forfaitair).map(Number);
    expect(years).toContain(2026);
    expect(years).toContain(2028);
    expect(Math.max(...years)).toBe(2100);
    expect(forfaitair[2028]).toEqual({ regime_switch_year: "9999" });
    expect(set[1].overrides.tax?.NL?.[2050]).toEqual({ box3_rate: "0.40" });
  });

  it("marks the two rate scenarios and leaves the assumptions one plain", () => {
    expect(hasUserTaxOverride(set[0].overrides)).toBe(true);
    expect(hasUserTaxOverride(set[1].overrides)).toBe(true);
    expect(hasUserTaxOverride(set[2].overrides)).toBe(false);
    expect(set[2].overrides.assumptions).toEqual({ index_tax_allowances: false });
  });
});

describe("rentVsBuyScenarios", () => {
  const set = rentVsBuyScenarios({
    householdId: 7,
    rentFlowId: 3,
    rentAmount: 1200,
    nicerRentAmount: 1700,
    buyDate: "2027-06-01",
    priceA: 360000,
    priceB: 500000,
    mortgageA: 340000,
    annualRate: 0.042,
  });

  it("creates the four tax templates, named with their numbers", () => {
    expect(set.map((s) => s.name)).toEqual([
      "Stay renting €1200",
      "Rent nicer €1700",
      "Buy €360k",
      "Buy €500k",
    ]);
    expect(set.every((s) => s.household_id === 7)).toBe(true);
  });

  it("pins or raises the rent flow in the renting scenarios", () => {
    expect(set[0].overrides.cash_flows).toEqual({ 3: { amount_monthly: "1200.00" } });
    expect(set[1].overrides.cash_flows).toEqual({ 3: { amount_monthly: "1700.00" } });
  });

  it("ends the rent the month before the purchase (end_date is inclusive)", () => {
    expect(set[2].overrides.cash_flows).toEqual({ 3: { end_date: "2027-05-01" } });
    expect(set[3].overrides.cash_flows).toEqual({ 3: { end_date: "2027-05-01" } });
  });

  it("adds a BuyProperty milestone with Decimal-string params", () => {
    const m = set[2].overrides.added_milestones?.[0] as Record<string, unknown>;
    expect(m.on_date).toBe("2027-06-01");
    expect(m.params).toEqual({
      type: "buy_property",
      price: "360000",
      mortgage: "340000",
      annual_rate: "0.042",
    });
  });

  it("keeps the same down payment for the dearer purchase", () => {
    const m = set[3].overrides.added_milestones?.[0] as { params: { mortgage: string } };
    expect(m.params.mortgage).toBe("480000"); // 500k - (360k - 340k) down payment
  });
});

describe("incomeShockScenarios", () => {
  const set = incomeShockScenarios({
    householdId: 7,
    incomeFlowId: 4,
    baselineMonthly: 4000,
    startDate: "2028-03-01",
    months: 12,
    presets: [
      { key: "sabbatical", label: "Sabbatical", fraction: 0 },
      { key: "job_loss", label: "Job loss", fraction: 0.7 },
    ],
  });

  it("makes one scenario per preset", () => {
    expect(set.map((s) => s.name)).toEqual(["Sabbatical", "Job loss"]);
    expect(set.every((s) => s.household_id === 7)).toBe(true);
  });

  it("drops the income at the start month and restores it after", () => {
    const ms = set[1].overrides.added_milestones as Record<string, unknown>[];
    expect(ms).toHaveLength(2);
    expect(ms[0].on_date).toBe("2028-03-01");
    expect(ms[0].params).toEqual({
      type: "income_change",
      cash_flow_id: 4,
      new_amount_monthly: "2800.00",
    });
    expect(ms[1].on_date).toBe("2029-03-01");
    expect(ms[1].params).toEqual({
      type: "income_change",
      cash_flow_id: 4,
      new_amount_monthly: "4000.00",
    });
  });

  it("a total stop is 0, not a missing milestone", () => {
    const ms = set[0].overrides.added_milestones as Record<string, unknown>[];
    expect((ms[0].params as { new_amount_monthly: string }).new_amount_monthly).toBe("0.00");
  });

  it("rolls the restore date across a year boundary", () => {
    const [s] = incomeShockScenarios({
      householdId: 1,
      incomeFlowId: 2,
      baselineMonthly: 1000,
      startDate: "2028-11-01",
      months: 4,
      presets: [{ key: "job_loss", label: "X", fraction: 0.5 }],
    });
    const ms = s.overrides.added_milestones as Record<string, unknown>[];
    expect(ms[1].on_date).toBe("2029-03-01");
  });

  it("omits the restore milestone when the shock is permanent", () => {
    const [s] = incomeShockScenarios({
      householdId: 1,
      incomeFlowId: 2,
      baselineMonthly: 1000,
      startDate: "2028-01-01",
      months: null,
      presets: [{ key: "disability", label: "Disability", fraction: 0.7 }],
    });
    // Permanent by choice — a restore milestone would silently un-do it.
    expect(s.overrides.added_milestones).toHaveLength(1);
  });

  it("gives each scenario a synthetic milestone id, never a real one", () => {
    const ms = set[0].overrides.added_milestones as Record<string, unknown>[];
    expect(ms.every((m) => (m.id as number) < 0)).toBe(true);
  });
});

describe("retirementSmileScenario", () => {
  const s = retirementSmileScenario({
    householdId: 7,
    expenseFlowId: 9,
    baselineMonthly: 3000,
    startDate: "2040-01-01",
    annualDeclinePct: 2,
    years: 3,
  });

  it("steps the expense down once a year, in real terms", () => {
    const ms = s.overrides.added_milestones as Record<string, unknown>[];
    expect(ms.map((m) => m.on_date)).toEqual(["2041-01-01", "2042-01-01", "2043-01-01"]);
    const amounts = ms.map((m) => (m.params as { new_amount_monthly: string }).new_amount_monthly);
    // 3000 x 0.98^n, quoted in the euros of the change month — the engine re-bases an
    // inflation-linked flow there, so a nominal step is a real decline.
    expect(amounts).toEqual(["2940.00", "2881.20", "2823.58"]);
  });

  it("stops declining after `years` — the smile flattens, it does not fall forever", () => {
    const ms = s.overrides.added_milestones as unknown[];
    expect(ms).toHaveLength(3);
  });

  it("targets the chosen expense flow with expense_change", () => {
    const ms = s.overrides.added_milestones as Record<string, unknown>[];
    expect((ms[0].params as { type: string; cash_flow_id: number }).type).toBe("expense_change");
    expect((ms[0].params as { cash_flow_id: number }).cash_flow_id).toBe(9);
  });

  it("emits nothing at a zero decline rather than a run of identical milestones", () => {
    const flat = retirementSmileScenario({
      householdId: 7,
      expenseFlowId: 9,
      baselineMonthly: 3000,
      startDate: "2040-01-01",
      annualDeclinePct: 0,
      years: 3,
    });
    expect(flat.overrides.added_milestones).toEqual([]);
  });
});

describe("aflossenVsBeleggenScenarios", () => {
  const set = aflossenVsBeleggenScenarios({
    householdId: 7,
    contributionFlowId: 4,
    contributionMonthly: 1000,
    extraMonthly: 500,
    startDate: "2027-01-01",
  });

  it("makes exactly two symmetric arms", () => {
    expect(set.map((s) => s.name)).toEqual(["Aflossen €500/mo", "Beleggen €500/mo"]);
  });

  it("puts the extra onto the mortgage in the aflossen arm", () => {
    const ms = set[0].overrides.added_milestones as Record<string, unknown>[];
    expect(ms).toHaveLength(1);
    expect(ms[0].on_date).toBe("2027-01-01");
    expect(ms[0].params).toEqual({ type: "extra_repayment", monthly_amount: "500.00" });
  });

  it("puts the same money into the contribution flow in the beleggen arm", () => {
    const ms = set[1].overrides.added_milestones as Record<string, unknown>[];
    expect(ms).toHaveLength(1);
    expect(ms[0].on_date).toBe("2027-01-01");
    // Raised, not replaced: the household keeps investing what it already was.
    expect(ms[0].params).toEqual({
      type: "contribution_change",
      cash_flow_id: 4,
      new_amount_monthly: "1500.00",
    });
  });

  it("starts both arms on the same date, or the comparison is rigged", () => {
    const dates = set.map(
      (s) => (s.overrides.added_milestones as Record<string, unknown>[])[0].on_date,
    );
    expect(dates[0]).toBe(dates[1]);
  });
});

describe("allocationScenarios", () => {
  const accounts = [
    { id: 1, kind: "equity" as const, value: 60000 },
    { id: 2, kind: "equity" as const, value: 20000 },
    { id: 3, kind: "bond" as const, value: 20000 },
  ];
  const set = allocationScenarios({ householdId: 7, accounts, splits: [80, 60] });

  it("makes one scenario per split, named for it", () => {
    expect(set.map((s) => s.name)).toEqual([
      "80/20 aandelen/obligaties",
      "60/40 aandelen/obligaties",
    ]);
  });

  it("keeps the invested total identical, or it is not an allocation comparison", () => {
    for (const s of set) {
      const patched = s.overrides.accounts as Record<number, { manual_value: string }>;
      const total = Object.values(patched).reduce((sum, p) => sum + Number(p.manual_value), 0);
      expect(total).toBeCloseTo(100000, 2);
    }
  });

  it("splits within a kind in proportion to what is already there", () => {
    const p = set[0].overrides.accounts as Record<number, { manual_value: string }>;
    // 80% of 100k across two equity accounts holding 60k and 20k -> 3:1.
    expect(p[1].manual_value).toBe("60000.00");
    expect(p[2].manual_value).toBe("20000.00");
    expect(p[3].manual_value).toBe("20000.00");
  });

  it("moves money when the split differs from today's", () => {
    const p = set[1].overrides.accounts as Record<number, { manual_value: string }>;
    expect(Number(p[1].manual_value) + Number(p[2].manual_value)).toBeCloseTo(60000, 2);
    expect(Number(p[3].manual_value)).toBeCloseTo(40000, 2);
  });

  it("handles an all-equity split without dividing by zero on the bond side", () => {
    const [all] = allocationScenarios({ householdId: 7, accounts, splits: [100] });
    const p = all.overrides.accounts as Record<number, { manual_value: string }>;
    expect(Number(p[3].manual_value)).toBe(0);
    expect(Number(p[1].manual_value) + Number(p[2].manual_value)).toBeCloseTo(100000, 2);
  });

  it("returns nothing when there is no bond side to shift into", () => {
    const equityOnly = [{ id: 1, kind: "equity" as const, value: 50000 }];
    expect(allocationScenarios({ householdId: 7, accounts: equityOnly, splits: [60] })).toEqual([]);
  });
});
