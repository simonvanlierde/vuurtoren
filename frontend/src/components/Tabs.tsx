import { type MsgKey, useT } from "../lib/i18n";

const TABS: { id: string; label: MsgKey }[] = [
  { id: "today", label: "nav.today" },
  { id: "plan", label: "nav.plan" },
  { id: "flows", label: "nav.flows" },
  { id: "settings", label: "nav.settings" },
];

/** The four surfaces, twice over: a top bar from `sm` up, a fixed bottom bar on a phone.
 *
 * Same four destinations in the same order — this is one information architecture shown
 * where the hand is. At the top of a phone the strip sat at the far end from the thumb,
 * and its 38px targets were under the 44px floor. The bottom bar is the platform
 * convention users already expect, and it clears the home indicator via
 * `env(safe-area-inset-bottom)`. Below `sm` the labels drop to `text-xs` with 4px side
 * padding: "Instellingen" at `text-sm` all but fills the 80px cell a 320px phone gives it. */
// NOTE: a raw <button>, deliberately, while the rest of the app moved to `Button`. This
// is an underline tab strip — the active state is a bottom border and a text weight, not
// one of the four button weights — and dressing it as a `Button` variant would mean a
// fifth variant used exactly once.
export function Tabs({ active, onSelect }: { active: string; onSelect: (id: string) => void }) {
  const t = useT();

  const label = (tab: (typeof TABS)[number], isActive: boolean) => (
    <button
      type="button"
      aria-current={isActive ? "page" : undefined}
      onClick={() => onSelect(tab.id)}
      className={`flex min-h-11 w-full items-center justify-center border-b-2 px-1 text-xs sm:px-3 sm:text-sm font-medium transition-colors sm:w-auto ${
        isActive
          ? "border-ring text-ink-navy dark:text-paper"
          : "text-ink-navy/70 dark:text-paper/60 hover:text-ink-navy dark:hover:text-paper border-transparent"
      }`}
    >
      {t(tab.label)}
    </button>
  );

  return (
    <>
      <nav
        aria-label={t("nav.aria")}
        className="border-ink-navy/10 dark:border-paper/10 hidden border-b sm:block"
      >
        <ul className="flex flex-wrap gap-1 px-4">
          {TABS.map((tab) => (
            <li key={tab.id} className={tab.id === "settings" ? "ml-auto" : undefined}>
              {label(tab, tab.id === active)}
            </li>
          ))}
        </ul>
      </nav>

      <nav
        aria-label={t("nav.aria")}
        className="border-ink-navy/10 bg-paper dark:border-paper/10 dark:bg-night-sea fixed inset-x-0 bottom-0 z-40 border-t pb-[env(safe-area-inset-bottom)] sm:hidden"
      >
        <ul className="grid grid-cols-4">
          {TABS.map((tab) => (
            <li key={tab.id}>{label(tab, tab.id === active)}</li>
          ))}
        </ul>
      </nav>
    </>
  );
}
