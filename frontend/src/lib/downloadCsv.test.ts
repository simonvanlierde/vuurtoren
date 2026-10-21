import { describe, expect, it } from "vitest";
import { type CsvColumn, toCsv } from "./downloadCsv";

describe("toCsv", () => {
  it("writes a header row then one row per index", () => {
    const columns: CsvColumn[] = [
      { header: "month", values: ["2026-01", "2026-02"] },
      { header: "net worth", values: [1000, 2000] },
    ];
    expect(toCsv(columns)).toBe("month,net worth\r\n2026-01,1000\r\n2026-02,2000");
  });

  it("quotes fields containing a comma or quote and doubles embedded quotes", () => {
    const columns: CsvColumn[] = [{ header: 'a,b"c', values: ['x"y'] }];
    expect(toCsv(columns)).toBe('"a,b""c"\r\n"x""y"');
  });

  it("pads a short column with blanks rather than dropping the row", () => {
    const columns: CsvColumn[] = [
      { header: "m", values: ["a", "b"] },
      { header: "v", values: [1] },
    ];
    expect(toCsv(columns)).toBe("m,v\r\na,1\r\nb,");
  });
});
