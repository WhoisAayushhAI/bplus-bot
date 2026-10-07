import os, requests
from datetime import datetime, timedelta, timezone

PROXY = (os.getenv("CLOUDFLARE_PROXY") or "https://aayush-proxy.aayushrathod7878.workers.dev").strip().rstrip("/")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def via_proxy(url):
    try:
        r = requests.get(f"{PROXY}/?url={url}", timeout=20)
        return r.json()
    except:
        return None

def get_tf_data(bar):
    spot_url = f"https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar={bar}&limit=2"
    spot = via_proxy(spot_url)
    spot_now = spot_prev = 0
    if spot and spot.get("data") and len(spot["data"])>=2:
        spot_now = float(spot["data"][0][4])
        spot_prev = float(spot["data"][1][4])

    fut_url = f"https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar={bar}&limit=2"
    fut = via_proxy(fut_url)
    fut_now = fut_prev = 0
    if fut and fut.get("data") and len(fut["data"])>=2:
        fut_now = float(fut["data"][0][4])
        fut_prev = float(fut["data"][1][4])

    oi_url = f"https://www.okx.com/api/v5/public/open-interest-history?instId=BTC-USDT-SWAP&period={bar}&limit=2"
    oi = via_proxy(oi_url)
    oi_now = oi_prev = 0
    if oi and oi.get("data") and len(oi["data"])>=2:
        oi_now = float(oi["data"][0]["oi"])
        oi_prev = float(oi["data"][1]["oi"])

    return {
        "spot_now": spot_now, "spot_chg": spot_now - spot_prev,
        "fut_now": fut_now, "fut_chg": fut_now - fut_prev,
        "oi_now": oi_now, "oi_chg": oi_now - oi_prev
    }

def send(msg):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

data_4h = get_tf_data("4H")
data_1h = get_tf_data("1H")
data_15m = get_tf_data("15m")

ticker = via_proxy("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT")
price = float(ticker["data"][0]["last"]) if ticker and ticker.get("data") else 0

fund_now_data = via_proxy("https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP")
fund_now = float(fund_now_data["data"][0]["fundingRate"]) if fund_now_data and fund_now_data.get("data") else 0

fund_hist = via_proxy("https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=8")
fund_1d_avg = 0
if fund_hist and fund_hist.get("data"):
    vals = [float(x["fundingRate"]) for x in fund_hist["data"][:3]]
    fund_1d_avg = sum(vals)/len(vals) if vals else 0

# IST Time without pytz
ist = timezone(timedelta(hours=5, minutes=30))
now_ist = datetime.now(ist).strftime("%d-%m %I:%M:%S %p IST")

msg = f"""📊 *BPLUS MTF*

*Price:* {price:.1f}

*4H*
Future: {data_4h['fut_now']:.1f} ({data_4h['fut_chg']:+.1f})
Spot: {data_4h['spot_now']:.1f} ({data_4h['spot_chg']:+.1f})
OI: {data_4h['oi_now']:.0f} ({data_4h['oi_chg']:+.0f})

*1H*
Future: {data_1h['fut_now']:.1f} ({data_1h['fut_chg']:+.1f})
Spot: {data_1h['spot_now']:.1f} ({data_1h['spot_chg']:+.1f})
OI: {data_1h['oi_now']:.0f} ({data_1h['oi_chg']:+.0f})

*15M*
Future: {data_15m['fut_now']:.1f} ({data_15m['fut_chg']:+.1f})
Spot: {data_15m['spot_now']:.1f} ({data_15m['spot_chg']:+.1f})
OI: {data_15m['oi_now']:.0f} ({data_15m['oi_chg']:+.0f})

*Funding*
Current: {fund_now:.8f}
1Day Avg: {fund_1d_avg:.8f}

*Time:* {now_ist}
"""

print(msg)
send(msg)
