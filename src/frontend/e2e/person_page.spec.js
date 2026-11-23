import { test, expect } from "@playwright/test";
import { FIXTURE_IDS, setupApiMock } from "./support/api.js";

const PERSON_URL = `/saadik/${FIXTURE_IDS.personUuid}`;

function fulfillJson(route, status, body) {
  return route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(body),
  });
}

test.describe("Member page", () => {
  test("paging the speeches keeps the speech list in view (C-2)", async ({ page }) => {
    await setupApiMock(page);
    await page.goto(PERSON_URL);
    const list = page.locator('section[aria-label="Saadiku kõnede loend"]');
    const next = list.getByRole("button", { name: /Järgmine/ });
    await next.scrollIntoViewIfNeeded();
    await next.click();

    await expect(page).toHaveURL(/leht=2/);
    await expect
      .poll(() => list.evaluate((el) => Math.round(el.getBoundingClientRect().top)))
      .toBeLessThan(50);
    expect(await list.evaluate((el) => el.getBoundingClientRect().top)).toBeGreaterThan(-50);
  });

  test("a late 'Näita rohkem' answer is not added to another membership (C-4)", async ({
    page,
  }) => {
    await setupApiMock(page);
    let releaseLate;
    const lateHeld = new Promise((resolve) => (releaseLate = resolve));
    let lateServed = false;
    await page.route(
      /api\.e2e\.test\/persons\/[^/]+\/faction-alignment\/differences\?.*offset=10/,
      async (route) => {
        await lateHeld;
        lateServed = true;
        await fulfillJson(route, 200, {
          total: 176,
          results: Array.from({ length: 10 }, (_, i) => ({
            voting_uuid: `late-${i}`,
            sitting_date: "2019-05-01",
            description: "Hilinenud hääletus",
            member_decision: "POOLT",
            faction_position: "VASTU",
          })),
        });
      }
    );

    await page.goto(PERSON_URL);
    const panel = page.locator('section[aria-label="Hääletamine fraktsiooni enamusega"]');
    await panel.getByRole("button", { name: "Näita rohkem" }).click();
    await panel.getByRole("button", { name: "XV Riigikogu" }).click();
    await expect(panel.getByRole("button", { name: "XV Riigikogu" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    releaseLate();
    await expect.poll(() => lateServed).toBe(true);

    await expect(panel.locator(".alignment-diff-card")).toHaveCount(10);
    await expect(panel.getByText("Hilinenud hääletus")).toHaveCount(0);
  });

  test("a failed alignment request says so and can be retried (C-6)", async ({ page }) => {
    await setupApiMock(page, { allowConsoleError: true });
    let fail = true;
    await page.route(/api\.e2e\.test\/persons\/[^/]+\/faction-alignment(\?.*)?$/, (route) =>
      fail ? fulfillJson(route, 500, { detail: "Sisemine viga" }) : route.fallback()
    );

    await page.goto(PERSON_URL);
    const panel = page.locator('section[aria-label="Hääletamine fraktsiooni enamusega"]');
    await expect(
      panel.getByText("Fraktsiooniga hääletamise andmete laadimine ebaõnnestus.")
    ).toBeVisible();

    fail = false;
    await panel.getByRole("button", { name: "Proovi uuesti" }).click();
    await expect(panel.getByText("Hääletas samamoodi kui fraktsiooni enamus")).toBeVisible();
  });

  test("the alignment panel states the 'ei hääletanud' rule and links the votes methodology (C-3)", async ({
    page,
  }) => {
    await setupApiMock(page);
    await page.goto(PERSON_URL);
    const panel = page.locator('section[aria-label="Hääletamine fraktsiooni enamusega"]');
    await expect(
      panel.getByText(/hääletamata jätmine \(„ei hääletanud“\) on eraldi seisukoht/)
    ).toBeVisible();

    await panel.getByRole("button", { name: "Loe metoodika kohta" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "2. Hääletused" })).toBeVisible();
    await expect(dialog.getByText(/Salajastel hääletustel nimelisi hääli pole/)).toBeVisible();
  });
});

test.describe("Sitting page", () => {
  test("failed votings are reported instead of disappearing (C-6)", async ({ page }) => {
    await setupApiMock(page, { allowConsoleError: true });
    await page.route(/api\.e2e\.test\/votings\?/, (route) =>
      fulfillJson(route, 500, { detail: "Sisemine viga" })
    );

    await page.goto(`/istung/${FIXTURE_IDS.date}`);
    await expect(page.getByText("Selle istungi hääletuste laadimine ebaõnnestus.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Proovi uuesti" })).toBeVisible();
  });
});
