import yfinance as yf
import pandas as pd
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8645220556:AAFH8GO9pZs7X4-GstlI2fGU477ThusIJAs"
CHAT_ID = "1846362978"

SYMBOLS = {
    "nasdaq": "^IXIC",
    "sp500": "^GSPC",
    "gold": "GC=F"
}

INTERVALS = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "60m"
}

last_alert_time = {}

# HTF
def get_htf_trend(symbol):
    df = yf.download(symbol, period="7d", interval="60m")
    df = df.dropna()
    df["EMA200"] = df["Close"].ewm(span=200).mean()
    last = df.iloc[-1]
    return "UP" if last["Close"] > last["EMA200"] else "DOWN"


def analyze(symbol, interval):

    period = "7d"
    if interval == "1m":
        period = "1d"
    elif interval == "5m":
        period = "5d"

    df = yf.download(symbol, period=period, interval=interval)

    if df.empty:
        return None

    df = df.dropna()

    # EMA
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["EMA200"] = df["Close"].ewm(span=200).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # ATR
    df["TR"] = (df["High"] - df["Low"]).combine(
        abs(df["High"] - df["Close"].shift(1)), max
    )
    df["ATR"] = df["TR"].rolling(14).mean()

    # Volume
    df["VOL_MA"] = df["Volume"].rolling(20).mean()

    df = df.dropna()

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    close = last["Close"]
    rsi = last["RSI"]
    atr = last["ATR"]

    trend = "UP" if close > last["EMA200"] else "DOWN"
    htf = get_htf_trend(symbol)

    volume_spike = last["Volume"] > last["VOL_MA"] * 1.5

    # 🔥 MARKET STRUCTURE
    hh = last["High"] > prev["High"]
    ll = last["Low"] < prev["Low"]

    structure = "BULLISH" if hh else "BEARISH" if ll else "RANGE"

    # 🔥 LIQUIDITY SWEEP (STOP HUNT)
    sweep_high = last["High"] > prev["High"] and close < prev["High"]
    sweep_low = last["Low"] < prev["Low"] and close > prev["Low"]

    # 🔥 FAKE BREAKOUT
    fake_breakout_up = prev["High"] < prev2["High"] and close < prev["High"]
    fake_breakout_down = prev["Low"] > prev2["Low"] and close > prev["Low"]

    # FILTR CHOP
    if 45 < rsi < 55 and not volume_spike:
        return {"signal": "NO TRADE", "reason": "chop"}

    # CONFLUENCE
    score = 0

    if trend == "UP":
        score += 1
    if trend == "DOWN":
        score -= 1

    if volume_spike:
        score += 1

    if structure == "BULLISH":
        score += 1
    elif structure == "BEARISH":
        score -= 1

    # 🔥 SMART MONEY SIGNALS
    signal = "NO TRADE"

    # BUY SETUP
    if sweep_low and trend == "UP" and volume_spike:
        signal = "BUY"

    # SELL SETUP
    if sweep_high and trend == "DOWN" and volume_spike:
        signal = "SELL"

    # FAKE BREAKOUT REVERSAL
    if fake_breakout_up and trend == "DOWN":
        signal = "SELL"

    if fake_breakout_down and trend == "UP":
        signal = "BUY"

    # HTF FILTER
    if trend != htf:
        signal = "NO TRADE"

    # ENTRY / SL / TP (smart)
    entry = close
    sl = None
    tp = None

    if signal == "BUY":
        sl = last["Low"] - atr * 0.5
        tp = close + (2 * atr)

    elif signal == "SELL":
        sl = last["High"] + atr * 0.5
        tp = close - (2 * atr)

    # 🔥 ULTRA SETUP (bardzo rzadki)
    ultra = False

    if (
        signal != "NO TRADE"
        and volume_spike
        and trend == htf
        and abs(rsi - 50) > 10
        and (sweep_high or sweep_low)
    ):
        ultra = True

    # OPIS
    desc = f"Trend {trend}, struktura {structure}."
    if sweep_high or sweep_low:
        desc += " Liquidity sweep."
    if volume_spike:
        desc += " Wysoki wolumen."

    return {
        "signal": signal,
        "trend": trend,
        "rsi": round(rsi, 2),
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "desc": desc,
        "ultra": ultra
    }


async def trend(update: Update, context: ContextTypes.DEFAULT_TYPE):

    asset = context.args[0]
    timeframe = context.args[1]

    symbol = SYMBOLS.get(asset)
    interval = INTERVALS.get(timeframe)

    data = analyze(symbol, interval)

    if not data:
        await update.message.reply_text("Brak danych")
        return

    msg = f"{asset.upper()} ({timeframe})\n\n"
    msg += f"{data['desc']}\n\n"
    msg += f"Sygnał: {data['signal']}\n"
    msg += f"RSI: {data['rsi']}\n"

    if data["signal"] != "NO TRADE":
        msg += f"\nENTRY: {round(data['entry'],2)}"
        msg += f"\nSL: {round(data['sl'],2)}"
        msg += f"\nTP: {round(data['tp'],2)}"

    await update.message.reply_text(msg)


# 🚨 AUTO ALERT (ULTRA)
async def auto_alert(app):
    global last_alert_time

    while True:
        now = datetime.now()

        for name, symbol in SYMBOLS.items():
            data = analyze(symbol, "15m")

            if data and data["ultra"]:

                last_time = last_alert_time.get(name)

                if last_time and (now - last_time).seconds < 7200:
                    continue

                last_alert_time[name] = now

                msg = f"🚨 ULTRA SETUP {name.upper()} 🚨\n\n"
                msg += f"{data['desc']}\n"
                msg += f"\nRSI: {data['rsi']}"
                msg += f"\nENTRY: {round(data['entry'],2)}"
                msg += f"\nSL: {round(data['sl'],2)}"
                msg += f"\nTP: {round(data['tp'],2)}"

                await app.bot.send_message(chat_id=CHAT_ID, text=msg)

        await asyncio.sleep(300)


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("trend", trend))

app.job_queue.run_once(lambda ctx: asyncio.create_task(auto_alert(app)), 1)

app.run_polling()
