import { test, expect } from "@playwright/test";
const screenshotRoot = "../../var/ui-review/screenshots";

test("real analysis, exact sources, review conflicts across tabs, reload and logout", async ({
  page,
  context,
}) => {
  const requests: { origin: string; path: string; authorization: boolean }[] =
    [];
  const errors: string[] = [];
  page.on("request", (request) =>
    requests.push({
      origin: new URL(request.url()).origin,
      path: new URL(request.url()).pathname,
      authorization: Boolean(request.headers()["authorization"]),
    }),
  );
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1050 });
  const response = await page.goto("/");
  expect(response?.headers()["content-security-policy"]).toContain(
    "connect-src 'self'",
  );
  await expect(
    page.getByRole("heading", {
      name: "Can this supplier meet the buyer’s requirements?",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "How to use this demo" }),
  ).toContainText("4 hours");
  await expect(
    page.getByText("This demo searches the supplied text using rules", {
      exact: false,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: `${screenshotRoot}/lab-start-desktop.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Run sample analysis" }).click();
  await expect(page.locator("article.requirement")).toHaveCount(8);
  await page
    .getByRole("button", {
      name: "Open the recovery-time example",
      exact: true,
    })
    .click();
  const examplePanel = page.getByRole("complementary", {
    name: "Human review",
  });
  await expect(
    examplePanel.getByRole("heading", {
      name: "5.2 Recovery time must be at most 4 hours.",
      exact: true,
    }),
  ).toBeVisible();
  await expect(examplePanel).toContainText(
    "Recovery time is only guaranteed within 8 hours.",
  );
  await expect(examplePanel).toContainText(
    "The supplied documents appear to disagree",
  );
  await page
    .getByText("What do the three findings mean?", { exact: true })
    .click();
  await expect(
    page.getByText("This is a gap in the supplied evidence, not proof", {
      exact: false,
    }),
  ).toBeVisible();
  const source = page
    .getByRole("button", { name: "Inspect obligation source", exact: true })
    .first();
  await source.click();
  const dialog = page.getByRole("dialog", { name: "Source excerpt" });
  await expect(dialog.locator("mark")).toHaveText(
    "4.1 Data must remain in Canada.",
  );
  await expect(
    dialog.getByRole("button", { name: "Close", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(source).toBeFocused();
  await page.getByRole("searchbox").fill("no matching phrase");
  await expect(page.getByText("No matching requirements.")).toBeVisible();
  await page.getByRole("searchbox").fill("");
  await page
    .locator('article[data-status="evidence_found"]')
    .first()
    .getByRole("button", { name: /^Review / })
    .click();
  const panel = page.getByRole("complementary", { name: "Human review" });
  await panel
    .getByRole("combobox", { name: "Decision", exact: true })
    .selectOption("approved");
  await panel
    .getByRole("combobox", { name: "Review note", exact: true })
    .selectOption("excerpt_checked");
  const second = await context.newPage();
  await second.goto("/");
  await expect(second.locator("article.requirement")).toHaveCount(8);
  await expect(
    second.getByRole("region", { name: "How to use this demo" }),
  ).toBeVisible();
  await second
    .locator('article[data-status="evidence_found"]')
    .first()
    .getByRole("button", { name: /^Review / })
    .click();
  await panel.getByRole("button", { name: "Save review" }).click();
  await expect(panel.locator(".review-state")).toHaveText(
    "Current review: approved · version 2",
  );
  const otherPanel = second.getByRole("complementary", {
    name: "Human review",
  });
  await otherPanel.getByRole("button", { name: "Save review" }).click();
  await expect(second.getByRole("status")).toContainText(
    "Another review changed this requirement",
  );
  await expect(otherPanel.locator(".review-state")).toHaveText(
    "Current review: approved · version 2",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `${screenshotRoot}/synthetic-workbench.png`,
    fullPage: true,
  });
  expect(
    await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
      cookie: document.cookie,
    })),
  ).toEqual({ local: 0, session: 0, cookie: "" });
  const cookie = (await context.cookies()).find(
    (c) => c.name === "atlas-lab-local",
  );
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");
  expect(cookie?.secure).toBe(false); // Real loopback HTTP; hosted TLS is not claimed.
  expect(
    requests.every(
      (r) =>
        r.origin === "http://127.0.0.1:8134" &&
        !r.authorization &&
        (!r.path.startsWith("/api/") || r.path.startsWith("/api/lab/")),
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
  await second.getByRole("button", { name: "End session" }).click();
  await expect(second.getByRole("status")).toHaveText(
    "Session cleared. No review history is retained.",
  );
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Run sample analysis" }),
  ).toBeEnabled();
  await expect(page.locator("article.requirement")).toHaveCount(0);
});

test("mobile conflict review and a controlled capacity message recover without automatic retries", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let attempts = 0;
  await page.route("**/api/lab/session", async (route) => {
    if (route.request().method() === "POST") {
      attempts++;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: '{"detail":"Controlled capacity fault"}',
      });
    } else await route.continue();
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Can this supplier meet the buyer’s requirements?",
    }),
  ).toBeVisible();
  await page.screenshot({
    path: `${screenshotRoot}/lab-start-mobile.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Run sample analysis" }).click();
  await expect(page.getByRole("status")).toContainText(
    "temporary capacity or activity limit",
  );
  expect(attempts).toBe(1);
  await page.unroute("**/api/lab/session");
  await page.getByRole("button", { name: "Run sample analysis" }).click();
  await expect(page.locator("article.requirement")).toHaveCount(8);
  await page
    .getByRole("combobox", { name: "Finding", exact: true })
    .selectOption("conflicting_evidence");
  const row = page
    .locator('article[data-status="conflicting_evidence"]')
    .filter({ hasText: "Recovery time" });
  await row.getByRole("button", { name: /^Review / }).click();
  const panel = page.getByRole("complementary", { name: "Human review" });
  await expect(
    panel.getByRole("option", { name: "Approve evidence" }),
  ).toHaveAttribute("disabled", "");
  await panel
    .getByRole("button", { name: /Inspect capability source/ })
    .click();
  await expect(page.getByRole("dialog").locator("mark")).toContainText(
    "8 hours",
  );
  await page.keyboard.press("Escape");
  await panel.getByRole("button", { name: "Save review" }).click();
  await expect(panel.locator(".review-state")).toHaveText(
    "Current review: rejected · version 2",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `${screenshotRoot}/synthetic-workbench-mobile.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "End session" }).click();
});

test("client expiry clears a restored workspace using controlled lifetime metadata", async ({
  page,
}) => {
  const headers = { Origin: "http://127.0.0.1:8134" };
  expect(
    (
      await page.request.post("/api/lab/session", { headers, data: {} })
    ).status(),
  ).toBe(200);
  expect(
    (
      await page.request.post("/api/lab/run", {
        headers,
        data: { case_id: "municipal" },
      })
    ).status(),
  ).toBe(200);
  await page.route("**/api/lab/session", async (route) => {
    const response = await route.fetch();
    const metadata = await response.json();
    await route.fulfill({
      response,
      json: { ...metadata, expires_in_seconds: 1 },
    });
  });
  await page.goto("/");
  await expect(page.locator("article.requirement")).toHaveCount(8);
  await expect(page.locator("article.requirement")).toHaveCount(0);
  await expect(page.getByRole("status")).toContainText(
    "temporary session ended",
  );
  // Only lifetime metadata was shortened. Actual server expiry is covered by native tests.
  expect((await page.request.get("/api/lab/session")).status()).toBe(200);
  expect(
    (await page.request.delete("/api/lab/session", { headers })).status(),
  ).toBe(204);
});

for (const width of [1440, 390]) {
  test(`recorded evaluation at ${width}px explains comparisons and failures without API calls`, async ({
    page,
    context,
  }) => {
    const apiRequests: string[] = [];
    const errors: string[] = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname.startsWith("/api/"))
        apiRequests.push(request.url());
    });
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/?view=evaluation");
    await expect(
      page.getByRole("heading", {
        name: "Does the model make the review better?",
      }),
    ).toBeVisible();
    await expect(
      page.getByText("Opening this page makes no model request", {
        exact: false,
      }),
    ).toBeVisible();
    const scenarios = page.getByRole("region", {
      name: "Complete review scenarios",
    });
    await expect(
      scenarios.getByRole("cell", { name: "5 / 9", exact: true }),
    ).toBeVisible();
    await expect(
      scenarios.getByRole("cell", { name: "9 / 9", exact: true }),
    ).toBeVisible();
    const transfer = page.getByRole("table").filter({
      has: page.getByText("Recorded results on the same twelve cases", {
        exact: true,
      }),
    });
    await expect(transfer).toContainText("7 / 12");
    await expect(transfer).toContainText("10 / 12");
    const failure = page.getByRole("region", {
      name: "Inspect a recorded model failure",
    });
    await expect(failure).toContainText("48 hours");
    await expect(failure).toContainText("24 hours");
    await expect(failure).toContainText(
      "Matched the source text, even though the decision was wrong",
    );
    await page
      .getByRole("combobox", { name: "Failed case" })
      .selectOption("availability-3");
    await expect(failure).toContainText("No valid requirement extracted");
    await expect(failure).toContainText(
      "Not available for this failed extraction",
    );
    await page
      .getByText("Inspect recorded model scenarios", { exact: true })
      .click();
    await page
      .getByText("What these results do and do not establish", { exact: true })
      .click();
    await expect(
      page.getByText("Their counts cannot be", { exact: false }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(
      await page.evaluate(() => ({
        local: localStorage.length,
        session: sessionStorage.length,
      })),
    ).toEqual({ local: 0, session: 0 });
    expect(await context.cookies()).toEqual([]);
    expect(apiRequests).toEqual([]);
    expect(errors).toEqual([]);
    await page.screenshot({
      path: `${screenshotRoot}/public-evaluation-${width}.png`,
      fullPage: true,
    });
    await page
      .getByRole("navigation")
      .getByRole("link", { name: "Review sample", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Run sample analysis" }),
    ).toBeEnabled();
  });
}
