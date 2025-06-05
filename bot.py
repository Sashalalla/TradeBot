import logging
import pandas as pd
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes
)
from datetime import time
import pytz

TOKEN = '7639729513:AAEoXUYk4sQDRWb03lt3VMWuXkFe1Bu7Zik'
ALPHA_VANTAGE_API_KEY = '6IO85LUA6K3PISYB'  # твой ключ

logging.basicConfig(level=logging.INFO)

main_menu = ReplyKeyboardMarkup([
    [KeyboardButton("📊 Дай сделку"), KeyboardButton("📉 Завершить торговлю")],
    [KeyboardButton("💱 Изменить валютную пару"), KeyboardButton("📈 Какой рынок сейчас?")]
], resize_keyboard=True)

users_to_monitor = set()
SYMBOL = 'EURUSD'
kiev_tz = pytz.timezone("Europe/Kyiv")


def get_market_data(symbol):
    url = f"https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol={symbol[:3]}&to_symbol={symbol[3:]}&interval=1min&apikey={ALPHA_VANTAGE_API_KEY}"
    response = requests.get(url)
    data = response.json()
    if "Time Series FX (1min)" not in data:
        return None
    df = pd.DataFrame.from_dict(data['Time Series FX (1min)'], orient='index')
    df = df.rename(columns={
        '1. open': 'open',
        '2. high': 'high',
        '3. low': 'low',
        '4. close': 'close'
    })
    df = df.astype(float)
    df = df.sort_index()
    return df


def analyze(df):
    df['sma'] = df['close'].rolling(window=14).mean()
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))
    latest = df.iloc[-1]

    if latest['rsi'] < 30 and latest['close'] > latest['sma']:
        return ("CALL", 85)
    elif latest['rsi'] > 70 and latest['close'] < latest['sma']:
        return ("PUT", 80)
    else:
        return ("WAIT", 50)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_to_monitor.add(chat_id)
    await update.message.reply_text(
        "👋 Привет! Я твой бот-напарник по трейду. Жми кнопки снизу ⬇",
        reply_markup=main_menu
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global SYMBOL
    text = update.message.text
    chat_id = update.effective_chat.id

    if text == "📊 Дай сделку":
        await update.message.reply_text("⏳ Анализирую рынок...")
        df = get_market_data(SYMBOL)
        if df is None:
            await update.message.reply_text("⚠️ Не удалось получить данные.")
            return
        direction, confidence = analyze(df)
        if direction == "WAIT" or confidence < 70:
            await update.message.reply_text("🤔 Я не уверен в рынке сейчас. Лучше подождать.")
        else:
            await update.message.reply_text(
                f"📢 Сигнал: {direction}\n💸 Валюта: {SYMBOL}\n⏱️ Время: 1-5 минут\n✅ Уверенность: {confidence}%"
            )

    elif text == "📉 Завершить торговлю":
        users_to_monitor.discard(chat_id)
        await update.message.reply_text("🛑 СТОП ТРЕЙД! Торговля завершена.")

    elif text == "💱 Изменить валютную пару":
        await update.message.reply_text("✍️ Введи валютную пару (например: GBPUSD):")
        context.user_data['await_symbol'] = True

    elif text == "📈 Какой рынок сейчас?":
        df = get_market_data(SYMBOL)
        if df is None:
            await update.message.reply_text("⚠️ Не удалось получить данные.")
            return
        direction, confidence = analyze(df)
        if confidence > 80:
            mood = "✅ Спокойный и подходящий для входа"
        elif confidence > 60:
            mood = "⚠️ Средний — будь внимателен"
        else:
            mood = "🚨 Волатильный/опасный рынок"
        await update.message.reply_text(
            f"📊 Текущий рынок: {mood}\nПара: {SYMBOL}\nУверенность: {confidence}%"
        )

    elif context.user_data.get('await_symbol'):
        SYMBOL = text.upper()
        context.user_data['await_symbol'] = False
        await update.message.reply_text(f"✅ Валютная пара установлена: {SYMBOL}")

    else:
        await update.message.reply_text("😅 Не понял. Используй кнопки внизу.")


async def morning_analysis(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in users_to_monitor:
        df = get_market_data(SYMBOL)
        if df is not None:
            direction, confidence = analyze(df)
            await context.bot.send_message(chat_id, f"🌅 Доброе утро!\nАнализ по {SYMBOL}: {direction}\nУверенность: {confidence}%")


async def evening_stop(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in users_to_monitor:
        await context.bot.send_message(chat_id, "🌙 Уже 18:00 по Киеву.\n🚫 СТОП ТРЕЙД! Лучше завершить торговлю.")


async def auto_monitor(context: ContextTypes.DEFAULT_TYPE):
    df = get_market_data(SYMBOL)
    if df is None:
        return
    direction, confidence = analyze(df)
    if direction != "WAIT" and confidence >= 80:
        for chat_id in users_to_monitor:
            await context.bot.send_message(chat_id,
                                           f"📢 Обнаружена возможность!\nСигнал: {direction}\nПара: {SYMBOL}\nУверенность: {confidence}%")


if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_daily(morning_analysis, time(hour=8, minute=0, tzinfo=kiev_tz))
    app.job_queue.run_daily(evening_stop, time(hour=18, minute=0, tzinfo=kiev_tz))
    app.job_queue.run_repeating(auto_monitor, interval=120, first=10)

    app.run_polling()
