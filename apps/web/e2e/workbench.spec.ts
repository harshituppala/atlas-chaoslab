import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const token = Object.keys(
  JSON.parse(readFileSync("../../var/local-credentials.json", "utf8")),
)[0];
test("review a sourced requirement and inspect measured failures", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  const accepted = page.waitForResponse(
    (r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Run seeded demonstration" }).click();
  expect((await accepted).status()).toBe(202);
  await expect(
    page.getByText("Analysis complete", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Requirement register")).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect requirement source" })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Source document" }),
  ).toBeVisible();
  await expect(page.locator("mark")).toContainText("Canada");
  await page.getByLabel("Close source").click();
  await page
    .getByLabel("Review note")
    .fill("Validated against the source excerpt in the demo.");
  const previousVersion = Number(
    (await page
      .getByText(/^v\d+ · (pending|approved|rejected)$/)
      .textContent())!.match(/v(\d+)/)![1],
  );
  const reviewed = page.waitForResponse(
    (response) =>
      response.url().includes("/reviews/") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Approve evidence review" }).click();
  expect((await reviewed).status()).toBe(200);
  await expect(
    page.getByText(`v${previousVersion + 1} · approved`, { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../../reports/workbench.png",
    fullPage: false,
  });
  await page.getByRole("button", { name: "CHAOSLAB benchmarks" }).click();
  await expect(page.getByText("extraction-heldout-language")).toBeVisible();
  const reasoning = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Factual support evaluation" }),
  });
  await expect(
    reasoning.getByText("10 / 18 grounded cases passed", { exact: true }),
  ).toBeVisible();
  await expect(reasoning.getByText("50.0%", { exact: true })).toBeVisible();
  await reasoning
    .getByText("Inspect 18 labelled cases", { exact: true })
    .click();
  await expect(
    reasoning
      .getByRole("row")
      .filter({ hasText: "paraphrased obligation" })
      .getByText("omitted", { exact: true }),
  ).toBeVisible();
  await reasoning.screenshot({ path: "../../reports/chaoslab-reasoning.png" });
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "extraction-heldout-language" })
      .getByText("Failed", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Workflow recovery", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("7 / 7 scenarios passed")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Adversarial evidence selection" }),
  ).toBeVisible();
  await expect(
    page.getByText("3 / 6 authored probes passed", { exact: true }),
  ).toBeVisible();
  await page
    .locator("section")
    .filter({
      has: page.getByRole("heading", {
        name: "Adversarial evidence selection",
      }),
    })
    .screenshot({ path: "../../reports/chaoslab-adversarial.png" });
  await expect(
    page.getByText("Retrieval comparison", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("10 authored queries · local CPU")).toBeVisible();
  await expect(
    page.getByText("Document ingestion", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("4 / 4 authored cases passed")).toBeVisible();
  await expect(
    page.getByText("PostgreSQL integration", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Persistent retrieval", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("17 / 17 integration groups passed"),
  ).toBeVisible();
});

test("modal keyboard boundaries, focus return, disconnect and response privacy", async ({
  page,
}) => {
  const policyErrors: string[] = [];
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      message.text().includes("Content Security Policy")
    )
      policyErrors.push(message.text());
  });
  const initial = await page.goto("/");
  expect(initial!.headers()["content-security-policy"]).toContain(
    "script-src 'self'",
  );
  await page.getByLabel("Workspace token").fill(token);
  const privateResponse = page.waitForResponse((r) =>
    r.url().endsWith("/api/runs"),
  );
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  expect((await privateResponse).headers()["cache-control"]).toBe("no-store");
  const opener = page.getByRole("button", {
    name: "+ New analysis",
    exact: true,
  });
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "New analysis" });
  const close = dialog.getByRole("button", { name: "Close", exact: true });
  await expect(close).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(
    dialog.getByLabel("Knowledge text", { exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.getByLabel("Workspace token")).toHaveValue("");
  await expect(opener).toBeDisabled();
  expect(policyErrors).toEqual([]);
});

test("upload PDF and DOCX, inspect a mapped page, and recover the original", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page
    .getByRole("button", { name: "+ New analysis", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "New analysis" });
  await dialog
    .getByLabel("RFP file", { exact: true })
    .setInputFiles("../../datasets/documents/municipal-rfp.pdf");
  await expect(
    dialog.getByText("2 mapped pages · Immutable source"),
  ).toBeVisible();
  await dialog
    .getByLabel("Knowledge file", { exact: true })
    .setInputFiles("../../datasets/documents/capability-register.docx");
  await expect(
    dialog.getByText("8 mapped paragraphs · Immutable source"),
  ).toBeVisible();
  await dialog
    .getByRole("button", { name: "Analyze documents", exact: true })
    .click();
  await expect(
    page.getByText("Analysis complete", { exact: true }),
  ).toBeVisible();
  await page
    .locator("button.requirement")
    .filter({ hasText: "Recovery time must be at most 4 hours." })
    .click();
  await page
    .getByRole("button", { name: "Inspect requirement source" })
    .click();
  const source = page.getByRole("dialog", { name: "Source document" });
  await expect(source.getByText("Page 2", { exact: true })).toBeVisible();
  await expect(source.locator("mark")).toHaveText(
    "5.2 Recovery time must be at most 4 hours.",
  );
  const downloaded = page.waitForEvent("download");
  await source
    .getByRole("button", { name: "Download original source" })
    .click();
  const download = await downloaded;
  expect(readFileSync((await download.path())!)).toEqual(
    readFileSync("../../datasets/documents/municipal-rfp.pdf"),
  );
  await page.screenshot({
    path: "../../reports/upload-source.png",
    fullPage: false,
  });
});

test("source highlighting preserves Unicode character offsets after emoji", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page
    .getByRole("button", { name: "+ New analysis", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "New analysis" });
  await dialog
    .getByLabel("RFP text", { exact: true })
    .fill("📄 Procurement résumé\nData must remain in Canada.");
  await dialog
    .getByLabel("Knowledge text", { exact: true })
    .fill("Canada data residency is provided.");
  await dialog
    .getByRole("button", { name: "Analyze documents", exact: true })
    .click();
  await expect(
    page.getByText("Analysis complete", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect requirement source" })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Source document" }).locator("mark"),
  ).toHaveText("Data must remain in Canada.");
});

// Controlled identity response tests presentation; backend tests enforce the actual permissions.
test("viewer controls reflect the resolved workspace identity", async ({
  page,
}) => {
  await page.route("**/api/me", (route) =>
    route.fulfill({
      json: {
        tenant: "northstar",
        actor: "viewer-fixture",
        role: "viewer",
        authentication: "local-bearer",
      },
    }),
  );
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByText("northstar · viewer", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "+ New analysis" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Run seeded demonstration" }),
  ).toBeDisabled();
  await page.locator(".history button").first().click();
  await expect(page.getByText("Requirement register")).toBeVisible();
  await expect(page.getByLabel("Review note")).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Reject", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Approve evidence review" }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Inspect requirement source" })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Source document" }),
  ).toBeVisible();
  await page.getByLabel("Close source").click();
  await page.getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.getByLabel("Workspace token")).toHaveValue("");
  await expect(page.getByLabel("Workspace ID")).toHaveValue("");
  await expect(
    page.getByText("northstar · viewer", { exact: true }),
  ).toHaveCount(0);
});

// An empty-denominator report is a presentation fixture, not another measured quality case.
test("unknown quality metrics are displayed without fabricated zeroes", async ({
  page,
}) => {
  await page.route("**/api/benchmarks", (route) =>
    route.fulfill({
      json: {
        unique_cases: 1,
        case_pass_rate: 1,
        extraction_precision: null,
        extraction_recall: null,
        citation_integrity: null,
        latency_median_ms: 0,
        scope: "Controlled empty-denominator UI fixture",
        results: [
          {
            id: "no-mandatory-control",
            repeat: 0,
            passed: true,
            checks: {},
            latency_ms: 0,
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Disconnect", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "CHAOSLAB benchmarks" }).click();
  await expect(page.getByText("Not measured", { exact: true })).toHaveCount(2);
  await expect(page.getByText("0.0%", { exact: true })).toHaveCount(0);
});

test("live diagnostics expose incomplete coverage and unknown cost", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "CHAOSLAB benchmarks" }).click();
  const live = page.getByRole("region", { name: "Live model diagnostics" });
  await live.getByLabel("Recorded model run").selectOption({
    label: "source-selection-v3 · 18-case set · 15 attempted",
  });
  await expect(live.getByText("11 / 15", { exact: true })).toBeVisible();
  await expect(live.getByText("Unknown", { exact: true })).toBeVisible();
  await expect(live.getByText(/Incomplete run: 3 cases/)).toBeVisible();
  await expect(live.getByText(/Unknown cost is not zero/)).toBeVisible();
  await live.getByLabel("Recorded model run").selectOption({
    label: "source-selection-v4 · 12-case set · 12 attempted",
  });
  await expect(live.getByText("10 / 12", { exact: true })).toBeVisible();
  await expect(live.getByText(/Incomplete run:/)).toHaveCount(0);
  await expect(live.getByText("$0.0183", { exact: true })).toBeVisible();
  await live.getByText("Inspect 12 labelled cases", { exact: true }).click();
  await expect(
    live
      .getByRole("row")
      .filter({ hasText: "deletion 1" })
      .getByText("Failed", { exact: true }),
  ).toBeVisible();
});

test("analysis mode selection is explicit and resets to baseline (controlled capabilities)", async ({
  page,
}) => {
  await page.route("**/api/execution-options", (route) =>
    route.fulfill({
      json: {
        model: {
          enabled: true,
          model_id: "synthetic-ui-fixture",
          region: "test-region",
          maximum_reserved_inference_usd: "0.0202752",
          model_config_sha256: "a".repeat(64),
        },
      },
    }),
  );
  let submitted: Record<string, unknown> | undefined;
  await page.route("**/api/jobs", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submitted = route.request().postDataJSON();
    await route.fulfill({
      status: 202,
      json: {
        id: "controlled-mode-fixture",
        status: "failed",
        attempts: 1,
        max_attempts: 1,
        error_code: "execution_error",
      },
    });
  });
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "New analysis" }).click();
  await expect(page.getByLabel("Analysis mode")).toHaveValue("baseline");
  await page.getByLabel("Analysis mode").selectOption("bedrock");
  await expect(
    page.getByText(/Source text will be sent to AWS Bedrock/),
  ).toBeVisible();
  await expect(page.getByText(/US\$0.0203/)).toBeVisible();
  await page.screenshot({
    path: "../../reports/analysis-mode.png",
    fullPage: false,
  });
  await page.getByLabel("RFP text").fill("The vendor must support federation.");
  await page.getByLabel("Knowledge text").fill("Federation is supported.");
  await page.getByRole("button", { name: "Analyze documents" }).click();
  await expect(page.getByRole("dialog", { name: "New analysis" })).toHaveCount(
    0,
  );
  expect(submitted?.execution_mode).toBe("bedrock");
  expect(submitted?.expected_model_config_sha256).toBe("a".repeat(64));
  expect(submitted).not.toHaveProperty("profile");
  await page.getByRole("button", { name: "New analysis" }).click();
  await expect(page.getByLabel("Analysis mode")).toHaveValue("baseline");
});

test("saved model review displays unknown cost and configuration (controlled result)", async ({
  page,
}) => {
  const result = {
    id: "controlled-attribution",
    created: "2026-10-16T10:00:00Z",
    documents: [
      {
        id: "synthetic",
        title: "Synthetic saved review",
        kind: "rfp",
        text: "Synthetic obligation.",
      },
    ],
    assessments: [],
    trace: [],
    limitations: "Controlled presentation fixture",
    provider: "bedrock",
    pipeline_version: "source-selection-v4",
    model_cost_usd: null,
    model_config_sha256: "b".repeat(64),
  };
  await page.route("**/api/runs", (route) =>
    route.fulfill({ json: [{ id: result.id, created: result.created }] }),
  );
  await page.route("**/api/runs/controlled-attribution", (route) =>
    route.fulfill({ json: result }),
  );
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: /Analysis 1/ }).click();
  const execution = page.getByRole("region", { name: "Analysis execution" });
  await expect(
    execution.getByText("AI-assisted review · AWS Bedrock", { exact: true }),
  ).toBeVisible();
  await expect(execution.getByText(/Model cost unknown/)).toBeVisible();
  await expect(page.locator(".sidebar-bottom")).toContainText("Bedrock review");
  await execution.getByText("Execution configuration identity").click();
  await expect(execution.getByText("b".repeat(64))).toBeVisible();
});

test("complete scenarios distinguish obligation and whole-review results", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "CHAOSLAB benchmarks" }).click();
  const panel = page.getByRole("region", { name: "Complete review scenarios" });
  const baseline = panel
    .getByRole("row")
    .filter({ hasText: "Extractive baseline" });
  await expect(baseline.getByText("5 / 9", { exact: true })).toBeVisible();
  await expect(baseline.getByText("0 / 3", { exact: true })).toBeVisible();
  const model = panel
    .getByRole("row")
    .filter({ hasText: "source-selection-v4" });
  await expect(model.getByText("9 / 9", { exact: true })).toBeVisible();
  await expect(model.getByText("3 / 3", { exact: true })).toBeVisible();
  await panel.getByText("Inspect recorded model scenarios").click();
  await expect(
    panel.getByRole("heading", { name: "split evidence and service hours" }),
  ).toBeVisible();
  await panel.screenshot({ path: "../../reports/scenarios-dashboard.png" });
});
