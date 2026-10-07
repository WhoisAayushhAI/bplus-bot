"""
BTC snapshot (Coinglass-style) -> Telegram. Sirf info, trade nahi.

Futures CVD / OI / Funding : Coinalyze (Binance BTCUSDT perp)
Spot CVD                   : Binance public data (data-api.binance.vision)
Premium                    : Coinbase BTC-USD vs Binance BTCUSDT (optional)

Keys GitHub Secrets me. Pydroid me test karna ho to neeche constants bharo,
par wo file kabhi GitHub pe upload mat karna.
"""
import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta

CZ_KEY = os.environ.get("COINALYZE_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

COIN = "BTC"
CZ = "https://api.coinalyze.net/v1"
BV = "https://data-api.binance.vision/api/v3"
CB = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"

# (naam, coinalyze interval, binance interval, seconds)
TFS = [("4H", "4hour", "4h", 14400),
       ("1H", "1hour", "1h", 3600),
       ("15M", "15min", "15m", 900)]

# Pehli run me Coinglass se match karke dekho. Agar funding 100x bada/chhota
# dikhe to isse False/True karo.
FUNDING_IS_PERCENT = True

errors = []


def cz_get(path, params):
    params = dict(params, api_key=CZ_KEY)
    for _ in range(3):
        r = requests.get(f"{CZ}/{path}", params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5")) + 1)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Coinalyze rate limit")


def find_symbol():
    for m in cz_get("future-markets", {}):
        if (m.get("exchange") == "A" and m.get("is_perpetual")
                and m.get("symbol_on_exchange") == f"{COIN}USDT"):
            return m["symbol"]
    raise RuntimeError("Coinalyze perp symbol nahi mila")


def cum_from_to(deltas):
    """Cumulative CVD: last candle ka (from, to). Anchor Coinglass se alag hoga."""
    total = sum(deltas)
    return total - deltas[-1], total


def fut_cvd_and_oi(sym, cz_int, secs, now):
    base = {"symbols": sym, "interval": cz_int, "from": now - 150 * secs, "to": now}
    ohlcv = cz_get("ohlcv-history", base)[0]["history"]
    deltas = [2 * x["bv"] - x["v"] for x in ohlcv]
    f_from, f_to = cum_from_to(deltas)
    oi = cz_get("open-interest-history", dict(base, convert_to_usd="false"))[0]["history"]
    return (f_from, f_to), (oi[-1]["o"], oi[-1]["c"]), ohlcv[-1]["c"]


def spot_cvd(bn_int):
    r = requests.get(f"{BV}/klines",
                     params={"symbol": f"{COIN}USDT", "interval": bn_int, "limit": 150},
                     timeout=30)
    r.raise_for_status()
    k = r.json()
    # index 5 = volume, index 9 = taker buy BASE volume
    deltas = [2 * float(x[9]) - float(x[5]) for x in k]
    return cum_from_to(deltas), float(k[-1][4])


def funding(sym, now):
    cur = cz_get("funding-rate", {"symbols": sym})[0]["value"]
    hist = cz_get("funding-rate-history",
                  {"symbols": sym, "interval": "1hour", "from": now - 24 * 3600, "to": now})
    vals = [h["c"] for h in hist[0]["history"]]
    avg = sum(vals) / len(vals) if vals else cur
    mult = 1 if FUNDING_IS_PERCENT else 100
    return cur * mult, avg * mult


def premium():
    cb = float(requests.get(CB, timeout=20).json()["price"])
    bn = float(requests.get(f"{BV}/ticker/price", params={"symbol": f"{COIN}USDT"},
                            timeout=20).json()["price"])
    return (cb - bn) / bn * 100


def k(x):
    return f"{x/1000:.2f}K" if abs(x) >= 1000 else f"{x:.1f}"


def arrow(a, b):
    return "▲" if b > a else ("▼" if b < a else "▬")


def line(label, pair):
    if not pair:
        return f"{label}: NA"
    a, b = pair
    return f"{label}: {k(a)} to {k(b)} {arrow(a, b)}"


def safe(name, fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # noqa
        errors.append(f"{name}: {type(e).__name__}")
        print(f"{name} error: {e}", file=sys.stderr)
        return None


def main():
    if not (CZ_KEY and TG_TOKEN and TG_CHAT):
        sys.exit("Keys missing")
    now = int(time.time())
    sym = safe("symbol", find_symbol)
    price = None
    blocks = []

    for name, cz_int, bn_int, secs in TFS:
        fut = oi = None
        if sym:
            res = safe(f"fut {name}", fut_cvd_and_oi, sym, cz_int, secs, now)
            if res:
                fut, oi, _ = res
        sp = safe(f"spot {name}", spot_cvd, bn_int)
        spot = None
        if sp:
            spot, p = sp
            if name == "15M":
                price = p
        blocks.append(f"{name}\n{line('Future', fut)}\n{line('Spot', spot)}\n{line('OI', oi)}")
        time.sleep(1)

    fund = safe("funding", funding, sym, now) if sym else None
    prem = safe("premium", premium)

    ist = timezone(timedelta(hours=5, minutes=30))
    msg = f"📊 {COIN} SNAPSHOT\nPrice: {price:.1f}\n\n" if price else f"📊 {COIN} SNAPSHOT\n\n"
    msg += "\n\n".join(blocks)
    msg += f"\n\nPremium (Coinbase): {prem:+.3f}%" if prem is not None else "\n\nPremium: NA"
    if fund:
        msg += f"\nFunding now: {fund[0]:.4f}%\nFunding 1D avg: {fund[1]:.4f}%"
    else:
        msg += "\nFunding: NA"
    msg += f"\n\nTime: {datetime.now(ist).strftime('%d-%m %I:%M %p IST')}"
    if errors:
        msg += "\n⚠ Data fail: " + ", ".join(errors)
    print(msg)

    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id": TG_CHAT, "text": msg}, timeout=30)
    r.raise_for_status()


if __name__ == "__main__":
    main()
            
