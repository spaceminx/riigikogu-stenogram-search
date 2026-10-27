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

    await expect(page.getByLabel("Ainult praegu aktiivsed saadikud")).toBeChecked();
    await expect
      .poll(() => factionRequests(mock).at(-1)?.queryParams)
      .toMatchObject({ membership: "15", active_only: "true" });

    await expect(page.locator(".faction-card")).toHaveCount(7);
    await expect(page.locator(".faction-card-title").first()).toHaveText("Reformierakond");
    await expect(card(page, "Reformierakond").locator(".faction-card-count")).toHaveText(
      "4 saadikut"
    );
    await expect(card(page, "Reformierakond").locator(".faction-member")).toHaveCount(4);
    await expect(page.locator(".factions-government-line")).toContainText("Valitsus: Michal");
    await expect(page.locator(".factions-seats-line")).toHaveText(
      "Koalitsioonis 7, opositsioonis 6, fraktsiooni mittekuuluvaid 3 · kokku 16 saadikut"
    );
    await expect(page.locator(".faction-former")).toHaveCount(0);

    // Chairs and vice-chairs come first and carry their position
    const e200 = card(page, "Eesti 200");
    await expect(e200.locator(".faction-member-name")).toHaveText([
      "Diana Ingerainen",
      "Irja Lutsar",
      "Lauri Hussar",
    ]);
    await expect(e200.locator(".faction-leader-tag")).toHaveText(["aseesimees", "aseesimees"]);
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

  test("shows former members with dates when the filter is off", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/fraktsioonid");
    const checkbox = page.getByLabel("Ainult praegu aktiivsed saadikud");
    await expect(checkbox).toBeChecked();

    // The state follows the URL, so wait for it instead of using uncheck()
    await checkbox.click();
    await expect(page).toHaveURL(/[?&]fr_active=0/);
    await expect(checkbox).not.toBeChecked();
    await expect.poll(() => factionRequests(mock).at(-1)?.queryParams.active_only).toBeUndefined();

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

  test("shows a past membership without the active filter", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/fraktsioonid");
    await page.getByLabel("Periood:").selectOption("14");

    await expect(page.getByLabel("Ainult praegu aktiivsed saadikud")).toHaveCount(0);
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
