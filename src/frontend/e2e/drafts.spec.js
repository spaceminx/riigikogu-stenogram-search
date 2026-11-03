import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { FIXTURE_IDS, setupApiMock } from "./support/api.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const readFixture = (name) =>
  JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf-8"));
const list = readFixture("drafts_list.json");
const draft = readFixture("draft_detail.json");

const draftRequests = (mock) =>
  mock.interceptedRequests.filter((r) => r.pathname === "/drafts").map((r) => r.queryParams);

test.describe("Drafts list", () => {
  test("lists drafts with their mark, stage and committee", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/eelnoud");

    const rows = page.locator(".draft-row-link");
    await expect(rows).toHaveCount(list.results.length);
    await expect(page.locator(".results-badge")).toHaveText(
      `${list.total.toLocaleString("et-EE")} eelnõu`
    );

    const first = list.results[0];
    const firstRow = rows.first();
    await expect(firstRow).toHaveAttribute("href", `/eelnou/${first.uuid}`);
    await expect(firstRow.locator(".draft-row-mark")).toHaveText(
      `${first.mark} ${first.type_code}`
    );
    await expect(firstRow.locator(".draft-stage-badge")).toHaveText("Algatatud");

    // Stage and status differ: both are shown
    const secondReading = rows.filter({ hasText: "I lugemine lõpetatud" }).first();
    await expect(secondReading.locator(".draft-stage-badge")).toHaveText("Teine lugemine");

    const withCommittee = list.results.findIndex((d) => d.leading_committee);
    await expect(rows.nth(withCommittee).locator(".draft-row-facts")).toContainText(
      list.results[withCommittee].leading_committee.name
    );

    await expect(page.locator("nav.nav-links a[href='/eelnoud']")).toHaveAttribute(
      "aria-current",
      "page"
    );
    mock.verifyNoErrors();
  });

  test("filters, search and sort go to the URL and the API", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/eelnoud");
    await expect(page.locator(".draft-row-link").first()).toBeVisible();
    expect(draftRequests(mock).at(-1)).toEqual({ limit: "50", offset: "0" });

    const adopted = list.facets.status.adopted.toLocaleString("et-EE");
    await expect(page.locator("#filter-draft-status option[value='adopted']")).toHaveText(
      `Vastu võetud (${adopted})`
    );
    await page.locator("#filter-draft-status").selectOption("adopted");
    await expect(page).toHaveURL(/status=adopted/);

    await page.locator("#filter-draft-type").selectOption("SE");
    await expect(page.locator("#filter-draft-type option[value='SE']")).toHaveText(
      `Seadus (SE) (${list.facets.type.SE.toLocaleString("et-EE")})`
    );

    const committee = list.facets.committee[0];
    await page.locator("#filter-draft-committee").selectOption(committee.uuid);
    await page.locator("#filter-draft-membership").selectOption("15");
    await page.locator("#filter-draft-sort").selectOption("initiated");

    await page
      .getByRole("textbox", { name: "Otsi eelnõu pealkirja või numbri järgi" })
      .fill("919 SE");
    await page.getByRole("button", { name: "Otsi", exact: true }).click();

    await expect(page).toHaveURL(/q=919\+SE/);
    await expect
      .poll(() => draftRequests(mock).at(-1))
      .toEqual({
        membership: "15",
        type: "SE",
        status: "adopted",
        committee: committee.uuid,
        q: "919 SE",
        sort: "initiated",
        limit: "50",
        offset: "0",
      });

    // Reloading keeps every choice
    await page.reload();
    await expect(page.locator("#filter-draft-status")).toHaveValue("adopted");
    await expect(page.locator("#filter-draft-committee")).toHaveValue(committee.uuid);
    await expect(page.locator("#filter-draft-sort")).toHaveValue("initiated");
    mock.verifyNoErrors();
  });

  test("a row opens the draft page, whose header shows the draft list fields", async ({ page }) => {
    const mock = await setupApiMock(page);
    const summary = {
      ...list.results[0],
      ...Object.fromEntries(Object.entries(draft).filter(([k]) => k in list.results[0])),
    };
    await page.route(/api\.e2e\.test\/drafts\?/, (route) =>
      route.fulfill({
        contentType: "application/json",
        headers: { "access-control-allow-origin": "*" },
        body: JSON.stringify({ ...list, results: [summary] }),
      })
    );

    await page.goto("/eelnoud");
    await page.locator(".draft-row-link").first().click();
    await expect(page).toHaveURL(new RegExp(`/eelnou/${FIXTURE_IDS.draftUuid}`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(draft.title);

    await expect(page.locator(".draft-mark-badge")).toHaveText(`${draft.mark} ${draft.type_code}`);
    const facts = page.locator(".draft-facts");
    await expect(facts).toContainText("Seadus");
    await expect(facts).toContainText("XV koosseis");
    await expect(facts).toContainText("Teine lugemine · I lugemine lõpetatud");
    await expect(facts).toContainText(draft.leading_committee.name);

    await page.getByRole("button", { name: "← Tagasi" }).click();
    await expect(page).toHaveURL(/\/eelnoud$/);
    mock.verifyNoErrors();
  });

  test("an empty result says so", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.route(/api\.e2e\.test\/drafts\?/, (route) =>
      route.fulfill({
        contentType: "application/json",
        headers: { "access-control-allow-origin": "*" },
        body: JSON.stringify({
          total: 0,
          limit: 50,
          offset: 0,
          results: [],
          facets: { status: {}, type: {}, committee: [] },
        }),
      })
    );

    await page.goto("/eelnoud?q=olematu");
    await expect(page.getByText("Nende valikutega eelnõusid ei leitud.")).toBeVisible();
    mock.verifyNoErrors();
  });
});
