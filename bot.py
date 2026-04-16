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
        return "BRAK DANYCH ⚠️", 0, "-", "-", "-", 0

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

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

    # Bollinger
    df["MA20"] = df["Close"].rolling(20).mean()
    df["STD"] = df["Close"].rolling(20).std()
    df["UPPER"] = df["MA20"] + 2 * df["STD"]
    df["LOWER"] = df["MA20"] - 2 * df["STD"]

    df = df.dropna()
    last = df.iloc[-1]

    close = float(last["Close"])
    ema20 = float(last["EMA20"])
    ema50 = float(last["EMA50"])
    ema200 = float(last["EMA200"])
    rsi = float(last["RSI"])
    macd = float(last["MACD"])
    signal_line = float(last["SIGNAL"])

    # 🔥 TREND
    trend = "UP 📈" if close > ema200 else "DOWN 📉"

    # 🔥 MOMENTUM
    momentum = "BULLISH" if macd > signal_line else "BEARISH"

    # 🔥 FVG DETECTION
    fvg = "NONE"
    if len(df) > 3:
        c1 = df.iloc[-3]
        c3 = df.iloc[-1]

        if c1["High"] < c3["Low"]:
            fvg = "BULLISH"
        elif c1["Low"] > c3["High"]:
            fvg = "BEARISH"

    score = 0

    # trend alignment
    if ema20 > ema50:
        score += 1
    else:
        score -= 1

    # RSI mid zone
    if 45 < rsi < 65:
        score += 1

    # MACD
    if macd > signal_line:
        score += 1
    else:
        score -= 1

    # FVG boost
    if fvg == "BULLISH":
        score += 1
    elif fvg == "BEARISH":
        score -= 1

    # Bollinger filter
    if close > last["UPPER"] or close < last["LOWER"]:
        score -= 1  # overextended

    # FINAL
    if score >= 3:
        signal = "BUY 🔼 (STRONG)"
    elif score <= -3:
        signal = "SELL 🔽 (STRONG)"
    else:
        signal = "NO TRADE ⚪"

    confidence = min(abs(score) * 20, 100)

    return signal, round(rsi, 2), trend, momentum, fvg, confidence


async def trend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        asset = context.args[0]
        timeframe = context.args[1]

        symbol = SYMBOLS.get(asset)
        interval = INTERVALS.get(timeframe)

        if symbol is None or interval is None:
            await update.message.reply_text("Błędne dane. Użyj np: /trend nasdaq 15m")
            return

        signal, rsi, trend_dir, momentum, fvg, confidence = analyze(symbol, interval)

        now = datetime.now().strftime("%H:%M")

        msg = f"{asset.upper()} ({timeframe})\n"
        msg += f"Czas: {now}\n\n"
        msg += f"Trend: {trend_dir}\n"
        msg += f"Momentum: {momentum}\n"
        msg += f"FVG: {fvg}\n\n"
        msg += f"Sygnał: {signal}\n"
        msg += f"Confidence: {confidence}%\n\n"
        msg += f"RSI: {rsi}"

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"Błąd: {str(e)}")


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("trend", trend))

app.run_polling()
