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
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "60m"
}


def get_htf_trend(symbol):
    df = yf.download(symbol, period="7d", interval="60m")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()
    df["EMA200"] = df["Close"].ewm(span=200).mean()

    last = df.iloc[-1]

    if float(last["Close"]) > float(last["EMA200"]):
        return "UP 📈"
    else:
        return "DOWN 📉"


def analyze(symbol, interval):
    # dobór danych
    if interval == "1m":
        period = "1d"
    elif interval == "5m":
        period = "5d"
    else:
        period = "7d"

    df = yf.download(symbol, period=period, interval=interval)

    if df.empty:
        return "BRAK DANYCH ⚠️", 0, "-", "-", "-", 0, None, None, None

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

    # ATR
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift(1))
    df["L-PC"] = abs(df["Low"] - df["Close"].shift(1))
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].rolling(14).mean()

    df = df.dropna()
    last = df.iloc[-1]

    close = float(last["Close"])
    ema20 = float(last["EMA20"])
    ema50 = float(last["EMA50"])
    ema200 = float(last["EMA200"])
    rsi = float(last["RSI"])
    macd = float(last["MACD"])
    signal_line = float(last["SIGNAL"])
    atr = float(last["ATR"])

    # TREND
    trend = "UP 📈" if close > ema200 else "DOWN 📉"

    # MOMENTUM
    momentum = "BULLISH" if macd > signal_line else "BEARISH"

    # FVG
    fvg = "NONE"
    if len(df) > 3:
        c1 = df.iloc[-3]
        c3 = df.iloc[-1]

        if c1["High"] < c3["Low"]:
            fvg = "BULLISH"
        elif c1["Low"] > c3["High"]:
            fvg = "BEARISH"

    # filtr szumu
    if interval in ["1m", "5m"]:
        if abs(rsi - 50) < 5:
            return "NO TRADE ⚪ (CHOP)", rsi, trend, momentum, fvg, 0, None, None, None

    score = 0

    if ema20 > ema50:
        score += 1
    else:
        score -= 1

    if 45 < rsi < 65:
        score += 1

    if macd > signal_line:
        score += 1
    else:
        score -= 1

    if fvg == "BULLISH":
        score += 1
    elif fvg == "BEARISH":
        score -= 1

    if close > last["UPPER"] or close < last["LOWER"]:
        score -= 1

    if score >= 3:
        signal = "BUY 🔼 (STRONG)"
    elif score <= -3:
        signal = "SELL 🔽 (STRONG)"
    else:
        signal = "NO TRADE ⚪"

    confidence = min(abs(score) * 20, 100)

    # fake breakout
    prev = df.iloc[-2]

    if signal.startswith("BUY") and close < prev["High"]:
        return "NO TRADE ⚪ (FAKE)", rsi, trend, momentum, fvg, 0, None, None, None

    if signal.startswith("SELL") and close > prev["Low"]:
        return "NO TRADE ⚪ (FAKE)", rsi, trend, momentum, fvg, 0, None, None, None

    # ENTRY / SL / TP
    entry = None
    sl = None
    tp = None

    if signal.startswith("BUY") and momentum == "BULLISH":
        entry = close
        sl = close - atr
        tp = close + (2 * atr)

    elif signal.startswith("SELL") and momentum == "BEARISH":
        entry = close
        sl = close + atr
        tp = close - (2 * atr)

    return signal, round(rsi, 2), trend, momentum, fvg, confidence, entry, sl, tp


async def trend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        asset = context.args[0]
        timeframe = context.args[1]

        symbol = SYMBOLS.get(asset)
        interval = INTERVALS.get(timeframe)

        if symbol is None or interval is None:
            await update.message.reply_text("Użycie: /trend nasdaq 15m")
            return

        signal, rsi, trend_dir, momentum, fvg, confidence, entry, sl, tp = analyze(symbol, interval)
        htf = get_htf_trend(symbol)

        now = datetime.now().strftime("%H:%M")

        msg = f"{asset.upper()} ({timeframe})\n"
        msg += f"Czas: {now}\n\n"
        msg += f"HTF (1h): {htf}\n"
        msg += f"Trend: {trend_dir}\n"
        msg += f"Momentum: {momentum}\n"
        msg += f"FVG: {fvg}\n\n"
        msg += f"Sygnał: {signal}\n"
        msg += f"Confidence: {confidence}%\n\n"
        msg += f"RSI: {rsi}"

        if entry:
            msg += f"\nENTRY: {round(entry,2)}\n"
            msg += f"SL: {round(sl,2)}\n"
            msg += f"TP: {round(tp,2)}\n"

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"Błąd: {str(e)}")


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("trend", trend))

app.run_polling()
