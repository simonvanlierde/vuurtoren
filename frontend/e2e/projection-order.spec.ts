import { expect, test } from "@playwright/test";

test("Composition shows the baseline before starting its Monte Carlo simulation", async ({
  page,
}) => {
  const requests: number[] = [];
  let releaseBaseline!: () => void;
  let releaseBands!: () => void;
  const baseline = new Promise<void>((resolve) => {
    releaseBaseline = resolve;
  });
  const bands = new Promise<void>((resolve) => {
    releaseBands = resolve;
  });
  await page.route("**/api/project", async (route) => {
    const runs = (route.request().postDataJSON().n_runs as number | undefined) ?? 1;
    requests.push(runs);
    await (runs === 1 ? baseline : bands);
    await route.continue();
  });

  try {
    await page.goto("/#plan");
    await expect(page.getByText("Running projection…", { exact: true })).toBeVisible();
    await expect.poll(() => requests).toEqual([1]);

    releaseBaseline();
    const chart = page.getByRole("group", { name: /^Net worth from/ });
    await expect(chart).toBeVisible();
    await expect.poll(() => requests).toEqual([1, 750]);
    await expect(chart).not.toHaveAccessibleName(/Monte Carlo median/);

    releaseBands();
    await expect(chart).toHaveAccessibleName(/Monte Carlo median/, { timeout: 20_000 });
  } finally {
    releaseBaseline();
    releaseBands();
  }
});

test("an assumption edit waits for its own baseline before refreshing sensitivity", async ({
  page,
}) => {
  const editedRequests: string[] = [];
  let releaseBaseline!: () => void;
  const baseline = new Promise<void>((resolve) => {
    releaseBaseline = resolve;
  });
  await page.route(/\/api\/(project|sensitivity)$/, async (route) => {
    const body = route.request().postDataJSON();
    if (body.assumptions?.inflation === 0.035) {
      const kind = new URL(route.request().url()).pathname.split("/").at(-1);
      const name = kind === "sensitivity" ? "sensitivity" : body.n_runs ? "bands" : "baseline";
      editedRequests.push(name);
      if (name === "baseline") await baseline;
    }
    await route.continue();
  });

  try {
    await page.goto("/#plan");
    const firstSensitivity = page.waitForResponse("**/api/sensitivity");
    await page.getByRole("tab", { name: "Sensitivity" }).click();
    expect((await firstSensitivity).ok()).toBe(true);

    await page.getByRole("textbox", { name: "Inflation" }).fill("3.5");
    await expect.poll(() => editedRequests).toEqual(["baseline"]);

    releaseBaseline();
    await expect
      .poll(() => [...editedRequests].sort())
      .toEqual(["bands", "baseline", "sensitivity"]);
  } finally {
    releaseBaseline();
  }
});
