import os, requests
from datetime import datetime, timedelta, timezone

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def fetch(url):
    try:
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
        if r.status_code==200:
            return r.json()
    except Exception as e:
        print(f"Fail {url}: {e}")
    return None

def get_spot_cvd(interval):
    # interval: 15m, 1h, 4h -> Binance Vision (block nahi karta)
    url = f"https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit=2"
    data = fetch(url)
    if not data or len(data)<1:
        return 0,0
    try:
        last = data[-1]
        vol = float(last[5]); taker = float(last[10]); price = float(last[4])
        cur = (taker*2 - vol) * price / 1000
        prev = 0
        if len(data)>=2:
            p = data[-2]
            vol2 = float(p[5]); taker2 = float(p[10]); price2 = float(p[4])
            prev = (taker2*2 - vol2) * price2 / 1000
        return prev, cur
    except:
        return 0,0

def get_fut_cvd(interval_bybit):
    # Bybit: 15,60,240
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval={interval_bybit}&limit=2"
    data = fetch(url)
    if not data or 'result' not in data or not data['result'].get('list'):
        return 0,0,0,0
    try:
        lst = data['result']['list']
        # lst[0]=latest, lst[1]=prev, format [start,open,high,low,close,volume,turnover]
        # Bybit me taker volume direct nahi, volume se CVD approx: close-open sign * volume
        cur_price = float(lst[0][4]); prev_price = float(lst[0][1])
        cur_vol = float(lst[0][5])
        delta_cur = (cur_price - prev_price) * cur_vol / 1000 # K USD
        prev_delta = 0
        if len(lst)>=2:
            prev_p = float(lst[1][4]); prev_o = float(lst[1][1]); prev_v = float(lst[1][5])
            prev_delta = (prev_p - prev_o) * prev_v / 1000
        # price
        price = cur_price
        return prev_delta, delta_cur, price, price
    except Exception as e:
        print(f"Bybit CVD err {e}")
        return 0,0,0,0

def get_oi_funding():
    oi = fetch("https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT")
    oi_val = 0
    if oi and oi.get('result') and oi['result'].get('list'):
        try:
            oi_val = float(oi['result']['list'][0]['openInterest'])/1000
        except: pass

    fund = fetch("https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=3")
    cur = avg = 0
    if fund and fund.get('result') and fund['result'].get('list'):
        try:
            lst = fund['result']['list']
            cur = float(lst[0]['fundingRate'])*100
            vals = [float(x['fundingRate'])*100 for x in lst[:3]]
            avg = sum(vals)/len(vals) if vals else cur
        except: pass
    return oi_val, cur, avg

def send(msg):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id":CHAT_ID,"text":msg,"parse_mode":"Markdown"})

s4_o,s4_c = get_spot_cvd("4h")
s1_o,s1_c = get_spot_cvd("1h")
s15_o,s15_c = get_spot_cvd("15m")

f4_o,f4_c,price4,_ = get_fut_cvd("240")
f1_o,f1_c,price1,_ = get_fut_cvd("60")
f15_o,f15_c,price15,_ = get_fut_cvd("15")

oi, fund_cur, fund_1d = get_oi_funding()
price = price15 if price15!=0 else price1 if price1!=0 else 0

ist = timezone(timedelta(hours=5,minutes=30))
now_ist = datetime.now(ist).strftime("%d-%m %I:%M:%S %p IST")

msg = f"""📊 *BPLUS - Coinglass Style*

*Price:* {price:.1f}

*4H*
Future: {f4_o:.2f}K to {f4_c:.2f}K
Spot: {s4_o:.2f}K to {s4_c:.2f}K
OI: {oi:.2f}K
Premium: {fund_cur:.4f}%

*1H*
Future: {f1_o:.2f}K to {f1_c:.2f}K
Spot: {s1_o:.2f}K to {s1_c:.2f}K
OI: {oi:.2f}K

*15M*
Future: {f15_o:.2f}K to {f15_c:.2f}K
Spot: {s15_o:.2f}K to {s15_c:.2f}K
OI: {oi:.2f}K

*Funding*
Current: {fund_cur:.4f}%
1D Avg: {fund_1d:.4f}%

*Time:* {now_ist}
"""
print(msg)
send(msg)
