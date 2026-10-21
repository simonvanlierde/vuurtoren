import { Lock } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { CompositionBar } from "../components/CompositionBar";
import { AccountDrawer } from "../components/editor/AccountDrawer";
import { PriceDrawer } from "../components/editor/PriceDrawer";
import { GettingStarted } from "../components/GettingStarted";
import { NetWorthChart } from "../components/NetWorthChart";
import { DataTable } from "../components/ui/DataTable";
import {
  type Account,
  type AccountKind,
  type Currency,
  useAccounts,
  useHouseholds,
  usePeople,
  usePricePoints,
  useRefreshPrices,
} from "../lib/api";
import { SERIES } from "../lib/chartColors";
import { KIND_COLORS, KIND_ORDER } from "../lib/composition";
import { todayLocal } from "../lib/dates";
import { accountValueText, latestUsdRate, useDisplayCurrency } from "../lib/displayCurrency";
import {
  type AccountBalance,
  groupByPerson,
  householdTotalCents,
  totalsByKind,
} from "../lib/grouping";
import { useT } from "../lib/i18n";
import { formatMoney, formatShare, toCents } from "../lib/money";
import { buildNetWorthSeries, monthDelta } from "../lib/netWorthSeries";
import { PYODIDE } from "../pyodide/flag";

export function AccountsView() {
  const t = useT();
  const households = useHouseholds();
  const people = usePeople();
  const accounts = useAccounts();
  const pricePoints = usePricePoints();
  const refresh = useRefreshPrices();
  const [editing, setEditing] = useState<{ account: Account | null } | null>(null);
  const [pricing, setPricing] = useState<Account | null>(null);
  const { pref } = useDisplayCurrency();
  const usdRate = useMemo(() => latestUsdRate(pricePoints.data ?? []), [pricePoints.data]);
  const display = (cents: number): string => accountValueText(cents, pref, usdRate, null);

  const household = households.data?.[0];

  // Each account's latest price point, in full — EUR cents for `display()`/totals,
  // and native currency/fx/price for quote mode, which needs one row's
  // value in its own currency rather than the household-wide EUR figure.
  const latestByAccount = useMemo(() => {
    const map = new Map<
      number,
      { date: string; valueCents: number; priceNative: string; currency: Currency; fxRate: number }
    >();
    for (const p of pricePoints.data ?? []) {
      const existing = map.get(p.account_id);
      if (!existing || p.date > existing.date) {
        map.set(p.account_id, {
          date: p.date,
          valueCents: toCents(p.value_eur),
          priceNative: p.price_native,
          currency: p.currency,
          fxRate: Number(p.fx_rate_to_eur),
        });
      }
    }
    return map;
  }, [pricePoints.data]);

  const householdAccounts = useMemo(
    () => (accounts.data ?? []).filter((a) => a.household_id === household?.id),
    [accounts.data, household],
  );

  const householdAccountIds = useMemo(
    () => new Set(householdAccounts.map((a) => a.id)),
    [householdAccounts],
  );

  const balances: AccountBalance[] = useMemo(
    () =>
      householdAccounts.map((a) => ({
        id: a.id,
        name: a.name,
        kind: a.kind,
        ownerPersonId: a.owner_person_id,
        cents: latestByAccount.get(a.id)?.valueCents ?? toCents(a.manual_value ?? "0.00"),
      })),
    [householdAccounts, latestByAccount],
  );

  const personNames = useMemo(
    () => new Map((people.data ?? []).map((p) => [p.id, p.name] as const)),
    [people.data],
  );

  // The table renders `AccountBalance` rows; the currency cell needs the whole account
  // back, because PUT /api/accounts/{id} replaces every field.
  const accountsById = useMemo(
    () => new Map(householdAccounts.map((a) => [a.id, a] as const)),
    [householdAccounts],
  );

  const groups = useMemo(() => groupByPerson(balances, personNames), [balances, personNames]);
  const kindTotals = useMemo(() => totalsByKind(balances), [balances]);
  const total = householdTotalCents(balances);

  const today = todayLocal();
  const freshest = (pricePoints.data ?? []).reduce<string | null>(
    (max, p) =>
      householdAccountIds.has(p.account_id) && (max === null || p.date > max) ? p.date : max,
    null,
  );

  const series = useMemo(
    () =>
      buildNetWorthSeries(
        householdAccounts.map((a) => ({
          id: a.id,
          fallbackCents: toCents(a.manual_value ?? "0.00"),
        })),
        (pricePoints.data ?? []).map((p) => ({
          accountId: p.account_id,
          date: p.date,
          valueCents: toCents(p.value_eur),
        })),
      ),
    [householdAccounts, pricePoints.data],
  );
  const delta = useMemo(() => monthDelta(series, today), [series, today]);

  if (households.isLoading || accounts.isLoading) {
    return <p className="p-8">{t("today.loading")}</p>;
  }

  if (!household) {
    return (
      <div className="space-y-3 p-8">
        <h1 className="font-display text-2xl">{t("today.accounts")}</h1>
        <p className="max-w-prose text-ink-navy/70 dark:text-paper/70">{t("empty.noHousehold")}</p>
        <Button
          type="button"
          onClick={() => {
            window.location.hash = "#settings";
          }}
        >
          {t("empty.noHousehold.cta")}
        </Button>
        <p className="max-w-prose text-xs text-ink-navy/70 dark:text-paper/50">
          {t("empty.tomlNote")}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8 p-4 sm:p-8">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="font-display text-2xl">{t("today.accounts")}</h1>
        <Button type="button" onClick={() => setEditing({ account: null })} variant="emphasis">
          {t("today.addAccount")}
        </Button>
      </div>

      <GettingStarted onAddAccount={() => setEditing({ account: null })} />

      <section aria-labelledby="today-stats-heading">
        <h2 id="today-stats-heading" className="sr-only">
          {t("today.overview")}
        </h2>
        {/* One column below sm: a real household's net worth ("€ 1.172.061,33") clipped
            its neighbour at text-3xl in a half-width 320px column. */}
        <dl className="grid gap-4 sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-navy/70 dark:text-paper/60">
              {t("today.netWorth")}
            </dt>
            <dd className="font-display text-3xl tabular-nums">{display(total)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink-navy/70 dark:text-paper/60">
              {t("today.monthDelta")}
            </dt>
            <dd
              className={`font-display text-3xl tabular-nums ${
                delta == null ? "" : delta >= 0 ? "text-sea-green" : "text-brick"
              }`}
            >
              {delta == null ? "—" : `${delta >= 0 ? "+" : ""}${display(delta)}`}
            </dd>
          </div>
          {/* The browser build cannot fetch prices (CORS), so it gets the muted line below
              instead of a stat whose only control is a disabled button. */}
          {!PYODIDE && (
            <div>
              <dt className="text-xs uppercase tracking-wide text-ink-navy/70 dark:text-paper/60">
                {t("today.freshness")}
              </dt>
              <dd className="text-sm">
                <span className="tabular-nums">{freshest ?? t("today.noPricesYet")}</span>
                <Button
                  type="button"
                  onClick={() => refresh.mutate(household.id)}
                  disabled={refresh.isPending}
                  variant="emphasis"
                  className="ml-3"
                >
                  {refresh.isPending ? t("today.refreshing") : t("today.refresh")}
                </Button>
              </dd>
            </div>
          )}
        </dl>
        {PYODIDE && (
          <p className="mt-2 text-xs text-ink-navy/70 dark:text-paper/60">
            {t("demo.prices").replaceAll("{date}", freshest ?? t("today.noPricesYet"))}
          </p>
        )}

        {refresh.isError && (
          <p role="alert" className="mt-2 text-sm text-brick">
            {t("today.refreshFailed")} {(refresh.error as Error).message}
          </p>
        )}
        {refresh.data && (
          <ul className="mt-2 space-y-1 text-sm">
            {refresh.data.map((outcome) => (
              <li key={outcome.account_id}>
                <span className={outcome.ok ? "text-sea-green" : "text-brick"} aria-hidden="true">
                  {outcome.ok ? "✓" : "✗"}
                </span>{" "}
                <span className="font-medium">{outcome.account_name}</span>:{" "}
                {outcome.ok ? formatMoney(outcome.value_eur ?? "0.00") : outcome.error}
              </li>
            ))}
          </ul>
        )}
      </section>

      <CompositionBar kindTotals={kindTotals} />

      <section aria-labelledby="breakdown-heading">
        <h2
          id="breakdown-heading"
          className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
        >
          {t("today.byKind")}
        </h2>
        <dl className="mt-2 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {KIND_ORDER.filter((kind) => kindTotals[kind]).map((kind) => (
            <div key={kind} className="border-t border-ink-navy/10 pt-2 dark:border-paper/10">
              <dt className="flex items-center gap-2 text-sm">
                <span
                  aria-hidden="true"
                  className="inline-block size-2.5 rounded-sm"
                  style={{ backgroundColor: KIND_COLORS[kind] ?? SERIES.neutral }}
                />
                {t(`today.kind.${kind}`)}
              </dt>
              <dd className="font-medium tabular-nums">{display(kindTotals[kind])}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="net-worth-heading">
        <h2
          id="net-worth-heading"
          className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
        >
          {t("today.history")}
        </h2>
        {series.length > 0 ? (
          <NetWorthChart series={series} />
        ) : (
          <p className="mt-2 text-sm text-ink-navy/70 dark:text-paper/60">{t("today.noHistory")}</p>
        )}
      </section>

      {groups.map((group) => {
        const groupKey = group.personId ?? "household";
        return (
          <section key={groupKey} aria-labelledby={`group-${groupKey}`}>
            <div className="flex items-baseline justify-between">
              <h2 id={`group-${groupKey}`} className="font-display text-lg">
                {group.personName}
              </h2>
              <p className="text-sm tabular-nums">
                {display(group.totalCents)} · {formatShare(group.totalCents, total)}
              </p>
            </div>
            <DataTable
              className="mt-2"
              caption={group.personName}
              rows={group.accounts}
              rowKey={(account) => String(account.id)}
              columns={[
                {
                  header: t("today.table.account"),
                  title: true,
                  cell: (account) => {
                    const row = accountsById.get(account.id);
                    return (
                      <>
                        {account.name}
                        {row?.kind === "pension" && row.liquid_from && (
                          <span
                            className="ml-2 text-xs text-ink-navy/70 dark:text-paper/60"
                            title={t("today.lockedUntil")}
                          >
                            <Lock aria-hidden="true" className="inline size-3 align-[-1px]" />
                            <span className="sr-only">{t("today.lockedUntil")}</span>{" "}
                            <span className="tabular-nums">{row.liquid_from}</span>
                          </span>
                        )}
                      </>
                    );
                  },
                },
                {
                  header: t("today.table.kind"),
                  cell: (account) => t(`today.kind.${account.kind as AccountKind}`),
                },
                {
                  header: t("today.table.quotedIn"),
                  cell: (account) => accountsById.get(account.id)?.currency,
                },
                {
                  header: t("today.table.value"),
                  numeric: true,
                  cell: (account) => {
                    const point = latestByAccount.get(account.id);
                    return accountValueText(
                      account.cents,
                      pref,
                      usdRate,
                      point ? { currency: point.currency, fxRate: point.fxRate } : null,
                    );
                  },
                },
                {
                  header: t("today.table.share"),
                  numeric: true,
                  cell: (account) => formatShare(account.cents, total),
                },
                {
                  header: t("today.table.updated"),
                  numeric: true,
                  cell: (account) =>
                    latestByAccount.get(account.id)?.date ?? t("today.manualEntry"),
                },
                {
                  header: t("today.actions"),
                  headerHidden: true,
                  full: true,
                  numeric: true,
                  cell: (account) => {
                    const row = accountsById.get(account.id);
                    if (!row) return null;
                    return (
                      // -my-2 keeps the 44px touch height from stretching the desktop row.
                      <div className="-my-2 flex gap-1 sm:justify-end">
                        <Button
                          type="button"
                          onClick={() => setEditing({ account: row })}
                          aria-label={`${t("today.edit")}: ${account.name}`}
                          variant="link"
                        >
                          {t("today.edit")}
                        </Button>
                        <Button
                          type="button"
                          onClick={() => setPricing(row)}
                          aria-label={`${t("today.recordPrice")}: ${account.name}`}
                          variant="link"
                        >
                          {t("today.recordPrice")}
                        </Button>
                      </div>
                    );
                  },
                },
              ]}
            />
          </section>
        );
      })}

      {pref === "quote" && (
        <p className="text-xs text-ink-navy/70 dark:text-paper/60">{t("today.quoteTotalsNote")}</p>
      )}

      {editing && (
        <AccountDrawer
          key={editing.account?.id ?? "new"}
          open
          onOpenChange={(o) => {
            if (!o) setEditing(null);
          }}
          account={editing.account}
          householdId={household.id}
          taxCountry={household.tax_country}
          people={people.data ?? []}
        />
      )}

      {pricing && (
        <PriceDrawer
          key={pricing.id}
          open
          onOpenChange={(o) => {
            if (!o) setPricing(null);
          }}
          account={pricing}
        />
      )}
    </div>
  );
}
