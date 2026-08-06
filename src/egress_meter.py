"""Measure how many bytes a build actually pulls out of Supabase.

Exists because the 2026-08-06 egress incident was diagnosed structurally --
"five full-window query passes became one" -- without anyone ever knowing
what a pass actually costs in bytes. Query counts are not the billed unit.
Supabase meters egress, the free-tier allowance is shared across the whole
organisation (BliGlomd's production database included), and going over it
returns 402s on every project in the org. That is not a number to run blind
on.

Reads the kernel's own interface counters (/proc/net/dev) rather than trying
to add up row widths in Python, because what Supabase bills is bytes on the
wire: TLS framing, the Postgres protocol's own overhead, and psycopg2's text
representation of every value, none of which a sum of len(str(...)) would
see. Loopback is excluded. Anything else running concurrently on the machine
would be counted too, which is fine on a single-purpose CI runner and the
reason this reports a measurement window rather than a global total.

Degrades to None off Linux (no /proc), so a developer running a build
locally on Windows/macOS just doesn't get the readout.
"""

import os

_PROC_NET_DEV = "/proc/net/dev"


def _read_rx_bytes():
    """Total bytes received across every non-loopback interface, or None
    where /proc isn't available."""
    if not os.path.exists(_PROC_NET_DEV):
        return None
    total = 0
    with open(_PROC_NET_DEV, "r", encoding="utf-8") as f:
        for line in f.readlines()[2:]:  # two header lines
            name, _, rest = line.partition(":")
            name = name.strip()
            if name == "lo" or not rest.strip():
                continue
            total += int(rest.split()[0])
    return total


class EgressMeter:
    """Context manager reporting bytes received during its own block.

    Usage:
        with EgressMeter("page build") as m:
            ...
        print(m.summary())
    """

    def __init__(self, label):
        self.label = label
        self.start = None
        self.end = None

    def begin(self):
        self.start = _read_rx_bytes()
        return self

    def finish(self):
        self.end = _read_rx_bytes()
        return self

    def __enter__(self):
        return self.begin()

    def __exit__(self, *exc):
        self.finish()
        return False  # never suppress

    @property
    def bytes_received(self):
        if self.start is None or self.end is None:
            return None
        return max(0, self.end - self.start)

    def summary(self, builds_remaining=None, allowance_gb=None):
        """Bytes measured, plus what the REST OF THE PROJECT will cost at the
        current cadence.

        Deliberately not a per-30-days projection. This project has a fixed
        end date (config.WINDOW_END), after which window_guard.py stops every
        workflow and the published site is static forever -- so a monthly
        run-rate overstates the real bill and would argue for cutting the
        cadence harder than the facts justify. What matters is the finite
        number of builds actually left."""
        n = self.bytes_received
        if n is None:
            return "Egress meter unavailable on this platform (no %s)." % _PROC_NET_DEV
        mb = n / 1024.0 / 1024.0
        out = "EGRESS: %.1f MB received during %s." % (mb, self.label)
        if builds_remaining is not None:
            total_gb = mb * max(builds_remaining, 0) / 1024.0
            out += " %d build(s) left before the season closes = %.2f GB for the rest of this project's life" % (
                builds_remaining, total_gb)
            if allowance_gb:
                out += " (%.0f%% of the %.1f GB monthly allowance)" % (
                    100.0 * total_gb / allowance_gb, allowance_gb)
            out += "."
        return out
