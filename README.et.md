# Riigikogu stenogrammide otsing

🇬🇧 [English README](README.md)

Täistekstotsingu ja analüütika rakendus Eesti Riigikogu stenogrammidele.

Projekt võimaldab:

- otsida stenogrammidest märksõnade järgi;

- kasutada mitmesõnalisi AND päringuid;

- kasutada OR päringuid komadega;

- visualiseerida märksõnade aktiivsust ajas;

- kuvada enim teemat kasutanud kõnelejaid;

- avada algseid stenogramme;

- kasutada frontendis dark/light mode'i.

---

# Funktsionaalsus

## Otsing

### Üks märksõna

```text
kliima
```

Leiab kõik kõned, kus esineb lemma kliima.

### AND otsing

```text
tartu ülikool
```

Leiab ainult kõned, kus esinevad mõlemad sõnad.

### OR otsing

```text
kliima, ilm
```

Leiab kõned, kus esineb vähemalt üks komaga eraldatud märksõna.

### Kombineeritud otsing

```text
kliima muutus, taastuv energia
```

Tähendab:
```text
(kliima AND muutus) OR (taastuv AND energia)
```

---

## Analüütika

### Aktiivsus ajas

Märksõnade sagedust saab kuvada:

* päeva kaupa;
* nädala kaupa;
* kuu kaupa.

Vaikimisi kasutatakse kuuvaadet.

Puuduvad kuud täidetakse automaatselt nullidega, et graafikud oleksid pidevad.

### Top kõnelejad

Kuvab poliitikud, kes on vastavaid märksõnu enim kasutanud.

---

## Kuidas käivatada

Varsti tulemas (Docker)
