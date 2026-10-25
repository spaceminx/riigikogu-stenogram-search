import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";
import { ROUTES } from "./support/routes.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const vercelConfig = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../vercel.json"), "utf-8")
);

// The production CSP from vercel.json, pointed at the fixture API host.
// upgrade-insecure-requests is left out because the fixture API is plain http.
const productionCsp = vercelConfig.headers
  .flatMap((entry) => entry.headers)
  .find((header) => header.key === "Content-Security-Policy").value;
const testCsp = productionCsp
  .replace("https://api.riigivaade.me", "http://api.e2e.test")
  .replace(/;\s*upgrade-insecure-requests/, "");

test.describe("Content Security Policy", () => {
  for (const { path: routePath, name, contentSelector } of ROUTES) {
    test(`${name} (${routePath}) loads without CSP violations`, async ({ page }) => {
      const mock = await setupApiMock(page);

      await page.route("**/*", async (route) => {
        if (route.request().resourceType() !== "document") {
          return route.fallback();
        }
        const response = await route.fetch();
        return route.fulfill({
          response,
          headers: { ...response.headers(), "content-security-policy": testCsp },
        });
      });

      await page.goto(routePath);
      await page.waitForLoadState("networkidle");
      await expect(page.locator(contentSelector).first()).toBeVisible({ timeout: 10000 });
      await page.evaluate(() => document.fonts.ready);

      mock.verifyNoErrors();
    });
  }
});
