import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const FIXTURES_DIR = path.resolve(__dirname, "../fixtures");

const indexData = JSON.parse(fs.readFileSync(path.join(FIXTURES_DIR, "index.json"), "utf-8"));

export const FIXTURE_IDS = indexData.ids;

// Pre-load fixtures into memory
const fixtureCache = new Map();
for (const entry of indexData.endpoints) {
  if (!fixtureCache.has(entry.fixture)) {
    const content = fs.readFileSync(path.join(FIXTURES_DIR, entry.fixture), "utf-8");
    fixtureCache.set(entry.fixture, content);
  }
}

/**
 * Normalizes query params for matching:
 * Returns an object with key/values.
 */
function getQueryParams(url) {
  const parsed = new URL(url);
  const params = {};
  for (const [key, value] of parsed.searchParams.entries()) {
    params[key] = value;
  }
  return params;
}

/**
 * Finds matching fixture for given method, pathname and query params
 */
function findFixture(method, pathname, queryParams) {
  // Sort candidates: ones with queryParams match first
  for (const entry of indexData.endpoints) {
    if (entry.method !== method || entry.path !== pathname) {
      continue;
    }
    if (entry.queryParams) {
      const matchAll = Object.entries(entry.queryParams).every(([k, v]) => queryParams[k] === v);
      if (matchAll) {
        return entry.fixture;
      }
    }
  }

  // Fallback to entry without queryParams requirement
  for (const entry of indexData.endpoints) {
    if (entry.method === method && entry.path === pathname && !entry.queryParams) {
      return entry.fixture;
    }
  }

  // Additional fallback for search auxiliary endpoints (/search/activity, /search/speakers, /suggest)
  // when searched with varying queries during UI interaction
  if (method === "GET") {
    if (pathname === "/search/activity") return "search_activity.json";
    if (pathname === "/search/speakers") return "search_speakers.json";
    if (pathname === "/suggest") return "suggest.json";
  }

  return null;
}

/**
 * Sets up interceptor on page
 */
export async function setupApiMock(page, options = {}) {
  const { allowConsoleError = false } = options;
  const interceptedRequests = [];
  const errors = [];
  const externalRequests = [];

  page.on("pageerror", (err) => {
    errors.push(`Page error: ${err.message}\n${err.stack}`);
  });

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      // Ignore React favicon / 404 resource errors if benign, but track others
      if (!allowConsoleError) {
        errors.push(`Console error: ${text}`);
      }
    }
  });

  // Guard: route all requests and abort any whose host is not localhost:4173 or api.e2e.test
  await page.route("**/*", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const host = url.host;

    if (host !== "localhost:4173" && host !== "127.0.0.1:4173" && host !== "api.e2e.test") {
      externalRequests.push(req.url());
      return route.abort();
    }

    if (host === "api.e2e.test") {
      const method = req.method();
      const pathname = url.pathname;
      const queryParams = getQueryParams(req.url());

      interceptedRequests.push({
        method,
        url: req.url(),
        pathname,
        queryParams,
      });

      const fixtureFile = findFixture(method, pathname, queryParams);

      if (!fixtureFile) {
        // Unmatched route -> 599
        return route.fulfill({
          status: 599,
          contentType: "application/json",
          body: JSON.stringify({
            error: `Unmatched mock API route: ${method} ${url.href}`,
          }),
        });
      }

      const body = fixtureCache.get(fixtureFile);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "access-control-allow-origin": "*",
        },
        body,
      });
    }

    return route.continue();
  });

  return {
    interceptedRequests,
    errors,
    externalRequests,
    verifyNoErrors() {
      if (externalRequests.length > 0) {
        throw new Error(`external request: ${externalRequests.join(", ")}`);
      }
      const unmatched = interceptedRequests.filter(
        (r) => !findFixture(r.method, r.pathname, r.queryParams)
      );
      if (unmatched.length > 0) {
        throw new Error(
          `Unmatched API requests detected:\n${unmatched
            .map((u) => `${u.method} ${u.url}`)
            .join("\n")}`
        );
      }
      if (errors.length > 0) {
        throw new Error(`Browser errors encountered:\n${errors.join("\n")}`);
      }
    },
  };
}
