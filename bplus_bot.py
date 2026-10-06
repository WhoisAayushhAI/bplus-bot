import os, sys, time, requests

MY_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN","").strip().lstrip("bot")
MY_CHAT = os.environ.get("TELEGRAM_CHAT_ID","").strip()

HEADERS = {"User-Agent":"Mozilla/5.0"}

def send_tg(msg):
    url = f"https://api.telegram.org/bot{MY_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": MY_CHAT, "text": msg, "parse_mode":"Markdown"}, timeout=15)
    print(f"TG {r.status_code}")
    r.raise_for_status()

# --- Fetchers with fallback ---
def get_bybit():
    try:
        # Try Bybit
        oi = requests.get("https://api.bybit.com/v5/market/open-interest", params={"category":"linear","symbol":"BTCUSDT","intervalTime":"15min","limit":2}, headers=HEADERS, timeout=10).json()
        kl = requests.get("https://api.bybit.com/v5/market/kline", params={"category":"linear","symbol":"BTCUSDT","interval":"15","limit":2}, headers=HEADERS, timeout=10).json()
        tr = requests.get("https://api.bybit.com/v5/market/recent-trade", params={"category":"linear","symbol":"BTCUSDT","limit":1000}, headers=HEADERS, timeout=10).json()
        strd = requests.get("https://api.bybit.com/v5/market/recent-trade", params={"category":"spot","symbol":"BTCUSDT","limit":1000}, headers=HEADERS, timeout=10).json()
        if oi.get('retCode')!=0: raise Exception("bybit blocked")
        curr_oi = float(oi['result']['list'][0]['openInterest'])
        prev_oi = float(oi['result']['list'][1]['openInterest'])
        curr_c = float(kl['result']['list'][0][4])
        prev_c = float(kl['result']['list'][1][4])
        now = int(time.time()*1000); cut = now-15*60*1000
        f_cvd=s_cvd=0
        for t in tr['result']['list']:
            if int(t['time'])<cut: continue
            f_cvd += float(t['size']) if t['side']=='Buy' else -float(t['size'])
        for t in strd['result']['list']:
            if int(t['time'])<cut: continue
            s_cvd += float(t['size']) if t['side']=='Buy' else -float(t['size'])
        return {"src":"Bybit","price":curr_c,"prev_price":prev_c,"oi":curr_oi,"prev_oi":prev_oi,"f_cvd":f_cvd,"s_cvd":s_cvd}
    except Exception as e:
        print(f"Bybit fail {e}")
        return None

def get_okx():
    try:
        kl = requests.get("https://www.okx.com/api/v5/market/candles", params={"instId":"BTC-USDT-SWAP","bar":"15m","limit":2}, headers=HEADERS, timeout=10).json()
        oi = requests.get("https://www.okx.com/api/v5/public/open-interest-history", params={"instId":"BTC-USDT-SWAP","period":"5m","limit":2}, headers=HEADERS, timeout=10).json()
        f_tr = requests.get("https://www.okx.com/api/v5/market/history-trades", params={"instId":"BTC-USDT-SWAP","limit":1000}, headers=HEADERS, timeout=10).json()
        s_tr = requests.get("https://www.okx.com/api/v5/market/history-trades", params={"instId":"BTC-USDT","limit":1000}, headers=HEADERS, timeout=10).json()
        curr_c = float(kl['data'][0][4]); prev_c = float(kl['data'][1][4])
        curr_oi = float(oi['data'][0]['oi']); prev_oi = float(oi['data'][1]['oi'])
        now=int(time.time()*1000); cut=now-15*60*1000
        f_cvd=s_cvd=0
        for t in f_tr['data']:
            if int(t['ts'])<cut: continue
            f_cvd += float(t['sz']) if t['side']=='buy' else -float(t['sz'])
        for t in s_tr['data']:
            if int(t['ts'])<cut: continue
            s_cvd += float(t['sz']) if t['side']=='buy' else -float(t['sz'])
        return {"src":"OKX","price":curr_c,"prev_price":prev_c,"oi":curr_oi,"prev_oi":prev_oi,"f_cvd":f_cvd,"s_cvd":s_cvd}
    except Exception as e:
        print(f"OKX fail {e}")
        return None

def get_binance():
    try:
        kl = requests.get("https://fapi.binance.com/fapi/v1/klines", params={"symbol":"BTCUSDT","interval":"15m","limit":2}, timeout=10).json()
        oi = requests.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol":"BTCUSDT"}, timeout=10).json()
        # Binance OI history not easy, use current only
        curr_c = float(kl[1][4]); prev_c = float(kl[0][4])
        curr_oi = float(oi['openInterest']); prev_oi = curr_oi # approx
        # aggTrades for CVD proxy
        trades = requests.get("https://fapi.binance.com/fapi/v1/aggTrades", params={"symbol":"BTCUSDT","limit":1000}, timeout=10).json()
        now=int(time.time()); cut=now-15*60
        f_cvd=0
        for t in trades:
            if int(t['T']/1000)<cut: continue
            f_cvd += float(t['q']) if not t['m'] else -float(t['q'])
        return {"src":"Binance","price":curr_c,"prev_price":prev_c,"oi":curr_oi,"prev_oi":prev_oi,"f_cvd":f_cvd,"s_cvd":0}
    except Exception as e:
        print(f"Binance fail {e}")
        return None

def analyze():
    # Try all, aggregate like Coinglass
    sources=[]
    for fn in [get_bybit, get_okx, get_binance]:
        d=fn()
        if d: sources.append(d)
        time.sleep(0.5)

    if not sources:
        send_tg("⚠️ All APIs blocked - will retry in 15m")
        sys.exit(0)

    # Coinglass style aggregate
    price = sources[0]['price']; prev_price = sources[0]['prev_price']
    oi = sum(s['oi'] for s in sources)/len(sources)
    prev_oi = sum(s['prev_oi'] for s in sources)/len(sources)
    f_cvd = sum(s['f_cvd'] for s in sources)
    s_cvd = sum(s['s_cvd'] for s in sources) if any(s['s_cvd']!=0 for s in sources) else sources[0]['s_cvd']*2

    price_up = price > prev_price
    price_down = price < prev_price
    oi_up = oi > prev_oi
    oi_down = oi < prev_oi
    s_up = s_cvd > 0
    s_down = s_cvd < 0
    f_up = f_cvd > 0
    f_down = f_cvd < 0

    srcs = "+".join([s['src'] for s in sources])

    print(f"AGG {srcs} Price {price} prev {prev_price} OI {oi:.0f} prev {prev_oi:.0f} f{f_cvd:.2f} s{s_cvd:.2f}")

    # Logic as per your Spot Main theory
    msg = ""
    # A+ Long: Sab UP
    if price_up and oi_up and f_up and s_up:
        msg = f"🔥 *A+ LONG CONFIRM 15M ({srcs})* Coinglass Style\nPrice UP {price:.1f} ({price-prev_price:+.1f})\nOI UP {oi:.0f} (+{oi-prev_oi:.0f})\nFut CVD UP {f_cvd:+.2f} + Spot CVD UP {s_cvd:+.2f} - Spot Main Strong"
    # B+ Long: Price UP + Spot UP (Main) + Future Down bhi chalega + OI up/down chalega
    elif price_up and s_up:
        msg = f"🟢 *B+ LONG 15M ({srcs})* Spot Main\nPrice UP {price:.1f} + Spot CVD UP {s_cvd:+.2f} (Main)\nFut CVD {f_cvd:+.2f} {'UP' if f_up else 'DOWN but Spot absorbing'} + OI {'UP' if oi_up else 'DOWN'} {oi-prev_oi:+.0f}\nCoinglass: Fut {f_cvd:+.2f} / Spot {s_cvd:+.2f}"
    # A+ Short
    elif price_down and oi_up and f_down and s_down:
        msg = f"🔥 *A+ SHORT CONFIRM 15M ({srcs})*\nPrice DOWN {price:.1f} ({price-prev_price:+.1f})\nOI UP {oi:.0f} (+{oi-prev_oi:.0f})\nFut CVD DOWN {f_cvd:+.2f} + Spot CVD DOWN {s_cvd:+.2f}"
    # B+ Short
    elif price_down and s_down:
        msg = f"🔴 *B+ SHORT 15M ({srcs})* Spot Main\nPrice DOWN {price:.1f} + Spot CVD DOWN {s_cvd:+.2f} (Main)\nFut CVD {f_cvd:+.2f} + OI {'UP' if oi_up else 'DOWN'} {oi-prev_oi:+.0f}"
    # Long Liquidation: Sab DOWN
    elif price_down and oi_down and f_down and s_down and abs(f_cvd)>100:
        msg = f"💀 *LONG LIQUIDATION 15M ({srcs})*\nPrice DOWN {price:.1f} + OI DOWN {oi-prev_oi:+.0f} + Fut CVD {f_cvd:+.2f} + Spot {s_cvd:+.2f}\nLongs getting REKT - Short momentum"
    # Short Liquidation
    elif price_up and oi_down and f_up and s_up and f_cvd>100:
        msg = f"💀 *SHORT LIQUIDATION 15M ({srcs})*\nPrice UP {price:.1f} + OI DOWN {oi-prev_oi:+.0f} + Shorts REKT"
    else:
        msg = f"ℹ️ *No B+ 15M ({srcs})*\nPrice {'UP' if price_up else 'DOWN'}:{price:.1f} OI {'UP' if oi_up else 'DOWN'}({oi-prev_oi:+.0f}) Fut {f_cvd:+.2f} Spot {s_cvd:+.2f}\nWait for B+ - Spot Main: {s_cvd:+.2f}"

    send_tg(msg)

analyze()
        
