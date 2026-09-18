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
- **Kasutajaliides:** Reageeriv React rakendus Dark / Light režiimi toega.
- **Automaatne andmetoru:** Igaöine GitHub Actions töövoog laeb uued stenogrammid ja sünkroniseerib need Backblaze B2 pilvesalvestusega.

---

## Tehnoloogiline virn

| Kiht | Tehnoloogiad |
| :--- | :--- |
| **Frontend** | React 19, Vite, Recharts, ESLint 10, Prettier |
| **Backend & API** | Python 3.10+, FastAPI, Uvicorn, SQLAlchemy, SQLite |
| **Keeletöötlus (NLP)** | EstNLTK, NLTK |
| **Andmetorud & pilv** | GitHub Actions, Backblaze B2, BeautifulSoup4, Requests |
| **Koodikvaliteet & CI** | Ruff (Python), ESLint + Prettier (JS/React), GitHub Actions CI |

---

## Paigaldus ja käivitamine

### Eeltingimused
- Python 3.10+ (soovitatav Python 3.13)
- Node.js 20+ & npm

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

### 4. FastAPI serveri käivitamine
```bash
uvicorn src.api.main:app --reload --port 8000
```
API dokumentatsiooniga saab tutvuda aadressidel:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Redoc: `http://127.0.0.1:8000/redoc`

### 5. Frontendi käivitamine
Ava uus terminaliaken:
```bash
cd src/frontend
npm install
npm run dev
```
Ava brauseris `http://localhost:5173`.

---

## Koodikvaliteet ja vormindamine

Projekt kasutab Pythoni jaoks Ruffi ning frontendi jaoks ESLint + Prettierit.

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
│   └── workflows/
│       ├── ci.yml                 # Automaatne CI (Ruff, ESLint, Prettier, Vite build)
│       └── daily_pipeline.yml     # Igaöine kraapija ja B2 sünkroonimine
├── config.py                      # Globaalsed seadistused ja teekonnad
├── pyproject.toml                 # Ruffi ja projekti seadistused
├── requirements.txt               # Backendi Pythoni sõltuvused
├── scripts/
│   ├── build_full_database.py     # Paralleelne täielik andmebaasi ehitaja
│   ├── fetch_stenograms_api.py    # Stenogrammide allalaadija Riigikogu API-st
│   ├── fetch_factions.py          # Fraktsioonide allalaadija
│   ├── fetch_attendance.py        # Kohaloleku ja hääletuste allalaadija
│   └── upload_to_b2.py            # Backblaze B2 sünkroonija
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
│   │   ├── models.py              # SQLAlchemy mudelid
│   │   └── loader.py              # JSONL failide laadimine SQLite baasi
│   └── frontend/                  # React + Vite kasutajaliides
│       ├── eslint.config.js       # ESLint konfiguratsioon
│       ├── package.json
│       └── src/
│           ├── App.jsx            # Põhikomponent ja dashboard
│           └── api.js             # API klientpäringud
└── HOSTING.md                     # Majutuse ja arhitektuuri juhised
```

---

## Litsents

See projekt on avatud lähtekoodiga ja litsentseeritud [MIT litsentsi](LICENSE) alusel.
