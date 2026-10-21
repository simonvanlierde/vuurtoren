/** Markup-level checks on the editor fields: the error text exists, but a screen reader
 * only reaches it if the input points at it. Rendered through `react-dom/server` — no
 * DOM, no component framework; interaction stays with the Playwright specs. */
import { renderToStaticMarkup } from "react-dom/server";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../../lib/i18n";
import { CheckboxField, DecimalField, SelectField, TextField } from "./fields";

// I18nProvider reads both at first render; neither exists in the node environment.
beforeAll(() => {
  vi.stubGlobal("localStorage", { getItem: () => "en", setItem: () => {} });
  vi.stubGlobal("navigator", { language: "en" });
});

const render = (node: React.ReactNode) => renderToStaticMarkup(<I18nProvider>{node}</I18nProvider>);

/** The id the error/hint paragraph carries, so the assertion follows the pointer
 * instead of hard-coding React's generated id. */
function describedBy(html: string): { id: string | null; text: string | null } {
  const control = /<(?:input|select)\b[^>]*aria-describedby="([^"]+)"/.exec(html);
  if (!control) return { id: null, text: null };
  const target = new RegExp(`<p[^>]*id="${control[1]}"[^>]*>([^<]*)</p>`).exec(html);
  return { id: control[1], text: target?.[1] ?? null };
}

describe("field error wiring", () => {
  it("marks an invalid input and points it at its own error text", () => {
    const html = render(
      <TextField label="Name" value="" onChange={() => {}} error="Name is required" />,
    );
    expect(html).toContain('aria-invalid="true"');
    expect(describedBy(html).text).toBe("Name is required");
  });

  it("points at the hint when there is no error", () => {
    const html = render(
      <TextField label="Ticker" value="" onChange={() => {}} hint="Yahoo symbol" />,
    );
    // `aria-invalid:` also appears as a Tailwind variant in the class list, so the
    // negative assertion has to be on the attribute, not the substring.
    expect(html).not.toContain('aria-invalid="true"');
    expect(describedBy(html).text).toBe("Yahoo symbol");
  });

  it("wires a select the same way as an input", () => {
    const html = render(
      <SelectField
        label="Kind"
        value="cash"
        onChange={() => {}}
        options={[{ value: "cash", label: "Cash" }]}
        error="Unknown kind"
      />,
    );
    expect(html).toContain('aria-invalid="true"');
    expect(describedBy(html).text).toBe("Unknown kind");
  });

  it("leaves a valid field unmarked", () => {
    const html = render(<DecimalField label="Value" value="100.00" onChange={() => {}} />);
    expect(html).not.toContain('aria-invalid="true"');
    expect(html).not.toContain("aria-describedby");
  });
});

describe("checkbox target", () => {
  it("makes the 44px row itself the label, so all of it toggles (WCAG 2.5.8)", () => {
    const html = render(<CheckboxField label="Real terms" checked={false} onChange={() => {}} />);
    expect(html).toMatch(
      /<label[^>]*class="[^"]*min-h-11[^"]*"[^>]*>\s*<input[^>]*type="checkbox"/,
    );
  });
});
