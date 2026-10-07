import os, requests
from datetime import datetime, timedelta, timezone

PROXY = (os.getenv("CLOUDFLARE_PROXY") or "https://aayush-proxy.aayushrathod7878.workers.dev").strip().rstrip("/")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def fetch(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    # direct try
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code==200:
            return r.json()
    except: pass
    # proxy try
    try:
        r = requests.get(f"{PROXY}/?url={url}", headers=headers, timeout=15)
        if r.status_code==200:
            return r.json()
    except Exception as e:
        print(f"Fetch fail {url}: {e}")
    return None

def get_cvd_and_oi(interval, limit=2):
    # interval: 15m, 1h, 4h for Binance
    # Futures CVD
    f_url = f"https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval={interval}&limit={limit}"
    f_data = fetch(f_url)
    f_cvd_open = f_cvd_close = 0
    if f_data and len(f_data)>=1:
        # Binance kline: [0]openTime, [5]close, [7]quoteVol, [10]takerBuyBaseVol
        # CVD = takerBuy - takerSell = 2*takerBuy - totalVol
        last = f_data[-1]
        # last candle delta
        total = float(last[5]) if len(last)>5 else 0 # close? actually volume
        # correct: index 5 is volume, index 9 is taker buy quote
        vol = float(last[5])
        taker_buy = float(last[10]) if len(last)>10 else vol/2
        delta = (taker_buy*2 - vol) # in BTC
        f_cvd_close = delta*float(last[4]) / 1000 # convert to K USD approx
        if len(f_data)>=2:
            prev = f_data[-2]
            vol2 = float(prev[5]); taker2 = float(prev[10]) if len(prev)>10 else vol2/2
            f_cvd_open = (taker2*2 - vol2)*float(prev[4])/1000

    # Spot CVD
    s_url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit={limit}"
    s_data = fetch(s_url)
    s_cvd_open = s_cvd_close = 0
    if s_data and len(s_data)>=1:
        last = s_data[-1]
        vol = float(last[5]); taker = float(last[10]) if len(last)>10 else vol/2
        s_cvd_close = (taker*2 - vol)*float(last[4])/1000
        if len(s_data)>=2:
            prev = s_data[-2]
            vol2 = float(prev[5]); taker2 = float(prev[10]) if len(prev)>10 else vol2/2
            s_cvd_open = (taker2*2 - vol2)*float(prev[4])/1000

    # OI from Binance
    oi_url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT"
    # history OI for interval not free, so use current + approx
    oi_data = fetch(f"https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period={interval}&limit=2")
    oi_open = oi_close = 0
    if oi_data and len(oi_data)>=1:
        oi_close = float(oi_data[-1]['sumOpenInterest'])/1000
        if len(oi_data)>=2:
            oi_open = float(oi_data[-2]['sumOpenInterest'])/1000
    else:
        oi_d = fetch("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT")
        if oi_d:
            oi_close = float(oi_d['openInterest'])/1000
            oi_open = oi_close

    # Premium
    prem_url = "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"
    prem_d = fetch(prem_url)
    premium = float(prem_d['lastFundingRate'])*100 if prem_d and 'lastFundingRate' in prem_d else 0

    return {
        "f_open": f_cvd_open, "f_close": f_cvd_close,
        "s_open": s_cvd_open, "s_close": s_cvd_close,
        "oi_open": oi_open, "oi_close": oi_close,
        "premium": premium
    }

def send(msg):
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

d4h = get_cvd_and_oi("4h")
d1h = get_cvd_and_oi("1h")
d15m = get_cvd_and_oi("15m")

# Funding
fund = fetch("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
fund_cur = float(fund['lastFundingRate'])*100 if fund else 0

fund_hist = fetch("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=8")
fund_1d = 0
if fund_hist:
    vals = [float(x['fundingRate'])*100 for x in fund_hist[:3]]
    fund_1d = sum(vals)/len(vals) if vals else 0

ist = timezone(timedelta(hours=5,minutes=30))
now_ist = datetime.now(ist).strftime("%d-%m %I:%M:%S %p IST")

msg = f"""📊 *BPLUS - Coinglass Style*

*4H*
Future: {d4h['f_open']:.2f}K to {d4h['f_close']:.2f}K
Spot: {d4h['s_open']:.0f} to {d4h['s_close']:.0f}
OI: {d4h['oi_open']:.2f}K to {d4h['oi_close']:.2f}K
Premium: {d4h['premium']:.3f}%

*1H*
Future: {d1h['f_open']:.2f}K to {d1h['f_close']:.2f}K
Spot: {d1h['s_open']:.0f} to {d1h['s_close']:.0f}
OI: {d1h['oi_open']:.2f}K to {d1h['oi_close']:.2f}K
Premium: {d1h['premium']:.3f}%

*15M*
Future: {d15m['f_open']:.2f}K to {d15m['f_close']:.2f}K
Spot: {d15m['s_open']:.0f} to {d15m['s_close']:.0f}
OI: {d15m['oi_open']:.2f}K to {d15m['oi_close']:.2f}K
Premium: {d15m['premium']:.3f}%

*Funding*
Current: {fund_cur:.4f}%
1D Avg: {fund_1d:.4f}%

*Time:* {now_ist}
"""

print(msg)
send(msg)
