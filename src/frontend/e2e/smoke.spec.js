import { test, expect } from "@playwright/test";
import { setupApiMock, FIXTURE_IDS } from "./support/api.js";

const ROUTES = [
  { path: "/", name: "Dashboard", contentSelector: ".dashboard-grid" },
  { path: "/otsing", name: "Otsing", contentSelector: ".search-section" },
  { path: `/istung/${FIXTURE_IDS.date}`, name: "Istung", contentSelector: ".speeches-view-title" },
  { path: "/kohalolek", name: "Kohalolek", contentSelector: ".attendance-filter-bar" },
  { path: `/kone/${FIXTURE_IDS.speechId}`, name: "Kõne", contentSelector: ".speech-card" },
  {
    path: `/saadik/${FIXTURE_IDS.personUuid}`,
    name: "Saadik",
    contentSelector: ".person-view-container",
  },
  { path: "/haaletused", name: "Hääletused", contentSelector: ".votings-view-container" },
  {
    path: `/haaletus/${FIXTURE_IDS.votingUuid}`,
    name: "Hääletus",
    contentSelector: ".voting-detail-container",
  },
  { path: `/eelnou/${FIXTURE_IDS.draftUuid}`, name: "Eelnõu", contentSelector: ".reading-card" },
  { path: "/andmed", name: "Andmed", contentSelector: "h1:has-text('Andmed ja privaatsus')" },
];

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
});
