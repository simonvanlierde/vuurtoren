/** The shared deck below every lens's chart: the read-only panels — tax, milestones,
 * plus whatever lens-specific tabs (`extra`) the calling lens wants shown first. The
 * live assumptions are NOT here; they sit in the rail beside the chart they drive. */
import type { ReactNode } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePeople } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { usePlanState } from "../../lib/usePlanState";
import { MilestoneChips } from "./MilestoneChips";
import { TaxPanel } from "./TaxPanel";
import { UsReportingPanel } from "./UsReportingPanel";

export function Deck({
  extra,
  plan,
}: {
  extra?: { value: string; label: string; content: ReactNode }[];
  plan: ReturnType<typeof usePlanState>;
}) {
  const t = useT();
  const people = usePeople();
  // Only for a household that has one. FBAR and Form 8938 are US filing obligations, and
  // a tab about them in a Dutch household's deck would read as a fifth kind of Dutch tax.
  const usReporting = (people.data ?? []).some((p) => p.us_person);
  const tabs = extra ?? [];
  const defaultValue = tabs[0]?.value ?? "tax";

  return (
    <Tabs defaultValue={defaultValue}>
      {/* Up to six tabs — scroll horizontally rather than overflow the page below sm.
          `shrink-0` on the triggers is what makes that real: the primitive's `flex-1`
          squeezed them instead, so at 320px the last tab was clipped mid-word and the
          strip never scrolled. The 44px touch height now comes from the primitive. */}
      <TabsList
        variant="line"
        className="scroll-x-hint max-w-full justify-start overflow-x-auto [&>*]:shrink-0"
      >
        {tabs.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value}>
            {tab.label}
          </TabsTrigger>
        ))}
        <TabsTrigger value="tax">{t("plan.deck.tax")}</TabsTrigger>
        <TabsTrigger value="milestones">{t("plan.deck.milestones")}</TabsTrigger>
        {usReporting && (
          <TabsTrigger value="us-reporting">{t("plan.deck.usReporting")}</TabsTrigger>
        )}
      </TabsList>
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
