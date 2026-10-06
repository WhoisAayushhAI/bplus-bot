import os, sys, time, requests

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN","").strip().lstrip("bot")
CHAT = os.environ.get("TELEGRAM_CHAT_ID","").strip()
H = {"User-Agent":"Mozilla/5.0"}

def send(msg):
    r=requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id":CHAT,"text":msg,"parse_mode":"Markdown"}, timeout=15)
    print(r.text[:300]); r.raise_for_status()

def okx(url, p):
    for i in range(3):
        try:
            r=requests.get(url, params=p, headers=H, timeout=12)
            j=r.json()
            if j.get('code')=='0':
                return j
            print(f"OKX err {j}")
        except Exception as e:
            print(f"OKX {e} try {i}")
            time.sleep(1+i)
    return None

def analyze():
    kl = okx("https://www.okx.com/api/v5/market/candles", {"instId":"BTC-USDT-SWAP","bar":"15m","limit":3})
    # Use OI history for prev OI - more reliable
    oi_h = okx("https://www.okx.com/api/v5/public/open-interest-history", {"instId":"BTC-USDT-SWAP","period":"5m","limit":4})
    # Fallback to current OI if history fails
    if not oi_h:
        oi_h = okx("https://www.okx.com/api/v5/public/open-interest", {"instId":"BTC-USDT-SWAP"})
        # make it compatible
        if oi_h:
            oi_h['data'] = [{"oi":oi_h['data'][0]['oi']},{"oi":oi_h['data'][0]['oi']}]
    
    f_tr = okx("https://www.okx.com/api/v5/market/history-trades", {"instId":"BTC-USDT-SWAP","limit":1000})
    s_tr = okx("https://www.okx.com/api/v5/market/history-trades", {"instId":"BTC-USDT","limit":1000})

    if not kl or not oi_h or not f_tr or not s_tr:
        print("OKX fail, will retry 15m")
        send("⚠️ OKX temp fail - will retry in 15m (setup OK)")
        sys.exit(0)

    curr_c = float(kl['data'][0][4]); prev_c = float(kl['data'][1][4])
    # oi_h may be list of dicts
    try:
        curr_oi = float(oi_h['data'][0]['oi']); prev_oi = float(oi_h['data'][1]['oi'])
    except:
        curr_oi = float(oi_h['data'][0]['oi']); prev_oi = curr_oi

    now=int(time.time()*1000); cut=now-15*60*1000
    f_cvd=s_cvd=0.0
    for t in f_tr['data']:
        if int(t['ts'])<cut: continue
        f_cvd += float(t['sz']) if t['side']=='buy' else -float(t['sz'])
    for t in s_tr['data']:
        if int(t['ts'])<cut: continue
        s_cvd += float(t['sz']) if t['side']=='buy' else -float(t['sz'])

    price_up = curr_c > prev_c; price_down = curr_c < prev_c
    oi_up = curr_oi > prev_oi; oi_down = curr_oi < prev_oi
    oi_chg = curr_oi - prev_oi
    s_up = s_cvd > 0; s_down = s_cvd < 0
    f_up = f_cvd > 0; f_down = f_cvd < 0

    print(f"Price {curr_c} {prev_c} OI {curr_oi} {prev_oi} f {f_cvd} s {s_cvd}")

    # Your Coinglass logic - Spot Main
    # A+ Long: Price UP + OI UP + Fut UP + Spot UP
    if price_up and oi_up and f_up and s_up:
        msg = f"🔥 *A+ LONG CONFIRM 15M (OKX)*\nPrice UP {curr_c:.1f} (+{curr_c-prev_c:.1f})\nOI UP {curr_oi:.0f} (+{oi_chg:.0f})\nFut CVD UP {f_cvd:+.2f} + Spot CVD UP {s_cvd:+.2f} - Spot Main Strong"
    # B+ Long: Price UP + Spot UP main (Future DOWN bhi chalega, OI up/down chalega)
    elif price_up and s_up:
        msg = f"🟢 *B+ LONG 15M (OKX)* Spot Main\nPrice UP {curr_c:.1f} + Spot CVD UP {s_cvd:+.2f} (Main)\nFut CVD {f_cvd:+.2f} {'UP' if f_up else 'DOWN but Spot absorbing'} + OI {'UP' if oi_up else 'DOWN'} {oi_chg:+.0f}\nWait for A+"
    # A+ Short
    elif price_down and oi_up and f_down and s_down:
        msg = f"🔥 *A+ SHORT CONFIRM 15M (OKX)*\nPrice DOWN {curr_c:.1f} ({curr_c-prev_c:+.1f})\nOI UP {curr_oi:.0f} (+{oi_chg:.0f})\nFut DOWN {f_cvd:+.2f} + Spot DOWN {s_cvd:+.2f}"
    # B+ Short: Price DOWN + Spot DOWN main
    elif price_down and s_down:
        msg = f"🔴 *B+ SHORT 15M (OKX)* Spot Main\nPrice DOWN {curr_c:.1f} + Spot CVD DOWN {s_cvd:+.2f} (Main)\nFut CVD {f_cvd:+.2f} + OI {oi_chg:+.0f}"
    # Long Liquidation: Sab DOWN + OI DOWN bada
    elif price_down and oi_down and f_down and s_down:
        msg = f"💀 *LONG LIQUIDATION 15M (OKX)*\nPrice DOWN {curr_c:.1f} + OI DOWN {oi_chg:+.0f} + Fut {f_cvd:+.2f} + Spot {s_cvd:+.2f}\nLongs REKT - Short momentum"
    # Short Liquidation
    elif price_up and oi_down and f_up and s_up:
        msg = f"💀 *SHORT LIQUIDATION 15M (OKX)*\nPrice UP {curr_c:.1f} + OI DOWN {oi_chg:+.0f} + Shorts REKT"
    else:
        msg = f"ℹ️ *No B+ 15M (OKX)*\nPrice {'UP' if price_up else 'DOWN'}:{curr_c:.1f} OI {'UP' if oi_up else 'DOWN'}({oi_chg:+.0f}) Fut {f_cvd:+.2f} Spot {s_cvd:+.2f}\nWait for B+ - Spot Main: {s_cvd:+.2f}"

    send(msg)

analyze()
        
