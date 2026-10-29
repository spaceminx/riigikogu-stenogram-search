# Riigivaade – Riigikogu stenogrammide otsing

[![CI](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml/badge.svg)](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml)

[English README](README.md)

[Riigivaade](https://www.riigivaade.me) on erapooletu avalik leht Riigikogu kohta: täiskogu stenogrammide täistekstotsing, istungid, saadikute aktiivsus ja kohalolek, hääletused, eelnõud ja fraktsioonid. Andmed pärinevad Riigikogu avaandmete API-st (CC BY-SA), hõlmavad XIV ja XV koosseisu (alates 2019. aasta aprillist) ning uuenevad iga päev.

---

## Mis lehel on

- **Avaleht** (`/`): näidisteemad, sõnavõtud kuude kaupa, viimased istungid, kõige aktiivsemad kõnelejad ja kalender, kust saab avada mis tahes istungi.
- **Kõneotsing** (`/otsing`): otsib sõnade algvormide (lemmade) järgi, nii et „eelarve“ leiab ka „eelarvest“. Ühe ploki sõnad peavad kõik esinema, plokid on alternatiivid (`+ JA`, `+ VÕI`) ja mitmesõnaline plokk on täpne fraas. Filtrid: koosseis, fraktsioon, kuupäevad, esineja ja sõnavõtu liik, soovi korral ilma istungi juhatajata või ilma liitsõnadeta. Lisapaneelid näitavad mainimisi ajas (päev, nädal või kuu; arv või osakaal) ja saadikuid, kes teemat kõige rohkem mainivad. Iga tulemuse saab avada istungi kontekstis, tulemused saab alla laadida CSV või JSON failina ja igal otsingul on RSS-voog.
- **Istung** (`/istung/<kuupäev>`): istungi kogu stenogramm järjekorras, istungi hääletused, iga kõne video ja link allikale.
- **Kõne** (`/kone/<id>`): üks kõne püsilingiga, kõneleja, päevakorrapunkt, video ja allikas.
- **Saadik** (`/saadik/<id>`): aktiivsus ja osalus, kõned saadiku, ministri või istungi juhatajana, kohalolek ja hääletamine koalitsioonis ja opositsioonis olles, kõned aastate kaupa, kohalolek koosseisude kaupa, kui sageli saadik hääletas fraktsiooni enamusega (koos erinevate hääletustega) ning saadiku kõned koos RSS-vooga.
- **Kohalolek** (`/kohalolek`): kohalolekukontrollides registreerumine ja hääletustel osalemine saadikute või fraktsioonide kaupa, koosseisu, fraktsiooni ja rolli järgi, soovi korral ilma infotunnita.
- **Hääletused** (`/haaletused`, `/haaletus/<id>`): kõik täiskogu hääletused, otsitavad pealkirja või eelnõu järgi ja filtreeritavad kuupäeva ning liigi järgi. Hääletuse lehel on tulemus, iga fraktsiooni tulemus ja iga saadiku hääl; salajastel hääletustel ainult koondtulemus.
- **Eelnõu** (`/eelnou/<id>`): eelnõu lugemised ja arutelud koos hääletuste ja sõnavõttudega.
- **Fraktsioonid** (`/fraktsioonid`): iga fraktsiooni liikmed koosseisude kaupa, kohad koalitsioonis ja opositsioonis, esimehed ja aseesimehed ning endised liikmed.
- **Andmed ja privaatsus** (`/andmed`): kes lehte haldab, mida külastajate kohta kogutakse, avaandmete allalaadimine ja erapooletuse põhimõtted. Metoodika on avatav igalt lehelt.

Andmed avaldatakse ka igakuise avaandmete väljalaskena [GitHub Releasesis](https://github.com/spaceminx/riigikogu-stenogram-search/releases) (vt [docs/open-data.md](docs/open-data.md)).

---

## Tehniliselt

- **Lemmaindeks:** kõned lemmatiseeritakse EstNLTK-ga; otsing kasutab lemmaindeksit koos päringu laiendamise ja fraasiotsinguga.
- **Igapäevane andmetoru:** serveri töö laeb uued stenogrammid, hääletused, kohaloleku ja päevakorra, kontrollib neid Riigikogu API vastu, varundab Backblaze B2-sse ja uuendab andmebaasi ühe luku all.
- **Püsilingid:** kõnedel on stabiilsed võtmed ja aliased, nii et lingid töötavad ka pärast seda, kui Riigikogu stenogrammi toimetab.
- **Läbipaistvus:** `/system/status` näitab andmete värskust ning metoodika selgitab, kuidas kohalolekut, sõnavõtu liike ja toimetamata stenogramme arvestatakse.

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

## Dokumentatsioon

Tehniline dokumentatsioon on inglise keeles:

- [Arendus](docs/development.md): kohalik käivitamine, testid, koodikontroll, Pythoni sõltuvuste uuendamine, E2E testid, live ja upstream API kontrollid
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
