import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { setupApiMock } from "./support/api.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const suggestions = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures/suggest.json"), "utf-8")
);

const suggestRequests = (mock) => mock.interceptedRequests.filter((r) => r.pathname === "/suggest");
const searchRequests = (mock) => mock.interceptedRequests.filter((r) => r.pathname === "/search");

test.describe("Search suggestions", () => {
  test("lists suggestions with counts and picks one with the keyboard", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/otsing");

    const input = page.getByRole("combobox", { name: "Otsingusõna" });
    await input.fill("riigi");

    const listbox = page.getByRole("listbox", { name: "Otsingusõnade soovitused" });
    await expect(listbox).toBeVisible();
    const options = listbox.getByRole("option");
    await expect(options).toHaveCount(suggestions.length);
    await expect(options.first().locator(".suggestion-term")).toHaveText(suggestions[0].term);
    await expect(options.first().locator(".suggestion-count")).toHaveText("6 574 kõnet");
    await expect(input).toHaveAttribute("aria-expanded", "true");

    expect(suggestRequests(mock)).toHaveLength(1);
    expect(suggestRequests(mock)[0].queryParams).toEqual({ prefix: "riigi", limit: "8" });

    await input.press("ArrowDown");
    await input.press("ArrowDown");
    await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");
    await expect(input).toHaveAttribute("aria-activedescendant", "suggestion-option-1");

    // Enter picks the highlighted suggestion instead of submitting the search
    await input.press("Enter");
    await expect(page.locator(".token-pill")).toHaveText([`${suggestions[1].term}×`]);
    await expect(input).toHaveValue("");
    await expect(listbox).toHaveCount(0);
    await expect(input).toBeFocused();
    expect(searchRequests(mock)).toHaveLength(0);

    mock.verifyNoErrors();
  });

  test("picks a suggestion with the mouse and closes the list with Escape", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/otsing");

    const input = page.getByRole("combobox", { name: "Otsingusõna" });
    const listbox = page.getByRole("listbox", { name: "Otsingusõnade soovitused" });

    await input.fill("riigi");
    await expect(listbox).toBeVisible();
    await input.press("Escape");
    await expect(listbox).toHaveCount(0);
    await expect(input).toHaveValue("riigi");
    await expect(page.locator(".token-pill")).toHaveCount(0);

    // Focus reopens the cached list without a new request
    await input.blur();
    await input.focus();
    await expect(listbox).toBeVisible();
    expect(suggestRequests(mock)).toHaveLength(1);

    await listbox.getByRole("option", { name: new RegExp(`^${suggestions[0].term}`) }).click();
    await expect(page.locator(".token-pill")).toHaveText([`${suggestions[0].term}×`]);
    await expect(listbox).toHaveCount(0);

    mock.verifyNoErrors();
  });

  test("does not ask for suggestions for one letter or several words", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/otsing");

    const input = page.getByRole("combobox", { name: "Otsingusõna" });
    await input.fill("r");
    await input.fill("riigi kaitse");
    // Longer than the 200 ms debounce
    await page.waitForTimeout(500);

    expect(suggestRequests(mock)).toHaveLength(0);
    await expect(page.getByRole("listbox")).toHaveCount(0);

    mock.verifyNoErrors();
  });
});
