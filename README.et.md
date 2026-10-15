# Riigikogu stenogrammide otsing

[![CI](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml/badge.svg)](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml)
[![Riigikogu Daily Data Pipeline](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/daily_pipeline.yml/badge.svg)](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/daily_pipeline.yml)

[English README](README.md)

Kiire täistekstotsingu ja analüütika veebirakendus Eesti Riigikogu stenogrammidele ja istungite protokollidele (andmed alates 2019. aastast).

Tehnoloogiline virn: FastAPI, React + Vite, EstNLTK (eesti keele morfoloogiline analüüs ja lemmatiseerimine) ning SQLite.

---

## Funktsionaalsus

- **Morfanalüüsil põhinev otsing:** Otsib sõnade algvormide (lemmade) järgi EstNLTK abil.
- **Paindlik otsinguloogika:**
  - Mitmesõnaline `AND` otsing: `tartu ülikool` (leiab kõned, kus esinevad mõlemad sõnad)
  - Komaga eraldatud `OR` otsing: `kliima, ilm` (leiab kõned, kus esineb vähemalt üks märksõna)
  - Kombineeritud päringud: `kliima muutus, taastuv energia` -> `(kliima AND muutus) OR (taastuv AND energia)`
- **Aktiivsus ajas:** Visualiseerib märksõnade sagedust kuude, nädalate või päevade lõikes pideva graafikuna.
- **Top kõnelejad:** Kuvab saadikud, kes on valitud märksõnu enim kasutanud.
- **Kohaloleku ja fraktsioonide seosed:** Seob stenogrammid saadikute kohalolekukontrolli andmetega.
- **Püsivad isikud ja püsilingid:** Kõik saadikute kõned on seotud ametlike UUID-dega (koos `ems_id` talletamise ja ministrite-saadikute lahendamisega), stabiilse `speech_key` tunnusega ning püsilingi aliastabeliga (`speech_aliases`), mis suunab toimetamata kõnede vanad Riigikogu ID-d toimetatud versiooni avalikustamisel uuele kõnele.
- **Dünaamilised koosseisud:** Koosseisude kuupäevad ja valikud laetakse automaatselt Riigikogu ametlikust API-st koos jooksva dünaamilise uuendamisega.
- **Andmetoru terviklikkus ja statistika verifitseerimine:** Andmetoru kontrollib igaöiselt istungite täielikkust otse Riigikogu API vastu (`verify_pipeline_integrity.py`), toetab kõnede mahu pistelist kontrolli ametliku statistikaga (`verify_statistics.py`) ja monitoorib süsteemi tervist (`/system/status`).
- **Läbipaistev metoodika:** Kasutajaliideses on selgitatud kohaloleku, kõnede ja toimetamata tekstide arvestuse põhimõtted.
- **Kasutajaliides:** Reageeriv React rakendus Dark / Light režiimi toega.
- **Automaatne andmetoru:** Igaöine GitHub Actions töövoog laeb uued stenogrammid, kontrollib andmete terviklikkust ja sünkroniseerib need Backblaze B2 pilvesalvestusega.

---

## Tehnoloogiline virn

| Kiht | Tehnoloogiad |
| :--- | :--- |
| **Frontend** | React 19, Vite, Recharts, ESLint 10, Prettier |
| **Backend & API** | Python 3.10+, FastAPI, Uvicorn, SQLAlchemy, SQLite |
| **Keeletöötlus (NLP)** | EstNLTK, NLTK |
| **Andmetorud & pilv** | GitHub Actions, Backblaze B2, Requests |
| **Paigaldus & konteinerid** | Docker, Docker Compose, Cloudflare Tunnel |
| **Koodikvaliteet & CI** | Ruff (Python), ESLint + Prettier (JS/React), Pytest, Dependabot, GitHub Actions CI |

---

## Paigaldus ja käivitamine

### Eeltingimused
- Python 3.10+ (soovitatav Python 3.13)
- Node.js 20+ & npm
- Docker (valikuline, konteineris käivitamiseks)

### 1. Projekti allalaadimine
```bash
git clone https://github.com/spaceminx/riigikogu-stenogram-search.git
cd riigikogu-stenogram-search
```

### 2. Backendi seadistus
```bash
# Loo virtuaalkeskkond ja aktiveeri see
python3 -m venv .venv
source .venv/bin/activate  # Windowsis: .venv\Scripts\activate

# Paigalda vajalikud teegid
pip install -r requirements.txt
```

### 3. Andmebaasi loomine ja andmete ettevalmistus
Käivita täielik andmebaasi ehitamise skript (laeb vajadusel B2-st andmed, lemmatiseerib tekstid paralleelselt ja loob SQLite indeksid):
```bash
python scripts/build_full_database.py
```

*Märkus ajaloo uuendamise kohta:*
Igapäevane automaatne sünkroonimine serveris (`sync_database.py`) laeb B2-st alla ainult aktiivsete aastate andmed (jooksev aasta ning eelmine aasta seni, kuni see jääb 60 päeva aknasse, umbes 1. märtsini) ning uuendab vaid uusi või poolikuid istungeid. Kui varasemate aastate andmeid muudetakse (näiteks puuduva ajaloo tagasitäitmisel või andmemudeli uuendamisel), ei uuenda `build_full_database.py` olemasolevas andmebaasis juba olevaid istungeid. Uue ajaloo rakendamiseks ehita uus fail, peata API, vaheta andmebaasifail ning kontrolli WAL ajutisi faile:
```bash
python scripts/download_from_b2.py --all

# 1. Ehita uus andmebaas (soovitatavalt konteineris, et tagada õiged failiõigused)
docker compose run --rm -e DATABASE_URL=sqlite:///database/riigikogu_new.sqlite backend python scripts/build_full_database.py
# Kui ehitad hostis, kontrolli ja muuda vajadusel uue faili omanikku (chown), et appuser saaks seda lugeda/kirjutada:
# DATABASE_URL=sqlite:///database/riigikogu_new.sqlite python scripts/build_full_database.py

# 2. Peata API ja puhasta vanad WAL ajutised failid
docker compose stop backend
rm -f database/riigikogu.sqlite-wal database/riigikogu.sqlite-shm

# 3. Kontrolli, et uuel failil ei oleks .sqlite-wal faili kõrval
if [ -f database/riigikogu_new.sqlite-wal ]; then echo "VIGA: Uue andmebaasi WAL fail on olemas, andmed pole lõplikud!"; exit 1; fi

# 4. Asenda andmebaasifail ja taaskäivita
mv database/riigikogu_new.sqlite database/riigikogu.sqlite
docker compose start backend
```

### 4. Ajaloo tagasitäitmine (`backfill_history.py`)
Varasemate istungite (2019–2026) rikaste metaandmete (`external_id`, `ems_id`, `speech_type`, `start_time`, `end_time`, `duration_seconds`) tagasitäitmiseks:
1. Laadi B2-st kõik ajaloolised failid alla:
   ```bash
   python scripts/download_from_b2.py --all
   ```
2. Käivita testkäivitus ühe aasta kohta aruande vaatamiseks:
   ```bash
   python scripts/backfill_history.py --year 2021 --dry-run
   ```
3. Käivita päriselt tagasitäitmine aasta kaupa koos `--upload`-iga või eraldi `--upload-only --year YYYY`:
   ```bash
   python scripts/backfill_history.py --year 2021 --upload
   # või eraldi sammudena:
   # python scripts/backfill_history.py --year 2021
   # python scripts/backfill_history.py --upload-only --year 2021
   ```
4. Serveris: ehita andmebaas uuesti, järgides eespool toodud juhist jaotises "Märkus ajaloo uuendamise kohta" (uus fail `DATABASE_URL`-iga konteineris, `docker compose stop backend`, WAL-faili kontroll, `mv`, `docker compose start backend`).

> [!NOTE]
> Vaikimisi lõppkuupäev (täna miinus `UNEDITED_REFETCH_DAYS`) jätab vahele hiljuti toimetatud istungid, mida vana kood juba toimetatuna salvestas (näiteks september 2026). Neid ei uuenda ka igapäevane andmetoru. Nende uuendamiseks käivita eraldi:
> ```bash
> python scripts/backfill_history.py --start-date 2026-09-01 --end-date <täna> --upload
> ```
> Jooksva aasta faili kaitseb B2-s samaaegsuse ja ETag-i kontroll.

### Hääletuste ajaloo laadimine (ühekordne)

Hääletuste ajaloo (2019 kuni tänaseni) esmane laadimine käib serveris konteineri sees (`backend` teenus).

Täpne järjekord:
1. Laadi 2019. aasta hääletused (alates 14. koosseisu algusest 01.04.2019) ja saada Backblaze B2-sse:
   ```bash
   docker compose exec backend python scripts/fetch_votes.py --start-date 2019-04-01 --end-date 2019-12-31 --upload
   ```
2. Laadi aastad 2020–2025 aastapõhise tsüklina ja saada B2-sse:
   ```bash
   for y in {2020..2025}; do
     docker compose exec backend python scripts/fetch_votes.py --start-date ${y}-01-01 --end-date ${y}-12-31 --upload
   done
   ```
3. Laadi jooksva 2026. aasta hääletused ja saada B2-sse:
   ```bash
   docker compose exec backend python scripts/fetch_votes.py --start-date 2026-01-01 --upload
   ```
4. Laadi kõik hääletused serveri SQLite andmebaasi:
   ```bash
   docker compose exec backend python scripts/load_votes.py
   ```
5. Kontroll:
   ```bash
   curl http://127.0.0.1:8000/system/status
   # votings = 3621 + pärast 13.10 lisandunud

   curl "http://127.0.0.1:8000/votings?start_date=2026-09-29&end_date=2026-09-29"
   ```

> [!NOTE]
> **Olulised märkused juurutamisel:**
> - Kuni samm 3 pole tehtud, toob igapäevane pipeline ainult viimased 14 päeva.
> - **Käivituse ajastus:** Aastaid 2019–2025 võib jooksutada igal ajal, sest GitHub Actions runner laeb alla ainult aktiivse aasta faile ega kirjuta vanu votes-faile B2-sse. Ainult 2026 käivitus (samm 3) ei tohi joosta kella 07:00 UTC paiku (mil töötab igapäevane andmetoru).
> - **Tõrketaluvus:** Skript teeb vahesalvestusi iga 25 hääletuse järel ning püüab katkestused (Ctrl-C / SIGTERM). Kui mõni aasta lõpetab koodiga 1 (nt ajutine API võrgutõrge), käivita sama aasta käsk uuesti – juba salvestatud hääletused jäetakse vahele ja laadimine jätkub poolelijäänud kohast.
> - **Hinnangulised ajad aastate kaupa** (~5,1 s hääletuse kohta):
>   - 2019: 172 hääletust → ~15 min
>   - 2020: 356 hääletust → ~30 min
>   - 2021: 533 hääletust → ~45 min
>   - 2022: 718 hääletust → ~61 min
>   - 2023: 436 hääletust → ~37 min
>   - 2024: 692 hääletust → ~59 min
>   - 2025: 402 hääletust → ~34 min
>   - 2026: 312 hääletust → ~27 min

### 5. Kohaloleku UUID-de migratsioon (`repair_attendance_uuids.py`)
Saadikute `member_uuid` sidumiseks olemasolevate kohaloleku andmetega (`data/processed/attendance.jsonl`) ja SQLite `attendance` tabeliga:
1. Käivita kuivkäivitus, et vaadata vastavusse viimise statistikat ilma faile muutmata:
   ```bash
   python scripts/repair_attendance_uuids.py --dry-run
   ```
2. Rakenda muudatused kohalikult, laadi uuendatud `attendance.jsonl` Backblaze B2-sse ja uuenda andmebaas:
   ```bash
   python scripts/repair_attendance_uuids.py --apply --upload --db database/riigikogu.sqlite
   ```
   *Märkus:* Skeemi migratsioon (`ensure_schema()`) toimub automaatselt ja idempotentselt rakenduse käivitumisel, lisades tabelisse veeru `member_uuid TEXT` ja indeksi `idx_attendance_member_uuid`, kui need veel puuduvad.

### 6. FastAPI serveri käivitamine
```bash
uvicorn src.api.main:app --reload --port 8000
```
API dokumentatsiooniga saab tutvuda aadressidel:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Redoc: `http://127.0.0.1:8000/redoc`

### 7. Frontendi käivitamine
Ava uus terminaliaken:
```bash
cd src/frontend
npm install
npm run dev
```
Ava brauseris `http://localhost:5173`.

---

## Paigaldus ja pidev integratsioon (CI/CD)

Tootmiskeskkonna paigaldus käivitub automaatselt pärast `master` haru CI õnnestumist või käsitsi käivitades töövootagant `.github/workflows/deploy.yml`.

### Paigalduse seadistamine
Serveri `self-hosted` runner vajab repositooriumi saladust (secret) `DEPLOY_DIR`:
- Ava repositooriumi **Settings** -> **Secrets and variables** -> **Actions** -> **Secrets**.
- Lisa saladus (secret) `DEPLOY_DIR`, mis määrab projekti kataloogitee serveris (nt `/home/<kasutaja>/riigikogu-stenogram-search`).

### Tootmiskeskkonna migratsioon
Uute skeemimuudatuste või andmetäienduste (nt kohaloleku `member_uuid` veerg) tootmisse viimisel:
1. Koodi paigaldamisel teostab rakenduse käivitus vajadusel puuduvate veergude ja indeksite lisamise automaatselt (`ensure_schema()`).
2. Ajalooliste kohaloleku kirjete UUID-de täitmiseks serveris käivita:
   ```bash
   docker compose run --rm backend python scripts/repair_attendance_uuids.py --apply --upload --db database/riigikogu.sqlite
   ```
   Eraldi uut tõmmise ehitamist ega teenuse katkestust vaja ei ole.

---

## Testimine ja koodikvaliteet

Projekt kasutab koodikontrolliks Ruffi, ESLint + Prettierit ning automaattestideks Pytesti.

### Automaattestid
```bash
# Käivita backendi ja API testid
pytest -v
```

### Python (Backend & skriptid)
```bash
# Kontrolli koodi ja paranda impordid / vead automaatselt
ruff check . --fix

# Vorminda kood
ruff format .
```

### Frontend (React / JS)
```bash
cd src/frontend

# Koodikontroll
npm run lint
npm run lint:fix

# Vormindamine Prettieriga
npm run format
npm run format:check
```

---

## Projekti struktuur

```text
riigikogu-stenogram-search/
├── .github/
│   ├── dependabot.yml             # Dependaboti iganädalane automaatne turvaseire
│   └── workflows/
│       ├── ci.yml                 # Automaatne CI (Ruff, ESLint, Prettier, Pytest, Vite build)
│       ├── deploy.yml             # Automaatne serverisse paigaldus pärast masteri CI õnnestumist
│       └── daily_pipeline.yml     # Igaöine andmetoru (B2 sünkroonimine, API kraapija, terviklikkuse kontroll)
├── config.py                      # Globaalsed seadistused ja dünaamilised koosseisude kuupäevad
├── docker-compose.yml             # Multi-container Docker paigaldus
├── Dockerfile                     # Tootmistasemel backend Docker konteiner
├── pyproject.toml                 # Ruffi, pytesti ja projekti seadistused
├── requirements.txt               # Backendi Pythoni sõltuvused
├── scripts/
│   ├── backfill_history.py        # Ajalooliste stenogrammide rikaste andmete tagasitäitmine
│   ├── build_full_database.py     # Paralleelne täielik andmebaasi ehitaja
│   ├── download_all_from_b2.py    # Kõigi andmete ja olekute allalaadija B2-st
│   ├── download_from_b2.py        # Igapäevane inkrementaalne B2 allalaadija
│   ├── fetch_attendance.py        # Kohaloleku ja hääletuste allalaadija
│   ├── fetch_factions.py          # Fraktsioonide kuuluvuse ajaloo ja isikute allalaadija
│   ├── fetch_memberships.py       # Koosseisude (XIV, XV jne) allalaadija Riigikogu API-st
│   ├── fetch_stenograms_api.py    # Stenogrammide allalaadija Riigikogu API-st
│   ├── repair_attendance_uuids.py # Täidab kohaloleku kirjetes ja andmebaasis member_uuid
│   ├── repair_speaker_uuids.py    # Kõnelejate UUID lahendaja ja parandaja
│   ├── sync_database.py           # SQLite andmebaasi uuendaja ja aliashaldur
│   ├── upload_to_b2.py            # Backblaze B2 üleslaadija andmetele ja olekutele
│   ├── verify_pipeline_integrity.py # Andmetoru terviklikkuse ja istungite kontroll Riigikogu API vastu
│   └── verify_statistics.py       # Ametliku kõnestatistika ristkontrolli skript
├── src/
│   ├── api/                       # FastAPI marsruudid ja loogika
│   │   ├── main.py                # Rakenduse peafail ja CORS seaded
│   │   ├── routes.py              # API endpointide definitsioonid
│   │   ├── search.py              # Otsingu ja analüütika funktsioonid
│   │   └── attendance.py          # Kohaloleku päringud
│   ├── transform/                 # Tekstitöötlus ja morfoloogia
│   │   ├── lemmatizer.py          # EstNLTK paralleelne lemmatiseerija
│   │   └── term_builder.py        # Lemmade sagedusindeksi ehitaja
│   ├── load/                      # Andmebaasimudelid ja laadimine
│   │   ├── models.py              # SQLAlchemy mudelid (kõned, aliased, kohalolek)
│   │   └── loader.py              # JSONL failide laadimine SQLite baasi koos aliastabeliga
│   └── frontend/                  # React + Vite kasutajaliides
│       ├── eslint.config.js       # ESLint konfiguratsioon
│       ├── package.json
│       └── src/
│           ├── App.jsx            # Põhikomponent ja dashboard
│           └── api.js             # API klientpäringud
├── tests/
│   ├── test_api.py                # FastAPI endpointide integratsioonitestid
│   ├── test_pipeline.py           # Andmetoru, dünaamiliste kuupäevade ja terviklikkuse testid
│   └── test_query_parser.py       # Päringuparsija ja otsinguloogika ühiktestid
└── HOSTING.md                     # Majutuse ja arhitektuuri juhised
```

---

## Litsents

See projekt on avatud lähtekoodiga ja litsentseeritud [MIT litsentsi](LICENSE) alusel.
