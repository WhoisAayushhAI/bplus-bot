"""
US High-Impact News Alert -> Telegram. Sirf info, trade nahi.

Data: Forex Factory ka free weekly feed (nfs.faireconomy.media).
Is feed me Time, Forecast, Previous milta hai. ACTUAL number nahi milta.

Do alert aate hain:
  1) Event se ~60 minute pehle: "Heads-up" + kya hai + kaise padhein
  2) Event ke time par (30 min tak): "Abhi aa raha hai" + kaise padhein

Keys GitHub Secrets me: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Test: workflow me test=1, ya local me DRY_RUN=1 (sirf print) / TEST=1 (agla event bhejo)
"""
import os
import sys
import json
import requests
from datetime import datetime, timezone, timedelta

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DRY = os.environ.get("DRY_RUN") == "1"
TEST = os.environ.get("TEST") == "1"

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
STATE = "news_sent.json"
PRE_MIN = 60        # event se kitne minute pehle heads-up
NOW_WINDOW = 30     # event ke baad kitne minute tak "abhi aaya" alert
IST = timezone(timedelta(hours=5, minutes=30))

# (keywords, naam, ye kya hai, kaise padhein). Upar wale pehle match hote hain.
EXPLAIN = [
    (("unemployment rate",), "US Unemployment Rate (berozgari dar)",
     "Kitne log berozgar hain.",
     "ZYADA = economy kamzor = rate cut ki umeed = USD weak, aam taur pe Gold/BTC ko support. "
     "KAM = economy majboot = USD strong, Gold/BTC pe dabav ho sakta hai."),
    (("non-farm", "nfp", "payroll"), "US NFP (nayi naukriyan)",
     "Pichhle mahine kitni nayi naukriyan bani.",
     "ZYADA = economy majboot = USD strong = Gold/BTC pe dabav ho sakta hai. "
     "KAM = economy kamzor = rate cut ki umeed = Gold/BTC ko support. "
     "Par bahut hi kamzor aaya to darr (risk-off) se BTC bhi gir sakta hai."),
    (("core cpi", "cpi"), "US CPI (mehengayi)",
     "Mehengayi (inflation) ka number. Fed ke rate faisle ka sabse bada driver.",
     "ZYADA = mehengayi zyada = rate cut ki umeed kam = USD strong = Gold/BTC pe dabav ho sakta hai. "
     "KAM = ulta, Gold/BTC ko support."),
    (("core ppi", "ppi"), "US PPI (producer ki mehengayi)",
     "Factory/producer level ki mehengayi. CPI ka aage ka sanket mana jata hai.",
     "ZYADA = mehengayi ka dabav = USD strong = Gold/BTC pe dabav ho sakta hai. KAM = ulta."),
    (("pce",), "US PCE (Fed ka pasandida inflation number)",
     "Fed isi inflation number ko sabse zyada dekhta hai.",
     "ZYADA = USD strong = Gold/BTC pe dabav ho sakta hai. KAM = Gold/BTC ko support."),
    (("fomc", "federal funds", "fed chair", "powell"), "FOMC / Fed (byaaj dar / Fed Chair ka bayan)",
     "Fed byaaj dar (interest rate) ka faisla, ya Fed Chair ka bhashan/bayan.",
     "Tone SAKHT (hawkish, rate kam nahi karenge) = USD strong = Gold/BTC pe dabav ho sakta hai. "
     "Tone NARM (dovish, rate cut ke sanket) = Gold/BTC ko support. "
     "Market ki ummeed se alag nikla to bada jhatka aata hai. "
     "Tumhara rule: FOMC me sirf observe, trade nahi."),
    (("gdp",), "US GDP (economy ki growth)",
     "Economy kitni tezi se badh rahi hai.",
     "ZYADA = economy majboot = USD strong = Gold/BTC pe dabav ho sakta hai. "
     "KAM = kamzor economy, rate cut ki umeed = Gold/BTC ko support."),
    (("retail sales",), "US Retail Sales (logon ka kharch)",
     "Log dukanon me kitna kharch kar rahe hain.",
     "ZYADA = majboot economy = USD strong = Gold/BTC pe dabav ho sakta hai. KAM = ulta."),
    (("ism manufacturing", "ism services", "ism non-manufacturing"), "US ISM PMI (factory/services ki activity)",
     "50 se upar matlab growth, neeche matlab sikudna.",
     "Forecast se ZYADA = USD strong = Gold/BTC pe dabav ho sakta hai. KAM = Gold/BTC ko support."),
]
DEFAULT = ("High impact US news", "Ye US ki badi news hai.",
           "Forecast se bahut alag aaya to price me bada jhatka aata hai. Dollar ki taraf dekho: "
           "USD upar = Gold/BTC pe dabav, USD neeche = support.")


def explain(title):
    t = title.lower()
    for kws, name, what, read in EXPLAIN:
        if any(k in t for k in kws):
            return name, what, read
    return (DEFAULT[0] + f" ({title})", DEFAULT[1], DEFAULT[2])


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_state(sent):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(sorted(sent)[-300:], f)


def fetch_events():
    r = requests.get(FEED, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"feed status {r.status_code}")
    out = []
    for e in r.json():
        if e.get("country") != "USD" or e.get("impact") != "High":
            continue
        try:
            when = datetime.fromisoformat(e["date"])
        except Exception:
            continue
        out.append({"title": e.get("title", "").strip(), "when": when,
                    "date": e["date"], "forecast": e.get("forecast") or "NA",
                    "previous": e.get("previous") or "NA"})
    return sorted(out, key=lambda x: x["when"])


def pre_text(ev, mins):
    name, what, read = explain(ev["title"])
    return (f"⏰ {mins} minute me: {name}\n"
            f"Time: {ev['when'].astimezone(IST):%d-%b %I:%M %p} IST\n"
            f"Forecast: {ev['forecast']} | Previous: {ev['previous']}\n\n"
            f"Ye kya hai: {what}\n\n"
            f"Kaise padhein: {read}\n\n"
            "Dhyan: number aate hi pehle 1-2 minute price dono taraf jhatka deta hai "
            "aur spread badhta hai. Actual number TradingView ya Forex Factory calendar me dekho.")


def now_text(ev):
    name, _, read = explain(ev["title"])
    return (f"🔔 Abhi aa raha hai / aaya: {name}\n"
            f"Forecast: {ev['forecast']} | Previous: {ev['previous']}\n"
            "Actual number yahan dekho: https://www.tradingview.com/economic-calendar/\n\n"
            f"Kaise padhein: {read}\n\n"
            "Ye aam tendency hai, kabhi ulta bhi hota hai.")


def build_messages(events, now, sent):
    msgs = []
    for ev in events:
        mins = (ev["when"] - now).total_seconds() / 60
        k_pre = f"{ev['title']}|{ev['date']}|pre"
        k_now = f"{ev['title']}|{ev['date']}|now"
        if 0 < mins <= PRE_MIN and k_pre not in sent:
            msgs.append((k_pre, pre_text(ev, int(round(mins)))))
        if -NOW_WINDOW <= mins <= 0 and k_now not in sent:
            msgs.append((k_now, now_text(ev)))
    return msgs


def send(text):
    if DRY:
        print(text, "\n[DRY_RUN] bheja nahi\n")
        return
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id": TG_CHAT, "text": text}, timeout=30)
    if not r.ok:
        sys.exit(f"Telegram error {r.status_code}: {r.text[:200]}")


def main():
    if not DRY and not (TG_TOKEN and TG_CHAT):
        sys.exit("Keys missing")
    now = datetime.now(timezone.utc)
    try:
        events = fetch_events()
    except Exception as e:  # noqa
        print(f"Feed error: {e}")      # agli run me phir try hoga
        if TEST:
            send(f"TEST: Forex Factory feed se data nahi aaya ({str(e)[:100]})")
        return

    up = [x for x in events if x["when"] > now]
    print(f"Is hafte ki US High impact news: {len(events)} | aage aane wali: {len(up)}")
    if up:
        print(f"Agli: {up[0]['title']} | {up[0]['when'].astimezone(IST):%d-%b %I:%M %p} IST")

    if TEST:
        up = [e for e in events if e["when"] > now]
        ev = up[0] if up else (events[-1] if events else None)
        if not ev:
            send("TEST: is hafte koi High impact US news nahi mili")
            return
        mins = max(1, int((ev["when"] - now).total_seconds() / 60))
        send("🧪 TEST MESSAGE\n\n" + pre_text(ev, mins))
        return

    sent = load_state()
    todo = build_messages(events, now, sent)
    if not todo:
        print("Abhi koi alert due nahi (heads-up 60 min pehle, 'abhi aaya' event ke 30 min tak).")
    for key, text in todo:
        send(text)
        sent.add(key)
    if not DRY:
        save_state(sent)


if __name__ == "__main__":
    main()
