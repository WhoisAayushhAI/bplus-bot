import os, requests
from datetime import datetime, timedelta, timezone

PROXY = (os.getenv("CLOUDFLARE_PROXY") or "https://aayush-proxy.aayushrathod7878.workers.dev").strip().rstrip("/")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def via_proxy(url):
    try:
        r = requests.get(f"{PROXY}/?url={url}", timeout=20)
        j = r.json()
        return j
    except Exception as e:
        print(f"Proxy fail {url} {e}")
        return None

def get_bybit_tf(interval):
    # interval: 15, 60, 240
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval={interval}&limit=2"
    data = via_proxy(url)
    # Bybit return: result.list[0]=latest, [1]=prev : [startTime, open, high, low, close...]
    if data and data.get("result") and data["result"].get("list"):
        lst = data["result"]["list"]
        if len(lst)>=2:
            now = float(lst[0][4])
            prev = float(lst[1][4])
            return now, now-prev, lst
    return 0, 0, []

def send(msg):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

# --- MTF from Bybit (Future) ---
f15_now, f15_chg, _ = get_bybit_tf("15")
f1h_now, f1h_chg, _ = get_bybit_tf("60")
f4h_now, f4h_chg, _ = get_bybit_tf("240")

# Spot price from OKX Ticker (100% working)
ticker = via_proxy("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT")
spot_price = float(ticker["data"][0]["last"]) if ticker and ticker.get("data") else f15_now

# OI
oi_data = via_proxy("https://www.okx.com/api/v5/public/open-interest?instId=BTC-USDT-SWAP")
oi_now = float(oi_data["data"][0]["oi"]) if oi_data and oi_data.get("data") else 0

# Funding
fund_now_data = via_proxy("https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP")
fund_now = float(fund_now_data["data"][0]["fundingRate"]) if fund_now_data and fund_now_data.get("data") else 0

fund_hist = via_proxy("https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=3")
fund_1d = 0
if fund_hist and fund_hist.get("data"):
    vals = [float(x["fundingRate"]) for x in fund_hist["data"]]
    fund_1d = sum(vals)/len(vals) if vals else 0

ist = timezone(timedelta(hours=5, minutes=30))
now_ist = datetime.now(ist).strftime("%d-%m %I:%M:%S %p IST")

msg = f"""📊 *BPLUS MTF - FIXED*

*Price:* {spot_price:.1f}

*4H*
Future: {f4h_now:.1f} ({f4h_chg:+.1f})
Spot: {spot_price:.1f} (same)
OI: {oi_now:.0f}

*1H*
Future: {f1h_now:.1f} ({f1h_chg:+.1f})
Spot: {spot_price:.1f}
OI: {oi_now:.0f}

*15M*
Future: {f15_now:.1f} ({f15_chg:+.1f})
Spot: {spot_price:.1f}
OI: {oi_now:.0f}

*Funding*
Current: {fund_now:.8f}
1Day Avg: {fund_1d:.8f}

*Time:* {now_ist}
"""

print(msg)
send(msg)
