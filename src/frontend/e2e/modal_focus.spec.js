import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { FIXTURE_IDS, setupApiMock } from "./support/api.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const readFixture = (name) => fs.readFileSync(path.join(__dirname, "fixtures", name), "utf-8");

function fulfillJson(route, body) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body,
  });
}

test.describe("Modal focus", () => {
  test("keeps focus in the context modal when the member page re-renders behind it", async ({
    page,
  }) => {
    const mock = await setupApiMock(page);
    await page.route(/api\.e2e\.test\/speeches\/\d+\/context/, (route) =>
      fulfillJson(route, readFixture("speech_context.json"))
    );
    // Hold the faction alignment until the modal is open, so the page re-renders behind it
    let releaseAlignment;
    const alignmentHeld = new Promise((resolve) => (releaseAlignment = resolve));
    let alignmentServed = false;
    await page.route(/api\.e2e\.test\/persons\/[^/]+\/faction-alignment$/, async (route) => {
      await alignmentHeld;
      await fulfillJson(route, readFixture("person_alignment.json"));
      alignmentServed = true;
    });

    await page.goto(`/saadik/${FIXTURE_IDS.personUuid}`);
    await page.locator(".person-speeches-list .speech-card .context-btn").first().click();
    const dialog = page.getByRole("dialog", { name: "Istungi ajajoon ja kontekst" });
    await expect(dialog).toBeVisible();

    const filter = dialog.getByRole("textbox", { name: "Otsi sellest istungist" });
    await filter.click();
    await expect(filter).toBeFocused();

    releaseAlignment();
    await expect.poll(() => alignmentServed).toBe(true);
    await expect(
      page.getByRole("heading", { name: "Hääletamine fraktsiooni enamusega" })
    ).toBeAttached();
    await expect(filter).toBeFocused();

    mock.verifyNoErrors();
  });
});
