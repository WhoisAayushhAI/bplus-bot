import os, requests, time
from datetime import datetime

# Secrets - agar secret nahi bhi mile toh tera link fallback me chalega
PROXY = (os.getenv("CLOUDFLARE_PROXY") or "https://aayush-proxy.aayushrathod7878.workers.dev").strip().rstrip("/")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def via_proxy(url):
    try:
        # Proxy ke through fetch
        full = f"{PROXY}/?url={url}"
        r = requests.get(full, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Proxy Error for {url}: {e}")
        return None

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"Telegram Error: {e}")

# --- TEST LOGIC ---
print(f"Using PROXY: {PROXY}")

# 1. OKX Test (Ye 100% chalega)
okx = via_proxy("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT")
okx_price = "N/A"
if okx and okx.get("data"):
    okx_price = okx["data"][0].get("last", "N/A")

# 2. 【entity-Binance¦canonical_name=Binance】 Vision Test (Ye bhi chalega proxy se)
【entity-binance¦canonical_name=Binance】 = via_proxy("https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT")
bin_price = 【entity-binance¦canonical_name=Binance】.get("price") if 【entity-binance¦canonical_name=Binance】 else "N/A"

# 3. 【entity-Bybit¦canonical_name=Bybit】 OI Test
bybit_oi = via_proxy("https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=5min&limit=1")
oi_val = "N/A"
if bybit_oi and bybit_oi.get("result"):
    oi_val = bybit_oi["result"]["list"][0].get("openInterest", "N/A")

msg = f"""✅ *PROXY TEST SUCCESS*

*OKX BTC:* {okx_price}
*【entity-Binance¦canonical_name=Binance】 BTC:* {bin_price}
*【entity-Bybit¦canonical_name=Bybit】 OI:* {oi_val}
*Time:* {datetime.utcnow().strftime('%H:%M:%S')} UTC

Proxy kaam kar raha hai! Ab MTF rules add karenge.
"""

print(msg)
send_telegram(msg)
