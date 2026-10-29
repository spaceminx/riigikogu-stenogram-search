import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { FIXTURE_IDS, setupApiMock } from "./support/api.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const contextBody = fs.readFileSync(path.join(__dirname, "fixtures/speech_context.json"), "utf-8");
const context = JSON.parse(contextBody);

// The search and member page cards are other speeches than the fixture's target,
// so every context request gets the one recorded context
async function serveContext(page) {
  const requests = [];
  await page.route(/api\.e2e\.test\/speeches\/\d+\/context/, (route) => {
    requests.push(new URL(route.request().url()));
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "access-control-allow-origin": "*" },
      body: contextBody,
    });
  });
  return requests;
}

test.describe("Speech context modal", () => {
  test("opens from a search result with the session timeline and the target speech", async ({
    page,
  }) => {
    const mock = await setupApiMock(page);
    const requests = await serveContext(page);

    await page.goto("/otsing?q=kliima");
    const card = page.locator(".speeches-list .speech-card").first();
    await expect(card).toBeVisible();
    const contextBtn = card.locator(".context-btn");
    await contextBtn.click();

    const dialog = page.getByRole("dialog", { name: "Istungi ajajoon ja kontekst" });
    await expect(dialog).toBeVisible();
    expect(requests).toHaveLength(1);
    expect(requests[0].searchParams.get("q")).toBe("kliima");

    await expect(dialog).toContainText(`${context.total_speeches} kõnet/repliiki`);
    const rows = dialog.locator(".transcript-speech-row");
    await expect(rows).toHaveCount(context.speeches.length);

    const target = dialog.locator(".target-speech-highlight");
    await expect(target).toHaveCount(1);
    const targetSpeech = context.speeches.find((s) => s.id === context.target_speech_id);
    await expect(target.locator(".transcript-row-speaker")).toHaveText(targetSpeech.speaker);
    await expect(target.locator(".target-speech-badge")).toHaveText("Otsitud kõne");

    // Filtering inside the modal matches speaker names and text
    const term = "Riisalo";
    const expected = context.speeches.filter((s) =>
      `${s.speaker} ${s.text}`.toLowerCase().includes(term.toLowerCase())
    ).length;
    expect(expected).toBeGreaterThan(0);
    expect(expected).toBeLessThan(context.speeches.length);
    await dialog.getByRole("textbox", { name: "Otsi sellest istungist" }).fill(term);
    await expect(rows).toHaveCount(expected);

    // Escape closes the modal and gives focus back to the button that opened it
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(contextBtn).toBeFocused();

    mock.verifyNoErrors();
  });

  test("opens from a member page and closes with the close button", async ({ page }) => {
    const mock = await setupApiMock(page);
    const requests = await serveContext(page);

    await page.goto(`/saadik/${FIXTURE_IDS.personUuid}`);
    const card = page.locator(".person-speeches-list .speech-card").first();
    await expect(card).toBeVisible();
    await card.locator(".context-btn").click();

    const dialog = page.getByRole("dialog", { name: "Istungi ajajoon ja kontekst" });
    await expect(dialog).toBeVisible();
    expect(requests).toHaveLength(1);
    await expect(dialog.locator(".target-speech-highlight")).toHaveCount(1);

    await dialog.getByRole("button", { name: "Sulge aken" }).click();
    await expect(dialog).toHaveCount(0);

    mock.verifyNoErrors();
  });
});
