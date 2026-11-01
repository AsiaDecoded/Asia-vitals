"""Asia Financial tab: year-to-date change of each currency against the US dollar (calculated, asked for 2 Nov 2026).

Reads the BIS daily rates already written for each economy (fx_bis: data/<cc>/fx/<cc>_fx_daily.csv, column rate;
Indonesia id_fx_bis: data/id/fx/id_fx_daily.csv, column usd_idr), national currency per US dollar.

  ytd_pct = (base_rate / latest_rate - 1) * 100

base = the last BIS observation dated on or before 31 December of the previous year; latest = the latest observation.
This is the change in the US-dollar value of the currency: positive means the currency has gained against the dollar.
(The rate itself moves the other way: fewer units per dollar.) Each economy uses its own latest date. Vietnam has no
BIS daily series and is left out.

Output: data/asia/fx/asia_fx_ytd.csv, release.json, release_row.json (code F<latest date>-<hash>).
"""
import csv
import hashlib

from core.common import DATA, read_json, write_release

OUT = DATA / "asia" / "fx"
# economy, name, currency, file under data/, rate column
SPEC = [
    ("JP", "Japan", "JPY", "jp/fx/jp_fx_daily.csv", "rate"),
    ("KR", "South Korea", "KRW", "kr/fx/kr_fx_daily.csv", "rate"),
    ("TW", "Taiwan", "TWD", "tw/fx/tw_fx_daily.csv", "rate"),
    ("HK", "Hong Kong", "HKD", "hk/fx/hk_fx_daily.csv", "rate"),
    ("CN", "China", "CNY", "cn/fx/cn_fx_daily.csv", "rate"),
    ("IN", "India", "INR", "in/fx/in_fx_daily.csv", "rate"),
    ("ID", "Indonesia", "IDR", "id/fx/id_fx_daily.csv", "usd_idr"),
    ("TH", "Thailand", "THB", "th/fx/th_fx_daily.csv", "rate"),
    ("MY", "Malaysia", "MYR", "my/fx/my_fx_daily.csv", "rate"),
    ("SG", "Singapore", "SGD", "sg/fx/sg_fx_daily.csv", "rate"),
    ("PH", "Philippines", "PHP", "ph/fx/ph_fx_daily.csv", "rate"),
]
COLUMNS = ["economy", "name", "currency", "base_date", "base_rate", "latest_date", "latest_rate", "ytd_pct", "file"]


def build():
    rows, warnings = [], []
    for econ, name, ccy, rel, col in SPEC:
        path = DATA / rel
        if not path.exists():
            warnings.append(f"{econ}: data/{rel} not found")
            continue
        with open(path, newline="") as f:
            obs = sorted((r["date"], float(r[col])) for r in csv.DictReader(f) if r.get(col) not in (None, "") and float(r[col]) > 0)
        if not obs:
            warnings.append(f"{econ}: no rates in data/{rel}")
            continue
        last_d, last_v = obs[-1]
        cut = f"{int(last_d[:4]) - 1}-12-31"
        before = [o for o in obs if o[0] <= cut]
        if not before:
            warnings.append(f"{econ}: no rate on or before {cut}")
            continue
        base_d, base_v = before[-1]
        if base_d < f"{int(last_d[:4]) - 1}-12-15":
            warnings.append(f"{econ}: year-end base is {base_d} (gap in the BIS series)")
        rows.append({"economy": econ, "name": name, "currency": ccy, "base_date": base_d, "base_rate": base_v,
                     "latest_date": last_d, "latest_rate": last_v,
                     "ytd_pct": round((base_v / last_v - 1) * 100, 2), "file": f"data/{rel}"})
    if not rows:
        return {"updated": False, "code": None, "summary": "no exchange-rate files", "warnings": warnings}
    dates = sorted({r["latest_date"] for r in rows})
    if len(dates) > 1:
        warnings.append(f"latest dates differ: {', '.join(r['economy'] + ' ' + r['latest_date'] for r in rows if r['latest_date'] != dates[-1])}")
    content = "".join(f"{r['economy']}{r['base_date']}{r['latest_date']}{r['ytd_pct']}" for r in rows)
    code = f"F{dates[-1]}-" + hashlib.sha1(content.encode()).hexdigest()[:6]
    old = read_json(OUT / "release_row.json", [{}]) or [{}]
    if old and old[0].get("code") == code:
        return {"updated": False, "code": code, "summary": "Asia FX unchanged", "warnings": warnings}
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "asia_fx_ytd.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    label = f"BIS daily to {dates[-1]}"
    write_release(OUT, {"code": code, "label": label, "latest_date": dates[-1], "economies": " ".join(r["economy"] for r in rows)},
                  warnings, len(rows))
    return {"updated": True, "code": code, "warnings": warnings,
            "summary": f"{len(rows)} currencies, year to date to {dates[-1]}"}
