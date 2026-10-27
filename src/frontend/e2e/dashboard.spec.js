import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { setupApiMock, FIXTURE_IDS } from "./support/api.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const sessionDates = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures", "session_dates.json"), "utf-8")
).dates;

test.describe("Dashboard session calendar and search filters", () => {
  test("session calendar enables session days and opens the selected session", async ({ page }) => {
    // The calendar opens on the current month, so pin the clock to the fixture session date.
    await page.clock.setFixedTime(new Date(`${FIXTURE_IDS.date}T12:00:00`));
    const mock = await setupApiMock(page);

    await page.goto("/");
    await page.getByRole("button", { name: "Ava kalendrivaade" }).click();

    const calendar = page.getByRole("dialog", { name: "Riigikogu istungite kalender" });

    // The popover is position: fixed; an ancestor with a backdrop-filter used to push it off-screen
    const box = await calendar.boundingBox();
    const viewport = page.viewportSize();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);

    const monthPrefix = FIXTURE_IDS.date.slice(0, 7);
    const expectedDays = sessionDates.filter((d) => d.startsWith(monthPrefix)).length;
    const sessionDays = calendar.locator(".calendar-day.has-session:not(.is-outside-month)");
    await expect(sessionDays).toHaveCount(expectedDays);
    await expect(sessionDays.first()).toBeEnabled();

    await calendar.locator(`[aria-describedby$="-${FIXTURE_IDS.date}"]`).click();
    await expect(page).toHaveURL(new RegExp(`/istung/${FIXTURE_IDS.date}$`));
    await expect(page.locator(".speeches-view-title").first()).toBeVisible();

    mock.verifyNoErrors();
  });

  test("exact-match filter on the dashboard is passed to the search", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/");
    await page.locator("input.search-input").fill("kliima");
    await page.getByLabel("Ainult täpne sõna (ilma liitsõnadeta)").check();
    await page.locator("button.search-button").click();

    await expect(page).toHaveURL(/[?&]expand=false/);
    await expect
      .poll(() =>
        mock.interceptedRequests.some(
          (r) => r.pathname === "/search" && r.queryParams.expand === "false"
        )
      )
      .toBe(true);

    mock.verifyNoErrors();
  });

  test("an example topic opens in the search box as OR blocks", async ({ page }) => {
    const mock = await setupApiMock(page);
    // No recorded fixture for this query; any OR search result will do
    const orResults = fs.readFileSync(
      path.join(__dirname, "fixtures", "search_kliima_voi_mets.json"),
      "utf-8"
    );
    await page.route(
      (url) => url.pathname === "/search" && url.searchParams.get("q")?.startsWith("tuulepark"),
      (route) => route.fulfill({ contentType: "application/json", body: orResults })
    );

    await page.goto("/");
    await page.getByRole("button", { name: "Energeetika" }).click();

    await expect(page).toHaveURL(/\/otsing\?q=/);
    const box = page.locator(".search-section");
    await expect(box.locator(".and-group-box")).toHaveCount(4);
    await expect(box.locator(".or-divider")).toHaveCount(3);
    await expect(box.locator(".token-pill")).toHaveText([
      /tuulepark/,
      /tuumajaam/,
      /põlevkivi/,
      /"elektri hind"/,
    ]);

    mock.verifyNoErrors();
  });
});
