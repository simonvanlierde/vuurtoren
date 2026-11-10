/** Create, update and delete for one editor drawer: picks update when a record is being
 * edited, and surfaces whichever mutation failed last as a field-error map. */
import type { UseMutationResult } from "@tanstack/react-query";
import { NO_ERRORS, parseApiError } from "../../lib/fieldErrors";

export interface CrudApi<TIn, TOut> {
  useCreate(): UseMutationResult<TOut, Error, TIn>;
  useUpdate(): UseMutationResult<TOut, Error, { id: number; body: TIn }>;
  useDelete(): UseMutationResult<void, Error, number>;
}

export function useRecordEditor<TIn, TOut>(api: CrudApi<TIn, TOut>, record: { id: number } | null) {
  const create = api.useCreate();
  const update = api.useUpdate();
  const remove = api.useDelete();
  const active = record ? update : create;
  const errors = active.isError
    ? parseApiError(active.error)
    : remove.isError
      ? parseApiError(remove.error)
      : NO_ERRORS;
  return {
    errors,
    saving: active.isPending,
    creating: create.isPending,
    save: (body: TIn, onSuccess: () => void) =>
      record
        ? update.mutate({ id: record.id, body }, { onSuccess })
        : create.mutate(body, { onSuccess }),
    /** Callers offer delete only for an existing record. */
    remove: (onSuccess: () => void) => {
      if (record) remove.mutate(record.id, { onSuccess });
    },
  };
}
