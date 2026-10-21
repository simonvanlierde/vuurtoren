/**
 * Pure grouping over already-priced accounts ("accounts grouped by
 * person and kind"). Takes plain eurocent balances — see `money.ts` for turning the
 * API's Decimal strings into cents — so this stays testable with no API shapes.
 */

export interface AccountBalance {
  id: number;
  name: string;
  kind: string;
  ownerPersonId: number | null;
  cents: number;
}

export interface PersonGroup {
  personId: number | null;
  personName: string;
  accounts: readonly AccountBalance[];
  kindTotals: Record<string, number>;
  totalCents: number;
}

const UNOWNED_LABEL = "Household";

/** Group accounts by owner, each owner's accounts further summed by kind. */
export function groupByPerson(
  accounts: readonly AccountBalance[],
  personNameById: ReadonlyMap<number, string>,
): PersonGroup[] {
  const byOwner = new Map<number | null, AccountBalance[]>();
  for (const account of accounts) {
    const key = account.ownerPersonId;
    const bucket = byOwner.get(key);
    if (bucket) bucket.push(account);
    else byOwner.set(key, [account]);
  }

  return [...byOwner.entries()]
    .sort(([a], [b]) => (a ?? Infinity) - (b ?? Infinity))
    .map(([personId, ownerAccounts]) => {
      const kindTotals: Record<string, number> = {};
      for (const account of ownerAccounts) {
        kindTotals[account.kind] = (kindTotals[account.kind] ?? 0) + account.cents;
      }
      return {
        personId,
        personName: personId === null ? UNOWNED_LABEL : (personNameById.get(personId) ?? "Unknown"),
        accounts: ownerAccounts,
        kindTotals,
        totalCents: ownerAccounts.reduce((sum, a) => sum + a.cents, 0),
      };
    });
}

/** Household-wide subtotal per `AccountKind` (the equity/cash/debt breakdown). */
export function totalsByKind(accounts: readonly AccountBalance[]): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const account of accounts) {
    totals[account.kind] = (totals[account.kind] ?? 0) + account.cents;
  }
  return totals;
}

export function householdTotalCents(accounts: readonly AccountBalance[]): number {
  return accounts.reduce((sum, a) => sum + a.cents, 0);
}
