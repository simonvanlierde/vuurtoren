/** Native form fields for the editor drawer: label + input + error slot
 * with role="alert". Money and unit counts stay Decimal strings in text inputs —
 * never a number input's float round-trip. */
import type * as React from "react";
import { type ReactNode, useId, useState } from "react";
import { useT } from "../../lib/i18n";
import { isDecimalString } from "../../lib/money";
import { Input } from "../ui/input";

// The 44px touch floor lives on the `Input` primitive. `<select>` has no primitive and
// keeps this class, matched to `Input`'s so the two line up in a drawer.
const SELECT =
  "h-8 min-h-11 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base sm:min-h-0 md:text-sm";

/** Wires an input to the message under it. Without this the error text is on screen and
 * nowhere else: a screen reader announces the field as valid and never reads the reason
 * the save bounced. Hint and error share one slot, so they share one id. */
function described(id: string, error?: string, hint?: string) {
  if (error) return { "aria-invalid": true, "aria-describedby": `${id}-msg` } as const;
  if (hint) return { "aria-describedby": `${id}-msg` } as const;
  return {};
}

function Shell({
  htmlFor,
  label,
  error,
  hint,
  required,
  children,
}: {
  htmlFor: string;
  label: string;
  error?: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
}) {
  const t = useT();
  return (
    <div className="space-y-1">
      {/* Marked before submit, not discovered by it. The marker sits OUTSIDE the label and is aria-hidden — the input's own `required` announces it,
          and any text inside the label becomes part of how the field is looked up. */}
      <div className="flex items-baseline gap-1">
        <label htmlFor={htmlFor} className="text-sm font-medium">
          {label}
        </label>
        {required && (
          <span aria-hidden="true" className="text-ink-navy/70 dark:text-paper/60 text-xs">
            {t("editor.required")}
          </span>
        )}
      </div>
      {children}
      {hint && !error && (
        <p id={`${htmlFor}-msg`} className="text-xs text-ink-navy/70 dark:text-paper/60">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${htmlFor}-msg`} role="alert" className="text-sm text-brick">
          {error}
        </p>
      )}
    </div>
  );
}

interface BaseProps {
  label: string;
  error?: string;
  hint?: string;
  required?: boolean;
  autoFocus?: boolean;
}

export function TextField({
  value,
  onChange,
  placeholder,
  ...p
}: BaseProps & { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const id = useId();
  return (
    <Shell htmlFor={id} label={p.label} error={p.error} hint={p.hint} required={p.required}>
      <Input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={p.required}
        autoFocus={p.autoFocus}
        {...described(id, p.error, p.hint)}
      />
    </Shell>
  );
}

/** A Decimal-string input for money, unit counts and exact rates. Blur runs the
 * shape check only; the server's 422 remains the source of truth. */
export function DecimalField({
  value,
  onChange,
  ...p
}: BaseProps & { value: string; onChange: (v: string) => void }) {
  const t = useT();
  const id = useId();
  const [shapeError, setShapeError] = useState<string | null>(null);
  return (
    <Shell
      htmlFor={id}
      label={p.label}
      error={p.error ?? shapeError ?? undefined}
      hint={p.hint}
      required={p.required}
    >
      <Input
        id={id}
        type="text"
        inputMode="decimal"
        value={value}
        autoFocus={p.autoFocus}
        onChange={(e) => {
          onChange(e.target.value);
          setShapeError(null);
        }}
        onBlur={() =>
          setShapeError(value !== "" && !isDecimalString(value) ? t("editor.decimalShape") : null)
        }
        required={p.required}
        className="tabular-nums"
        {...described(id, p.error ?? shapeError ?? undefined, p.hint)}
      />
    </Shell>
  );
}

export function DateField({
  value,
  onChange,
  ...p
}: BaseProps & { value: string; onChange: (v: string) => void }) {
  const id = useId();
  return (
    <Shell htmlFor={id} label={p.label} error={p.error} hint={p.hint} required={p.required}>
      <Input
        id={id}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={p.required}
        autoFocus={p.autoFocus}
        {...described(id, p.error, p.hint)}
      />
    </Shell>
  );
}

/** Ints and rate-percentages only — never money (float round-trip). */
export function NumberField({
  value,
  onChange,
  step,
  ...p
}: BaseProps & { value: string; onChange: (v: string) => void; step?: string }) {
  const id = useId();
  return (
    <Shell htmlFor={id} label={p.label} error={p.error} hint={p.hint} required={p.required}>
      <Input
        id={id}
        type="number"
        value={value}
        step={step}
        onChange={(e) => onChange(e.target.value)}
        required={p.required}
        autoFocus={p.autoFocus}
        className="tabular-nums"
        {...described(id, p.error, p.hint)}
      />
    </Shell>
  );
}

/** A bare native `<select>`, styled to match `Input`. For a control that carries its own
 * label and needs no Shell — the settings page's language, theme and currency pickers.
 *
 * One select primitive in the app, and it is this one: native, because the platform
 * gives keyboard behaviour, screen-reader semantics and a phone's picker for free.
 */
export function NativeSelect({
  className,
  ...props
}: React.ComponentProps<"select"> & { className?: string }) {
  return <select {...props} className={`${SELECT} ${className ?? ""}`} />;
}

export function SelectField({
  value,
  onChange,
  options,
  emptyLabel,
  ...p
}: BaseProps & {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  emptyLabel?: string;
}) {
  const id = useId();
  return (
    <Shell htmlFor={id} label={p.label} error={p.error} hint={p.hint} required={p.required}>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={p.required}
        // biome-ignore lint/a11y/noAutofocus: the first drawer field autofocuses
        autoFocus={p.autoFocus}
        className={SELECT}
        {...described(id, p.error, p.hint)}
      >
        {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Shell>
  );
}

export function CheckboxField({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      {/* The label is the 44px row and wraps the box, so the whole strip toggles while
          the box keeps its 20px visual weight (WCAG 2.5.8). min-h-11 on a plain div
          left only the 20px text line clickable. */}
      <label htmlFor={id} className="flex min-h-11 w-fit items-center gap-2 text-sm font-medium">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="size-5 accent-ink-navy dark:accent-paper"
        />
        {label}
      </label>
      {hint && <p className="text-xs text-ink-navy/70 dark:text-paper/60">{hint}</p>}
    </div>
  );
}
