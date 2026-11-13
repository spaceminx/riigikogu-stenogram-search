import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { FIXTURE_IDS, setupApiMock } from "./support/api.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const session = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures", "session_votings.json"), "utf-8")
);

// A sitting with more votings than one API page (max 100), e.g. a night-long obstruction
const TOTAL = 130;
const allVotings = Array.from({ length: TOTAL }, (_, i) => {
  const base = session.results[i % session.results.length];
  return { ...base, uuid: `${base.uuid.slice(0, 24)}${String(i).padStart(12, "0")}` };
});

const votingRequests = (mock) =>
  mock.interceptedRequests.filter((r) => r.pathname === "/votings").map((r) => r.queryParams);

test.describe("Session votings", () => {
  test("loads every voting of a sitting that does not fit on one API page", async ({ page }) => {
    const mock = await setupApiMock(page);
    const requests = [];
    await page.route(/api\.e2e\.test\/votings\?/, (route) => {
      const url = new URL(route.request().url());
      requests.push(Object.fromEntries(url.searchParams));
      const limit = Number(url.searchParams.get("limit"));
      const offset = Number(url.searchParams.get("offset"));
      return route.fulfill({
        contentType: "application/json",
        headers: { "access-control-allow-origin": "*" },
        body: JSON.stringify({
          total: TOTAL,
          limit,
          offset,
          results: allVotings.slice(offset, offset + limit),
        }),
      });
    });

    await page.goto(`/istung/${FIXTURE_IDS.date}`);
    await expect(page.locator("#session-votings-title")).toHaveText(`Hääletused (${TOTAL})`);
    await page.getByRole("button", { name: `Näita kõiki hääletusi (${TOTAL})` }).click();
    await expect(page.locator(".voting-row-link")).toHaveCount(TOTAL);

    expect(requests).toEqual([
      { sitting_date: FIXTURE_IDS.date, limit: "100", offset: "0" },
      { sitting_date: FIXTURE_IDS.date, limit: "100", offset: "100" },
    ]);
    mock.verifyNoErrors();
  });

  test("a sitting that fits on one page is fetched with one request", async ({ page }) => {
    const mock = await setupApiMock(page);

    await page.goto(`/istung/${FIXTURE_IDS.date}`);
    await expect(page.locator("#session-votings-title")).toHaveText(
      `Hääletused (${session.results.length})`
    );
    expect(votingRequests(mock)).toHaveLength(1);
    mock.verifyNoErrors();
  });
});
