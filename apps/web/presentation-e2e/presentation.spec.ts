import { test, expect } from "@playwright/test";

const screenshotRoot = "../../var/ui-review/screenshots";

for (const width of [1440, 390]) {
  test(`workbench navigation and disconnected layout at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors: string[] = [];
    const apiRequests: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (request.url().includes("/api/")) apiRequests.push(request.url());
    });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Requirement review", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Workspace token", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Connect", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "+ New analysis", exact: true }),
    ).toBeDisabled();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    if (width === 1440)
      await page.screenshot({
        path: `${screenshotRoot}/review-workbench.png`,
        fullPage: false,
      });
    await page
      .getByRole("button", { name: "CHAOSLAB benchmarks", exact: false })
      .click();
    await expect(
      page.getByRole("heading", { name: "Evaluation results", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Audit trail", exact: false })
      .click();
    await expect(
      page.getByRole("heading", { name: "Audit trail", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
    expect(apiRequests).toEqual([]);
  });
}
