import { expect, test, type Page } from "@playwright/test";

async function mockTurnstile(page: Page) {
  await page.addInitScript(() => {
    const mock = {
      render: (_element: HTMLElement, options: { callback: (token: string) => void }) => {
        window.setTimeout(() => options.callback("playwright-turnstile-token"), 1000);
        return "playwright-widget";
      },
      remove: () => undefined,
    };
    Object.defineProperty(window, "turnstile", { configurable: true, value: mock });
  });
}

test("listener sends the Turnstile token before assignment", async ({ page }) => {
  await mockTurnstile(page);
  await page.addInitScript(() => localStorage.setItem("heardit-participant", "listener-" + "a".repeat(48)));
  await page.route("**/api/v1/tests/captcha-listener/assignment", route => {
    expect(route.request().postDataJSON()).toMatchObject({ captcha_token: "playwright-turnstile-token" });
    return route.fulfill({ json: { condition: "audio", assignment_token: "captcha-assignment-token", creator_preview: false } });
  });
  await page.route("**/api/v1/tests/captcha-listener/public**", route => route.fulfill({ json: {
    id: "captcha-listener", condition: "audio", labels: ["Curious", "Annoyed", "Hurt", "Playful"], audio_url: "/api/v1/audio/captcha-audio",
  } }));

  await page.goto("/t/captcha-listener");
  await expect(page.locator(".hi-turnstile")).toBeVisible();
  await expect(page.getByRole("heading", { name: "What do you hear?" })).toBeVisible();
});

test("creator sends a fresh Turnstile token with publish", async ({ page }) => {
  await mockTurnstile(page);
  await page.route("**/api/v1/audio/generate", route => route.fulfill({ json: {
    audio_id: "captcha-audio", url: "/api/v1/audio/captcha-audio", cached: false, model: "s2.1-pro-free",
    direction: "[curious]", voice: "fish-account-default-v1", created_at: "2026-10-23T00:00:00Z",
  } }));
  await page.route("**/api/v1/tests", route => {
    if (route.request().method() !== "POST") return route.continue();
    expect(route.request().postDataJSON()).toMatchObject({ captcha_token: "playwright-turnstile-token" });
    return route.fulfill({ status: 201, json: { id: "captcha-published", status: "published", management_token: "private-test-token" } });
  });

  await page.goto("/create");
  await page.getByRole("button", { name: /Generate voice/ }).click();
  await expect(page.getByRole("heading", { name: "Your voice is ready" })).toBeVisible();
  await page.getByRole("button", { name: /Continue to review/ }).click();
  await expect(page.locator(".hi-turnstile")).toBeVisible();
  await page.getByRole("button", { name: "Publish test" }).click();
  await expect(page).toHaveURL(/\/created\/captcha-published$/);
});
