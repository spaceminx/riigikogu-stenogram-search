#!/usr/bin/env node
/**
 * scripts/capture_e2e_fixtures.mjs
 *
 * Captures real responses from https://api.riigivaade.me for E2E testing.
 * - Trims large arrays to at most 20 items.
 * - Writes fixtures to src/frontend/e2e/fixtures/<name>.json
 * - Writes e2e/fixtures/index.json mapping method + path + query pattern -> fixture file.
 * - Sets User-Agent: "riigivaade-e2e-capture".
 * - Sleeps at least 500 ms between requests.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');
const FIXTURES_DIR = path.resolve(ROOT_DIR, 'src/frontend/e2e/fixtures');

const BASE_URL = 'https://api.riigivaade.me';
const USER_AGENT = 'riigivaade-e2e-capture';
const DELAY_MS = 600;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function trimData(data, maxItems = 20) {
  if (data === null || typeof data !== 'object') {
    return data;
  }
  if (Array.isArray(data)) {
    return data.slice(0, maxItems).map((item) => trimData(item, maxItems));
  }
  const result = {};
  for (const [key, value] of Object.entries(data)) {
    if (Array.isArray(value)) {
      result[key] = value.slice(0, maxItems).map((item) => trimData(item, maxItems));
    } else if (value !== null && typeof value === 'object') {
      result[key] = trimData(value, maxItems);
    } else {
      result[key] = value;
    }
  }
  return result;
}

async function fetchJson(endpoint) {
  const url = `${BASE_URL}${endpoint}`;
  console.log(`Fetching: ${url}`);
  const resp = await fetch(url, {
    headers: {
      'User-Agent': USER_AGENT,
      Accept: 'application/json',
    },
  });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status} ${resp.statusText} for ${url}`);
  }
  await sleep(DELAY_MS);
  const data = await resp.json();
  return trimData(data, 20);
}

async function main() {
  fs.mkdirSync(FIXTURES_DIR, { recursive: true });

  // 1. Pick concrete IDs
  console.log('--- Step 1: Picking concrete IDs ---');
  const systemStatus = await fetchJson('/system/status');
  const memberships = await fetchJson('/memberships');
  const overview = await fetchJson('/overview');
  const sessionDates = await fetchJson('/sessions/dates');
  const governments = await fetchJson('/governments');
  const factionsList = await fetchJson('/attendance/factions/list?membership=all');

  const concreteDate = sessionDates.dates && sessionDates.dates[0] ? sessionDates.dates[0] : '2026-10-21';

  // Pick person
  const personsList = await fetchJson('/persons?limit=5');
  const concretePersonUuid = personsList.results && personsList.results[0]
    ? personsList.results[0].uuid
    : '6b45cfb5-8a17-481c-b674-80fc00c6cf5d';

  // Pick speech from search
  const searchSample = await fetchJson('/search?q=riigieelarve&limit=5');
  const concreteSpeechId = searchSample.results && searchSample.results[0]
    ? searchSample.results[0].id
    : 210253;

  // Pick voting
  const votingsList = await fetchJson('/votings?limit=5');
  const concreteVotingUuid = votingsList.results && votingsList.results[0]
    ? votingsList.results[0].uuid
    : '3943e6d1-4259-4435-bb44-644bc6ce6105';

  // Pick draft
  let concreteDraftUuid = 'c6ccd71d-8bd6-4400-bf17-830ea1913485';
  if (votingsList.results) {
    for (const v of votingsList.results) {
      if (v.related_document && v.related_document.type === 'DRAFT' && v.related_document.uuid) {
        concreteDraftUuid = v.related_document.uuid;
        break;
      }
    }
  }

  const ids = {
    date: concreteDate,
    personUuid: concretePersonUuid,
    speechId: concreteSpeechId,
    votingUuid: concreteVotingUuid,
    draftUuid: concreteDraftUuid,
  };
  console.log('Concrete IDs picked:', ids);

  // 2. Fetch all required route endpoints
  console.log('--- Step 2: Fetching route endpoints ---');
  const sessionDetail = await fetchJson(`/sessions/${concreteDate}`);
  const sessionVotings = await fetchJson(`/votings?sitting_date=${concreteDate}&limit=100`);
  const attendanceStats = await fetchJson('/attendance/stats?membership=all');
  const attendanceFactions = await fetchJson('/attendance/factions?membership=all');
  const speechDetail = await fetchJson(`/speeches/${concreteSpeechId}`);
  const speechContext = await fetchJson(`/speeches/${concreteSpeechId}/context?expand=true`);
  const personDetail = await fetchJson(`/persons/${concretePersonUuid}`);
  const personStats = await fetchJson(`/persons/${concretePersonUuid}/stats`);
  const personAttendance = await fetchJson(`/persons/${concretePersonUuid}/attendance?exclude_infotund=false`);
  const personSpeeches = await fetchJson(`/persons/${concretePersonUuid}/speeches?limit=20&offset=0`);
  const personAlignment = await fetchJson(`/persons/${concretePersonUuid}/faction-alignment`);
  const personDiffs = await fetchJson(`/persons/${concretePersonUuid}/faction-alignment/differences?limit=10&offset=0`);
  const votingDetail = await fetchJson(`/votings/${concreteVotingUuid}`);
  const draftDetail = await fetchJson(`/drafts/${concreteDraftUuid}`);
  const draftSpeeches = await fetchJson(`/drafts/${concreteDraftUuid}/speeches?limit=20&offset=0`);
  const searchActivity = await fetchJson('/search/activity?q=riigieelarve&interval=monthly');
  const searchSpeakers = await fetchJson('/search/speakers?q=riigieelarve&limit=20');
  const searchSuggestions = await fetchJson('/suggest?prefix=riigi');

  // Multi-term and phrase search for pill test
  const searchKliima = await fetchJson('/search?q=kliima&limit=20');
  const searchKliimaMuutus = await fetchJson('/search?q=%22kliima+muutus%22&limit=20');
  const searchKliimaJaMets = await fetchJson('/search?q=kliima+mets&limit=20');
  const searchKliimaVoiMets = await fetchJson('/search?q=kliima%2C+mets&limit=20');

  // 3. Write individual fixture files
  console.log('--- Step 3: Writing fixture files ---');
  const fixtures = [
    { name: 'system_status.json', data: systemStatus },
    { name: 'memberships.json', data: memberships },
    { name: 'overview.json', data: overview },
    { name: 'session_dates.json', data: sessionDates },
    { name: 'governments.json', data: governments },
    { name: 'factions_list.json', data: factionsList },
    { name: 'persons_list.json', data: personsList },
    { name: 'session_detail.json', data: sessionDetail },
    { name: 'session_votings.json', data: sessionVotings },
    { name: 'attendance_stats.json', data: attendanceStats },
    { name: 'attendance_factions.json', data: attendanceFactions },
    { name: 'speech_detail.json', data: speechDetail },
    { name: 'speech_context.json', data: speechContext },
    { name: 'person_detail.json', data: personDetail },
    { name: 'person_stats.json', data: personStats },
    { name: 'person_attendance.json', data: personAttendance },
    { name: 'person_speeches.json', data: personSpeeches },
    { name: 'person_alignment.json', data: personAlignment },
    { name: 'person_diffs.json', data: personDiffs },
    { name: 'votings_list.json', data: votingsList },
    { name: 'voting_detail.json', data: votingDetail },
    { name: 'draft_detail.json', data: draftDetail },
    { name: 'draft_speeches.json', data: draftSpeeches },
    { name: 'search_sample.json', data: searchSample },
    { name: 'search_activity.json', data: searchActivity },
    { name: 'search_speakers.json', data: searchSpeakers },
    { name: 'suggest.json', data: searchSuggestions },
    { name: 'search_kliima.json', data: searchKliima },
    { name: 'search_kliima_muutus.json', data: searchKliimaMuutus },
    { name: 'search_kliima_ja_mets.json', data: searchKliimaJaMets },
    { name: 'search_kliima_voi_mets.json', data: searchKliimaVoiMets },
  ];

  for (const f of fixtures) {
    fs.writeFileSync(
      path.join(FIXTURES_DIR, f.name),
      JSON.stringify(f.data, null, 2) + '\n',
      'utf-8'
    );
  }

  // 4. Build index.json
  console.log('--- Step 4: Writing index.json ---');
  const index = {
    ids,
    endpoints: [
      { method: 'GET', path: '/system/status', fixture: 'system_status.json' },
      { method: 'GET', path: '/memberships', fixture: 'memberships.json' },
      { method: 'GET', path: '/overview', fixture: 'overview.json' },
      { method: 'GET', path: '/sessions/dates', fixture: 'session_dates.json' },
      { method: 'GET', path: '/governments', fixture: 'governments.json' },
      { method: 'GET', path: '/attendance/factions/list', fixture: 'factions_list.json' },
      { method: 'GET', path: '/attendance/stats', fixture: 'attendance_stats.json' },
      { method: 'GET', path: '/attendance/factions', fixture: 'attendance_factions.json' },
      { method: 'GET', path: '/persons', fixture: 'persons_list.json' },
      { method: 'GET', path: `/persons/${concretePersonUuid}`, fixture: 'person_detail.json' },
      { method: 'GET', path: `/persons/${concretePersonUuid}/stats`, fixture: 'person_stats.json' },
      { method: 'GET', path: `/persons/${concretePersonUuid}/attendance`, fixture: 'person_attendance.json' },
      { method: 'GET', path: `/persons/${concretePersonUuid}/speeches`, fixture: 'person_speeches.json' },
      { method: 'GET', path: `/persons/${concretePersonUuid}/faction-alignment`, fixture: 'person_alignment.json' },
      { method: 'GET', path: `/persons/${concretePersonUuid}/faction-alignment/differences`, fixture: 'person_diffs.json' },
      { method: 'GET', path: `/sessions/${concreteDate}`, fixture: 'session_detail.json' },
      { method: 'GET', path: '/votings', fixture: 'session_votings.json', queryParams: { sitting_date: concreteDate } },
      { method: 'GET', path: '/votings', fixture: 'votings_list.json' },
      { method: 'GET', path: `/votings/${concreteVotingUuid}`, fixture: 'voting_detail.json' },
      { method: 'GET', path: `/speeches/${concreteSpeechId}`, fixture: 'speech_detail.json' },
      { method: 'GET', path: `/speeches/${concreteSpeechId}/context`, fixture: 'speech_context.json' },
      { method: 'GET', path: `/drafts/${concreteDraftUuid}`, fixture: 'draft_detail.json' },
      { method: 'GET', path: `/drafts/${concreteDraftUuid}/speeches`, fixture: 'draft_speeches.json' },
      { method: 'GET', path: '/suggest', fixture: 'suggest.json', queryParams: { prefix: 'riigi' } },
      { method: 'GET', path: '/search/activity', fixture: 'search_activity.json', queryParams: { q: 'riigieelarve' } },
      { method: 'GET', path: '/search/speakers', fixture: 'search_speakers.json', queryParams: { q: 'riigieelarve' } },
      { method: 'GET', path: '/search', fixture: 'search_kliima_muutus.json', queryParams: { q: '"kliima muutus"' } },
      { method: 'GET', path: '/search', fixture: 'search_kliima_ja_mets.json', queryParams: { q: 'kliima mets' } },
      { method: 'GET', path: '/search', fixture: 'search_kliima_voi_mets.json', queryParams: { q: 'kliima, mets' } },
      { method: 'GET', path: '/search', fixture: 'search_kliima.json', queryParams: { q: 'kliima' } },
      { method: 'GET', path: '/search', fixture: 'search_sample.json', queryParams: { q: 'riigikogu' } },
    ],
  };

  fs.writeFileSync(
    path.join(FIXTURES_DIR, 'index.json'),
    JSON.stringify(index, null, 2) + '\n',
    'utf-8'
  );

  console.log(`Successfully captured ${fixtures.length} fixtures and index.json!`);
}

main().catch((err) => {
  console.error('Capture failed:', err);
  process.exit(1);
});
