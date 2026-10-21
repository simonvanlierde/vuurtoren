/** "This figure is yours, not the Belastingdienst's."
 *
 * One badge, three call sites: the Plan headline's edits marker, the scenario picker's
 * per-column marker, and the tax panel's "edited" status. All three were the same
 * twenty-token class string typed out separately, and they were the only place in the
 * app still reaching for a raw Tailwind `blue-*` instead of a token.
 */
export function EditedBadge({ children }: { children: string }) {
  return (
    <span
      className="rounded border px-1.5 py-0.5 text-xs font-medium"
      style={{
        borderColor: "var(--vt-marker-user)",
        color: "var(--vt-marker-user)",
        backgroundColor: "color-mix(in srgb, var(--vt-marker-user) 15%, transparent)",
      }}
    >
      {children}
    </span>
  );
}
