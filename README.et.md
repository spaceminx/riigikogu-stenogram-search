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
- Node.js 24 & npm
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
├── .github/            # CI, paigalduse, live API kontrolli ja varu-andmetoru töövood; Dependabot
├── docs/               # Arenduse, käituse, andmete hoolduse, avaandmete ja API dokumentatsioon
├── scripts/            # Andmetoru, allalaadijad, B2 sünkroniseerimine, parandused, väljalasked, varundus
├── src/
│   ├── api/            # FastAPI rakendus, marsruudid, otsingu ja kohaloleku päringud
│   ├── data/           # Staatilised viiteandmed (valitsused)
│   ├── fetch_models/   # Pydantic mudelid Riigikogu API vastustele
│   ├── load/           # SQLAlchemy mudelid, migratsioonid, indeksid, JSONL laadija
│   ├── transform/      # EstNLTK lemmatiseerija ja terminiindeksi ehitaja
│   └── frontend/       # React + Vite kasutajaliides (Vercel)
│       ├── e2e/        # Playwright testid ja salvestatud API vastused
│       ├── src/        # Komponendid, vaated, abiteegid, stiilid
│       └── test/       # Ühiktestid (node --test)
├── tests/              # Pytesti backendi, API ja andmetoru testid
├── config.py           # Globaalsed seadistused ja dünaamilised koosseisude kuupäevad
├── docker-compose.yml  # Backendi ja ühekordse andmetoru konteinerid
├── Dockerfile          # Mitmeastmeline tootmise backendi tõmmis
├── requirements.in     # Pythoni otsesed sõltuvused
├── requirements.txt    # Lukustatud Pythoni sõltuvused (uv genereerib)
└── requirements-dev.txt
```

---

## Litsents

See projekt on avatud lähtekoodiga ja litsentseeritud [MIT litsentsi](LICENSE) alusel.
