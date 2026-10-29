import { test, expect } from "@playwright/test";
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
  for (const width of [641, 700, 720, 760]) {
    test(`the four nav links fit at ${width}px`, async ({ page }) => {
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
      // One line of the tagline; a wrapped one is at least two font sizes tall
      expect(height).toBeLessThan(fontSize * 2);
      expect(overflow).toBe(false);
      await expect(page.locator("nav.nav-links a")).toHaveCount(4);

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

test.describe("Search speakers next to the timeline", { tag: "@desktop-only" }, () => {
  test("side by side, the speaker list is as tall as the chart and scrolls inside", async ({
    page,
  }) => {
    await setupApiMock(page);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/otsing?q=kliima");
    await page.getByRole("button", { name: "Näita ajajoont" }).click();
    await page.getByRole("button", { name: "Näita kõnelejaid" }).click();
    await expect(page.locator(".speaker-item")).toHaveCount(20);
    await expect(page.locator(".search-panels-grid .recharts-surface").first()).toBeVisible();

    const measure = () =>
      page.evaluate(() => {
        const [chart, rail] = document.querySelector(".search-panels-grid").children;
        const list = rail.querySelector(".speakers-list");
        const c = chart.getBoundingClientRect();
        const r = rail.getBoundingClientRect();
        return {
          sideBySide: Math.abs(c.top - r.top) < 1,
          chart: c.height,
          rail: r.height,
          scrolls: list.scrollHeight > list.clientHeight,
        };
      });

    // The grid keeps two columns down to 721 px; the old rule only applied from 1025 px
    for (const width of [1280, 1024, 1000, 900, 721]) {
      await page.setViewportSize({ width, height: 900 });
      const sizes = await measure();
      expect(sizes.sideBySide, `${width}px`).toBe(true);
      expect(Math.abs(sizes.rail - Math.max(sizes.chart, 320)), `${width}px`).toBeLessThanOrEqual(
        1
      );
      expect(sizes.scrolls, `${width}px`).toBe(true);
    }

    // Stacked under the chart, the whole list shows
    await page.setViewportSize({ width: 720, height: 900 });
    const stacked = await measure();
    expect(stacked.sideBySide).toBe(false);
    expect(stacked.scrolls).toBe(false);
  });
});

test.describe("Attendance faction names on phones", { tag: "@mobile-only" }, () => {
  test("long faction names stay inside their column", async ({ page }) => {
    await setupApiMock(page);
    await page.goto("/kohalolek?att_tab=factions");
    const table = page.getByRole("region", { name: "Fraktsioonide kohaloleku koondtabel" });
    await expect(table.locator(".faction-title").first()).toBeVisible();

    for (const width of [430, 393, 360, 320]) {
      await page.setViewportSize({ width, height: 850 });
      const overflowing = await table.evaluate((region) =>
        [...region.querySelectorAll("td.att-col-name")]
          .filter((cell) => {
            const range = document.createRange();
            range.selectNodeContents(cell.querySelector(".faction-title"));
            const right = Math.max(...[...range.getClientRects()].map((r) => r.right));
            return right > cell.getBoundingClientRect().right;
          })
          .map((cell) => cell.querySelector(".faction-title").textContent)
      );
      expect(overflowing, `${width}px`).toEqual([]);
    }
  });
});
