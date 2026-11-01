"""Probe: Yahoo Finance ^JKSE via yfinance (cookie and crumb), monthly and daily, max range. Round 2 after HTTP 429 on the bare API."""
import sys, pathlib, traceback
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
log = []
try:
    import yfinance as yf
    for iv in ["1mo", "1d"]:
        try:
            df = yf.Ticker("^JKSE").history(period="max", interval=iv, auto_adjust=False)
            df.to_csv(out / f"jkse_{iv}.csv")
            log.append(f"{iv}: {len(df)} rows {df.index.min()}..{df.index.max()}; first close {df['Close'].iloc[0] if len(df) else None}; last {df['Close'].iloc[-1] if len(df) else None}")
        except Exception as e:
            log.append(f"{iv}: {type(e).__name__} {e}")
except Exception:
    log.append(traceback.format_exc())
(out / "log.txt").write_text("\n".join(log) + "\n"); print("\n".join(log))
