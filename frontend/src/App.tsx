import { lazy, Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import markMarkup from "./assets/vuurtoren.svg?raw";
import { Tabs } from "./components/Tabs";
import { useMeta } from "./lib/api";
import { useT } from "./lib/i18n";
import { useHash } from "./lib/useHash";
import { PYODIDE } from "./pyodide/flag";

// One chunk per surface. The app shipped as a single 947 kB bundle, so Settings — which
// draws no charts at all — was downloading Recharts to render three selects. A route
// switch here is the natural split point: `useHash` already renders exactly one of these.
//
// AccountsView is in the list for the same reason as the rest even though the plan named
// only the lenses and Flows: it pulls `NetWorthChart`, so leaving it eager would have kept
// Recharts in the entry chunk and left the stated defect standing.
const AccountsView = lazy(() =>
  import("./views/AccountsView").then((m) => ({ default: m.AccountsView })),
);
const CashFlowView = lazy(() =>
  import("./views/CashFlowView").then((m) => ({ default: m.CashFlowView })),
);
const PlanView = lazy(() => import("./views/PlanView").then((m) => ({ default: m.PlanView })));
const SettingsView = lazy(() =>
  import("./views/SettingsView").then((m) => ({ default: m.SettingsView })),
);

// The asset pins a fixed `color` attribute for standalone use; strip it here so the
// inlined mark's currentColor follows the header text colour (ink navy / paper) instead.
const mark = markMarkup.replace(/ color="[^"]*"/, "").replace(/<title>.*?<\/title>/, "");

export function App() {
  const [view, navigate] = useHash();
  const t = useT();
  const meta = useMeta();
  const [dismissed, setDismissed] = useState(false);
  // Two separate claims that happen to share a strip, and both can be true at once.
  //
  // Whose numbers these are was gated on PYODIDE, so a visitor to a hosted *server* build
  // landed on #plan and read a stranger's € 75.000 with nothing saying it was not theirs.
  // The server answers that from the data now. The privacy line is a different statement
  // — it is only true of the browser build — and stays on the flag.
  const exampleData = meta.data?.example_data === true;
  const showBanner = exampleData || PYODIDE;

  const viewTitle = t(
    view === "plan"
      ? "nav.plan"
      : view === "flows"
        ? "nav.flows"
        : view === "settings"
          ? "nav.settings"
          : "nav.today",
  );
  useEffect(() => {
    // The view in the tab title, so history and a row of tabs stay legible.
    document.title = `${viewTitle} — vuurtoren`;
  }, [viewTitle]);

  // relative + overflow-x-clip on the root: sr-only captions inside the scrollable tables
  // are absolutely positioned and, with no positioned ancestor, escape into document space
  // and widen the page at 320px. `relative` makes the root their containing block so the
  // clip actually catches them; the body then never scrolls horizontally, while wide tables
  // still scroll inside their own overflow-x-auto boxes. clip (not hidden) creates no scroll
  // container, so it can't break sticky/portal positioning.
  return (
    <div className="relative min-h-screen overflow-x-clip">
      <header className="flex items-center gap-2 px-4 pt-6">
        <span
          aria-hidden="true"
          className="inline-block size-6 [&>svg]:h-full [&>svg]:w-full"
          // biome-ignore lint/security/noDangerouslySetInnerHtml: static bundled SVG asset, not user input — inlining keeps currentColor working
          dangerouslySetInnerHTML={{ __html: mark }}
        />
        <p className="font-display text-lg font-bold tracking-tight">vuurtoren</p>
      </header>
      {!dismissed && showBanner && (
        <div className="mx-4 mt-2 flex items-center justify-between gap-3 rounded bg-ink-navy/5 px-3 py-2 text-sm dark:bg-paper/10">
          <span>
            {exampleData && (
              <>
                {t("demo.exampleData")}{" "}
                {/* Lands on the Start-empty button itself, not just the Settings page. */}
                <a href="#settings/start-empty" className="underline underline-offset-4">
                  {t("demo.exampleData.replace")}
                </a>{" "}
              </>
            )}
            {PYODIDE && `${t("demo.banner")} ${t("demo.banner.reload")}`}
          </span>
          <Button
            type="button"
            onClick={() => setDismissed(true)}
            variant="link"
            className="shrink-0"
          >
            {t("demo.banner.dismiss")}
          </Button>
        </div>
      )}
      <Tabs active={view} onSelect={navigate} />
      {/* Clears the fixed bottom nav on a phone; from `sm` up the nav is back on top. */}
      {/* tabIndex -1: the browser build's gate moves focus here once the engine is ready,
          so a keyboard user starts at the content instead of the top of the page. */}
      <main
        tabIndex={-1}
        className="pb-[calc(3.5rem+env(safe-area-inset-bottom))] outline-none sm:pb-0"
      >
        {/* A bare <p>, not a skeleton: the chunk is a local fetch and the fallback is
            visible for a frame or two. A shimmer here would be motion for its own sake. */}
        <Suspense
          fallback={
            <p className="p-8 text-sm text-ink-navy/70 dark:text-paper/60">{t("app.loading")}</p>
          }
        >
          {view === "plan" ? (
            <PlanView />
          ) : view === "flows" ? (
            <CashFlowView />
          ) : view === "settings" ? (
            <SettingsView />
          ) : (
            <AccountsView />
          )}
        </Suspense>
      </main>
    </div>
  );
}
