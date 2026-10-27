import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";

const factionRequests = (mock) =>
  mock.interceptedRequests.filter((r) => r.pathname === "/factions");
const card = (page, name) =>
  page.locator(".faction-card", { has: page.getByRole("heading", { name }) });

test.describe("Factions page", () => {
  test("lists the current members of each faction by default", async ({ page, isMobile }) => {
    const mock = await setupApiMock(page);

    await page.goto("/");
    if (isMobile) {
      await page.locator(".header-menu-trigger").click();
      await page.locator('.header-menu-panel a[href="/fraktsioonid"]').click();
    } else {
      await page.locator('nav.nav-links a[href="/fraktsioonid"]').click();
    }
    await expect(page).toHaveURL(/\/fraktsioonid$/);
    await expect(page.locator("h1")).toHaveText("Fraktsioonid");

    // Current and former members come in one request; there is no filter to switch
    await expect(page.getByRole("checkbox")).toHaveCount(0);
    await expect
      .poll(() => factionRequests(mock).at(-1)?.queryParams)
      .toEqual({ membership: "15" });

    await expect(page.locator(".faction-card")).toHaveCount(7);
    await expect(page.locator(".faction-card-title").first()).toHaveText("Reformierakond");
    await expect(card(page, "Reformierakond").locator(".faction-card-count")).toHaveText(
      "4 saadikut"
    );
    await expect(
      card(page, "Reformierakond").locator(":scope > .faction-member-list > .faction-member")
    ).toHaveCount(4);
    await expect(page.locator(".factions-government-line")).toContainText("Valitsus: Michal");
    await expect(page.locator(".factions-seats-line")).toHaveText(
      "Koalitsioonis 7, opositsioonis 6, fraktsiooni mittekuuluvaid 3 · kokku 16 saadikut"
    );
    // Chairs and vice-chairs come first and carry their position
    const e200 = card(page, "Eesti 200");
    await expect(e200.locator(":scope > .faction-member-list .faction-member-name")).toHaveText([
      "Diana Ingerainen",
      "Irja Lutsar",
      "Lauri Hussar",
    ]);
    await expect(e200.locator(":scope > .faction-member-list .faction-leader-tag")).toHaveText([
      "aseesimees",
      "aseesimees",
    ]);
    await expect(card(page, "Keskerakond").locator(".faction-leader-tag")).toHaveText(["esimees"]);
    // A past vice-chair carries no tag on the current list
    await expect(
      card(page, "Reformierakond").locator(".faction-member", { hasText: "Yoko Alender" })
    ).not.toContainText("aseesimees");

    await expect(
      card(page, "Isamaa").getByRole("link", { name: /Fraktsiooni leht riigikogu\.ee-s/ })
    ).toHaveAttribute("href", "https://www.riigikogu.ee/riigikogu/fraktsioonid/isamaa-fraktsioon/");

    mock.verifyNoErrors();
  });

  test("always offers former members in a collapsed section with dates", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/fraktsioonid");
    // Factions with former members in the fixture: Reform, Eesti 200, EKRE, Keskerakond, non-affiliated
    await expect(page.locator(".faction-former")).toHaveCount(5);
    await expect(page.locator(".faction-former[open]")).toHaveCount(0);

    const reform = card(page, "Reformierakond");
    await expect(reform.locator(".faction-card-count")).toHaveText("4 saadikut");
    // Former members are listed only under their own heading
    await expect(reform.locator(":scope > .faction-member-list > .faction-member")).toHaveCount(4);
    const former = reform.locator(".faction-former");
    await expect(former.locator("summary")).toHaveText("Varem selles fraktsioonis (2)");
    await former.locator("summary").click();
    await expect(former.locator(".faction-member")).toHaveCount(2);
    // Every former member shows when they were in the faction
    for (const meta of await former.locator(".faction-member").all()) {
      await expect(meta.locator(".faction-member-meta").last()).toHaveText(/\d{2}\.\d{2}\.\d{4}/);
    }

    mock.verifyNoErrors();
  });

  test("filters factions by government role", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/fraktsioonid");
    await expect(page.locator(".faction-card")).toHaveCount(7);
    await page.getByLabel("Roll:").selectOption("coalition");

    await expect(page).toHaveURL(/[?&]role=coalition/);
    await expect(page.locator(".faction-card-title")).toHaveText(["Reformierakond", "Eesti 200"]);
    // The seat bar still describes the whole parliament
    await expect(page.locator(".factions-seats-line")).toContainText("kokku 16 saadikut");

    await page.getByLabel("Roll:").selectOption("opposition");
    await expect(page.locator(".faction-card")).toHaveCount(4);

    mock.verifyNoErrors();
  });

  test("shows a past membership without government roles", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/fraktsioonid");
    await page.getByLabel("Periood:").selectOption("14");

    // XIV had several governments, so the page shows no single role per faction
    await expect(page.getByLabel("Roll:")).toHaveCount(0);
    await expect(page.locator(".faction-card .faction-badge")).toHaveCount(0);
    await expect
      .poll(() => factionRequests(mock).at(-1)?.queryParams)
      .toMatchObject({ membership: "14" });
    expect(factionRequests(mock).at(-1).queryParams.active_only).toBeUndefined();

    await expect(page.locator(".factions-government-line")).toContainText(
      "Valitsus koosseisu viimasel päeval (09.04.2023): Kallas II"
    );
    await expect(page.locator(".factions-seats")).toHaveCount(0);
    await expect(card(page, "Reformierakond").locator(".faction-card-count")).toHaveText(
      "3 liiget koosseisu jooksul"
    );
    // Positions held during the membership are shown with their dates
    await expect(
      card(page, "Reformierakond").locator(".faction-member", { hasText: "Arto Aas" })
    ).toContainText("aseesimees 04.04.2019–21.05.2019");
    // riigikogu.ee shows only the current members, so a past membership links only to attendance
    await expect(page.getByRole("link", { name: /riigikogu\.ee-s/ })).toHaveCount(0);
    await expect(card(page, "Reformierakond").locator(".faction-card-link")).toHaveAttribute(
      "href",
      "/kohalolek?att_faction=Eesti+Reformierakonna+fraktsioon&att_membership=14"
    );

    mock.verifyNoErrors();
  });
});
