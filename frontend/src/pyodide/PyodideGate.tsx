import { type ReactNode, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { type MsgKey, useT } from "../lib/i18n";
import { PYODIDE } from "./flag";

type Phase = "idle" | "loading" | "ready" | "error";

/** Browser build only: names the product and gates the app behind a "start the demo"
 * click that lazy-boots the Pyodide worker (tens of MB), showing progress. The server
 * build (PYODIDE=false) renders children straight through. Hooks run unconditionally, before any branch. */
export function PyodideGate({ children }: { children: ReactNode }) {
  const t = useT();
  const [phase, setPhase] = useState<Phase>("idle");
  const [stage, setStage] = useState<string>("runtime");

  // The start button unmounts with the gate, so hand focus to the app's content rather
  // than letting it fall back to <body> (WCAG 2.4.3).
  useEffect(() => {
    if (PYODIDE && phase === "ready") document.querySelector<HTMLElement>("main")?.focus();
  }, [phase]);

  if (!PYODIDE || phase === "ready") return <>{children}</>;

  async function start() {
    if (phase === "loading") return;
    setPhase("loading");
    try {
      // Dynamic, like api.ts's import: a static one here kept the worker in its own
      // chunk's graph and shipped it with the server build.
      const { bootWorker } = await import("./client");
      await bootWorker((s) => (s === "error" ? setPhase("error") : setStage(s)));
      // Land a first visit on the plan, the demo's point; a deep link keeps its view.
      // Set before App mounts, which reads the hash once; replace, so Back leaves the site.
      if (!location.hash) history.replaceState(null, "", "#plan");
      setPhase("ready");
    } catch {
      setPhase("error");
    }
  }

  const loadingKey = `demo.gate.loading.${stage}` as MsgKey;
  const loading = phase === "loading";
  return (
    <div aria-busy={loading} className="mx-auto max-w-prose px-4 py-16 text-center">
      <h1 className="font-display text-2xl font-bold">{t("demo.gate.title")}</h1>
      <p className="mt-4 text-lg">{t("demo.gate.lede")}</p>
      <p className="mt-4 text-ink-navy/70 dark:text-paper/70">{t("demo.gate.body")}</p>
      {phase === "error" ? (
        <div className="mt-8 space-y-3">
          <p role="alert" className="text-brick">
            {t("demo.gate.error")}
          </p>
          <Button type="button" onClick={start} variant="emphasis">
            {t("demo.gate.retry")}
          </Button>
        </div>
      ) : (
        // Stays mounted while loading, aria-disabled rather than disabled, so a keyboard
        // user's focus stays on it instead of dropping to <body> (WCAG 2.4.3).
        <Button
          type="button"
          onClick={start}
          variant="emphasis"
          aria-disabled={loading}
          className="mt-8 aria-disabled:opacity-50"
        >
          {t("demo.gate.start")}
        </Button>
      )}
      {/* Mounted before it has anything to say, so the first stage is announced too. */}
      <p role="status" className="mt-4 min-h-5 text-sm">
        {loading && (
          <span className="animate-pulse motion-reduce:animate-none">{t(loadingKey)}</span>
        )}
      </p>
    </div>
  );
}
