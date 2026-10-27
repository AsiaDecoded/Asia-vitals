"""Which sources are due today, and when the dashboard refresh should next run (release_calendar.json).

  python -I pipeline/tools/due.py sources [--date YYYY-MM-DD]      # space-separated sources due that day (Singapore date)
  python -I pipeline/tools/due.py next-refresh [--after YYYY-MM-DD] # next refresh date and what it picks up
  python -I pipeline/tools/due.py warnings [--date YYYY-MM-DD]      # calendar running out (45 days ahead)

A source is due from its release date (or window start) to the end of its window: official dates
4 days after release, expected dates to the window's end. The workflow runs at 08:15 and 11:15 SGT,
so a release after 11:15 SGT reaches the repo the next day: refresh dates are the release date for
morning releases and the day after for later ones.
"""
import datetime as dt
import json
import sys
from pathlib import Path

CAL = Path(__file__).resolve().parents[1] / "release_calendar.json"
SGT = dt.timezone(dt.timedelta(hours=8))
CATCHUP = 4


def _d(s):
    return dt.date.fromisoformat(s)


def windows():
    """[(group, source list, from, to, refresh date or None, entry)]"""
    g = json.loads(CAL.read_text())["groups"]
    out = []
    for name, grp in g.items():
        if "follows" in grp:
            continue
        late = grp.get("time_sgt", "00:00") > "11:15"
        for e in grp["dates"]:
            rel = _d(e["date"])
            a = _d(e.get("from", e["date"]))
            b = _d(e["to"]) if "to" in e else rel + dt.timedelta(days=CATCHUP)
            if late:
                b = max(b, rel + dt.timedelta(days=CATCHUP + 1))
            out.append((name, grp["sources"], a, b, rel + dt.timedelta(days=1 if late else 0), e))
    for name, grp in g.items():
        if "follows" in grp:
            for (n, _s, a, _b, _r, e) in [w for w in out if w[0] == grp["follows"]]:
                out.append((name, grp["sources"], a, a + dt.timedelta(days=grp["extra_days"]), None, e))
    return out


def due(day):
    srcs = []
    for _n, sources, a, b, _r, _e in windows():
        if a <= day <= b:
            srcs += [s for s in sources if s not in srcs]
    return srcs


def next_refresh(after):
    by = {}
    g = json.loads(CAL.read_text())["groups"]
    for n, _s, _a, _b, r, e in windows():
        if r and r > after:
            by.setdefault(r, []).append(f"{g[n]['label']} ({e['ref']})")
    if not by:
        return None, []
    d = min(by)
    return d, by[d]


def warnings(day):
    out = []
    g = json.loads(CAL.read_text())["groups"]
    for n, grp in g.items():
        if "follows" in grp:
            continue
        last = max(_d(e["date"]) for e in grp["dates"])
        if last - day < dt.timedelta(days=45):
            out.append(f"ACTION: release calendar for {grp['label']} ends {last}: add the next dates to pipeline/release_calendar.json")
    return out


def main(argv):
    cmd = argv[0]
    today = dt.datetime.now(SGT).date()
    if "--date" in argv:
        today = _d(argv[argv.index("--date") + 1])
    if cmd == "sources":
        print(" ".join(due(today)))
    elif cmd == "next-refresh":
        after = _d(argv[argv.index("--after") + 1]) if "--after" in argv else today
        d, what = next_refresh(after)
        print(d.isoformat() if d else "none")
        for w in what:
            print("  " + w)
    elif cmd == "warnings":
        for w in warnings(today):
            print(w)


if __name__ == "__main__":
    main(sys.argv[1:])
