/** The shared deck below every lens's chart: the read-only panels — tax, milestones,
 * plus whatever lens-specific tabs (`extra`) the calling lens wants shown first. The
 * live assumptions are NOT here; they sit in the rail beside the chart they drive. */
import { type ReactNode, useId, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePeople } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { usePlanState } from "../../lib/usePlanState";
import { MilestoneChips } from "./MilestoneChips";
import { TaxPanel } from "./TaxPanel";
import { UsReportingPanel } from "./UsReportingPanel";

/** "decide": a panel that answers "what if I change something". "evidence": a panel that
 * shows what the plan already says. */
export type DeckGroup = "decide" | "evidence";

export interface DeckTab {
  value: string;
  group: DeckGroup;
  label: string;
  content: ReactNode;
}

export function Deck({
  extra,
  plan,
}: {
  extra?: DeckTab[];
  plan: ReturnType<typeof usePlanState>;
}) {
  const t = useT();
  const id = useId();
  const people = usePeople();
  // Only for a household that has one. FBAR and Form 8938 are US filing obligations, and
  // a tab about them in a Dutch household's deck would read as a fifth kind of Dutch tax.
  const usReporting = (people.data ?? []).some((p) => p.us_person);
  const tabs = extra ?? [];
  const defaultValue = tabs[0]?.value ?? "tax";
  const shared: Omit<DeckTab, "content">[] = [
    { value: "tax", group: "evidence", label: t("plan.deck.tax") },
    { value: "milestones", group: "evidence", label: t("plan.deck.milestones") },
    ...(usReporting
      ? [{ value: "us-reporting", group: "evidence" as const, label: t("plan.deck.usReporting") }]
      : []),
  ];
  const all = [...tabs, ...shared];
  const [selected, setSelected] = useState(defaultValue);
  // The US reporting tab goes away when no person is a US person any more; fall back
  // rather than show a deck with no panel.
  const value = all.some((tab) => tab.value === selected) ? selected : defaultValue;

  return (
    // Manual activation: the deck has two tab lists, and Tab from the first lands on the
    // second's first tab. Automatic activation would switch the panel on that keystroke.
    <Tabs value={value} onValueChange={setSelected} activationMode="manual">
      {/* Two labelled tab lists sharing one set of panels, rather than one list of up to
          eight that scrolled off a phone screen. Each list wraps instead of scrolling, so
          every tab is visible at 320px. A `group` inside one tablist is not allowed by
          ARIA, so the grouping is two tablists, each named by its visible label. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:gap-8">
        {(["decide", "evidence"] as const).map((group) => {
          const inGroup = all.filter((tab) => tab.group === group);
          if (inGroup.length === 0) return null;
          return (
            <div key={group} className="min-w-0">
              <p
                id={`${id}-${group}`}
                className="text-xs tracking-wide text-ink-navy/70 uppercase dark:text-paper/60"
              >
                {t(`plan.deck.group.${group}`)}
              </p>
              <TabsList
                variant="line"
                aria-labelledby={`${id}-${group}`}
                className="flex-wrap justify-start gap-y-2 sm:group-data-horizontal/tabs:h-auto [&>*]:flex-none"
              >
                {inGroup.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value}>
                    {tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <TabsContent key={tab.value} value={tab.value}>
          {tab.content}
        </TabsContent>
      ))}
      <TabsContent value="tax">
        <TaxPanel
          country={plan.household?.tax_country}
          taxYear={plan.taxYear}
          setTaxYear={plan.setTaxYear}
          overrides={plan.overrides}
          editField={plan.editField}
          resetField={plan.resetField}
        />
      </TabsContent>
      <TabsContent value="milestones">
        <MilestoneChips plan={plan} />
      </TabsContent>
      {usReporting && (
        <TabsContent value="us-reporting">
          <UsReportingPanel plan={plan} />
        </TabsContent>
      )}
    </Tabs>
  );
}
