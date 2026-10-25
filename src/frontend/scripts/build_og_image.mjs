// Renders the link preview image (public/og-image.png, 1200 × 630) with the site's own fonts.
// Run after changing the brand: npm run og-image
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outFile = path.join(rootDir, "public", "og-image.png");

function fontFace(family, pkg, file) {
  const fontPath = path.join(rootDir, "node_modules", "@fontsource-variable", pkg, "files", file);
  const data = fs.readFileSync(fontPath).toString("base64");
  return `@font-face { font-family: "${family}"; font-weight: 200 900; src: url(data:font/woff2;base64,${data}) format("woff2"); }`;
}

const fonts = [
  fontFace("Serif", "source-serif-4", "source-serif-4-latin-wght-normal.woff2"),
  fontFace("Serif", "source-serif-4", "source-serif-4-latin-ext-wght-normal.woff2"),
  fontFace("Mono", "source-code-pro", "source-code-pro-latin-wght-normal.woff2"),
  fontFace("Mono", "source-code-pro", "source-code-pro-latin-ext-wght-normal.woff2"),
].join("\n");

const mark = `
  <svg width="100" height="100" viewBox="0 0 40 40" aria-hidden="true">
    <rect width="40" height="40" rx="6" fill="#2E3F78"/>
    <path d="M14 21a5 5 0 1 1 0 10c0 3.4-2 6-5 7.4l-.9-1.8c1.7-1 2.8-2.6 3.1-4.5A5 5 0 0 1 14 21z" fill="#FFFFFF"/>
    <path d="M27 21a5 5 0 1 1 0 10c0 3.4-2 6-5 7.4l-.9-1.8c1.7-1 2.8-2.6 3.1-4.5A5 5 0 0 1 27 21z" fill="#F0A47E"/>
  </svg>`;

const html = `<!doctype html>
<html lang="et">
<head>
<meta charset="utf-8">
<style>
${fonts}
html, body { margin: 0; }
.card {
  width: 1200px;
  height: 630px;
  box-sizing: border-box;
  padding: 76px 84px;
  background: #1C1F26;
  color: #FFFFFF;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.brand { display: flex; align-items: center; gap: 26px; }
.wordmark { font-family: "Serif"; font-weight: 600; font-size: 76px; line-height: 1; }
.headline { font-family: "Serif"; font-weight: 600; font-size: 58px; line-height: 1.18; max-width: 980px; margin: 0; }
.footer { font-family: "Mono"; font-size: 27px; letter-spacing: 0.04em; color: #C8CBD3; margin-top: 22px; }
</style>
</head>
<body>
  <div class="card">
    <div class="brand">${mark}<span class="wordmark">Riigivaade</span></div>
    <div>
      <p class="headline">Riigikogu kõned, hääletused ja kohalolek ühes kohas</p>
      <div class="footer">STENOGRAMMID 2019– · RIIGIVAADE.ME</div>
    </div>
  </div>
</body>
</html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
await page.setContent(html);
await page.evaluate(() => document.fonts.ready);
await page.locator(".card").screenshot({ path: outFile });
await browser.close();
console.log(`Wrote ${path.relative(rootDir, outFile)}`);
