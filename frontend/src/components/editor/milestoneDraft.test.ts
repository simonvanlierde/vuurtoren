import { describe, expect, it } from "vitest";
import {
  defaultParams,
  emptyDraft,
  fromMilestone,
  isComplete,
  MILESTONE_TYPES,
  type MilestoneType,
  toBody,
} from "./milestoneDraft";

describe("milestone draft", () => {
  it("builds a lump_sum_in body with Decimal strings and a date timing", () => {
    const d = {
      ...emptyDraft(),
      label: "windfall",
      timing: "date" as const,
      on_date: "2027-01-01",
      type: "lump_sum_in" as const,
      params: { amount: "100000", target_account_id: "", is_gift_exemption: true },
    };
    expect(isComplete(d)).toBe(true);
    expect(toBody(d, 1)).toEqual({
      household_id: 1,
      label: "windfall",
      on_date: "2027-01-01",
      age_person_id: null,
      age_years: null,
      params: {
        type: "lump_sum_in",
        amount: "100000",
        target_account_id: null,
        is_gift_exemption: true,
      },
    });
  });

  it("builds an age-timed retire body and nulls the date", () => {
    const d = {
      ...emptyDraft(),
      label: "stop",
      timing: "age" as const,
      age_person: "2",
      age_years: "55",
      type: "retire" as const,
      params: { person_id: "2" },
    };
    expect(toBody(d, 1)).toMatchObject({
      on_date: null,
      age_person_id: 2,
      age_years: 55,
      params: { type: "retire", person_id: 2 },
    });
  });

  it("is incomplete without timing or required params", () => {
    expect(isComplete(emptyDraft())).toBe(false);
    const noAmount = {
      ...emptyDraft(),
      label: "x",
      timing: "date" as const,
      on_date: "2027-01-01",
      type: "lump_sum_out" as const,
      params: { amount: "" },
    };
    expect(isComplete(noAmount)).toBe(false);
  });

  it("round-trips an existing milestone into a draft", () => {
    const draft = fromMilestone({
      id: 7,
      household_id: 1,
      label: "buy",
      on_date: "2028-06-01",
      age_person_id: null,
      age_years: null,
      params: {
        type: "buy_property",
        price: "450000",
        mortgage: "400000",
        annual_rate: "0.044",
        term_months: 360,
        vve_monthly: "0",
        buyer_person_id: null,
        gift_used: "0",
        own_occupancy: true,
      },
    });
    expect(draft.type).toBe("buy_property");
    expect(draft.timing).toBe("date");
    expect(draft.params.price).toBe("450000");
  });

  it("sends a move's retags as one map, leaving out the accounts it keeps", () => {
    const d = {
      ...emptyDraft(),
      label: "Vienna",
      on_date: "2030-01-01",
      type: "change_tax_residence" as const,
      params: { country: "AT", "retag.1": "at.bank", "retag.2": "" },
    };
    expect(toBody(d, 1).params).toEqual({
      type: "change_tax_residence",
      country: "AT",
      retag: { "1": "at.bank" },
    });
  });

  it("holds a move back until every account the new country cannot tax is retagged", () => {
    const d = {
      ...emptyDraft(),
      label: "Vienna",
      on_date: "2030-01-01",
      type: "change_tax_residence" as const,
      params: { country: "AT", "retag.1": "at.bank" },
    };
    expect(isComplete(d, [1, 2])).toBe(false);
    expect(isComplete({ ...d, params: { ...d.params, "retag.2": "at.investment" } }, [1, 2])).toBe(
      true,
    );
    // Not known yet: the target country's treatments are still loading.
    expect(isComplete(d, null)).toBe(false);
  });

  it("round-trips a stored move's retags into the draft", () => {
    const draft = fromMilestone({
      id: 3,
      household_id: 1,
      label: "Vienna",
      on_date: "2030-01-01",
      age_person_id: null,
      age_years: null,
      params: { type: "change_tax_residence", country: "AT", retag: { "4": "at.investment" } },
    });
    expect(draft.params).toEqual({ country: "AT", "retag.4": "at.investment" });
    expect(toBody(draft, 1).params).toEqual({
      type: "change_tax_residence",
      country: "AT",
      retag: { "4": "at.investment" },
    });
  });

  it("defaultParams matches each type's field set", () => {
    // Keyed by MilestoneType, not a loose string map: a type added to MILESTONE_TYPES
    // and forgotten here fails to compile instead of silently going untested — which is
    // how extra_repayment shipped without an entry.
    const expectedKeys: Record<MilestoneType, string[]> = {
      retire: ["person_id"],
      lump_sum_in: ["amount", "target_account_id", "is_gift_exemption"],
      lump_sum_out: ["amount"],
      buy_property: [
        "price",
        "mortgage",
        "annual_rate",
        "term_months",
        "vve_monthly",
        "buyer_person_id",
        "gift_used",
        "own_occupancy",
      ],
      sell_property: ["costs"],
      extra_repayment: ["monthly_amount"],
      income_change: ["cash_flow_id", "new_amount_monthly"],
      expense_change: ["cash_flow_id", "new_amount_monthly"],
      contribution_change: ["cash_flow_id", "new_amount_monthly"],
      change_tax_residence: ["country"],
    };
    for (const type of MILESTONE_TYPES) {
      expect(Object.keys(defaultParams(type))).toEqual(expectedKeys[type]);
    }
    expect(defaultParams("change_tax_residence")).toEqual({ country: "" });
  });
});
