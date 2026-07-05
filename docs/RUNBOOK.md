# Runbook

## Rotera API-nycklarna (gör detta snarast — se säkerhetsvarning i README)

Nycklarna som används idag har synts i klartext i en tidigare chatt-session.

1. Logga in på https://developer.trafiklab.se
2. Rotera/generera nya nycklar för **GTFS Regional Static** och
   **GTFS Regional Realtime** (Bronze-tier räcker).
3. Uppdatera GitHub-secrets:
   ```bash
   gh secret set TRAFIKLAB_STATIC_KEY --body "NY_STATIC_NYCKEL" -R ThorstenGru/SkanetrafikenForseningar
   gh secret set TRAFIKLAB_REALTIME_KEY --body "NY_REALTIME_NYCKEL" -R ThorstenGru/SkanetrafikenForseningar
   ```
4. Kör en manuell scan för att verifiera att de nya nycklarna fungerar:
   ```bash
   gh workflow run scan.yml -R ThorstenGru/SkanetrafikenForseningar
   gh run list --workflow=scan.yml -R ThorstenGru/SkanetrafikenForseningar --limit 1
   ```
5. Om du kör lokalt också: uppdatera dina lokala miljövariabler
   (`TRAFIKLAB_STATIC_KEY`, `TRAFIKLAB_REALTIME_KEY`).

Glöm inte att även byta lösenordet för `ThorstenGrund@icloud.com`, som
exponerades i samma tidigare konversation.

## Köra en manuell scan

**Via GitHub Actions (rekommenderat, kräver inget lokalt uppsatt):**
```bash
gh workflow run scan.yml -R ThorstenGru/SkanetrafikenForseningar
```

**Lokalt:**
```bash
cd SkanetrafikenForseningar
pip install -r requirements.txt
export TRAFIKLAB_STATIC_KEY=...
export TRAFIKLAB_REALTIME_KEY=...
python src/scan.py
```

## Generera dashboard

Ingen nätåtkomst eller API-nyckel krävs — läser bara den lokala databasen.
Synka först ner senaste datan med `git pull` om du inte redan har den.

```bash
python src/build_dashboard.py                # idag (lokal tid)
python src/build_dashboard.py --date 20260705
python src/build_dashboard.py --out annan_fil.html
```

Öppna den resulterande `dashboard.html` direkt i en webbläsare.

## Inspektera databasen direkt

```bash
sqlite3 data/forseningar.db
sqlite> SELECT route_short_name, COUNT(*) FROM delays WHERE trip_start_date = '20260705' GROUP BY 1 ORDER BY 2 DESC;
sqlite> .schema delays
```

## Felsökning

| Symptom | Trolig orsak | Åtgärd |
|---|---|---|
| GH Actions-jobbet failar på `Run scanner` med HTTP 403 | Nyckel ogiltig/roterad utan att secrets uppdaterats | Kör steg 3 ovan igen med rätt nyckel |
| HTTP 429 eller kvotfel på static-hämtningen | Static-kvoten (60/30 dagar) förbrukad | Vänta, eller höj `STATIC_CACHE_MAX_AGE_DAYS` i `src/config.py` |
| Alla `route_short_name` visar `okand` | `trip_id`-matchning mot static-indexet missar | Static-indexet kan vara skadat/ur synk — radera `data/static_index.sqlite` och kör om (kostar 1 static-request) |
| Workflow committar inget varannan timme trots att data borde ha ändrats | Normalt — `git diff --cached --quiet` hoppar över commit om inget faktiskt förändrats | Ingen åtgärd |
| `data/forseningar.db` växer väldigt stort (100-tals MB) | Förväntat över lång tid | Överväg att dela upp per månad/år, se README → Framtida idéer |

## Kontrollera körningshistorik

```bash
gh run list --workflow=scan.yml -R ThorstenGru/SkanetrafikenForseningar --limit 10
gh run view <run-id> --log -R ThorstenGru/SkanetrafikenForseningar
```
