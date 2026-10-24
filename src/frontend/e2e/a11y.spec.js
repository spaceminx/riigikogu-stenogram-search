import { test, expect } from "@playwright/test";
import { setupApiMock, FIXTURE_IDS } from "./support/api.js";

test.describe("Accessibility basics", () => {
  test("the search tab is the current page only on the dashboard and search", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "the desktop navigation is hidden on mobile");
    const mock = await setupApiMock(page);
    const searchTab = page.locator("nav.nav-links a", { hasText: "Kõneotsing" });

    await page.goto("/otsing");
    await expect(searchTab).toHaveAttribute("aria-current", "page");

    await page.goto(`/saadik/${FIXTURE_IDS.personUuid}`);
    await expect(page.locator(".person-view-container")).toBeVisible();
    await expect(searchTab).not.toHaveAttribute("aria-current", "page");

    mock.verifyNoErrors();
  });

  test("text filters have an accessible name, not only a placeholder", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/haaletused");
    await expect(
      page.getByRole("textbox", { name: "Otsi hääletuse või eelnõu nime järgi" })
    ).toBeVisible();

    await page.goto(`/haaletus/${FIXTURE_IDS.votingUuid}`);
    await expect(page.getByRole("textbox", { name: "Otsi saadiku nime järgi" })).toBeVisible();

    mock.verifyNoErrors();
  });
});
