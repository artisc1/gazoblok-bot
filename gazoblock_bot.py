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
    "б1":   {"name": "Б1 (100мм)",   "thickness": 0.10, "volume": 0.018, "per_pallet": 96,  "price_m3": 29000, "price_pc": 522},
    "б1.5": {"name": "Б1.5 (150мм)", "thickness": 0.15, "volume": 0.027, "per_pallet": 64,  "price_m3": 29000, "price_pc": 783},
    "б2":   {"name": "Б2 (200мм)",   "thickness": 0.20, "volume": 0.036, "per_pallet": 48,  "price_m3": 29000, "price_pc": 1046},
    "б2.5": {"name": "Б2.5 (250мм)", "thickness": 0.25, "volume": 0.045, "per_pallet": 40,  "price_m3": 29000, "price_pc": 1306},
    "б3":   {"name": "Б3 (300мм)",   "thickness": 0.30, "volume": 0.054, "per_pallet": 35,  "price_m3": 29000, "price_pc": 1567},
}

SYSTEM_PROMPT = """Ты — консультант по газоблокам компании из Алматы.
Отвечаешь на русском и казахском языке.
Данные о блоках (цена 29 000 тенге/м³ с НДС, без доставки):
Б1(100мм):522тг/шт, 96шт/поддон; Б1.5(150мм):783тг/шт, 64шт/поддон; Б2(200мм):1046тг/шт, 48шт/поддон; Б2.5(250мм):1306тг/шт, 40шт/поддон; Б3(300мм):1567тг/шт, 35шт/поддон
Формула: V=(P x H - S_проёмов) x T. Запас 6%. Клей: 1 мешок 25кг на 1м³.
Контакт: +7 771 799 92 91 (Наталья), Боралдай, Промзона 71.
Отвечай кратко и дружелюбно. Без markdown."""

user_states   = {}
user_data     = {}
user_history  = {}
processed_ids = set()

MAIN_KB  = [
    ["🧮 Блоктарды есептеу / Расчёт блоков"],
    ["❓ Сұрақ / Вопрос", "📞 Байланыс / Контакты"]
]
BLOCK_KB = [
    ["Б1 (100мм)", "Б1.5 (150мм)"],
    ["Б2 (200мм)", "Б2.5 (250мм)"],
    ["Б3 (300мм)"],
    ["⬅️ Артқа / Назад"]
]
YES_NO_KB = [["✅ Иә / Да", "❌ Жоқ / Нет"], ["⬅️ Артқа / Назад"]]

# Порядок шагов расчёта
STEPS = [
    "choose_block", "get_length", "get_width", "get_height", "get_floors",
    "get_inner_walls",
    "get_window_count", "get_window_size",
    "get_front_door_count", "get_front_door_size",
    "get_inner_door_count", "get_inner_door_size",
    "get_columns"
]

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
    send(chat_id, msg or "Әрекет таңдаңыз / Выберите действие 👇", MAIN_KB)

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
    if clean in BLOCKS: return clean
    for key in BLOCKS:
        if key in clean: return key
    m = re.search(r'б(\d+\.?\d*)', clean)
    if m:
        c = "б" + m.group(1)
        if c in BLOCKS: return c
    return None

def parse_size(text):
    """Парсит размер вида '1.6 х 1.4' или '1.6x1.4' или '1,6 1,4'"""
    text = text.replace(",", ".").replace("х", "x").replace("Х", "x").replace(" x ", "x").replace(" ", "x")
    parts = re.findall(r'\d+\.?\d*', text)
    if len(parts) >= 2:
        return float(parts[0]), float(parts[1])
    return None, None

def calculate(d):
    b = BLOCKS[d["block"]]
    T = b["thickness"]

    # Считаем проёмы
    win_area     = d.get("window_count", 0) * d.get("window_w", 0) * d.get("window_h", 0)
    fdoor_area   = d.get("front_door_count", 0) * d.get("front_door_w", 0) * d.get("front_door_h", 0)
    idoor_area   = d.get("inner_door_count", 0) * d.get("inner_door_w", 0) * d.get("inner_door_h", 0)
    total_openings = win_area + fdoor_area + idoor_area

    # Объём колонн вычитаем из кладки
    col_count  = d.get("column_count", 0)
    col_volume = col_count * T * T * d["height"] * d["floors"]  # T x T x H на каждую колонну

    perimeter  = 2*(d["length"]+d["width"]) + d["inner_walls"]
    net_area   = perimeter * d["height"] * d["floors"] - total_openings
    volume     = net_area * T - col_volume
    vol_r      = volume * 1.06
    pieces     = vol_r / b["volume"]
    pallets    = pieces / b["per_pallet"]
    cost       = vol_r * b["price_m3"]

    lines = [
        f"✅ Есеп нәтижесі / Результат расчёта\n",
        f"🏠 {d['length']}x{d['width']} м | {d['floors']} қабат | {d['height']} м",
        f"🧱 {b['name']}\n",
        f"📐 Периметр: {perimeter:.1f} м",
    ]
    if d.get("window_count", 0):
        lines.append(f"🪟 Терезе / Окна: {d['window_count']} шт × {d['window_w']}x{d['window_h']} м = {win_area:.2f} м²")
    if d.get("front_door_count", 0):
        lines.append(f"🚪 Кіреберіс есік / Вх. дверь: {d['front_door_count']} шт × {d['front_door_w']}x{d['front_door_h']} м = {fdoor_area:.2f} м²")
    if d.get("inner_door_count", 0):
        lines.append(f"🚪 Ішкі есіктер / Межк. двери: {d['inner_door_count']} шт × {d['inner_door_w']}x{d['inner_door_h']} м = {idoor_area:.2f} м²")
    lines.append(f"🪟🚪 Проёмдар / Проёмы барлығы: {total_openings:.2f} м²")
    if col_count:
        lines.append(f"🏛 Бағандар / Колонны: {col_count} шт (вычтено {col_volume:.2f} м³)")
    lines += [
        f"\nҚалау ауданы / Площадь кладки: {net_area:.1f} м²",
        f"Көлем / Объём (+6%): {vol_r:.1f} м³\n",
        f"📦 Блок: ~{int(pieces):,} дана/шт",
        f"📦 Паллет / Поддон: ~{int(pallets)+1} дана/шт",
        f"🪣 Желім / Клей: ~{int(vol_r)+1} қап/мешков (25кг)\n",
        f"💰 Бағасы / Цена за шт: {b['price_pc']:,} тенге",
        f"💰 Құны / Стоимость: ~{int(cost):,} тенге",
        f"(НДС қосылған, жеткізусіз / с НДС, без доставки)\n",
        f"📞 +7 771 799 92 91 (Наталья)"
    ]
    return "\n".join(lines)

def handle(chat_id, text):
    text = text.strip()
    state   = user_states.get(chat_id, "menu")
    history = user_history.get(chat_id, [])

    if text.startswith("/start"):
        user_states[chat_id]  = "menu"
        user_data[chat_id]    = {}
        user_history[chat_id] = []
        main_menu(chat_id,
            "👋 Сәлем! Привет!\n\n"
            "Мен газоблок бойынша сізге көмектесемін.\n"
            "Я помогу рассчитать газоблок для вашего дома.")
        return

    if "Назад" in text or "Артқа" in text:
        user_data[chat_id] = {}
        main_menu(chat_id)
        return

    if "Байланыс" in text or "Контакт" in text or "📞" in text:
        send(chat_id,
            "📞 Байланыс / Контакты:\n\n"
            "👤 Наталья: +7 771 799 92 91\n"
            "📍 Алматы обл., Боралдай,\n"
            "Промзона 71-й разъезд, стр. 61\n\n"
            "⏰ Дүй-Сенбі / Пн-Сб: 9:00-18:00")
        main_menu(chat_id)
        return

    if "есептеу" in text.lower() or "Расчёт" in text or "расчет" in text.lower() or "🧮" in text:
        user_states[chat_id] = "choose_block"
        user_data[chat_id]   = {}
        send(chat_id, "Қандай блок? / Какой тип блока?", BLOCK_KB)
        return

    if "Сұрақ" in text or "Вопрос" in text or "❓" in text:
        user_states[chat_id] = "question"
        send(chat_id, "Сұрағыңызды жазыңыз 👇\nНапишите ваш вопрос 👇")
        return

    # ── Шаги расчёта ──────────────────────────────────────────────────────────

    if state == "choose_block":
        key = find_block(text)
        if key:
            user_data[chat_id] = {"block": key}
            user_states[chat_id] = "get_length"
            send(chat_id, f"✅ {BLOCKS[key]['name']} таңдалды.\n\nҮйдің ұзындығы (м) / Длина дома (м):")
        else:
            send(chat_id, "Тізімнен таңдаңыз 👆 / Выберите из списка 👆", BLOCK_KB)
        return

    if state == "get_length":
        try:
            user_data[chat_id]["length"] = float(text.replace(",","."))
            user_states[chat_id] = "get_width"
            send(chat_id, "Үйдің ені (м) / Ширина дома (м):")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 14")
        return

    if state == "get_width":
        try:
            user_data[chat_id]["width"] = float(text.replace(",","."))
            user_states[chat_id] = "get_height"
            send(chat_id, "Қабырға биіктігі (м) / Высота стен (м):")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 14")
        return

    if state == "get_height":
        try:
            user_data[chat_id]["height"] = float(text.replace(",","."))
            user_states[chat_id] = "get_floors"
            send(chat_id, "Қабат саны / Количество этажей (1, 2, 3):")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 3")
        return

    if state == "get_floors":
        try:
            val = int(float(text.replace(",",".")))
            if val < 1 or val > 5: raise ValueError
            user_data[chat_id]["floors"] = val
            user_states[chat_id] = "get_inner_walls"
            send(chat_id, "Ішкі қабырғалар ұзындығы (м) / Длина внутренних стен (м)\n(білмесеңіз / не знаете — 0):")
        except:
            send(chat_id, "❗ 1-5 аралығында / Введите от 1 до 5")
        return

    if state == "get_inner_walls":
        try:
            user_data[chat_id]["inner_walls"] = float(text.replace(",","."))
            user_states[chat_id] = "get_window_count"
            send(chat_id, "🪟 Терезе саны / Количество окон:")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 29")
        return

    if state == "get_window_count":
        try:
            val = int(float(text.replace(",",".")))
            user_data[chat_id]["window_count"] = val
            if val == 0:
                user_data[chat_id]["window_w"] = 0
                user_data[chat_id]["window_h"] = 0
                user_states[chat_id] = "get_front_door_count"
                send(chat_id, "🚪 Кіреберіс есік саны / Кол-во входных дверей:")
            else:
                user_states[chat_id] = "get_window_size"
                send(chat_id, f"🪟 Терезе өлшемі / Размер окна (ен x биіктік / ширина x высота):\nМысалы / Например: 1.6 x 1.4")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 7")
        return

    if state == "get_window_size":
        w, h = parse_size(text)
        if w and h:
            user_data[chat_id]["window_w"] = w
            user_data[chat_id]["window_h"] = h
            user_states[chat_id] = "get_front_door_count"
            send(chat_id, "🚪 Кіреберіс есік саны / Кол-во входных дверей:")
        else:
            send(chat_id, "❗ Форматты сақтаңыз / Введите в формате: 1.6 x 1.4")
        return

    if state == "get_front_door_count":
        try:
            val = int(float(text.replace(",",".")))
            user_data[chat_id]["front_door_count"] = val
            if val == 0:
                user_data[chat_id]["front_door_w"] = 0
                user_data[chat_id]["front_door_h"] = 0
                user_states[chat_id] = "get_inner_door_count"
                send(chat_id, "🚪 Ішкі есік саны / Кол-во межкомнатных дверей:")
            else:
                user_states[chat_id] = "get_front_door_size"
                send(chat_id, "🚪 Кіреберіс есік өлшемі / Размер входной двери:\nМысалы / Например: 1.4 x 2.1")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 1")
        return

    if state == "get_front_door_size":
        w, h = parse_size(text)
        if w and h:
            user_data[chat_id]["front_door_w"] = w
            user_data[chat_id]["front_door_h"] = h
            user_states[chat_id] = "get_inner_door_count"
            send(chat_id, "🚪 Ішкі есік саны / Кол-во межкомнатных дверей:")
        else:
            send(chat_id, "❗ Форматты сақтаңыз / Введите в формате: 1.4 x 2.1")
        return

    if state == "get_inner_door_count":
        try:
            val = int(float(text.replace(",",".")))
            user_data[chat_id]["inner_door_count"] = val
            if val == 0:
                user_data[chat_id]["inner_door_w"] = 0
                user_data[chat_id]["inner_door_h"] = 0
                user_states[chat_id] = "get_columns"
                send(chat_id, "🏛 Арматуралы бағандар бар ма? / Есть армированные колонны (стойки)?\n(Иә/Да = санын жазыңыз / напишите кол-во, Жоқ/Нет = 0)", YES_NO_KB)
            else:
                user_states[chat_id] = "get_inner_door_size"
                send(chat_id, "🚪 Ішкі есік өлшемі / Размер межкомнатной двери:\nМысалы / Например: 0.9 x 2.1")
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 8")
        return

    if state == "get_inner_door_size":
        w, h = parse_size(text)
        if w and h:
            user_data[chat_id]["inner_door_w"] = w
            user_data[chat_id]["inner_door_h"] = h
            user_states[chat_id] = "get_columns"
            send(chat_id, "🏛 Арматуралы бағандар бар ма? / Есть армированные колонны (стойки)?", YES_NO_KB)
        else:
            send(chat_id, "❗ Форматты сақтаңыз / Введите в формате: 0.9 x 2.1")
        return

    if state == "get_columns":
        low = text.lower()
        if "жоқ" in low or "нет" in low or "❌" in text or text == "0":
            user_data[chat_id]["column_count"] = 0
        elif "иә" in low or "да" in low or "✅" in text:
            user_states[chat_id] = "get_column_count"
            send(chat_id, "🏛 Баған санын енгізіңіз / Введите количество колонн:")
            return
        else:
            try:
                user_data[chat_id]["column_count"] = int(float(text.replace(",",".")))
            except:
                send(chat_id, "❗ Иә/Да немесе Жоқ/Нет / Ответьте Да или Нет", YES_NO_KB)
                return
        # Считаем
        result = calculate(user_data[chat_id])
        user_data[chat_id] = {}
        user_states[chat_id] = "menu"
        send(chat_id, result, MAIN_KB)
        return

    if state == "get_column_count":
        try:
            user_data[chat_id]["column_count"] = int(float(text.replace(",",".")))
            result = calculate(user_data[chat_id])
            user_data[chat_id] = {}
            user_states[chat_id] = "menu"
            send(chat_id, result, MAIN_KB)
        except:
            send(chat_id, "❗ Санды енгізіңіз / Введите число, например: 4")
        return

    # Вопрос через Gemini
    if state == "question":
        answer = ask_gemini(text, history)
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": answer})
        user_history[chat_id] = history[-10:]
        send(chat_id, answer, MAIN_KB)
        user_states[chat_id] = "menu"
        return

    # Любой текст → Gemini
    answer = ask_gemini(text, history)
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": answer})
    user_history[chat_id] = history[-10:]
    send(chat_id, answer, MAIN_KB)
    user_states[chat_id] = "menu"

def main():
    logger.info("Бот запущен!")
    offset = 0
    while True:
        try:
            resp = requests.get(f"{BASE_URL}/getUpdates",
                                params={"offset": offset, "timeout": 30}, timeout=35)
            for update in resp.json().get("result", []):
                uid = update["update_id"]
                offset = uid + 1
                if uid in processed_ids:
                    continue
                processed_ids.add(uid)
                if len(processed_ids) > 1000:
                    processed_ids.clear()
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
