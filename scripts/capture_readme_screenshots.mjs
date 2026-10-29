#!/usr/bin/env node
/**
 * scripts/capture_readme_screenshots.mjs
 *
 * Captures the README screenshots from https://www.riigivaade.me in the light theme.
 * - Writes docs/images/<name>.webp (1200 px wide, WebP via Chromium's canvas, no extra deps).
 * - Uses Playwright from src/frontend/node_modules: run `npm install` there first.
 *
 * The examples are chosen to stay impartial: a general search topic, the Speaker of the
 * Riigikogu as the member example, and a broadly supported final vote. Change them here.
 *
 * Member photos are blocked, so the page shows its no-photo placeholder: the Riigikogu photo
 * terms allow use on the site but not redistributing copies, which a screenshot in the repo is.
 *
 * Usage: node scripts/capture_readme_screenshots.mjs
 */

import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const ROOT_DIR = path.resolve(path.dirname(__filename), '..');
const OUT_DIR = path.join(ROOT_DIR, 'docs/images');
const require = createRequire(path.join(ROOT_DIR, 'src/frontend/package.json'));
const { chromium } = require('@playwright/test');

const BASE_URL = 'https://www.riigivaade.me';
const WIDTH = 1200;
const WEBP_QUALITY = 0.85;

const SPEAKER_UUID = '64c0141f-371b-4520-8a50-09e65231f775'; // Lauri Hussar, Speaker of the Riigikogu
const SITTING_DATE = '2026-10-26'; // one vote only, so the stenogram starts near the top
const VOTING_UUID = 'f00ae6f6-bc70-4be6-8e1f-9e000b5d4f0f'; // Taimekaitseseaduse muutmise seadus, final vote
const DRAFT_UUID = '1fdf1be7-b35c-44bf-9ed8-ab5d309838fd'; // the same bill

const SHOTS = [
  {
    name: 'search',
    path: '/otsing?q=eelarve',
    height: 940,
    ready: '.speeches-list .speech-card',
    async prepare(page) {
      await page.getByRole('button', { name: 'Näita ajajoont' }).click();
      await page.getByRole('button', { name: 'Näita kõnelejaid' }).click();
      await page.locator('.search-panels-grid .recharts-surface').first().waitFor();
      await page.locator('.speaker-item').first().waitFor();
    },
  },
  { name: 'sitting', path: `/istung/${SITTING_DATE}`, height: 900, ready: '.speech-card' },
  { name: 'member', path: `/saadik/${SPEAKER_UUID}`, height: 900, ready: '.person-view-container h1' },
  // The faction summary rather than a list of named members
  {
    name: 'attendance',
    path: '/kohalolek?att_tab=factions',
    height: 800,
    ready: '.attendance-table tbody tr',
  },
  { name: 'vote', path: `/haaletus/${VOTING_UUID}`, height: 900, ready: '.voting-factions-section' },
  { name: 'bill', path: `/eelnou/${DRAFT_UUID}`, height: 800, ready: '.reading-card' },
  { name: 'factions', path: '/fraktsioonid', height: 800, ready: '.faction-card' },
];

async function toWebp(page, png) {
  const dataUrl = `data:image/png;base64,${png.toString('base64')}`;
  const webp = await page.evaluate(
    async ({ src, quality }) => {
      const img = new Image();
      img.src = src;
      await img.decode();
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.getContext('2d').drawImage(img, 0, 0);
      return canvas.toDataURL('image/webp', quality);
    },
    { src: dataUrl, quality: WEBP_QUALITY }
  );
  return Buffer.from(webp.split(',')[1], 'base64');
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({ deviceScaleFactor: 1 });
  await context.addInitScript(() => localStorage.setItem('theme', 'light'));
  await context.route('https://api.riigikogu.ee/api/files/**', (route) => route.abort());
  const converter = await context.newPage();

  for (const shot of SHOTS) {
    const page = await context.newPage();
    await page.setViewportSize({ width: WIDTH, height: shot.height });
    await page.goto(BASE_URL + shot.path);
    await page.locator(shot.ready).first().waitFor({ timeout: 30000 });
    if (shot.prepare) await shot.prepare(page);
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => document.fonts.ready);
    const png = await page.screenshot({ animations: 'disabled' });
    const file = path.join(OUT_DIR, `${shot.name}.webp`);
    fs.writeFileSync(file, await toWebp(converter, png));
    console.log(`${path.relative(ROOT_DIR, file)} ${Math.round(fs.statSync(file).size / 1024)} KB`);
    await page.close();
  }
  await browser.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
