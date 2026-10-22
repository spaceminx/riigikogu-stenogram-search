import { test, expect } from "@playwright/test";
import { setupApiMock, FIXTURE_IDS } from "./support/api.js";

test.describe("Client-side navigation", () => {
  test("navigates through >= 5 routes without full page reload", async ({ page, isMobile }) => {
    const mock = await setupApiMock(page);

    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    // Mark window object to detect if a full page reload occurs
    await page.evaluate(() => {
      window.__riigivaade_spa_marker = "persisted";
    });

    const verifyNotReloaded = async () => {
      const marker = await page.evaluate(() => window.__riigivaade_spa_marker);
      expect(marker).toBe("persisted");
    };

    const navigateTo = async (path) => {
      if (isMobile) {
        // Open details menu and click link
        const menuTrigger = page.locator(".header-menu-trigger");
        await menuTrigger.click();
        const link = page.locator(`.header-menu-panel a[href="${path}"]`).first();
        await link.click();
      } else {
        const link = page.locator(`nav.nav-links a[href="${path}"]`).first();
        await link.click();
      }
    };

    // 1. Dashboard -> Kohalolek
    await navigateTo("/kohalolek");
    await expect(page).toHaveURL(/\/kohalolek/);
    await expect(page.locator("h1")).toBeVisible();
    await verifyNotReloaded();

    // 2. Kohalolek -> Hääletused
    await navigateTo("/haaletused");
    await expect(page).toHaveURL(/\/haaletused/);
    await expect(page.locator("h1")).toBeVisible();
    await verifyNotReloaded();

    // 3. Hääletused -> Hääletuse detailvaade (Click voting card link)
    const votingLink = page.locator(`a[href="/haaletus/${FIXTURE_IDS.votingUuid}"]`).first();
    await votingLink.click();
    await expect(page).toHaveURL(new RegExp(`/haaletus/${FIXTURE_IDS.votingUuid}`));
    await expect(page.locator("h1")).toBeVisible();
    await verifyNotReloaded();

    // 4. Hääletuse detailvaade -> Andmed ja privaatsus (Footer link)
    await page.locator('footer a[href="/andmed"]').click();
    await expect(page).toHaveURL(/\/andmed/);
    await expect(page.locator("h1")).toBeVisible();
    await verifyNotReloaded();

    // 5. Andmed -> Dashboard / Avaleht (Header brand link)
    await page.locator("header a.brand-lockup").click();
    await expect(page).toHaveURL(/http:\/\/localhost:4173\/?$/);
    await expect(page.locator("h1, h2").first()).toBeVisible();
    await verifyNotReloaded();

    // Verify no unhandled errors or unmatched API calls
    const errorAlert = page.locator('.glass-panel[role="alert"]:has-text("Midagi läks valesti")');
    await expect(errorAlert).toHaveCount(0);
    mock.verifyNoErrors();
  });
});
