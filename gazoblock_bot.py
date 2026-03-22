#!/usr/bin/env python3
"""
Газоблок бот / Газблок боты
Telegram бот с Google Gemini AI (бесплатно)
"""

import logging
import os
import google.generativeai as genai
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)

# ─── Настройки ────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

genai.configure(api_key=GEMINI_API_KEY)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

CHOOSE_ACTION, CHOOSE_BLOCK, GET_LENGTH, GET_WIDTH, GET_HEIGHT, GET_FLOORS, GET_OPENINGS, GET_INNER_WALLS = range(8)

BLOCKS = {
    "Б1 (100мм)":   {"thickness": 0.10, "volume": 0.018, "per_pallet": 96,  "price_m3": 30000},
    "Б1.5 (150мм)": {"thickness": 0.15, "volume": 0.027, "per_pallet": 64,  "price_m3": 30000},
    "Б2 (200мм)":   {"thickness": 0.20, "volume": 0.036, "per_pallet": 48,  "price_m3": 30000},
    "Б2.5 (250мм)": {"thickness": 0.25, "volume": 0.045, "per_pallet": 40,  "price_m3": 30000},
    "Б3 (300мм)":   {"thickness": 0.30, "volume": 0.054, "per_pallet": 35,  "price_m3": 30000},
}

SYSTEM_PROMPT = """Ты — консультант по газоблокам компании из Алматы.
Отвечаешь на русском и казахском языке (если клиент пишет по-казахски — отвечай по-казахски, иначе по-русски).

Данные о блоках:
- Б1 (100мм): 96 шт/поддон, 30 000 тенге/м³
- Б1.5 (150мм): 64 шт/поддон, 30 000 тенге/м³
- Б2 (200мм): 48 шт/поддон, 30 000 тенге/м³
- Б2.5 (250мм): 40 шт/поддон, 30 000 тенге/м³
- Б3 (300мм): 35 шт/поддон, 30 000 тенге/м³

Формула: V = (P x H - S_проёмов) x T. Запас 6%. Клей: 1 мешок 25кг на 1м³.
Цена: 30 000 тенге/м³ с НДС, без доставки.
Контакт: +7 771 799 92 91 (Наталья), Боралдай, Промзона 71.
Отвечай кратко и дружелюбно."""

def main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🧮 Расчёт блоков / Блок есептеу")],
        [KeyboardButton("❓ Вопрос про газоблок / Сұрақ қою")],
        [KeyboardButton("📞 Контакты / Байланыс")],
    ], resize_keyboard=True)

def block_keyboard():
    keys = [[KeyboardButton(b)] for b in BLOCKS.keys()]
    keys.append([KeyboardButton("⬅️ Назад")])
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

def calculate(data: dict) -> str:
    block = BLOCKS[data["block"]]
    T = block["thickness"]
    perimeter = 2 * (data["length"] + data["width"]) + data["inner_walls"]
    net_area = perimeter * data["height"] * data["floors"] - data["openings"]
    volume = net_area * T
    vol_r = volume * 1.06
    pieces = vol_r / block["volume"]
    pallets = pieces / block["per_pallet"]
    cost = vol_r * block["price_m3"]

    return (f'✅ *Результат расчёта / Есеп нәтижесі*\n\n'
            f'🏠 Дом: {data["length"]}×{data["width"]} м, {data["floors"]} этаж, высота {data["height"]} м\n'
            f'🧱 Блок: {data["block"]}\n\n'
            f'📐 *Расчёт:*\n'
            f'• Периметр стен: {perimeter:.1f} м\n'
            f'• Площадь кладки: {net_area:.1f} м²\n'
            f'• Объём без запаса: {volume:.1f} м³\n'
            f'• Объём с запасом 6%: *{vol_r:.1f} м³*\n\n'
            f'📦 *Количество:*\n'
            f'• Блоков: ~{int(pieces):,} шт\n'
            f'• Поддонов: ~{int(pallets)+1} шт\n'
            f'• Клей: ~{int(vol_r)+1} мешков (25 кг)\n\n'
            f'💰 *Стоимость:* ~{int(cost):,} ₸\n'
            f'(с НДС, без доставки)\n\n'
            f'📞 Заказ: +7 771 799 92 91 (Наталья)')

async def ask_gemini(question: str, history: list) -> str:
    model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
    chat_history = [{"role": "user" if m["role"]=="user" else "model", "parts": [m["content"]]} for m in history]
    chat = model.start_chat(history=chat_history)
    response = chat.send_message(question)
    return response.text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["history"] = []
    await update.message.reply_text(
        "👋 Сәлем! Привет!\n\nМен газоблок бойынша сізге көмектесемін.\nЯ помогу рассчитать газоблок для вашего дома.\n\nВыберите действие 👇",
        reply_markup=main_keyboard()
    )
    return CHOOSE_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "Расчёт" in text or "есептеу" in text.lower():
        await update.message.reply_text("Қандай блок таңдайсыз?\nКакой тип блока выбираете?", reply_markup=block_keyboard())
        return CHOOSE_BLOCK
    elif "Вопрос" in text or "Сұрақ" in text:
        await update.message.reply_text("Газоблок туралы сұрағыңызды жазыңыз 👇\nНапишите ваш вопрос про газоблок 👇")
        return CHOOSE_ACTION
    elif "Контакт" in text or "Байланыс" in text:
        await update.message.reply_text(
            "📞 *Наши контакты:*\n\n👤 Наталья: +7 771 799 92 91\n📍 Алматинская обл., Боралдай,\nПромзона 71-й разъезд, стр. 61\n\n⏰ Пн-Сб: 9:00 - 18:00",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )
        return CHOOSE_ACTION
    else:
        history = context.user_data.get("history", [])
        thinking_msg = await update.message.reply_text("⏳ Ойлап жатырмын... Думаю...")
        try:
            answer = await ask_gemini(text, history)
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": answer})
            context.user_data["history"] = history[-10:]
            await thinking_msg.edit_text(answer)
        except Exception as e:
            await thinking_msg.edit_text("❌ Қате болды. Кейінірек қайталаңыз.\nОшибка. Попробуйте позже.")
            logger.error(f"Gemini error: {e}")
        return CHOOSE_ACTION

async def choose_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "Назад" in text:
        await update.message.reply_text("Басты мәзір:", reply_markup=main_keyboard())
        return CHOOSE_ACTION
    if text not in BLOCKS:
        await update.message.reply_text("Блокты таңдаңыз / Выберите блок из списка:")
        return CHOOSE_BLOCK
    context.user_data["block"] = text
    await update.message.reply_text(f"✅ {text} таңдалды.\n\nВведите длину дома в метрах (например: 14):")
    return GET_LENGTH

async def get_length(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["length"] = float(update.message.text.replace(",", "."))
        await update.message.reply_text("Введите ширину дома в метрах (например: 14):")
        return GET_WIDTH
    except:
        await update.message.reply_text("❗ Введите число, например: 14")
        return GET_LENGTH

async def get_width(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["width"] = float(update.message.text.replace(",", "."))
        await update.message.reply_text("Введите высоту стен в метрах (например: 3):")
        return GET_HEIGHT
    except:
        await update.message.reply_text("❗ Введите число, например: 14")
        return GET_WIDTH

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["height"] = float(update.message.text.replace(",", "."))
        await update.message.reply_text("Количество этажей (1, 2 или 3):")
        return GET_FLOORS
    except:
        await update.message.reply_text("❗ Введите число, например: 3")
        return GET_HEIGHT

async def get_floors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = int(update.message.text)
        if val < 1 or val > 5: raise ValueError
        context.user_data["floors"] = val
        await update.message.reply_text("Общая площадь окон и дверей в м² (например: 30):")
        return GET_OPENINGS
    except:
        await update.message.reply_text("❗ Введите число от 1 до 5")
        return GET_FLOORS

async def get_openings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["openings"] = float(update.message.text.replace(",", "."))
        await update.message.reply_text("Суммарная длина несущих внутренних стен в метрах\n(если не знаете — напишите 0):")
        return GET_INNER_WALLS
    except:
        await update.message.reply_text("❗ Введите число, например: 30")
        return GET_OPENINGS

async def get_inner_walls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["inner_walls"] = float(update.message.text.replace(",", "."))
        result = calculate(context.user_data)
        await update.message.reply_text(result, parse_mode="Markdown", reply_markup=main_keyboard())
        return CHOOSE_ACTION
    except:
        await update.message.reply_text("❗ Введите число, например: 28")
        return GET_INNER_WALLS

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Отменено.", reply_markup=main_keyboard())
    return CHOOSE_ACTION

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_ACTION:   [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            CHOOSE_BLOCK:    [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_block)],
            GET_LENGTH:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_length)],
            GET_WIDTH:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_width)],
            GET_HEIGHT:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            GET_FLOORS:      [MessageHandler(filters.TEXT & ~filters.COMMAND, get_floors)],
            GET_OPENINGS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_openings)],
            GET_INNER_WALLS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_inner_walls)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)
    logger.info("Бот запущен с Google Gemini!")
    app.run_polling()

if __name__ == "__main__":
    main()
