/** "Deel deze weergave": copies a link whose
 * hash carries the assumption knobs. A shared link carries the numbers in it, so the
 * warning is always visible — not a quiet Copy button. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useT } from "../../lib/i18n";
import type { usePlanState } from "../../lib/usePlanState";

export function ShareButton({ plan }: { plan: ReturnType<typeof usePlanState> }) {
  const t = useT();
  const [copied, setCopied] = useState(false);

  const onShare = async () => {
    try {
      await navigator.clipboard.writeText(plan.shareUrl());
      setCopied(true);
    } catch {
      // Clipboard blocked (insecure context / denied) — leave the button un-ticked
      // rather than claiming a copy that didn't happen.
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <Button type="button" onClick={onShare} variant="outline">
        {t("plan.share.button")}
      </Button>
      <span className="text-ink-navy/70 dark:text-paper/60">
        {copied ? t("plan.share.copied") : t("plan.share.warning")}
      </span>
    </div>
  );
}
