#!/usr/bin/env python3
"""
Газоблок бот - использует requests (без ConversationHandler)
"""
import os
import logging
import requests
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")

genai.configure(api_key=GEMINI_API_KEY)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

BLOCKS = {
    "б1":   {"name": "Б1 (100мм)",   "thickness": 0.10, "volume": 0.018, "per_pallet": 96,  "price_m3": 30000},
    "б1.5": {"name": "Б1.5 (150мм)", "thickness": 0.15, "volume": 0.027, "per_pallet": 64,  "price_m3": 30000},
    "б2":   {"name": "Б2 (200мм)",   "thickness": 0.20, "volume": 0.036, "per_pallet": 48,  "price_m3": 30000},
    "б2.5": {"name": "Б2.5 (250мм)", "thickness": 0.25, "volume": 0.045, "per_pallet": 40,  "price_m3": 30000},
    "б3":   {"name": "Б3 (300мм)",   "thickness": 0.30, "volume": 0.054, "per_pallet": 35,  "price_m3": 30000},
}

SYSTEM_PROMPT = """Ты — консультант по газоблокам компании из Алматы.
Отвечаешь на русском и казахском языке.

Данные о блоках (цена 30 000 тенге/м³ с НДС, без доставки):
- Б1 (100мм): 96 шт/поддон
- Б1.5 (150мм): 64 шт/поддон
- Б2 (200мм): 48 шт/поддон
- Б2.5 (250мм): 40 шт/поддон
- Б3 (300мм): 35 шт/поддон

Формула: V = (P x H - S_проёмов) x T. Запас 6%. Клей: 1 мешок 25кг на 1м³.
Контакт: +7 771 799 92 91 (Наталья), Боралдай, Промзона 71.
Отвечай кратко и дружелюбно. Не используй markdown форматирование."""

# Хранилище состояний пользователей
user_states = {}
user_data = {}
user_history = {}

def send_message(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = {"keyboard": keyboard, "resize_keyboard": True}
    requests.post(f"{BASE_URL}/sendMessage", json=data)

def main_menu(chat_id):
    send_message(chat_id,
        "Выберите действие / Әрекет таңдаңыз:",
        [
            ["🧮 Расчёт блоков"],
            ["❓ Вопрос про газоблок"],
            ["📞 Контакты"],
        ]
    )

def ask_gemini(question, history):
    try:
        model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
        chat_history = [{"role": "user" if m["role"]=="user" else "model", "parts": [m["content"]]} for m in history]
        chat = model.start_chat(history=chat_history)
        response = chat.send_message(question)
        return response.text
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "Қате болды. Кейінірек қайталаңыз. / Ошибка. Попробуйте позже."

def calculate(d):
    b = BLOCKS[d["block"]]
    T = b["thickness"]
    perimeter = 2 * (d["length"] + d["width"]) + d["inner_walls"]
    net_area = perimeter * d["height"] * d["floors"] - d["openings"]
    volume = net_area * T
    vol_r = volume * 1.06
    pieces = vol_r / b["volume"]
    pallets = pieces / b["per_pallet"]
    cost = vol_r * b["price_m3"]

    return (
        f"✅ Результат расчёта / Есеп нәтижесі\n\n"
        f"🏠 Дом: {d['length']}x{d['width']} м, {d['floors']} этаж, высота {d['height']} м\n"
        f"🧱 Блок: {b['name']}\n\n"
        f"Периметр стен: {perimeter:.1f} м\n"
        f"Площадь кладки: {net_area:.1f} м²\n"
        f"Объём без запаса: {volume:.1f} м³\n"
        f"Объём с запасом 6%: {vol_r:.1f} м³\n\n"
        f"📦 Блоков: ~{int(pieces):,} шт\n"
        f"📦 Поддонов: ~{int(pallets)+1} шт\n"
        f"🪣 Клей: ~{int(vol_r)+1} мешков (25 кг)\n\n"
        f"💰 Стоимость: ~{int(cost):,} тенге\n"
        f"(с НДС, без доставки)\n\n"
        f"📞 Заказ: +7 771 799 92 91 (Наталья)"
    )

def handle_message(chat_id, text):
    text = text.strip()
    state = user_states.get(chat_id, "menu")
    data = user_data.get(chat_id, {})
    history = user_history.get(chat_id, [])

    # Команда старт
    if text in ["/start", "/start@Almatygazablokbot"]:
        user_states[chat_id] = "menu"
        user_data[chat_id] = {}
        user_history[chat_id] = []
        send_message(chat_id,
            "👋 Сәлем! Привет!\n\nМен газоблок бойынша сізге көмектесемін.\nЯ помогу рассчитать газоблок для вашего дома.")
        main_menu(chat_id)
        return

    # Главное меню
    if "Расчёт" in text or "есептеу" in text.lower():
        user_states[chat_id] = "choose_block"
        user_data[chat_id] = {}
        send_message(chat_id, "Какой тип блока выбираете?", [
            ["Б1 (100мм)", "Б1.5 (150мм)"],
            ["Б2 (200мм)", "Б2.5 (250мм)"],
            ["Б3 (300мм)"],
            ["⬅️ Назад"],
        ])
        return

    if "Вопрос" in text or "Сұрақ" in text:
        user_states[chat_id] = "question"
        send_message(chat_id, "Напишите ваш вопрос про газоблок 👇\nГазоблок туралы сұрағыңызды жазыңыз 👇")
        return

    if "Контакт" in text or "Байланыс" in text or "📞" in text:
        send_message(chat_id,
            "📞 Наши контакты:\n\n"
            "👤 Наталья: +7 771 799 92 91\n"
            "📍 Алматинская обл., Боралдай,\n"
            "Промзона 71-й разъезд, стр. 61\n\n"
            "⏰ Пн-Сб: 9:00 - 18:00")
        main_menu(chat_id)
        return

    if "Назад" in text or "⬅️" in text:
        user_states[chat_id] = "menu"
        user_data[chat_id] = {}
        main_menu(chat_id)
        return

    # Выбор блока
    if state == "choose_block":
        block_key = text.lower().replace(" ", "").replace("(100мм)","").replace("(150мм)","").replace("(200мм)","").replace("(250мм)","").replace("(300мм)","")
        if block_key in BLOCKS:
            user_data[chat_id]["block"] = block_key
            user_states[chat_id] = "get_length"
            send_message(chat_id, f"✅ {BLOCKS[block_key]['name']} выбран.\n\nВведите длину дома в метрах (например: 14):")
        else:
            send_message(chat_id, "Выберите блок из списка 👆")
        return

    # Сбор размеров
    if state == "get_length":
        try:
            val = float(text.replace(",", "."))
            user_data[chat_id]["length"] = val
            user_states[chat_id] = "get_width"
            send_message(chat_id, "Введите ширину дома в метрах (например: 14):")
        except:
            send_message(chat_id, "❗ Введите число, например: 14")
        return

    if state == "get_width":
        try:
            val = float(text.replace(",", "."))
            user_data[chat_id]["width"] = val
            user_states[chat_id] = "get_height"
            send_message(chat_id, "Введите высоту стен в метрах (например: 3):")
        except:
            send_message(chat_id, "❗ Введите число, например: 14")
        return

    if state == "get_height":
        try:
            val = float(text.replace(",", "."))
            user_data[chat_id]["height"] = val
            user_states[chat_id] = "get_floors"
            send_message(chat_id, "Количество этажей (1, 2 или 3):")
        except:
            send_message(chat_id, "❗ Введите число, например: 3")
        return

    if state == "get_floors":
        try:
            val = int(text)
            if val < 1 or val > 5: raise ValueError
            user_data[chat_id]["floors"] = val
            user_states[chat_id] = "get_openings"
            send_message(chat_id, "Общая площадь окон и дверей в м²\n(если не знаете — напишите 30):")
        except:
            send_message(chat_id, "❗ Введите число от 1 до 5")
        return

    if state == "get_openings":
        try:
            val = float(text.replace(",", "."))
            user_data[chat_id]["openings"] = val
            user_states[chat_id] = "get_inner_walls"
            send_message(chat_id, "Суммарная длина несущих внутренних стен в метрах\n(если не знаете — напишите 0):")
        except:
            send_message(chat_id, "❗ Введите число, например: 30")
        return

    if state == "get_inner_walls":
        try:
            val = float(text.replace(",", "."))
            user_data[chat_id]["inner_walls"] = val
            result = calculate(user_data[chat_id])
            user_states[chat_id] = "menu"
            send_message(chat_id, result)
            main_menu(chat_id)
        except:
            send_message(chat_id, "❗ Введите число, например: 28")
        return

    # Вопрос через Gemini
    if state == "question":
        answer = ask_gemini(text, history)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": answer})
        user_history[chat_id] = history[-10:]
        send_message(chat_id, answer)
        main_menu(chat_id)
        return

    # Любой другой текст — спрашиваем Gemini
    answer = ask_gemini(text, history)
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": answer})
    user_history[chat_id] = history[-10:]
    send_message(chat_id, answer)
    main_menu(chat_id)

def main():
    logger.info("Бот запущен (polling через requests)!")
    offset = 0
    while True:
        try:
            resp = requests.get(f"{BASE_URL}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=35)
            updates = resp.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                if "message" in update and "text" in update["message"]:
                    chat_id = update["message"]["chat"]["id"]
                    text = update["message"]["text"]
                    try:
                        handle_message(chat_id, text)
                    except Exception as e:
                        logger.error(f"Handler error: {e}")
        except Exception as e:
            logger.error(f"Polling error: {e}")
            import time
            time.sleep(5)

if __name__ == "__main__":
    main()
