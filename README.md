# Riigikogu Stenogram Search

🇪🇪 [Eestikeelne README](README.et.md)

A full-text search and analytics application for Estonian Parliament (Riigikogu) transcripts.

The project allows users to:

- search parliamentary speeches by keyword;
- use multi-word AND queries;
- use OR queries with commas;
- visualize keyword activity over time;
- display top speakers for a topic;
- open original transcript sources;
- switch between dark and light mode in the frontend.

---

# Features

## Search

### Single keyword

```text
climate
```
Finds all speeches containing the lemma climate.


### AND search


```text
tartu university
```
Finds only speeches where both words appear.


### OR search


```text
climate, weather
```
Finds speeches where at least one keyword group appears.



### Combined search


```text
climate change, renewable energy
```
This means:
```text
(climate AND change) OR (renewable AND energy)
```

## Analytics

### Activity over time

Keyword frequency can be visualized by:

* day
* week
* month

Monthly view is the default.

Missing monthly periods are automatically filled with zero values for continuous graphs.

### Top speakers

Displays politicians who have used matching keywords the most.


### Running

Coming Soon... (Docker)
