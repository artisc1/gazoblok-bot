#!/usr/bin/env python3
import os, logging, requests, re, time
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
Б1(100мм):96шт/поддон, Б1.5(150мм):64шт/поддон, Б2(200мм):48шт/поддон, Б2.5(250мм):40шт/поддон, Б3(300мм):35шт/поддон
Формула: V=(P x H - S_проёмов) x T. Запас 6%. Клей: 1 мешок 25кг на 1м³.
Контакт: +7 771 799 92 91 (Наталья), Боралдай, Промзона 71.
Отвечай кратко и дружелюбно. Без markdown."""

user_states  = {}
user_data    = {}
user_history = {}

MAIN_KB  = [["🧮 Блок есептеу / Расчёт блоков"], ["❓ Сұрақ / Вопрос", "📞 Байланыс / Контакты"]]
BLOCK_KB = [["Б1 (100мм)", "Б1.5 (150мм)"], ["Б2 (200мм)", "Б2.5 (250мм)"], ["Б3 (300мм)"], ["⬅️ Артқа / Назад"]]

def send(chat_id, text, kb=None):
    body = {"chat_id": chat_id, "text": text}
    if kb is not None:
        body["reply_markup"] = {"keyboard": kb, "resize_keyboard": True, "one_time_keyboard": False}
    try:
        requests.post(f"{BASE_URL}/sendMessage", json=body, timeout=10)
    except Exception as e:
        logger.error(f"Send error: {e}")

def main_menu(chat_id, msg=None):
    user_states[chat_id] = "menu"
    if msg is None:
        msg = "Выберите действие / Әрекет таңдаңыз 👇"
    send(chat_id, msg, MAIN_KB)

def ask_gemini(question, history):
    try:
        model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
        chat_history = [{"role": "user" if m["role"]=="user" else "model", "parts": [m["content"]]} for m in history]
        chat = model.start_chat(history=chat_history)
        return chat.send_message(question).text
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "Қате болды. Кейінірек қайталаңыз.\nОшибка, попробуйте позже."

def find_block(text):
    clean = text.lower().replace(" ","").replace(",",".") \
                .replace("(100мм)","").replace("(150мм)","") \
                .replace("(200мм)","").replace("(250мм)","").replace("(300мм)","")
    if clean in BLOCKS:
        return clean
    for key in BLOCKS:
        if key in clean:
            return key
    m = re.search(r'б(\d+\.?\d*)', clean)
    if m:
        c = "б" + m.group(1)
        if c in BLOCKS:
            return c
    return None

def calculate(d):
    b = BLOCKS[d["block"]]
    T = b["thickness"]
    perimeter = 2*(d["length"]+d["width"]) + d["inner_walls"]
    net_area = perimeter * d["height"] * d["floors"] - d["openings"]
    volume = net_area * T
    vol_r = volume * 1.06
    pieces = vol_r / b["volume"]
    pallets = pieces / b["per_pallet"]
    cost = vol_r * b["price_m3"]
    return (
        f"✅ Есеп нәтижесі / Результат расчёта\n\n"
        f"🏠 Үй / Дом: {d['length']}x{d['width']} м, {d['floors']} қабат/этаж, биіктік/высота {d['height']} м\n"
        f"🧱 Блок: {b['name']}\n\n"
        f"📐 Қабырға периметрі / Периметр стен: {perimeter:.1f} м\n"
        f"📐 Қалау ауданы / Площадь кладки: {net_area:.1f} м²\n"
        f"📐 Көлем запассыз / Объём без запаса: {volume:.1f} м³\n"
        f"📐 Көлем 6% запаспен / Объём с запасом 6%: {vol_r:.1f} м³\n\n"
        f"📦 Блок саны / Блоков: ~{int(pieces):,} дана/шт\n"
        f"📦 Паллет саны / Поддонов: ~{int(pallets)+1} дана/шт\n"
        f"🪣 Желім / Клей: ~{int(vol_r)+1} қап/мешков (25 кг)\n\n"
        f"💰 Құны / Стоимость: ~{int(cost):,} тенге\n"
        f"(НДС қосылған, жеткізусіз / с НДС, без доставки)\n\n"
        f"📞 Тапсырыс / Заказ: +7 771 799 92 91 (Наталья)"
    )

def handle(chat_id, text):
    text = text.strip()
    state   = user_states.get(chat_id, "menu")
    data    = user_data.get(chat_id, {})
    history = user_history.get(chat_id, [])

    # /start
    if text.startswith("/start"):
        user_states[chat_id]  = "menu"
        user_data[chat_id]    = {}
        user_history[chat_id] = []
        main_menu(chat_id,
            "👋 Сәлем! Привет!\n\n"
            "Мен газоблок бойынша сізге көмектесемін.\n"
            "Я помогу рассчитать газоблок для вашего дома.\n\n"
            "Выберите действие / Әрекет таңдаңыз 👇")
        return

    # Назад
    if "Назад" in text or "Артқа" in text or text == "⬅️":
        user_data[chat_id] = {}
        main_menu(chat_id)
        return

    # Контакты
    if "Контакт" in text or "Байланыс" in text or "📞" in text:
        send(chat_id,
            "📞 Байланыс / Контакты:\n\n"
            "👤 Наталья: +7 771 799 92 91\n"
            "📍 Алматы обл., Боралдай,\n"
            "Промзона 71-й разъезд, стр. 61\n\n"
            "⏰ Дүйсенбі-Сенбі / Пн-Сб: 9:00-18:00")
        main_menu(chat_id)
        return

    # Расчёт блоков
    if "есептеу" in text.lower() or "Расчёт" in text or "расчет" in text.lower():
        user_states[chat_id] = "choose_block"
        user_data[chat_id]   = {}
        send(chat_id, "Қандай блок таңдайсыз? / Какой тип блока выбираете?", BLOCK_KB)
        return

    # Вопрос
    if "Сұрақ" in text or "Вопрос" in text or "❓" in text:
        user_states[chat_id] = "question"
        send(chat_id, "Сұрағыңызды жазыңыз 👇\nНапишите ваш вопрос про газоблок 👇")
        return

    # Выбор блока
    if state == "choose_block":
        key = find_block(text)
        if key:
            user_data[chat_id] = {"block": key}
            user_states[chat_id] = "get_length"
            send(chat_id, f"✅ {BLOCKS[key]['name']} таңдалды / выбран.\n\nҮйдің ұзындығын метрмен енгізіңіз:\nВведите длину дома в метрах (мысалы/например: 14):")
        else:
            send(chat_id, "Тізімнен блок таңдаңыз 👆\nВыберите блок из списка 👆", BLOCK_KB)
        return

    if state == "get_length":
        try:
            user_data[chat_id]["length"] = float(text.replace(",","."))
            user_states[chat_id] = "get_width"
            send(chat_id, "Үйдің енін метрмен енгізіңіз:\nВведите ширину дома в метрах (мысалы/например: 14):")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 14")
        return

    if state == "get_width":
        try:
            user_data[chat_id]["width"] = float(text.replace(",","."))
            user_states[chat_id] = "get_height"
            send(chat_id, "Қабырға биіктігін метрмен енгізіңіз:\nВведите высоту стен в метрах (мысалы/например: 3):")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 14")
        return

    if state == "get_height":
        try:
            user_data[chat_id]["height"] = float(text.replace(",","."))
            user_states[chat_id] = "get_floors"
            send(chat_id, "Қабат санын енгізіңіз:\nКоличество этажей (1, 2 или 3):")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 3")
        return

    if state == "get_floors":
        try:
            val = int(float(text.replace(",",".")))
            if val < 1 or val > 5: raise ValueError
            user_data[chat_id]["floors"] = val
            user_states[chat_id] = "get_openings"
            send(chat_id, "Есіктер мен терезелердің жалпы ауданы м²:\nОбщая площадь окон и дверей в м²\n(білмесеңіз / если не знаете — напишите 30):")
        except:
            send(chat_id, "❗ 1-ден 5-ке дейін сан енгізіңіз / Введите цифру от 1 до 5")
        return

    if state == "get_openings":
        try:
            user_data[chat_id]["openings"] = float(text.replace(",","."))
            user_states[chat_id] = "get_inner_walls"
            send(chat_id, "Ішкі тасымалдаушы қабырғалардың жалпы ұзындығы (м):\nСуммарная длина несущих внутренних стен в метрах\n(білмесеңіз / если не знаете — напишите 0):")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 34")
        return

    if state == "get_inner_walls":
        try:
            user_data[chat_id]["inner_walls"] = float(text.replace(",","."))
            result = calculate(user_data[chat_id])
            user_data[chat_id] = {}
            main_menu(chat_id, result)
        except Exception as e:
            logger.error(f"Calc error: {e}")
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 29")
        return

    # Вопрос через Gemini
    if state == "question":
        answer = ask_gemini(text, history)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": answer})
        user_history[chat_id] = history[-10:]
        send(chat_id, answer)
        main_menu(chat_id)
        return

    # Любой текст → Gemini
    answer = ask_gemini(text, history)
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": answer})
    user_history[chat_id] = history[-10:]
    send(chat_id, answer)
    main_menu(chat_id)

def main():
    logger.info("Бот запущен!")
    offset = 0
    while True:
        try:
            resp = requests.get(f"{BASE_URL}/getUpdates",
                                params={"offset": offset, "timeout": 30}, timeout=35)
            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                if msg.get("text"):
                    try:
                        handle(msg["chat"]["id"], msg["text"])
                    except Exception as e:
                        logger.error(f"Handler error: {e}")
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
