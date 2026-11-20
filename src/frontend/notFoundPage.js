import fs from "node:fs";
import path from "node:path";

// Vercel answers unknown paths with dist/404.html and status 404, and the middleware serves the
// same file to link-preview bots for a missing speech, person, voting or draft. Building it from
// the app shell lets React's NotFoundView render it with the site header, fonts and theme; a
// hand-written static page fell behind every design change.
export const NOT_FOUND_TITLE = "Lehekülge ei leitud — Riigivaade";

export function buildNotFoundHtml(indexHtml) {
  if (!/<title>[\s\S]*?<\/title>/i.test(indexHtml)) {
    throw new Error("index.html has no <title>; cannot build 404.html");
  }
  return (
    indexHtml
      .replace(
        /<title>[\s\S]*?<\/title>/i,
        () => `<title>${NOT_FOUND_TITLE}</title>\n    <meta name="robots" content="noindex" />`
      )
      // The page has no address of its own; drop the canonical site URL
      .replace(/\s*<meta\s+property="og:url"[^>]*>/i, "")
  );
}

export function notFoundPagePlugin() {
  return {
    name: "riigivaade-404-page",
    apply: "build",
    writeBundle(options) {
      const outDir = options.dir;
      const indexHtml = fs.readFileSync(path.join(outDir, "index.html"), "utf-8");
      fs.writeFileSync(path.join(outDir, "404.html"), buildNotFoundHtml(indexHtml));
    },
  };
}
