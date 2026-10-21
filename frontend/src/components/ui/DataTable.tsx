/** One data set, two honest renderings: a real `<table>` from `sm` up, a stack of
 * cards below it.
 *
 * The tempting alternative — one table reflowed to `display: block` with CSS and
 * `data-label` pseudo-element captions — was rejected: `display: block` strips a
 * table's implicit ARIA semantics, and `::before` content is not reliably announced,
 * so the phone reading would have lost its column names entirely. Two renderings cost
 * a hidden subtree (row counts here are household-sized) and keep both correct.
 *
 * Why at all: `w-full` inside `overflow-x-auto` shrinks columns to fit rather than
 * scrolling, so at 320px seven columns collided into "€ 50.000,0066,7%".
 */
import type { ReactNode } from "react";

export interface DataColumn<T> {
  /** Table header, and the label beside the value on a card. */
  header: string;
  cell: (row: T) => ReactNode;
  /** Right-align the column, and the card's value slot — money and percentages. */
  numeric?: boolean;
  /** Card only: the card's title line, rendered without a label. At most one. */
  title?: boolean;
  /** Card only: full width with no label, below the pairs — the row's actions. */
  full?: boolean;
  /** Header text is for screen readers only (an actions column). */
  headerHidden?: boolean;
}

interface DataTableProps<T> {
  columns: readonly DataColumn<T>[];
  rows: readonly T[];
  rowKey: (row: T) => string;
  /** Names the table for screen readers; visually hidden. */
  caption: string;
  className?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  className,
}: DataTableProps<T>): ReactNode {
  const titleColumn = columns.find((c) => c.title);
  const pairColumns = columns.filter((c) => !c.title && !c.full);
  const fullColumns = columns.filter((c) => !c.title && c.full);

  return (
    <>
      <div className={`hidden overflow-x-auto sm:block ${className ?? ""}`}>
        <table className="w-full text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b border-ink-navy/10 text-left dark:border-paper/10">
              {columns.map((column) => (
                <th
                  key={column.header}
                  scope="col"
                  className={`py-1 font-medium ${column.numeric ? "text-right" : ""}`}
                >
                  {column.headerHidden ? (
                    <span className="sr-only">{column.header}</span>
                  ) : (
                    column.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={rowKey(row)} className="border-b border-ink-navy/5 dark:border-paper/5">
                {columns.map((column) => (
                  <td
                    key={column.header}
                    className={`py-1 ${column.numeric ? "text-right tabular-nums" : ""}`}
                  >
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className={`space-y-2 sm:hidden ${className ?? ""}`}>
        {rows.map((row) => (
          <li
            key={rowKey(row)}
            className="rounded-lg border border-ink-navy/10 p-3 dark:border-paper/10"
          >
            {titleColumn && <p className="font-medium">{titleColumn.cell(row)}</p>}
            <dl className={titleColumn ? "mt-2 space-y-1" : "space-y-1"}>
              {pairColumns.map((column) => (
                <div key={column.header} className="flex items-baseline justify-between gap-3">
                  <dt className="shrink-0 text-sm text-ink-navy/70 dark:text-paper/60">
                    {column.header}
                  </dt>
                  <dd className={`text-sm ${column.numeric ? "tabular-nums" : ""} text-right`}>
                    {column.cell(row)}
                  </dd>
                </div>
              ))}
            </dl>
            {fullColumns.map((column) => (
              <div key={column.header} className="mt-2">
                {column.cell(row)}
              </div>
            ))}
          </li>
        ))}
      </ul>
    </>
  );
}
