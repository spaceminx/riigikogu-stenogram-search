import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";

test.describe("Search pills and query building", () => {
  test("typing a quoted phrase creates a single phrase pill, not multiple tokens", async ({
    page,
  }) => {
    const mock = await setupApiMock(page);

    await page.goto("/otsing");
    await page.waitForLoadState("domcontentloaded");

    const input = page.locator("input.search-input");
    await input.fill('"kliima muutus"');
    await input.press("Enter");

    // Should create a single pill with `"kliima muutus"`
    const pills = page.locator(".token-pill");
    await expect(pills).toHaveCount(1);
    await expect(pills.first()).toContainText('"kliima muutus"');

    // Submitting updates URL query params
    await page.locator("button.search-button").click();
    await expect(page).toHaveURL(/q=%22kliima\+muutus%22|q="kliima muutus"/);

    // Assert the intercepted GET /search request query (q)
    const searchReq = mock.interceptedRequests.find(
      (r) =>
        r.method === "GET" && r.pathname === "/search" && r.queryParams?.q === '"kliima muutus"'
    );
    expect(searchReq).toBeDefined();

    mock.verifyNoErrors();
  });

  test("+JA and +VÕI buttons add clauses and update the URL query string on submit", async ({
    page,
  }) => {
    const mock = await setupApiMock(page);

    await page.goto("/otsing");
    await page.waitForLoadState("domcontentloaded");

    const input = page.locator("input.search-input");
    const andBtn = page.locator("button.and-btn");
    const orBtn = page.locator("button.or-btn");

    // Type first word: kliima
    await input.fill("kliima");
    // Click +JA
    await andBtn.click();
    // Pill for kliima created in group 0
    let pills = page.locator(".token-pill");
    await expect(pills).toHaveCount(1);
    await expect(pills.first()).toContainText("kliima");

    // Type second word: mets and submit
    await input.fill("mets");
    const [searchResponse] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("api.e2e.test/search") && res.url().includes("kliima")
      ),
      page.locator("button.search-button").click(),
    ]);
    expect(searchResponse.status()).toBe(200);

    // Query should serialize as "kliima mets"
    await expect(page).toHaveURL(/q=kliima\+mets|q=kliima%20mets/);
    pills = page.locator(".token-pill");
    await expect(pills).toHaveCount(2);

    // Assert intercepted GET /search request for +JA
    const andReq = mock.interceptedRequests.find(
      (r) => r.method === "GET" && r.pathname === "/search" && r.queryParams?.q === "kliima mets"
    );
    expect(andReq).toBeDefined();

    // Now click +VÕI
    await orBtn.click();
    const orDividers = page.locator(".or-divider");
    await expect(orDividers).toHaveCount(1);
    await expect(orDividers.first()).toHaveText("VÕI");

    mock.verifyNoErrors();
  });

  test("+VÕI search query is intercepted correctly on submit", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/otsing?q=kliima%2C+mets");
    await page.waitForLoadState("networkidle");

    const searchReq = mock.interceptedRequests.find(
      (r) => r.method === "GET" && r.pathname === "/search" && r.queryParams?.q === "kliima, mets"
    );
    expect(searchReq).toBeDefined();

    mock.verifyNoErrors();
  });

  test("removing a pill updates the state", async ({ page }) => {
    const mock = await setupApiMock(page);

    // Start with a URL containing two words
    await page.goto("/otsing?q=kliima+mets");
    await page.waitForLoadState("domcontentloaded");

    const pills = page.locator(".token-pill");
    await expect(pills).toHaveCount(2);

    // Remove the first pill
    const removeBtn = pills.first().locator("button");
    await removeBtn.click();

    await expect(pills).toHaveCount(1);
    await expect(pills.first()).toContainText("mets");

    mock.verifyNoErrors();
  });

  test("on 390px mobile viewport, the search-bar does not break layout or overflow", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const mock = await setupApiMock(page);

    await page.goto("/otsing?q=%22kliima+muutus%22");
    await page.waitForLoadState("domcontentloaded");

    const searchRow = page.locator(".search-query-row");
    await expect(searchRow).toBeVisible();

    // Check no horizontal document scroll
    const isOverflowing = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(isOverflowing).toBe(false);

    mock.verifyNoErrors();
  });
});
