/** Parts the five scenario-template forms share: their props, and labelled controls built
 * on the app's own `Input` and `NativeSelect` so they keep the 44px touch floor. */
import type * as React from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type { ScenarioCreate } from "../../lib/api";
import { NativeSelect } from "../editor/fields";

export interface TemplateFormProps {
  householdId: number;
  existingNames: Set<string>;
  onCreate: (payloads: ScenarioCreate[]) => void;
  pending: boolean;
}

export const LABEL_CLS =
  "text-ink-navy/70 dark:text-paper/60 block text-xs tracking-wide uppercase";

export function LabelledInput({
  id,
  label,
  className,
  ...props
}: { id: string; label: string } & React.ComponentProps<"input">) {
  return (
    <div>
      <label htmlFor={id} className={LABEL_CLS}>
        {label}
      </label>
      <Input
        id={id}
        className={cn("mt-1 w-32 tabular-nums", props.type === "month" && "w-auto", className)}
        {...props}
      />
    </div>
  );
}

export function LabelledSelect({
  id,
  label,
  ...props
}: { id: string; label: string } & React.ComponentProps<"select">) {
  return (
    <div>
      <label htmlFor={id} className={LABEL_CLS}>
        {label}
      </label>
      <NativeSelect id={id} className="mt-1 w-auto" {...props} />
    </div>
  );
}
