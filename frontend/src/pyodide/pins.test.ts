/** The browser build installs wheels.json: uv.lock's pure-Python wheels, served from the
 * site, plus the compiled packages this Pyodide release bundles. These checks fail when
 * uv.lock moves and the pins do not, or when a dependency arrives that neither source
 * covers, which micropip would otherwise fetch from PyPI at boot. */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import pyodideLock from "../../node_modules/pyodide/pyodide-lock.json";
import pins from "./wheels.json";

const uvLock = readFileSync(new URL("../../../uv.lock", import.meta.url), "utf8");
const blocks = new Map(
  uvLock
    .split("\n[[package]]\n")
    .slice(1)
    .map((b) => [/^name = "([^"]+)"/.exec(b)?.[1] ?? "", b]),
);
const lockVersion = (name: string) => /^version = "([^"]+)"/m.exec(blocks.get(name) ?? "")?.[1];
const lockDeps = (name: string): string[] => {
  const deps = /^dependencies = \[\n([\s\S]*?)\n\]/m.exec(blocks.get(name) ?? "")?.[1] ?? "";
  return (
    [...deps.matchAll(/\{ name = "([^"]+)"(?:, marker = "([^"]+)")?/g)]
      // A `python_full_version < 'X.Y'` marker holds only if X.Y is past this Pyodide's
      // Python 3.14. Any other marker is kept, which errs toward checking too much.
      .filter((m) => {
        const below = /python_full_version < '(\d+)\.(\d+)'/.exec(m[2] ?? "");
        return !below || Number(below[1]) * 100 + Number(below[2]) > 314;
      })
      .map((m) => m[1])
  );
};
const bundled = pyodideLock.packages as Record<string, { version: string }>;

describe("browser build wheels", () => {
  it.each(Object.entries(pins.pypi))("pins %s to the uv.lock version", (name, version) => {
    expect(version).toBe(lockVersion(name));
  });

  it.each(pins.pyodide)("takes %s from this Pyodide release", (name) => {
    expect(bundled[name]).toBeDefined();
  });

  it("covers every runtime dependency, so nothing comes from PyPI", () => {
    // uvicorn and alembic are server-only; the wheel installs with deps=False.
    const seen = new Set<string>();
    const queue = lockDeps("vuurtoren").filter((n) => n !== "uvicorn" && n !== "alembic");
    while (queue.length > 0) {
      const name = queue.shift() as string;
      if (seen.has(name)) continue;
      seen.add(name);
      if (name in pins.pypi) queue.push(...lockDeps(name));
    }
    const uncovered = [...seen].filter((n) => !(n in pins.pypi) && !(n in bundled));
    expect(uncovered).toEqual([]);
  });

  it("leaves no version pin in the worker", () => {
    const worker = readFileSync(new URL("./worker.ts", import.meta.url), "utf8");
    expect(worker).not.toMatch(/"[a-z-]+==[\d.]+"/);
  });
});
