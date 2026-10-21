/** What the model does not cover, on the surface where its answer is read.
 *
 * Principle 2 was met everywhere except here. Each regime's module docstring has always
 * listed its simplifications and which way each one bends the answer, but that list was
 * only ever readable by someone editing the module — while the person who most needs it
 * is the one looking at an FI date and deciding what to do about it.
 *
 * Collapsed by default. This is a caveat, not the headline: it has to be *findable*
 * without leaving Plan, which is the defect, and it does not have to be loud.
 */
import { useMeta } from "../../lib/api";
import { useLocale, useT } from "../../lib/i18n";

export function ModelLimits() {
  const t = useT();
  const [locale] = useLocale();
  const meta = useMeta();
  const limits = meta.data?.limitations ?? [];
  if (limits.length === 0) return null;

  return (
    <details className="max-w-prose">
      <summary className="flex min-h-11 cursor-pointer items-center text-sm text-ink-navy/70 sm:min-h-0 dark:text-paper/70">
        {t("plan.limits.summary")
          .replace("{count}", String(limits.length))
          .replace("{country}", meta.data?.tax_country ?? "")}
      </summary>
      <ul className="mt-2 space-y-2 border-t border-ink-navy/10 pt-2 text-sm dark:border-paper/10">
        {limits.map((lim) => (
          <li key={lim.en} className="flex flex-col gap-0.5">
            {/* The direction is the load-bearing half. "Not modelled" alone leaves a
                reader unable to tell whether the omission is in their favour. */}
            <span className="text-xs uppercase tracking-wide text-ink-navy/70 dark:text-paper/50">
              {t(`plan.limits.${lim.direction}` as const)}
            </span>
            <span className="text-ink-navy/70 dark:text-paper/70">
              {locale === "nl" ? lim.nl : lim.en}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}
