import os, requests
PROXY = os.getenv("CLOUDFLARE_PROXY").rstrip("/")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")

def via_proxy(url):
    r = requests.get(f"{PROXY}/?url={url}", timeout=15)
    return r.json()

# Test
btc = via_proxy("https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT")
print(btc) # {"symbol":"BTCUSDT","price":"838..."}
