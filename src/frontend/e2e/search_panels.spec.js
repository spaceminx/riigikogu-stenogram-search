import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";

const count = (mock, pathname) =>
  mock.interceptedRequests.filter((r) => r.pathname === pathname).length;

test("search always shows the timeline and speakers, without toggle buttons", async ({ page }) => {
  const mock = await setupApiMock(page);

  await page.goto("/otsing?q=kliima");
  await expect(page.locator(".speech-card").first()).toBeVisible();
  await expect(page.locator(".search-panels-grid .recharts-surface").first()).toBeVisible();
  await expect(page.locator(".search-panels-grid .speaker-item")).toHaveCount(20);
  await expect(page.getByRole("button", { name: /ajajoon|kõnelejai?d/i })).toHaveCount(0);
  await page.waitForLoadState("networkidle");
  expect(count(mock, "/search/activity")).toBe(1);
  expect(count(mock, "/search/speakers")).toBe(1);

  // Sorting does not fetch the panels again
  await page.locator("#search-sort-select").selectOption("date_asc");
  await expect(page).toHaveURL(/sort=date_asc/);
  await page.waitForLoadState("networkidle");
  expect(count(mock, "/search/activity")).toBe(1);
  expect(count(mock, "/search/speakers")).toBe(1);

  mock.verifyNoErrors();
});

test("the speaker box says so when no speakers match", async ({ page }) => {
  const mock = await setupApiMock(page);
  await page.route("**/search/speakers*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "access-control-allow-origin": "*" },
      body: JSON.stringify({ speakers: [] }),
    })
  );

  await page.goto("/otsing?q=kliima");
  await expect(page.locator(".search-panels-grid .members-panel")).toContainText(
    "Otsingule vastavaid kõnelejaid ei leitud."
  );

  mock.verifyNoErrors();
});
