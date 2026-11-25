// Stuck states, dead ends, keyboard use and accessibility (audit C-7…C-16 and C-22)
import { test, expect } from "@playwright/test";
import { FIXTURE_IDS, expectLastRequest, setupApiMock } from "./support/api.js";

const addDays = (dateKey, days) => {
  const [y, m, d] = dateKey.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + days));
  return date.toISOString().slice(0, 10);
};

test.describe("Search state", () => {
  test("going back during a search leaves the button usable (C-7)", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.route(/api\.e2e\.test\/search\?/, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2500));
      await route.fallback();
    });
    await page.goto("/otsing");
    const input = page.locator("input.search-input");
    await input.fill("kliima");
    // Enter searches; the button is disabled until the delayed answer
    await input.press("Enter");
    await expect(page).toHaveURL(/q=kliima/);
    await expect(page.locator("button.search-button")).toContainText("Otsin");

    await page.goBack();
    await expect(page).not.toHaveURL(/q=/);
    const button = page.locator("button.search-button");
    await expect(button).not.toContainText("Otsin");
    await expect(button).toBeEnabled();

    mock.verifyNoErrors();
  });

  test("the panels name what they count (C-9)", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/");
    await expect(page.locator(".speaker-count-caption").first()).toContainText("sõnavõttu");
    await expect(page.locator("#members-title")).toHaveText("Kõige rohkem sõnavõtte");

    await page.goto("/otsing?q=kliima");
    await expect(page.locator("#members-title")).toHaveText("Kõige rohkem mainimisi");
    await expect(page.locator(".speaker-count-caption").first()).toContainText(
      "teemakohast mainimist"
    );
    mock.verifyNoErrors();
  });
});

test.describe("Header menu (C-8)", () => {
  test("closes on Escape, on a press outside and on navigation", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/haaletused");
    const menu = page.locator("details.header-menu");
    const trigger = page.locator(".header-menu-trigger");

    await trigger.click();
    await expect(menu).toHaveAttribute("open", "");
    await page.keyboard.press("Escape");
    await expect(menu).not.toHaveAttribute("open", "");
    await expect(trigger).toBeFocused();

    await trigger.click();
    await expect(menu).toHaveAttribute("open", "");
    await page.locator("footer").click({ position: { x: 5, y: 5 } });
    await expect(menu).not.toHaveAttribute("open", "");

    // Back in the browser is navigation too. The menu's own links are for phones; wider screens
    // show the navigation bar instead
    await trigger.click();
    const menuLink = page.locator(".header-menu-panel a.menu-link", { hasText: "Eelnõud" });
    const navLink = page.locator("nav.nav-links a", { hasText: "Eelnõud" });
    await ((await menuLink.isVisible()) ? menuLink : navLink).click();
    await expect(page).toHaveURL(/\/eelnoud/);
    await trigger.click();
    await expect(menu).toHaveAttribute("open", "");
    await page.goBack();
    await expect(page).toHaveURL(/\/haaletused/);
    await expect(menu).not.toHaveAttribute("open", "");

    mock.verifyNoErrors();
  });
});

test.describe("Theme (C-11)", () => {
  test("a stored dark theme applies before the app's code has loaded", async ({ page }) => {
    await setupApiMock(page);
    await page.addInitScript(() => localStorage.setItem("theme", "dark"));
    let release;
    const held = new Promise((resolve) => (release = resolve));
    await page.route(/\/assets\/index-[^/]+\.js$/, async (route) => {
      await held;
      await route.fallback();
    });

    await page.goto("/haaletused", { waitUntil: "commit" });
    await expect
      .poll(() => page.evaluate(() => document.documentElement.dataset.theme ?? null))
      .toBe("dark");
    // React has not drawn anything yet
    expect(await page.locator("#root").innerHTML()).toBe("");

    release();
    await expect(page.locator(".votings-heading")).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });
});

test.describe("Date picker keyboard (C-12)", () => {
  test("one tab stop in the grid, arrows move it, Escape returns to the button", async ({
    page,
  }) => {
    const mock = await setupApiMock(page);
    await page.goto("/haaletused");
    const trigger = page.locator("#date-range-trigger");
    await trigger.click();

    const tabStops = page.locator(".date-range-popover .calendar-day[tabindex='0']");
    await expect(tabStops).toHaveCount(1);
    const start = await tabStops.getAttribute("data-date");
    await tabStops.focus();

    const focusedDate = () =>
      page.evaluate(() => document.activeElement?.getAttribute("data-date") ?? null);
    await page.keyboard.press("ArrowRight");
    await expect.poll(focusedDate).toBe(addDays(start, 1));
    await page.keyboard.press("ArrowDown");
    await expect.poll(focusedDate).toBe(addDays(start, 8));
    await page.keyboard.press("ArrowUp");
    await expect.poll(focusedDate).toBe(addDays(start, 1));
    await expect(tabStops).toHaveCount(1);

    // Past the two months shown, the calendar follows
    const before = await page.locator(".calendar-month-title").first().textContent();
    for (let i = 0; i < 3; i += 1) await page.keyboard.press("PageDown");
    await expect.poll(focusedDate).not.toBe(addDays(start, 1));
    await expect(page.locator(".calendar-month-title").first()).not.toHaveText(before);
    await expect(page.locator(".calendar-day:focus")).toHaveCount(1);

    // Enter picks the day
    const picked = await focusedDate();
    await page.keyboard.press("Enter");
    await expect(trigger).toContainText(
      picked.split("-").reverse().join(".") // DD.MM.YYYY
    );

    await page.keyboard.press("Escape");
    await expect(page.locator(".date-range-popover")).toHaveCount(0);
    await expect(trigger).toBeFocused();

    mock.verifyNoErrors();
  });
});

test.describe("Charts (C-13, C-22)", () => {
  test("the home chart is no keyboard stop and its numbers are in a table", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/");
    await expect(page.locator(".timeline-chart .recharts-surface")).toBeVisible();
    await expect(page.locator(".timeline-chart [tabindex]:not([tabindex^='-'])")).toHaveCount(0);
    await expect(page.locator(".timeline-chart-bars")).toHaveAttribute("aria-hidden", "true");
    const rows = page.locator(".timeline-chart .visually-hidden tbody tr");
    // One row per period of the fixture's overview
    await expect(rows).toHaveCount(20);
    await expect(rows.first().locator("td")).toContainText("sõnavõttu");
    mock.verifyNoErrors();
  });

  test("a page without a chart does not load the chart library", async ({ page }) => {
    const mock = await setupApiMock(page);
    const scripts = [];
    page.on("request", (req) => {
      if (req.resourceType() === "script") scripts.push(new URL(req.url()).pathname);
    });
    await page.goto("/");
    await expect(page.locator(".timeline-chart .recharts-surface")).toBeVisible();
    const chartChunks = scripts.filter((s) => /ActivityBars/.test(s));
    expect(chartChunks).toHaveLength(1);

    scripts.length = 0;
    await page.goto("/haaletused");
    await expect(page.locator(".votings-heading")).toBeVisible();
    expect(scripts.filter((s) => /ActivityBars|PersonYearChart/.test(s))).toEqual([]);
    mock.verifyNoErrors();
  });
});

test.describe("Accessibility gaps (C-14)", () => {
  test("a skip link is the first stop and moves focus past the header", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/haaletused");
    await expect(page.locator(".votings-heading")).toBeVisible();
    await page.keyboard.press("Tab");
    const skip = page.locator(".skip-link");
    await expect(skip).toBeFocused();
    await expect(skip).toBeInViewport();
    await page.keyboard.press("Enter");
    await expect(page.locator("#sisu")).toBeFocused();
    await expect(page).not.toHaveURL(/#sisu/);
    mock.verifyNoErrors();
  });

  test("the result counts are announced", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/haaletused");
    await expect(page.locator(".votings-heading [aria-live='polite']")).toContainText("tulemus");
    await page.goto("/eelnoud");
    await expect(page.locator(".votings-heading [aria-live='polite']")).toContainText("eelnõu");
    await page.goto(`/haaletus/${FIXTURE_IDS.votingUuid}`);
    await expect(page.locator("#members-heading [aria-live='polite']")).toContainText("/");
    mock.verifyNoErrors();
  });

  test("the page does not scroll behind an open modal", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/haaletused");
    await page.locator("footer .footer-link-btn").click();
    await expect(page.locator(".methodology-scroll")).toBeVisible();
    await expect(page.locator("body")).toHaveCSS("overflow", "hidden");
    await page.keyboard.press("Escape");
    await expect(page.locator(".methodology-scroll")).toHaveCount(0);
    await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
    mock.verifyNoErrors();
  });

  test("small links are at least 24 px targets", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto(`/istung/${FIXTURE_IDS.date}`);
    const anchor = page.locator(".speech-anchor-link").first();
    await expect(anchor).toBeVisible();
    for (const locator of [anchor, page.locator("footer .footer-link-btn")]) {
      const box = await locator.boundingBox();
      expect(box.height).toBeGreaterThanOrEqual(24);
    }
    expect((await anchor.boundingBox()).width).toBeGreaterThanOrEqual(24);
    mock.verifyNoErrors();
  });
});

test.describe("Dead ends (C-15, C-16)", () => {
  test("'Tagasi' on a voting entered directly stays on the site", async ({ page }) => {
    const mock = await setupApiMock(page);
    // An earlier document in the tab: Back would return there, not to the votings list
    await page.goto("/eelnoud");
    await page.goto(`/haaletus/${FIXTURE_IDS.votingUuid}`);
    await page.locator(".back-nav-btn").click();
    await expect(page).toHaveURL(/\/haaletused$/);
    mock.verifyNoErrors();
  });

  test("a page number past the end goes to the last page", async ({ page }) => {
    const mock = await setupApiMock(page);
    // The mock always reports 5429 votings: 109 pages of 50
    await page.goto("/haaletused?page=999");
    await expect(page).toHaveURL(/page=109$/);
    await expectLastRequest(mock, "/votings", { offset: "5400" });
    await expect(page.locator(".votings-list > *").first()).toBeVisible();

    await page.goto(`/saadik/${FIXTURE_IDS.personUuid}?leht=999`);
    await expect(page).not.toHaveURL(/leht=999/);
    await expect(page.locator(".person-speeches-list .speech-card").first()).toBeVisible();
    mock.verifyNoErrors();
  });

  test("a faction the membership does not have is ignored", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/saadikud?sd_faction=Olematu%20fraktsioon");
    await expect(page.locator("#members-faction-select")).toHaveValue("");
    await expect(page.locator(".members-table tbody tr").first()).toBeVisible();
    await expect(page.locator(".members-count")).not.toContainText("Leitud 0");
    mock.verifyNoErrors();
  });
});
