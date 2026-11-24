// Filters reach the API, and numbers land in the right cells (audit C-20). The mock serves one
// fixture whatever the query says, so these tests read the requests, not only the page.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { FIXTURE_IDS, expectLastRequest, setupApiMock } from "./support/api.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const readFixture = (name) =>
  JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf-8"));

const PERSON = FIXTURE_IDS.personUuid;
const FACTION = "Eesti 200 fraktsioon";

function fulfillJson(route, body) {
  return route.fulfill({
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(body),
  });
}

test.describe("Search filters", () => {
  test("opens on the current membership; 'Kõik' searches every membership", async ({ page }) => {
    const mock = await setupApiMock(page);
    // Slow memberships: the search must wait for them, not search every membership first
    await page.route(/api\.e2e\.test\/memberships$/, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 700));
      await route.fallback();
    });
    await page.goto("/otsing?q=riigikogu");
    await expect(page.locator("#filter-membership")).toHaveValue("15");
    await expectLastRequest(mock, "/search", { membership: "15" });
    // No request for every membership first while the memberships load
    expect(mock.requestsTo("/search").map((r) => r.membership)).toEqual(["15"]);

    await page.locator("#filter-membership").selectOption("all");
    await page.locator("button.search-button").click();
    await expect(page).toHaveURL(/membership=all/);
    await expectLastRequest(mock, "/search", { membership: null });
    await expectLastRequest(mock, "/search/activity", { membership: null });

    await page.locator("#filter-membership").selectOption("15");
    await page.locator("button.search-button").click();
    await expect(page).not.toHaveURL(/membership=/);
    await expectLastRequest(mock, "/search", { membership: "15" });
    mock.verifyNoErrors();
  });

  test("dates outside the chosen membership switch it to every membership", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/otsing?q=riigikogu");
    await expect(page.locator("#filter-membership")).toHaveValue("15");

    await page.locator("#date-range-trigger").click();
    await page.getByRole("button", { name: /^XIV Riigikogu/ }).click();
    await expect(page.locator("#filter-membership")).toHaveValue("all");
    mock.verifyNoErrors();
  });

  test("the dashboard search opens on the current membership", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/");
    await expect(page.locator("#filter-membership")).toHaveValue("15");
    await page.locator("input.search-input").fill("riigikogu");
    await page.locator("button.search-button").click();
    await expect(page).toHaveURL(/\/otsing\?q=riigikogu$/);
    await expectLastRequest(mock, "/search", { membership: "15" });
    mock.verifyNoErrors();
  });

  test("a search from the member page covers every membership", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto(`/saadik/${PERSON}`);
    await page.getByRole("textbox", { name: "Otsi selle saadiku kõnesid" }).fill("riigikogu");
    await page.getByRole("textbox", { name: "Otsi selle saadiku kõnesid" }).press("Enter");
    await expect(page).toHaveURL(/membership=all/);
    await expectLastRequest(mock, "/search", { speaker_uuid: PERSON, membership: null });
    mock.verifyNoErrors();
  });

  test("every filter reaches the search, the timeline and the speakers", async ({ page }) => {
    const mock = await setupApiMock(page);
    const sample = readFixture("search_sample.json");
    // Dates already in the URL must survive a new search
    await page.goto("/otsing?q=riigikogu&membership=14&start_date=2020-01-01&end_date=2020-12-31");
    await expect(page.locator(".speeches-header-bar .results-badge")).toContainText(
      `${sample.total_count.toLocaleString("et-EE")} tk`
    );

    await page.locator("#filter-faction").selectOption(FACTION);
    await page.locator("#filter-speaker").fill("Kallas");
    await page.locator("#filter-speech-type").selectOption("questions");
    await page.getByLabel("Jäta istungi juhataja välja").check();
    await page.getByLabel("Ainult täpne sõna (ilma liitsõnadeta)").check();
    await page.locator("button.search-button").click();

    const filters = {
      q: "riigikogu",
      membership: "14",
      faction: FACTION,
      speaker: "Kallas",
      start_date: "2020-01-01",
      end_date: "2020-12-31",
      speech_category: "questions",
      exclude_chair: "true",
      expand: "false",
    };
    await expectLastRequest(mock, "/search", { ...filters, offset: "0" });
    await expectLastRequest(mock, "/search/activity", filters);
    await expectLastRequest(mock, "/search/speakers", filters);

    await page.locator("#search-sort-select").selectOption("date_asc");
    await expectLastRequest(mock, "/search", { ...filters, sort_by: "date_asc", offset: "0" });

    await page.getByRole("button", { name: /Järgmine/ }).click();
    await expectLastRequest(mock, "/search", { ...filters, sort_by: "date_asc", offset: "50" });
    mock.verifyNoErrors();
  });
});

test.describe("Drafts, votings and attendance filters", () => {
  test("drafts: each filter refetches on its own", async ({ page }) => {
    const mock = await setupApiMock(page);
    const committee = readFixture("drafts_list.json").facets.committee[0].uuid;
    await page.goto("/eelnoud");
    await expectLastRequest(mock, "/drafts", { membership: "15", committee: null });
    await page.locator("#filter-draft-committee").selectOption(committee);
    await expectLastRequest(mock, "/drafts", { membership: "15", committee });
    await page.locator("#filter-draft-type").selectOption("SE");
    await expectLastRequest(mock, "/drafts", { committee, type: "SE" });
    mock.verifyNoErrors();
  });

  test("votings: type, search and page reach the API", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/haaletused");
    await expectLastRequest(mock, "/votings", { type: null, offset: "0" });

    await page.locator("#filter-voting-type").selectOption("SALAJANE");
    await expectLastRequest(mock, "/votings", { type: "SALAJANE", offset: "0" });

    await page
      .getByRole("textbox", { name: "Otsi hääletuse või eelnõu nime järgi" })
      .fill("eelarve");
    await page.getByRole("button", { name: "Otsi", exact: true }).click();
    await expectLastRequest(mock, "/votings", { type: "SALAJANE", q: "eelarve", offset: "0" });

    await page.getByRole("button", { name: /Järgmine/ }).click();
    await expectLastRequest(mock, "/votings", { type: "SALAJANE", q: "eelarve", offset: "50" });
    mock.verifyNoErrors();
  });

  test("attendance: role, infotund and faction reach both tables", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto("/kohalolek");
    await expectLastRequest(mock, "/attendance/stats", { membership: "15", role: null });

    // Each change is checked on its own: a later change refetches with every filter anyway
    await page.locator("#role-select").selectOption("coalition");
    await expectLastRequest(mock, "/attendance/stats", { membership: "15", role: "coalition" });
    await page.getByLabel("Jäta infotunnid välja").click();
    await expect(page.getByLabel("Jäta infotunnid välja")).toBeChecked();
    await expectLastRequest(mock, "/attendance/factions", {
      membership: "15",
      role: "coalition",
      exclude_infotund: "true",
    });

    await page.locator("#faction-select").selectOption(FACTION);
    await expectLastRequest(mock, "/attendance/stats", {
      membership: "15",
      role: "coalition",
      exclude_infotund: "true",
      faction: FACTION,
    });
    mock.verifyNoErrors();
  });

  test("attendance factions: each number lands in its own cell", async ({ page }) => {
    const mock = await setupApiMock(page);
    const [base] = readFixture("attendance_factions.json");
    // Every count differs, so a swapped field shows up as a wrong number
    await page.route(/api\.e2e\.test\/attendance\/factions(\?|$)/, (route) =>
      fulfillJson(route, [
        {
          ...base,
          faction: FACTION,
          member_count: 9,
          total_sessions: 50,
          present_sessions: 11,
          total_checks: 50,
          registered_checks: 11,
          registered_pct: 22,
          attendance_percentage: 22,
          votes_total: 70,
          votes_voted: 33,
          votes_voted_pct: 47.1,
          votes_not_voted: 20,
          votes_absent: 17,
        },
      ])
    );
    await page.goto("/kohalolek?att_tab=factions");
    const row = page.locator(".attendance-table tbody tr").first();
    await expect(row.locator(".att-col-count")).toHaveText("9");
    await expect(row.locator(".att-col-registered")).toContainText("11/50");
    await expect(row.locator(".att-col-votes")).toContainText("33/70");
    await expect(row.locator(".att-col-votes")).toContainText("ei hääletanud 28,6% · puudus 24,3%");
    mock.verifyNoErrors();
  });
});

test.describe("Member page filters", () => {
  test("role tab, page and infotund reach the API", async ({ page }) => {
    const mock = await setupApiMock(page);
    await page.goto(`/saadik/${PERSON}`);
    const speechesPath = `/persons/${PERSON}/speeches`;
    await expectLastRequest(mock, speechesPath, { role_class: "mp", offset: "0" });

    const list = page.locator('section[aria-label="Saadiku kõnede loend"]');
    await list.getByRole("button", { name: /Ministrina/ }).click();
    await expectLastRequest(mock, speechesPath, { role_class: "minister", offset: "0" });

    await list.getByRole("button", { name: /Järgmine/ }).click();
    await expectLastRequest(mock, speechesPath, { role_class: "minister", offset: "20" });

    await page.getByLabel("Jäta infotunnid välja").click();
    await expect(page.getByLabel("Jäta infotunnid välja")).toBeChecked();
    await expectLastRequest(mock, `/persons/${PERSON}/attendance`, { exclude_infotund: "true" });
    mock.verifyNoErrors();
  });

  test("attendance by membership shows present out of total", async ({ page }) => {
    const mock = await setupApiMock(page);
    const attendance = readFixture("person_attendance.json");
    await page.goto(`/saadik/${PERSON}`);
    const table = page.locator('section[aria-label="Koosseisude kaupa ülevaade"]');
    for (const m of attendance.by_membership) {
      await expect(table).toContainText(`(${m.present_sessions}/${m.total_sessions})`);
    }
    mock.verifyNoErrors();
  });
});

test.describe("Voting page", () => {
  test("totals and the member filters", async ({ page }) => {
    const mock = await setupApiMock(page);
    const voting = readFixture("voting_detail.json");
    await page.goto(`/haaletus/${voting.uuid}`);

    const { present, in_favor, against, neutral, absent } = voting.totals;
    const notVoted = present - in_favor - against - neutral;
    expect(notVoted).not.toBe(absent);
    await expect(page.locator(".voting-total-card.ei_haaletanud .voting-total-count")).toHaveText(
      String(notVoted)
    );
    await expect(page.locator(".voting-total-card.puudus .voting-total-count")).toHaveText(
      String(absent)
    );

    const rows = page.locator(".voting-members-table tbody tr");
    await expect(rows).toHaveCount(voting.votes.length);
    const against_ = voting.votes.filter((v) => v.decision === "VASTU").length;
    await page
      .getByRole("group", { name: "Otsuse filter" })
      .getByRole("button", { name: "Vastu" })
      .click();
    await expect(rows).toHaveCount(against_);

    await page
      .getByRole("group", { name: "Otsuse filter" })
      .getByRole("button", { name: "Kõik" })
      .click();
    const name = voting.votes[0].member_name;
    await page.getByRole("textbox", { name: "Otsi saadiku nime järgi" }).fill(name);
    await expect(rows).toHaveCount(voting.votes.filter((v) => v.member_name === name).length);
    mock.verifyNoErrors();
  });
});

test("an unknown address is not indexed", async ({ page }) => {
  await setupApiMock(page);
  await page.goto("/seda-lehte-pole");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
});
