"""Decides whether a scheduled workflow should still do any work, given
where today sits relative to the season window in config.py.

The season this project documents is fixed (config.WINDOW_START ..
config.WINDOW_END). Once it ends there is nothing left to poll for, and a
couple of days later nothing left to rebuild either -- at which point every
workflow should go quiet permanently rather than keep opening connections to
Supabase forever for a dataset that can no longer change. That shutdown is
the difference between this project costing egress indefinitely and costing
none at all (see docs/RUNBOOK.md, "After the season").

Deliberately date-driven rather than state-driven: no marker row, no cache,
nothing to get out of sync. Every run recomputes the same answer from the
calendar, so a re-run, a manual dispatch and a replayed workflow all agree.

Phases:
    scan          -- stops at WINDOW_END. No new data can belong to the
                     season after it closes.
    build         -- stops at WINDOW_END + WINDOW_GRACE_DAYS, so the finished
                     season is guaranteed at least one final build+deploy.
    housekeeping  -- same bound as build: one guaranteed final purge of
                     anything that landed outside the window, then quiet.

Writes `should_run=true|false` on stdout in GitHub Actions' own
$GITHUB_OUTPUT format, and a human-readable explanation on stderr so the
reason a run skipped is visible in the Action log rather than silent.

Usage:
    python src/window_guard.py --phase scan >> "$GITHUB_OUTPUT"
"""

import argparse
import sys

import config

PHASES = ("scan", "build", "housekeeping")


def should_run(phase, today=None):
    """(bool, reason). `today` is injectable so this is testable without
    waiting for August."""
    today = today or config.today_local()
    start, end = config.WINDOW_START, config.WINDOW_END

    if today < start:
        return False, "season has not started yet (opens %s)" % start

    if phase == "scan":
        if config.window_is_closed(today):
            return False, "season closed on %s -- no new data can belong to it" % end
        return True, "season is open (%s .. %s)" % (start, end)

    # build / housekeeping both get the post-season grace period.
    if config.past_grace_period(today):
        return False, (
            "season closed on %s and the %d-day wind-down is over -- "
            "the dataset is final and the site is static" % (end, config.WINDOW_GRACE_DAYS)
        )
    if config.window_is_closed(today):
        return True, "season closed on %s -- final %s pass within the wind-down" % (end, phase)
    return True, "season is open (%s .. %s)" % (start, end)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=PHASES)
    args = parser.parse_args()

    run, reason = should_run(args.phase)
    print("should_run=%s" % ("true" if run else "false"))
    print(
        "%s: %s -- %s" % (args.phase, "RUN" if run else "SKIP", reason),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
