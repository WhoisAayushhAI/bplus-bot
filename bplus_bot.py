import os, requests
from datetime import datetime

PROXY = (os.getenv("CLOUDFLARE_PROXY") or "https://aayush-proxy.aayushrathod7878.workers.dev").strip().rstrip("/")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def via_proxy(url):
    try:
        r = requests.get(f"{PROXY}/?url={url}", timeout=20)
        return r.json()
    except:
        return None

def get_candles(tf, limit=2):
    # tf = 15m, 1H, 4H
    url = f"https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&bar={tf}&limit={limit}"
    data = via_proxy(url)
    if data and data.get("data"):
        # data[0]=latest, data[1]=prev
        latest_close = float(data["data"][0][4])
        prev_close = float(data["data"][1][4])
        change = ((latest_close - prev_close) / prev_close) * 100
        return latest_close, change
    return None, 0

def send(msg):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

# --- MTF DATA ---
price_15m, chg_15m = get_candles("15m")
price_1h, chg_1h = get_candles("1H")
price_4h, chg_4h = get_candles("4H")

ticker = via_proxy("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT")
spot_price = float(ticker["data"][0]["last"]) if ticker and ticker.get("data") else 0

swap_ticker = via_proxy("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP")
fut_price = float(swap_ticker["data"][0]["last"]) if swap_ticker and swap_ticker.get("data") else spot_price

oi_data = via_proxy("https://www.okx.com/api/v5/public/open-interest?instId=BTC-USDT-SWAP")
oi_now = float(oi_data["data"][0]["oi"]) if oi_data and oi_data.get("data") else 0

fund = via_proxy("https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP")
funding = float(fund["data"][0]["fundingRate"]) if fund and fund.get("data") else 0

# --- AI BRAIN / ABSORPTION LOGIC ---
premium = fut_price - spot_price
signal = "NEUTRAL"
reason = ""

# Rule 1: 15M UP but 4H DOWN
if chg_15m > 0.3 and chg_4h < -0.5:
    signal = "⚠️ FAKE PUMP / ABSORPTION"
    reason = f"15M +{chg_15m:.2f}% but 4H {chg_4h:.2f}% DOWN - Bulls trapped"
elif chg_15m < -0.3 and chg_4h > 0.5:
    signal = "⚠️ FAKE DUMP / ABSORPTION"
    reason = f"15M {chg_15m:.2f}% but 4H +{chg_4h:.2f}% UP - Bears trapped"
elif chg_15m > 0.2 and chg_1h > 0.3 and chg_4h > 0.5:
    signal = "🚀 STRONG UPTREND"
    reason = "All TF aligned UP"
elif chg_15m < -0.2 and chg_1h < -0.3 and chg_4h < -0.5:
    signal = "🔻 STRONG DOWNTREND"
    reason = "All TF aligned DOWN"

# OI Logic
oi_note = "OI Stable"
if oi_now > 3070000: # tu apna threshold dega
    oi_note = "High OI - Big move coming"

msg = f"""📊 *BPLUS MTF FINAL*

*Price:* {spot_price} | Fut: {fut_price} (Prem: {premium:.1f})
*15M:* {chg_15m:+.2f}% | *1H:* {chg_1h:+.2f}% | *4H:* {chg_4h:+.2f}%
*OI:* {oi_now:.0f} | *Funding:* {funding:.6f}

*SIGNAL:* {signal}
*Logic:* {reason}
*Note:* {oi_note}

*Time:* {datetime.utcnow().strftime('%H:%M:%S')} UTC
"""

print(msg)
send(msg)
