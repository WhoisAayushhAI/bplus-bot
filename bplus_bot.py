import os, requests
from datetime import datetime, timedelta, timezone

PROXY = (os.getenv("CLOUDFLARE_PROXY") or "https://aayush-proxy.aayushrathod7878.workers.dev").strip().rstrip("/")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def fetch(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    # Binance ke liye seedha proxy, baaki ke liye direct+proxy
    is_binance = "binance.com" in url or "fapi" in url

    if not is_binance:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code==200 and r.text.strip().startswith(('{','[')):
                return r.json()
        except: pass

    # Proxy se (Binance ke liye yehi chalega)
    try:
        r = requests.get(f"{PROXY}/?url={url}", headers=headers, timeout=20)
        if r.status_code==200 and r.text.strip().startswith(('{','[')):
            return r.json()
        else:
            print(f"Proxy returned non-json: {r.text[:100]}")
    except Exception as e:
        print(f"Fetch fail {url}: {e}")
    return None

def safe_cvd(klines):
    if not klines or not isinstance(klines, list) or len(klines)==0:
        return 0,0
    try:
        last = klines[-1]
        vol = float(last[5])
        taker = float(last[10]) if len(last)>10 else vol/2
        price = float(last[4])
        delta_k = (taker*2 - vol) * price / 1000.0
        prev_delta_k = 0
        if len(klines)>=2:
            prev = klines[-2]
            vol2 = float(prev[5]); taker2 = float(prev[10]) if len(prev)>10 else vol2/2
            prev_delta_k = (taker2*2 - vol2) * float(prev[4]) / 1000.0
        return prev_delta_k, delta_k
    except Exception as e:
        print(f"CVD calc error: {e}")
        return 0,0

def get_tf(interval):
    # interval: 15m, 1h, 4h
    f_data = fetch(f"https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval={interval}&limit=2")
    s_data = fetch(f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={interval}&limit=2")

    f_o, f_c = safe_cvd(f_data)
    s_o, s_c = safe_cvd(s_data)

    # OI
    oi_data = fetch(f"https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period={interval}&limit=2")
    oi_o = oi_c = 0
    if oi_data and isinstance(oi_data, list) and len(oi_data)>0:
        try:
            oi_c = float(oi_data[-1]['sumOpenInterest'])/1000
            if len(oi_data)>=2:
                oi_o = float(oi_data[-2]['sumOpenInterest'])/1000
        except: pass
    else:
        # fallback current OI
        cur = fetch("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT")
        if cur and 'openInterest' in cur:
            oi_c = float(cur['openInterest'])/1000
            oi_o = oi_c

    # Premium
    prem = fetch("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
    premium = float(prem['lastFundingRate'])*100 if prem and 'lastFundingRate' in prem else 0

    return f_o, f_c, s_o, s_c, oi_o, oi_c, premium

def send(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"TG fail: {e}")

f4_o,f4_c,s4_o,s4_c,oi4_o,oi4_c,prem4 = get_tf("4h")
f1_o,f1_c,s1_o,s1_c,oi1_o,oi1_c,prem1 = get_tf("1h")
f15_o,f15_c,s15_o,s15_c,oi15_o,oi15_c,prem15 = get_tf("15m")

# Funding
fund_cur_data = fetch("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
fund_cur = float(fund_cur_data['lastFundingRate'])*100 if fund_cur_data else 0

fund_hist = fetch("https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=8")
fund_1d = 0
if fund_hist and isinstance(fund_hist, list):
    try:
        vals = [float(x['fundingRate'])*100 for x in fund_hist[:3]]
        fund_1d = sum(vals)/len(vals) if vals else 0
    except: pass

ist = timezone(timedelta(hours=5,minutes=30))
now_ist = datetime.now(ist).strftime("%d-%m %I:%M:%S %p IST")

msg = f"""📊 *BPLUS - Coinglass Style*

*4H*
Future: {f4_o:.2f}K to {f4_c:.2f}K
Spot: {s4_o:.0f} to {s4_c:.0f}
OI: {oi4_o:.2f}K to {oi4_c:.2f}K
Premium: {prem4:.3f}%

*1H*
Future: {f1_o:.2f}K to {f1_c:.2f}K
Spot: {s1_o:.0f} to {s1_c:.0f}
OI: {oi1_o:.2f}K to {oi1_c:.2f}K
Premium: {prem1:.3f}%

*15M*
Future: {f15_o:.2f}K to {f15_c:.2f}K
Spot: {s15_o:.0f} to {s15_c:.0f}
OI: {oi15_o:.2f}K to {oi15_c:.2f}K
Premium: {prem15:.3f}%

*Funding*
Current: {fund_cur:.4f}%
1D Avg: {fund_1d:.4f}%

*Time:* {now_ist}
"""

print(msg)
send(msg)
