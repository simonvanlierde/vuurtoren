import { expect, test } from "@playwright/test";

// A move to Austria leaves every Dutch-tagged account with a key Austria does not know,
// and the engine refuses such a move. The drawer has to collect the new treatment for
// each one, or a Move abroad made in the editor can never project.
test("a move abroad retags the accounts and the plan still projects", async ({ page, request }) => {
  await page.goto("/#plan");
  await page.getByRole("tab", { name: "Milestones" }).click();
  await page.getByRole("button", { name: "+ milestone" }).click();
  const drawer = page.getByRole("dialog");
  const label = `Move to Vienna ${Date.now()}`;
  await drawer.getByLabel("Label").fill(label);
  await drawer.getByRole("button", { name: "Move abroad" }).click();
  await drawer.getByLabel("Date", { exact: true }).fill("2030-01-01");
  await drawer.getByLabel("Country").selectOption("AT");

  // Read from the API rather than hard-coded: the smoke spec shares this database and
  // renames an account.
  const austrian: Record<string, string> = {
    "nl.box3_bank": "AT · bank savings",
    "nl.box3_investment": "AT · investments",
    "nl.box1_pension": "AT · pension",
  };
  const accounts = (await (await request.get("/api/accounts")).json()) as {
    name: string;
    tax_treatment: string;
  }[];
  expect(accounts.length).toBeGreaterThan(0);
  for (const account of accounts) {
    const select = drawer.getByLabel(account.name, { exact: true });
    // Each one is required: its Dutch key means nothing in Austria.
    await expect(select).toHaveAttribute("required", "");
    await select.selectOption({ label: austrian[account.tax_treatment] });
  }

  const projected = page.waitForResponse(
    (r) => r.url().endsWith("/api/project") && r.request().method() === "POST",
  );
  await drawer.getByRole("button", { name: "Save", exact: true }).click();
  await expect(drawer).not.toBeVisible();
  expect((await projected).status()).toBe(200);
  await expect(page.getByRole("button", { name: new RegExp(`^${label}`) })).toBeVisible();
  await expect(page.locator("dd.text-2xl").first()).toHaveText(/[1-9]/, { timeout: 20_000 });

  // The other specs share this database; leave it as the seed made it.
  const stored = (await (await request.get("/api/milestones")).json()) as {
    id: number;
    label: string;
  }[];
  const mine = stored.find((m) => m.label === label);
  expect(mine).toBeDefined();
  expect((await request.delete(`/api/milestones/${mine?.id}`)).status()).toBe(204);
});
