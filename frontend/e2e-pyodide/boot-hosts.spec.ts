import { expect, test } from "@playwright/test";

// The gate names exactly what the boot fetches: the Pyodide runtime from jsDelivr.
// Everything else, the engine's wheels included, is served by the site itself.
test("the boot fetches only from this site and cdn.jsdelivr.net", async ({ page, baseURL }) => {
  test.setTimeout(180_000);
  const hosts = new Set<string>();
  // Worker requests reach the page's context too, so this sees micropip's fetches.
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
