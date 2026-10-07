import os, requests
from datetime import datetime

PROXY = (os.getenv("CLOUDFLARE_PROXY") or "https://aayush-proxy.aayushrathod7878.workers.dev").strip().rstrip("/")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def via_proxy(url):
    try:
        r = requests.get(f"{PROXY}/?url={url}", timeout=20)
        return r.json()
    except Exception as e:
        print(f"Error {url}: {e}")
        return None

def send(msg):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

# OKX Endpoints - Ye sab proxy se chalega
ticker = via_proxy("https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT")
oi_data = via_proxy("https://www.okx.com/api/v5/public/open-interest?instId=BTC-USDT-SWAP")
fund_data = via_proxy("https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP")

price = "N/A"
if ticker and ticker.get("data"):
    price = ticker["data"][0].get("last","N/A")

oi = "N/A"
if oi_data and oi_data.get("data"):
    oi = oi_data["data"][0].get("oi","N/A")

funding = "N/A"
if fund_data and fund_data.get("data"):
    funding = fund_data["data"][0].get("fundingRate","N/A")

msg = f"""✅ *BPLUS PROXY FINAL LIVE*

*BTC Price:* {price}
*OI (BTC-USDT-SWAP):* {oi}
*Funding:* {funding}
*Time:* {datetime.utcnow().strftime('%H:%M:%S')} UTC

Ab 4H + 1H + 15M wala Absorption logic isi me add kar denge.
"""

print(msg)
send(msg)
