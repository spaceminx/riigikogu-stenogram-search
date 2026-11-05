import { test, expect } from "@playwright/test";
import fs from "node:fs";
import { setupApiMock } from "./support/api.js";
import { ROUTES } from "./support/routes.js";

test.describe("Mobile viewport 390px layout", { tag: "@mobile-only" }, () => {
  test.use({ viewport: { width: 390, height: 844 } });

  for (const { path, name, contentSelector } of ROUTES) {
    test(`no horizontal scroll on ${name} (${path})`, async ({ page }) => {
      const mock = await setupApiMock(page);

      await page.goto(path);
      // Measure after the lazy route chunk and its data have rendered
      await expect(page.locator(contentSelector).first()).toBeVisible();
      await page.waitForLoadState("networkidle");

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

test.describe("Voting summary wrapping at 390px", { tag: "@mobile-only" }, () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("a wrapped summary line never starts with the separator", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/haaletused");
    await expect(page.locator(".voting-row-summary").first()).toBeVisible();

    // Where the line breaks depends on the numbers and the card width, so try a range of widths
    const lineStarts = await page.evaluate(() => {
      const summary = document.querySelector(".voting-row-summary");
      const range = document.createRange();
      const starts = new Set();
      for (let width = 120; width <= 360; width += 2) {
        summary.style.width = `${width}px`;
        // Leftmost glyph on each rendered line
        const firstByLine = new Map();
        const walker = document.createTreeWalker(summary, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          for (let i = 0; i < node.length; i++) {
            if (!node.data[i].trim()) continue;
            range.setStart(node, i);
            range.setEnd(node, i + 1);
            const rect = range.getBoundingClientRect();
            const line = Math.round(rect.top);
            const current = firstByLine.get(line);
            if (!current || rect.left < current.left) {
              firstByLine.set(line, { left: rect.left, char: node.data[i] });
            }
          }
        }
        for (const start of firstByLine.values()) starts.add(start.char);
      }
      return [...starts];
    });

    expect(lineStarts.length).toBeGreaterThan(1);
    expect(lineStarts).not.toContain("·");

    mock.verifyNoErrors();
  });
});

test.describe("Header between the mobile menu and full width", { tag: "@desktop-only" }, () => {
  for (const width of [641, 700, 720, 721, 736, 760, 761, 785, 800, 801]) {
    test(`the five nav links fit at ${width}px`, async ({ page }) => {
      const mock = await setupApiMock(page);
      await page.setViewportSize({ width, height: 800 });

      await page.goto("/fraktsioonid");
      await expect(page.locator(".faction-card").first()).toBeVisible();

      const tagline = page.locator(".brand-copy > span");
      const { height, fontSize, overflow } = await tagline.evaluate((el) => ({
        height: el.getBoundingClientRect().height,
        fontSize: parseFloat(getComputedStyle(el).fontSize),
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      }));
      // The tagline is hidden or on one line; a wrapped one is at least two font sizes tall
      expect(height).toBeLessThan(fontSize * 2);
      expect(overflow).toBe(false);
      await expect(page.locator("nav.nav-links a")).toHaveCount(5);
      // The last link ends before the menu button
      const [linkRight, menuLeft] = await page.evaluate(() => [
        [...document.querySelectorAll("nav.nav-links a")].pop().getBoundingClientRect().right,
        document.querySelector(".header-menu").getBoundingClientRect().left,
      ]);
      expect(linkRight).toBeLessThanOrEqual(menuLeft);

      mock.verifyNoErrors();
    });
  }
});

test.describe("Search pills wrapping", { tag: "@desktop-only" }, () => {
  test("the input never sits under a word of its own group", async ({ page }) => {
    await setupApiMock(page, { allowConsoleError: true });
    await page.goto("/otsing?q=" + encodeURIComponent("käibemaks, tulumaks, automaks, maksuküür"));
    await expect(page.locator(".token-pill")).toHaveCount(4);

    // The old layout put the last word above a narrow input around 1000–1024 px and at 390 px
    for (const width of [1100, 1024, 1010, 1000, 900, 800, 600, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      const layout = await page.evaluate(() => {
        const pills = [...document.querySelectorAll(".token-pill")];
        const word = pills[pills.length - 1].getBoundingClientRect();
        const input = document.querySelector("input.search-input").getBoundingClientRect();
        const box = document.querySelector(".search-groups-container").getBoundingClientRect();
        return {
          sameLine: Math.abs(input.top - word.top) < 6,
          // On its own line the input starts at the left edge and takes the full width
          ownLine: input.top >= word.bottom && input.left - box.left < 20,
        };
      });
      expect(layout.sameLine || layout.ownLine, `${width}px`).toBe(true);
    }
  });
});

test.describe("Search timeline and speakers", { tag: "@desktop-only" }, () => {
  const measure = (page) =>
    page.evaluate(() => {
      const grid = document.querySelector(".search-panels-grid");
      const [chart, rail] = grid.children;
      const list = rail.querySelector(".speakers-list");
      const g = grid.getBoundingClientRect();
      const c = chart.getBoundingClientRect();
      const r = rail.getBoundingClientRect();
      const plot = chart.querySelector(".timeline-chart").getBoundingClientRect();
      const surface = chart.querySelector(".recharts-surface")?.getBoundingClientRect();
      return {
        sideBySide: Math.abs(c.top - r.top) < 1,
        chartHeight: c.height,
        railHeight: r.height,
        scrolls: list ? list.scrollHeight > list.clientHeight : false,
        // Both panels fill the grid: side by side they share its width, stacked each takes all of it
        fillsGrid:
          Math.abs(c.left - g.left) <= 1 &&
          Math.abs(r.right - g.right) <= 1 &&
          (Math.abs(c.top - r.top) < 1
            ? c.right <= r.left
            : Math.abs(c.width - g.width) <= 1 && Math.abs(r.width - g.width) <= 1),
        chartFits: surface ? Math.abs(surface.width - plot.width) <= 1 : false,
        pageOverflow: document.documentElement.scrollWidth > window.innerWidth,
      };
    });

  const sizesAt = async (page, width) => {
    await page.setViewportSize({ width, height: 900 });
    // The chart follows its container after a resize
    await expect.poll(async () => (await measure(page)).chartFits, `${width}px`).toBe(true);
    return measure(page);
  };

  test("the panels fill the width and the speaker box keeps its size and scrolls", async ({
    page,
  }) => {
    await setupApiMock(page);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/otsing?q=kliima");
    await expect(page.locator(".speaker-item")).toHaveCount(20);
    await expect(page.locator(".search-panels-grid .recharts-surface").first()).toBeVisible();

    // The grid keeps two columns down to 721 px (light-theme.css)
    for (const width of [1280, 1024, 1000, 900, 721]) {
      const sizes = await sizesAt(page, width);
      expect(sizes.sideBySide, `${width}px`).toBe(true);
      expect(sizes.fillsGrid, `${width}px`).toBe(true);
      expect(sizes.pageOverflow, `${width}px`).toBe(false);
      expect(
        Math.abs(sizes.railHeight - Math.max(sizes.chartHeight, 320)),
        `${width}px`
      ).toBeLessThanOrEqual(1);
      expect(sizes.scrolls, `${width}px`).toBe(true);
    }

    // Stacked under the chart, the speaker box keeps one height and scrolls inside
    for (const width of [720, 390, 360]) {
      const sizes = await sizesAt(page, width);
      expect(sizes.sideBySide, `${width}px`).toBe(false);
      expect(sizes.fillsGrid, `${width}px`).toBe(true);
      expect(sizes.pageOverflow, `${width}px`).toBe(false);
      expect(Math.abs(sizes.railHeight - 320), `${width}px`).toBeLessThanOrEqual(1);
      expect(sizes.scrolls, `${width}px`).toBe(true);
    }
  });

  test("the speaker box is the same size with few speakers", async ({ page }) => {
    await setupApiMock(page);
    const fixture = JSON.parse(
      fs.readFileSync(new URL("./fixtures/search_speakers.json", import.meta.url), "utf-8")
    );
    await page.route("**/search/speakers*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "access-control-allow-origin": "*" },
        body: JSON.stringify({ ...fixture, speakers: fixture.speakers.slice(0, 3) }),
      })
    );
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/otsing?q=kliima");
    await expect(page.locator(".speaker-item")).toHaveCount(3);
    await expect(page.locator(".search-panels-grid .recharts-surface").first()).toBeVisible();

    const wide = await sizesAt(page, 1280);
    expect(Math.abs(wide.railHeight - Math.max(wide.chartHeight, 320))).toBeLessThanOrEqual(1);
    const narrow = await sizesAt(page, 390);
    expect(Math.abs(narrow.railHeight - 320)).toBeLessThanOrEqual(1);
  });
});
