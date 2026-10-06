import os, sys, time, requests

MY_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN","").strip().lstrip("bot")
MY_CHAT = os.environ.get("TELEGRAM_CHAT_ID","").strip()
print(f"TOKEN len={len(MY_TOKEN)} CHAT={MY_CHAT}")

def okx_get(url, params):
    for i in range(3):
        try:
            r = requests.get(url, params=params, headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
            print(f"GET {url} -> {r.status_code}")
            data = r.json()
            if data.get('code') == '0':
                return data
            print("OKX error:", data)
        except Exception as e:
            print(f"OKX err {e}")
            time.sleep(2)
    return None

def send_tg(msg):
    url = f"https://api.telegram.org/bot{MY_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": MY_CHAT, "text": msg, "parse_mode":"Markdown"}, timeout=15)
    print(f"TG {r.status_code} {r.text[:300]}")
    r.raise_for_status()

def get_cvd(inst, m=15):
    d = okx_get("https://www.okx.com/api/v5/market/history-trades", {"instId": inst, "limit": 1000})
    if not d:
        return 0
    now = int(time.time()*1000)
    cut = now - m*60*1000
    cvd = 0.0
    for t in d['data']:
        if int(t['ts']) < cut:
            continue
        sz = float(t['sz'])
        if t['side'] == 'buy':
            cvd += sz
        else:
            cvd -= sz
    return cvd

def analyze():
    # OKX 15M klines
    kl = okx_get("https://www.okx.com/api/v5/market/candles", {"instId":"BTC-USDT-SWAP","bar":"15m","limit":5})
    oi = okx_get("https://www.okx.com/api/v5/public/open-interest", {"instId":"BTC-USDT-SWAP"})

    if not kl or not oi:
        print("OKX failed")
        send_tg("⚠️ OKX also failed - check net")
        sys.exit(0)

    # kl data is newest first: [ts,o,h,l,c,vol...]
    curr_c = float(kl['data'][0][4])
    prev_c = float(kl['data'][1][4])
    price_up = curr_c > prev_c
    price_down = curr_c < prev_c

    curr_oi = float(oi['data'][0]['oi'])
    # OKX OI endpoint only gives current, so get prev from 15m ago kline vol as proxy, or fetch history OI
    oi_hist = okx_get("https://www.okx.com/api/v5/public/open-interest-history", {"instId":"BTC-USDT-SWAP","period":"5m","limit":4})
    if oi_hist and len(oi_hist['data']) >=2:
        prev_oi = float(oi_hist['data'][1]['oi'])
    else:
        prev_oi = curr_oi

    oi_up = curr_oi > prev_oi

    f_cvd = get_cvd("BTC-USDT-SWAP", 15)
    s_cvd = get_cvd("BTC-USDT", 15)

    print(f"Price {curr_c} prev {prev_c} OI {curr_oi} prevOI {prev_oi} oi_up {oi_up} f_cvd {f_cvd} s_cvd {s_cvd}")

    if price_up and oi_up and f_cvd>0 and s_cvd>0:
        msg = f"🟢 *B+ LONG 15M (OKX CLOUD)* Price {curr_c} OI {curr_oi:.0f} (+{curr_oi-prev_oi:.0f}) Fut CVD {f_cvd:+.2f} Spot CVD {s_cvd:+.2f}"
    elif price_down and oi_up and f_cvd<0 and s_cvd<0:
        msg = f"🔴 *B+ SHORT 15M (OKX CLOUD)* Price {curr_c} OI {curr_oi:.0f} (+{curr_oi-prev_oi:.0f}) Fut CVD {f_cvd:+.2f} Spot CVD {s_cvd:+.2f}"
    else:
        msg = f"ℹ️ *No B+ 15M (OKX)* Price {curr_c} OI UP:{oi_up} Fut {f_cvd:+.2f} Spot {s_cvd:+.2f} Wait for B+"

    send_tg(msg)

analyze()
        
