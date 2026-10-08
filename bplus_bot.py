"""
BTC snapshot (Coinglass-style) + HINT -> Telegram. Sirf info, trade nahi.

Futures CVD / OI / Funding : Coinalyze (Binance BTCUSDT perp)
Spot CVD + Price           : Binance public data (data-api.binance.vision)
Premium                    : Coinbase BTC-USD vs Binance BTCUSDT (optional)

Keys GitHub Secrets me hain. Code me kabhi key mat likhna.
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

FUNDING_IS_PERCENT = True

# ---- Thresholds (andaaze hain, 1-2 hafte dekh ke tune karna) ----
PRICE_TH = {"4H": 0.30, "1H": 0.15, "15M": 0.08}   # price change % (is se kam = flat)
OI_TH = {"4H": 0.30, "1H": 0.15, "15M": 0.05}      # OI change % (is se kam = flat)
SPOT_TH = 0.03                                      # spot CVD / volume (3% se kam = flat)
PREMIUM_TH = 0.03                                   # tumhare notes ka +-0.03%

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
    total = sum(deltas)
    return total - deltas[-1], total


def fut_cvd_and_oi(sym, cz_int, secs, now):
    base = {"symbols": sym, "interval": cz_int, "from": now - 150 * secs, "to": now}
    ohlcv = cz_get("ohlcv-history", base)[0]["history"]
    deltas = [2 * x["bv"] - x["v"] for x in ohlcv]
    f_from, f_to = cum_from_to(deltas)
    oi = cz_get("open-interest-history", dict(base, convert_to_usd="false"))[0]["history"]
    return (f_from, f_to), (oi[-1]["o"], oi[-1]["c"])


def spot_cvd(bn_int):
    r = requests.get(f"{BV}/klines",
                     params={"symbol": f"{COIN}USDT", "interval": bn_int, "limit": 150},
                     timeout=30)
    r.raise_for_status()
    k = r.json()
    # index 5 = volume, index 9 = taker buy BASE volume
    deltas = [2 * float(x[9]) - float(x[5]) for x in k]
    last = k[-1]
    vol = float(last[5])
    ratio = deltas[-1] / vol if vol else 0.0
    return cum_from_to(deltas), float(last[1]), float(last[4]), ratio


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


# ---------- formatting ----------
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


# ---------- rules (tumhare notes se) ----------
def sign(x, th):
    return 1 if x > th else (-1 if x < -th else 0)


def pct(a, b):
    return (b - a) / a * 100 if a else 0.0


def case_text(p, s, o):
    """p = price dir, s = spot CVD dir, o = OI dir (1 up, -1 down, 0 flat)."""
    if p == 0:
        return "Price flat, koi case lagu nahi"
    if p == 1 and s == 1:
        return "Case 1: real demand" + (", OI bhi badh raha = aur best" if o == 1 else "")
    if p == 1 and s == 0:
        return ("Case 2: spot flat, buy futures kar rahe" +
                (", OI badh raha = naye leverage longs, trap ban sakta hai" if o == 1 else ""))
    if p == 1 and s == -1:
        return "Case 3: sabse dangerous. Spot sell, real demand nahi, long trap ki smell"
    if p == -1 and s == -1:
        t = "Case 4: real selling"
        if o == 1:
            t += ", OI badh raha = naye shorts add"
        elif o == -1:
            t += ", OI gir raha = long liquidation"
        return t
    if p == -1 and s == 0:
        return "Case 5: spot flat, sell futures ne kiya, recovery aa sakti hai"
    return "Case 6: price gir raha, spot up = big players quietly accumulate (Absorption)"


def overall(d4, d1, d15):
    """Spot direction ko 3 timeframe me match karo. Priority: 4H, 1H phir 15M."""
    names = {1: "BULLISH", -1: "BEARISH"}
    if d4 != 0 and d4 == d1 == d15:
        return "A+", names[d4], "Teeno timeframe saath hain"
    if d4 != 0 and d4 == d1:
        if d15 == 0:
            return "B+", names[d4], "4H+1H saath, 15M flat"
        return "B+", names[d4], "4H+1H saath, 15M ulta. 4H/1H ko priority, 15M ke align hone ka wait"
    if d1 != 0 and d1 == d15:
        if d4 == 0:
            return "B+", names[d1], "1H+15M saath, 4H flat"
        return "WAIT", names[d1], "1H+15M ek taraf par 4H ulta hai, 4H sath nahi de raha"
    if d4 != 0 and d4 == d15 and d1 == -d4:
        return "WAIT", names[d4], "4H+15M ek taraf par 1H ulta hai"
    if d4 != 0 and d1 == -d4:
        return "WAIT", "MIXED", "4H aur 1H ulte hain"
    return "NO SIGNAL", "-", "Timeframe ka koi clear match nahi"


def premium_hint(direction, prem):
    if prem is None or direction not in ("BULLISH", "BEARISH"):
        return None
    if direction == "BULLISH" and prem >= PREMIUM_TH:
        return f"Premium {prem:+.3f}%: Spot up + premium upar = real buying"
    if direction == "BEARISH" and prem <= -PREMIUM_TH:
        return f"Premium {prem:+.3f}%: Spot down + premium neeche = real selling"
    return f"Premium {prem:+.3f}%: neutral (spot ko premium ka saath nahi)"


def main():
    if not (CZ_KEY and TG_TOKEN and TG_CHAT):
        sys.exit("Keys missing")
    now = int(time.time())
    sym = safe("symbol", find_symbol)
    price = None
    blocks, hints, dirs = [], {}, {}

    for name, cz_int, bn_int, secs in TFS:
        fut = oi = None
        if sym:
            res = safe(f"fut {name}", fut_cvd_and_oi, sym, cz_int, secs, now)
            if res:
                fut, oi = res
        sp = safe(f"spot {name}", spot_cvd, bn_int)
        spot = None
        s = p = o = 0
        if sp:
            spot, po, pc, ratio = sp
            if name == "15M":
                price = pc
            p = sign(pct(po, pc), PRICE_TH[name])
            s = sign(ratio, SPOT_TH)
            if oi:
                o = sign(pct(oi[0], oi[1]), OI_TH[name])
            hints[name] = case_text(p, s, o)
        else:
            hints[name] = "data NA"
        dirs[name] = s
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

    grade, direction, why = overall(dirs["4H"], dirs["1H"], dirs["15M"])
    msg += f"\n\n🧠 HINT\n{grade} | {direction}\n{why}\n"
    for name in ("4H", "1H", "15M"):
        msg += f"\n{name}: {hints[name]}"
    ph = premium_hint(direction, prem)
    if ph:
        msg += f"\n\n{ph}"
    msg += "\n\nSirf info hai, faisla tumhara."

    msg += f"\nTime: {datetime.now(ist).strftime('%d-%m %I:%M %p IST')}"
    if errors:
        msg += "\n⚠ Data fail: " + ", ".join(errors)
    print(msg)

    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id": TG_CHAT, "text": msg}, timeout=30)
    r.raise_for_status()


if __name__ == "__main__":
    main()
