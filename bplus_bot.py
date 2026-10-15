"""
BTC snapshot (Coinglass-style) + HINT + TIMEFRAME RELIABILITY -> Telegram.
Sirf info, trade nahi.

Futures CVD / OI / Funding : Coinalyze (Binance BTCUSDT perp)
Spot CVD + Price           : Binance public data (data-api.binance.vision)
Premium                    : Coinbase BTC-USD vs Binance BTCUSDT (optional)

Keys GitHub Secrets me hain. Code me kabhi key mat likhna.
"""
import os
import sys
import time
import math
import requests
from urllib.parse import quote
from datetime import datetime, timezone, timedelta

CZ_KEY = os.environ.get("COINALYZE_API_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

COIN = "BTC"
CZ = "https://api.coinalyze.net/v1"
BV = "https://data-api.binance.vision/api/v3"
CB = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"
YF = "https://query1.finance.yahoo.com/v8/finance/chart/"   # DXY / US10Y (free, unofficial)

# (naam, coinalyze interval, binance interval, seconds)
TFS = [("4H", "4hour", "4h", 14400),
       ("1H", "1hour", "1h", 3600),
       ("15M", "15min", "15m", 900)]

FUNDING_IS_PERCENT = True

# ---- Thresholds (andaaze hain) ----
PRICE_TH = {"4H": 0.30, "1H": 0.15, "15M": 0.08}   # price change % (is se kam = flat)
OI_TH = {"4H": 0.30, "1H": 0.15, "15M": 0.05}      # OI change % (is se kam = flat)
SPOT_TH = 0.03                                      # spot CVD / volume (3% se kam = flat)
PREMIUM_TH = 0.03                                   # tumhare notes ka +-0.03%

# ---- Timeframe reliability ----
REL_DAYS = 60          # kitne din ka data dekhna hai
REL_HORIZON = 16       # 15m candles me: Spot CVD ke baad 4H aage tak price dekho
REL_MIN_N = 30         # isse kam signals = data kam
REL_Z = 2.5            # isse kam z-score = noise (windows overlap karti hain, isliye strict)

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


def yahoo_quote(sym):
    """(abhi ka level, pichhle din ka close). Free Yahoo data, thoda delayed ho sakta hai."""
    r = requests.get(YF + quote(sym, safe=""), params={"interval": "1d", "range": "5d"},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    price = res["meta"]["regularMarketPrice"]
    closes = [x for x in res["indicators"]["quote"][0]["close"] if x is not None]
    prev = closes[-2] if len(closes) >= 2 else res["meta"].get("chartPreviousClose")
    return price, prev


def macro_lines():
    out = []
    dxy = safe("DXY", yahoo_quote, "DX-Y.NYB")
    if dxy and dxy[1]:
        p, pv = dxy
        ch = (p - pv) / pv * 100
        out.append(f"DXY: {p:.2f} ({ch:+.2f}%) {'▲' if ch > 0 else '▼' if ch < 0 else '▬'}")
    else:
        out.append("DXY: NA")
    y10 = safe("US10Y", yahoo_quote, "^TNX")
    if y10 and y10[1]:
        p, pv = y10
        ch = (p - pv) / pv * 100
        bps = (p - pv) * 100
        out.append(f"US10Y: {p:.3f}% ({ch:+.2f}% | {bps:+.1f}bps) {'▲' if ch > 0 else '▼' if ch < 0 else '▬'}")
    else:
        out.append("US10Y: NA")
    return out


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


# ---------- rules (tumhare notes se, neutral shabdon me) ----------
def sign(x, th):
    return 1 if x > th else (-1 if x < -th else 0)


def pct(a, b):
    return (b - a) / a * 100 if a else 0.0


def case_text(p, s, o):
    """p = price dir, s = spot CVD dir, o = OI dir (1 up, -1 down, 0 flat)."""
    if p == 0:
        return "Price flat, koi case lagu nahi"
    if p == 1 and s == 1:
        return "Case 1: Price up + Spot buying saath" + (", OI bhi badh raha" if o == 1 else "")
    if p == 1 and s == 0:
        return ("Case 2: Price up, Spot flat (buy futures se aa raha ho sakta hai)" +
                (", OI badh raha = naye leverage longs, trap ho sakta hai" if o == 1 else ""))
    if p == 1 and s == -1:
        return "Case 3: Price up par Spot sell kar raha, Spot saath nahi de raha"
    if p == -1 and s == -1:
        t = "Case 4: Price down + Spot selling saath"
        if o == 1:
            t += ", OI badh raha = naye shorts add ho rahe ho sakte hain"
        elif o == -1:
            t += ", OI gir raha = long liquidation ho sakti hai"
        return t
    if p == -1 and s == 0:
        return "Case 5: Price down, Spot flat (sell futures se aa raha ho sakta hai)"
    return "Case 6: Price down par Spot buying, absorption ho sakta hai (pakka nahi)"


def overall(d4, d1, d15):
    """Spot direction ko 3 timeframe me match karo. Priority: 4H, 1H phir 15M."""
    names = {1: "BULLISH", -1: "BEARISH"}
    if d4 != 0 and d4 == d1 == d15:
        return "A+", names[d4], "Teeno timeframe me Spot ek taraf"
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
        return f"Premium {prem:+.3f}%: Spot up + Coinbase premium upar (US side ka saath)"
    if direction == "BEARISH" and prem <= -PREMIUM_TH:
        return f"Premium {prem:+.3f}%: Spot down + Coinbase premium neeche (US side ka saath)"
    return f"Premium {prem:+.3f}%: neutral (premium ka saath nahi)"


# ---------- timeframe reliability ----------
def fetch_hist_15m(days):
    end = int(time.time() * 1000)
    t = end - days * 86400 * 1000
    out = []
    while t < end:
        r = requests.get(f"{BV}/klines",
                         params={"symbol": f"{COIN}USDT", "interval": "15m",
                                 "startTime": t, "limit": 1000}, timeout=30)
        r.raise_for_status()
        kk = r.json()
        if not kk:
            break
        out += kk
        t = kk[-1][0] + 900000
        time.sleep(0.2)
    out = [x for x in out if x[6] < end]
    return [(int(x[0]) // 1000, float(x[1]), float(x[4]), float(x[5]), float(x[9]))
            for x in out]


def closed_candles(c, secs):
    per = secs // 900
    out, cur = [], None
    for i, (ts, o, cl, v, tb) in enumerate(c):
        start = ts - ts % secs
        if cur is None or cur["start"] != start:
            cur = {"start": start, "n": 0, "vol": 0.0, "buy": 0.0}
        cur["n"] += 1
        cur["vol"] += v
        cur["buy"] += tb
        if cur["n"] == per:
            out.append((i, cur["vol"], cur["buy"]))
    return out


def reliability(c):
    """Har timeframe: Spot CVD ki direction ke baad 4H aage price usi taraf gaya, baseline se kitna behtar."""
    h = REL_HORIZON
    n_all = len(c) - h
    if n_all <= 0:
        return {}
    base_up = sum(1 for i in range(n_all) if c[i + h][2] > c[i][2]) / n_all * 100
    res = {}
    for tf, secs in (("4H", 14400), ("1H", 3600), ("15M", 900)):
        wins = n = 0
        exp = 0.0
        for i, vol, buy in closed_candles(c, secs):
            if i + h >= len(c):
                continue
            s = sign((2 * buy - vol) / vol if vol else 0, SPOT_TH)
            if s == 0:
                continue
            r = (c[i + h][2] - c[i][2]) / c[i][2] * 100 * s
            n += 1
            wins += 1 if r > 0 else 0
            exp += base_up if s == 1 else 100 - base_up
        if n:
            edge = wins / n * 100 - exp / n
            z = edge / (50 / math.sqrt(n))
            res[tf] = (edge, n, z)
    return res


def reliability_text(res):
    if not res:
        return None
    lines = []
    for tf in ("4H", "1H", "15M"):
        if tf not in res:
            lines.append(f"{tf}: NA")
            continue
        edge, n, z = res[tf]
        if n < REL_MIN_N:
            tag = "data kam"
        elif z >= REL_Z:
            tag = "kuch asar"
        elif z <= -REL_Z:
            tag = "ULTA chal raha"
        else:
            tag = "noise"
        lines.append(f"{tf}: {edge:+.1f} pts vs baseline (n={n}) {tag}")
    return "\n".join(lines)


def main():
    dry = os.environ.get("DRY_RUN") == "1"     # test mode: Telegram pe nahi bhejta
    if not CZ_KEY or (not dry and not (TG_TOKEN and TG_CHAT)):
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
    hist = safe("history", fetch_hist_15m, REL_DAYS)
    rel = reliability_text(reliability(hist)) if hist else None

    ist = timezone(timedelta(hours=5, minutes=30))
    msg = f"📊 {COIN} SNAPSHOT\nPrice: {price:.1f}\n\n" if price else f"📊 {COIN} SNAPSHOT\n\n"
    msg += "\n\n".join(blocks)
    msg += f"\n\nPremium (Coinbase): {prem:+.3f}%" if prem is not None else "\n\nPremium: NA"
    if fund:
        msg += f"\nFunding now: {fund[0]:.4f}%\nFunding 1D avg: {fund[1]:.4f}%"
    else:
        msg += "\nFunding: NA"

    msg += "\n\n🌍 MACRO (daily change)\n" + "\n".join(macro_lines())

    grade, direction, why = overall(dirs["4H"], dirs["1H"], dirs["15M"])
    msg += f"\n\n🧠 HINT\n{grade} | {direction}\n{why}\n"
    for name in ("4H", "1H", "15M"):
        msg += f"\n{name}: {hints[name]}"
    ph = premium_hint(direction, prem)
    if ph:
        msg += f"\n\n{ph}"
    if rel:
        msg += f"\n\n{rel}"
    if errors:
        msg += "\n⚠ Data fail: " + ", ".join(errors)
    print(msg)
    if dry:
        print("\n[DRY_RUN] Telegram pe nahi bheja")
        return

    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id": TG_CHAT, "text": msg}, timeout=30)
    r.raise_for_status()


if __name__ == "__main__":
    main()
       
