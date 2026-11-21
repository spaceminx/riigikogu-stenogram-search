import { test, expect } from "@playwright/test";
import { setupApiMock, FIXTURE_IDS } from "./support/api.js";

const rows = (page) => page.locator(".members-table tbody tr");
const names = (page) => page.locator(".members-table .members-name-link");

test.describe("Members page", () => {
  test("is reachable from the navigation and lists the current members", async ({
    page,
    isMobile,
  }) => {
    const mock = await setupApiMock(page);

    await page.goto("/");
    if (isMobile) {
      await page.locator(".header-menu-trigger").click();
      await page.locator('.header-menu-panel a[href="/saadikud"]').click();
    } else {
      await page.locator('nav.nav-links a[href="/saadikud"]').click();
    }
    await expect(page).toHaveURL(/\/saadikud$/);
    await expect(page.locator("h1")).toHaveText("Saadikud");
    await expect(rows(page)).toHaveCount(16);
    await expect(page.locator(".members-count")).toHaveText("16 saadikut");
    await expect(names(page).first()).toHaveText("Annely Akkermann");

    mock.verifyNoErrors();
  });

  test("requests no photos from the Riigikogu API", async ({ page }) => {
    // api.riigikogu.ee allows about one request per second per IP; a photo per row got 429s
    const photoRequests = [];
    page.on("request", (req) => {
      if (new URL(req.url()).host === "api.riigikogu.ee") photoRequests.push(req.url());
    });
    const mock = await setupApiMock(page);

    await page.goto("/saadikud?sd_all=1");
    await expect(rows(page)).toHaveCount(19);
    await expect(page.locator(".members-table img")).toHaveCount(0);
    expect(photoRequests).toEqual([]);

    mock.verifyNoErrors();
  });

  test("filters by name, faction and former members, and keeps them in the URL", async ({
    page,
  }) => {
    const mock = await setupApiMock(page);
    await page.goto("/saadikud");
    await expect(rows(page)).toHaveCount(16);

    await page.getByRole("searchbox", { name: "Otsi saadikut nime järgi" }).fill("polluaas");
    await expect(names(page)).toHaveText(["Henn Põlluaas"]);
    await expect(page.locator(".members-count")).toHaveText("Leitud 1 / 16 saadikut");
    await expect(page).toHaveURL(/sd_q=polluaas/);

    await page.getByRole("button", { name: "Tühjenda otsing" }).click();
    await page.getByLabel("Fraktsioon:").selectOption("Eesti 200 fraktsioon");
    await expect(page).toHaveURL(/sd_faction=/);
    const e200 = await names(page).allTextContents();
    expect(e200.length).toBeGreaterThan(0);
    expect(e200).toContain("Züleyxa Izmailova"); // now outside the faction, listed with "varem"

    await page.getByLabel("Fraktsioon:").selectOption("");
    await page.getByLabel("Ainult praegused saadikud").uncheck();
    await expect(rows(page)).toHaveCount(19);
    await expect(page).toHaveURL(/sd_all=1/);
    await expect(
      page.locator("tr", { hasText: "Jüri Ratas" }).locator(".members-former")
    ).toHaveText("varem: Keskerakond");

    mock.verifyNoErrors();
  });

  test("fast typing keeps every letter", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/saadikud");
    await expect(rows(page)).toHaveCount(16);

    // Bound straight to the URL, the input dropped letters typed faster than the router updates
    const box = page.getByRole("searchbox", { name: "Otsi saadikut nime järgi" });
    await box.pressSequentially("henn polluaas", { delay: 0 });
    await expect(box).toHaveValue("henn polluaas");
    await expect(names(page)).toHaveText(["Henn Põlluaas"]);
    await expect(page).toHaveURL(/sd_q=henn\+polluaas/);

    mock.verifyNoErrors();
  });

  test("names link to the members' own pages, where the members link stays active", async ({
    page,
  }) => {
    const mock = await setupApiMock(page);
    await page.goto("/saadikud");
    await expect(names(page).first()).toHaveAttribute(
      "href",
      "/saadik/7655e8d3-b658-49f0-8e09-f6cbc4a2c714"
    );

    await page.goto(`/saadik/${FIXTURE_IDS.personUuid}`);
    await expect(page.locator(".person-view-container")).toBeVisible();
    await expect(page.locator('nav.nav-links a[href="/saadikud"]')).toHaveAttribute(
      "aria-current",
      "page"
    );

    mock.verifyNoErrors();
  });

  test("a past membership lists everyone who served, without the current-only switch", async ({
    page,
  }) => {
    const mock = await setupApiMock(page);
    await page.goto("/saadikud?sd_membership=14");
    await expect(rows(page)).toHaveCount(17);
    await expect(page.getByLabel("Ainult praegused saadikud")).toHaveCount(0);

    mock.verifyNoErrors();
  });
});

test.describe("Filter text inputs", () => {
  // search.css once had ".filter-text-input:hover, .filter-clear-icon-btn { position: absolute;
  // border: none; … }": hovering a filter box restyled it as the clear button and, in a column
  // layout, collapsed it under the pointer
  for (const [path, label] of [
    ["/saadikud", "Otsi saadikut nime järgi"],
    [`/haaletus/${FIXTURE_IDS.votingUuid}`, "Otsi saadiku nime järgi"],
  ]) {
    test(`hovering the box keeps its layout on ${path.split("/")[1]}`, async ({ page }) => {
      const mock = await setupApiMock(page);
      await page.goto(path);
      const input = page.getByLabel(label);
      await expect(input).toBeVisible();
      const before = await input.boundingBox();
      await input.hover();
      const after = await input.evaluate((el) => {
        const cs = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return {
          position: cs.position,
          border: cs.borderTopStyle,
          height: r.height,
          width: r.width,
        };
      });
      expect(after.position).toBe("static");
      expect(after.border).toBe("solid");
      expect(after.height).toBeCloseTo(before.height, 0);
      expect(after.width).toBeCloseTo(before.width, 0);

      mock.verifyNoErrors();
    });
  }
});
