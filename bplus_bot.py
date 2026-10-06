import requests, time, os, sys

【entity-TOKEN¦canonical_name=TOKEN】 = os.environ.get("TELEGRAM_BOT_TOKEN","").strip().lstrip("bot")
CHAT = os.environ.get("TELEGRAM_CHAT_ID","").strip()

print(f"TOKEN len={len(TOKEN)} CHAT={CHAT}")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

def bybit_get(url, params):
    for i in range(3):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            print(f"GET {url} -> {r.status_code} len={len(r.text)}")
            # agar HTML aaya to log karo
            if r.text.strip().startswith("<"):
                print("HTML response (blocked):", r.text[:400])
                time.sleep(2)
                continue
            data = r.json()
            if data.get('retCode') == 0:
                return data
            else:
                print("Bybit retCode error:", data)
        except Exception as e:
            print(f"Bybit error {url}: {e}")
            if 'r' in locals():
                print("Raw:", r.text[:500])
            time.sleep(2)
    return None

def send_tg(msg):
    if not TOKEN or not CHAT:
        print("Secrets missing"); sys.exit(1)
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": CHAT, "text": msg, "parse_mode":"Markdown"}, timeout=15)
    print("TG:", r.status_code, r.text[:300])
    r.raise_for_status()

def get_real_cvd(cat,sym,m=15):
    d=bybit_get("https://api.bybit.com/v5/market/recent-trade",{"category":cat,"symbol":sym,"limit":1000})
    if not d: return 0,0,0,0
    now=int(time.time()*1000); cut=now-m*60*1000
    buy=sell=0.0
    for t in d['result']['list']:
        if int(t['time'])<cut: continue
        sz=float(t['size'])
        if t['side']=='Buy': buy+=sz
        else: sell+=sz
    return buy,sell,buy-sell,0

def analyze():
    oi=bybit_get("https://api.bybit.com/v5/market/open-interest",{"category":"linear","symbol":"BTCUSDT","intervalTime":"15min","limit":3})
    kl=bybit_get("https://api.bybit.com/v5/market/kline",{"category":"linear","symbol":"BTCUSDT","interval":"15","limit":3})
    if not oi or not kl:
        print("Failed OI/Kline, sending alert anyway")
        send_tg("⚠️ B+ Bot: Bybit API blocked from GitHub (Cloudflare). Will retry next run. Price check manually.")
        sys.exit(0)

    curr_oi=float(oi['result']['list'][0]['openInterest'])
    prev_oi=float(oi['result']['list'][1]['openInterest'])
    curr_c=float(kl['result']['list'][0][4])
    prev_c=float(kl['result']['list'][1][4])
    oi_up=curr_oi>prev_oi
    price_up=curr_c>prev_c
    price_down=curr_c<prev_c
    _,_,f_cvd,_=get_real_cvd("linear","BTCUSDT",15)
    _,_,s_cvd,_=get_real_cvd("spot","BTCUSDT",15)

    if price_up and oi_up and f_cvd>0 and s_cvd>0:
        msg=f"🟢 *B+ LONG 15M CLOUD* {curr_c} OI {curr_oi:.0f} Fut {f_cvd:+.2f} Spot {s_cvd:+.2f}"
    elif price_down and oi_up and f_cvd<0 and s_cvd<0:
        msg=f"🔴 *B+ SHORT 15M CLOUD* {curr_c} OI {curr_oi:.0f} Fut {f_cvd:+.2f} Spot {s_cvd:+.2f}"
    else:
        msg=f"ℹ️ *No B+ 15M CLOUD* {curr_c} OI UP:{oi_up} Fut {f_cvd:+.2f} Spot {s_cvd:+.2f}"
    send_tg(msg)

analyze()
