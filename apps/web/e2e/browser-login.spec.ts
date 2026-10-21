import { test, expect, type Page } from "@playwright/test";

const csrf = "x".repeat(43);
async function setup(page: Page, seconds = 300) {
  await page.route("**/auth/config", (route) =>
    route.fulfill({ json: { mode: "browser-session" } }),
  );
  await page.route("**/auth/session", (route) =>
    route.fulfill({
      json: {
        csrf_token: csrf,
        expires_at: Math.floor(Date.now() / 1000) + seconds,
      },
    }),
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    expect(route.request().headers()["authorization"]).toBeUndefined();
    if (path === "/api/me")
      return route.fulfill({
        json: {
          tenant: "Fictional review team",
          actor: "synthetic-alice",
          role: "reviewer",
          authentication: "managed-access-token",
        },
      });
    if (path === "/api/execution-options")
      return route.fulfill({ json: { model: { enabled: false } } });
    return route.fulfill({ json: [] });
  });
}

test("cookie mode omits bearer credentials, sends CSRF on writes and confirms logout", async ({
  page,
}) => {
  await setup(page);
  let writes = 0;
  await page.route("**/api/jobs", async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    expect(route.request().headers()["authorization"]).toBeUndefined();
    expect(route.request().headers()["x-atlas-csrf"]).toBe(csrf);
    writes += 1;
    return route.fulfill({
      status: 422,
      json: { detail: "Controlled schema refusal" },
    });
  });
  await page.route("**/api/demo", (route) =>
    route.fulfill({ json: { rfp: {}, knowledge: [] } }),
  );
  await page.route("**/auth/logout", async (route) => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().headers()["x-atlas-csrf"]).toBe(csrf);
    return route.fulfill({ status: 204 });
  });
  await page.goto("/");
  await expect(page.getByLabel("Workspace token")).toHaveCount(0);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByText("Fictional review team · reviewer"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Run seeded demonstration" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Controlled schema refusal",
  );
  expect(writes).toBe(1);
  expect(
    await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
    })),
  ).toEqual({ local: 0, session: 0 });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Signed out of ATLAS");
  await expect(page.getByText("Fictional review team · reviewer")).toHaveCount(
    0,
  );
});

test("expiry unmounts the workspace and a late request cannot restore it", async ({
  page,
}) => {
  await setup(page, 2);
  await page.route("**/api/runs", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    await route
      .fulfill({ json: [{ id: "late-private-run", created: "2026-10-21" }] })
      .catch(() => {});
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in to your workspace" }),
  ).toBeVisible();
  await page.waitForTimeout(2800);
  await expect(
    page.getByRole("button", { name: "Connect", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("late-private-run")).toHaveCount(0);
});

test("membership refusal hides the workspace without claiming server logout", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/api/me", (route) =>
    route.fulfill({ status: 403, json: { detail: "Membership revoked" } }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Workspace access ended");
  await expect(
    page.getByRole("button", { name: "Connect", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Retry sign-out" }),
  ).toBeVisible();
});

test("failed logout hides source text and offers an honest retry", async ({
  page,
}) => {
  await setup(page);
  let calls = 0;
  await page.route("**/auth/logout", (route) =>
    route.fulfill({ status: ++calls === 1 ? 503 : 204 }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByText("Fictional review team · reviewer"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Sign-out was not confirmed",
  );
  await expect(page.getByText("Fictional review team · reviewer")).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "Retry sign-out" }).click();
  await expect(page.getByRole("alert")).toContainText("Signed out of ATLAS");
});

test("signed-out mode uses a navigation form and never asks for a token", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/auth/session", (route) =>
    route.fulfill({ status: 401 }),
  );
  await page.goto("/?signin=failed");
  const form = page.locator('form[action="/auth/start"]');
  await expect(form).toHaveAttribute("method", "post");
  await expect(
    form.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Workspace token")).toHaveCount(0);
  await page.screenshot({ path: "../../var/browser-login-ui/signed-out.png" });
});

test("configuration outages fail closed; an explicit absent feature preserves local mode", async ({
  page,
}) => {
  await page.route("**/auth/config", (route) => route.fulfill({ status: 503 }));
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText(
    "Sign-in settings could not be loaded",
  );
  await expect(page.getByLabel("Workspace token")).toHaveCount(0);
  await page.route("**/auth/config", (route) => route.fulfill({ status: 404 }));
  await page.getByRole("button", { name: "Check sign-in" }).click();
  await expect(page.getByLabel("Workspace token")).toBeVisible();
});

test("page policy permits the pinned provider as a direct form target", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/auth/session", (route) =>
    route.fulfill({ status: 401 }),
  );
  await page.route("https://identity.example.invalid/authorize", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<h1>Controlled provider destination</h1>",
    }),
  );
  await page.route(/\/$/, async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      headers: {
        ...response.headers(),
        "content-security-policy":
          "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self' https://identity.example.invalid",
      },
    });
  });
  await page.goto("/");
  // Direct target probes test CSP. They do not simulate the backend's redirect chain.
  await page
    .locator("form")
    .evaluate(
      (form) =>
        ((form as HTMLFormElement).action =
          "https://identity.example.invalid/authorize"),
    );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Controlled provider destination" }),
  ).toBeVisible();
});
