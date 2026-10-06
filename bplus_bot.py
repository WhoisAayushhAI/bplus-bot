import os, sys, time
MY_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN","").strip().lstrip("bot")
MY_CHAT = os.environ.get("TELEGRAM_CHAT_ID","").strip()
print(f"TOKEN len={len(MY_TOKEN)} CHAT={MY_CHAT}")

# Try cloudscraper for bypass, else requests
try:
    import cloudscraper
    scraper = cloudscraper.create_scraper(browser={'browser':'chrome','platform':'windows','mobile':False})
    print("Using cloudscraper")
    def http_get(url, params, timeout=20):
        return scraper.get(url, params=params, timeout=timeout)
except Exception as e:
    print(f"cloudscraper not available {e}, using requests")
    import requests
    def http_get(url, params, timeout=20):
        return requests.get(url, params=params, headers={"User-Agent":"Mozilla/5.0"}, timeout=timeout)

import requests as req_lib

def bybit_get(url, params):
    for i in range(4):
        try:
            r = http_get(url, params, timeout=20)
            print(f"GET {url} -> {r.status_code} attempt {i+1}")
            txt = r.text.strip()
            if not txt:
                print("Empty response")
                time.sleep(3)
                continue
            if txt.startswith("<") or "Attention Required" in txt or "cf-challenge" in txt:
                print("Cloudflare block HTML:", txt[:400])
                time.sleep(4)
                continue
            data = r.json()
            if data.get('retCode') == 0:
                return data
            else:
                print(f"Bybit retCode {data.get('retCode')} msg {data.get('retMsg')}")
                # if rate limit, wait
                time.sleep(2)
        except Exception as e:
            print(f"Bybit error try {i+1}: {e}")
            if 'r' in locals():
                try:
                    print("Raw:", r.text[:500])
                except:
                    pass
            time.sleep(3+i*2)
    return None

def send_tg(msg):
    if not MY_TOKEN or not MY_CHAT:
        print("Secrets missing")
        sys.exit(1)
    url = f"https://api.telegram.org/bot{MY_TOKEN}/sendMessage"
    r = req_lib.post(url, data={"chat_id": MY_CHAT, "text": msg, "parse_mode":"Markdown"}, timeout=15)
    print(f"TG {r.status_code} {r.text[:400]}")
    r.raise_for_status()

def get_cvd(cat, sym, m=15):
    d = bybit_get("https://api.bybit.com/v5/market/recent-trade", {"category":cat,"symbol":sym,"limit":1000})
    if not d:
        return 0,0
    now = int(time.time()*1000)
    cut = now - m*60*1000
    buy=sell=0.0
    for t in d['result']['list']:
        if int(t['time']) < cut:
            continue
        sz=float(t['size'])
        if t['side']=='Buy':
            buy+=sz
        else:
            sell+=sz
    return buy-sell, buy+sell

def analyze():
    print("Fetching OI and Kline...")
    oi = bybit_get("https://api.bybit.com/v5/market/open-interest", {"category":"linear","symbol":"BTCUSDT","intervalTime":"15min","limit":5})
    kl = bybit_get("https://api.bybit.com/v5/market/kline", {"category":"linear","symbol":"BTCUSDT","interval":"15","limit":5})

    if not oi or not kl:
        # last try with different endpoint domain api.bybit.com -> api.bytick.com sometimes works
        print("Retrying with api.bytick.com fallback")
        oi = bybit_get("https://api.bytick.com/v5/market/open-interest", {"category":"linear","symbol":"BTCUSDT","intervalTime":"15min","limit":5})
        kl = bybit_get("https://api.bytick.com/v5/market/kline", {"category":"linear","symbol":"BTCUSDT","interval":"15","limit":5})

    if not oi or not kl:
        print("Still failed, sending blocked alert")
        send_tg("⚠️ B+ Bot: Bybit still blocking GitHub IP after cloudscraper retry. Will auto-retry in 15m. Setup is OK.")
        sys.exit(0)

    curr_oi = float(oi['result']['list'][0]['openInterest'])
    prev_oi = float(oi['result']['list'][1]['openInterest'])
    curr_c = float(kl['result']['list'][0][4])
    prev_c = float(kl['result']['list'][1][4])
    oi_up = curr_oi > prev_oi
    price_up = curr_c > prev_c
    price_down = curr_c < prev_c

    f_cvd, f_vol = get_cvd("linear","BTCUSDT",15)
    s_cvd, s_vol = get_cvd("spot","BTCUSDT",15)

    print(f"Price {curr_c} prev {prev_c} OI {curr_oi} prevOI {prev_oi} oi_up {oi_up} f_cvd {f_cvd} s_cvd {s_cvd}")

    if price_up and oi_up and f_cvd>0 and s_cvd>0:
        msg = f"🟢 *B+ LONG 15M CLOUD* Price {curr_c} OI {curr_oi:.0f} (+{curr_oi-prev_oi:.0f}) Fut CVD {f_cvd:+.2f} Spot CVD {s_cvd:+.2f}"
    elif price_down and oi_up and f_cvd<0 and s_cvd<0:
        msg = f"🔴 *B+ SHORT 15M CLOUD* Price {curr_c} OI {curr_oi:.0f} (+{curr_oi-prev_oi:.0f}) Fut CVD {f_cvd:+.2f} Spot CVD {s_cvd:+.2f}"
    else:
        msg = f"ℹ️ *No B+ 15M* Price {curr_c} OI UP:{oi_up} (+{curr_oi-prev_oi:.0f}) Fut {f_cvd:+.2f} Spot {s_cvd:+.2f} Wait for B+"

    send_tg(msg)

analyze()
    
