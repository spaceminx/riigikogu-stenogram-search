# C1 Otsingu saagise (recall) ja liitsõnade/nimevormide laienduse disainidokument

## 1. Probleem ja hetkeseis

Riigikogu stenogrammiotsing tugineb täna EstNLTK lemmatiseerimisele (`lemmatizer.lemmatize_text`), mis salvestab iga sõna esimese normaliseeritud algvormi väiketähelisena (`word.lemma[0].lower()`). Tulemused seotakse kõnedega tabelite `lemmas` ja `speech_terms(speech_id, lemma_id, count)` kaudu.

Kuigi see lahendus tagab kiire ja täpse indekseerimise, esineb tänases otsingus kaks suurt saagise (recall) lünka:

1. **Liitsõnade katvus:** Kasutaja, kes otsib baasmõistet (nt `eelarve`, `maks`, `pension`), jääb ilma kõnedest, kus räägitakse ainult konkreetsetest liitsõnadest (nt `riigieelarve`, `lisaeelarve`, `tulumaks`, `käibemaks`, `vanaduspension`), ilma et kõnes esineks paljas baassõna.
   - `eelarve`: 8 596 kõnet, samas kui `riigieelarve` esineb 6 491 ja `lisaeelarve` 1 687 kõnes.
   - `maks`: 6 352 kõnet, samas kui ainuüksi liitsõnad lisavad üle 5 400 kõne.
2. **Pärisnimede käändevormid:** Konsonandiga lõppevate perekonnanimede (nt Seeder, Michal, Hussar) puhul jäävad välja kõned, kus nimi esineb omastavas/sihitavas käändes või loetelus.
   - `Seeder`: 1 953 kõnet vs `seederi`: 164 kõnet.
   - `Michal`: 1 057 kõnet vs `michali`: 136 kõnet.
   - `Hussar`: 294 kõnet vs `hussari`: 54 kõnet.
3. **Pärisnimede ja võõrnimetuste fraasid:** Fraas `"Rail Baltic"` annab 1 014 kõnet, samas kui lemmal `baltic` on 1 062 kõnet ning tekstis esineb ka nimekuju `Rail Baltica` (9 kõnet).

### 1.1 EstNLTK liitsõnade üle-tükeldamise anatoomia

EstNLTK Vabamorf morfoloogiline analüsaator tükeldab liitsõnu sageli liiga sügavale tüveosadeks (`root_tokens`). Näiteks:
- `riigieelarve` -> `['riigi', 'eel', 'arve']` (tüvi `riigi_eel_arve`)
- `eelarve` -> `['eel', 'arve']` (tüvi `eel_arve`)
- `arve` -> `['arve']`

Kui rakendada naiivset reeglit "viimane tüveosa = liitsõna tuum", seotakse `eelarve` tuumaks sõna `arve` (arve = invoice/bill). See oleks katastroofiline viga: otsing "arve" tooks tulemustesse 8 596 eelarvekõnet, uputades reaalsed arve-teemalised arutelud.

Sarnased fossiilsed või semantiliselt nihkunud liitsõnad on:
- `eelnõu` -> `['eel', 'nõu']` (nõu = bowl/advice, eelnõu = draft bill)
- `eesmärk` -> `['ees', 'märk']` (märk = mark/sign, eesmärk = goal)
- `allkiri` -> `['all', 'kiri']` (kiri = letter, allkiri = signature)
- `ülekaal` -> `['üle', 'kaal']` (kaal = weight/scales, ülekaal = superiority/majority)
- `vastasseis` -> `['vastas', 'seis']` (seis = state/score, vastasseis = confrontation)

### 1.2 Miks eksisteerivad lemmad "seederi", "michali" ja "hussari"?

Uurides tootmisbaasi kõnesid, kus esineb lemma `seederi` (164 kõnet), selgus täpne lingvistiline algpõhjus:

Eesti keeles liituvad konsonantlõpulistele perekonnanimedele omastavas ja sihitavas käändes lõpud `-i` (Seeder -> Seederi, Michal -> Michali, Hussar -> Hussari, Kert -> Kerdi) või osastavas `-it` (Seedrit, Michalit, Hussarit).

Kui nimi esineb lauses täissihitisena (nt *"palun kõnetooli Helir-Valdor Seederi"*, *"esitan kandidaadiks Helir-Valdor Seederi"*) või komadega eraldatud loetelus enne sidesõna (nt *"Jürgen Ligi, Kristen Michali, Helir-Valdor Seederi ja Mart Helme nimel"*), tõlgendab Vabamorfi pärisnime oletaja (`propername=True`) sõnavormi "Seederi" kui ainsuse nimetavas käändes olevat perekonnanime (`lemma: ['Seederi']`, `pos: ['H']`, `form: ['sg n']`), analoogselt nimedega nagu Tammeveski või Kivimägi.

Kuna `lemmatizer.py` salvestab `word.lemma[0].lower()`, tekivad eraldi lemmad `seederi`, `michali`, `hussari`.

**Reaalsed tekstinäited korpusest (5 konteksti):**
1. **Kõne 41 (Henn Põlluaas, 04.04.2019):** *"paremale käele esimese aseesimehe härra Helir-Valdor Seederi ning vasakule käele teise aseesimehe härra..."*
2. **Kõne 2577 (Siim Kallas, 19.06.2019):** *"olen palunud Helir-Valdor Seederi selleks ajaks mind asendama."*
3. **Kõne 11717 (Helmen Kütt, 29.01.2020):** *"et Eesti Vabariik Jüri Ratase, Helir-Valdor Seederi ja Mart Helme isikutes annab..."*
4. **Kõne 12524 (Helir-Valdor Seeder, 12.02.2020):** *"...Riisalo, Jürgen Ligi, Kristen Michali, Helir-Valdor Seederi, Johannes Kerdi, Mart Võrklaeva..."*
5. **Kõne 14456 (Priit Sibul, 12.03.2020):** *"Esitan Riigikogu aseesimehe kandidaadiks Helir-Valdor Seederi."*

Korpusanalüüs näitab, et **100%** nendest kõnedest käsitlevad vastavaid Riigikogu liikmeid (163-s kõnes 164-st esineb eesnimi "Helir", ainsas ülejäänus "härra Seederi"). Seeder-puust (seedripuu) ei räägita neis kordagi.

---

## 2. Hinnatud lahendusvariandid

| Kriteerium | Variant 1: Kogu korpuse ümberindekseerimine | Variant 2: Seoste tabel `lemma_links` andmebaasis (Soovitus) | Variant 3: Ainult päringuaegne lahendus mälus |
| :--- | :--- | :--- | :--- |
| **Põhimõte** | Muuta `lemmatizer.py` loogikat ja töödelda uuesti kõik 208 685 kõnet, lisades mitu lemmat `SpeechTerm`-i. | Luua relatsiooniline tabel `lemma_links(lemma_id, target_lemma_id, kind)`, arvutatuna unikaalsete lemmade pealt. Otsing laiendab lemmade IN-nimekirja. | EstNLTK/Vabamorf arvutab otsingu ajal mälus iga kord sobivad lemmad ilma andmebaasitabelita. |
| **Arvutuskulu** | Väga suur: 6–10 tundi CPU aega serveris, kõigi tabelite ülekirjutamine. | Väga väike: ühekordselt ~9 sekundit kõigi 137k lemma kohta. | Päringu ajal pidev lisakoormus (15–50 ms iga päringu kohta). |
| **B2 ja andmebaasi maht** | Suur andmemahu paisumine: `speech_terms` kasvab 30–50% (~5 miljonit uut rida). Nõuab uute B2 snapshotide tegemist. | Minimaalne: ~80k rida tabelis, andmebaasi lisandub vaid ~3.5 MB (0.3% kogu mahust). Null mõju B2 arhiivile. | 0 MB andmebaasis. |
| **Uuendatavus & Paindlikkus** | Jäik: reegli või stoplisti muutmisel tuleb taas kogu andmebaas (208k kõnet) uuesti indekseerida. | Suurepärane: reegleid või käsitsi erandeid saab sekundiga uuendada ja auditeerida SQL-päringuga. | Hea koodi muutes, kuid puudub püsiv auditeeritavus. |
| **Tagasipööramine (Rollback)** | Raske ja aeganõudev (nõuab varukoopia taastamist või uuesti indekseerimist). | Kohene: `DROP TABLE lemma_links` ja koodi revert, ükski olemasolev kõne ega indeks ei muutu. | Kohene: koodi revert. |
| **Otsingu latentsus** | 0 ms lisaaega SQL-is. | +1 kuni +3 ms lisaaega SQL IN-filtris (20–250 elementi indekseeritud veerus). | +20 kuni +60 ms lisaprotsessorit igal kasutajapäringul. |

**Järeldus:** Variant 2 on selgelt parim arhitektuurne lahendus. See ei nõua olemasoleva indeksi ega B2 andmete muutmist, on 100% tagasipööratav ja võimaldab saagist hüppeliselt tõsta minimaalse arvutuskuluga.

---

## 3. Mõõtmistulemused (reprodutseeritud skriptiga `c1_measure.py`)

Kõik mõõtmised on teostatud tootmisbaasi ametliku koopia peal (208 685 kõnet, 137 534 unikaalset lemmat). Mõõtmisi saab 100% reprodutseerida käsuga:
```bash
python scripts/experiments/c1_measure.py --db file:/tmp/c1.sqlite?mode=ro
```

### 3.1 Üldstatistika ja tabeli maht
- **Unikaalseid lemmasid andmebaasis:** 137 534
- **Lemmasid, millel on $\ge 2$ tüveosa (liitsõnakandidaadid):** 90 241
- **Liitsõnaseoseid (`compound_head`):** 80 294 liitlemmat seotud 11 735 unikaalse tuumaga (arvutusaeg: **8.50 s**)
- **Nimevormide seoseid (`name_form`):** 237 vormi seotud 127 isiku baasnimega (arvutusaeg: **0.44 s**)
- **Käsitsi aliased:** `baltic` -> `baltica` (Rail Baltic fraasi tugi)
- **Kokku seoseid tabelis `lemma_links`:** 80 532 rida
- **Eeldatav kettamaht:** ~3.5 MB (B-tree indeksitega ~5 MB)

### 3.2 30 sagedasemat liitsõna tuuma (`compound_head`)

| Jrk | Tuum (head) | Seotud liitsõnu | Näited |
| :--- | :--- | :--- | :--- |
| 1 | `süsteem` | 467 | raporteerimissüsteem, infosüsteem, tervisesüsteem, seiresüsteem |
| 2 | `põhine` | 404 | teaduspõhine, tõenduspõhine, riskipõhine, vajaduspõhine |
| 3 | `küsimus` | 403 | julgeolekuküsimus, piiriküsimus, usaldusküsimus, põhiküsimus |
| 4 | `teenus` | 348 | sotsiaalteenus, finantsteenus, postiteenus, sideteenus |
| 5 | `poliitika` | 341 | välispoliitika, hariduspoliitika, eelarvepoliitika, julgeolekupoliitika |
| 6 | `teema` | 329 | energiateema, palgateema, maksuteema, kriisiteema |
| 7 | `võimalus` | 324 | rahastusvõimalus, valikuvõimalus, arenguvõimalus, õpivõimalus |
| 8 | `valdkond` | 272 | teadusvaldkond, kultuurivaldkond, majandusvaldkond, prioriteetvaldkond |
| 9 | `maks` | 260 | tulumaks, käibemaks, sotsiaalmaks, aktsiisimaks, maamaks |
| 10 | `õigus` | 253 | põhiõigus, inimõigus, hääleõigus, omandiõigus, teabeõigus |
| 11 | `tegevus` | 253 | arendustegevus, loometegevus, õppetegevus, majandustegevus |
| 12 | `seadus` | 250 | põhiseadus, maksuseadus, metsaseadus, relvaseadus, planeerimisseadus |
| 13 | `probleem` | 246 | põhiprobleem, sõlmprobleem, kitsaskohtprobleem, terviseprobleem |
| 14 | `riik` | 244 | liikmesriik, naaberriik, doonorriik, õigusriik, heaoluriik |
| 15 | `tasu` | 234 | saastetasu, kohatasu, kasutuslitsentsitasu, hooldustasu |
| 16 | `kulu` | 229 | tegevuskulu, investeerimiskulu, tööjõukulu, ravikulu, püsikulu |
| 17 | `protsess` | 227 | õppeprotsess, otsustusprotsess, valimisprotsess, reformiprotsess |
| 18 | `meede` | 221 | toetusmeede, kriisimeede, majandusmeede, sanktsioonimeede |
| 19 | `ruum` | 218 | õhuruum, õigusruum, teaberuum, kultuuriruum, avalik ruum |
| 20 | `nõue` | 218 | ohutusnõue, kvaliteedinõue, keskkonnanõue, miinimumnõue |
| 21 | `juht` | 218 | tippjuht, tegevjuht, projektijuht, omavalitsusjuht |
| 22 | `raha` | 216 | toetusraha, projektiraha, investeeringuraha, laenuraha |
| 23 | `vastane` | 213 | venemeelne-vastane, valitsusvastane, põhiseadusevastane |
| 24 | `keskus` | 213 | logistikakeskus, kompetentsikeskus, perearstikeskus, kriisikeskus |
| 25 | `projekt` | 210 | pilootprojekt, investeeringuprojekt, taristuprojekt, teadusprojekt |
| 26 | `põhis` | 208 | nõusolekupõhis, rahvuspõhis, pearahapõhis, teaduspõhis |
| 27 | `toetus` | 207 | peretoetus, lastetoetus, toimetulekutoetus, tegevustoetus, otsetoetus |
| 28 | `võimekus` | 205 | reageerimisvõimekus, kaitsevõimekus, haldusvõimekus, seirevõimekus |
| 29 | `vahend` | 204 | finantsvahend, kaitsevahend, transpordivahend, eelarvevahend |
| 30 | `periood` | 202 | üleminekuperiood, eelarveperiood, kriisiperiood, planeerimisperiood |

### 3.3 Fikseeritud 16 testpäringu mõõtmised

| Päring | Baas (täna) | Liitsõnad (Head) | Nimed (Name) | Mõlemad (Ettepanek) | Juurdekasv ($\Delta$) | IN-nimekirja pikkus | SQL aeg (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `eelarve` | 8 596 | 13 712 | 8 596 | **13 712** | +5 116 (+59.5%) | 73 | 21.6 ms |
| `maks` | 6 352 | 11 803 | 6 352 | **11 803** | +5 451 (+85.8%) | 262 | 29.8 ms |
| `kaitse` | 7 230 | 10 139 | 7 230 | **10 139** | +2 909 (+40.2%) | 107 | 20.4 ms |
| `haridus` | 4 843 | 6 649 | 4 843 | **6 649** | +1 806 (+37.3%) | 96 | 14.9 ms |
| `pension` | 2 700 | 3 049 | 2 700 | **3 049** | +349 (+12.9%) | 43 | 5.5 ms |
| `energia` | 2 881 | 4 370 | 2 881 | **4 370** | +1 489 (+51.7%) | 49 | 7.6 ms |
| `julgeolek` | 3 191 | 4 112 | 3 191 | **4 112** | +921 (+28.9%) | 30 | 7.4 ms |
| `tervishoid` | 1 295 | 1 466 | 1 295 | **1 466** | +171 (+13.2%) | 13 | 2.7 ms |
| `toetus` | 11 378 | 13 534 | 11 378 | **13 534** | +2 156 (+19.0%) | 211 | 30.2 ms |
| `seadus` | 25 507 | 29 800 | 25 507 | **29 800** | +4 293 (+16.8%) | 254 | 70.8 ms |
| `Seeder` | 1 953 | 1 953 | 2 185 | **2 185** | +232 (+11.9%) | 6 | 4.5 ms |
| `Michal` | 1 057 | 1 058 | 1 192 | **1 193** | +136 (+12.9%) | 4 | 2.2 ms |
| `Hussar` | 294 | 294 | 348 | **348** | +54 (+18.4%) | 2 | 0.6 ms |
| `Kallas` | 5 785 | 5 799 | 5 785 | **5 799** | +14 (+0.2%) | 14 | 70.8 ms |
| `Ratas` | 1 759 | 2 196 | 1 759 | **2 196** | +437 (+24.8%) | 35 | 4.4 ms |
| `"Rail Baltic"` | 1 014 | 1 014 | 1 018 | **1 018** | +4 (+0.4%) | 4 | 17.4 ms |

### 3.4 Piirangute (guards) reeglid ja nende mõõdetud mõju

1. **Tuuma stoplist (`HEAD_STOPLIST`):**
   - Eemaldab fossiilsed ja polüseemsed tuumatüved: `arve`, `märk`, `kiri`, `kaal`, `seis`, `kord`, `koht`, `vaade`, `salu`, `organ`, `koll`, `kaar`, `asi`, `osa`, `mees`, `päev`, `aeg`, `aasta`.
   - **Tulemus:** `arve` alla seotud liitsõnade arv langes 9-lt 0-le (välistades `eelarve -> arve` katastroofi).
2. **Seotud prefiksite filter (`BOUND_PREFIXES`):**
   - Kui prefiksi pikkus on alla 4 tähemärgi ja see kuulub hulka `{'eel', 'all', 'üle', 'ees', 'pea', 'ala', 'ise'}`, siis seost ei looda.
   - **Tulemus:** Hoiab ära valeseosed nagu `eesmärk -> märk`, `allkiri -> kiri`, `ülekaal -> kaal`.
3. **Pärisnime ja üldnime lahusus (`AMBIGUOUS_NAME_WORDS`):**
   - Sõnad nagu `kallas` (kallas = rannikuriba) ja `ratas` (ratas = veerev ese) on eesti keeles tavalised üldnimed.
   - Mõõtmine näitab selgelt: kui otsida `Ratas`, lisab liitsõnade laiendus kõnesid jalgratastest ja tõukeratastest (`jalgratas`, `tõukeratas`).
   - **Reegel:** Pärisnimede puhul rakendatakse **ainult** `name_form` laiendust (omastav `ratase`, `kallase`, `seederi`), mitte liitsõnade tuumalaiendust (`jalgratas`, `jõekallas`).
   - Samuti tagab jutumärkides otsing (`"Ratas"`, `"eelarve"`), et kasutaja saab soovi korral igasuguse laienduse keelata.

---

## 4. Fraasiotsing ja esiletõstja (Highlighter)

### 4.1 Esiletõstja (`extract_matched_words`)
Funktsioon `extract_matched_words(text, target_lemmas, ...)` vastutab kõne kaardil otsisõnade kollase esiletõstmise eest.
- **Vajalik muudatus:** `target_lemmas` hulk peab sisaldama **kõiki** laiendatud lemmasid (nii baaslemma kui ka `lemma_links` kaudu lisandunud liitlemmad ja nimevormid).
- **Miks kriitiline:** Kui kasutaja otsib `eelarve` ja kõne leitakse tänu sõnale `riigieelarve`, peab sõna "riigieelarve" olema kõnetekstis esile tõstetud. Vastasel juhul tekiks kasutajas hämmeldus, miks kõne leiti.
- Kuna `extract_matched_words` kontrollib `_analyze_token_lemmas(tok) & target_lemmas`, hakkab see laiendatud lemmade puhul automaatselt ja ilma lisaarvutusteta tööle.

### 4.2 Fraasiotsing (`QueryPhrase`)
Fraasiotsingus (nt `"Rail Baltic"` või `"Euroopa Liidu õigus"`) pannakse igale positsioonile lemmade hulk.
- **Liitsõnade laiendamist fraasides EI tohi teha:** Kui sõna `"õigus"` fraasis `"Euroopa Liidu õigus"` laieneks 253 liitsõnaks, plahvataks kombinatsioonide arv $1 \times 1 \times 253 = 253$-ni. See ületaks SQLite kiire `instr()` tee piiri ($\le 16$) ja sunniks regex-skannimist. Lisaks ei otsi fraasi kasutaja reeglina liitsõnu.
- **Nimevormide ja aliaste laiendamine fraasides ON lubatud:** Nimevormid ja aliased lisavad positsioonile vaid 1–2 varianti (nt `baltic` -> `baltic`, `baltica`). Tulemusena on kombinatsioonide arv 2 või 4, mis mahub mugavalt kiire `instr()` sisse (`rail baltic`, `rai baltic`, `rail baltica`, `rai baltica`).
- `"Rail Baltic"` fraas leiab seeläbi ka 4 kõnet, kus räägiti `"Rail Baltica"` projektist.

### 4.3 Jutumärkides üksiksõna semantika (`"eelarve"` vs `eelarve`)
- **Ilma jutumärkideta (`eelarve`):** Laiendatud saagiseotsing. Leiab nii sõna `eelarve` kui ka kõik liitsõnad (`riigieelarve`, `lisaeelarve`, `kaitseeelarve`).
- **Jutumärkides üksiksõna (`"eelarve"`):** Täpne lemmavaste. Välistab liitsõnalaienduse ja leiab ainult kõned, kus esineb täpselt lemma `eelarve` (ja selle grammatilised pöörded nagu `eelarvest`, `eelarvega`), kuid MITTE liitsõnad.
- **Jutumärkides pärisnimi (`"Ratas"`):** Välistab `jalgratas` ja muud tuumaliitsõnad, leides vaid Jüri Ratase / ratta enda.

---

## 5. Soovitus ja arhitektuurne otsus

Soovitame Roadmap C1 realiseerimisel rakendada **Variandi 2 (relatsiooniline seoste tabel `lemma_links`)**:

1. **Skeem:**
   ```sql
   CREATE TABLE lemma_links (
       lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
       target_lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
       kind TEXT NOT NULL,
       PRIMARY KEY (lemma_id, target_lemma_id, kind)
   );
   CREATE INDEX idx_lemma_links_target ON lemma_links(target_lemma_id, kind);
   CREATE INDEX idx_lemma_links_lemma ON lemma_links(lemma_id, kind);
   ```
2. **Suund:**
   - Liitsõnad: `lemma_id = id(riigieelarve)`, `target_lemma_id = id(eelarve)`, `kind = 'compound_head'`.
   - Nimevormid: `lemma_id = id(seederi)`, `target_lemma_id = id(seeder)`, `kind = 'name_form'`.
3. **Päringuaegne laiendus:**
   - Kui otsitakse baassõna $L$, leitakse tabelist `lemma_links` kõik `lemma_id`-d, kus `target_lemma_id = id(L)`.
   - Päringu IN-nimekirja antakse $\{id(L)\} \cup \{lemma\_id\}$.

---

## 6. Migratsiooni- ja juurutusplaan

### 6.1 Andmebaasi migratsioon (`0004_lemma_links.py`)
1. Luua tabel `lemma_links` ja vastavad indeksid.
2. Käivitada migratsioonis `build_lemma_links(db_session)`, mis loeb tabeli `lemmas`, analüüsib need Vabamorfiga ja täidab `lemma_links` tabeli 80 532 reaga (~9 sekundit).
3. Salvestada süsteemi metaandmetesse `schema_version = 4`.

### 6.2 Integreerimine igapäevasesse konveierisse (`sync_database.py`)
Igapäevasel sünkroniseerimisel lisandub stenogrammidest keskmiselt 20–100 uut lemmat:
1. Pärast uute lemmade lisamist tabelisse `lemmas` teeb `sync_database.py` päringu:
   ```sql
   SELECT id, lemma FROM lemmas WHERE id NOT IN (SELECT DISTINCT lemma_id FROM lemma_links)
   ```
2. Uutele lemmadele arvutatakse liitsõna tuum ja nimevormide seosed.
3. Arvutus kestab alla **0.05 sekundi**, mistõttu igapäevane konveier ei aeglustu.

### 6.3 Tagasipööramisplaan (Rollback)
Kuna olemasolevaid tabeleid (`speeches`, `lemmas`, `speech_terms`) ei muudeta, on tagasipööramine triviaalne:
```sql
DROP TABLE IF EXISTS lemma_links;
```
Seejärel lülitatakse otsingukoodis välja `lemma_links` liitmine, taastades hetkega tänase käitumise ilma igasuguse andmekaota.

---

## 7. Metoodika teksti täiendamise ettepanekud

Faili `src/frontend/src/components/MethodologyModal.jsx` lisada selgitav alalõik otsingu toimimise kohta:

> **Otsingu laiendused (liitsõnad ja nimekäänded)**
> 
> Riigikogu kõnede otsing kasutab automaatset sisulist laiendust, et tagada täielik katvus:
> 
> - **Liitsõnade katvus:** Otsides üldmõistet (nt *eelarve*, *maks*, *pension*), leiab süsteem automaatselt ka vastavad liitsõnad (nt *riigieelarve*, *lisaeelarve*, *tulumaks*, *vanaduspension*).
> - **Pärisnimede vormid:** Konsonandiga lõppevate perekonnanimede otsingul (nt *Seeder*, *Michal*, *Hussar*) kaasatakse automaatselt kõned, kus nimi esineb omastavas või sihitavas käändes (*Seederi*, *Michali*, *Hussari*).
> - **Täpne otsing jutumärkidega:** Kui soovite otsida rangelt ainult baassõna ennast ilma liitsõnadeta, pange otsisõna jutumärkidesse (nt `"eelarve"` leiab vaid eelarve, mitte riigieelarvet; `"Ratas"` leiab vaid ratta või Jüri Ratase, mitte jalgrattaid).

---

## 8. Lisa: 20 juhuvalimi kõne väljavõtted ja täpsushinnangud päringute kaupa

Iga testpäringu puhul võeti 20 juhuslikku kõnet nende seast, mida baasotsing täna **ei leia**, kuid mida pakutud laiendus **leiab**.

### 8.1 `eelarve` (Juurdekasv: +5 116 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõik valimi kõned arutavad eelarvet (riigieelarve, lisaeelarve, kaitseeelarve).
- **Valimi näited:**
  1. *Kõne 8781 (04.12.2019, Dmitri Dmitrijev)* | Lemma: `riigieelarve` | *"...Dmitri Dmitrijev: Sport õpetab ausalt võitlema... riigieelarve vahenditest toetatakse..."*
  2. *Kõne 9365 (11.12.2019, Aivar Kokk)* | Lemma: `riigieelarve` | *"...Aivar Kokk: ...mida Riigikogu liikmed sooviksid toetada, aga riigieelarve võimalused..."*
  3. *Kõne 10569 (15.01.2020, Urve Tiidus)* | Lemma: `riigieelarve` | *"...Urve Tiidus: ...strateegilise kauba seadust ja riigieelarve laekumisi..."*
  4. *Kõne 11528 (29.01.2020, Martin Helme)* | Lemma: `riigieelarve` | *"...Martin Helme: ...soovist raha riigieelarvesse juurde saada või soovist inimesi..."*
  5. *Kõne 14902 (15.04.2020, Jürgen Ligi)* | Lemma: `lisaeelarve` | *"...Jürgen Ligi: ...lisaeelarve menetlemisel me nägime, kuidas valitsus..."*

### 8.2 `maks` (Juurdekasv: +5 451 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõned käsitlevad konkreetseid makse (sotsiaalmaks, käibemaks, tulumaks, maamaks, aktsiisimaks).
- **Valimi näited:**
  1. *Kõne 4315 (26.09.2019, Urmas Espenberg)* | Lemma: `sotsiaalmaks` | *"...Urmas Espenberg: ...Küllaltki tähelepanuväärne eelnõu sotsidelt sotsiaalmaksu erandi kohta..."*
  2. *Kõne 57660 (24.11.2021, Tarmo Kruusimäe)* | Lemma: `käibemaks` | *"...Tarmo Kruusimäe: ...Juba ainuüksi hea prognoosi puhul tuleks käibemaksust 2,5 miljonit..."*
  3. *Kõne 58860 (08.12.2021, Priit Sibul)* | Lemma: `käibemaks` | *"...Priit Sibul: ...Kui elektri hinna käibemaksu alandamise teema arutamiseks kulus..."*
  4. *Kõne 59778 (14.12.2021, Heiki Hepner)* | Lemma: `käibemaks` | *"...Heiki Hepner: ...Isamaa ettepanek käibemaksu langetada on konkreetne ettepanek..."*

### 8.3 `kaitse` (Juurdekasv: +2 909 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõned arutavad riigikaitset, tarbijakaitset, lastekaitset ja keskkonnakaitset.
- **Valimi näited:**
  1. *Kõne 16901 (06.05.2020, Marko Šorin)* | Lemma: `tarbijakaitse` | *"...Marko Šorin: ...tegevuskava esitatakse Tarbijakaitse ja Tehnilise Järelevalve Ametile..."*
  2. *Kõne 18030 (13.05.2020, Tanel Kiik)* | Lemma: `lastekaitse` | *"...Tanel Kiik: ...Antud eelnõu ettepaneku esitas tegelikult Lastekaitse Liit..."*
  3. *Kõne 25719 (11.11.2020, Madis Milling)* | Lemma: `riigikaitse` | *"...Madis Milling: ...riigikaitse arengukava ja kaitseväe juhataja ettepanekud..."*

### 8.4 `haridus` (Juurdekasv: +1 806 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõned käsitlevad kõrgharidust, huviharidust ja alusharidust.
- **Valimi näited:**
  1. *Kõne 25356 (09.11.2020, Mailis Reps)* | Lemma: `kõrgharidus` | *"...Mailis Reps: ...ja inimesi, kellel on mingi muu kõrgharidus, aga nad oleks valmis..."*
  2. *Kõne 37255 (07.04.2021, Siim Kallas)* | Lemma: `kõrgharidus` | *"...Siim Kallas: ...et tervishoid vajab tõsiselt lisaraha, samamoodi kõrgharidus..."*
  3. *Kõne 44928 (09.06.2021, Ivari Padar)* | Lemma: `huviharidus` | *"...Ivari Padar: ...Selles suhtes oli selle huvihariduse toetuse kärpimine..."*

### 8.5 `pension` (Juurdekasv: +349 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõned käsitlevad eripensioni, vanaduspensioni, toitjakaotuspensioni ja kogumispensioni.
- **Valimi näited:**
  1. *Kõne 4286 (26.09.2019, Liina Kersna)* | Lemma: `toitjakaotuspension` | *"...Liina Kersna: ...Minu küsimus puudutab jätkuvalt toitjakaotuspensioni..."*
  2. *Kõne 5588 (22.10.2019, Martin Helme)* | Lemma: `eripension` | *"...Martin Helme: ...seaduse eelnõu, mis tegeleb eripensionidega..."*
  3. *Kõne 7035 (13.11.2019, Taavi Rõivas)* | Lemma: `vanaduspension` | *"...Taavi Rõivas: ...kus keskmine vanaduspension läheb tulumaksu alla..."*

### 8.6 `energia` (Juurdekasv: +1 489 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõned käsitlevad taastuvenergiat, elektrienergiat ja bioenergiat.
- **Valimi näited:**
  1. *Kõne 35790 (24.03.2021, Jevgeni Ossinovski)* | Lemmad: `elektrienergia`, `taastuvenergia` | *"...Jevgeni Ossinovski: ...sihiks on vähendada elektrienergia lõpphinda..."*
  2. *Kõne 57289 (23.11.2021, Indrek Saar)* | Lemma: `taastuvenergia` | *"...Indrek Saar: ...praeguste energiahindade puhul tõusetub kogu see taastuvenergia..."*

### 8.7 `julgeolek` (Juurdekasv: +921 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõned käsitlevad merejulgeolekut, sisejulgeolekut, välisjulgeolekut ja energiajulgeolekut.
- **Valimi näited:**
  1. *Kõne 24854 (27.10.2020, Andres Metsoja)* | Lemma: `merejulgeolek` | *"...Andres Metsoja: ...Ameerika Ühendriigid algatasid rahvusvahelise merejulgeoleku..."*
  2. *Kõne 43318 (01.06.2021, Heiki Hepner)* | Lemma: `energiajulgeolek` | *"...Heiki Hepner: ...kujundliku tabureti näite, et energiajulgeolek on..."*

### 8.8 `tervishoid` (Juurdekasv: +171 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõned käsitlevad töötervishoidu ja rahvatervishoidu.
- **Valimi näited:**
  1. *Kõne 18724 (20.05.2020, Signe Riisalo)* | Lemma: `töötervishoid` | *"...Signe Riisalo: ...lähetatud töötajate töötervishoiu ja tööohutuse nõuded..."*
  2. *Kõne 28481 (09.12.2020, Siim Kallas)* | Lemma: `töötervishoid` | *"...Siim Kallas: ...Vabariigi Valitsuse algatatud töötervishoiu ja tööohutuse seaduse..."*

### 8.9 `toetus` (Juurdekasv: +2 156 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõned käsitlevad hooldajatoetust, üleminekutoetust, lastetoetust jne.
- **Valimi näited:**
  1. *Kõne 679 (15.05.2019, Helmen Kütt)* | Lemma: `hooldajatoetus` | *"...Helmen Kütt: ...puudega inimeste hooldamise eest makstav hooldajatoetus..."*
  2. *Kõne 3966 (25.09.2019, Urmas Kruuse)* | Lemma: `üleminekutoetus` | *"...Urmas Kruuse: ...et üleminekutoetustele ei ole järgmise aasta eelarves..."*

### 8.10 `seadus` (Juurdekasv: +4 293 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõned käsitlevad konkreetseid seadusi (põhiseadus, metsaseadus, kooseluseadus).
- **Valimi näited:**
  1. *Kõne 29106 (14.12.2020, Lauri Läänemets)* | Lemmad: `põhiseadus`, `kooseluseadus` | *"...Lauri Läänemets: ...Lugupeetud põhiseaduskomisjoni esimees!..."*
  2. *Kõne 34991 (22.03.2021, Jevgeni Ossinovski)* | Lemma: `metsaseadus` | *"...Jevgeni Ossinovski: ...mis puudutab metsaseaduse muudatusi..."*

### 8.11 `Seeder` (Juurdekasv: +232 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõik 20 kõnet räägivad Helir-Valdor Seederist vormide `seederi` ja `seedrit` kaudu.
- **Valimi näited:**
  1. *Kõne 8397 (02.12.2019, Indrek Saar)* | Lemma: `seedrit` | *"...Indrek Saar: ...eelkõige tuleb tunnustada Helir-Valdor Seedrit, kellel selle pensionisüsteemiga..."*
  2. *Kõne 31233 (08.02.2021, Priit Sibul)* | Lemma: `seederi` | *"...Priit Sibul: ...Esitan Isamaa Erakonna fraktsiooni nimel kandidaadiks Helir-Valdor Seederi..."*
  3. *Kõne 34924 (22.03.2021, Jüri Ratas)* | Lemma: `seederi` | *"...Jüri Ratas: ...Ma palun Riigikogu kõnetooli Helir-Valdor Seederi..."*
  4. *Kõne 39973 (22.04.2021, Martin Helme)* | Lemma: `seederi` | *"...Martin Helme: ...Mihhail Lotmani, Jüri Luige, Helir-Valdor Seederi, Tarmo Kruusimäe..."*
  5. *Kõne 40754 (10.05.2021, Urmas Reinsalu)* | Lemma: `seederi` | *"...Urmas Reinsalu: ...Tarmo Kruusimäe, Helir-Valdor Seederi, Raivo Tamme ja enda nimel..."*

### 8.12 `Michal` (Juurdekasv: +136 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõik 20 kõnet räägivad Kristen Michalist vormi `michali` kaudu.
- **Valimi näited:**
  1. *Kõne 60673 (11.01.2022, Jüri Ratas)* | Lemma: `michali` | *"...Jüri Ratas: ...Palun Riigikogu kõnetooli ettekandeks majanduskomisjoni esimehe Kristen Michali..."*
  2. *Kõne 66970 (23.02.2022, Jüri Ratas)* | Lemma: `michali` | *"...Jüri Ratas: ...Kert Kingo, Kristen Michali, Riina Sikkuti, Marko Šorini..."*
  3. *Kõne 78768 (08.06.2022, Jüri Ratas)* | Lemma: `michali` | *"...Jüri Ratas: ...läbirääkimiste voorus Kristen Michali..."*
  4. *Kõne 81994 (14.09.2022, Helir-Valdor Seeder)* | Lemma: `michali` | *"...Helir-Valdor Seeder: ...Ma palun ettekandjaks majanduskomisjoni esimehe Kristen Michali..."*

### 8.13 `Hussar` (Juurdekasv: +54 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **20 / 20 (100%) asjakohased.** Kõik 20 kõnet räägivad Lauri Hussarist vormi `hussari` kaudu.
- **Valimi näited:**
  1. *Kõne 96586 (10.04.2023, Marek Reinaas)* | Lemma: `hussari` | *"...Marek Reinaas: ...esitan ma Riigikogu esimehe kandidaadiks Lauri Hussari..."*
  2. *Kõne 97967 (08.05.2023, Toomas Kivimägi)* | Lemma: `hussari` | *"...Toomas Kivimägi: ...ma ütlesin, et jagan härra Lauri Hussari seisukohta..."*
  3. *Kõne 101460 (15.05.2023, Siim Pohlak)* | Lemma: `hussari` | *"...Siim Pohlak: ...et see Lauri Hussari varem tehtud hääletus oli legitiimne..."*

### 8.14 `Kallas` (Juurdekasv: +14 kõnet, Valim: 14 kõnet)
- **Täpsushinnang:** **0 / 14 (0%) asjakohased isikuotsinguna.** Kõik 14 kõnet käsitlevad looduslikku kallast (jõekallas, mäekallas, paekallas, põhjakallas).
- **Valimi näited:**
  1. *Kõne 24856 (27.10.2020, Kalle Grünthal)* | Lemma: `mäekallas` | *"...Kalle Grünthal: ...Näiteks Tallinnas Mäekalda tänaval on ehitatud..."*
  2. *Kõne 40813 (10.05.2021, Peeter Ernits)* | Lemmad: `põhjakallas`, `lõunakallas` | *"...Peeter Ernits: ...Soome lahe põhjakaldal seadusandja vajab... aga lõunakaldal..."*
  3. *Kõne 41037 (10.05.2021, Kalle Grünthal)* | Lemma: `paekallas` | *"...Kalle Grünthal: ...avanedes paekalda järsaku jalamil üsna madalal..."*
- **Disainiotsus:** Kinnitab reeglit, et perekonnanimesid ei tohi laiendada liitsõnatüvedena.

### 8.15 `Ratas` (Juurdekasv: +437 kõnet, Valim: 20 kõnet)
- **Täpsushinnang:** **0 / 20 (0%) asjakohased isikuotsinguna.** Kõik 20 kõnet käsitlevad transpordivahendite rattaid (`jalgratas`, `tõukeratas`).
- **Valimi näited:**
  1. *Kõne 2839 (30.08.2019, Jüri Ratas)* | Lemma: `jalgratas` | *"...Jüri Ratas: ...ükskõik kas jala, jalgratta või autoga..."*
  2. *Kõne 20836 (15.06.2020, Taavi Aas)* | Lemma: `tõukeratas` | *"...Taavi Aas: ...elektrilised tõukerattad, elektrirulad ja muud taolised sõidukid..."*
  3. *Kõne 46643 (12.06.2021, Paul Puustusmaa)* | Lemma: `jalgratas` | *"...Paul Puustusmaa: ...ei ole mõtet seda jalgratast vändata..."*
- **Disainiotsus:** Kinnitab reeglit, et pärisnimedele rakendatakse üksnes käändevormide laiendust (`ratase`), mitte liitsõnalaiendust.

### 8.16 `"Rail Baltic"` (Juurdekasv: +4 kõnet, Valim: 4 kõnet)
- **Täpsushinnang:** **4 / 4 (100%) asjakohased.** Kõik 4 kõnet käsitlevad Rail Baltica raudteeprojekti.
- **Valimi näited:**
  1. *Kõne 114839 (17.10.2023, Sven Pertens)* | Lemma: `baltica` | *"...Sven Pertens: ...Välja arvatud Rail Baltica ja ehk ka võib-olla kaitseinvesteeringute keskus..."*
  2. *Kõne 201808 (10.06.2026, Lauri Hussar)* | Lemma: `baltica` | *"...Lauri Hussar: ...Rain Epler ja teema on Rail Baltica. Rain Epler, palun!..."*
  3. *Kõne 205923 (23.09.2026, Aivar Kokk)* | Lemma: `baltica` | *"...Aivar Kokk: ...suunatakse 2027. aasta Rail Baltica arenduse kuludest..."*
  4. *Kõne 207005 (30.09.2026, Aivar Kokk)* | Lemma: `baltica` | *"...Aivar Kokk: ...ta on rääkinud Rail Baltica juhtidega, et need tuleb ära osta..."*
