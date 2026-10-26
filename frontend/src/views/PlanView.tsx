/** The Plan canvas: a persistent headline strip, a lens switch, and a
 * shared deck underneath whichever lens is active. */
import { lazy, Suspense, useState } from "react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MilestoneDrawer } from "../components/editor/MilestoneDrawer";
import { AssumptionsRail } from "../components/plan/AssumptionsRail";
import {
  type HeadlineSlot,
  HeadlineStrip,
  UserEditsMarker,
} from "../components/plan/HeadlineStrip";
import { ModelLimits } from "../components/plan/ModelLimits";

// One chunk per lens. Radix unmounts an inactive TabsContent, so a visitor who never
// opens Scenarios never downloads its overlay chart or its template forms.
const OpbouwLens = lazy(() =>
  import("../components/plan/OpbouwLens").then((m) => ({ default: m.OpbouwLens })),
);
const OnzekerheidLens = lazy(() =>
  import("../components/plan/OnzekerheidLens").then((m) => ({ default: m.OnzekerheidLens })),
);
const ScenariosLens = lazy(() =>
  import("../components/plan/ScenariosLens").then((m) => ({ default: m.ScenariosLens })),
);

import { useHouseholds, useMilestones, useProjection, useTaxConfig } from "../lib/api";
import { useT } from "../lib/i18n";
import { hashForLens, lensFromHash, type PlanLens, useRawHash } from "../lib/useHash";
import { usePlanState } from "../lib/usePlanState";

export function PlanView() {
  const t = useT();
  const plan = usePlanState();
  const rawHash = useRawHash();
  const lens = lensFromHash(rawHash);
  const [slot, setSlot] = useState<HeadlineSlot>({ label: t("plan.headline.coast"), value: "—" });
  const baseline = useProjection(plan.deferredRequest);
  const milestones = useMilestones();
  const households = useHouseholds();

  function navigate(next: string) {
    window.location.hash = next;
  }

  if (households.data && households.data.length === 0) {
    return (
      <div className="space-y-3 p-8">
        <h1 className="font-display text-2xl">{t("nav.plan")}</h1>
        <p className="max-w-prose text-ink-navy/70 dark:text-paper/70">{t("empty.plan")}</p>
        <Button
          type="button"
          onClick={() => {
            window.location.hash = "#settings";
          }}
        >
          {t("empty.noHousehold.cta")}
        </Button>
      </div>
    );
  }

  // Inside each TabsContent, not around them: while a lens chunk loads the panel must
  // already exist, or the selected tab's aria-controls points at nothing.
  const lensFallback = (
    <p className="px-4 text-sm text-ink-navy/70 sm:px-8 dark:text-paper/60">{t("app.loading")}</p>
  );

  return (
    <div className="space-y-6 pt-6">
      {/* The headline strip owns the visual title slot, but the document still needs its
          level-1 heading: navigating #plan by heading otherwise started at "Milestone". */}
      <h1 className="sr-only">{t("nav.plan")}</h1>
      <div className="flex items-start justify-between px-4 sm:px-8">
        <HeadlineStrip fire={baseline.data?.fire} slot={slot} />
        <div className="flex items-center gap-3">
          {plan.isCalculating && (
            <span className="animate-pulse text-xs text-ink-navy/70 motion-reduce:animate-none dark:text-paper/50">
              {t("plan.calculating")}
            </span>
          )}
          {plan.hasEdits && <UserEditsMarker />}
        </div>
      </div>
      <ProvenanceStamp country={plan.household?.tax_country} taxYear={plan.taxYear} />
      {/* The rail is a sibling of the whole lens column, not of one chart: it drives every
          lens, and `lg:items-start` is what lets it be sticky (a stretched flex item is
          already full height, so it has nowhere to stick). It comes first in the DOM so
          that below `lg` it lands under the headline as a collapsed strip. */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:gap-6">
        <AssumptionsRail plan={plan} />
        <Tabs
          className="min-w-0 flex-1"
          value={lens}
          onValueChange={(l) => navigate(hashForLens(l as PlanLens))}
        >
          <TabsList variant="line" className="mx-4 sm:mx-8">
            <TabsTrigger value="opbouw">{t("plan.lens.opbouw")}</TabsTrigger>
            <TabsTrigger value="onzekerheid">{t("plan.lens.onzekerheid")}</TabsTrigger>
            <TabsTrigger value="scenarios">{t("plan.lens.scenarios")}</TabsTrigger>
          </TabsList>
          <TabsContent value="opbouw">
            <Suspense fallback={lensFallback}>
              <OpbouwLens plan={plan} setSlot={setSlot} />
            </Suspense>
          </TabsContent>
          <TabsContent value="onzekerheid">
            <Suspense fallback={lensFallback}>
              <OnzekerheidLens plan={plan} setSlot={setSlot} />
            </Suspense>
          </TabsContent>
          <TabsContent value="scenarios">
            <Suspense fallback={lensFallback}>
              <ScenariosLens plan={plan} setSlot={setSlot} />
            </Suspense>
          </TabsContent>
        </Tabs>
      </div>
      <div className="px-4 sm:px-8">
        <ModelLimits />
      </div>
      {plan.milestoneEditor !== null && plan.household && (
        <MilestoneDrawer
          key={plan.milestoneEditor}
          plan={plan}
          milestone={
            plan.milestoneEditor === "new"
              ? null
              : ((milestones.data ?? []).find((m) => m.id === plan.milestoneEditor) ?? null)
          }
        />
      )}
    </div>
  );
}

/** The proof line under the headline: how many tax figures carry a source and when they
 * were last verified. It is the product's strongest claim, and it lived six deck tabs
 * deep; here it sits one line under the number it vouches for. Renders nothing until the
 * config is loaded — a stamp with placeholders would undercut the point. */
function ProvenanceStamp({ country, taxYear }: { country: string | undefined; taxYear: number }) {
  const t = useT();
  const config = useTaxConfig(country, taxYear);
  const fields = config.data ? Object.values(config.data.fields) : [];
  if (fields.length === 0) return null;
  const latest = fields.reduce((max, f) => (f.verified_on > max ? f.verified_on : max), "");
  return (
    <p className="px-4 text-xs text-ink-navy/70 sm:px-8 dark:text-paper/60">
      {t("plan.provenance").replaceAll("{n}", String(fields.length)).replaceAll("{d}", latest)}
    </p>
  );
}
