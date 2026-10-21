/** Allocation comparison: 80/20 against 60/40, as scenarios.
 *
 * Every piece of machinery already existed — the `accounts` scenario override group went
 * live for the sensitivity tornado — so this is the UI half and nothing else. Each split
 * restates today's equity and bond balances at that ratio, holding the invested total
 * fixed, and the Scenarios overlay does the comparing. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAccounts } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { type AllocationAccount, allocationScenarios } from "../../lib/scenarioCompare";

/** The splits worth putting side by side. More than four scenarios stops being a
 * comparison and starts being a table, and the overlay caps at four anyway. */
const SPLITS = [100, 80, 60, 40] as const;

const LABEL_CLS = "text-ink-navy/70 dark:text-paper/60 block text-xs tracking-wide uppercase";

export function AllocationForm({
  householdId,
  existingNames,
  onCreate,
  pending,
}: {
  householdId: number;
  existingNames: Set<string>;
  onCreate: (payloads: ReturnType<typeof allocationScenarios>) => void;
  pending: boolean;
}) {
  const t = useT();
  const accountsQuery = useAccounts();
  const [chosen, setChosen] = useState<number[]>([80, 60]);

  const investable: AllocationAccount[] = (accountsQuery.data ?? [])
    .filter((a) => a.kind === "equity" || a.kind === "bond")
    .map((a) => ({
      id: a.id,
      kind: a.kind as "equity" | "bond",
      value: Number(a.manual_value ?? 0),
    }));

  const hasBoth =
    investable.some((a) => a.kind === "equity") && investable.some((a) => a.kind === "bond");

  // Without a bond account there is nowhere for the non-equity share to sit, and
  // inventing one would answer a different question than the user asked.
  if (!accountsQuery.isLoading && !hasBoth) {
    return (
      <p className="text-ink-navy/70 dark:text-paper/60 mt-3 text-sm">
        {t("plan.scenarios.allocation.needsBoth")}
      </p>
    );
  }

  const equityNow = investable
    .filter((a) => a.kind === "equity")
    .reduce((sum, a) => sum + a.value, 0);
  const total = investable.reduce((sum, a) => sum + a.value, 0);
  const currentPct = total > 0 ? Math.round((equityNow / total) * 100) : 0;

  function submit() {
    const payloads = allocationScenarios({
      householdId,
      accounts: investable,
      splits: [...chosen].sort((a, b) => b - a),
    });
    onCreate(payloads.filter((p) => !existingNames.has(p.name)));
  }

  return (
    <div className="mt-3 flex flex-wrap items-end gap-4">
      <fieldset>
        <legend className={LABEL_CLS}>{t("plan.scenarios.allocation.splitsLabel")}</legend>
        <div className="mt-1 flex flex-wrap items-center gap-4 text-sm">
          {SPLITS.map((pct) => (
            <label key={pct} className="flex items-center gap-1 py-2">
              <input
                type="checkbox"
                checked={chosen.includes(pct)}
                onChange={(e) =>
                  setChosen((prev) =>
                    e.target.checked ? [...prev, pct] : prev.filter((p) => p !== pct),
                  )
                }
              />{" "}
              {pct}/{100 - pct}
            </label>
          ))}
        </div>
      </fieldset>

      <Button
        type="button"
        onClick={submit}
        disabled={pending || chosen.length === 0}
        variant="emphasis"
      >
        {t("plan.scenarios.allocation.addButton")}
      </Button>

      <p className="text-ink-navy/70 dark:text-paper/50 w-full max-w-prose text-xs">
        {t("plan.scenarios.allocation.hint").replace(
          "{current}",
          `${currentPct}/${100 - currentPct}`,
        )}
      </p>
    </div>
  );
}
