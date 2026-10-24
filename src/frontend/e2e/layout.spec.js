import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";
import { ROUTES } from "./support/routes.js";

test.describe("Mobile viewport 390px layout", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  for (const { path, name, contentSelector } of ROUTES) {
    test(`no horizontal scroll on ${name} (${path})`, async ({ page }) => {
      const mock = await setupApiMock(page);

      await page.goto(path);
      // Measure after the lazy route chunk and its data have rendered
      await expect(page.locator(contentSelector).first()).toBeVisible();
      await page.waitForLoadState("networkidle");

      const isOverflowing = await page.evaluate(() => {
        return (
          document.documentElement.scrollWidth > document.documentElement.clientWidth ||
          document.body.scrollWidth > window.innerWidth
        );
      });

      expect(isOverflowing).toBe(false);

      mock.verifyNoErrors();
    });
  }
});
