import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";

test("real browser model review retains evidence, attribution and pending review", async ({
  page,
}) => {
  test.skip(
    process.env.ATLAS_LIVE_MODEL_VALIDATION !== "1",
    "Explicit paid validation opt-in required",
  );
  const name = process.env.ATLAS_LIVE_RUN_NAME;
  if (!name || !/^[a-z0-9-]{1,64}$/.test(name))
    throw new Error("A new bounded run name is required");
  const directory = `../../var/browser-model/${name}`;
  mkdirSync(directory, { recursive: true });
  // Never silently replay an interrupted or failed potentially billable run.
  writeFileSync(
    `${directory}/attempt.json`,
    JSON.stringify({ started: new Date().toISOString() }),
    { flag: "wx", mode: 0o600 },
  );
  const token = Object.keys(
    JSON.parse(readFileSync("../../var/local-credentials.json", "utf8")),
  )[0];
  const golden = JSON.parse(
    readFileSync("../../datasets/reasoning.json", "utf8"),
  ).cases[0];
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByRole("button", { name: "New analysis" }).click();
  await expect(page.getByLabel("Analysis mode")).toHaveValue("baseline");
  await page.getByLabel("Analysis mode").selectOption("bedrock");
  await page.getByLabel("RFP text").fill(golden.requirement);
  await page.getByLabel("Knowledge text").fill(golden.evidence);
  const submitted = page.waitForResponse(
    (r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST",
  );
  const readback = page.waitForResponse(
    (r) =>
      /\/api\/runs\/[^/]+$/.test(r.url()) && r.request().method() === "GET",
    { timeout: 280000 },
  );
  await page.getByRole("button", { name: "Analyze documents" }).click();
  const accepted = await submitted;
  expect(accepted.status()).toBe(202);
  const job = await accepted.json();
  await expect(
    page.getByText("Analysis complete", { exact: true }),
  ).toBeVisible({ timeout: 280000 });
  const response = await readback;
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.provider).toBe("bedrock");
  expect(result.model_config_sha256).toBe(job.model_config_sha256);
  expect(result.assessments).toHaveLength(1);
  const item = result.assessments[0];
  expect(item.requirement.text).toBe(golden.requirement);
  expect(item.status).toBe("evidence_found");
  expect(item.review_state).toBe("pending");
  expect(item.evidence[0].quote).toBe(golden.evidence);
  await expect(
    page
      .getByRole("region", { name: "Analysis execution" })
      .getByText("AI-assisted review · AWS Bedrock", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect requirement source" })
    .click();
  await expect(page.locator("mark")).toHaveText(golden.requirement);
  await page.getByLabel("Close source").click();
  await page.screenshot({
    path: `${directory}/workbench.png`,
    fullPage: false,
  });
  writeFileSync(
    `${directory}/result.json`,
    JSON.stringify(
      {
        job,
        result,
        submitted_input: accepted.request().postDataJSON(),
        case_id: golden.id,
      },
      null,
      2,
    ),
    { mode: 0o600 },
  );
});
