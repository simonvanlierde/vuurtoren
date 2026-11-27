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

for (const trigger of ["cached inflation", "refocus", "milestone save"] as const) {
  test(`automatic analyses wait for a refreshed baseline on ${trigger}`, async ({
    page,
    request: api,
  }) => {
    const responses: number[] = [];
    const refreshOrder: string[] = [];
    let refreshing = false;
    let releaseBaseline!: () => void;
    const heldBaseline = new Promise<void>((resolve) => {
      releaseBaseline = resolve;
    });

    await page.route(/\/api\/(project|sensitivity)$/, async (route) => {
      const request = route.request();
      const body = request.postDataJSON();
      const sensitivity = request.url().endsWith("/sensitivity");
      const kind = sensitivity ? "sensitivity" : body.n_runs ? "bands" : "baseline";
      if (refreshing) {
        refreshOrder.push(kind);
        if (kind === "baseline") await heldBaseline;
      }
      await route.continue();
    });
    page.on("response", (response) => {
      const request = response.request();
      if (!response.ok() || !/\/api\/(project|sensitivity)$/.test(request.url())) return;
      const body = request.postDataJSON();
      responses.push(body.assumptions?.inflation);
      if (refreshing && request.url().endsWith("/project") && !body.n_runs) {
        refreshOrder.push("baseline response");
      }
    });

    const milestoneLabel = "Projection ordering check";
    let milestoneId: number | undefined;
    try {
      if (trigger === "milestone save") {
        const [household] = await (await api.get("/api/households")).json();
        const created = await api.post("/api/milestones", {
          data: {
            household_id: household.id,
            label: milestoneLabel,
            on_date: "2030-01-01",
            params: { type: "lump_sum_in", amount: "1000" },
          },
        });
        expect(created.ok()).toBe(true);
        milestoneId = (await created.json()).id;
      }
      await page.goto("/#plan");
      await page.getByRole("tab", { name: "Sensitivity" }).click();
      await expect.poll(() => responses.filter((rate) => rate === 0.02)).toHaveLength(3);

      const inflation = page.getByRole("textbox", { name: "Inflation" });
      if (trigger === "cached inflation") {
        await inflation.fill("3.5");
        await expect.poll(() => responses.filter((rate) => rate === 0.035)).toHaveLength(3);
      }

      refreshing = true;
      if (trigger === "cached inflation") {
        await inflation.fill("2");
      } else if (trigger === "refocus") {
        await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
      } else {
        await page.getByRole("button", { name: `Milestone: ${milestoneLabel}` }).press("Enter");
        const drawer = page.getByRole("dialog");
        await drawer.getByLabel("Amount (EUR)").fill("2000");
        await drawer.getByRole("button", { name: "Save", exact: true }).click();
      }

      await expect.poll(() => refreshOrder).toContain("baseline");
      if (trigger !== "milestone save") {
        await expect(page.getByRole("group", { name: /^Net worth from/ })).toBeVisible();
      }
      releaseBaseline();

      await expect.poll(() => refreshOrder.length).toBe(4);
      expect(refreshOrder.slice(0, 2)).toEqual(["baseline", "baseline response"]);
      expect(refreshOrder.slice(2).sort()).toEqual(["bands", "sensitivity"]);
    } finally {
      releaseBaseline();
      if (milestoneId !== undefined) await api.delete(`/api/milestones/${milestoneId}`);
    }
  });
}
