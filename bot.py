import yfinance as yf
import pandas as pd
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8645220556:AAFH8GO9pZs7X4-GstlI2fGU477ThusIJAs"
CHAT_ID = "1846362978"  # do auto alertów

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
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["EMA200"] = df["Close"].ewm(span=200).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df["Close"].ewm(span=12).mean()
    ema26 = df["Close"].ewm(span=26).mean()
    df["MACD"] = ema12 - ema26
    df["SIGNAL"] = df["MACD"].ewm(span=9).mean()

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

    close = last["Close"]
    rsi = last["RSI"]
    atr = last["ATR"]

    # TREND
    trend = "UP" if close > last["EMA200"] else "DOWN"

    # MOMENTUM
    momentum = "BULLISH" if last["MACD"] > last["SIGNAL"] else "BEARISH"

    # VOLUME
    volume_spike = last["Volume"] > last["VOL_MA"] * 1.5

    # MARKET STRUCTURE (proste HH/LL)
    hh = last["High"] > prev["High"]
    ll = last["Low"] < prev["Low"]

    structure = "BULLISH" if hh else "BEARISH" if ll else "RANGE"

    # HTF
    htf = get_htf_trend(symbol)

    # FILTRY (NO TRADE)
    if 45 < rsi < 55 and not volume_spike:
        return {"signal": "NO TRADE", "reason": "chop"}

    if trend != htf:
        return {"signal": "NO TRADE", "reason": "against HTF"}

    # CONFLUENCE
    confluence = 0

    if trend == "UP":
        confluence += 1
    if momentum == "BULLISH":
        confluence += 1
    if volume_spike:
        confluence += 1
    if structure == "BULLISH":
        confluence += 1

    if trend == "DOWN":
        confluence -= 1
    if momentum == "BEARISH":
        confluence -= 1
    if structure == "BEARISH":
        confluence -= 1

    # SIGNAL
    signal = "NO TRADE"

    if confluence >= 3:
        signal = "BUY"
    elif confluence <= -3:
        signal = "SELL"

    # ENTRY
    entry = close
    sl = close - atr if signal == "BUY" else close + atr
    tp = close + (2 * atr) if signal == "BUY" else close - (2 * atr)

    # ULTRA SETUP
    ultra = False
    if signal != "NO TRADE" and volume_spike and trend == htf and abs(rsi - 50) > 10:
        ultra = True

    # LUDZKI OPIS
    description = f"Trend {trend}, momentum {momentum}, struktura {structure}."
    if volume_spike:
        description += " Wysoki wolumen."

    return {
        "signal": signal,
        "trend": trend,
        "momentum": momentum,
        "rsi": round(rsi, 2),
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "desc": description,
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


# 🚨 AUTO ALERT LOOP
async def auto_alert(app):
    while True:
        for name, symbol in SYMBOLS.items():
            data = analyze(symbol, "15m")

            if data and data["ultra"]:
                msg = f"🚨 ULTRA SETUP {name.upper()} 🚨\n\n"
                msg += f"{data['desc']}\n"
                msg += f"\nENTRY: {round(data['entry'],2)}"
                msg += f"\nSL: {round(data['sl'],2)}"
                msg += f"\nTP: {round(data['tp'],2)}"

                await app.bot.send_message(chat_id=CHAT_ID, text=msg)

        await asyncio.sleep(300)  # co 5 min


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("trend", trend))

app.job_queue.run_once(lambda ctx: asyncio.create_task(auto_alert(app)), 1)

app.run_polling()
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("trend", trend))

app.run_polling()
