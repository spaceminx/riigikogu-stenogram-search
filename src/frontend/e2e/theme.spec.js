import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";

test.describe("Theme toggle and contrast check", () => {
  test("persists dark mode in localStorage and keeps it across reloads", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    // Initial theme should be light
    const html = page.locator("html");
    await expect(html).toHaveAttribute("data-theme", "light");

    // Open the header menu details dropdown
    const menuTrigger = page.locator(".header-menu-trigger");
    await menuTrigger.click();

    // Click theme toggle
    const themeBtn = page.locator("button.menu-action[aria-pressed]");
    await themeBtn.click();

    // Should now be dark
    await expect(html).toHaveAttribute("data-theme", "dark");

    // Check localStorage
    const savedTheme = await page.evaluate(() => localStorage.getItem("theme"));
    expect(savedTheme).toBe("dark");

    // Reload and assert dark remains
    await page.reload();
    await page.waitForLoadState("domcontentloaded");
    await expect(html).toHaveAttribute("data-theme", "dark");

    mock.verifyNoErrors();
  });

  test("dark mode key elements pass WCAG AA contrast check (>= 4.5 or >= 3 for large/bold text)", async ({
    page,
  }) => {
    // Set dark theme in localStorage before navigating
    await page.addInitScript(() => {
      localStorage.setItem("theme", "dark");
    });

    const mock = await setupApiMock(page);

    await page.goto("/kohalolek");
    await page.waitForLoadState("domcontentloaded");

    // Wait for html[data-theme="dark"] and disable transitions/animations to prevent timing flakes
    await page.waitForSelector('html[data-theme="dark"]');
    await page.addStyleTag({
      content: "* { transition: none !important; animation: none !important; }",
    });

    // Helper to evaluate element contrast against its effective background
    const getElementContrast = async (selector) => {
      return await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;

        function getLuminance(r, g, b) {
          const [rs, gs, bs] = [r, g, b].map((c) => {
            const s = c / 255;
            return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
          });
          return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
        }

        function parseRgb(colorStr) {
          const m = colorStr.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
          return m ? [parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10)] : null;
        }

        const style = window.getComputedStyle(el);
        const color = parseRgb(style.color);
        if (!color) return null;

        // Traverse up to find first non-transparent background
        let bgEl = el;
        let bgColor = null;
        while (bgEl) {
          const bgStyle = window.getComputedStyle(bgEl);
          const bg = parseRgb(bgStyle.backgroundColor);
          if (bg && bgStyle.backgroundColor !== "rgba(0, 0, 0, 0)") {
            bgColor = bg;
            break;
          }
          bgEl = bgEl.parentElement;
        }

        if (!bgColor) {
          bgColor = [15, 23, 42]; // #0f172a dark default
        }

        const l1 = getLuminance(...color);
        const l2 = getLuminance(...bgColor);
        const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);

        const fontSize = parseFloat(style.fontSize);
        const isBold = parseInt(style.fontWeight, 10) >= 700 || style.fontWeight === "bold";
        const isLarge = fontSize >= 24 || (fontSize >= 18.66 && isBold);

        return {
          ratio,
          isLarge,
          color: style.color,
          bgColor,
        };
      }, selector);
    };

    // Spot-check headings
    const headingInfo = await getElementContrast("h1");
    if (headingInfo) {
      expect(headingInfo.ratio).toBeGreaterThanOrEqual(headingInfo.isLarge ? 3.0 : 4.5);
    }

    // Spot-check nav button elements (.nav-btn and .nav-btn.active)
    const navBtnInfo = await getElementContrast(".nav-btn:not(.active)");
    if (navBtnInfo) {
      expect(navBtnInfo.ratio).toBeGreaterThanOrEqual(navBtnInfo.isLarge ? 3.0 : 4.5);
    }

    const activeNavBtnInfo = await getElementContrast(".nav-btn.active");
    if (activeNavBtnInfo) {
      expect(activeNavBtnInfo.ratio).toBeGreaterThanOrEqual(activeNavBtnInfo.isLarge ? 3.0 : 4.5);
    }

    // Spot-check attendance header / table header
    const thInfo = await getElementContrast(".attendance-table th");
    if (thInfo) {
      expect(thInfo.ratio).toBeGreaterThanOrEqual(thInfo.isLarge ? 3.0 : 4.5);
    }

    mock.verifyNoErrors();
  });
});
