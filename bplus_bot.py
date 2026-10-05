import requests, time
import os

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SYMBOL = "BTCUSDT"

def bybit_get(url, params):
    for _ in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            data = r.json()
            if data.get('retCode') == 0:
                return data
        except:
            time.sleep(2)
    return None

def send_tg(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        requests.post(url, data=data, timeout=15)
    except Exception as e:
        print(e)

def get_real_cvd(category, symbol, minutes=15):
    url = "https://api.bybit.com/v5/market/recent-trade"
    data = bybit_get(url, {"category": category, "symbol": symbol, "limit": 1000})
    if not data:
        return 0,0,0,0
    trades = data['result']['list']
    now_ms = int(time.time()*1000)
    cutoff = now_ms - minutes*60*1000
    buy=sell=0.0
    for t in trades:
        if int(t['time']) < cutoff: continue
        sz=float(t['size'])
        if t['side']=='Buy': buy+=sz
        else: sell+=sz
    return buy,sell,buy-sell,len(trades)

def analyze():
    oi_data = bybit_get("https://api.bybit.com/v5/market/open-interest", {"category":"linear","symbol":SYMBOL,"intervalTime":"15min","limit":3})
    kline_data = bybit_get("https://api.bybit.com/v5/market/kline", {"category":"linear","symbol":SYMBOL,"interval":"15","limit":3})
    if not oi_data or not kline_data:
        print("Data fail")
        return
    oi_list=oi_data['result']['list']
    curr_oi=float(oi_list[0]['openInterest']); prev_oi=float(oi_list[1]['openInterest'])
    oi_up=curr_oi>prev_oi; oi_change=curr_oi-prev_oi
    kline_list=kline_data['result']['list']
    curr_close=float(kline_list[0][4]); prev_close=float(kline_list[1][4])
    price_up=curr_close>prev_close; price_down=curr_close<prev_close
    fut_buy,fut_sell,fut_cvd,_=get_real_cvd("linear",SYMBOL,15)
    spot_buy,spot_sell,spot_cvd,_=get_real_cvd("spot",SYMBOL,15)
    fut_up=fut_cvd>0; spot_up=spot_cvd>0
    print(f"Price {prev_close}->{curr_close} UP:{price_up}")
    print(f"OI {prev_oi}->{curr_oi} UP:{oi_up}")
    print(f"Fut CVD {fut_cvd} Spot CVD {spot_cvd}")

    if price_up and oi_up and fut_up and spot_up:
        msg=f"🟢 *B+ LONG CONFIRM 15M - CLOUD*\nPrice UP {curr_close} + OI UP {curr_oi:.0f} ({oi_change:+.0f})\nFut CVD {fut_cvd:+.3f} / Spot CVD {spot_cvd:+.3f} - *SPOT MAIN ✅*"
    elif price_down and oi_up and not fut_up and not spot_up:
        msg=f"🔴 *B+ SHORT CONFIRM 15M - CLOUD*\nPrice DOWN {curr_close} + OI UP {curr_oi:.0f}\nFut CVD {fut_cvd:+.3f} / Spot CVD {spot_cvd:+.3f} - *SPOT MAIN ✅*"
    elif price_up and oi_up and fut_up and not spot_up:
        msg=f"🟡 *Weak Long / TRAP 15M - CLOUD*\nFut UP {fut_cvd:+.3f} par Spot DOWN {spot_cvd:+.3f} - *Mat faso*"
    else:
        msg=f"ℹ️ *No B+ 15M - CLOUD*\nPrice UP:{price_up} OI UP:{oi_up} ({oi_change:+.0f})\nFut {fut_cvd:+.3f} Spot {spot_cvd:+.3f} - Wait for B+"
    send_tg(msg)

if __name__=="__main__":
    analyze()
      
