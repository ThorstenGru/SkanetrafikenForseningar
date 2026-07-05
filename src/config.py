"""Configuration and constants for the Skånetrafiken förseningsscanner."""

import os

OPERATOR = "skane"

STATIC_URL_TMPL = "https://opendata.samtrafiken.se/gtfs/{op}/{op}.zip?key={key}"
TRIPUPDATES_URL_TMPL = "https://opendata.samtrafiken.se/gtfs-rt/{op}/TripUpdates.pb?key={key}"
SERVICEALERTS_URL_TMPL = "https://opendata.samtrafiken.se/gtfs-rt/{op}/ServiceAlerts.pb?key={key}"

# Static data changes rarely (timetable updates a few times a year). The static
# API key has a very low quota (60 requests / 30 days), so we refresh weekly,
# not daily, to keep a safe margin.
STATIC_CACHE_MAX_AGE_DAYS = 7

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "forseningar.db")
STATIC_INDEX_PATH = os.path.join(DATA_DIR, "static_index.sqlite")
RAW_STATIC_CACHE_DIR = os.path.join(REPO_ROOT, ".gtfs_static_raw")  # never committed


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
