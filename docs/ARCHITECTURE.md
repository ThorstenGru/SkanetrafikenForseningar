# Arkitektur

## Flöde, i ordning

```
GitHub Actions (cron var 2:e timme, .github/workflows/scan.yml)
        │
        ▼
src/scan.py
   ├─ 1. static_index.ensure_index()
   │      om data/static_index.sqlite saknas eller är äldre än
   │      STATIC_CACHE_MAX_AGE_DAYS (7 dagar):
   │        → laddar ner hela GTFS-zippen (~300 MB uppackad) till
   │          .gtfs_static_raw/ (aldrig committad)
   │        → destillerar routes.txt + stops.txt + en engångs-pass
   │          över stop_times.txt (finner sista hållplats per trip_id)
   │        → skriver data/static_index.sqlite (routes, stops, trip_meta)
   │        → raderar .gtfs_static_raw/
   │
   ├─ 2. hämtar TripUpdates.pb (förseningar + inställda turer)
   ├─ 3. hämtar ServiceAlerts.pb (orsak/effekt-koder + fritext)
   │
   └─ 4. db.upsert_* mot data/forseningar.db (SQLite)
          → delays, trip_cancellations, alerts, alert_entities, scan_runs
        │
        ▼
GitHub Actions committar data/-mappen och pushar (om något ändrats)
```

## Varför static-datan hanteras separat från realtidsdatan

Trafiklabs static-nyckel har en mycket knapp kvot: 60 anrop/30 dagar. Skulle vi
laddat ner den råa GTFS-zippen (rutter, hållplatser, tidtabeller för hela
regionen) vid varje 2-timmarskörning hade kvoten tagit slut på en dryg vecka.
Tidtabellsdata ändras dessutom sällan (några gånger per år vid större
tidtabellsskiften), så en veckas cache-fönster ger stor marginal (~4
anrop/månad) utan att riskera att missa ett tidtabellsbyte i mer än några
dagar.

Den råa zippen är för stor (~300 MB uppackad, domineras av `stop_times.txt` på
~150 MB) för att committas i git. Vi kör därför en engångs-transformation:
för varje `trip_id` letar vi upp raden med högst `stop_sequence` i
`stop_times.txt` (en enda strömmande genomläsning, minnesåtgången är
begränsad av antal turer — inte antal rader i filen) och sparar bara
destinationens `stop_id`/namn. Resultatet, `data/static_index.sqlite`, är
några MB och committas normalt.

## Varför "schemalagd tid" inte kräver att hela `stop_times.txt` indexeras

GTFS-RT `StopTimeUpdate` innehåller, när Skånetrafiken publicerar det, både
ett absolut `time`-fält (faktisk ankomst/avgång, unix-epoch) **och** ett
`delay`-fält (sekunder). Schemalagd tid är därför helt enkelt:

```
scheduled_time = time - delay
```

Detta undviker att behöva slå upp exakta tabelltider i den 150 MB stora
`stop_times.txt` — realtidsfeeden ger oss redan båda talen vi behöver.

## Deduplicering

Nyckeln `(trip_id, trip_start_date, stop_id)` är unik per rad i `delays`.
Varje ny pollning av samma nyckel **uppdaterar** raden istället för att skapa
en ny: `last_seen_at` och `poll_count` uppdateras, och `max_abs_delay_sec`
hålls kvar som det största observerade värdet (en försening kan både öka och
minska under resans gång, men det är den störst uppmätta förseningen som är
mest relevant som bevis).

Hela turer med `trip.schedule_relationship = CANCELED` hanteras separat i
`trip_cancellations`, eftersom sådana turer ofta saknar `stop_time_update`-rader
helt (och därmed inget att skriva i `delays`).

## Orsakskoppling (ServiceAlerts)

`ServiceAlerts.pb` innehåller `cause`/`effect`-koder (GTFS-RT-spec) och
fritext (`header_text`/`description_text`) på svenska. Kopplingen mot en
specifik försening görs "bäst möjligt": vi letar först efter en alert vars
`informed_entity` pekar exakt på `trip_id`, därefter `stop_id`, därefter
`route_id`. De flesta rutinmässiga förseningar (trafikstockning i vanlig
mening) saknar dock en publicerad alert — reason blir då `null`.

## GitHub Actions-workflow (`.github/workflows/scan.yml`)

- `cron: "0 */2 * * *"` — kör varannan timme, dygnet runt (UTC).
- `workflow_dispatch` — går även att köra manuellt (`gh workflow run scan.yml`).
- `concurrency` med `cancel-in-progress: false` — förhindrar att två körningar
  race:ar mot samma `data/`-commit om en körning skulle dra ut på tiden.
- Secrets `TRAFIKLAB_STATIC_KEY`/`TRAFIKLAB_REALTIME_KEY` injiceras som
  miljövariabler — nycklarna finns aldrig i kod eller loggar.
- Sista steget committar bara om `git diff --cached` faktiskt har ändringar
  (annars blir det tomma commits varannan timme även när inget hänt).

## Dashboard (`src/build_dashboard.py`)

Ett helt fristående, lokalt script: läser `data/forseningar.db`, bygger en
JSON-payload för en given dag, och klistrar in den i
`src/dashboard_template.html` (statisk HTML/CSS/vanilla JS, inga externa
beroenden). Kräver inget nätverksanrop och ingen API-nyckel — all data finns
redan lokalt. Se [RUNBOOK.md](RUNBOOK.md#generera-dashboard).
