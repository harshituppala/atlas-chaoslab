import assert from "node:assert/strict";
import path from "node:path";
import { chromium } from "../apps/web/node_modules/@playwright/test/index.mjs";

const APP = "https://127.0.0.1";
const PROVIDER = "https://localhost";
const checks = {};
const browser = await chromium.launch({
  proxy: { server: process.env.ATLAS_FIXTURE_PROXY },
  args: [
    "--proxy-bypass-list=<-loopback>",
    "--ignore-certificate-errors-spki-list=" + process.env.ATLAS_FIXTURE_SPKI,
  ],
});
const context = await browser.newContext();
const page = await context.newPage();
page.setDefaultTimeout(15000);
const failures = [];
const diagnostics = [];
page.on("response", (response) =>
  diagnostics.push([
    new URL(response.url()).origin + new URL(response.url()).pathname,
    response.status(),
  ]),
);
page.on("console", (message) => {
  if (message.type() === "error")
    diagnostics.push(message.text().split("?")[0]);
});
page.on("pageerror", (error) => failures.push(error.message));
async function probe(action, expectedStatus = 200) {
  const control = await context.newPage();
  assert.equal(
    (await control.goto(PROVIDER + "/probe/" + action)).status(),
    expectedStatus,
  );
  await control.close();
}
async function signIn() {
  await page.goto(APP);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("heading", { name: "Synthetic identity provider" })
    .waitFor();
  const binding = (await context.cookies(APP)).find(
    (c) => c.name === "__Host-atlas-login",
  );
  assert(binding?.secure && binding.httpOnly && binding.sameSite === "Lax");
  const callback = page.waitForRequest(
    (request) => new URL(request.url()).pathname === "/auth/callback",
  );
  await page
    .getByRole("button", { name: "Continue as synthetic reviewer" })
    .click();
  await page.getByRole("heading", { name: "Open your workspace" }).waitFor();
  assert.equal(page.url(), APP + "/");
  return { binding, callbackUrl: (await callback).url() };
}
async function connect() {
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.getByText("fictional-team · reviewer").waitFor();
}
async function api(path, options = {}) {
  return page.evaluate(
    async ({ path, options }) => {
      const response = await fetch(path, options);
      return response.status;
    },
    { path, options },
  );
}
try {
  const cdp = await browser.newBrowserCDPSession();
  const command = await cdp.send("Browser.getBrowserCommandLine");
  const profile = command.arguments
    .find((argument) => argument.startsWith("--user-data-dir="))
    ?.slice("--user-data-dir=".length);
  assert(
    profile &&
      path
        .resolve(profile)
        .startsWith(path.resolve(process.env.TMPDIR) + path.sep),
  );
  await cdp.detach();
  checks.browser_profile_inside_workspace = true;
  const first = await signIn();
  checks.cross_site_code_callback = true;
  let cookie = (await context.cookies(APP)).find(
    (c) => c.name === "__Host-atlas-session",
  );
  assert(cookie?.secure && cookie.httpOnly && cookie.sameSite === "Strict");
  assert(
    !(await page.evaluate(() => document.cookie)).includes("atlas-session"),
  );
  checks.secure_httponly_strict_cookie = true;
  const foreign = await context.newPage();
  await foreign.goto(PROVIDER + "/cross-site");
  const refused = foreign.waitForResponse(
    (response) => response.url() === APP + "/api/me",
  );
  await foreign
    .getByRole("link", { name: "Try cross-site workspace access" })
    .click();
  const crossSiteResponse = await refused;
  assert.equal(crossSiteResponse.status(), 401);
  assert(
    !(await crossSiteResponse.request().allHeaders()).cookie?.includes(
      "__Host-atlas-session",
    ),
  );
  await foreign.close();
  assert.equal(await api("/api/me"), 200);
  checks.cross_site_navigation_withholds_strict_cookie = true;
  const replayContext = await browser.newContext();
  await replayContext.addCookies([first.binding]);
  const replayPage = await replayContext.newPage();
  await replayPage.goto(first.callbackUrl);
  await replayPage
    .getByRole("button", { name: "Sign in", exact: true })
    .waitFor();
  assert.equal(
    await replayPage.evaluate(async () => (await fetch("/api/me")).status),
    401,
  );
  await replayContext.close();
  checks.consumed_callback_replay_refused = true;
  await connect();
  await page.evaluate(async () => {
    const response = await fetch("/auth/session");
    const metadata = await response.json();
    if (Object.keys(metadata).sort().join(",") !== "csrf_token,expires_at")
      throw Error("Unexpected session fields");
    if (typeof metadata.csrf_token !== "string")
      throw Error("Missing CSRF metadata");
  });
  assert.equal(
    await api("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }),
    403,
  );
  checks.browser_write_requires_csrf = true;
  if (process.env.ATLAS_FIXTURE_SEPARATE_WORKER === "1")
    await probe("pause-worker");
  const accepted = page.waitForResponse(
    (r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Run seeded demonstration" }).click();
  const acceptedResponse = await accepted;
  assert.equal(acceptedResponse.status(), 202);
  if (process.env.ATLAS_FIXTURE_SEPARATE_WORKER === "1") {
    await probe("process", 409);
    const job = await acceptedResponse.json();
    const state = await page.evaluate(
      async (id) => (await fetch("/api/jobs/" + id)).json(),
      job.id,
    );
    assert.equal(state.status, "queued");
    await probe("resume-worker");
  } else {
    await probe("process");
  }
  await page.getByText("Analysis complete", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Inspect requirement source" })
    .click();
  await page.getByRole("dialog", { name: "Source document" }).waitFor();
  await page.getByLabel("Close source").click();
  const review = page.waitForResponse(
    (r) => r.url().includes("/reviews/") && r.request().method() === "POST",
  );
  await page
    .getByLabel("Review note")
    .fill("Synthetic browser acceptance review.");
  await page.getByRole("button", { name: "Approve evidence review" }).click();
  assert.equal((await review).status(), 200);
  checks.signed_identity_job_source_review = true;
  if (process.env.ATLAS_FIXTURE_SEPARATE_WORKER === "1")
    checks.separate_worker_restart_processed_queued_job = true;
  if (process.env.ATLAS_FIXTURE_RESTART_ORIGIN) {
    const reviewUrl = (await review).url();
    const runPath = new URL(reviewUrl).pathname.split("/reviews/")[0];
    const before = await page.evaluate(
      async (p) => ({
        run: await (await fetch(p)).json(),
        audit: await (await fetch(p + "/audit")).json(),
      }),
      runPath,
    );
    const response = await fetch(
      process.env.ATLAS_FIXTURE_RESTART_ORIGIN + "/restart-app",
      {
        method: "POST",
        headers: {
          "X-Fixture-Control": process.env.ATLAS_FIXTURE_RESTART_SECRET,
        },
      },
    );
    assert.equal(response.status, 200);
    assert.equal(await api("/api/me"), 401);
    await signIn();
    await connect();
    const after = await page.evaluate(
      async (p) => ({
        run: await (await fetch(p)).json(),
        audit: await (await fetch(p + "/audit")).json(),
      }),
      runPath,
    );
    assert.deepEqual(after, before);
    const currentCookie = (await context.cookies(APP)).find(
      (c) => c.name === "__Host-atlas-session",
    );
    await context.addCookies([cookie]);
    assert.equal(await api("/api/me"), 401);
    await context.addCookies([currentCookie]);
    assert.equal(await api("/api/me"), 200);
    cookie = currentCookie;
    checks.application_process_restart_preserves_review_and_rejects_old_session = true;
    if (process.env.ATLAS_FIXTURE_STORAGE === "restart")
      checks.database_process_restart_preserves_review_and_audit = true;
    if (process.env.ATLAS_FIXTURE_STORAGE === "restore")
      checks.fresh_database_restore_preserves_review_and_audit = true;
  }
  await page.screenshot({ path: process.env.ATLAS_FIXTURE_SCREENSHOT });
  await probe("revoke");
  assert.equal(await api("/api/me"), 403);
  await page.getByRole("button", { name: "CHAOSLAB benchmarks" }).click();
  await page
    .getByRole("heading", { name: "Sign in to your workspace" })
    .waitFor();
  assert.equal(await page.getByText("fictional-team · reviewer").count(), 0);
  checks.membership_revocation_hides_workspace = true;
  await page.getByRole("button", { name: "Retry sign-out" }).click();
  await page.getByText("Signed out of ATLAS.", { exact: false }).waitFor();
  assert.equal(await api("/api/me"), 401);
  // Restoring a captured opaque cookie must not restore a logged-out server session.
  await context.addCookies([cookie]);
  assert.equal(await api("/api/me"), 401);
  checks.logout_invalidates_captured_cookie = true;
  await context.clearCookies();
  await probe("restore");
  await signIn();
  await connect();
  await probe("expire");
  await page.getByRole("button", { name: "CHAOSLAB benchmarks" }).click();
  await page
    .getByRole("heading", { name: "Sign in to your workspace" })
    .waitFor();
  checks.controlled_server_expiry_hides_workspace = true;
  await probe("reset-clock");
  await context.clearCookies();
  await page.goto(APP);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Deny sign-in" }).click();
  await page.getByRole("button", { name: "Sign in", exact: true }).waitFor();
  assert.equal(await api("/api/me"), 401);
  checks.provider_denial_keeps_workspace_closed = true;
  assert.deepEqual(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
    [0, 0],
  );
  assert.deepEqual(failures, []);
  checks.no_browser_storage_or_runtime_errors = true;
  console.log(JSON.stringify({ checks, browser: browser.version() }));
} catch (error) {
  await page.screenshot({
    path: process.env.ATLAS_FIXTURE_SCREENSHOT.replace(
      "workbench.png",
      "failure.png",
    ),
  });
  console.error(
    JSON.stringify({
      page: new URL(page.url()).origin + new URL(page.url()).pathname,
      body: await page.locator("body").innerText(),
      completed_checks: Object.keys(checks),
      diagnostics,
    }),
  );
  throw new Error("Composed browser acceptance failed (" + error.name + ")");
} finally {
  await browser.close();
}
