# Datadictionary

## `data/forseningar.db`

### `delays`

En rad per unik `(trip_id, trip_start_date, stop_id)`. Uppdateras (inte
dupliceras) vid varje ny pollning av samma nyckel.

| Kolumn | Typ | Beskrivning |
|---|---|---|
| `trip_id` | TEXT | Trafiklabs interna tur-ID (stabilt per schemalagt turmönster). |
| `trip_start_date` | TEXT | `YYYYMMDD`, från GTFS-RT `trip.start_date`. Krävs för att skilja samma tur olika dagar. |
| `route_id` | TEXT | Rutt-ID från static-datan. |
| `route_short_name` | TEXT | Linjenummer, t.ex. `"817"`. |
| `direction_id` | INTEGER | 0/1, GTFS-riktning. |
| `destination_stop_name` | TEXT | Turens slutdestination, härledd ur sista hållplatsen i `stop_times.txt`. |
| `stop_id` | TEXT | Hållplats-ID för den här raden. |
| `stop_name` | TEXT | Läsbart hållplatsnamn. |
| `stop_sequence` | INTEGER | Hållplatsens ordningsnummer i turen. |
| `is_final_stop` | INTEGER (0/1) | 1 om detta är turens sista hållplats — mest relevant för kompensationsanspråk. |
| `stop_schedule_relationship` | TEXT | `SCHEDULED` / `SKIPPED` / `NO_DATA` / `UNSCHEDULED` för just denna hållplats. |
| `trip_schedule_relationship` | TEXT | `SCHEDULED` / `ADDED` / `CANCELED` / etc för hela turen. |
| `arrival_delay_sec` / `departure_delay_sec` | INTEGER | Försening i sekunder (negativt = före tiden). |
| `arrival_time_epoch` / `departure_time_epoch` | INTEGER | Faktisk tid, unix-epoch (UTC). |
| `scheduled_arrival_epoch` / `scheduled_departure_epoch` | INTEGER | Beräknad som `time - delay`. |
| `max_abs_delay_sec` | INTEGER | Största observerade absoluta försening över alla pollningar av denna rad. |
| `weekday` | INTEGER | 0=måndag .. 6=söndag, från `trip_start_date`. |
| `first_seen_at` / `last_seen_at` | TEXT (ISO 8601, UTC) | När raden först respektive senast sågs i feeden. |
| `poll_count` | INTEGER | Antal gånger denna rad har uppdaterats. |

### `trip_cancellations`

En rad per `(trip_id, trip_start_date)` där hela turen har
`schedule_relationship = CANCELED` (till skillnad från `delays`, där enskilda
hållplatser kan vara `SKIPPED` medan turen i övrigt går).

| Kolumn | Beskrivning |
|---|---|
| `trip_id`, `trip_start_date` | Se ovan. |
| `route_id`, `route_short_name`, `destination_stop_name` | Se ovan. |
| `first_seen_at`, `last_seen_at`, `poll_count` | Se ovan. |

### `alerts`

En rad per unik `alert_uid` (GTFS-RT entity-ID från `ServiceAlerts.pb`).

| Kolumn | Beskrivning |
|---|---|
| `alert_uid` | Feedens entity-ID, primärnyckel. |
| `cause_code` / `cause_label` | GTFS-RT `Alert.Cause`-enum (t.ex. `CONSTRUCTION`, `OTHER_CAUSE`). Ofta `OTHER_CAUSE` — den riktiga orsaken finns i fritexten. |
| `effect_code` / `effect_label` | GTFS-RT `Alert.Effect`-enum. |
| `header_text` / `description_text` | Svensk fritext från Skånetrafiken. |
| `active_period_start_epoch` / `active_period_end_epoch` | Giltighetsperiod, unix-epoch (kan vara `NULL` = tillsvidare). |
| `first_seen_at` / `last_seen_at` | Se ovan. |

### `alert_entities`

Kopplingstabell: en alert kan gälla flera rutter/turer/hållplatser samtidigt.

| Kolumn | Beskrivning |
|---|---|
| `alert_uid` | FK mot `alerts`. |
| `route_id`, `trip_id`, `stop_id` | Vilken av dessa som är satt varierar — Skånetrafiken anger olika granularitet per alert. |

### `scan_runs`

Loggrad per körning, för felsökning och för att se historiken av lyckade/
misslyckade körningar.

| Kolumn | Beskrivning |
|---|---|
| `run_at` | ISO 8601-tidsstämpel för körningen. |
| `delays_seen` / `delays_new` | Antal rader processade respektive nya denna körning. |
| `cancellations_seen` | Antal heltursinställningar denna körning. |
| `alerts_seen` / `alerts_new` | Se ovan, för alerts. |
| `static_refreshed` | 1 om static-indexet byggdes om denna körning. |
| `error` | Textbeskrivning av eventuellt fel (`NULL` om lyckad körning). |

## `data/static_index.sqlite`

Byggs om av `src/static_index.py`, max 1 gång/vecka.

| Tabell | Innehåll |
|---|---|
| `meta` | En rad: `built_at` (unix-epoch för när indexet senast byggdes). |
| `routes` | `route_id` → `short_name`, `long_name`. |
| `stops` | `stop_id` → `stop_name`. |
| `trip_meta` | `trip_id` → `route_id`, `direction_id`, `destination_stop_id`, `destination_stop_name`, `final_stop_sequence`. |
