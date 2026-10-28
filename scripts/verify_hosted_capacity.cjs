/* Real public-lab capacity/refusal/recovery. Own fictional sessions only. */
const {
  chromium,
  request,
  expect,
} = require("../apps/web/node_modules/@playwright/test");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const assert = require("node:assert/strict");
const verificationDigest = crypto
  .createHash("sha256")
  .update(fs.readFileSync(__filename))
  .digest("hex");
const origin = process.argv[2] || "https://atlas-review-lab.onrender.com";
assert.equal(origin, "https://atlas-review-lab.onrender.com");
const root = path.resolve(__dirname, "..");
const out = path.join(root, "var/employer-review");
fs.mkdirSync(out, { recursive: true });
(async () => {
  const holders = [];
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(45000);
  const headers = { Origin: origin };
  const errors = [];
  const responses = [];
  let posts = 0;
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (r.method() === "POST") posts++;
  });
  page.on("response", (r) => {
    const u = new URL(r.url());
    if (u.pathname.startsWith("/api/"))
      responses.push({ path: u.pathname, status: r.status() });
  });
  try {
    const health = await page.request.get(origin + "/healthz");
    assert.equal(health.status(), 200);
    assert.equal((await health.json()).profile, "temporary-synthetic-lab");
    for (let i = 0; i < 4; i++) {
      const holder = await request.newContext({ baseURL: origin });
      holders.push(holder);
      assert.equal(
        (await holder.post("/api/lab/session", { headers, data: {} })).status(),
        200,
        "Four own slots unavailable; release owned sessions and retain failure rather than disturbing other visitors",
      );
    }
    await page.goto(origin, { waitUntil: "domcontentloaded", timeout: 90000 });
    await expect(
      page.getByRole("button", { name: "Run sample analysis", exact: true }),
    ).toBeEnabled();
    await page.clock.install();
    await page.clock.pauseAt(new Date());
    await page
      .getByRole("button", { name: "Run sample analysis", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("wait 60 seconds");
    await expect(
      page.getByRole("button", { name: "Try again in 60s", exact: true }),
    ).toBeDisabled();
    assert.equal(posts, 1);
    const widths = [];
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      const opener = page.getByRole("button", {
        name: "View saved worked example",
        exact: true,
      });
      await opener.click();
      const dialog = page.getByRole("dialog", {
        name: "Saved worked example",
        exact: true,
      });
      await expect(dialog).toContainText("fictional · read-only");
      await expect(dialog).toContainText(
        "runs no analysis and saves no review",
      );
      await expect(dialog).toContainText(
        "5.2 Recovery time must be at most 4 hours.",
      );
      await expect(dialog).toContainText(
        "Recovery time is only guaranteed within 8 hours.",
      );
      await expect(
        dialog.getByRole("button", { name: "Close saved example" }),
      ).toBeFocused();
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
      await page.screenshot({
        path: path.join(out, `capacity-hosted-${width}.png`),
        fullPage: true,
      });
      await page.keyboard.press("Escape");
      await expect(opener).toBeFocused();
      widths.push(width);
    }
    assert.equal(posts, 1);
    await page.clock.fastForward(59000);
    await expect(
      page.getByRole("button", { name: "Try again in 1s" }),
    ).toBeDisabled();
    assert.equal(posts, 1);
    assert.equal(
      (await holders[0].delete("/api/lab/session", { headers })).status(),
      204,
    );
    await page.clock.fastForward(1000);
    const retry = page.getByRole("button", { name: "Try sample again" });
    await expect(retry).toBeEnabled();
    assert.equal(posts, 1);
    await retry.click();
    await expect(page.locator("article.requirement")).toHaveCount(8, {
      timeout: 45000,
    });
    assert.equal(posts, 3);
    await expect(
      page.getByRole("region", { name: "While the lab is busy" }),
    ).toHaveCount(0);
    await page
      .getByRole("button", {
        name: "Open the recovery-time example",
        exact: true,
      })
      .click();
    const panel = page.getByRole("complementary", { name: "Human review" });
    await expect(panel).toContainText("within 8 hours");
    await panel
      .getByRole("button", { name: "Save review", exact: true })
      .click();
    await expect(panel.locator(".review-state")).toContainText(
      "rejected · version 2",
    );
    await page
      .getByRole("button", { name: "End session", exact: true })
      .click();
    await expect(page.getByRole("status")).toHaveText(
      "Session cleared. No review history is retained.",
    );
    assert.deepEqual(errors, []);
    assert.equal(
      crypto
        .createHash("sha256")
        .update(fs.readFileSync(__filename))
        .digest("hex"),
      verificationDigest,
    );
    fs.writeFileSync(
      path.join(out, "capacity-hosted.json"),
      JSON.stringify(
        {
          recorded_at: new Date().toISOString(),
          url: origin,
          status: "passed",
          scope:
            "Real HTTPS/Chromium, four owned fictional sessions and actual 503. Browser clock alone advanced for advisory countdown; server capacity was restored by deleting an owned session. Not a server-time, load, expiry or participant test.",
          checks: {
            actual_session_capacity_503: true,
            retry_header_displayed: true,
            no_automatic_post: true,
            saved_example_no_post: true,
            read_only_label_and_sources: true,
            escape_focus_return: true,
            viewport_widths: widths,
            manual_recovery_after_owned_slot_release: true,
            analysis_requirements: 8,
            human_review_saved: true,
            logout_cleared: true,
            runtime_errors: 0,
          },
          responses,
          verification_source_sha256: crypto
            .createHash("sha256")
            .update(fs.readFileSync(__filename))
            .digest("hex"),
          new_model_calls: 0,
        },
        null,
        2,
      ) + "\n",
    );
    console.log(JSON.stringify({ status: "passed", widths, requirements: 8 }));
  } catch (e) {
    await page
      .screenshot({
        path: path.join(out, "capacity-hosted-failure.png"),
        fullPage: true,
      })
      .catch(() => {});
    fs.writeFileSync(
      path.join(out, "capacity-hosted-failure.json"),
      JSON.stringify(
        {
          recorded_at: new Date().toISOString(),
          status: "failed",
          responses,
          reason: e.message,
        },
        null,
        2,
      ),
    );
    throw e;
  } finally {
    await page.request
      .delete(origin + "/api/lab/session", { headers })
      .catch(() => {});
    for (const holder of holders) {
      await holder.delete("/api/lab/session", { headers }).catch(() => {});
      await holder.dispose();
    }
    await browser.close();
  }
})().catch((e) => {
  console.error(e.message);
  process.exitCode = 1;
});
