/** Map a failed mutation onto drawer fields: FastAPI 422s carry
 * `detail: [{loc: ["body", ...path], msg}]`; 400/409s carry a string detail. */
import { ApiError } from "./api";

export interface ParsedErrors {
  fields: Record<string, string>;
  general: string | null;
}

export const NO_ERRORS: ParsedErrors = { fields: {}, general: null };

interface ValidationItem {
  loc: (string | number)[];
  msg: string;
}

function isValidationList(detail: unknown): detail is ValidationItem[] {
  return (
    Array.isArray(detail) &&
    detail.every(
      (d) =>
        Array.isArray((d as ValidationItem)?.loc) && typeof (d as ValidationItem)?.msg === "string",
    )
  );
}

export function parseApiError(error: unknown): ParsedErrors {
  if (!(error instanceof ApiError)) {
    return { fields: {}, general: error instanceof Error ? error.message : String(error) };
  }
  if (isValidationList(error.detail) && error.detail.length > 0) {
    const fields: Record<string, string> = {};
    for (const item of error.detail) {
      // strip "body"; keep the dotted path (numeric list indices included, so two
      // list items' errors stay distinct) AND index by the last *named* segment,
      // because a discriminated-union 422 inserts the union tag into the path.
      // The named-segment convenience key keeps the first message on collision.
      const path = item.loc.filter((p) => p !== "body");
      const key = path.map(String).join(".");
      if (key && !(key in fields)) fields[key] = item.msg;
      const last = path.filter((p): p is string => typeof p === "string").at(-1);
      if (last && !(last in fields)) fields[last] = item.msg;
    }
    return { fields, general: null };
  }
  return {
    fields: {},
    general: typeof error.detail === "string" ? error.detail : error.message,
  };
}
