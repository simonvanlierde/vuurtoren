import { describe, expect, it } from "vitest";
import { type AccountBalance, groupByPerson, householdTotalCents, totalsByKind } from "./grouping";

const accounts: AccountBalance[] = [
  { id: 1, name: "World equity index fund", kind: "equity", ownerPersonId: 1, cents: 5_000_000 },
  { id: 2, name: "Pension fund", kind: "pension", ownerPersonId: 1, cents: 1_000_000 },
  { id: 3, name: "World equity ETF", kind: "equity", ownerPersonId: 2, cents: 500_000 },
  { id: 4, name: "Cash buffer", kind: "cash", ownerPersonId: 2, cents: 1_000_000 },
  { id: 5, name: "Mortgage", kind: "debt", ownerPersonId: null, cents: -3_000_000 },
];

const names = new Map([
  [1, "Alex"],
  [2, "Sam"],
]);

describe("groupByPerson", () => {
  it("groups accounts under their owner, in ascending person-id order", () => {
    const groups = groupByPerson(accounts, names);
    expect(groups.map((g) => g.personName)).toEqual(["Alex", "Sam", "Household"]);
  });

  it("sums each owner's accounts by kind and in total", () => {
    const [alex] = groupByPerson(accounts, names);
    expect(alex.kindTotals).toEqual({ equity: 5_000_000, pension: 1_000_000 });
    expect(alex.totalCents).toBe(6_000_000);
  });

  it("buckets unowned accounts under Household", () => {
    const groups = groupByPerson(accounts, names);
    const household = groups.find((g) => g.personId === null);
    expect(household?.totalCents).toBe(-3_000_000);
  });
});

describe("totalsByKind", () => {
  it("sums across all owners for the equity/cash/debt breakdown", () => {
    expect(totalsByKind(accounts)).toEqual({
      equity: 5_500_000,
      pension: 1_000_000,
      cash: 1_000_000,
      debt: -3_000_000,
    });
  });
});

describe("householdTotalCents", () => {
  it("nets debt against assets", () => {
    expect(householdTotalCents(accounts)).toBe(4_500_000);
  });
});
