import { test, expect } from "@playwright/test";
import { setupApiMock, FIXTURE_IDS } from "./support/api.js";

const ROUTES = [
  { path: "/", name: "Dashboard" },
  { path: "/otsing", name: "Otsing" },
  { path: `/istung/${FIXTURE_IDS.date}`, name: "Istung" },
  { path: "/kohalolek", name: "Kohalolek" },
  { path: `/kone/${FIXTURE_IDS.speechId}`, name: "Kõne" },
  { path: `/saadik/${FIXTURE_IDS.personUuid}`, name: "Saadik" },
  { path: "/haaletused", name: "Hääletused" },
  { path: `/haaletus/${FIXTURE_IDS.votingUuid}`, name: "Hääletus" },
  { path: `/eelnou/${FIXTURE_IDS.draftUuid}`, name: "Eelnõu" },
  { path: "/andmed", name: "Andmed" },
];

test.describe("Mobile viewport 390px layout", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  for (const { path, name } of ROUTES) {
    test(`no horizontal scroll on ${name} (${path})`, async ({ page }) => {
      const mock = await setupApiMock(page);

      await page.goto(path);
      await page.waitForLoadState("domcontentloaded");

      const isOverflowing = await page.evaluate(() => {
        return (
          document.documentElement.scrollWidth > document.documentElement.clientWidth ||
          document.body.scrollWidth > window.innerWidth
        );
      });

      expect(isOverflowing).toBe(false);

      mock.verifyNoErrors();
    });
  }
});
