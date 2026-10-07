import os, requests
from datetime import datetime

PROXY = (os.getenv("CLOUDFLARE_PROXY") or "https://aayush-proxy.aayushrathod7878.workers.dev").strip().rstrip("/")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def via_proxy(url):
    try:
        full = f"{PROXY}/?url={url}"
        r = requests.get(full, timeout=20)
        return r.json()
    except Exception as e:
        print(f"Error {url}: {e}")
        return None

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print(e)

print(f"Using PROXY: {PROXY}")

# 1. OKX
okx_data = via_proxy("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT")
okx_last = okx_data["data"][0]["last"] if okx_data and "data" in okx_data else "N/A"

# 2. Binance Vision (block-free)
bn_data = via_proxy("https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT")
bn_last = bn_data.get("price") if bn_data else "N/A"

# 3. Bybit OI
by_data = via_proxy("https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=5min&limit=1")
oi_val = "N/A"
if by_data and by_data.get("result"):
    try:
        oi_val = by_data["result"]["list"][0]["openInterest"]
    except:
        pass

msg = f"PROXY TEST SUCCESS\nOKX: {okx_last}\nBinanceVision: {bn_last}\nBybit OI: {oi_val}\nTime: {datetime.utcnow()}"

print(msg)
send_telegram(msg)
