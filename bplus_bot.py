import requests, time, os, sys

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

print(f"TOKEN present: {bool(TELEGRAM_BOT_TOKEN)} len={len(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else 0}")
print(f"CHAT_ID present: {bool(TELEGRAM_CHAT_ID)} value={TELEGRAM_CHAT_ID}")

SYMBOL = "BTCUSDT"

def bybit_get(url, params):
    for _ in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            data = r.json()
            if data.get('retCode') == 0:
                return data
        except Exception as e:
            print(f"Bybit error {url}: {e}")
            time.sleep(2)
    return None

def send_tg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Secrets missing! Check Settings > Secrets")
        sys.exit(1)

    # Token me 'bot' word nahi hona chahiye
    token = TELEGRAM_BOT_TOKEN.strip()
    if token.startswith("bot"):
        token = token[3:]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID.strip(), "text": msg, "parse_mode": "Markdown"}

    try:
        print(f"Sending to Telegram... chat_id={TELEGRAM_CHAT_ID}")
        r = requests.post(url, data=data, timeout=15)
        print("Telegram status:", r.status_code)
        print("Telegram response:", r.text)
        r.raise_for_status()
        print("✅ Message sent!")
    except Exception as e:
        print("❌ Telegram error:", e)
        if 'r' in locals():
            print("Response text:", r.text)
        sys.exit(1) # Isse workflow FAIL hoga, pata chalega

def get_real_cvd(cat,sym,m=15):
    d=bybit_get("https://api.bybit.com/v5/market/recent-trade",{"category":cat,"symbol":sym,"limit":1000})
    if not d:
        return 0,0,0,0
    now=int(time.time()*1000)
    cut=now-m*60*1000
    buy=sell=0.0
    for t in d['result']['list']:
        if int(t['time'])<cut:
            continue
        sz=float(t['size'])
        if t['side']=='Buy':
            buy+=sz
        else:
            sell+=sz
    return buy,sell,buy-sell,0

def analyze():
    print("Fetching Bybit data...")
    oi=bybit_get("https://api.bybit.com/v5/market/open-interest",{"category":"linear","symbol":SYMBOL,"intervalTime":"15min","limit":3})
    kl=bybit_get("https://api.bybit.com/v5/market/kline",{"category":"linear","symbol":SYMBOL,"interval":"15","limit":3})
    if not oi or not kl:
        print("Failed to get OI/Kline")
        sys.exit(1)

    curr_oi=float(oi['result']['list'][0]['openInterest'])
    prev_oi=float(oi['result']['list'][1]['openInterest'])
    curr_c=float(kl['result']['list'][0][4])
    prev_c=float(kl['result']['list'][1][4])
    oi_up=curr_oi>prev_oi
    price_up=curr_c>prev_c
    price_down=curr_c<prev_c
    _,_,f_cvd,_=get_real_cvd("linear",SYMBOL,15)
    _,_,s_cvd,_=get_real_cvd("spot",SYMBOL,15)

    print(f"Price {curr_c} OI {curr_oi} OI_up:{oi_up} Fut:{f_cvd} Spot:{s_cvd}")

    if price_up and oi_up and f_cvd>0 and s_cvd>0:
        msg=f"🟢 *B+ LONG 15M CLOUD* {curr_c} OI {curr_oi:.0f} Fut {f_cvd:+.2f} Spot {s_cvd:+.2f}"
    elif price_down and oi_up and f_cvd<0 and s_cvd<0:
        msg=f"🔴 *B+ SHORT 15M CLOUD* {curr_c} OI {curr_oi:.0f} Fut {f_cvd:+.2f} Spot {s_cvd:+.2f}"
    else:
        msg=f"ℹ️ *No B+ 15M CLOUD* Price {curr_c} OI UP:{oi_up} Fut {f_cvd:+.2f} Spot {s_cvd:+.2f}"

    send_tg(msg)

analyze()
