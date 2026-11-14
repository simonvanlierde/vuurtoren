import { expect, test } from "@playwright/test";

// The gate names exactly what the boot fetches: the Pyodide runtime from jsDelivr.
// Everything else, the engine's wheels included, is served by the site itself.
test("the boot fetches only from this site and cdn.jsdelivr.net", async ({ page, baseURL }) => {
  test.setTimeout(180_000);
  const hosts = new Set<string>();
  // BrowserContext includes package downloads made by the worker.
  page.context().on("request", (r) => {
    const url = new URL(r.url());
    if (url.protocol.startsWith("http")) hosts.add(url.host);
  });
  await page.goto("/");
  await page.getByRole("button", { name: /start the demo/i }).click();
  await expect(page.getByText(/\d+ tax figures with source/i).first()).toBeVisible({
    timeout: 150_000,
  });
  expect([...hosts].sort()).toEqual([new URL(baseURL ?? "").host, "cdn.jsdelivr.net"].sort());
});

test("the site lockfile matches every staged wheel and its pinned version", async ({ request }) => {
  const { createHash } = await import("node:crypto");
  const pins = (await import("../src/pyodide/wheels.json", { with: { type: "json" } })).default;
  const manifest = await (await request.get("/pyodide/manifest.json")).json();
  const lockfile = await (await request.get("/pyodide/pyodide-lock.json")).json();
  for (const name of manifest.packages) {
    const pkg = lockfile.packages[name];
    const wheel = await request.get(`/pyodide/${pkg.file_name}`);
    expect(wheel.ok()).toBe(true);
    expect(
      createHash("sha256")
        .update(await wheel.body())
        .digest("hex"),
    ).toBe(pkg.sha256);
    if (name in pins.pypi) {
      expect(pkg.version).toBe(pins.pypi[name as keyof typeof pins.pypi]);
    }
  }
});
