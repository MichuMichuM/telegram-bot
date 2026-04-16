import yfinance as yf
import pandas as pd
import numpy as np
import asyncio
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# =========================
# CONFIG
# =========================

TOKEN = "8645220556:AAFH8GO9pZs7X4-GstlI2fGU477ThusIJAs"
CHAT_ID = "1846362978"

SYMBOLS = {
    "nasdaq": "^IXIC",
    "sp500": "^GSPC",
    "gold": "GC=F"
}

bot = Bot(token=TOKEN)

# =========================
# DATA
# =========================

def get_data(symbol, interval="5m", period="5d"):
    df = yf.download(symbol, interval=interval, period=period)

    if df is None or df.empty or len(df) < 100:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    return df.dropna()


# =========================
# RSI (clean version)
# =========================

def rsi(df, period=14):
    delta = df["Close"].diff()

    gain = delta.where(delta > 0, 0).ewm(alpha=1/period).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period).mean()

    rs = gain / loss
    return 100 - (100 / (1 + rs))


# =========================
# MARKET REGIME
# =========================

def regime(df):
    atr = (df["High"] - df["Low"]).rolling(14).mean().iloc[-1]
    price = df["Close"].iloc[-1]

    vol = atr / price

    ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
    ema50 = df["Close"].ewm(span=50).mean().iloc[-1]

    trend_strength = abs(ema20 - ema50) / price

    if vol < 0.003:
        return "CHOP"
    elif trend_strength > 0.008:
        return "TREND"
    else:
        return "TRANSITION"


# =========================
# LIQUIDITY / SWEEP LOGIC
# =========================

def liquidity(df):
    high = df["High"]
    low = df["Low"]

    sweep_high = high.iloc[-1] > high.iloc[-10:-1].max()
    sweep_low = low.iloc[-1] < low.iloc[-10:-1].min()

    return sweep_high, sweep_low


# =========================
# HTF BIAS
# =========================

def htf_bias(symbol):
    df = get_data(symbol, "1h", "7d")

    if df is None:
        return "NEUTRAL"

    df["EMA200"] = df["Close"].ewm(span=200).mean()

    return "BULL" if df["Close"].iloc[-1] > df["EMA200"].iloc[-1] else "BEAR"


# =========================
# CORE ENGINE (PRO SCORING)
# =========================

def analyze(symbol):

    df = get_data(symbol, "5m", "5d")
    if df is None:
        return None

    df["EMA20"] = df["Close"].ewm(span=20).mean()
    df["EMA50"] = df["Close"].ewm(span=50).mean()
    df["EMA200"] = df["Close"].ewm(span=200).mean()
    df["RSI"] = rsi(df)

    close = df["Close"].iloc[-1]
    prev = df.iloc[-2]

    ema20 = df["EMA20"].iloc[-1]
    ema50 = df["EMA50"].iloc[-1]
    ema200 = df["EMA200"].iloc[-1]
    rsi_v = df["RSI"].iloc[-1]

    reg = regime(df)
    bias = htf_bias(symbol)
    sweep_high, sweep_low = liquidity(df)

    atr = (df["High"] - df["Low"]).rolling(14).mean().iloc[-1]

    # =========================
    # SCORE ENGINE (IMPORTANT)
    # =========================

    score = 0

    # trend alignment
    if ema20 > ema50 > ema200:
        score += 3
    elif ema20 < ema50 < ema200:
        score -= 3

    # HTF bias
    score += 2 if bias == "BULL" else -2

    # RSI logic
    if 40 < rsi_v < 65:
        score += 1
    elif rsi_v > 70:
        score -= 2
    elif rsi_v < 30:
        score += 2

    # regime filter
    if reg == "TREND":
        score += 2
    elif reg == "CHOP":
        score -= 3

    # liquidity traps
    if sweep_low:
        score += 2
    if sweep_high:
        score -= 2

    # breakout zones
    recent_high = df["High"].iloc[-15:].max()
    recent_low = df["Low"].iloc[-15:].min()

    breakout_up = close > recent_high * 0.999
    breakout_down = close < recent_low * 1.001

    # =========================
    # SIGNAL DECISION
    # =========================

    signal = "NO TRADE"

    if score >= 8 and breakout_up:
        signal = "BUY A+ 🔼"
    elif score <= -8 and breakout_down:
        signal = "SELL A+ 🔽"

    confidence = min(100, max(0, (score + 6) * 10))

    # fake breakout protection
    if signal.startswith("BUY") and close < prev["High"]:
        return None
    if signal.startswith("SELL") and close > prev["Low"]:
        return None

    # =========================
    # STRICT FILTER (NO TRASH TRADES)
    # =========================

    if confidence < 85:
        return None

    if abs(score) < 8:
        return None

    # SL / TP (ATR based)
    entry = close

    if "BUY" in signal:
        sl = close - atr
        tp = close + 3 * atr
    else:
        sl = close + atr
        tp = close - 3 * atr

    return {
        "signal": signal,
        "score": score,
        "confidence": confidence,
        "rsi": rsi_v,
        "regime": reg,
        "bias": bias,
        "entry": entry,
        "sl": sl,
        "tp": tp
    }


# =========================
# TELEGRAM MESSAGE
# =========================

async def send(symbol, data):

    msg = f"""
🏦 INSTITUTIONAL ALERT

📊 {symbol.upper()}

🔥 {data['signal']}
🧠 Score: {data['score']}
🎯 Confidence: {data['confidence']}%

📈 Bias: {data['bias']}
🌊 Regime: {data['regime']}
📉 RSI: {round(data['rsi'],2)}

ENTRY: {round(data['entry'],2)}
SL: {round(data['sl'],2)}
TP: {round(data['tp'],2)}

⚡ HIGH QUALITY ONLY ⚡
"""

    await bot.send_message(chat_id=CHAT_ID, text=msg)


# =========================
# AUTO SCANNER
# =========================

async def scanner():

    while True:
        for name, symbol in SYMBOLS.items():

            try:
                result = analyze(symbol)

                if result:
                    await send(name, result)

                    with open("signals_v5.csv", "a") as f:
                        f.write(f"{datetime.now()},{name},{result['signal']},{result['score']},{result['confidence']}\n")

            except Exception as e:
                print("error:", e)

        await asyncio.sleep(300)


# =========================
# /trend COMMAND
# =========================

async def trend(update: Update, context: ContextTypes.DEFAULT_TYPE):

    asset = context.args[0]
    symbol = SYMBOLS.get(asset)

    if not symbol:
        await update.message.reply_text("Use: /trend nasdaq")
        return

    data = analyze(symbol)

    if not data:
        await update.message.reply_text("No A+ setup")
        return

    await update.message.reply_text(
        f"{asset.upper()}\n"
        f"{data['signal']} ({data['confidence']}%)\n"
        f"Score: {data['score']}\n"
        f"RSI: {round(data['rsi'],2)}"
    )


# =========================
# START
# =========================

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("trend", trend))

async def main():
    asyncio.create_task(scanner())
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("trend", trend))

app.run_polling()
