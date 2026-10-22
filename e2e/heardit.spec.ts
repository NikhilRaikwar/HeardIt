import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/events", route => route.fulfill({ status: 202, json: { accepted: true } }));
});

test("landing presents the HeardIt experiment and create CTA", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Same Words.*Four Meanings/ })).toBeVisible();
  await expect(page.getByText("Can you hear what an AI voice really means?")).toBeVisible();
  await expect(page.getByRole("link", { name: "Create a listening test" }).first()).toHaveAttribute("href", "/create");
  await expect(page.getByText("0 of 4 Fish Audio samples ready")).toBeVisible();
  await expect(page.getByRole("button", { name: "Curious", exact: true })).toBeDisabled();
  if (page.viewportSize()?.width === 1440) await page.screenshot({ path: "test-results/heardit-landing-desktop.png", fullPage: true });
  if (page.viewportSize()?.width === 375) await page.screenshot({ path: "test-results/heardit-landing-mobile.png", fullPage: true });
});

test("shared listening metadata and Open Graph image use generic copy", async ({ page }) => {
  await page.goto("/t/private-test-id");
  await expect(page).toHaveTitle(/A HeardIt listening experiment/);
  await expect(page.locator('meta[property="og:description"]')).toHaveAttribute(
    "content",
    "Listen or read the same words, then choose the interpretation that fits best.",
  );
  const imageUrl = await page.locator('meta[property="og:image"]').getAttribute("content");
  expect(imageUrl).toContain("opengraph-image");
  expect(imageUrl).not.toContain("private sentence");
  expect(imageUrl).not.toContain("voice direction");
  const imageResponse = await page.request.get(imageUrl!);
  expect(imageResponse.ok()).toBeTruthy();
  expect(imageResponse.headers()["content-type"]).toContain("image/png");
});

test("creator explains a plain-text API failure instead of throwing a JSON parse error", async ({ page }) => {
  await page.route("**/api/v1/suggestions", route => route.fulfill({ status: 500, contentType: "text/plain", body: "Internal Server Error" }));
  await page.goto("/create");
  await page.getByRole("button", { name: "AI suggest" }).click();
  await expect(page.locator(".hi-error")).toContainText("unexpected response (HTTP 500)");
});

test("audio listener receives no sentence before voting and sees the intended reading after", async ({ page }) => {
  const sentence = "The private sentence should not appear in an audio condition.";
  await page.addInitScript(() => localStorage.setItem("heardit-participant", "participant-" + "a".repeat(48)));
  const assignmentToken = "signed-assignment-from-server";
  await page.route("**/api/v1/tests/test-a/public**", route => {
    expect(route.request().headers()["x-assignment-token"]).toBe(assignmentToken);
    return route.fulfill({ json: { id: "test-a", condition: "audio", labels: ["Sarcastic", "Pleased", "Annoyed", "Sad"], audio_url: "/api/v1/audio/opaque-audio" } });
  });
  await page.route("**/api/v1/tests/test-a/assignment", route => route.fulfill({ json: { condition: "audio", assignment_token: assignmentToken, creator_preview: false } }));
  await page.route("**/api/v1/tests/test-a/votes", route => {
    expect(route.request().postDataJSON()).toMatchObject({ assignment_token: assignmentToken, selected_label: "Sarcastic" });
    expect(route.request().postDataJSON()).not.toHaveProperty("condition");
    return route.fulfill({ json: { submitted: true, intended_label: "Sarcastic", correct: true } });
  });
  await page.route("**/api/v1/audio/opaque-audio", route => route.fulfill({ status: 200, contentType: "audio/mpeg", body: Buffer.from("mocked audio") }));
  await page.goto("/t/test-a");
  await expect(page.getByRole("heading", { name: "What do you hear?" })).toBeVisible();
  if (page.viewportSize()?.width === 1440) await page.screenshot({ path: "test-results/heardit-listener-desktop.png", fullPage: true });
  await expect(page.getByText(sentence)).toHaveCount(0);
  await page.getByRole("button", { name: /Sarcastic/ }).click();
  await page.getByRole("button", { name: "Submit answer" }).click();
  await expect(page.getByText("The creator intended")).toBeVisible();
  if (page.viewportSize()?.width === 1440) await page.screenshot({ path: "test-results/heardit-listener-reveal-desktop.png", fullPage: true });
  await expect(page.locator(".hi-reveal b").first()).toHaveText("Sarcastic");
  await expect(page.getByRole("button", { name: /Share test/ })).toBeVisible();
});

test("text condition receives sentence but not audio URL, and results render explicit zero-vote states", async ({ page }) => {
  const sentence = "I thought you would be here by now.";
  await page.addInitScript(() => { localStorage.setItem("heardit-participant", "participant-" + "b".repeat(48)); });
  await page.route("**/api/v1/tests/test-b/assignment", route => route.fulfill({ json: { condition: "text", assignment_token: "signed-text-assignment", creator_preview: false } }));
  await page.route("**/api/v1/tests/test-b/public**", route => route.fulfill({ json: { id: "test-b", condition: "text", sentence, labels: ["Pleased", "Sarcastic", "Worried", "Annoyed"] } }));
  await page.route("**/api/v1/tests/test-b/results", route => route.fulfill({ json: {
    id: "test-b", intended_label: "Sarcastic", labels: ["Sarcastic", "Pleased", "Worried", "Annoyed"], total: 0,
    audio: { n: 0, correct: 0, rate: null, interval: null, distribution: { Sarcastic: 0, Pleased: 0, Worried: 0, Annoyed: 0 } },
    text: { n: 0, correct: 0, rate: null, interval: null, distribution: { Sarcastic: 0, Pleased: 0, Worried: 0, Annoyed: 0 } },
    voice_lift: null, preliminary: true,
  } }));
  await page.goto("/t/test-b");
  await expect(page.getByText(sentence)).toBeVisible();
  await expect(page.locator("audio")).toHaveCount(0);
  await page.evaluate(() => localStorage.setItem("heardit-owner-test-b", "private-test-token"));
  await page.goto("/r/test-b", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Preliminary results")).toBeVisible();
  await expect(page.getByText("Insufficient data").first()).toBeVisible();
  await expect(page.getByText("Not enough data")).toBeVisible();
  if (page.viewportSize()?.width === 1440) await page.screenshot({ path: "test-results/heardit-results-desktop.png", fullPage: true });
});

test("creator generates, reviews, and publishes a test through the staged journey", async ({ page }) => {
  await page.route("**/api/v1/audio/generate", route => route.fulfill({ json: { audio_id: "saved-audio", url: "/api/v1/audio/saved-audio", cached: false, model: "s2.1-pro-free", direction: "[curious]", voice: "fish-account-default-v1", created_at: "2026-10-22T00:00:00Z" } }));
  await page.route("**/api/v1/tests**", route => {
    if (route.request().method() !== "POST") return route.continue();
    const headers = route.request().headers();
    const headerNames = Object.keys(headers).map(name => name.toLowerCase());
    expect(headerNames).toContain("idempotency-key");
    expect(Object.entries(headers).find(([name]) => name.toLowerCase() === "idempotency-key")?.[1]).toMatch(/^[A-Za-z0-9-]{16,}$/);
    return route.fulfill({ status: 201, json: { id: "published-test", status: "published", management_token: "private-token" } });
  });
  await page.route("**/api/v1/tests/published-test/creator", route => route.fulfill({ json: { id: "published-test", sentence: "I thought you said you’d be here by now.", intended_label: "Curious", distractors: ["Annoyed", "Hurt", "Playful"], direction: "[curious, slightly surprised, gentle tone]", model: "s2.1-pro-free", audio_id: "saved-audio", created_at: "2026-10-22T00:00:00Z", status: "published" } }));
  await page.route("**/api/v1/audio/saved-audio", route => route.fulfill({ status: 200, contentType: "audio/mpeg", body: Buffer.from("mock audio") }));
  await page.goto("/create");
  await expect(page.getByRole("heading", { name: "Create a listening test" })).toBeVisible();
  if (page.viewportSize()?.width === 1440) await page.screenshot({ path: "test-results/heardit-create-desktop.png", fullPage: true });
  if (page.viewportSize()?.width === 375) await page.screenshot({ path: "test-results/heardit-create-mobile.png", fullPage: true });
  await page.getByRole("button", { name: /Generate voice/ }).click();
  await expect(page.getByRole("heading", { name: "Your voice is ready" })).toBeVisible({ timeout: 15_000 });
  if (page.viewportSize()?.width === 1440) await page.screenshot({ path: "test-results/heardit-generate-desktop.png", fullPage: true });
  await expect(page.getByText("s2.1-pro-free").first()).toBeVisible();
  await page.getByRole("button", { name: /Continue to review/ }).click();
  await expect(page.getByRole("heading", { name: "Review your test" })).toBeVisible();
  if (page.viewportSize()?.width === 1440) await page.screenshot({ path: "test-results/heardit-review-desktop.png", fullPage: true });
  const publishedResponse = page.waitForResponse(response => response.url().endsWith("/api/v1/tests") && response.request().method() === "POST");
  await page.getByRole("button", { name: /Publish test/ }).click();
  expect((await publishedResponse).status()).toBe(201);
  await expect(page.locator(".hi-error")).toHaveCount(0);
  await expect(page).toHaveURL(/\/created\/published-test$/, { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Your test is live." })).toBeVisible();
  if (page.viewportSize()?.width === 1440) await page.screenshot({ path: "test-results/heardit-share-desktop.png", fullPage: true });
  await expect(page.getByRole("link", { name: /Open listening test/ })).toHaveAttribute("href", "/t/published-test");
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  const privateLinkButton = page.getByRole("button", { name: "Copy private link" });
  await privateLinkButton.click();
  const privateLink = await page.evaluate(() => navigator.clipboard.readText());
  expect(new URL(privateLink).search).toBe("");
  expect(new URL(privateLink).hash).toContain("management_token=private-token");
  await expect(page.getByRole("button", { name: "Copied once" })).toBeDisabled();
});

test("private results links consume their fragment and do not retain the capability in the URL", async ({ page }) => {
  await page.route("**/api/v1/tests/fragment-results/results", route => {
    expect(route.request().headers()["x-management-token"]).toBe("fragment-capability");
    return route.fulfill({ json: { id: "fragment-results", intended_label: "Curious", labels: ["Curious", "Annoyed", "Hurt", "Playful"], total: 0, audio: { n: 0, correct: 0, rate: null, interval: null, distribution: { Curious: 0, Annoyed: 0, Hurt: 0, Playful: 0 } }, text: { n: 0, correct: 0, rate: null, interval: null, distribution: { Curious: 0, Annoyed: 0, Hurt: 0, Playful: 0 } }, voice_lift: null, preliminary: true, interpretation: "Insufficient data." } });
  });
  await page.goto("/r/fragment-results#management_token=fragment-capability");
  await expect(page.getByRole("heading", { name: "What people heard." })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.location.hash)).toBe("");
  await expect(page.getByText("Results are private to the creator.")).toHaveCount(0);
});

test("product funnel events sent to FastAPI contain only safe allowlisted properties", async ({ page }) => {
  const received: { event: string; properties: Record<string, unknown> }[] = [];
  await page.route("**/api/v1/events", async route => {
    received.push(route.request().postDataJSON());
    await route.fulfill({ status: 202, json: { accepted: true } });
  });
  await page.goto("/");
  await expect.poll(() => received.some(value => value.event === "landing_viewed")).toBe(true);
  for (const value of received) {
    expect(Object.keys(value.properties)).not.toContain("sentence");
    expect(Object.keys(value.properties)).not.toContain("direction");
    expect(Object.keys(value.properties)).not.toContain("management_token");
    expect(Object.keys(value.properties)).not.toContain("assignment_token");
    expect(Object.keys(value.properties)).not.toContain("participant_id");
  }
});

test("admin metrics require a private key and establish an HTTP-only expiring session", async ({ page, context }) => {
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "HeardIt metrics" })).toBeVisible();
  await page.getByLabel("Admin key").fill("incorrect-key");
  await page.getByRole("button", { name: "Open metrics" }).click();
  await expect(page.getByLabel("Admin key")).toBeVisible();
  expect(await context.cookies()).toEqual([]);

  await page.getByLabel("Admin key").fill("e2e-only-test-key-0123456789abcdef0123456789abcdef");
  await page.getByRole("button", { name: "Open metrics" }).click();
  await expect(page.getByText(/Counts come from MongoDB/)).toBeVisible();
  const session = (await context.cookies()).find(cookie => cookie.name === "heardit-admin-session");
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe("Strict");
  expect(session?.expires).toBeGreaterThan(Date.now() / 1000);
});

test("creator opens a labelled read-only preview without entering the listener experiment", async ({ page }) => {
  let assignments = 0;
  let votes = 0;
  await page.addInitScript(() => localStorage.setItem("heardit-owner-preview-test", "creator-capability"));
  await page.route("**/api/v1/tests/preview-test/creator", route => {
    expect(route.request().headers()["x-management-token"]).toBe("creator-capability");
    return route.fulfill({ json: { id: "preview-test", sentence: "This stays in the creator preview.", intended_label: "Curious", distractors: ["Annoyed", "Hurt", "Playful"], audio_id: "preview-audio" } });
  });
  await page.route("**/api/v1/tests/preview-test/assignment", route => { assignments++; return route.abort(); });
  await page.route("**/api/v1/tests/preview-test/votes", route => { votes++; return route.abort(); });
  await page.route("**/api/v1/audio/preview-audio", route => route.fulfill({ status: 200, contentType: "audio/mpeg", body: Buffer.from("mock audio") }));
  await page.goto("/t/preview-test");
  await expect(page.getByRole("heading", { name: "Preview your listening test" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("No listener assignment or vote is recorded");
  await expect(page.getByRole("button", { name: "Submit answer" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "View private results" })).toHaveAttribute("href", "/r/preview-test");
  expect(assignments).toBe(0);
  expect(votes).toBe(0);
});

test("private results loading status stays centered while results are pending", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("heardit-owner-pending-results", "creator-capability"));
  await page.route("**/api/v1/tests/pending-results/results", () => new Promise<void>(() => undefined));
  await page.goto("/r/pending-results");
  const loader = page.locator(".hi-page-loading > div");
  await expect(loader).toContainText("Loading results");
  const bounds = await loader.boundingBox();
  const viewport = page.viewportSize();
  expect(bounds).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(Math.abs(bounds!.x + bounds!.width / 2 - viewport!.width / 2)).toBeLessThan(3);
});
