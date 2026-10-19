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

| Kriteerium | Variant 1: Kogu korpuse ümberindekseerimine | Variant 2: Seoste tabel `lemma_links` andmebaasis (Otsustatud) | Variant 3: Ainult päringuaegne lahendus mälus |
| :--- | :--- | :--- | :--- |
| **Põhimõte** | Muuta `lemmatizer.py` loogikat ja töödelda uuesti kõik 208 685 kõnet, lisades mitu lemmat `SpeechTerm`-i. | Luua relatsiooniline tabel `lemma_links(lemma_id, target_lemma_id, kind)`, arvutatuna unikaalsete lemmade pealt. Otsing laiendab lemmade IN-nimekirja. | EstNLTK/Vabamorf arvutab otsingu ajal mälus iga kord sobivad lemmad ilma andmebaasitabelita. |
| **Arvutuskulu** | Väga suur: 6–10 tundi CPU aega serveris, kõigi tabelite ülekirjutamine. | Väga väike: ühekordselt ~9 sekundit kõigi 137k lemma kohta. | Päringu ajal pidev lisakoormus (15–50 ms iga päringu kohta). |
| **B2 ja andmebaasi maht** | Suur andmemahu paisumine: `speech_terms` kasvab 30–50% (~5 miljonit uut rida). Nõuab uute B2 snapshotide tegemist. | Minimaalne: ~80k rida tabelis, andmebaasi lisandub vaid ~3.5 MB (0.3% kogu mahust). Null mõju B2 arhiivile. | 0 MB andmebaasis. |
| **Uuendatavus & Paindlikkus** | Jäik: reegli või stoplisti muutmisel tuleb taas kogu andmebaas (208k kõnet) uuesti indekseerida. | Suurepärane: reegleid või käsitsi erandeid saab sekundiga uuendada ja auditeerida SQL-päringuga. | Hea koodi muutes, kuid puudub püsiv auditeeritavus. |
| **Tagasipööramine (Rollback)** | Raske ja aeganõudev (nõuab varukoopia taastamist või uuesti indekseerimist). | Kohene: `DROP TABLE lemma_links` ja koodi revert, ükski olemasolev kõne ega indeks ei muutu. | Kohene: koodi revert. |
| **Otsingu latentsus** | 0 ms lisaaega SQL-is. | +1 kuni +3 ms lisaaega SQL IN-filtris (20–250 elementi indekseeritud veerus). | +20 kuni +60 ms lisaprotsessorit igal kasutajapäringul. |

---

## 3. Mõõtmistulemused (reprodutseeritud skriptiga `c1_measure.py`)

Kõik mõõtmised on teostatud tootmisbaasi ametliku koopia peal (208 685 kõnet, 137 534 unikaalset lemmat). Mõõtmisi saab 100% reprodutseerida käsuga:
```bash
python scripts/experiments/c1_measure.py --db file:/tmp/c1.sqlite?mode=ro --output-csv docs/design/c1-precision.csv
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

### 3.3 Fikseeritud 16 testpäringu mõõtmised ja täpsushinnangud

Iga testpäringu puhul võeti 20 juhuslikku kõnet (fikseeritud juhuslikkuse seemnega `seed=42`) nende seast, mida baasotsing täna **ei leia**, kuid mida laiendatud otsing **leiab**. Kõik 295 rida on salvestatud faili `docs/design/c1-precision.csv`.

Hindamisel eristatakse kahte täpsuskriteeriumi:
- **`lexical_ok` (morfoloogiline täpsus):** Kas leitud kõne sisaldab otsisõna korrektse morfoloogilise tuumana või nimevormina?
- **`topic_ok` (teemakohasus):** Kas kõne käsitleb teemat, mida antud sõna otsiv kasutaja parlamendikontekstis eeldatavalt otsib? (nt otsides `kaitse`, kas kõne räägib riigikaitsest/elanikkonnakaitsest või tarbijakaitsest; otsides `Ratas`, kas räägitakse Jüri Ratasest või jalgrattast).

| Päring | Baas (täna) | Liitsõnad (Head) | Nimed (Name) | Mõlemad (Ettepanek) | Juurdekasv ($\Delta$) | IN-suurus | SQL aeg | Lexical OK (valim) | Topic OK (valim) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `eelarve` | 8 596 | 13 712 | 8 596 | **13 712** | +5 116 (+59.5%) | 73 | 21.6 ms | 20/20 (100%) | **20/20 (100%)** |
| `maks` | 6 352 | 11 803 | 6 352 | **11 803** | +5 451 (+85.8%) | 262 | 29.8 ms | 20/20 (100%) | **20/20 (100%)** |
| `kaitse` | 7 230 | 10 139 | 7 230 | **10 139** | +2 909 (+40.2%) | 107 | 20.4 ms | 20/20 (100%) | **11/20 (55.0%)** |
| `haridus` | 4 843 | 6 649 | 4 843 | **6 649** | +1 806 (+37.3%) | 96 | 14.9 ms | 20/20 (100%) | **20/20 (100%)** |
| `pension` | 2 700 | 3 049 | 2 700 | **3 049** | +349 (+12.9%) | 43 | 5.5 ms | 20/20 (100%) | **20/20 (100%)** |
| `energia` | 2 881 | 4 370 | 2 881 | **4 370** | +1 489 (+51.7%) | 49 | 7.6 ms | 20/20 (100%) | **20/20 (100%)** |
| `julgeolek` | 3 191 | 4 112 | 3 191 | **4 112** | +921 (+28.9%) | 30 | 7.4 ms | 20/20 (100%) | **20/20 (100%)** |
| `tervishoid` | 1 295 | 1 466 | 1 295 | **1 466** | +171 (+13.2%) | 13 | 2.7 ms | 20/20 (100%) | **20/20 (100%)** |
| `toetus` | 11 378 | 13 534 | 11 378 | **13 534** | +2 156 (+19.0%) | 211 | 30.2 ms | 20/20 (100%) | **20/20 (100%)** |
| `seadus` | 25 507 | 29 800 | 25 507 | **29 800** | +4 293 (+16.8%) | 254 | 70.8 ms | 20/20 (100%) | **20/20 (100%)** |
| `Seeder` | 1 953 | 1 953 | 2 185 | **2 185** | +232 (+11.9%) | 6 | 4.5 ms | 20/20 (100%) | **20/20 (100%)** |
| `Michal` | 1 057 | 1 058 | 1 192 | **1 193** | +136 (+12.9%) | 4 | 2.2 ms | 20/20 (100%) | **20/20 (100%)** |
| `Hussar` | 294 | 294 | 348 | **348** | +54 (+18.4%) | 2 | 0.6 ms | 20/20 (100%) | **20/20 (100%)** |
| `Kallas` | 5 785 | 5 799 | 5 785 | **5 799** | +14 (+0.2%) | 14 | 70.8 ms | 11/11 (100%) | **0/11 (0.0%)** |
| `Ratas` | 1 759 | 2 196 | 1 759 | **2 196** | +437 (+24.8%) | 35 | 4.4 ms | 20/20 (100%) | **0/20 (0.0%)** |
| `"Rail Baltic"` | 1 014 | 1 014 | 1 018 | **1 018** | +4 (+0.4%) | 4 | 17.4 ms | 4/4 (100%) | **4/4 (100%)** |

### 3.5 Tulemuste analüüs ja lingvistilised järeldused

1. **Valdkonnamõisted saavutavad 100% teematäpsuse:**
   Päringud nagu `eelarve`, `maks`, `pension`, `energia`, `haridus`, `julgeolek`, `tervishoid`, `toetus`, `seadus` saavad juurde sadu kuni tuhandeid uusi asjakohaseid kõnesid ilma ühegi teemavälise müra lisandumiseta.
2. **Päringu `kaitse` polüseemia (topic_ok 55%):**
   Valimis 11 kõnet 20-st käsitlesid riigikaitset, elanikkonnakaitset või droonikaitset. Ülejäänud 9 kõnet käsitlesid muid kaitsevaldkondi: tarbijakaitset (2), keskkonnakaitset (3), andmekaitset (2), lastekaitset (1) ja loomakaitset (1). Kuigi need on morfoloogiliselt 100% korrektsed liitsõnad (`lexical_ok = yes`), ei otsi riigikaitsele spetsialiseerunud kasutaja tarbijakaitset. See rõhutab täpse režiimi (Exact mode) vajalikkust.
3. **Poliitikute nimed vs üldnimed (`Kallas` ja `Ratas`):**
   Päringu `Ratas` kõik 20 uut vastet käsitlesid jalgrattaid ja tõukerattaid (`jalgratas`, `tõukeratas`). Päringu `Kallas` kõik 11 uut vastet käsitlesid jõekaldaid ja paekaldaid (`jõekallas`, `paekallas`). Seda põhjustab asjaolu, et eesti keeles on sõnad "ratas" ja "kallas" tavalised üldnimed.

---

## 4. Nimekaitsereegel (Name Rule)

Et vältida poliitikute nimede otsingul jalgrataste ja jõekallaste kuvamist, kehtestatakse selge **nimekaitsereegel**:

> **Reegel:** Kui otsingu lemma langeb kokku `persons` tabeli mis tahes isiku ees- või perekonnanime lemmaga, **jäetakse liitsõnade laiendus (`compound_head`) selle lemma puhul vahele**. Rakendatakse üksnes nimekäände laiendust (`name_form`).

### 4.1 Mõju andmebaasis
- Andmebaasi `persons` tabelis on **276** unikaalset isikukirjet.
- Need sisaldavad kokku 188 unikaalset eesnimetokenit ja 263 perenimetokenit (kokku **449** nimeosa).
- Täpselt **426** neist nimeosadest esinevad andmebaasi `lemmas` tabelis unikaalsete lemmadena.
- Neist 426-st lemmast **59** käituksid ilma reeglita liitsõna tuumadena:
  - `ratas` (34 liitsõna, sh `jalgratas`, `tõukeratas`)
  - `kallas` (6 liitsõna, sh `jõekallas`, `merekallas`)
  - `kivi` (48 liitsõna, sh `ohvrikivi`, `takistuskivi`)
  - `laine` (75 liitsõna, sh `migratsioonilaine`)
  - `klaas` (14 liitsõna, sh `aknaklaas`, `õlleklaas`)
  - `kokk` (5 liitsõna, sh `koolikokk`)
  - `anne` (25 liitsõna, sh `märguanne`, `metsaanne`)
  - `kaja` (6 liitsõna, sh `häälekaja`)
  - `laul` (27 liitsõna, sh `koorilaul`)
  - `maastik` (54 liitsõna, sh `rahvusmaastik`)

Tänu reeglile otsitakse nimede `Seeder`, `Michal`, `Hussar`, `Kallas`, `Ratas`, `Kivi`, `Kokk` puhul ainult isiku nimevorme (nt `seederi`, `michali`, `hussari`, `kallase`, `ratase`, `koka`), samas kui üldnimedest moodustatud liitsõnu ei kaasata.

---

## 5. Otsustatud arhitektuur (Kinnitatud Jaak poolt)

Otsingu saagise tõstmiseks Roadmap C1 raames on kinnitatud järgmised disainiotsused:

1. **Laiendus on vaikimisi SEES:**
   Laiendatud otsing (`compound_head` üldmõistetele + `name_form` isikunimedele) on sisse lülitatud vaikimisi kõigil otsingutel. Metoodikatekst selgitab seda kasutajatele, märkides, et tulemuste arv on varasemast suurem.
2. **Täpne režiim (Exact mode):**
   Kasutajad ei pea tippima jutumärke. Otsingufiltritesse (`src/frontend/src/components/SearchFilters.jsx`) lisatakse märkeruut:
   `"Ainult täpne sõna (ilma liitsõnadeta)"`
   - See kaardub API parameetrile `expand=false` (vaikimisi `expand=true`).
   - Filtrit hoitakse URL-i päringuparameetrina `?expand=false`, samamoodi nagu teisi filtreid (`searchExcludeChair` jne).
3. **Jutumärkides üksiksõna API-s:**
   Kui päringusõna on ümbritsetud jutumärkidega (nt `q="eelarve"` või `q="Ratas"`), tõlgendatakse seda API tasemel ilma laienduseta otsinguna, isegi kui üldine filter `expand=true` on aktiivne.
4. **Relatsiooniline seoste tabel `lemma_links`:**
   Andmebaasi lisatakse tabel:
   ```sql
   CREATE TABLE lemma_links (
       lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
       target_lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
       kind TEXT NOT NULL,
       PRIMARY KEY (lemma_id, target_lemma_id, kind)
   );
   ```
   Indeksid lisatakse `src/load/indexes.py` loendisse `INDEXES`:
   ```python
   (IndexConfig("idx_lemma_links_target", "lemma_links", ["target_lemma_id", "kind"]),)
   (IndexConfig("idx_lemma_links_lemma", "lemma_links", ["lemma_id", "kind"]),)
   ```

---

## 6. Fraasiotsing ja esiletõstja (Highlighter)

### 6.1 Esiletõstja (`extract_matched_words`)
Funktsioon `extract_matched_words(text, target_lemmas, ...)` vastutab kõne kaardil otsisõnade kollase esiletõstmise eest.
- **Käitumine:** Kui `expand=true`, antakse `target_lemmas` hulka nii baaslemma kui ka kõik `lemma_links` kaudu lisandunud liitlemmad ja nimevormid.
- **Tulemus:** Kui kõne leiti tänu sõnale "riigieelarve", värvitakse sõna "riigieelarve" kõne tekstis automaatselt kollaseks. Kui kasutaja valib "Ainult täpne sõna", antakse esiletõstjale vaid baaslemma.

### 6.2 Fraasiotsing (`QueryPhrase`)
Fraasiotsingus (nt `"Rail Baltic"` või `"Euroopa Liidu õigus"`):
- **Liitsõnade laiendamist fraasides EI rakendata:** See hoiab ära kombinatoorse plahvatuse ja tagab, et SQLite kasutab alati kiiret `instr()` teed ($\le 16$ kombinatsiooni).
- **Nimevormide ja aliaste laiendamine ON lubatud:** Kuna nimevorme on positsiooni kohta 1–2 (nt `baltic` -> `baltic`, `baltica`), teeb see kokku 2–4 kombinatsiooni, mis mahub mugavalt kiire `instr()` sisse (`rail baltic`, `rai baltic`, `rail baltica`, `rai baltica`).

---

## 7. Migratsiooni- ja juurutusplaan

### 7.1 Skeemipõhine migratsioon (`src/load/migrations.py`)
Kuna andmebaasi migratsioonid käivituvad API teenuse käivitumisel (`apply_migrations()`), **ei tohi migratsioon teha rasket arvutust ega käivitada Vabamorfi**.
1. Luuakse uus migratsioon `0004_lemma_links(conn)`:
   - Täidab `CREATE TABLE IF NOT EXISTS lemma_links (...)`.
   - Lisab tabeli `schema_migrations` uue kirje `0004_lemma_links`.
2. Indeksid registreeritakse failis `src/load/indexes.py` (`INDEXES` loendis), kus neid kontrollib ja haldab ühtne `ensure_indexes()` süsteem.

### 7.2 Seoste arvutamise skript (`scripts/build_lemma_links.py`)
Seoste loomiseks luuakse iseseisev skript:
- `python scripts/build_lemma_links.py`:
  - Loeb tabelist `lemmas` uued, veel töötlemata lemmad.
  - Arvutab liitsõna- ja nimeseosed Vabamorfiga.
  - Salvestab seosed tabelisse `lemma_links`.
  - Uuendab tabelis `system_meta` olekumarkerit `lemma_links_max_lemma_id`.
- `python scripts/build_lemma_links.py --rebuild`:
  - Kustutab tabelist `lemma_links` kõik read.
  - Lähtestab `system_meta` väärtuse `lemma_links_max_lemma_id = 0`.
  - Arvutab kõik seosed algusest peale uuesti (vajalik siis, kui reegleid või stoplisti muudetakse; kestab serveris ~9 sekundit).

### 7.3 Inkrementaalne sünkroniseerimine (`sync_database.py`)
Tänases andmebaasis on ~57 000 lemmat, millel puuduvad liitsõna- ja nimeseosed. Tingimus `lemmas NOT IN lemma_links` sunniks igapäevasel sünkroniseerimisel kõiki neid 57k lemmat asjatult uuesti analüüsima.
- **Lahendus:** Kasutatakse olekumarkerit `system_meta` võtmega `lemma_links_max_lemma_id`.
- Igapäevasel käivitusel loeb `sync_database.py`:
  ```sql
  SELECT id, lemma FROM lemmas WHERE id > :lemma_links_max_lemma_id;
  ```
- Arvutatakse seosed üksnes lisandunud lemmadele (tavaliselt 20–100 lemmat päevas).
- See võtab aega alla **0.01 sekundi**, hoides igapäevase konveieri ülikiirena.

### 7.4 Tagasipööramisplaan (Rollback)
Kuna olemasolevaid kõnetabeleid ega indekseid ei muudeta, on tagasipööramine kohene ja ohutu:
```sql
DROP TABLE IF EXISTS lemma_links;
DELETE FROM schema_migrations WHERE name = '0004_lemma_links';
```
Koodis eemaldatakse `expand` parameeter ja taastatakse eelnev otsingukäitumine ilma andmekaota.

---

## 8. Kasutajaliides ja metoodika teksti täiendused

### 8.1 Kasutajaliidese ettepanek (`SearchFilters.jsx`)
Otsingufiltrite paneeli lisatakse uus märkeruut:
```jsx
<div className="filter-group-item filter-checkbox-item">
  <label htmlFor="filter-exact-match" className="filter-checkbox-label filter-label">
    <input
      id="filter-exact-match"
      type="checkbox"
      checked={searchExactMatch}
      onChange={(e) => setSearchExactMatch(e.target.checked)}
    />
    <span>Ainult täpne sõna (ilma liitsõnadeta)</span>
  </label>
</div>
```
- Kui märkeruut on valitud, saadetakse API-le `expand=false` ning URL-i lisandub `?expand=false`.
- Vaikimisi on märkeruut valimata (`expand=true`).

### 8.2 Metoodika selgitustekst (`MethodologyModal.jsx`)
Faili `src/frontend/src/components/MethodologyModal.jsx` lisatakse järgmine selgitus:

> **Otsingu laiendused (liitsõnad ja nimekäänded)**
> 
> Riigikogu kõnede otsing kasutab automaatset sisulist laiendust, et tagada täielik katvus. Seetõttu on leitud kõnede arv suurem kui varasemas otsingus:
> 
> - **Liitsõnade katvus:** Otsides üldmõistet (nt *eelarve*, *maks*, *pension*), leiab süsteem automaatselt ka vastavad liitsõnad (nt *riigieelarve*, *lisaeelarve*, *tulumaks*, *vanaduspension*).
> - **Pärisnimede vormid:** Konsonandiga lõppevate perekonnanimede otsingul (nt *Seeder*, *Michal*, *Hussar*) kaasatakse automaatselt kõned, kus nimi esineb omastavas või sihitavas käändes (*Seederi*, *Michali*, *Hussari*).
> - **Täpne otsing:** Kui soovite otsida rangelt ainult baassõna ennast ilma liitsõnadeta, märkige otsingufiltrites ruut *"Ainult täpne sõna (ilma liitsõnadeta)"*. Samuti saab otsisõna panna jutumärkidesse (nt `"eelarve"` või `"Ratas"`).

---

## 9. Lisa: Täpsusvalimi CSV fail

Täielik 295 kõnega juhuvalim kõigi 16 testpäringu kohta on salvestatud faili:
[c1-precision.csv](file:///Users/karmoele/Projects/riigikogu-stenogram-search/docs/design/c1-precision.csv)

Fail sisaldab veerge:
`query,speech_id,date,matched_lemma,snippet,lexical_ok,topic_ok`
- `query`: otsitud päringusõna
- `speech_id`: kõne unikaalne identifikaator andmebaasis
- `date`: istungi toimumise kuupäev
- `matched_lemma`: laienenud lemma, mis antud kõnes leiti
- `snippet`: ~200 tähemärgi pikkune tekstikontekst otsisõna ümber
- `lexical_ok`: kas leitud sõna on korrektne morfoloogiline tuletis/liitsõna (`yes`/`no`)
- `topic_ok`: kas kõne käsitleb teemat, mida kasutaja antud sõna otsides parlamendis eeldatavalt soovib (`yes`/`no`)
