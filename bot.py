import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackContext, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from datetime import datetime, timedelta, time
import pytz
import finnhub
import pandas as pd

# === Конфигурация ===
TOKEN = '7639729513:AAEoXUYk4sQDRWb03lt3VMWuXkFe1Bu7Zik'
FINNHUB_API_KEY = 'd10toqhr01qse6le0l2gd10toqhr01qse6le0l30'
SYMBOL = 'EUR_USD'
users_to_monitor = set()
kiev_tz = pytz.timezone('Europe/Kyiv')

# === Finnhub клиент ===
finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)

# === Получение данных рынка ===
def get_market_data(symbol='EUR_USD'):
    try:
        full_symbol = f'OANDA:{symbol.upper()}'
        now = datetime.utcnow()
        from_time = int((now - timedelta(hours=24)).timestamp())
        to_time = int(now.timestamp())

        res = finnhub_client.forex_candles(full_symbol, '5', _from=from_time, to=to_time)

        if res['s'] != 'ok' or not res.get('t'):
            print("❌ Нет данных от API")
            return None

        df = pd.DataFrame({
            'timestamp': res['t'],
            'open': res['o'],
            'high': res['h'],
            'low': res['l'],
            'close': res['c'],
            'volume': res['v']
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df.set_index('timestamp', inplace=True)
        return df

    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        return None

# === Анализ данных (простая логика) ===
def analyze(df):
    last = df['close'].iloc[-1]
    prev = df['close'].iloc[-5]
    direction = "BUY" if last > prev else "SELL"
    confidence = round(abs(last - prev) / prev * 100, 2)
    if confidence < 0.05:
        return "WAIT", 0
    return direction, min(confidence * 10, 99)

# === Telegram обработчики ===
async def start(update: Update, context: CallbackContext):
    users_to_monitor.add(update.effective_chat.id)
    keyboard = [
        [InlineKeyboardButton("🚀 Начать торговлю", callback_data='start_trade')],
        [InlineKeyboardButton("🛑 Закончить торговлю", callback_data='stop_trade')],
        [InlineKeyboardButton("🔄 Продолжить торговлю", callback_data='continue_trade')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👋 Привет! Выбери действие:", reply_markup=reply_markup)

async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data == 'start_trade':
        await query.edit_message_text(text="🚀 Торговля начата.")
    elif query.data == 'stop_trade':
        await query.edit_message_text(text="🛑 СТОП ТРЕЙД. Торговля завершена.")
    elif query.data == 'continue_trade':
        await query.edit_message_text(text="🔄 Продолжаем торговлю.")

async def handle_message(update: Update, context: CallbackContext):
    text = update.message.text.strip().upper()
    global SYMBOL
    if text in ["EUR_USD", "GBP_USD", "USD_JPY"]:  # добавь другие пары
        SYMBOL = text
        await update.message.reply_text(f"✅ Валютная пара установлена: {SYMBOL}")
    elif "АНАЛИЗ" in text:
        df = get_market_data(SYMBOL)
        if df is None:
            await update.message.reply_text("❌ Нет данных для анализа.")
            return
        direction, confidence = analyze(df)
        await update.message.reply_text(f"📊 Сигнал: {direction}\nУверенность: {confidence}%")
    else:
        await update.message.reply_text("😅 Не понял. Используй кнопки или отправь название пары (например: EUR_USD).")

# === Планировщики ===
async def morning_analysis(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in users_to_monitor:
        df = get_market_data(SYMBOL)
        if df is not None:
            direction, confidence = analyze(df)
            await context.bot.send_message(chat_id, f"🌅 Доброе утро!\n📊 Анализ по {SYMBOL}:\nНаправление: {direction}\nУверенность: {confidence}%")

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
                f"📢 Возможность для сделки!\nСигнал: {direction}\nПара: {SYMBOL}\nУверенность: {confidence}%")

# === Запуск бота ===
if name == '__main__':
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.job_queue.run_daily(morning_analysis, time(hour=8, minute=0, tzinfo=kiev_tz))
    app.job_queue.run_daily(evening_stop, time(hour=18, minute=0, tzinfo=kiev_tz))
    app.job_queue.run_repeating(auto_monitor, interval=120, first=10)

    app.run_polling()
