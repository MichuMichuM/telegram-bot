import yfinance as yf
import pandas as pd
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8645220556:AAFH8GO9pZs7X4-GstlI2fGU477ThusIJAs"

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
    df = yf.download(symbol, period="7d", interval=interval)

    if df.empty:
        return "BRAK DANYCH ⚠️", 0

    # 🔴 KLUCZOWE — spłaszcz kolumny (naprawia błąd)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()

    # EMA
    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))

    df = df.dropna()

    last = df.iloc[-1]

    # 🔴 NA SIŁĘ zamieniamy na float (koniec problemów)
    ema20 = float(last["EMA20"])
    ema50 = float(last["EMA50"])
    rsi = float(last["RSI"])

    score = 0

    if ema20 > ema50:
        score += 1
    else:
        score -= 1

    if rsi < 30:
        score += 1
    elif rsi > 70:
        score -= 1

    if score >= 1:
        signal = "BUY 🔼"
    elif score <= -1:
        signal = "SELL 🔽"
    else:
        signal = "NEUTRAL ⚪"

    return signal, round(rsi, 2)


async def trend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        asset = context.args[0]
        timeframe = context.args[1]

        symbol = SYMBOLS.get(asset)
        interval = INTERVALS.get(timeframe)

        if symbol is None or interval is None:
            await update.message.reply_text("Błędne dane. Użyj np: /trend nasdaq 15m")
            return

        signal, rsi = analyze(symbol, interval)

        now = datetime.now().strftime("%H:%M")

        msg = f"{asset.upper()} ({timeframe})\n"
        msg += f"Czas analizy: {now}\n\n"
        msg += f"Sygnał: {signal}\n"
        msg += f"RSI: {rsi}"

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"Błąd: {str(e)}")


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("trend", trend))

app.run_polling()
