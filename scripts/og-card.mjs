// Rebuild the social card: read the example household's Plan series from the running
// app, write them into docs/og-card.html, and render frontend/public/og.png (1200 x 630).
// Run through `just og-card`, which builds the frontend and serves the example
// household on http://127.0.0.1:8123 (override with VUURTOREN_URL).
import { readFileSync, writeFileSync } from "node:fs";
import { chromium } from "../frontend/node_modules/@playwright/test/index.mjs";

const url = process.env.VUURTOREN_URL ?? "http://127.0.0.1:8123";
const card = new URL("../docs/og-card.html", import.meta.url);
const png = new URL("../frontend/public/og.png", import.meta.url);
const index = new URL("../frontend/index.html", import.meta.url);
const MONTHS = 340; // a little past what the 1200 px card shows

const browser = await chromium.launch();
try {
  for (let t = 0; ; t++) {
    try {
      if ((await fetch(`${url}/api/households`)).ok) break;
    } catch {}
    if (t > 60) throw new Error(`no app at ${url}`);
    await new Promise((r) => setTimeout(r, 1000));
  }

  // The Plan view posts the fixed-return projection and the Monte Carlo run itself.
  const page = await browser.newPage({ locale: "en-US", viewport: { width: 1280, height: 920 } });
  const bodies = [];
  page.on("response", (r) => {
    if (r.url().endsWith("/api/project") && r.request().method() === "POST") bodies.push(r.json());
  });
  await page.goto(`${url}/#plan`);
  await page.getByRole("tab", { name: "Composition" }).waitFor();
  await page.waitForFunction(() => document.body.innerText.includes("FI date"));
  await page.waitForTimeout(4000);
  const runs = await Promise.all(bodies);
  const fixed = runs.find((b) => b.net_worth);
  const mc = runs.find((b) => b.bands);
  if (!fixed || !mc) throw new Error("Plan did not post both projections");

  const fi = fixed.fire.fi_dates[0];
  const shown = await page.locator("main").innerText();
  const label = new Date(`${fi}T00:00:00Z`).toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
  if (!shown.includes(label)) throw new Error(`app shows a different FI date than ${label}`);
  if (!readFileSync(index, "utf8").includes(label)) throw new Error(`og:image:alt in frontend/index.html must say ${label}`);

  const cut = (a) => a.slice(0, MONTHS).map(Math.round);
  const data = { fi, m: fixed.months.slice(0, MONTHS), nw: cut(fixed.net_worth[0]), p10: cut(mc.bands.p10), p50: cut(mc.bands.p50), p90: cut(mc.bands.p90) };
  const html = readFileSync(card, "utf8").replace(/(<script id="plan" type="application\/json">)[\s\S]*?(<\/script>)/, `$1${JSON.stringify(data)}$2`);
  writeFileSync(card, html);

  const shot = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  await shot.goto(card.href);
  await shot.evaluate(() => document.fonts.ready);
  await shot.screenshot({ path: png.pathname });
  console.log(`og.png: FI date ${label}`);
} finally {
  await browser.close();
}
