import yfinance as yf
import pandas as pd
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8645220556:AAGmSpMANoV2EHyWBBr5B1jWllCpjcWWO-M"

SYMBOLS = {
    "nasdaq": "^IXIC",
    "sp500": "^GSPC",
    "gold": "GC=F"
}

INTERVALS = {
    "15m": "15m",
    "1h": "60m"
}

def analyze(symbol, interval):
    df = yf.download(symbol, period="5d", interval=interval)

    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    last = df.iloc[-1]

    score = 0

    if last["EMA20"] > last["EMA50"]:
        score += 1
    else:
        score -= 1

    if last["RSI"] < 30:
        score += 1
    elif last["RSI"] > 70:
        score -= 1

    if score >= 1:
        signal = "BUY 🔼"
    elif score <= -1:
        signal = "SELL 🔽"
    else:
        signal = "NEUTRAL ⚪"

    return signal, round(last["RSI"], 2)

async def trend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        asset = context.args[0]
        timeframe = context.args[1]

        symbol = SYMBOLS.get(asset)
        interval = INTERVALS.get(timeframe)

        signal, rsi = analyze(symbol, interval)

        now = datetime.now().strftime("%H:%M")

        msg = f"{asset.upper()} ({timeframe})\n"
        msg += f"Czas analizy: {now}\n\n"
        msg += f"Sygnał: {signal}\n"
        msg += f"RSI: {rsi}"

        await update.message.reply_text(msg)

    except:
        await update.message.reply_text("Użycie: /trend nasdaq 15m")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("trend", trend))
app.run_polling()
