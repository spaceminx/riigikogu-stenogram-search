import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";
import { FIXTURE_IDS, setupApiMock } from "./support/api.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const readFixture = (name) =>
  JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures", name), "utf-8"));

// The fixture sitting (21.10.2026) ran past midnight: this vote happened on 22.10 at 03:40
const overnight = (voting) => ({
  ...voting,
  date: "2026-10-22",
  start_time: "2026-10-22T03:40:58.373",
  sitting_date: "2026-10-21",
});

const json = (body) => ({
  contentType: "application/json",
  headers: { "access-control-allow-origin": "*" },
  body: JSON.stringify(body),
});

async function mockOvernightVotings(page) {
  const list = readFixture("votings_list.json");
  const session = readFixture("session_votings.json");
  const detail = readFixture("voting_detail.json");
  await page.route(/api\.e2e\.test\/votings\?/, (route) => {
    const url = new URL(route.request().url());
    const data = url.searchParams.has("sitting_date") ? session : list;
    const [first, ...rest] = data.results;
    return route.fulfill(json({ ...data, results: [overnight(first), ...rest] }));
  });
  await page.route(new RegExp(`api\\.e2e\\.test/votings/${FIXTURE_IDS.votingUuid}$`), (route) =>
    route.fulfill(json(overnight(detail)))
  );
}

test.describe("Overnight voting time", () => {
  test("the votings list leads with when the vote happened and names its sitting", async ({
    page,
  }) => {
    const mock = await setupApiMock(page);
    await mockOvernightVotings(page);

    await page.goto("/haaletused");
    const times = page.locator(".voting-row-time");
    await expect(times.first()).toHaveText("22.10.2026 03:40 · 21.10. istung");
    // A vote on the same day as its sitting shows only its date and time
    await expect(times.nth(1)).toHaveText(/^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$/);

    mock.verifyNoErrors();
  });

  test("the session page adds the date only to the overnight vote", async ({ page }) => {
    const mock = await setupApiMock(page);
    await mockOvernightVotings(page);

    await page.goto(`/istung/${FIXTURE_IDS.date}`);
    const times = page.locator(".voting-row-time");
    await expect(times.first()).toHaveText("22.10. kell 03:40");
    await expect(times.nth(1)).toHaveText(/^\d{2}:\d{2}$/);

    mock.verifyNoErrors();
  });

  test("the voting page shows the sitting and the vote's own date", async ({ page }) => {
    const mock = await setupApiMock(page);
    await mockOvernightVotings(page);

    await page.goto(`/haaletus/${FIXTURE_IDS.votingUuid}`);
    await expect(page.locator(".voting-sitting-link")).toHaveText("Istung 21.10.2026");
    await expect(page.locator(".voting-meta-row")).toContainText("Hääletus 22.10.2026 kell 03:40");
    await expect(page.locator(".voting-meta-row")).not.toContainText("Kell");

    mock.verifyNoErrors();
  });

  test("a wrapped time line never starts with the separator", async ({ page }) => {
    const mock = await setupApiMock(page);
    await mockOvernightVotings(page);
    await page.setViewportSize({ width: 320, height: 800 });

    await page.goto("/haaletused");
    const time = page.locator(".voting-row-time").first();
    await expect(time).toHaveText(/21\.10\. istung/);

    const lineStarts = await time.evaluate((el) => {
      const starts = new Set();
      for (let width = 80; width <= 280; width += 2) {
        el.style.display = "inline-block";
        el.style.width = `${width}px`;
        const parts = [...el.querySelectorAll(".voting-row-time-part")];
        const tops = parts.map((p) => Math.round(p.getBoundingClientRect().top));
        // Each part is nowrap, so a new line can only start with a part
        parts.forEach((p, i) => {
          if (i === 0 || tops[i] !== tops[i - 1]) starts.add(p.textContent.trim()[0]);
        });
      }
      return [...starts];
    });
    expect(lineStarts).not.toContain("·");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(overflow).toBe(false);

    mock.verifyNoErrors();
  });
});
