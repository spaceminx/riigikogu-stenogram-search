// Renders public/favicon.ico (16, 32 and 48 px) from public/favicon.svg for clients that only
// ask for /favicon.ico. Run after changing the icon: npm run favicon-ico
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const svg = fs.readFileSync(path.join(rootDir, "public", "favicon.svg"), "utf-8");
const outFile = path.join(rootDir, "public", "favicon.ico");
const sizes = [16, 32, 48];

const browser = await chromium.launch();
const images = [];
for (const size of sizes) {
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  const sized = svg.replace("<svg ", `<svg width="${size}" height="${size}" `);
  await page.setContent(
    `<!doctype html><style>html,body{margin:0}svg{display:block}</style>${sized}`
  );
  images.push(await page.locator("svg").screenshot({ omitBackground: true }));
  await page.close();
}
await browser.close();

// ICO container with PNG entries: 6-byte header, a 16-byte entry per image, then the images
const header = Buffer.alloc(6);
header.writeUInt16LE(0, 0);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(images.length, 4);
let offset = header.length + 16 * images.length;
const entries = images.map((png, i) => {
  const entry = Buffer.alloc(16);
  entry.writeUInt8(sizes[i], 0);
  entry.writeUInt8(sizes[i], 1);
  entry.writeUInt16LE(1, 4);
  entry.writeUInt16LE(32, 6);
  entry.writeUInt32LE(png.length, 8);
  entry.writeUInt32LE(offset, 12);
  offset += png.length;
  return entry;
});
fs.writeFileSync(outFile, Buffer.concat([header, ...entries, ...images]));
console.log(`Wrote ${path.relative(rootDir, outFile)}`);
