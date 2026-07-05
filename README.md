# Skånetrafiken Förseningar

**Copyright (c) 2026 Thorsten Grund. All rights reserved. USE AT YOUR OWN RISK.**

Kontinuerlig scanner som samlar in förseningar, inställda turer och trafikstörningar
för hela Skånetrafikens nät, via Trafiklabs öppna GTFS Regional-data. Körs automatiskt
var 2:e timme via GitHub Actions och bygger upp en historik i `data/forseningar.db`
(SQLite) — tänkt som underlag för kompensationsanspråk, klagomål till Skånetrafiken
om återkommande problem, och egen statistik.

## Dokumentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — flödet i detalj, designbeslut och varför.
- [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md) — alla tabeller och kolumner.
- [docs/RUNBOOK.md](docs/RUNBOOK.md) — nyckelrotation, manuell scan, dashboard, felsökning.

## Snabbstart

```bash
git clone https://github.com/ThorstenGru/SkanetrafikenForseningar.git
cd SkanetrafikenForseningar
pip install -r requirements.txt
export TRAFIKLAB_STATIC_KEY=...      # från developer.trafiklab.se
export TRAFIKLAB_REALTIME_KEY=...
python src/scan.py                   # kör en scan, skriver till data/forseningar.db
python src/build_dashboard.py        # bygger dashboard.html för idag
```

I produktion behövs inget av ovanstående lokalt — GitHub Actions kör `scan.py`
automatiskt varannan timme och committar resultatet. Se
[docs/RUNBOOK.md](docs/RUNBOOK.md) för hur du genererar en dashboard från den
datan utan att röra API-nycklarna alls.

## Arkitektur

1. **Statiskt index** (`data/static_index.sqlite`) — rutter, hållplatser och varje
   turs destination (härledd ur sista hållplatsen i `stop_times.txt`). Byggs om en
   gång i veckan (`STATIC_CACHE_MAX_AGE_DAYS` i `src/config.py`) för att skona den
   knappa static-kvoten (60 anrop/30 dagar). Den råa GTFS-zippen (~300 MB uppackad)
   laddas ner till `.gtfs_static_raw/` och raderas direkt efter — bara det destillerade
   indexet committas.
2. **Realtidsdata** hämtas varje körning:
   - `TripUpdates.pb` — förseningar per hållplats + inställda turer.
   - `ServiceAlerts.pb` — orsakskoder (cause/effect) och fritextbeskrivningar för
     kända störningar (vägarbete, flyttade hållplatser, etc).
3. Allt skrivs till `data/forseningar.db` med **deduplicering**: samma tur+datum+hållplats
   uppdateras (inte dupliceras) vid varje ny poll, med `first_seen_at`/`last_seen_at`/
   `poll_count` och den största observerade förseningen (`max_abs_delay_sec`), eftersom
   en försenings-siffra kan ändras flera gånger under en resas gång.

## Databasschema (`data/forseningar.db`)

- **delays** — en rad per (trip_id, trip_start_date, stop_id). Innehåller linje,
  destination, hållplats, schemalagd tid *och* faktisk tid (beräknad som `time - delay`
  från realtidsfeeden — ingen tung indexering av hela `stop_times.txt` krävs), försening
  i sekunder, veckodag, och om det är sista hållplatsen på turen (`is_final_stop` — mest
  relevant för kompensationsanspråk, där ankomsttiden på slutdestinationen brukar räknas).
- **trip_cancellations** — hela turer med `schedule_relationship = CANCELED`.
- **alerts** / **alert_entities** — kända störningar med orsak/effekt-koder och fritext,
  kopplade till route_id/trip_id/stop_id där Skånetrafiken har angett det.
- **scan_runs** — logg över varje körning (antal sedda/nya rader, ev. fel) för felsökning.

⚠️ **Viktig begränsning:** Bara en delmängd av förseningarna kommer ha en matchande
alert med orsak. De flesta "vanliga" förseningar i trafiken saknar en registrerad
orsak i Trafiklabs feed — `alerts`-tabellen är bäst-möjlig-koppling, inte facit.

## Körning lokalt

```bash
pip install -r requirements.txt
export TRAFIKLAB_STATIC_KEY=...
export TRAFIKLAB_REALTIME_KEY=...
python src/scan.py
```

## Säkerhet

API-nycklarna sätts **aldrig** i kod — de läses från miljövariabler
(`TRAFIKLAB_STATIC_KEY`, `TRAFIKLAB_REALTIME_KEY`), och i GitHub Actions från
repots secrets.

⚠️ De nycklar som användes under utveckling av detta projekt har tidigare synts
i klartext i en chattkonversation och bör roteras på developer.trafiklab.se
så snart som möjligt — uppdatera sedan GitHub-secrets med `gh secret set`.

## Verktyg i repot

| Script | Syfte |
|---|---|
| `src/scan.py` | Kör en scan (statisk uppdatering vid behov + realtidsdata → databas). Körs automatiskt av GitHub Actions. |
| `src/build_dashboard.py` | Bygger en fristående HTML-dashboard (filter/sortering/orsak) för en given dag, helt från lokal data. |
| `src/static_index.py` | Kan köras separat för att tvinga fram en omgång av det statiska indexet. |

## Kända begränsningar / framtida idéer

- Ingen väderdata korrelerad ännu (skulle stärka mönsteranalys).
- Inget fordons-ID (kräver `VehiclePositions.pb`, ej implementerat).
- Ingen filtrering på "mina linjer/hållplatser" ännu — dashboarden visar hela
  nätet. Ett färdigt underlag riktat mot en specifik kompensationsanmälan till
  Skånetrafiken (bara dina egna resor) är nästa naturliga steg ovanpå
  `build_dashboard.py`.
- `data/forseningar.db` växer obegränsat. Fungerar fint i git ett tag, men om den
  blir stor (hundratals MB) kan det bli aktuellt att dela upp per månad/år.
