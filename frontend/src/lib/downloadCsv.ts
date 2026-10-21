/** Client-side CSV download of chart series already loaded in the browser — no server
 * round-trip. The FIRE audience lives in
 * spreadsheets; "download this chart's data" is the difference between trusting the
 * numbers and retyping them. */

export interface CsvColumn {
  header: string;
  values: readonly (string | number)[];
}

/** RFC-4180-ish: quote a field only when it holds a comma, quote or newline, doubling
 * any embedded quote. Rows are as long as the first column (all series share a month
 * axis), so a short column pads with blanks rather than dropping the row. */
export function toCsv(columns: readonly CsvColumn[]): string {
  const escapeField = (v: string | number): string => {
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rowCount = columns[0]?.values.length ?? 0;
  const lines = [columns.map((c) => escapeField(c.header)).join(",")];
  for (let i = 0; i < rowCount; i++) {
    lines.push(columns.map((c) => escapeField(c.values[i] ?? "")).join(","));
  }
  return lines.join("\r\n");
}

export function downloadCsv(filename: string, columns: readonly CsvColumn[]): void {
  const blob = new Blob([toCsv(columns)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
