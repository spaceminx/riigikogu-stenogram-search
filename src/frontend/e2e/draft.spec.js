import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { FIXTURE_IDS, setupApiMock } from "./support/api.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const readFixture = (name) =>
  JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf-8"));
const draft = readFixture("draft_detail.json");
const firstPage = readFixture("draft_speeches.json");
const reading = draft.readings.find((r) => r.speech_count > 0);

// The fixture holds the first 20 speeches; the next page reuses them with new ids
const secondPageResults = firstPage.results
  .slice(0, firstPage.total - firstPage.results.length)
  .map((s) => ({ ...s, id: s.id + 1_000_000, speech_key: `${s.speech_key}-2` }));

function serveDraftSpeeches(page, { failFirst = false } = {}) {
  const requests = [];
  return page
    .route(/api\.e2e\.test\/drafts\/[^/]+\/speeches/, (route) => {
      const url = new URL(route.request().url());
      requests.push(url);
      const json = (status, body) =>
        route.fulfill({
          status,
          contentType: "application/json",
          headers: { "access-control-allow-origin": "*" },
          body: JSON.stringify(body),
        });
      if (failFirst && requests.length === 1) {
        return json(500, { detail: "Sõnavõttude viga" });
      }
      const offset = Number(url.searchParams.get("offset"));
      return json(200, {
        ...firstPage,
        offset,
        results: offset === 0 ? firstPage.results : secondPageResults,
      });
    })
    .then(() => requests);
}

test.describe("Draft readings", () => {
  test("loads a reading's speeches on demand and pages through them", async ({ page }) => {
    const mock = await setupApiMock(page);
    const requests = await serveDraftSpeeches(page);

    await page.goto(`/eelnou/${FIXTURE_IDS.draftUuid}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(draft.title);

    const card = page.locator(".reading-card").first();
    const toggle = card.getByRole("button", { name: `Sõnavõtud (${reading.speech_count})` });
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(requests).toHaveLength(0);

    await toggle.click();
    const cards = card.locator(".speech-card");
    await expect(cards).toHaveCount(firstPage.results.length);
    expect(requests).toHaveLength(1);
    expect(Object.fromEntries(requests[0].searchParams)).toEqual({
      agenda_item_uuid: reading.agenda_item_uuid,
      limit: "50",
      offset: "0",
    });

    const more = card.getByRole("button", { name: "Näita rohkem" });
    await more.click();
    await expect(cards).toHaveCount(firstPage.total);
    expect(requests[1].searchParams.get("offset")).toBe(String(firstPage.results.length));
    await expect(more).toHaveCount(0);

    // Collapsing and reopening keeps the loaded speeches without a new request
    const hide = card.getByRole("button", { name: `Peida sõnavõtud (${reading.speech_count})` });
    await expect(hide).toHaveAttribute("aria-expanded", "true");
    await hide.click();
    await expect(cards).toHaveCount(0);
    await toggle.click();
    await expect(cards).toHaveCount(firstPage.total);
    expect(requests).toHaveLength(2);

    mock.verifyNoErrors();
  });

  test("shows a failed speech load and retries it", async ({ page }) => {
    const mock = await setupApiMock(page, { allowConsoleError: true });
    const requests = await serveDraftSpeeches(page, { failFirst: true });

    await page.goto(`/eelnou/${FIXTURE_IDS.draftUuid}`);
    const card = page.locator(".reading-card").first();
    await card.getByRole("button", { name: `Sõnavõtud (${reading.speech_count})` }).click();

    const error = card.locator(".reading-speeches-error");
    await expect(error).toContainText("Sõnavõttude viga");
    await error.getByRole("button", { name: "Proovi uuesti" }).click();

    await expect(card.locator(".speech-card")).toHaveCount(firstPage.results.length);
    await expect(error).toHaveCount(0);
    expect(requests).toHaveLength(2);

    mock.verifyNoErrors();
  });
});
