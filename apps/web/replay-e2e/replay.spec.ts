import { test, expect } from "@playwright/test";
const screenshotRoot = "../../var/ui-review/screenshots";

test("recordings, exact citations, keyboard and honest failure reports without backend access", async ({
  page,
}) => {
  const requests: { url: string; method: string }[] = [];
  const errors: string[] = [];
  page.on("request", (request) =>
    requests.push({ url: request.url(), method: request.method() }),
  );
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByText("RECORDED SYNTHETIC DEMO", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("article.requirement")).toHaveCount(8);
  const source = page
    .getByRole("button", { name: "Inspect obligation source ↗" })
    .first();
  await source.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Citation source" });
  await expect(dialog.locator("mark")).toHaveText(
    "4.1 Data must remain in Canada.",
  );
  await page.keyboard.press("Tab");
  await expect(
    dialog.getByRole("button", { name: "Close", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(source).toBeFocused();
  await page.getByRole("searchbox").fill("no match");
  await expect(
    page.getByText("No matching requirements.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("searchbox").fill("Canada");
  await expect(page.locator("article.requirement")).toHaveCount(1);
  await page
    .getByLabel("Recording", { exact: true })
    .selectOption("recorded-residency");
  await expect(page.locator("article.requirement")).toHaveCount(1);
  await page
    .getByRole("button", {
      name: "“Customer data remains in Canada.”",
      exact: false,
    })
    .click();
  await expect(dialog.locator("mark")).toHaveText(
    "Customer data remains in Canada.",
  );
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "CHAOSLAB results", exact: true })
    .click();
  await expect(
    page.getByText("extraction-heldout-language", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".fail")).toHaveCount(10);
  await page
    .getByRole("button", { name: "Recording provenance", exact: true })
    .click();
  await expect(
    page.getByText("No new provider call is made by this viewer.", {
      exact: false,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
      cookies: document.cookie,
    })),
  ).toEqual({ local: 0, session: 0, cookies: "" });
  expect(
    requests.every(
      (r) =>
        r.method === "GET" &&
        new URL(r.url).origin === "http://127.0.0.1:8127" &&
        !r.url.includes("/api"),
    ),
  ).toBe(true);
  // CSP blocks even accidental future fetches. This is an intentional negative probe.
  expect(
    await page.evaluate(async () => {
      try {
        await fetch("/api/me");
        return false;
      } catch {
        return true;
      }
    }),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("mobile register and evidence remain readable without horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator("article.requirement")).toHaveCount(8);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "CHAOSLAB results", exact: true })
    .click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Requirements", exact: true }).click();
  await page
    .getByRole("button", { name: "Inspect obligation source ↗" })
    .first()
    .click();
  await expect(page.getByRole("dialog").locator("mark")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("capture desktop recorded demo", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.goto("/");
  await expect(page.locator("article.requirement")).toHaveCount(8);
  await page.screenshot({
    path: `${screenshotRoot}/replay.png`,
    fullPage: true,
  });
});
