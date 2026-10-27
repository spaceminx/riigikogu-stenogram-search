import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";
import { ROUTES } from "./support/routes.js";

test.describe("Mobile viewport 390px layout", () => {
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

test.describe("Voting summary wrapping at 390px", () => {
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

test.describe("Header between the mobile menu and full width", () => {
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
