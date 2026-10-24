import { test, expect } from "@playwright/test";
import { setupApiMock, FIXTURE_IDS } from "./support/api.js";
import { ROUTES } from "./support/routes.js";

test.describe("Smoke tests for all routes", () => {
  for (const { path, name, contentSelector } of ROUTES) {
    test(`loads ${name} (${path}) without crashes`, async ({ page }) => {
      const mock = await setupApiMock(page);

      await page.goto(path);
      await page.waitForLoadState("networkidle");

      // Wait for route-specific content after lazy chunk & fixture data load
      await expect(page.locator(contentSelector).first()).toBeVisible({ timeout: 10000 });

      // Assert ErrorBoundary alert is not rendered
      const errorAlert = page.locator('.glass-panel[role="alert"]:has-text("Midagi läks valesti")');
      await expect(errorAlert).toHaveCount(0);

      // Ensure no intercepted errors or external requests occurred
      mock.verifyNoErrors();
    });
  }

  test("loads 404 route displaying NotFoundView without crash", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/tundmatu-lehe-aadress");
    await page.waitForLoadState("networkidle");

    // Wait for NotFoundView specific content
    await expect(page.locator("h2:has-text('404 – Lehekülge ei leitud')")).toBeVisible();

    const errorAlert = page.locator('.glass-panel[role="alert"]:has-text("Midagi läks valesti")');
    await expect(errorAlert).toHaveCount(0);

    mock.verifyNoErrors();
  });

  test("person page shows the photo with its credit", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto(`/saadik/${FIXTURE_IDS.personUuid}`);
    await expect(page.locator("img.person-photo")).toBeVisible();
    await expect(page.locator(".person-photo-caption")).toHaveText("Foto: Riigikogu");

    mock.verifyNoErrors();
  });
});
