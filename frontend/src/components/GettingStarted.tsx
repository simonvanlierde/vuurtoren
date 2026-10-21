/** The dismissible getting-started card: four steps that check themselves
 * off as data appears. Never blocks anything; a TOML-seeded database has all four
 * steps complete on first render, so it only ever shows the finished state — and
 * we hide it entirely then. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAccounts, useCashFlows, useHouseholds, usePeople } from "../lib/api";
import { useT } from "../lib/i18n";
import { readStored, writeStored } from "../lib/storage";

const DISMISS_KEY = "vuurtoren-getting-started-dismissed";

export function GettingStarted({ onAddAccount }: { onAddAccount: () => void }) {
  const t = useT();
  const [dismissed, setDismissed] = useState(() => readStored(DISMISS_KEY) === "1");
  const households = useHouseholds();
  const people = usePeople();
  const accounts = useAccounts();
  const cashFlows = useCashFlows();

  if (dismissed) return null;
  // Wait for data: a flash of "0 of 4" on a seeded DB would be noise.
  if (!households.data || !people.data || !accounts.data || !cashFlows.data) return null;

  const steps = [
    {
      key: "household",
      done: households.data.length > 0,
      label: t("start.household"),
      action: () => {
        window.location.hash = "#settings";
      },
    },
    {
      key: "people",
      done: people.data.length > 0,
      label: t("start.people"),
      action: () => {
        window.location.hash = "#settings";
      },
    },
    {
      key: "accounts",
      done: accounts.data.length > 0,
      label: t("start.accounts"),
      action: onAddAccount,
    },
    {
      key: "flows",
      done: cashFlows.data.length > 0,
      label: t("start.flows"),
      action: () => {
        window.location.hash = "#flows";
      },
    },
  ];
  if (steps.every((s) => s.done)) return null;

  // Steps are sequential: everything after the first undone step needs its
  // predecessors (an account needs a household), so only the first undone one
  // gets an active button.
  const firstUndone = steps.findIndex((s) => !s.done);

  return (
    <section
      aria-labelledby="getting-started-heading"
      className="rounded border border-ink-navy/15 p-4 dark:border-paper/15"
    >
      <div className="flex items-baseline justify-between">
        <h2 id="getting-started-heading" className="font-display text-lg">
          {t("start.title")}
        </h2>
        <Button
          type="button"
          onClick={() => {
            writeStored(DISMISS_KEY, "1");
            setDismissed(true);
          }}
          variant="link"
          className="text-foreground/60"
        >
          {t("start.dismiss")}
        </Button>
      </div>
      <ol className="mt-3 space-y-2">
        {steps.map((step, i) => (
          <li key={step.key} className="flex items-center gap-3 text-sm">
            <span
              aria-hidden="true"
              className={step.done ? "text-sea-green" : "text-ink-navy/70 dark:text-paper/40"}
            >
              {step.done ? "✓" : "○"}
            </span>
            <span className={step.done ? "line-through opacity-60" : ""}>
              {step.label}
              {step.done && <span className="sr-only"> {t("start.done")}</span>}
            </span>
            {!step.done && i === firstUndone && (
              <Button type="button" onClick={step.action} variant="outline" size="xs">
                {t("start.go")}
              </Button>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
