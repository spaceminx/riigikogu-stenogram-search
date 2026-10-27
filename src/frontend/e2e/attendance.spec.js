import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";

const statsRequests = (mock) =>
  mock.interceptedRequests.filter((r) => r.pathname === "/attendance/stats");

test.describe("Attendance active-members filter", () => {
  test("is on by default for the current membership and can be turned off", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/kohalolek");
    const checkbox = page.getByLabel(/Ainult praegu aktiivsed Riigikogu liikmed/);
    await expect(checkbox).toBeChecked();
    await expect
      .poll(() => statsRequests(mock).some((r) => r.queryParams.active_only === "true"))
      .toBe(true);

    // The state follows the URL, so wait for it instead of using uncheck()
    await checkbox.click();
    await expect(page).toHaveURL(/[?&]att_active=0/);
    await expect(checkbox).not.toBeChecked();
    await expect.poll(() => statsRequests(mock).at(-1)?.queryParams.active_only).toBeUndefined();

    mock.verifyNoErrors();
  });

  test("does not apply to a past membership", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/kohalolek");
    await page.getByLabel("Periood:").selectOption("14");

    await expect(page.getByLabel(/Ainult praegu aktiivsed/)).toHaveCount(0);
    await expect
      .poll(() => statsRequests(mock).at(-1)?.queryParams)
      .toMatchObject({ membership: "14" });
    expect(statsRequests(mock).at(-1).queryParams.active_only).toBeUndefined();

    mock.verifyNoErrors();
  });
});
