#!/usr/bin/env python3
"""
ZigZag PA Alert -> Telegram
Port dari Pine Script "[STRATEGY][RS]ZigZag PA Strategy V4.1".
Dijalankan terjadwal oleh GitHub Actions (tanpa laptop).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state.json")

# ---------------- Konfigurasi (bisa diubah lewat env / GitHub Variables) ----------------
SYMBOLS = [s.strip() for s in os.getenv("SYMBOLS", "GC=F").split(",") if s.strip()]
INTERVAL = os.getenv("INTERVAL", "60m")      # timeframe ZigZag (Pine: tf = 60)
PERIOD = os.getenv("PERIOD", "60d")          # panjang history yang ditarik
USE_HA = os.getenv("USE_HA", "false").lower() == "true"
EW = float(os.getenv("EW_RATE", "0.236"))    # Fib rate Entry Window
TP = float(os.getenv("TP_RATE", "0.618"))    # Fib rate TP
SL = float(os.getenv("SL_RATE", "-0.236"))   # Fib rate SL
TZ_HOURS = float(os.getenv("TZ_OFFSET", "7"))  # WIB
TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

BAR_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1h": 60, "90m": 90, "1d": 1440}

# urutan rasio: (XAB, ABC, BCD, XAD); None = tanpa batas
PATTERNS = {
    "ABCD": (None, (0.382, 0.886), (1.13, 2.618), None),
    "Bat": ((0.382, 0.5), (0.382, 0.886), (1.618, 2.618), (0, 0.618)),
    "Anti Bat": ((0.5, 0.886), (1.0, 2.618), (1.618, 2.618), (0.886, 1.0)),
    "Alt Bat": ((0, 0.382), (0.382, 0.886), (2.0, 3.618), (0, 1.13)),
    "Butterfly": ((0, 0.786), (0.382, 0.886), (1.618, 2.618), (1.27, 1.618)),
    "Anti Butterfly": ((0.236, 0.886), (1.13, 2.618), (1.0, 1.382), (0.5, 0.886)),
    "Gartley": ((0.5, 0.618), (0.382, 0.886), (1.13, 2.618), (0.75, 0.875)),
    "Anti Gartley": ((0.5, 0.886), (1.0, 2.618), (1.5, 5.0), (1.0, 5.0)),
    "Crab": ((0.5, 0.875), (0.382, 0.886), (2.0, 5.0), (1.382, 5.0)),
    "Anti Crab": ((0.25, 0.5), (1.13, 2.618), (1.618, 2.618), (0.5, 0.75)),
    "Shark": ((0.5, 0.875), (1.13, 1.618), (1.27, 2.24), (0.886, 1.13)),
    "Anti Shark": ((0.382, 0.875), (0.5, 1.0), (1.25, 2.618), (0.5, 1.25)),
    "5-O": ((1.13, 1.618), (1.618, 2.24), (0.5, 0.625), (0, 0.236)),
    "Wolf Wave": ((1.27, 1.618), (0, 5), (1.27, 1.618), (0, 5)),
    "Head and Shoulders": ((2.0, 10), (0.9, 1.1), (0.236, 0.88), (0.9, 1.1)),
    "Contracting Triangle": ((0.382, 0.618), (0.382, 0.618), (0.382, 0.618), (0.236, 0.764)),
    "Expanding Triangle": ((1.236, 1.618), (1.0, 1.618), (1.236, 2.0), (2.0, 2.236)),
}


# ---------------- Data ----------------
def fetch_bars(symbol, now=None):
    """Ambil candle tertutup (urut lama -> baru)."""
    import yfinance as yf

    now = now or datetime.now(timezone.utc)
    df = yf.Ticker(symbol).history(period=PERIOD, interval=INTERVAL, auto_adjust=False)
    bars = []
    for ts, row in df.iterrows():
        if any(v != v for v in (row["Open"], row["High"], row["Low"], row["Close"])):
            continue
        t = ts.to_pydatetime().astimezone(timezone.utc)
        bars.append({"t": t, "o": float(row["Open"]), "h": float(row["High"]),
                     "l": float(row["Low"]), "c": float(row["Close"])})
    # buang bar terakhir kalau masih berjalan (belum close)
    minutes = BAR_MINUTES.get(INTERVAL, 60)
    if bars and bars[-1]["t"] + timedelta(minutes=minutes) > now:
        bars.pop()
    return bars


def to_heikin_ashi(bars):
    out, pho, phc = [], None, None
    for b in bars:
        hc = (b["o"] + b["h"] + b["l"] + b["c"]) / 4.0
        ho = (b["o"] + b["c"]) / 2.0 if pho is None else (pho + phc) / 2.0
        out.append({"t": b["t"], "o": ho, "c": hc,
                    "h": max(b["h"], ho, hc), "l": min(b["l"], ho, hc)})
        pho, phc = ho, hc
    return out


# ---------------- ZigZag ----------------
def build_pivots(bars):
    """Replikasi fungsi zigzag() Pine. Return 5 pivot terakhir [X, A, B, C, D]."""
    piv, dir_prev = [], 0
    for i in range(1, len(bars)):
        p, b = bars[i - 1], bars[i]
        p_up, p_dn = p["c"] >= p["o"], p["c"] <= p["o"]
        up, dn = b["c"] >= b["o"], b["c"] <= b["o"]
        direction = -1 if (p_up and dn) else (1 if (p_dn and up) else dir_prev)
        pv = None
        if p_up and dn and dir_prev != -1:
            pv = (b["h"], b["t"]) if b["h"] >= p["h"] else (p["h"], p["t"])
        elif p_dn and up and dir_prev != 1:
            pv = (b["l"], b["t"]) if b["l"] <= p["l"] else (p["l"], p["t"])
        dir_prev = direction
        if pv:
            piv.append({"p": pv[0], "t": pv[1], "sig": b["t"]})
    return piv[-5:]


def ratios(piv):
    x, a, b, c, d = (v["p"] for v in piv)
    if abs(x - a) == 0 or abs(a - b) == 0 or abs(b - c) == 0:
        return None
    return (abs(b - a) / abs(x - a),   # XAB
            abs(b - c) / abs(a - b),   # ABC
            abs(c - d) / abs(b - c),   # BCD
            abs(a - d) / abs(x - a))   # XAD


def in_range(v, r):
    return r is None or r[0] <= v <= r[1]


def match_patterns(rt):
    return [name for name, rng in PATTERNS.items()
            if all(in_range(v, r) for v, r in zip(rt, rng))]


def lvl(piv, rate):
    c, d = piv[3]["p"], piv[4]["p"]
    rg = abs(d - c)
    return d - rg * rate if d > c else d + rg * rate


# ---------------- Sinyal ----------------
def check_signal(bars):
    """Return dict sinyal atau None."""
    if USE_HA:
        bars = to_heikin_ashi(bars)
    if len(bars) < 10:
        return None
    piv = build_pivots(bars)
    if len(piv) < 5:
        return None
    rt = ratios(piv)
    if rt is None:
        return None
    names = match_patterns(rt)
    if not names:
        return None

    close = bars[-1]["c"]
    c, d = piv[3]["p"], piv[4]["p"]
    ew, tp, sl = lvl(piv, EW), lvl(piv, TP), lvl(piv, SL)

    if d < c:       # pola bullish -> BUY
        side = "BUY"
        ok = close <= ew and sl < close < tp
    elif d > c:     # pola bearish -> SELL
        side = "SELL"
        ok = close >= ew and tp < close < sl
    else:
        return None
    if not ok:
        return None
    return {"side": side, "patterns": names, "close": close, "tp": tp, "sl": sl,
            "ew": ew, "pivots": piv, "bar_time": bars[-1]["t"]}


# ---------------- Telegram & state ----------------
def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT:
        print("[!] TELEGRAM_TOKEN / TELEGRAM_CHAT_ID belum di-set. Pesan:\n" + text)
        return False
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      data={"chat_id": TG_CHAT, "text": text}, timeout=20)
    if not r.ok:
        print("[!] Telegram error:", r.status_code, r.text)
    return r.ok


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def fmt_time(t):
    return t.astimezone(timezone(timedelta(hours=TZ_HOURS))).strftime("%d %b %H:%M")


def format_message(sym, s):
    icon = "🟢" if s["side"] == "BUY" else "🔴"
    labels = ["X", "A", "B", "C", "D"]
    pv = " | ".join(f"{l} {v['p']:.2f}" for l, v in zip(labels, s["pivots"]))
    return (f"{icon} {s['side']} {sym} (TF {INTERVAL})\n"
            f"Pola: {', '.join(s['patterns'])}\n"
            f"Harga (close bar): {s['close']:.2f}\n"
            f"TP: {s['tp']:.2f}\n"
            f"SL: {s['sl']:.2f}\n"
            f"Pivot: {pv}\n"
            f"Bar: {fmt_time(s['bar_time'])} WIB")


def main():
    if "--test" in sys.argv:
        ok = send_telegram("✅ Tes ZigZag PA Alert: koneksi Telegram berhasil.")
        print("Test terkirim" if ok else "Test gagal")
        return

    state = load_state()
    for sym in SYMBOLS:
        try:
            bars = fetch_bars(sym)
            sig = check_signal(bars)
        except Exception as e:  # jangan hentikan simbol lain
            print(f"[!] {sym}: {e}")
            continue
        if not sig:
            print(f"{sym}: tidak ada sinyal")
            continue
        piv_id = sig["pivots"][4]["sig"].isoformat()
        key = f"{sym}|{sig['side']}"
        if state.get(key) == piv_id:
            print(f"{sym}: sinyal {sig['side']} sudah pernah dikirim untuk pivot ini")
            continue
        if send_telegram(format_message(sym, sig)):
            state[key] = piv_id
        print(f"{sym}: sinyal {sig['side']} {sig['patterns']}")
    save_state(state)


if __name__ == "__main__":
    main()
