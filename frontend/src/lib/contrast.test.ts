/** WCAG 1.4.11 on the two non-text strokes every form leans on: an input's border and
 * the focus ring. Read from the source, because a token edit is where these regress. */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("../index.css", import.meta.url), "utf8");

function hex(name: string): number[] {
  const m = new RegExp(`--color-${name}:\\s*#([0-9a-f]{6})`).exec(css);
  if (!m) throw new Error(`--color-${name} not found`);
  return [0, 2, 4].map((i) => Number.parseInt(m[1].slice(i, i + 2), 16));
}

function luminance(rgb: number[]): number {
  const [r, g, b] = rgb.map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: number[], b: number[]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** `color-mix(in srgb, fg p%, transparent)` composited over `bg`. */
const over = (fg: number[], pct: number, bg: number[]) =>
  fg.map((c, i) => c * (pct / 100) + bg[i] * (1 - pct / 100));

/** The `--input: color-mix(...)` percentages, light theme first, then `.dark`. */
const inputMixes = [
  ...css.matchAll(/--input:\s*color-mix\(in srgb, var\(--color-([\w-]+)\) (\d+)%/g),
].map((m) => ({
  color: m[1],
  pct: Number(m[2]),
}));

describe("input stroke", () => {
  it("is declared for both themes", () => {
    expect(inputMixes.map((m) => m.color)).toEqual(["ink-navy", "paper"]);
  });

  it("clears 3:1 against the page and card in both themes", () => {
    const [light, dark] = inputMixes;
    for (const bg of [hex("paper"), [255, 255, 255]]) {
      expect(contrast(over(hex(light.color), light.pct, bg), bg)).toBeGreaterThanOrEqual(3);
    }
    for (const bg of [hex("night-sea"), hex("ink-navy")]) {
      expect(contrast(over(hex(dark.color), dark.pct, bg), bg)).toBeGreaterThanOrEqual(3);
    }
  });
});

describe("focus ring", () => {
  // A ring at 50% composites the deep amber down to 1.7:1 on paper; opaque it is 3.1:1.
  it.each([
    "../components/ui/button.tsx",
    "../components/ui/input.tsx",
    "../components/ui/tabs.tsx",
    "../components/editor/fields.tsx",
  ])("is opaque in %s", (path) => {
    const source = readFileSync(new URL(path, import.meta.url), "utf8");
    expect(source).not.toMatch(/focus-visible:ring-(ring|destructive)\/\d+/);
  });

  it("clears 3:1 on paper in the light theme", () => {
    expect(contrast(hex("beacon-amber-deep"), hex("paper"))).toBeGreaterThanOrEqual(3);
  });
});
