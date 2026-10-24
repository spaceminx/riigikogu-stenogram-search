import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";

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
