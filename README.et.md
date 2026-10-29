# Riigivaade – Riigikogu stenogrammide otsing

[![CI](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml/badge.svg)](https://github.com/spaceminx/riigikogu-stenogram-search/actions/workflows/ci.yml)

[English README](README.md)

[Riigivaade](https://www.riigivaade.me) on erapooletu avalik leht Riigikogu kohta: täiskogu stenogrammide täistekstotsing, istungid, saadikute aktiivsus ja kohalolek, hääletused, eelnõud ja fraktsioonid. Andmed pärinevad Riigikogu avaandmete API-st (CC BY-SA), hõlmavad XIV ja XV koosseisu (alates 2019. aasta aprillist) ning uuenevad iga päev.

---

## Mis lehel on

Iga pilt avab sama lehe päris saidil. Piltidel on Riigikogu andmed ([api.riigikogu.ee](https://api.riigikogu.ee), CC BY-SA 3.0) ja pildid on sama litsentsi all; saadikute fotosid piltidel pole, sest Riigikogu fotode kasutustingimused ei luba koopiaid edasi anda.

### Kõneotsing

[![Kõneotsing sõnale „eelarve“ koos ajajoone ja kõnelejatega](docs/images/search.webp)](https://www.riigivaade.me/otsing?q=eelarve)

Otsib sõnade algvormide (lemmade) järgi, nii et „eelarve“ leiab ka „eelarvest“. Ühe ploki sõnad peavad kõik esinema, plokid on alternatiivid (`+ JA`, `+ VÕI`) ja mitmesõnaline plokk on täpne fraas. Filtrid: koosseis, fraktsioon, kuupäevad, esineja ja sõnavõtu liik, soovi korral ilma istungi juhatajata või ilma liitsõnadeta. Lisapaneelid näitavad mainimisi ajas (päev, nädal või kuu; arv või osakaal) ja saadikuid, kes teemat kõige rohkem mainivad. Iga tulemuse saab avada istungi kontekstis, tulemused saab alla laadida CSV või JSON failina ja igal otsingul on RSS-voog.

### Istung

[![26. oktoobri 2026 istungi stenogramm](docs/images/sitting.webp)](https://www.riigivaade.me/istung/2026-10-26)

Istungi kogu stenogramm järjekorras, istungi hääletused, iga kõne video ja link allikale. Igal kõnel on ka oma leht püsilingiga (`/kone/<id>`).

### Saadik

[![Riigikogu esimehe Lauri Hussari leht](docs/images/member.webp)](https://www.riigivaade.me/saadik/64c0141f-371b-4520-8a50-09e65231f775)

Aktiivsus ja osalus, kõned saadiku, ministri või istungi juhatajana, kohalolek ja hääletamine koalitsioonis ja opositsioonis olles, kõned aastate kaupa, kohalolek koosseisude kaupa, kui sageli saadik hääletas fraktsiooni enamusega (koos erinevate hääletustega) ning saadiku kõned koos RSS-vooga.

### Kohalolek

[![XV Riigikogu kohalolek fraktsioonide kaupa](docs/images/attendance.webp)](https://www.riigivaade.me/kohalolek?att_tab=factions)

Kohalolekukontrollides registreerumine ja hääletustel osalemine saadikute või fraktsioonide kaupa, koosseisu, fraktsiooni ja rolli järgi, soovi korral ilma infotunnita.

### Hääletused

[![Taimekaitseseaduse muutmise seaduse lõpphääletus](docs/images/vote.webp)](https://www.riigivaade.me/haaletus/f00ae6f6-bc70-4be6-8e1f-9e000b5d4f0f)

Kõik täiskogu hääletused, otsitavad pealkirja või eelnõu järgi ja filtreeritavad kuupäeva ning liigi järgi. Hääletuse lehel on tulemus, iga fraktsiooni tulemus ja iga saadiku hääl; salajastel hääletustel ainult koondtulemus.

### Eelnõu

[![Taimekaitseseaduse muutmise seaduse eelnõu lugemised](docs/images/bill.webp)](https://www.riigivaade.me/eelnou/1fdf1be7-b35c-44bf-9ed8-ab5d309838fd)

Eelnõu lugemised ja arutelud koos hääletuste ja sõnavõttudega.

### Fraktsioonid

[![XV Riigikogu fraktsioonid](docs/images/factions.webp)](https://www.riigivaade.me/fraktsioonid)

Iga fraktsiooni liikmed koosseisude kaupa, kohad koalitsioonis ja opositsioonis, esimehed ja aseesimehed ning endised liikmed.

### Lisaks

- **Avaleht** (`/`): näidisteemad, sõnavõtud kuude kaupa, viimased istungid, kõige aktiivsemad kõnelejad ja kalender, kust saab avada mis tahes istungi.
- **Andmed ja privaatsus** (`/andmed`): kes lehte haldab, mida külastajate kohta kogutakse, avaandmete allalaadimine ja erapooletuse põhimõtted. Metoodika on avatav igalt lehelt.

Andmed avaldatakse ka igakuise avaandmete väljalaskena [GitHub Releasesis](https://github.com/spaceminx/riigikogu-stenogram-search/releases) (vt [docs/open-data.md](docs/open-data.md)). Pildid tehakse käsuga `node scripts/capture_readme_screenshots.mjs`.

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
├── docs/               # Arenduse, käituse, andmete hoolduse, avaandmete ja API dokumentatsioon; README pildid
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

Kood on [MIT litsentsi](LICENSE) all. Andmed ja kaustas `docs/images/` olevad pildid on [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/deed.et) litsentsi all, allikas: Riigikogu.
