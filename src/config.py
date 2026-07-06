"""Configuration and constants for the Skånetrafiken delay scanner."""

import os
from zoneinfo import ZoneInfo

# Always use this explicitly for any human-facing time display — never bare
# dt.astimezone() with no argument. That converts to whatever timezone the
# MACHINE RUNNING THE CODE happens to be set to, which is fine on a
# developer's own PC but silently wrong in GitHub Actions (UTC runners):
# it displayed every stop time 2 hours early in summer (CEST = UTC+2).
# Found 2026-07-06 by comparing the live dashboard against the real
# Skånetrafiken app for the same trip.
LOCAL_TZ = ZoneInfo("Europe/Stockholm")

OPERATOR = "skane"

STATIC_URL_TMPL = "https://opendata.samtrafiken.se/gtfs/{op}/{op}.zip?key={key}"
TRIPUPDATES_URL_TMPL = "https://opendata.samtrafiken.se/gtfs-rt/{op}/TripUpdates.pb?key={key}"
SERVICEALERTS_URL_TMPL = "https://opendata.samtrafiken.se/gtfs-rt/{op}/ServiceAlerts.pb?key={key}"

# Static data changes rarely (timetable updates a few times a year). The static
# API key has a very low quota (60 requests / 30 days), so we refresh weekly,
# not daily, to keep a safe margin.
STATIC_CACHE_MAX_AGE_DAYS = 7

# How long detailed history is kept in Postgres before daily housekeeping
# deletes it. Applies uniformly to delays, trip_cancellations, seen_trips,
# missing_trips, alerts, and scan_runs.
RETENTION_DAYS = 45

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
STATIC_INDEX_PATH = os.path.join(DATA_DIR, "static_index.sqlite")
RAW_STATIC_CACHE_DIR = os.path.join(REPO_ROOT, ".gtfs_static_raw")  # never committed


def database_url():
    """Postgres connection string (Supabase). Set as the DATABASE_URL secret."""
    return get_key("DATABASE_URL")


def get_key(env_var, fallback=None):
    """Read an API key from the environment (GitHub Actions secret), with an
    optional fallback for local ad-hoc testing."""
    value = os.environ.get(env_var, fallback)
    if not value:
        raise RuntimeError(
            "Saknar API-nyckel: satt miljovariabeln %s (t.ex. via GitHub Actions secret)." % env_var
        )
    return value


def static_key():
    return get_key("TRAFIKLAB_STATIC_KEY")


def realtime_key():
    return get_key("TRAFIKLAB_REALTIME_KEY")


def koda_key():
    """API key for KoDa (Kollektivtrafikens Datalabb), Trafiklab's historical
    GTFS-RT archive — a separate product/key from the live realtime feed,
    used only by backfill_koda.py."""
    return get_key("KODA_API_KEY")


# GTFS-RT Alert.Cause / Alert.Effect enum labels (protobuf spec)
CAUSE_LABELS = {
    1: "UNKNOWN_CAUSE",
    2: "OTHER_CAUSE",
    3: "TECHNICAL_PROBLEM",
    4: "STRIKE",
    5: "DEMONSTRATION",
    6: "ACCIDENT",
    7: "HOLIDAY",
    8: "WEATHER",
    9: "MAINTENANCE",
    10: "CONSTRUCTION",
    11: "POLICE_ACTIVITY",
    12: "MEDICAL_EMERGENCY",
}

EFFECT_LABELS = {
    1: "NO_SERVICE",
    2: "REDUCED_SERVICE",
    3: "SIGNIFICANT_DELAYS",
    4: "DETOUR",
    5: "ADDITIONAL_SERVICE",
    6: "MODIFIED_SERVICE",
    7: "OTHER_EFFECT",
    8: "UNKNOWN_EFFECT",
    9: "STOP_MOVED",
    10: "NO_EFFECT",
    11: "ACCESSIBILITY_ISSUE",
}

SCHEDULE_RELATIONSHIP_LABELS = {
    0: "SCHEDULED",
    1: "SKIPPED",
    2: "NO_DATA",
    3: "UNSCHEDULED",
}

TRIP_SCHEDULE_RELATIONSHIP_LABELS = {
    0: "SCHEDULED",
    1: "ADDED",
    2: "UNSCHEDULED",
    3: "CANCELED",
    5: "DUPLICATED",
    6: "DELETED",
}

# GTFS route_type. Skånetrafiken uses the "extended" hierarchical vehicle
# type codes (100s/700s/900s/1000s/1500s), not just the basic 0-7 enum.
# Confirmed present in their feed (2026-07-05): 100 (rail), 700 (bus),
# 900 (tram), 1000 (ferry), 1501 (demand-responsive/Närtrafik).
ROUTE_TYPE_LABELS = {
    0: "TRAM", 1: "METRO", 2: "RAIL", 3: "BUS", 4: "FERRY",
    5: "CABLE_TRAM", 6: "AERIAL_LIFT", 7: "FUNICULAR", 11: "TROLLEYBUS", 12: "MONORAIL",
    100: "RAIL", 109: "RAIL", 400: "METRO",
    700: "BUS", 701: "BUS", 702: "BUS", 704: "BUS", 715: "DEMAND_RESPONSIVE_BUS",
    900: "TRAM", 1000: "FERRY",
    1500: "TAXI", 1501: "DEMAND_RESPONSIVE_BUS",
}


def route_type_label(route_type):
    if route_type is None:
        return "UNKNOWN"
    return ROUTE_TYPE_LABELS.get(route_type, "OTHER")


# Delay-compensation constants, per docs/COMPENSATION_RULES.md (retrieved
# 2026-07-05 from skanetrafiken.se — they can change these without notice).
# Only used by build_compensation.py; the estimate is illustrative, not a
# real claim calculation.
MIN_DELAY_FOR_COMPENSATION_MIN = 20  # below this, no compensation applies at all

SOMMARBILJETT_PRICE_SEK = 595
SOMMARBILJETT_DIVISOR = 40  # "single trips" the ticket price is divided by for price-deduction purposes
SOMMARBILJETT_SINGLE_TRIP_PRICE_SEK = SOMMARBILJETT_PRICE_SEK / SOMMARBILJETT_DIVISOR  # 14.875 kr

VOUCHER_BONUS = 1.5  # +50% for choosing a voucher code (värdekod) instead of cash — price-deduction only (section 3); no such bonus is documented for alternative-transport reimbursement (section 4)

CAR_RATE_SEK_PER_KM = 2.5  # Swedish Tax Agency's tax-free mileage rate, 25 kr/mil
ALT_TRANSPORT_CAP_SEK = 2960  # max per journey for car/taxi/other-operator reimbursement, effective 2026-01-01


# "Reasonable claim chain" page (build_claims.py): two trips are treated as
# happening at the same physical place — close enough that one could
# realistically have walked from one stop to the other — if their stops are
# within this radius. Covers cases like a bus stop and a train station in
# the same small town having different stop_ids. Not a routing distance,
# just straight-line (haversine).
CLAIM_CHAIN_CONNECT_RADIUS_M = 600


def price_deduction_pct(delay_min):
    """Price-deduction tier for a given final-destination delay, in minutes."""
    if delay_min >= 60:
        return 1.00
    if delay_min >= 40:
        return 0.75
    if delay_min >= 20:
        return 0.50
    return 0.0
