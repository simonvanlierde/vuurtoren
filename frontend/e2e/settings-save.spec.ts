import { expect, test } from "@playwright/test";

// Restore the shared example household after each check.
test("household save feedback survives the saved household refetch", async ({ page, request }) => {
  const [household] = await (await request.get("/api/households")).json();
  try {
    await page.goto("/#settings");
    await page.getByLabel("Name", { exact: true }).fill("Saved household");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText("Saved ✓", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Name", { exact: true })).toHaveValue("Saved household");
  } finally {
    await request.put(`/api/households/${household.id}`, { data: household });
  }
});

test("household status stays quiet until a save, and a blank age cannot be saved", async ({
  page,
}) => {
  await page.goto("/#settings");
  await expect(page.getByRole("status")).toHaveText("");
  await page.getByLabel("Plan until age", { exact: true }).fill("");
  await expect(page.getByText("Unsaved changes", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
});

test("editing during a household save keeps the newer unsaved draft", async ({ page, request }) => {
  const [household] = await (await request.get("/api/households")).json();
  let release = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let received = () => {};
  const requested = new Promise<void>((resolve) => {
    received = resolve;
  });
  await page.route("**/api/households/*", async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    const response = await route.fetch();
    received();
    await held;
    await route.fulfill({ response });
  });
  try {
    await page.goto("/#settings");
    const name = page.getByLabel("Name", { exact: true });
    const save = page.getByRole("button", { name: "Save", exact: true });
    await name.fill("Submitted household");
    await save.click();
    await requested;
    await expect(page.getByRole("status")).toHaveText("Saving…");
    await name.fill("Newer unsaved household");
    release();
    await expect(save).toBeEnabled();
    await expect(name).toHaveValue("Newer unsaved household");
    await expect(page.getByText("Unsaved changes", { exact: true })).toBeVisible();
    await expect(page.getByText("Saved ✓", { exact: true })).not.toBeVisible();
    expect((await (await request.get("/api/households")).json())[0].name).toBe(
      "Submitted household",
    );
    await save.click();
    await expect(page.getByRole("status")).toHaveText("Saved ✓");
    expect((await (await request.get("/api/households")).json())[0].name).toBe(
      "Newer unsaved household",
    );
  } finally {
    release();
    await request.put(`/api/households/${household.id}`, { data: household });
  }
});

test("display preferences save immediately across reloads", async ({ page }) => {
  await page.goto("/#settings");
  await expect(
    page.getByText("Language, theme and display currency save immediately on this device."),
  ).toBeVisible();
  await page.getByLabel("Theme", { exact: true }).selectOption("dark");
  await page.getByLabel("Display currency", { exact: true }).selectOption("quote");
  await page.getByLabel("Language", { exact: true }).selectOption("nl");
  await page.reload();
  await expect(page.getByLabel("Taal", { exact: true })).toHaveValue("nl");
  await expect(page.getByLabel("Thema", { exact: true })).toHaveValue("dark");
  await expect(page.locator("#settings-currency")).toHaveValue("quote");
});

test("tax editor explains the selected year and keeps edits in that year", async ({ page }) => {
  await page.goto("/#plan");
  await page.getByRole("tab", { name: "Tax figures", exact: true }).click();
  await page.getByLabel("Year", { exact: true }).fill("2030");
  await expect(page.getByText("Edits apply only to 2030.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Override Tarief,", exact: false }).first().click();
  await page.getByRole("textbox", { name: "Tarief", exact: true }).fill("0.40");
  await page.getByLabel("Year", { exact: true }).fill("2031");
  await expect(page.getByText("Edits apply only to 2031.", { exact: false })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Tarief", exact: true })).not.toBeVisible();
  await page.getByLabel("Year", { exact: true }).fill("2030");
  await expect(page.getByRole("textbox", { name: "Tarief", exact: true })).toHaveValue("0.40");
  const editedRate = page.getByRole("row").filter({
    has: page.getByRole("textbox", { name: "Tarief", exact: true }),
  });
  // An edit keeps the figure's source year; it does not relabel it with the edited year.
  await expect(editedRate.getByText("source year 2030", { exact: true })).not.toBeVisible();
});

test("tax money labels keep the source year through an edit", async ({ page }) => {
  await page.goto("/#plan");
  await page.getByRole("tab", { name: "Tax figures", exact: true }).click();
  await page.getByLabel("Year", { exact: true }).fill("2027");
  const allowance = page.getByRole("row").filter({
    has: page.getByText("Heffingsvrij vermogen (per person)", { exact: true }),
  });
  await expect(allowance.getByText("amount in 2026 prices", { exact: true })).toBeVisible();
  await expect(page.getByText("amount in 2027 prices", { exact: true }).first()).toBeVisible();
  await allowance.getByRole("button", { name: /^Override / }).click();
  await allowance.getByRole("textbox").fill("60000");
  // The edited amount is in the same 2026 prices as the figure it replaces.
  await expect(allowance.getByText("amount in 2026 prices", { exact: true })).toBeVisible();
  await expect(allowance.getByText("amount in 2027 prices", { exact: true })).not.toBeVisible();
  await allowance.getByRole("button", { name: /^Reset / }).click();
  await expect(allowance.getByText("amount in 2026 prices", { exact: true })).toBeVisible();
});
