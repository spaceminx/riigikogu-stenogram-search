import { test, expect } from "@playwright/test";
import { setupApiMock, FIXTURE_IDS } from "./support/api.js";

const ROUTES = [
  { path: "/", name: "Dashboard" },
  { path: "/otsing", name: "Otsing" },
  { path: `/istung/${FIXTURE_IDS.date}`, name: "Istung" },
  { path: "/kohalolek", name: "Kohalolek" },
  { path: `/kone/${FIXTURE_IDS.speechId}`, name: "Kõne" },
  { path: `/saadik/${FIXTURE_IDS.personUuid}`, name: "Saadik" },
  { path: "/haaletused", name: "Hääletused" },
  { path: `/haaletus/${FIXTURE_IDS.votingUuid}`, name: "Hääletus" },
  { path: `/eelnou/${FIXTURE_IDS.draftUuid}`, name: "Eelnõu" },
  { path: "/andmed", name: "Andmed" },
];

test.describe("Smoke tests for all routes", () => {
  for (const { path, name } of ROUTES) {
    test(`loads ${name} (${path}) without crashes`, async ({ page }) => {
      const mock = await setupApiMock(page);

      await page.goto(path);
      await page.waitForLoadState("domcontentloaded");

      // Verify no ErrorBoundary crashed
      const errorBoundary = page.locator(".error-boundary");
      await expect(errorBoundary).toHaveCount(0);

      // Verify at least one visible heading exists
      const heading = page.locator("h1, h2").first();
      await expect(heading).toBeVisible();

      // Ensure no intercepted errors occurred
      mock.verifyNoErrors();
    });
  }

  test("loads 404 route displaying NotFoundView without crash", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/tundmatu-lehe-aadress");
    await page.waitForLoadState("domcontentloaded");

    const errorBoundary = page.locator(".error-boundary");
    await expect(errorBoundary).toHaveCount(0);

    const heading = page.locator("h1, h2").first();
    await expect(heading).toBeVisible();

    mock.verifyNoErrors();
  });
});
