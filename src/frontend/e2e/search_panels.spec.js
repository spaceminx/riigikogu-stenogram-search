import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";

const count = (mock, pathname) =>
  mock.interceptedRequests.filter((r) => r.pathname === pathname).length;

test("search loads the timeline and speaker data only when their panels are opened", async ({
  page,
}) => {
  const mock = await setupApiMock(page);

  await page.goto("/otsing?q=kliima");
  await expect(page.locator(".speech-card").first()).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(count(mock, "/search")).toBeGreaterThan(0);
  expect(count(mock, "/search/activity")).toBe(0);
  expect(count(mock, "/search/speakers")).toBe(0);

  await page.getByRole("button", { name: "Näita ajajoont" }).click();
  await expect.poll(() => count(mock, "/search/activity")).toBe(1);

  await page.getByRole("button", { name: "Näita kõnelejaid" }).click();
  await expect.poll(() => count(mock, "/search/speakers")).toBe(1);

  // Closing and reopening with the same query does not fetch again
  await page.getByRole("button", { name: "Peida ajajoon" }).click();
  await page.getByRole("button", { name: "Näita ajajoont" }).click();
  await page.waitForLoadState("networkidle");
  expect(count(mock, "/search/activity")).toBe(1);

  mock.verifyNoErrors();
});
