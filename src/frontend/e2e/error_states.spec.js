import { test, expect } from "@playwright/test";
import { FIXTURE_IDS, setupApiMock } from "./support/api.js";

function fulfillJson(route, status, body) {
  return route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(body),
  });
}

test.describe("Error states", () => {
  test("speech page tells a server error apart from a missing speech", async ({ page }) => {
    await setupApiMock(page);
    // Registered after the fixture handler, so these take precedence
    await page.route(/api\.e2e\.test\/speeches\/500500$/, (route) =>
      fulfillJson(route, 500, { detail: "Sisemine viga" })
    );
    await page.route(/api\.e2e\.test\/speeches\/404404$/, (route) =>
      fulfillJson(route, 404, { detail: "Kõnet ei leitud." })
    );

    await page.goto("/kone/500500");
    await expect(page.getByRole("heading", { name: "Kõne laadimine ebaõnnestus" })).toBeVisible();

    await page.goto("/kone/404404");
    await expect(page.getByRole("heading", { name: "Kõnet ei leitud" })).toBeVisible();
  });

  test("a failed search shows the error, not an empty result", async ({ page }) => {
    await setupApiMock(page);
    await page.route(/api\.e2e\.test\/search\?/, (route) =>
      fulfillJson(route, 500, { detail: "Otsing ebaõnnestus" })
    );

    await page.goto("/otsing?q=kliima");
    await expect(page.locator(".error-banner")).toBeVisible();
    await expect(page.getByText("Otsingutingimustele vastavaid kõnesid ei leitud.")).toHaveCount(0);
  });
});

test.describe("Context load errors", () => {
  test("a failed context load on search keeps the results", async ({ page }) => {
    await setupApiMock(page);
    await page.route(/api\.e2e\.test\/speeches\/\d+\/context/, (route) =>
      fulfillJson(route, 500, { detail: "Konteksti viga" })
    );

    await page.goto("/otsing?q=kliima");
    const cards = page.locator(".speeches-list .speech-card");
    await expect(cards.first()).toBeVisible();
    const count = await cards.count();

    await cards.first().locator(".context-btn").click();
    const banner = page.locator(".error-banner");
    await expect(banner).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(cards).toHaveCount(count);

    await banner.getByRole("button", { name: "Sulge veateade" }).click();
    await expect(banner).toHaveCount(0);
    await expect(cards).toHaveCount(count);
  });

  test("a failed context load on a member page is reported", async ({ page }) => {
    await setupApiMock(page);
    await page.route(/api\.e2e\.test\/speeches\/\d+\/context/, (route) =>
      fulfillJson(route, 500, { detail: "Konteksti viga" })
    );

    await page.goto(`/saadik/${FIXTURE_IDS.personUuid}`);
    const cards = page.locator(".person-speeches-list .speech-card");
    await expect(cards.first()).toBeVisible();
    const count = await cards.count();

    await cards.first().locator(".context-btn").click();
    await expect(page.locator(".error-banner")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(cards).toHaveCount(count);
  });
});
