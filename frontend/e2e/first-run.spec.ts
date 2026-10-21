import { expect, test } from "@playwright/test";

test.use({ baseURL: "http://127.0.0.1:8124" });

test("first run: create household, person, account and flow through the UI", async ({
  page,
  request,
}) => {
  const households = await (await request.get("/api/households")).json();
  test.skip(
    households.length > 0,
    "server already onboarded (local rerun) - restart it to re-test",
  );

  // Today shows the empty state and routes to Settings
  await page.goto("/#today");
  await page.getByRole("button", { name: "Create household" }).click();
  await expect(page).toHaveURL(/#settings/);

  // create the household
  await page.getByLabel("Name", { exact: true }).fill("Testhuis");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("heading", { name: "People" })).toBeVisible();

  // add a person
  await page.getByRole("button", { name: "+ person" }).click();
  const personDrawer = page.getByRole("dialog");
  await personDrawer.getByLabel("Name").fill("Alex");
  await personDrawer.getByLabel("Birth date").fill("1990-01-01");
  await personDrawer.getByRole("button", { name: "Save", exact: true }).click();
  await expect(personDrawer).not.toBeVisible();

  // add an account from Today (getting-started card is visible there)
  await page.goto("/#today");
  await expect(page.getByRole("heading", { name: "Getting started" })).toBeVisible();
  await page.getByRole("button", { name: "+ account" }).click();
  const accountDrawer = page.getByRole("dialog");
  await accountDrawer.getByLabel("Name").fill("Spaarrekening");
  // A new account has no default treatment: Save stays blocked until one is picked.
  await accountDrawer.getByLabel("Tax treatment").selectOption("nl.box3_bank");
  await accountDrawer.getByLabel("Current value (EUR)").fill("25000.00");
  await accountDrawer.getByRole("button", { name: "Save", exact: true }).click();
  await expect(accountDrawer).not.toBeVisible();
  // Net-worth stat now reflects the one account just created.
  await expect(page.locator("dd.text-3xl").first()).toHaveText(/25\.000/);

  // add a cash flow — an expense, since the FIRE number derives from expenses
  // (monthly_expenses * 12 / swr) and an income-only household would headline €0.
  await page.goto("/#flows");
  // Two matches while the table is empty: the header button and the empty-row's
  // own copy of the same action — either is fine, they share one click handler.
  await page.getByRole("button", { name: "+ cash flow" }).first().click();
  const flowDrawer = page.getByRole("dialog");
  await flowDrawer.getByLabel("Label").fill("Groceries");
  await flowDrawer.getByLabel("Kind").selectOption("expense");
  await flowDrawer.getByLabel("Amount per month (EUR)").fill("1500.00");
  await flowDrawer.getByRole("button", { name: "Save", exact: true }).click();
  await expect(flowDrawer).not.toBeVisible();

  // the plan canvas now has a non-zero FIRE number headline
  await page.goto("/#plan");
  await expect(page.locator("dd.text-2xl").first()).toHaveText(/[1-9]/, { timeout: 20_000 });
});
