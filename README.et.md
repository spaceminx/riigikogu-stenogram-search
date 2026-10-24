# Riigikogu stenogrammide otsing

[![CI](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml/badge.svg)](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml)

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
- **Automaatne andmetoru:** Serveri igapäevane andmetoru laeb uued stenogrammid, kontrollib andmete terviklikkust, sünkroniseerib Backblaze B2 pilvesalvestusega ning uuendab andmebaasi ühtse luku all (koos käsitsi käivitatava GitHub Actions varuvariandiga).

---

## Tehnoloogiline virn

| Kiht | Tehnoloogiad |
| :--- | :--- |
| **Frontend** | React 19, Vite, Recharts, ESLint 10, Prettier |
| **Backend & API** | Python 3.10+, FastAPI, Uvicorn, SQLAlchemy, SQLite |
| **Keeletöötlus (NLP)** | EstNLTK, NLTK |
| **Andmetorud & pilv** | Serveri cron, Backblaze B2, Requests, GitHub Actions |
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

Tootmisandmebaasi uuesti ehitamine, ajaloo tagasitäitmine ja parandusskriptid: [docs/data-maintenance.md](docs/data-maintenance.md).

### 4. FastAPI serveri käivitamine
```bash
uvicorn src.api.main:app --reload --port 8000
```
API dokumentatsiooniga saab tutvuda aadressidel:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Redoc: `http://127.0.0.1:8000/redoc`

Peamised endpointid: [docs/api.md](docs/api.md).

### 5. Frontendi käivitamine
Ava uus terminaliaken:
```bash
cd src/frontend
npm install
npm run dev
```
Ava brauseris `http://localhost:5173`.

---

## Dokumentatsioon

Tehniline dokumentatsioon on inglise keeles:

- [Arendus](docs/development.md): testid, koodikontroll, Pythoni sõltuvuste uuendamine, E2E testid, live ja upstream API kontrollid
- [Paigaldus ja käitus](docs/operations.md): paigaldus, skeemimuudatused, serveri igapäevane andmetoru, cron, andmebaasi varundus
- [Andmete hooldus](docs/data-maintenance.md): andmebaasi uuesti ehitamine, ajaloo tagasitäitmine, hääletuste esmane laadimine, UUID parandused, B2 sünkroniseerimine
- [Avaandmed](docs/open-data.md): väljalaske ehitamine, avaldamine ja igakuine väljalase
- [API](docs/api.md): peamised endpointid

---

## Projekti struktuur

```text
riigikogu-stenogram-search/
├── .github/
│   ├── dependabot.yml             # Dependaboti iganädalane automaatne turvaseire
│   └── workflows/
│       ├── ci.yml                 # Automaatne CI (Ruff, ESLint, Prettier, Pytest, Vite build)
│       ├── deploy.yml             # Automaatne serverisse paigaldus pärast masteri CI õnnestumist
│       └── daily_pipeline.yml     # Käsitsi käivitatav varu-andmetoru (GitHub Actions)
├── config.py                      # Globaalsed seadistused ja dünaamilised koosseisude kuupäevad
├── docker-compose.yml             # Multi-container Docker paigaldus
├── Dockerfile                     # Tootmistasemel backend Docker konteiner
├── pyproject.toml                 # Ruffi, pytesti ja projekti seadistused
├── requirements.txt               # Backendi Pythoni sõltuvused
├── scripts/
│   ├── backfill_history.py        # Ajalooliste stenogrammide rikaste andmete tagasitäitmine
│   ├── build_full_database.py     # Paralleelne täielik andmebaasi ehitaja
│   ├── daily_pipeline.py          # Serveri igapäevane andmetoru
│   ├── download_all_from_b2.py    # Kõigi andmete ja olekute allalaadija B2-st
│   ├── download_from_b2.py        # Igapäevane inkrementaalne B2 allalaadija
│   ├── fetch_attendance.py        # Kohaloleku ja hääletuste allalaadija
│   ├── fetch_factions.py          # Fraktsioonide kuuluvuse ajaloo ja isikute allalaadija
│   ├── fetch_memberships.py       # Koosseisude (XIV, XV jne) allalaadija Riigikogu API-st
│   ├── fetch_stenograms_api.py    # Stenogrammide allalaadija Riigikogu API-st
│   ├── remove_ignored_sessions.py # Eemaldab ignoreeritud istungid JSONL-ist ja andmebaasist
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
