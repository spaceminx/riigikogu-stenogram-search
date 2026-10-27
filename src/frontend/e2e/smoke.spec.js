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

      // One main heading per page
      await expect(page.locator("h1")).toHaveCount(1);

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

  test("votings list keeps technical votings, with no switch to hide them", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/haaletused");
    await expect(page.locator(".voting-row-link").first()).toBeVisible();

    // The API includes technical votings by default; the list must not ask it to drop them
    const listRequests = mock.interceptedRequests.filter((r) => r.pathname === "/votings");
    expect(listRequests.length).toBeGreaterThan(0);
    for (const request of listRequests) {
      expect(request.queryParams.include_technical).toBeUndefined();
    }
    await expect(page.getByText("Näita tehnilisi kirjeid")).toHaveCount(0);

    mock.verifyNoErrors();
  });

  test("faction alignment panel stays when a membership has no comparable votes", async ({
    page,
  }) => {
    const mock = await setupApiMock(page);
    // A member who sat in XV only as non-affiliated: nothing to compare with a faction majority
    await page.route(
      (url) =>
        url.pathname.endsWith("/faction-alignment") && url.searchParams.get("membership") === "15",
      (route) =>
        route.fulfill({
          json: {
            same: 0,
            different: 0,
            share_same: null,
            excluded: { absent: 0, split: 0, too_few: 0, no_faction: 668 },
            by_membership: [
              { membership: 15, same: 0, different: 0, share_same: null },
              { membership: 14, same: 386, different: 116, share_same: 76.9 },
            ],
          },
        })
    );

    await page.goto(`/saadik/${FIXTURE_IDS.personUuid}`);
    const panel = page.getByRole("region", { name: "Hääletamine fraktsiooni enamusega" });
    await expect(panel).toBeVisible();

    await panel.getByRole("button", { name: "XV Riigikogu" }).click();
    await expect(panel.getByText("Selles koosseisus pole hääletusi")).toBeVisible();
    await expect(panel.getByText("668 fraktsioonita")).toBeVisible();

    await panel.getByRole("button", { name: "Kõik koosseisud" }).click();
    await expect(panel.getByText("Hääletas samamoodi kui fraktsiooni enamus")).toBeVisible();

    mock.verifyNoErrors();
  });
});
