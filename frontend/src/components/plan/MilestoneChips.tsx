/** Milestone chips for the deck's Milestones tab: clicking one opens the editor
 * drawer for that milestone; the trailing chip opens it for a new one. */

import { Button } from "@/components/ui/button";
import { useMilestones, usePeople } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { milestoneDate } from "../../lib/timeline";
import type { usePlanState } from "../../lib/usePlanState";

export function MilestoneChips({ plan }: { plan: ReturnType<typeof usePlanState> }) {
  const t = useT();
  const milestones = useMilestones();
  const people = usePeople();

  const birthByPerson = new Map((people.data ?? []).map((p) => [p.id, p.birth_date] as const));

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {(milestones.data ?? []).map((m) => {
          const date = milestoneDate(m, birthByPerson);
          const year = date ? date.slice(0, 4) : null;
          return (
            <Button
              key={m.id}
              type="button"
              onClick={() => plan.setMilestoneEditor(m.id)}
              variant="outline"
            >
              {m.label || m.params.type}
              {year && (
                <span className="tabular-nums text-ink-navy/70 dark:text-paper/60"> · {year}</span>
              )}
            </Button>
          );
        })}
        <Button
          type="button"
          onClick={() => plan.setMilestoneEditor("new")}
          variant="ghost"
          className="rounded border border-dashed border-ink-navy/40 px-2 py-1 text-sm dark:border-paper/40"
        >
          {t("plan.milestones.add")}
        </Button>
      </div>
    </div>
  );
}
